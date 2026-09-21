from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, Optional

from personal_injury.domain.calculator import CompensationCalculator
from personal_injury.domain.models import CaseType
from personal_injury.domain.rules import resolve_rule_set
from personal_injury.infrastructure.database import (
    AuditLogModel,
    CalculationSnapshotModel,
    CaseMemberModel,
    CaseModel,
    ClaimModel,
    ReviewTaskModel,
    StatisticalStandardModel,
    UserModel,
    utcnow,
)


class CalculationService:
    """把纯计算器包装为可审计的应用服务。"""

    STANDARD_TO_CONFIG_KEY = {
        "hospital_meal_subsidy": "住院伙食补助费标准",
        "nutrition_fee": "营养费标准",
        "transportation_fee": "交通费标准",
        "nursing_fee": "护理费标准",
        "urban_disposable_income": "上一年度城镇居民人均可支配收入",
        "urban_consumption_expenditure": "上一年度城镇居民人均消费支出",
    }

    def __init__(self, session):
        self.session = session

    def calculate_and_persist(
        self,
        *,
        case: CaseModel,
        input_data: Dict[str, Any],
        actor: UserModel,
        jurisdiction: Optional[str] = None,
        standard_year: Optional[int] = None,
        rule_as_of: Optional[date] = None,
        allow_demo_standards: bool = False,
    ) -> CalculationSnapshotModel:
        assessment_date = rule_as_of or date.today()
        rule = resolve_rule_set(
            CaseType(case.case_type),
            assessment_date,
            incident_date=case.incident_date,
            final_judgment_date=case.final_judgment_date,
        )
        resolved_standard_year = standard_year
        if resolved_standard_year is None and case.first_instance_debate_end_date:
            resolved_standard_year = case.first_instance_debate_end_date.year - 1
        resolved_region = case.statistical_region or jurisdiction or case.jurisdiction
        calculator_config = dict(rule.calculator_config)
        required_fields = self._required_standard_fields(input_data)
        used_standards, missing_standards = self._apply_approved_standards(
            calculator_config,
            required_fields=required_fields,
            region=resolved_region,
            year=resolved_standard_year,
        )
        if missing_standards and not allow_demo_standards:
            missing_text = "、".join(missing_standards)
            raise ValueError(f"正式试算缺少已审核统计标准：{missing_text}")
        calculator = CompensationCalculator(
            config=calculator_config,
            active_rule_source_keys=rule.source_keys,
        )
        report = calculator.calculate_with_review(input_data)
        raw_results = report["损失金额"]
        payable_results = report["责任比例后金额"]
        review_output = report["裁判审查提示"]
        rule_context = {
            "assessment_date": assessment_date.isoformat(),
            "incident_date": case.incident_date.isoformat() if case.incident_date else None,
            "final_judgment_date": (
                case.final_judgment_date.isoformat() if case.final_judgment_date else None
            ),
            "source_keys": list(rule.source_keys),
        }
        standards_snapshot = {
            "region": resolved_region,
            "year": resolved_standard_year,
            "used": used_standards,
            "missing": missing_standards,
        }
        review_metadata = review_output.setdefault("review_metadata", {})
        review_metadata.update(
            {
                "rule_context": rule_context,
                "used_statistical_standards": used_standards,
                "missing_statistical_standards": missing_standards,
                "blocking_flags": (
                    ["使用了演示标准，补齐并审核正式标准后才能批准"]
                    if missing_standards
                    else []
                ),
            }
        )
        snapshot = CalculationSnapshotModel(
            case_id=case.id,
            algorithm_version=calculator.ALGORITHM_VERSION,
            rule_version=rule.version,
            rule_as_of=assessment_date,
            rule_context=rule_context,
            standard_year=resolved_standard_year,
            standards_snapshot=standards_snapshot,
            jurisdiction=jurisdiction or case.jurisdiction,
            input_data=input_data,
            raw_results=raw_results,
            payable_results=payable_results,
            review_output=review_output,
            review_status="draft",
            created_by_id=actor.id,
        )
        self.session.add(snapshot)
        self.session.flush()
        self._create_review_tasks(case, snapshot, actor)
        self.session.add(
            AuditLogModel(
                actor_id=actor.id,
                case_id=case.id,
                action="calculation_created",
                entity_type="calculation_snapshot",
                entity_id=snapshot.id,
                details={"rule_version": rule.version},
            )
        )
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def _apply_approved_standards(
        self,
        calculator_config: dict[str, float],
        *,
        required_fields: set[str],
        region: str | None,
        year: int | None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if not required_fields:
            return [], []
        if not region or year is None:
            return [], sorted(required_fields)
        standards = self.session.query(StatisticalStandardModel).filter(
            StatisticalStandardModel.region == region,
            StatisticalStandardModel.year == year,
            StatisticalStandardModel.status == "approved",
        ).all()
        used: list[dict[str, Any]] = []
        found_fields: set[str] = set()
        for standard in standards:
            if standard.field_name not in required_fields:
                continue
            config_key = self.STANDARD_TO_CONFIG_KEY.get(standard.field_name)
            if config_key not in calculator_config:
                continue
            calculator_config[config_key] = float(standard.value)
            found_fields.add(standard.field_name)
            used.append({
                "id": standard.id,
                "field_name": standard.field_name,
                "value": float(standard.value),
                "source_key": standard.source_key,
                "source_url": standard.source_url,
            })
        return used, sorted(required_fields - found_fields)

    @staticmethod
    def _required_standard_fields(input_data: Dict[str, Any]) -> set[str]:
        required: set[str] = set()
        input_to_standard = {
            "hospitalization_days": "hospital_meal_subsidy",
            "nutrition_days": "nutrition_fee",
            "transportation_days": "transportation_fee",
            "nursing_days": "nursing_fee",
            "disability_level": "urban_disposable_income",
        }
        for input_key, standard_field in input_to_standard.items():
            if input_key in input_data:
                required.add(standard_field)
        if input_data.get("dependents"):
            required.add("urban_consumption_expenditure")
        return required

    def approve(
        self,
        snapshot: CalculationSnapshotModel,
        actor: UserModel,
        *,
        reason: str | None = None,
    ) -> CalculationSnapshotModel:
        if actor.role not in {"admin", "lawyer"}:
            raise ValueError("只有管理员或律师可以批准计算")
        if snapshot.review_status == "approved":
            raise ValueError("计算快照已经批准，不能重复批准")
        blocking_flags = snapshot.review_output.get("review_metadata", {}).get("blocking_flags", [])
        if blocking_flags:
            raise ValueError("；".join(blocking_flags))
        if snapshot.created_by_id == actor.id:
            if actor.role != "admin":
                raise ValueError("计算创建者不能批准自己的计算")
            if not reason or not reason.strip():
                raise ValueError("管理员紧急批准自己创建的计算时必须填写原因")
        open_tasks = self.session.query(ReviewTaskModel).filter(
            ReviewTaskModel.calculation_snapshot_id == snapshot.id,
            ReviewTaskModel.status == "open",
        ).count()
        if open_tasks and (not reason or not reason.strip()):
            raise ValueError("仍有未完成复核任务；如律师决定带保留意见批准，必须填写原因")
        snapshot.review_status = "approved"
        snapshot.approved_by_id = actor.id
        snapshot.approved_at = utcnow()
        self.session.add(
            AuditLogModel(
                actor_id=actor.id,
                case_id=snapshot.case_id,
                action="calculation_approved",
                entity_type="calculation_snapshot",
                entity_id=snapshot.id,
                details={"reason": reason.strip() if reason else None},
            )
        )
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def _create_review_tasks(
        self,
        case: CaseModel,
        snapshot: CalculationSnapshotModel,
        actor: UserModel,
    ) -> None:
        reviews = snapshot.review_output.get("claim_reviews", [])
        for review in reviews:
            amount = review.get("amount")
            if amount is None or amount <= 0:
                continue
            missing = review.get("missing_evidence", [])
            flags = review.get("risk_flags", [])
            if not missing and not flags:
                continue
            title = f"复核赔偿项目：{review.get('item', '未命名项目')}"
            existing = self.session.query(ReviewTaskModel).filter(
                ReviewTaskModel.calculation_snapshot_id == snapshot.id,
                ReviewTaskModel.title == title,
                ReviewTaskModel.status == "open",
            ).first()
            if existing:
                continue
            description = "；".join([*missing, *flags]) or "请律师复核该赔偿项目"
            self.session.add(
                ReviewTaskModel(
                    case_id=case.id,
                    calculation_snapshot_id=snapshot.id,
                    title=title,
                    description=description,
                    assigned_to_id=case.responsible_lawyer_id,
                    created_by_id=actor.id,
                )
            )


def import_legacy_case(session, payload: Dict[str, Any], actor: UserModel) -> CaseModel:
    """导入 data/example_case.json 形状的旧数据，不覆盖同编号案件。"""
    case_info = payload.get("case_info") or {}
    case_number = case_info.get("case_number")
    if not case_number:
        raise ValueError("旧案件缺少case_info.case_number")
    if session.query(CaseModel).filter(CaseModel.case_number == case_number).first():
        raise ValueError(f"案件编号已存在：{case_number}")

    case = CaseModel(
        case_number=case_number,
        title=f"{case_info.get('injured_party', '未命名')}人身损害案件",
        case_type="traffic_accident",
        status="open",
        jurisdiction=case_info.get("accident_location"),
        incident_date=_parse_date(case_info.get("accident_date")),
        description=json.dumps(payload, ensure_ascii=False),
        created_by_id=actor.id,
        responsible_lawyer_id=actor.id if actor.role == "lawyer" else None,
    )
    session.add(case)
    session.flush()
    session.add(
        CaseMemberModel(
            case_id=case.id,
            user_id=actor.id,
            member_role=actor.role,
        )
    )

    injured_party = case_info.get("injured_party")
    if injured_party:
        from personal_injury.infrastructure.database import PartyModel
        session.add(PartyModel(case_id=case.id, role="injured_party", name=injured_party, created_at=utcnow()))

    claim_inputs = {
        "医疗费": [
            *((payload.get("medical_expenses") or {}).get("hospital_bills") or []),
            *((payload.get("medical_expenses") or {}).get("medication_costs") or []),
            *((payload.get("medical_expenses") or {}).get("rehabilitation_costs") or []),
        ],
        "误工费": (payload.get("loss_of_income") or {}).get("daily_salary"),
    }
    if claim_inputs["医疗费"]:
        session.add(
            ClaimModel(
                case_id=case.id,
                claim_type="医疗费",
                input_data={"medical_bills": claim_inputs["医疗费"]},
                created_by_id=actor.id,
            )
        )
    if claim_inputs["误工费"] is not None:
        loss = payload.get("loss_of_income") or {}
        session.add(
            ClaimModel(
                case_id=case.id,
                claim_type="误工费",
                input_data={
                    "daily_salary": loss.get("daily_salary"),
                    "loss_of_work_days": loss.get("work_days_lost"),
                },
                created_by_id=actor.id,
            )
        )
    session.add(
        AuditLogModel(
            actor_id=actor.id,
            case_id=case.id,
            action="legacy_case_imported",
            entity_type="case",
            entity_id=case.id,
            details={"case_number": case_number},
        )
    )
    session.commit()
    session.refresh(case)
    return case


def _parse_date(value: Any):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"日期格式无效：{value}") from exc
