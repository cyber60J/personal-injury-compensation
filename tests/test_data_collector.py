import unittest
import tempfile
from pathlib import Path

from data_collector import (
    BulletinSearcher,
    CollectionStatus,
    DataCollector,
    DataRecord,
    DataExtractor,
    DataValidator,
    END_YEAR,
    REGIONS,
    START_YEAR,
    extract_number_with_evidence,
    extract_number_from_text,
    fetch_official_content,
    is_allowed_official_url,
    normalize_number,
    spreadsheet_safe_value,
)


class _FakeResponse:
    def __init__(self, url, status_code=200, headers=None, chunks=None):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks or []
        self.closed = False

    def iter_content(self, chunk_size):
        del chunk_size
        yield from self._chunks

    def close(self):
        self.closed = True


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class OfficialSourceBoundaryTests(unittest.TestCase):
    def test_official_url_allowlist_rejects_downgrade_credentials_and_lookalikes(self):
        official = "https://tjj.example.gov.cn"

        self.assertTrue(is_allowed_official_url("https://data.tjj.example.gov.cn/a", official))
        self.assertFalse(is_allowed_official_url("http://tjj.example.gov.cn/a", official))
        self.assertFalse(is_allowed_official_url("https://tjj.example.gov.cn.evil.test/a", official))
        self.assertFalse(is_allowed_official_url("https://user@tjj.example.gov.cn/a", official))
        self.assertFalse(is_allowed_official_url("file:///etc/passwd", official))

    def test_cross_domain_redirect_is_rejected_before_following_it(self):
        official = "https://tjj.example.gov.cn"
        session = _FakeSession([
            _FakeResponse(
                official + "/start",
                status_code=302,
                headers={"Location": "https://evil.test/secret"},
            )
        ])

        with self.assertRaisesRegex(ValueError, "非官方域名"):
            fetch_official_content(session, official + "/start", official)

        self.assertEqual(len(session.calls), 1)
        self.assertFalse(session.calls[0][1]["allow_redirects"])

    def test_response_size_limit_is_enforced_while_streaming(self):
        official = "https://tjj.example.gov.cn"
        session = _FakeSession([
            _FakeResponse(official + "/large", chunks=[b"1234", b"5678"])
        ])

        with self.assertRaisesRegex(ValueError, "响应体超过"):
            fetch_official_content(session, official + "/large", official, max_bytes=5)

        self.assertTrue(session.responses == [])

    def test_external_text_cannot_become_spreadsheet_formula(self):
        self.assertEqual(spreadsheet_safe_value("=HYPERLINK(\"https://evil.test\")"), "'=HYPERLINK(\"https://evil.test\")")
        self.assertEqual(spreadsheet_safe_value("  @SUM(1,1)"), "'  @SUM(1,1)")
        self.assertEqual(spreadsheet_safe_value("官方统计公报"), "官方统计公报")
        self.assertEqual(spreadsheet_safe_value(-12.5), -12.5)


class NumberExtractionTests(unittest.TestCase):
    def test_default_range_covers_ten_years(self):
        self.assertEqual(END_YEAR - START_YEAR + 1, 10)

    def test_normalize_number_handles_common_units(self):
        self.assertEqual(normalize_number("42,568元"), 42568.0)
        self.assertEqual(normalize_number("3.5万元"), 35000.0)
        self.assertEqual(normalize_number("１２，３４５元"), 12345.0)

    def test_extract_number_allows_connector_words(self):
        text = "全年城镇居民人均可支配收入为68,434元，比上年增长4.8%。"
        value = extract_number_from_text(text, ["城镇居民人均可支配收入"])
        self.assertEqual(value, 68434.0)

    def test_extract_number_skips_growth_amount_before_total(self):
        text = "城镇居民人均可支配收入比上年增加2300元，达到68,434元。"
        value = extract_number_from_text(text, ["城镇居民人均可支配收入"])
        self.assertEqual(value, 68434.0)

    def test_extract_number_supports_unitless_table_values(self):
        text = "指标 城镇居民人均消费支出 39856 3.2"
        value = extract_number_from_text(text, ["城镇居民人均消费支出"])
        self.assertEqual(value, 39856.0)

    def test_extract_number_returns_evidence(self):
        text = "全年城镇居民人均可支配收入为68,434元，比上年增长4.8%。"
        value, evidence = extract_number_with_evidence(text, ["城镇居民人均可支配收入"])

        self.assertEqual(value, 68434.0)
        self.assertEqual(evidence["keyword"], "城镇居民人均可支配收入")
        self.assertIn("68,434元", evidence["snippet"])


class CollectionStatusTests(unittest.TestCase):
    def test_failed_records_are_retried_by_default(self):
        status = CollectionStatus()
        status.add_record(DataRecord(region="江苏省", year=2024, status="提取失败"))

        self.assertFalse(status.is_completed("江苏省", 2024))
        self.assertTrue(status.is_completed("江苏省", 2024, retry_failed=False))

    def test_partial_records_are_retried_by_default(self):
        status = CollectionStatus()
        status.add_record(DataRecord(region="江苏省", year=2016, status="部分提取"))

        self.assertFalse(status.is_completed("江苏省", 2016))
        self.assertTrue(status.is_completed("江苏省", 2016, retry_failed=False))

    def test_add_record_replaces_same_region_year(self):
        status = CollectionStatus()
        status.add_record(DataRecord(region="江苏省", year=2024, status="提取失败"))
        status.add_record(
            DataRecord(
                region="江苏省",
                year=2024,
                urban_disposable_income=68000,
                urban_consumption_expenditure=42000,
                status="已提取",
            )
        )

        self.assertEqual(len(status.records), 1)
        self.assertTrue(status.is_completed("江苏省", 2024))

    def test_status_save_is_atomic_and_loadable(self):
        status = CollectionStatus(records=[DataRecord(region="江苏省", year=2024)])

        with tempfile.TemporaryDirectory() as temp_dir:
            status_path = Path(temp_dir) / "nested" / "status.json"
            status.save(str(status_path))
            loaded = CollectionStatus()
            loaded.load(str(status_path))

            self.assertEqual(loaded.records[0].region, "江苏省")
            self.assertFalse(Path(str(status_path) + ".tmp").exists())


