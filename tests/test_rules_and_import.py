from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine

from personal_injury.domain.models import CaseType
from personal_injury.domain.rules import resolve_rule_set
from personal_injury.application.services import CalculationService
from personal_injury.infrastructure.collector_import import import_collector_status
from personal_injury.infrastructure.database import (
    Base,
    CaseModel,
    StatisticalStandardModel,
    UserModel,
    create_session_factory,
)


class RulesAndImportTests(unittest.TestCase):
    def test_traffic_rule_changes_on_effective_date(self):
        before = resolve_rule_set(CaseType.TRAFFIC_ACCIDENT, date(2026, 6, 29))
        after = resolve_rule_set(CaseType.TRAFFIC_ACCIDENT, date(2026, 6, 30))
        self.assertEqual(before.version, "traffic-2022")
        self.assertEqual(after.version, "traffic-2026-ii")

    def test_traffic_rule_transition_respects_pre_effective_final_judgment(self):
        rule = resolve_rule_set(
            CaseType.TRAFFIC_ACCIDENT,
            date(2026, 7, 1),
            incident_date=date(2024, 1, 1),
            final_judgment_date=date(2026, 6, 29),
        )
        self.assertEqual(rule.version, "traffic-2022")

    def test_rules_before_supported_2022_boundary_fail_closed(self):
        with self.assertRaises(ValueError):
            resolve_rule_set(
                CaseType.GENERAL_PERSONAL_INJURY,
                date(2026, 7, 1),
                incident_date=date(2022, 4, 30),
            )

    def test_collector_data_is_pending_until_approved(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        sessions = create_session_factory(engine)
        payload = {
            "records": [{
                "region": "测试地区",
                "year": 2025,
                "urban_disposable_income": 70000,
                "source_url": "https://example.gov.cn/aggregate",
                "status": "已提取",
                "evidence": {
                    "城镇居民人均可支配收入": {
                        "source_url": "https://example.gov.cn/income",
                        "source_title": "居民收入公报",
                        "publish_date": "2026-03-01",
                        "source_domain_verified": True,
                        "transport_secure": True,
                    }
                },
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with sessions() as session:
                self.assertEqual(import_collector_status(session, path), 1)
                standard = session.query(StatisticalStandardModel).one()
                self.assertEqual(standard.status, "pending")
                self.assertEqual(standard.source_url, "https://example.gov.cn/income")
                self.assertEqual(standard.source_record["collector_status"], "已提取")
                self.assertTrue(standard.source_record["evidence"]["transport_secure"])
                standard.status = "approved"
                actor = UserModel(
                    username="lawyer",
                    display_name="Lawyer",
                    role="lawyer",
                    password_hash="test",
                )
                session.add(actor)
                session.flush()
                case = CaseModel(
                    case_number="RULE-001",
                    title="Rule test",
                    case_type="traffic_accident",
                    status="open",
                    statistical_region="测试地区",
                    created_by_id=actor.id,
                )
                session.add(case)
                session.flush()
                snapshot = CalculationService(session).calculate_and_persist(
                    case=case,
                    input_data={"disability_level": 8, "age": 35},
                    actor=actor,
                    standard_year=2025,
                    rule_as_of=date(2026, 7, 1),
                )
                self.assertEqual(snapshot.rule_version, "traffic-2026-ii")
                self.assertEqual(snapshot.standard_year, 2025)
                self.assertEqual(snapshot.algorithm_version, "2026.1")
                self.assertEqual(
                    snapshot.review_output["review_metadata"]["used_statistical_standards"][0]["value"],
                    70000.0,
                )
                session.commit()
                self.assertEqual(session.query(StatisticalStandardModel).one().status, "approved")

    def test_formal_calculation_rejects_missing_standard_and_demo_cannot_be_approved(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        sessions = create_session_factory(engine)
        with sessions() as session:
            actor = UserModel(
                username="lawyer",
                display_name="Lawyer",
                role="lawyer",
                password_hash="test",
            )
            session.add(actor)
            session.flush()
            case = CaseModel(
                case_number="RULE-STRICT-001",
                title="Strict rule test",
                case_type="traffic_accident",
                status="open",
                incident_date=date(2025, 1, 1),
                first_instance_debate_end_date=date(2026, 5, 1),
                statistical_region="测试地区",
                created_by_id=actor.id,
            )
            session.add(case)
            session.flush()

            service = CalculationService(session)
            with self.assertRaises(ValueError):
                service.calculate_and_persist(
                    case=case,
                    input_data={"disability_level": 8, "age": 35},
                    actor=actor,
                    rule_as_of=date(2026, 7, 1),
                )

            snapshot = service.calculate_and_persist(
                case=case,
                input_data={"disability_level": 8, "age": 35},
                actor=actor,
                rule_as_of=date(2026, 7, 1),
                allow_demo_standards=True,
            )
            self.assertEqual(snapshot.standard_year, 2025)
            self.assertIn(
                "urban_disposable_income",
                snapshot.standards_snapshot["missing"],
            )
            with self.assertRaises(ValueError):
                service.approve(snapshot, actor, reason="紧急复核")
