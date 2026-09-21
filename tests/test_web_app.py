from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from personal_injury.infrastructure.settings import Settings
from personal_injury.infrastructure.database import ReviewTaskModel, StatisticalStandardModel
from personal_injury.web.app import create_app


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app("sqlite://"))
        self.client.__enter__()
        response = self.client.post(
            "/api/auth/bootstrap",
            json={"username": "admin", "password": "password123", "display_name": "系统管理员"},
        )
        self.assertEqual(response.status_code, 201)
        self.bootstrap_response = response

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def _login(self, username: str, password: str = "password123"):
        response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200)
        return response

    def test_case_calculation_review_approval_and_audit(self):
        response = self.client.post(
            "/api/users",
            json={"username": "assistant", "password": "password123", "display_name": "助理", "role": "assistant"},
        )
        self.assertEqual(response.status_code, 201)
        response = self.client.post(
            "/api/users",
            json={"username": "lawyer", "password": "password123", "display_name": "律师", "role": "lawyer"},
        )
        self.assertEqual(response.status_code, 201)

        self._login("assistant")
        response = self.client.post(
            "/api/cases",
            json={
                "case_number": "TEST-001",
                "title": "交通事故测试案件",
                "case_type": "traffic_accident",
                "statistical_region": "测试地区",
            },
        )
        self.assertEqual(response.status_code, 201)
        case_id = response.json()["id"]
        self.assertEqual(self.client.get("/api/auth/me").json()["role"], "assistant")
        self._login("lawyer")
        lawyer_id = self.client.get("/api/auth/me").json()["id"]
        self._login("admin")
        self.assertEqual(
            self.client.post(
                f"/api/cases/{case_id}/members",
                json={"user_id": lawyer_id, "member_role": "lawyer"},
            ).status_code,
            201,
        )
        self.assertIsNone(self.client.get(f"/api/cases/{case_id}").json()["responsible_lawyer_id"])
        self._login("assistant")

        self.assertEqual(
            self.client.post(
                f"/api/cases/{case_id}/evidence",
                json={"name": "医疗费票据", "evidence_type": "invoice", "claim_type": "医疗费"},
            ).status_code,
            201,
        )
        response = self.client.post(
            f"/api/cases/{case_id}/calculations",
            json={"input_data": {"medical_bills": [1000], "daily_salary": 100, "loss_of_work_days": 10}},
        )
        self.assertEqual(response.status_code, 201)
        snapshot_id = response.json()["id"]
        self.assertGreater(len(response.json()["review_output"]["claim_reviews"]), 0)
        self.assertEqual(
            self.client.post(f"/api/cases/{case_id}/calculations/{snapshot_id}/approve").status_code,
            403,
        )
        tasks = self.client.get(f"/api/cases/{case_id}/review-tasks").json()
        self.assertGreater(len(tasks), 0)
        self.assertEqual(
            self.client.post(
                f"/api/cases/{case_id}/review-tasks/{tasks[0]['id']}/complete"
            ).status_code,
            403,
        )

        self._login("lawyer")
        for task in tasks:
            self.assertEqual(
                self.client.post(
                    f"/api/cases/{case_id}/review-tasks/{task['id']}/complete"
                ).status_code,
                200,
            )
        response = self.client.post(f"/api/cases/{case_id}/calculations/{snapshot_id}/approve")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["review_status"], "approved")
        response = self.client.get(f"/api/cases/{case_id}/export?format=markdown")
        self.assertEqual(response.status_code, 200)
        self.assertIn("TEST-001", response.text)
        audit = self.client.get("/api/audit-logs", params={"case_id": case_id})
        self.assertEqual(audit.status_code, 200)
        self.assertTrue(any(item["action"] == "calculation_approved" for item in audit.json()))

    def test_sources_are_seeded_and_cookie_auth_works(self):
        self.assertEqual(self.client.get("/api/legal-sources").status_code, 200)
        self.assertGreater(len(self.client.get("/api/legal-sources").json()), 0)
        self.assertEqual(self.client.get("/api/cases").status_code, 200)

    def test_session_response_cookie_and_workspace_are_hardened(self):
        self.assertNotIn("access_token", self.bootstrap_response.json())
        cookie = self.bootstrap_response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)

        workspace = self.client.get("/workspace")
        self.assertEqual(workspace.status_code, 200)
        self.assertNotIn("innerHTML", workspace.text)
        self.assertIn("textContent", workspace.text)
        self.assertEqual(workspace.headers["x-frame-options"], "DENY")

    def test_admin_self_approval_requires_reason(self):
        response = self.client.post(
            "/api/cases",
            json={"case_number": "ADMIN-SELF-001", "title": "管理员复核", "case_type": "traffic_accident"},
        )
        case_id = response.json()["id"]
        response = self.client.post(
            f"/api/cases/{case_id}/calculations",
            json={
                "input_data": {
                    "medical_bills": [100],
                    "evidence": {"医疗费": ["医疗费票据", "病历", "诊断证明"]},
                }
            },
        )
        snapshot_id = response.json()["id"]
        self.assertEqual(
            self.client.post(f"/api/cases/{case_id}/calculations/{snapshot_id}/approve").status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                f"/api/cases/{case_id}/calculations/{snapshot_id}/approve",
                json={"reason": "管理员紧急复核并确认"},
            ).status_code,
            200,
        )

    def test_lawyer_cannot_read_unassigned_case_audit(self):
        response = self.client.post(
            "/api/users",
            json={"username": "outside-lawyer", "password": "password123", "display_name": "其他律师", "role": "lawyer"},
        )
        self.assertEqual(response.status_code, 201)
        response = self.client.post(
            "/api/cases",
            json={"case_number": "PRIVATE-001", "title": "保密案件", "case_type": "traffic_accident"},
        )
        case_id = response.json()["id"]
        self._login("outside-lawyer")
        self.assertEqual(
            self.client.get("/api/audit-logs", params={"case_id": case_id}).status_code,
            404,
        )

    def test_cross_origin_cookie_write_is_rejected(self):
        response = self.client.post(
            "/api/users",
            headers={"Origin": "https://evil.example"},
            json={"username": "blocked", "password": "password123", "display_name": "Blocked", "role": "assistant"},
        )
        self.assertEqual(response.status_code, 403)

    def test_liveness_and_database_readiness(self):
        self.assertEqual(self.client.get("/health").json()["status"], "ok")
        self.assertEqual(self.client.get("/ready").json()["status"], "ready")

    def test_admin_can_reset_and_deactivate_user_but_must_first_reassign_lawyer_cases(self):
        assistant = self.client.post(
            "/api/users",
            json={"username": "leaver", "password": "password123", "display_name": "待离职助理", "role": "assistant"},
        ).json()
        lawyer = self.client.post(
            "/api/users",
            json={"username": "owner", "password": "password123", "display_name": "责任律师", "role": "lawyer"},
        ).json()
        response = self.client.post(
            "/api/cases",
            json={
                "case_number": "OFFBOARD-001",
                "title": "待移交案件",
                "case_type": "traffic_accident",
                "responsible_lawyer_id": lawyer["id"],
            },
        )
        self.assertEqual(response.status_code, 201)
        case_id = response.json()["id"]
        with self.client.app.state.session_factory() as db:
            review_task = ReviewTaskModel(
                case_id=case_id,
                title="待移交复核任务",
                description="由新责任律师继续复核",
                assigned_to_id=lawyer["id"],
                created_by_id=self.bootstrap_response.json()["user"]["id"],
            )
            db.add(review_task)
            db.commit()
            review_task_id = review_task.id
        self.assertEqual(
            self.client.patch(f"/api/users/{lawyer['id']}", json={"is_active": False}).status_code,
            409,
        )
        replacement = self.client.post(
            "/api/users",
            json={"username": "replacement", "password": "password123", "display_name": "接任律师", "role": "lawyer"},
        ).json()
        self.assertEqual(
            self.client.patch(
                f"/api/cases/{case_id}",
                json={"responsible_lawyer_id": replacement["id"]},
            ).status_code,
            200,
        )
        with self.client.app.state.session_factory() as db:
            reassigned_task = db.query(ReviewTaskModel).filter(
                ReviewTaskModel.id == review_task_id
            ).one()
            self.assertEqual(reassigned_task.assigned_to_id, replacement["id"])
        self.assertEqual(
            self.client.patch(f"/api/users/{lawyer['id']}", json={"is_active": False}).status_code,
            200,
        )

        response = self.client.patch(
            f"/api/users/{assistant['id']}",
            json={"password": "new-password123", "is_active": False},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_active"])
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"username": "leaver", "password": "new-password123"},
            ).status_code,
            401,
        )

    def test_removing_creator_membership_revokes_case_access(self):
        assistant = self.client.post(
            "/api/users",
            json={"username": "temporary", "password": "password123", "display_name": "临时助理", "role": "assistant"},
        ).json()
        self._login("temporary")
        case = self.client.post(
            "/api/cases",
            json={"case_number": "REVOKE-001", "title": "撤销访问测试"},
        ).json()
        self._login("admin")
        self.assertEqual(
            self.client.delete(f"/api/cases/{case['id']}/members/{assistant['id']}").status_code,
            204,
        )
        self._login("temporary")
        self.assertEqual(self.client.get(f"/api/cases/{case['id']}").status_code, 404)

    def test_case_dates_are_validated(self):
        response = self.client.post(
            "/api/cases",
            json={
                "case_number": "DATE-001",
                "title": "日期校验",
                "incident_date": "2025-05-01",
                "first_instance_debate_end_date": "2025-04-30",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_unsafe_statistical_source_requires_approval_reason(self):
        with self.client.app.state.session_factory() as db:
            standard = StatisticalStandardModel(
                region="测试地区",
                year=2025,
                field_name="urban_disposable_income",
                value=70000,
                source_url="http://example.gov.cn/income",
                status="pending",
                source_record={
                    "collector_status": "需人工复核",
                    "evidence": {
                        "source_domain_verified": True,
                        "transport_secure": False,
                    },
                },
            )
            db.add(standard)
            db.commit()
            standard_id = standard.id

        endpoint = f"/api/statistical-standards/{standard_id}/approve"
        self.assertEqual(self.client.post(endpoint).status_code, 422)
        response = self.client.post(endpoint, json={"reason": "已通过统计局电话核验原始公报"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "approved")


class ProductionBootstrapTests(unittest.TestCase):
    def test_bootstrap_requires_configured_token_and_secure_cookie(self):
        settings = Settings(
            database_url="sqlite://",
            environment="test",
            auto_create_schema=True,
            allow_demo_standards=False,
            cookie_secure=True,
            allow_open_bootstrap=False,
            bootstrap_token="bootstrap-secret",
            trusted_hosts=("*",),
            docs_enabled=False,
        )
        with TestClient(create_app(settings_override=settings)) as client:
            payload = {"username": "admin", "password": "password123", "display_name": "管理员"}
            self.assertEqual(client.post("/api/auth/bootstrap", json=payload).status_code, 403)
            response = client.post(
                "/api/auth/bootstrap",
                headers={"X-Bootstrap-Token": "bootstrap-secret"},
                json=payload,
            )
            self.assertEqual(response.status_code, 201)
            self.assertIn("secure", response.headers["set-cookie"].lower())
            self.assertNotIn("access_token", response.json())


class ProductionSettingsTests(unittest.TestCase):
    def test_database_password_is_encoded_when_built_from_components(self):
        with patch.dict(
            os.environ,
            {
                "DB_PASSWORD": "strong@:/%password",
                "DB_HOST": "db",
                "DB_USER": "personal_injury",
                "DB_NAME": "personal_injury",
            },
            clear=True,
        ):
            settings = Settings()

        self.assertIn("strong%40%3A%2F%25password", settings.database_url)

    def test_production_requires_https_cookie_and_explicit_host(self):
        base = {
            "database_url": "postgresql+psycopg://example",
            "environment": "production",
            "allow_demo_standards": False,
            "auto_create_schema": False,
            "allow_open_bootstrap": False,
            "docs_enabled": False,
        }
        with self.assertRaisesRegex(ValueError, "COOKIE_SECURE"):
            Settings(
                **base,
                cookie_secure=False,
                trusted_hosts=("law.example",),
                public_origin="https://law.example",
            )
        with self.assertRaisesRegex(ValueError, "TRUSTED_HOSTS"):
            Settings(
                **base,
                cookie_secure=True,
                trusted_hosts=("*",),
                public_origin="https://law.example",
            )
        with self.assertRaisesRegex(ValueError, "HTTPS PUBLIC_ORIGIN"):
            Settings(
                **base,
                cookie_secure=True,
                trusted_hosts=("law.example",),
                public_origin="http://law.example",
            )

        settings = Settings(
            **base,
            cookie_secure=True,
            trusted_hosts=("law.example",),
            public_origin="https://law.example",
        )
        self.assertEqual(settings.environment, "production")
