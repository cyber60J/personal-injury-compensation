from __future__ import annotations

import copy
from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from personal_injury.collection.nbs import INDICATORS, NBS_ORIGIN, NbsSource
from personal_injury.collection.source_archive import ArchiveStore


FIXTURES = Path(__file__).parent / "fixtures" / "nbs"
METRICS = list(INDICATORS)
SAMPLE_FILES = ["beijing_2024_income.json", "beijing_2024_consumption.json"]


class OfficialApiReplay:
    """Synthetic catalog around unmodified, captured official value responses."""

    def __init__(self):
        self.calls = []
        self.responses = {metric: json.loads((FIXTURES / file).read_bytes()) for metric, file in zip(METRICS, SAMPLE_FILES)}
        self.indicators = {}
        for metric, body in self.responses.items():
            self.indicators[metric] = copy.deepcopy(body["data"][0]["values"][0])
            self.indicators[metric]["kj1_name"] = "城镇"
        self.root_name = "分省年度数据"
        self.duplicate_indicator = False

    def __call__(self, session, url, official_url, **kwargs):
        assert official_url == NBS_ORIGIN
        assert url.startswith(NBS_ORIGIN + "/")
        assert kwargs["timeout"] == 12
        self.calls.append((url, kwargs))
        parsed = urlsplit(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        endpoint = parsed.path.rsplit("/", 1)[-1]
        data = None
        if endpoint == "queryIndexTreeAsync":
            assert params["code"] == ["6"]
            parent = params["pid"][0]
            if not parent:
                data = [{"_id": "root", "name": self.root_name}]
            elif parent == "root":
                data = [{"_id": "living", "name": "人民生活", "treeinfo_pid": "root"}]
            elif parent == "living":
                data = [
                    {"_id": indicator["catalogid"], "name": INDICATORS[metric], "treeinfo_pid": "living", "isLeaf": True}
                    for metric, indicator in self.indicators.items()
                ]
        elif endpoint == "queryIndicatorsByCid":
            records = [item for item in self.indicators.values() if item["catalogid"] == params["cid"][0]]
            if self.duplicate_indicator:
                records += copy.deepcopy(records)
            data = {"list": records}
        elif endpoint == "getDaCatalogTreeByIndicatorCid":
            data = [{"_id": "all", "name": "全部地区"}]
        elif endpoint == "getDasByDaCatalogId":
            data = [{"catalog_id": "all", "show_name": "北京市", "name_value": "110000000000"}]
        elif endpoint == "esData":
            assert kwargs["method"] == "POST"
            payload = kwargs["json_body"]
            assert payload["dts"] == ["2024YY"]
            assert payload["das"] == [{"text": "北京市", "value": "110000000000"}]
            for metric, indicator in self.indicators.items():
                if payload["indicatorIds"] == [indicator["_id"]]:
                    return SimpleNamespace(status_code=200), json.dumps(self.responses[metric], ensure_ascii=False).encode("utf-8")
        if data is None:
            raise AssertionError(f"Unexpected request: {url}")
        return SimpleNamespace(status_code=200), json.dumps({"success": True, "data": data}, ensure_ascii=False).encode("utf-8")


def make_source(tmp_path, replay=None):
    replay = replay or OfficialApiReplay()
    archive = ArchiveStore(tmp_path / "archive")
    return NbsSource(object(), fetch_content=replay, archive=archive), replay, archive


def test_official_beijing_2024_fixtures_replay_with_dimension_and_archive_proof(tmp_path):
    source, replay, archive = make_source(tmp_path)
    result = source.collect("北京市", 2024)
    assert result["data"] == {METRICS[0]: 92464.0, METRICS[1]: 53214.0}
    assert result["warnings"] == []
    assert result["publish_date"] == ""  # retrieval time is not publication time
    evidence = result["evidence"][METRICS[0]]
    assert evidence["raw_value"] == "92464"
    assert evidence["raw_unit"] == "元"
    assert evidence["statistical_year"] == 2024
    assert evidence["expected_year"] == 2024
    assert evidence["region"] == evidence["expected_region"] == "北京市"
    assert evidence["scope"]["population"] == "城镇居民"
    assert evidence["json_pointer"] == "/data/0/values/0/value"
    assert evidence["locator"] == {"type": "nbs_json", "json_pointer": "/data/0/values/0/value"}
    assert json.loads(evidence["snippet"])["record"]["value"] == "92464"
    assert evidence["conversion"] == {"factor": 1, "operation": "92464 × 1"}
    assert evidence["extract_method"] == "nbs_json"
    assert evidence["source_title"] == "国家统计局分省年度数据"
    assert evidence["transport_secure"] is True
    assert evidence["source_domain_verified"] is True
    assert datetime.fromisoformat(evidence["retrieved_at"]).utcoffset() == timedelta(0)
    assert evidence["validation_status"] == "verified"
    assert json.loads(archive.resolve(evidence["archive_sha256"]).read_bytes()) == replay.responses[METRICS[0]]
    assert all(archive.resolve(item["archive_sha256"]) for item in evidence["metadata_sources"])
    manifest = json.loads((archive.root / evidence["archive_metadata_path"]).read_bytes())
    assert manifest["metadata"]["request"]["json"]["dts"] == ["2024YY"]
    assert manifest["metadata"]["retrieved_at"] == evidence["retrieved_at"]


def test_validated_final_response_url_is_saved_separately_from_request_url(tmp_path):
    replay = OfficialApiReplay()

    def with_final_url(session, url, official_url, **kwargs):
        response, content = replay(session, url, official_url, **kwargs)
        response.url = url + ("&" if "?" in url else "?") + "canonical=1"
        return response, content

    source, _, archive = make_source(tmp_path, with_final_url)
    evidence = source.collect("北京市", 2024)["evidence"][METRICS[0]]
    assert evidence["source_url"] == evidence["request"]["url"] + "?canonical=1"
    assert evidence["transport_secure"] is True
    manifest = json.loads((archive.root / evidence["archive_metadata_path"]).read_bytes())
    assert manifest["source_url"] == evidence["source_url"]
    assert manifest["metadata"]["request"]["url"] == evidence["request"]["url"]


@pytest.mark.parametrize("change", [
    {"_id": "other-indicator"}, {"catalogid": "national-catalog"},
    {"i_showname": "全体居民人均可支配收入 (元)"},
    {"da": "000000000000"}, {"da_name": "全国"},
    {"du_name": "万元"}, {"value": None}, {"value": ""},
    {"value": "NaN"}, {"value": "Infinity"}, {"value": "0"}, {"value": True},
])
def test_wrong_dimensions_or_missing_values_stay_review_candidates(tmp_path, change):
    source, replay, _ = make_source(tmp_path)
    replay.responses[METRICS[0]]["data"][0]["values"][0].update(change)
    result = source.collect("北京市", 2024)
    assert METRICS[0] not in result["data"]
    candidate = result["candidates"][METRICS[0]][0]
    assert candidate["review_reasons"]
    assert candidate["validation_status"] == "pending"
    assert result["evidence"][METRICS[0]]["review_reasons"]
    assert result["data"][METRICS[1]] == 53214.0


@pytest.mark.parametrize("code,name", [("2023YY", "2023年"), ("202412MM", "2024年"), ("2024YY", "2023年")])
def test_year_and_annual_granularity_must_both_match(tmp_path, code, name):
    source, replay, _ = make_source(tmp_path)
    replay.responses[METRICS[0]]["data"][0].update(code=code, name=name)
    result = source.collect("北京市", 2024)
    assert METRICS[0] not in result["data"]
    candidate = result["candidates"][METRICS[0]][0]
    assert "统计期" in candidate["review_reasons"][0]
    assert candidate["statistical_year"] == (2023 if code == "2023YY" else None)
    assert candidate["expected_year"] == 2024
    assert candidate["statistical_period"] == code
    assert candidate["statistical_period_name"] == name


def test_candidate_displays_response_region_not_requested_region(tmp_path):
    source, replay, _ = make_source(tmp_path)
    replay.responses[METRICS[0]]["data"][0]["values"][0].update(da_name="全国", da="000000000000")
    result = source.collect("北京市", 2024)
    candidate = result["candidates"][METRICS[0]][0]
    assert candidate["region"] == "全国"
    assert candidate["region_code"] == "000000000000"
    assert candidate["expected_region"] == "北京市"
    assert candidate["expected_region_code"] == "110000000000"
    assert candidate["validation_status"] == "pending"
    assert METRICS[0] not in result["data"]


def test_conflicting_values_are_retained_and_neither_is_selected(tmp_path):
    source, replay, _ = make_source(tmp_path)
    values = replay.responses[METRICS[0]]["data"][0]["values"]
    values.append({**values[0], "value": "99999"})
    result = source.collect("北京市", 2024)
    assert METRICS[0] not in result["data"]
    assert len(result["candidates"][METRICS[0]]) == 2
    assert all(item["validation_status"] == "pending" for item in result["candidates"][METRICS[0]])
    evidence = result["evidence"][METRICS[0]]
    assert evidence["validation_status"] == "pending"
    assert {item["value"] for item in evidence["conflicts"]} == {92464.0, 99999.0}
    assert all(item["review_reasons"] for item in evidence["conflicts"])


@pytest.mark.parametrize("region", ["深圳市", "厦门市", "宁波市", "青岛市", "大连市", "全国"])
def test_unsupported_city_never_falls_back_to_province_or_national(tmp_path, region):
    source, replay, _ = make_source(tmp_path)
    result = source.collect(region, 2024)
    assert result["data"] == {}
    assert "不使用所在省或全国" in result["warnings"][0]
    assert replay.calls == []


def test_ambiguous_indicator_metadata_is_not_selected(tmp_path):
    source, replay, _ = make_source(tmp_path)
    replay.duplicate_indicator = True
    result = source.collect("北京市", 2024)
    assert result["data"] == {}
    assert not any(url.endswith("esData") for url, kwargs in replay.calls)


def test_national_root_is_not_accepted_as_provincial(tmp_path):
    source, replay, _ = make_source(tmp_path)
    replay.root_name = "年度数据"
    result = source.collect("北京市", 2024)
    assert result["data"] == {}
    assert len(replay.calls) == 1


def test_cache_reuses_only_this_run_and_does_not_leak_returned_evidence_mutation(tmp_path):
    source, replay, _ = make_source(tmp_path)
    first = source.collect("北京市", 2024)
    count = len(replay.calls)
    first["evidence"][METRICS[0]]["indicator_metadata"]["_id"] = "changed-by-caller"
    second = source.collect("北京市", 2024)
    assert len(replay.calls) == count
    assert second["evidence"][METRICS[0]]["indicator_metadata"]["_id"] != "changed-by-caller"
    fresh, _, _ = make_source(tmp_path, replay)
    assert fresh.collect("北京市", 2024)["data"]
    assert len(replay.calls) > count


def test_first_network_failure_stops_requests_for_remaining_regions(tmp_path):
    calls = []

    def fail(*args, **kwargs):
        calls.append(args)
        raise TimeoutError("test timeout")

    source, _, _ = make_source(tmp_path, fail)
    first = source.collect("北京市", 2024)
    second = source.collect("江苏省", 2024)
    assert not first["data"] and not second["data"]
    assert len(calls) == 1
    assert "停止请求" in second["warnings"][0]