class BulletinSearcherTests(unittest.TestCase):
    def test_finds_link_inside_cdata_record(self):
        content = """
        <script type="text/xml"><datastore>
        <record><![CDATA[
        <li><a title='2024年江苏省国民经济和社会发展统计公报'
        href="/art/2025/3/15/art_85764_11514117.html">2024年江苏省国民经济和社会发展统计公报</a>
        <span>2025-03-15</span></li>]]></record>
        </datastore></script>
        """
        searcher = BulletinSearcher(session=None, logger=None)

        result = searcher._find_bulletin_link_in_content(
            content,
            "https://tj.jiangsu.gov.cn/col/col85764/index.html",
            2024,
            {
                "name": "国民经济和社会发展统计公报",
                "keywords": ["国民经济和社会发展统计公报"],
            },
        )

        self.assertEqual(
            result["url"],
            "https://tj.jiangsu.gov.cn/art/2025/3/15/art_85764_11514117.html",
        )
        self.assertEqual(result["publish_date"], "2025-03-15")


class SourceExportTests(unittest.TestCase):
    def test_build_source_rows_contains_field_level_evidence(self):
        record = DataRecord(
            region="江苏省",
            year=2024,
            urban_disposable_income=66173,
            status="已提取",
            evidence={
                "城镇居民人均可支配收入": {
                    "source_url": "https://tj.jiangsu.gov.cn/art/example.html",
                    "source_title": "2024年江苏省国民经济和社会发展统计公报",
                    "publish_date": "2025-03-15",
                    "bulletin_type": "国民经济和社会发展统计公报",
                    "retrieved_at": "2026-07-09T13:00:00",
                    "content_sha256": "abc123",
                    "source_domain_verified": True,
                    "extract_method": "keyword_window",
                    "keyword": "城镇居民人均可支配收入",
                    "snippet": "城镇居民人均可支配收入 66173 元",
                }
            },
        )
        collector = DataCollector.__new__(DataCollector)
        collector.status = CollectionStatus(records=[record])

        rows = collector._build_source_rows()
        income_row = next(row for row in rows if row["数据项"] == "城镇居民人均可支配收入")

        self.assertEqual(income_row["数值"], 66173)
        self.assertEqual(income_row["字段要求"], "核心必需")
        self.assertTrue(income_row["官方域名校验"])
        self.assertEqual(income_row["内容SHA256"], "abc123")


class DataValidatorTests(unittest.TestCase):
    def test_default_regions_exclude_unverifiable_taiwan_entry(self):
        self.assertNotIn("台湾省", REGIONS)

    def test_marks_incomplete_historical_record_as_partial(self):
        validator = DataValidator(logger=None)
        record = DataRecord(
            region="江苏省",
            year=2016,
            urban_disposable_income=40152,
            status="已提取",
        )

        result = validator.validate_record(record, [])

        self.assertEqual(result.status, "部分提取")
        self.assertIn("城镇居民人均消费支出", result.error_message)

    def test_missing_optional_legacy_field_keeps_core_record_complete(self):
        validator = DataValidator(logger=None)
        record = DataRecord(
            region="江苏省",
            year=2024,
            urban_disposable_income=66173,
            urban_consumption_expenditure=42197,
            urban_non_private_wage=129220,
            urban_private_wage=78114,
            service_industry_wage=87803,
            status="已提取",
        )

        result = validator.validate_record(record, [])

        self.assertEqual(result.status, "已提取")
        self.assertIn("缺失可选历史口径", result.error_message)

    def test_out_of_range_value_requires_manual_review(self):
        validator = DataValidator(logger=None)
        record = DataRecord(
            region="江苏省",
            year=2024,
            urban_disposable_income=66,
            urban_consumption_expenditure=42197,
            urban_non_private_wage=129220,
            urban_private_wage=78114,
            service_industry_wage=87803,
            status="已提取",
        )

        result = validator.validate_record(record, [])

        self.assertEqual(result.status, "需人工复核")
        self.assertIn("超出合理范围", result.error_message)

    def test_unverified_or_conflicting_source_requires_manual_review(self):
        validator = DataValidator(logger=None)
        record = DataRecord(
            region="江苏省",
            year=2024,
            urban_disposable_income=66173,
            urban_consumption_expenditure=42197,
            urban_non_private_wage=129220,
            urban_private_wage=78114,
            service_industry_wage=87803,
            status="已提取",
            evidence={
                "城镇居民人均可支配收入": {
                    "source_domain_verified": False,
                    "conflicts": [{"value": 66000}],
                }
            },
        )

        result = validator.validate_record(record, [])

        self.assertEqual(result.status, "需人工复核")
        self.assertIn("来源域名未通过校验", result.error_message)
        self.assertIn("冲突候选值", result.error_message)


if __name__ == "__main__":
    unittest.main()
