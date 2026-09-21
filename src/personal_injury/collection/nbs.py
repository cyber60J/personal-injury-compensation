"""国家统计局分省年度城镇收支；精确维度匹配后才生成可复核数值。"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import math
import re
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit

NBS_ORIGIN = "https://data.stats.gov.cn"
NBS_API = NBS_ORIGIN + "/dg/website/publicrelease/web/external/"
NBS_PAGE = NBS_ORIGIN + "/dg/website/page.html"
EXTRACTOR_VERSION = "nbs-provincial-annual-v1"
INDICATORS = {
    "城镇居民人均可支配收入": "居民人均可支配收入",
    "城镇居民人均消费支出": "居民人均消费支出",
}
PROVINCE_CODES = {
    "北京市": "11", "天津市": "12", "河北省": "13", "山西省": "14",
    "内蒙古自治区": "15", "辽宁省": "21", "吉林省": "22", "黑龙江省": "23",
    "上海市": "31", "江苏省": "32", "浙江省": "33", "安徽省": "34",
    "福建省": "35", "江西省": "36", "山东省": "37", "河南省": "41",
    "湖北省": "42", "湖南省": "43", "广东省": "44", "广西壮族自治区": "45",
    "海南省": "46", "重庆市": "50", "四川省": "51", "贵州省": "52",
    "云南省": "53", "西藏自治区": "54", "陕西省": "61", "甘肃省": "62",
    "青海省": "63", "宁夏回族自治区": "64", "新疆维吾尔自治区": "65",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace("（", "(").replace("）", ")")


def _one(items: Any, key: str, value: str) -> dict:
    if not isinstance(items, list):
        raise ValueError("国家统计局目录结构发生变化")
    matches = [item for item in items if isinstance(item, dict) and _text(item.get(key)) == value]
    if len(matches) != 1:
        raise ValueError(f"国家统计局目录无法唯一确定：{value}")
    return matches[0]


class NbsSource:
    """只接入分省年度数据；目录和响应仅在当前实例内缓存。

    fetch_content 必须执行官方域名、重定向和响应大小校验，支持
    method/json_body/timeout 参数。传入独立无自动重试的 session，可使首次
    网络故障也有界；发生请求或协议故障后本实例停止请求，下一次运行再尝试。
    verified 仅表示抽取维度通过校验，不代表人工批准或法律适用确认。
    """

    def __init__(self, session: Any, *, fetch_content: Callable, archive: Any, logger=None):
        self.session = session
        self.fetch_content = fetch_content
        self.archive = archive
        self.logger = logger
        self._cache: dict[str, tuple[dict, dict]] = {}
        self._disabled = ""
        self._catalogs: dict[str, dict] | None = None
        self._catalog_errors: dict[str, str] = {}

    def _request(self, endpoint: str, *, params=None, payload=None) -> tuple[dict, dict]:
        url = NBS_API + endpoint
        if params is not None:
            url += "?" + urlencode(params)
        method = "POST" if payload is not None else "GET"
        request = {"method": method, "url": url, "json": payload}
        key = json.dumps(request, sort_keys=True, ensure_ascii=False)
        if key in self._cache:
            return self._cache[key]
        if self._disabled:
            raise ValueError(self._disabled)
        try:
            kwargs = {"timeout": 12}
            if payload is not None:
                kwargs.update(method="POST", json_body=payload)
            response, content = self.fetch_content(self.session, url, NBS_ORIGIN, **kwargs)
            final_url = getattr(response, "url", None) or url
            retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            transport = {
                "retrieved_at": retrieved_at,
                "transport_secure": urlsplit(final_url).scheme == "https",
                # fetch_content has checked every request/redirect and the final
                # response against NBS_ORIGIN before returning these bytes.
                "source_domain_verified": True,
            }
            saved = self.archive.save(
                content, source_url=final_url, content_type="application/json",
                metadata={"request": request, "extractor_version": EXTRACTOR_VERSION, **transport},
            )
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code}")
            decoded = json.loads(content)
            if not isinstance(decoded, dict) or decoded.get("success") is not True:
                raise ValueError("接口未返回成功的 JSON 数据")
            result = decoded, {**saved, **transport, "request": request, "source_url": final_url}
            self._cache[key] = result
            return result
        except Exception as exc:
            self._disabled = f"国家统计局本次运行停止请求：{type(exc).__name__}: {exc}"
            raise ValueError(self._disabled) from exc

    def _tree(self, parent: str) -> tuple[list, dict]:
        body, proof = self._request("new/queryIndexTreeAsync", params={"pid": parent, "code": 6})
        return body.get("data"), proof

    def _prepare(self) -> None:
        if self._catalogs is not None:
            return
        try:
            roots, root_proof = self._tree("")
            root = _one(roots, "name", "分省年度数据")
            children, child_proof = self._tree(root["_id"])
            living = _one(children, "name", "人民生活")
            if living.get("treeinfo_pid") != root["_id"]:
                raise ValueError("人民生活目录父级不匹配")
            leaves, leaf_proof = self._tree(living["_id"])
            self._catalogs = {}
            for metric, leaf_name in INDICATORS.items():
                try:
                    leaf = _one(leaves, "name", leaf_name)
                    if leaf.get("treeinfo_pid") != living["_id"] or leaf.get("isLeaf") is not True:
                        raise ValueError("指标目录父级或层级不匹配")
                    cid = leaf["_id"]
                    body, indicator_proof = self._request("new/queryIndicatorsByCid", params={"cid": cid})
                    indicator = _one(body.get("data", {}).get("list"), "i_showname", metric + "(元)")
                    if (indicator.get("catalogid") != cid or _text(indicator.get("du_name")) != "元"
                            or _text(indicator.get("kj1_name")) != "城镇" or not indicator.get("_id")):
                        raise ValueError("指标元数据口径、单位或目录不匹配")
                    body, da_proof = self._request("getDaCatalogTreeByIndicatorCid", params={"indicatorCid": cid})
                    area_catalog = _one(body.get("data"), "name", "全部地区")
                    body, members_proof = self._request("getDasByDaCatalogId", params={"daCid": area_catalog["_id"]})
                    self._catalogs[metric] = {
                        "root": root, "leaf": leaf, "indicator": indicator,
                        "areas": body.get("data"), "area_catalog_id": area_catalog["_id"],
                        "proofs": [root_proof, child_proof, leaf_proof, indicator_proof, da_proof, members_proof],
                    }
                except (ValueError, KeyError, TypeError, AttributeError) as exc:
                    self._catalog_errors[metric] = str(exc)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            self._disabled = f"国家统计局目录校验失败，本次运行停止请求：{exc}"
            raise ValueError(self._disabled) from exc

    def collect(self, region: str, year: int) -> dict:
        result = {
            "data": {}, "evidence": {}, "candidates": {}, "warnings": [],
            "source_url": NBS_PAGE, "bulletin_type": "国家统计局分省年度数据", "publish_date": "",
        }
        if region not in PROVINCE_CODES:
            result["warnings"].append(f"国家统计局分省年度接口不支持 {region}；不使用所在省或全国数据替代")
            return result
        if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2100:
            result["warnings"].append("统计年度必须是四位整数")
            return result
        if self._disabled:
            result["warnings"].append(self._disabled)
            return result
        try:
            self._prepare()
        except ValueError as exc:
            result["warnings"].append(str(exc))
            return result
        for metric in INDICATORS:
            catalog = self._catalogs.get(metric)
            if catalog is None:
                result["warnings"].append(f"{metric}：{self._catalog_errors.get(metric, '目录缺失')}")
                continue
            try:
                area = _one(catalog["areas"], "show_name", region)
                if (area.get("name_value") != PROVINCE_CODES[region] + "0" * 10
                        or area.get("catalog_id") != catalog["area_catalog_id"]):
                    raise ValueError("地区代码或地区目录不匹配")
                payload = {
                    "cid": catalog["leaf"]["_id"], "indicatorIds": [catalog["indicator"]["_id"]],
                    "daCatalogId": "", "das": [{"text": region, "value": area["name_value"]}],
                    "showType": "1", "rootId": catalog["root"]["_id"], "dts": [f"{year}YY"],
                }
                body, proof = self._request("stream/esData", payload=payload)
                candidates = self._candidates(body, proof, catalog, area, metric, year)
                result["candidates"][metric] = candidates
                verified = [c for c in candidates if not c["review_reasons"]]
                if len({c["normalized_value"] for c in verified}) > 1:
                    for candidate in verified:
                        candidate["validation_status"] = "pending"
                        candidate["review_reasons"].append("同一指标、地区和年度返回多个不同数值")
                    result["evidence"][metric] = {
                        **copy.deepcopy(verified[0]), "conflicts": copy.deepcopy(verified),
                    }
                    result["warnings"].append(f"{metric}：存在冲突，未选取任一数值")
                elif verified:
                    result["data"][metric] = verified[0]["normalized_value"]
                    result["evidence"][metric] = copy.deepcopy(verified[0])
                else:
                    if candidates:
                        result["evidence"][metric] = copy.deepcopy(candidates[0])
                    result["warnings"].append(f"{metric}：未返回地区、年度、指标及单位完全匹配的有效数值")
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                result["warnings"].append(f"{metric}：{exc}")
        return result

    @staticmethod
    def _candidates(body, proof, catalog, area, metric, year) -> list[dict]:
        periods = body.get("data")
        if not isinstance(periods, list):
            raise ValueError("年度数据响应结构不匹配")
        candidates = []
        for period_index, period in enumerate(periods):
            if not isinstance(period, dict) or not isinstance(period.get("values"), list):
                raise ValueError("年度数据记录结构不匹配")
            for value_index, item in enumerate(period["values"]):
                if not isinstance(item, dict):
                    raise ValueError("指标数据记录结构不匹配")
                reasons = []
                if period.get("code") != f"{year}YY" or _text(period.get("name")) != f"{year}年":
                    reasons.append("统计期不匹配，须为指定年度 YY")
                if item.get("_id") != catalog["indicator"]["_id"] or item.get("catalogid") != catalog["leaf"]["_id"]:
                    reasons.append("指标代码或目录不匹配")
                if _text(item.get("i_showname")) != metric + "(元)":
                    reasons.append("指标名称或口径不匹配")
                if item.get("da") != area["name_value"] or _text(item.get("da_name")) != area["show_name"]:
                    reasons.append("地区名称或代码不匹配")
                if _text(item.get("du_name")) != "元":
                    reasons.append("单位不匹配，要求元")
                raw = item.get("value")
                value = None
                if not isinstance(raw, bool) and re.fullmatch(r"\d+(?:\.\d+)?", str(raw or "")):
                    number = float(raw)
                    if math.isfinite(number) and number > 0:
                        value = number
                if value is None:
                    reasons.append("数值缺失、非数值或不大于零")
                pointer = f"/data/{period_index}/values/{value_index}/value"
                locator = {"type": "nbs_json", "json_pointer": pointer}
                snippet = json.dumps({"period": period.get("code"), "period_name": period.get("name"), "record": item}, ensure_ascii=False)
                annual_code = re.fullmatch(r"(\d{4})YY", str(period.get("code") or ""))
                annual_name = re.fullmatch(r"(\d{4})年", _text(period.get("name")))
                actual_year = int(annual_code.group(1)) if annual_code else None
                if annual_name and actual_year != int(annual_name.group(1)):
                    actual_year = None  # conflicting response dimensions cannot establish a year
                conversion = {"factor": 1, "operation": f"{raw} × 1"} if _text(item.get("du_name")) == "元" else None
                candidates.append({
                    **copy.deepcopy(proof), "source_type": "nbs_json", "extractor_version": EXTRACTOR_VERSION,
                    "extract_method": "nbs_json", "source_title": "国家统计局分省年度数据",
                    "indicator": metric, "indicator_id": catalog["indicator"]["_id"],
                    "indicator_metadata": copy.deepcopy(catalog["indicator"]),
                    "metadata_sources": copy.deepcopy(catalog["proofs"]),
                    "region": item.get("da_name"), "region_code": item.get("da"),
                    "expected_region": area["show_name"], "expected_region_code": area["name_value"],
                    "statistical_year": actual_year, "expected_year": year,
                    "statistical_period": period.get("code"), "statistical_period_name": period.get("name"),
                    "scope": {"population": "城镇居民", "metric": metric},
                    "raw_value": raw, "raw_unit": item.get("du_name"), "unit": "元",
                    "normalized_value": value, "value": value, "conversion_factor": 1,
                    "locator": locator, "snippet": snippet, "conversion": conversion,
                    "location": {"json_pointer": pointer}, "json_pointer": pointer,
                    "excerpt": snippet,
                    "validation_status": "pending" if reasons else "verified", "review_reasons": reasons,
                })
        return candidates
