from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from personal_injury.infrastructure.database import AuditLogModel, StatisticalStandardModel
from personal_injury.web.app import create_app


class ExtractionReviewTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app("sqlite://"))
        self.client.__enter__()
        response = self.client.post("/api/auth/bootstrap", json={
            "username": "admin", "password": "password123", "display_name": "管理员",
        })
        self.assertEqual(response.status_code, 201)

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def _standard(self, evidence=None, **changes):
        trusted = {
            "region": "浙江", "statistical_year": 2025,
            "scope": {"population": "城镇居民", "metric": "人均可支配收入"},
            "raw_value": "7", "raw_unit": "万元", "unit": "元",
            "conversion": {"factor": 10000}, "snippet": "2025年浙江城镇居民人均可支配收入7万元",
            "locator": {"table": 1, "row": 2, "column": 3, "headers": ["2025年"]},
            "extractor_version": "test-v1", "validation_status": "verified",
            "source_domain_verified": True, "transport_secure": True,
        }
        if evidence is not None:
            trusted.update(evidence)
        values = {
            "region": "浙江", "year": 2025, "field_name": "urban_disposable_income",
            "value": 70000, "status": "pending", "source_url": "https://tjj.zj.gov.cn/test",
            "source_record": {"collector_status": "已提取", "evidence": trusted},
        }
        values.update(changes)
        with self.client.app.state.session_factory() as db:
            item = StatisticalStandardModel(**values)
            db.add(item)
            db.commit()
            return item.id

    def _approve(self, standard_id, reason=None):
        return self.client.post(f"/api/statistical-standards/{standard_id}/approve",
                                json={"reason": reason})

    def test_complete_verified_evidence_can_be_approved(self):
        standard_id = self._standard()
        response = self._approve(standard_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "approved")
        self.assertEqual(response.json()["review_warnings"], [])
        self.assertEqual(self._approve(standard_id).status_code, 409)

    def test_region_or_year_mismatch_cannot_be_overridden_by_reason(self):
        for field, value in (("region", "江苏"), ("statistical_year", 2024)):
            with self.subTest(field=field):
                standard_id = self._standard({field: value}, field_name=field)
                response = self._approve(standard_id, "已经人工检查")
                self.assertEqual(response.status_code, 422)
                self.assertIn("不一致", response.json()["detail"])
                with self.client.app.state.session_factory() as db:
                    self.assertEqual(db.get(StatisticalStandardModel, standard_id).status, "pending")
                    self.assertFalse(db.query(AuditLogModel).filter_by(entity_id=standard_id).first())

    def test_invalidated_value_cannot_be_approved_even_with_reason(self):
        standard_id = self._standard(status="invalidated")
        response = self._approve(standard_id, "旧值看起来仍然合理")
        self.assertEqual(response.status_code, 422)
        self.assertIn("失效", response.json()["detail"])
        listed = self.client.get("/api/statistical-standards").json()[0]
        self.assertEqual(listed["status"], "invalidated")
        self.assertTrue(listed["approval_blockers"])
        with self.client.app.state.session_factory() as db:
            self.assertFalse(db.query(AuditLogModel).filter_by(entity_id=standard_id).first())

    def test_legacy_missing_metadata_requires_reason_and_records_warning(self):
        standard_id = self._standard(source_record={
            "collector_status": "已提取",
            "evidence": {"source_domain_verified": True, "transport_secure": True},
        })
        self.assertEqual(self._approve(standard_id).status_code, 422)
        response = self._approve(standard_id, "查阅留存公报，核实地区、年度、口径及单位")
        self.assertEqual(response.status_code, 200)
        with self.client.app.state.session_factory() as db:
            audit = db.query(AuditLogModel).filter_by(entity_id=standard_id).one()
            self.assertTrue(any("证据缺少" in item for item in audit.details["source_warnings"]))
            self.assertIn("查阅", audit.details["reason"])

    def test_pending_conflicts_and_extraction_warnings_require_explanation(self):
        standard_id = self._standard({
            "validation_status": "pending", "conflicts": [{"value": 68000}],
            "review_reasons": ["脚注指明口径调整"],
        })
        response = self._approve(standard_id, "   ")
        self.assertEqual(response.status_code, 422)
        self.assertIn("冲突", response.json()["detail"])
        self.assertIn("脚注", response.json()["detail"])
        self.assertEqual(self._approve(standard_id, "确认更正公报取代旧值，口径适用").status_code, 200)

    def test_zero_raw_value_is_present_not_missing(self):
        standard_id = self._standard({"raw_value": 0}, value=0)
        self.assertEqual(self._approve(standard_id).status_code, 200)

    def test_assistant_can_review_but_cannot_approve(self):
        standard_id = self._standard()
        self.client.post("/api/users", json={"username": "assistant", "password": "password123",
                                             "display_name": "助理", "role": "assistant"})
        self.client.post("/api/auth/login", json={"username": "assistant", "password": "password123"})
        self.assertEqual(self.client.get("/api/statistical-standards").status_code, 200)
        self.assertEqual(self._approve(standard_id, "已核验").status_code, 403)

    def test_anonymous_cannot_list_download_or_approve(self):
        standard_id = self._standard()
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/statistical-standards").status_code, 401)
        self.assertEqual(self.client.get(f"/api/statistical-standards/{standard_id}/original").status_code, 401)
        self.assertEqual(self._approve(standard_id).status_code, 401)

    def test_listing_exposes_review_context_but_hides_storage_paths(self):
        self._standard({"validation_status": "pending", "archive_path": "C:/private/source.html",
                        "review_reasons": ["missing_or_ambiguous_unit"],
                        "candidates": [{"value": 70000, "local_path": "C:/private/source.html"}]})
        response = self.client.get("/api/statistical-standards")
        item = response.json()[0]
        self.assertTrue(item["review_warnings"])
        self.assertEqual(item["source_record"]["evidence"]["locator"]["headers"], ["2025年"])
        self.assertNotIn("C:/private", response.text)
        self.assertNotIn("archive_path", response.text)
        self.assertIn("单位缺失或存在多种单位", item["source_record"]["evidence"]["review_messages"])

    def test_unregistered_or_invalid_archive_digest_never_reads_record_path(self):
        for digest in (None, "../private.txt", "a" * 64):
            with self.subTest(digest=digest):
                standard_id = self._standard({"archive_sha256": digest, "archive_path": "../private.txt"},
                                             field_name=str(digest))
                self.assertEqual(self.client.get(f"/api/statistical-standards/{standard_id}/original").status_code, 404)

    def test_verified_archive_is_downloaded_as_attachment_and_rechecked(self):
        content = b"<script>alert('untrusted original')</script>"
        digest = hashlib.sha256(content).hexdigest()
        standard_id = self._standard({"archive_sha256": digest, "archive_path": "../ignored.html"})
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.html"
            source.write_bytes(content)
            with patch("personal_injury.collection.source_archive.ArchiveStore.resolve", return_value=source):
                response = self.client.get(f"/api/statistical-standards/{standard_id}/original")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, content)
                self.assertEqual(response.headers["content-type"], "application/octet-stream")
                self.assertTrue(response.headers["content-disposition"].startswith("attachment;"))
                self.assertEqual(response.headers["x-content-type-options"], "nosniff")
                source.write_bytes(b"tampered")
                self.assertEqual(self.client.get(f"/api/statistical-standards/{standard_id}/original").status_code, 409)

    def test_actual_archive_store_serves_registered_bytes_and_rejects_tampering(self):
        from personal_injury.collection.source_archive import ArchiveStore

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"STATISTICAL_ARCHIVE_DIR": directory}):
            content = b"original statistical data"
            store = ArchiveStore()
            record = store.save(content, source_url="https://tjj.zj.gov.cn/test", content_type="text/plain")
            standard_id = self._standard(record)
            endpoint = f"/api/statistical-standards/{standard_id}/original"
            self.assertEqual(self.client.get(endpoint).content, content)
            self.assertIn('.txt"', self.client.get(endpoint).headers["content-disposition"])
            path = store.resolve(record["archive_sha256"])
            self.assertIsNotNone(path)
            path.write_bytes(b"changed")
            self.assertEqual(self.client.get(endpoint).status_code, 404)


if __name__ == "__main__":
    unittest.main()
