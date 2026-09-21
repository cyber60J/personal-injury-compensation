from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from personal_injury.application.services import CalculationService
from personal_injury.domain.models import (
    CalculationRequest,
    ApprovalRequest,
    CaseMemberCreate,
    CaseCreate,
    CaseStatus,
    CaseUpdate,
    ClaimCreate,
    EvidenceCreate,
    PartyCreate,
    UserRole,
)
from personal_injury.infrastructure.database import (
    AuditLogModel,
    CaseMemberModel,
    CaseModel,
    CalculationSnapshotModel,
    ClaimModel,
    EvidenceItemModel,
    PartyModel,
    ReviewTaskModel,
    UserModel,
    utcnow,
)
from personal_injury.web.deps import get_current_user, get_db, role_required
from personal_injury.web.policies import case_query, get_case as get_case_for_user


router = APIRouter(prefix="/api/cases", tags=["cases"])


def _case_dict(case: CaseModel) -> dict[str, Any]:
    return {
        "id": case.id,
        "case_number": case.case_number,
        "title": case.title,
        "case_type": case.case_type,
        "status": case.status,
        "jurisdiction": case.jurisdiction,
        "statistical_region": case.statistical_region,
        "incident_date": case.incident_date.isoformat() if case.incident_date else None,
        "first_instance_debate_end_date": (
            case.first_instance_debate_end_date.isoformat()
            if case.first_instance_debate_end_date
            else None
        ),
        "final_judgment_date": (
            case.final_judgment_date.isoformat() if case.final_judgment_date else None
        ),
        "description": case.description,
        "responsible_lawyer_id": case.responsible_lawyer_id,
        "created_by_id": case.created_by_id,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }


def _audit(db: Session, user: UserModel, case_id: str | None, action: str, entity_type: str, entity_id: str | None, details=None):
    db.add(AuditLogModel(
        actor_id=user.id,
        case_id=case_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    ))


def _validate_case_dates(case: CaseModel) -> None:
    if case.incident_date and case.first_instance_debate_end_date:
        if case.first_instance_debate_end_date < case.incident_date:
            raise HTTPException(status_code=422, detail="一审法庭辩论终结日期不能早于侵权日期")
    if case.incident_date and case.final_judgment_date:
        if case.final_judgment_date < case.incident_date:
            raise HTTPException(status_code=422, detail="生效裁判日期不能早于侵权日期")
    if case.first_instance_debate_end_date and case.final_judgment_date:
        if case.final_judgment_date < case.first_instance_debate_end_date:
            raise HTTPException(status_code=422, detail="生效裁判日期不能早于一审法庭辩论终结日期")


@router.get("")
def list_cases(
    q: str | None = Query(default=None, max_length=100),
    status_filter: CaseStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    query = case_query(db, user)
    if q:
        query = query.filter(or_(CaseModel.case_number.contains(q), CaseModel.title.contains(q)))
    if status_filter:
        query = query.filter(CaseModel.status == status_filter.value)
    return [_case_dict(case) for case in query.order_by(CaseModel.updated_at.desc()).all()]


@router.post("", status_code=201)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    if db.query(CaseModel).filter(CaseModel.case_number == payload.case_number).first():
        raise HTTPException(status_code=409, detail="案件编号已存在")
    if payload.responsible_lawyer_id and user.role == UserRole.ASSISTANT.value:
        raise HTTPException(status_code=403, detail="助理不能指定承办律师")
    if payload.responsible_lawyer_id:
        responsible_lawyer = db.query(UserModel).filter(
            UserModel.id == payload.responsible_lawyer_id,
            UserModel.role == UserRole.LAWYER.value,
            UserModel.is_active.is_(True),
        ).first()
        if not responsible_lawyer:
            raise HTTPException(status_code=422, detail="承办律师不存在、未启用或角色不是律师")
    case_data = payload.model_dump(mode="python", exclude={"case_type", "status"})
    case_data.update(
        case_type=payload.case_type.value,
        status=payload.status.value,
        created_by_id=user.id,
    )
    case = CaseModel(**case_data)
    _validate_case_dates(case)
    db.add(case)
    db.flush()
    db.add(CaseMemberModel(case_id=case.id, user_id=user.id, member_role=user.role))
    if payload.responsible_lawyer_id and payload.responsible_lawyer_id != user.id:
        db.add(
            CaseMemberModel(
                case_id=case.id,
                user_id=payload.responsible_lawyer_id,
                member_role=UserRole.LAWYER.value,
            )
        )
    _audit(db, user, case.id, "case_created", "case", case.id, {"case_number": case.case_number})
    db.commit()
    db.refresh(case)
    return _case_dict(case)


@router.post("/{case_id}/members", status_code=201)
def add_case_member(
    case_id: str,
    payload: CaseMemberCreate,
    db: Session = Depends(get_db),
    actor: UserModel = Depends(role_required(UserRole.ADMIN, UserRole.LAWYER)),
):
    case = get_case_for_user(case_id, db, actor)
    if actor.role != UserRole.ADMIN.value and case.responsible_lawyer_id != actor.id:
        raise HTTPException(status_code=403, detail="只有管理员或责任律师可以维护案件成员")
    target = db.query(UserModel).filter(UserModel.id == payload.user_id, UserModel.is_active.is_(True)).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标用户不存在")
    if target.role != payload.member_role.value:
        raise HTTPException(status_code=422, detail="案件成员角色必须与用户系统角色一致")
    existing = db.query(CaseMemberModel).filter(
        CaseMemberModel.case_id == case.id,
        CaseMemberModel.user_id == target.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="用户已经是案件成员")
    member = CaseMemberModel(case_id=case.id, user_id=target.id, member_role=payload.member_role.value)
    db.add(member)
    _audit(db, actor, case.id, "case_member_added", "case_member", member.id, {"user_id": target.id})
    db.commit()
    db.refresh(member)
    return {"id": member.id, "case_id": member.case_id, "user_id": member.user_id, "member_role": member.member_role}


@router.delete("/{case_id}/members/{user_id}", status_code=204)
def remove_case_member(
    case_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    actor: UserModel = Depends(role_required(UserRole.ADMIN, UserRole.LAWYER)),
):
    case = get_case_for_user(case_id, db, actor)
    if actor.role != UserRole.ADMIN.value and case.responsible_lawyer_id != actor.id:
        raise HTTPException(status_code=403, detail="只有管理员或责任律师可以维护案件成员")
    if case.responsible_lawyer_id == user_id:
        raise HTTPException(status_code=409, detail="请先移交责任律师，再移除其案件成员关系")
    member = db.query(CaseMemberModel).filter(
        CaseMemberModel.case_id == case.id,
        CaseMemberModel.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="案件成员不存在")
    _audit(
        db,
        actor,
        case.id,
        "case_member_removed",
        "case_member",
        member.id,
        {"user_id": user_id},
    )
    db.delete(member)
    db.commit()


@router.patch("/{case_id}")
def update_case(
    case_id: str,
    payload: CaseUpdate,
    db: Session = Depends(get_db),
    actor: UserModel = Depends(get_current_user),
):
    case = get_case_for_user(case_id, db, actor)
    fields = payload.model_fields_set
    if not fields:
        raise HTTPException(status_code=422, detail="至少提供一个需要更新的字段")
    if "responsible_lawyer_id" in fields and actor.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="只有管理员可以移交责任律师")
    if "status" in fields and actor.role == UserRole.ASSISTANT.value:
        raise HTTPException(status_code=403, detail="助理不能变更案件状态")
    if "title" in fields and payload.title is None:
        raise HTTPException(status_code=422, detail="案件标题不能为空")
    if "status" in fields and payload.status is None:
        raise HTTPException(status_code=422, detail="案件状态不能为空")

    responsible_member_added = False
    if "responsible_lawyer_id" in fields and payload.responsible_lawyer_id:
        responsible_lawyer = db.query(UserModel).filter(
            UserModel.id == payload.responsible_lawyer_id,
            UserModel.role == UserRole.LAWYER.value,
            UserModel.is_active.is_(True),
        ).first()
        if not responsible_lawyer:
            raise HTTPException(status_code=422, detail="承办律师不存在、未启用或角色不是律师")
        existing_member = db.query(CaseMemberModel).filter(
            CaseMemberModel.case_id == case.id,
            CaseMemberModel.user_id == responsible_lawyer.id,
        ).first()
        if not existing_member:
            db.add(
                CaseMemberModel(
                    case_id=case.id,
                    user_id=responsible_lawyer.id,
                    member_role=UserRole.LAWYER.value,
                )
            )
            responsible_member_added = True

    values = payload.model_dump(mode="python", exclude_unset=True)
    if "status" in values and values["status"] is not None:
        values["status"] = values["status"].value
    original_values = {field: getattr(case, field) for field in fields}
    for field, value in values.items():
        setattr(case, field, value)
    _validate_case_dates(case)
    changed_fields = [field for field in fields if getattr(case, field) != original_values[field]]
    reassigned_task_count = 0
    if "responsible_lawyer_id" in changed_fields:
        task_query = db.query(ReviewTaskModel).filter(
            ReviewTaskModel.case_id == case.id,
            ReviewTaskModel.status == "open",
        )
        old_responsible_id = original_values["responsible_lawyer_id"]
        if old_responsible_id:
            task_query = task_query.filter(ReviewTaskModel.assigned_to_id == old_responsible_id)
        else:
            task_query = task_query.filter(ReviewTaskModel.assigned_to_id.is_(None))
        reassigned_task_count = task_query.update(
            {ReviewTaskModel.assigned_to_id: case.responsible_lawyer_id},
            synchronize_session=False,
        )
    if not changed_fields and not responsible_member_added:
        return _case_dict(case)
    case.updated_at = utcnow()
    audit_fields = sorted(changed_fields)
    if responsible_member_added and "responsible_lawyer_id" not in changed_fields:
        audit_fields.append("responsible_lawyer_membership")
    _audit(
        db,
        actor,
        case.id,
        "case_updated",
        "case",
        case.id,
        {"fields": audit_fields, "reassigned_open_tasks": reassigned_task_count},
    )
    db.commit()
    db.refresh(case)
    return _case_dict(case)


@router.get("/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    case = get_case_for_user(case_id, db, user)
    return {
        **_case_dict(case),
        "parties": [_party_dict(item) for item in db.query(PartyModel).filter(PartyModel.case_id == case.id).all()],
        "evidence": [_evidence_dict(item) for item in db.query(EvidenceItemModel).filter(EvidenceItemModel.case_id == case.id).all()],
        "claims": [_claim_dict(item) for item in db.query(ClaimModel).filter(ClaimModel.case_id == case.id).all()],
        "calculations": [_snapshot_dict(item) for item in db.query(CalculationSnapshotModel).filter(CalculationSnapshotModel.case_id == case.id).all()],
        "review_tasks": [_task_dict(item) for item in db.query(ReviewTaskModel).filter(ReviewTaskModel.case_id == case.id).all()],
    }


@router.post("/{case_id}/parties", status_code=201)
def add_party(
    case_id: str,
    payload: PartyCreate,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    case = get_case_for_user(case_id, db, user)
    party = PartyModel(case_id=case.id, **payload.model_dump())
    db.add(party)
    db.flush()
    _audit(db, user, case.id, "party_created", "party", party.id, {"role": party.role})
    db.commit()
    db.refresh(party)
    return _party_dict(party)


@router.post("/{case_id}/evidence", status_code=201)
def add_evidence(
    case_id: str,
    payload: EvidenceCreate,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    case = get_case_for_user(case_id, db, user)
    evidence_data = payload.model_dump(mode="python", exclude={"status"})
    evidence_data.update(
        case_id=case.id,
        created_by_id=user.id,
        status=payload.status.value,
    )
    evidence = EvidenceItemModel(**evidence_data)
    db.add(evidence)
    db.flush()
    _audit(db, user, case.id, "evidence_created", "evidence", evidence.id, {"name": evidence.name})
    db.commit()
    db.refresh(evidence)
    return _evidence_dict(evidence)


@router.post("/{case_id}/claims", status_code=201)
def add_claim(
    case_id: str,
    payload: ClaimCreate,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    case = get_case_for_user(case_id, db, user)
    claim = ClaimModel(
        case_id=case.id,
        created_by_id=user.id,
        requested_amount=Decimal(str(payload.requested_amount)) if payload.requested_amount is not None else None,
        claim_type=payload.claim_type,
        input_data=payload.input_data,
        notes=payload.notes,
    )
    db.add(claim)
    db.flush()
    _audit(db, user, case.id, "claim_created", "claim", claim.id, {"claim_type": claim.claim_type})
    db.commit()
    db.refresh(claim)
    return _claim_dict(claim)


@router.post("/{case_id}/calculations", status_code=201)
def calculate_case(
    case_id: str,
    payload: CalculationRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    case = get_case_for_user(case_id, db, user)
    try:
        snapshot = CalculationService(db).calculate_and_persist(
            case=case,
            input_data=payload.input_data,
            actor=user,
            jurisdiction=payload.jurisdiction,
            standard_year=payload.standard_year,
            rule_as_of=payload.rule_as_of,
            allow_demo_standards=request.app.state.settings.allow_demo_standards,
        )
    except (ValueError, KeyError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _snapshot_dict(snapshot)


@router.post("/{case_id}/calculations/{snapshot_id}/approve")
def approve_calculation(
    case_id: str,
    snapshot_id: str,
    payload: ApprovalRequest | None = None,
    db: Session = Depends(get_db),
    user: UserModel = Depends(role_required(UserRole.ADMIN, UserRole.LAWYER)),
):
    case = get_case_for_user(case_id, db, user)
    snapshot = db.query(CalculationSnapshotModel).filter(
        CalculationSnapshotModel.id == snapshot_id,
        CalculationSnapshotModel.case_id == case.id,
    ).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="计算快照不存在")
    try:
        approved = CalculationService(db).approve(
            snapshot,
            user,
            reason=payload.reason if payload else None,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _snapshot_dict(approved)


@router.get("/{case_id}/review-tasks")
def list_review_tasks(case_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    case = get_case_for_user(case_id, db, user)
    return [_task_dict(item) for item in db.query(ReviewTaskModel).filter(ReviewTaskModel.case_id == case.id).all()]


@router.post("/{case_id}/review-tasks/{task_id}/complete")
def complete_review_task(
    case_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    user: UserModel = Depends(role_required(UserRole.ADMIN, UserRole.LAWYER)),
):
    case = get_case_for_user(case_id, db, user)
    task = db.query(ReviewTaskModel).filter(
        ReviewTaskModel.id == task_id,
        ReviewTaskModel.case_id == case.id,
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="复核任务不存在")
    if task.assigned_to_id and user.role != UserRole.ADMIN.value and task.assigned_to_id != user.id:
        raise HTTPException(status_code=403, detail="该复核任务未分配给当前律师")
    task.status = "completed"
    task.completed_at = utcnow()
    _audit(db, user, case.id, "review_task_completed", "review_task", task.id)
    db.commit()
    return _task_dict(task)


@router.get("/{case_id}/export", response_class=PlainTextResponse)
def export_case(
    case_id: str,
    export_format: str = Query(default="markdown", alias="format"),
    db: Session = Depends(get_db),
    user: UserModel = Depends(role_required(UserRole.ADMIN, UserRole.LAWYER)),
):
    if export_format not in {"markdown", "txt"}:
        raise HTTPException(status_code=400, detail="仅支持 markdown 或 txt")
    case = get_case_for_user(case_id, db, user)
    calculations = db.query(CalculationSnapshotModel).filter(
        CalculationSnapshotModel.case_id == case.id
    ).order_by(CalculationSnapshotModel.created_at.desc()).all()
    tasks = db.query(ReviewTaskModel).filter(ReviewTaskModel.case_id == case.id).all()
    lines = [
        f"# {case.title}",
        "",
        f"- 案件编号：{case.case_number}",
        f"- 案由：{case.case_type}",
        f"- 管辖地区：{case.jurisdiction or ''}",
        f"- 状态：{case.status}",
        "",
        "## 计算快照",
    ]
    for snapshot in calculations:
        lines.extend([
            f"- 规则版本：{snapshot.rule_version}",
            f"- 审核状态：{snapshot.review_status}",
            f"- 应付结果：{snapshot.payable_results}",
            f"- 规则与证据复核：{snapshot.review_output.get('review_metadata', {})}",
        ])
    lines.extend(["", "## 待复核事项"])
    for item in tasks:
        lines.append(f"- [{item.status}] {item.title}：{item.description}")
    _audit(db, user, case.id, "case_exported", "case", case.id, {"format": export_format})
    db.commit()
    return "\n".join(lines)


def _party_dict(item: PartyModel):
    return {"id": item.id, "role": item.role, "name": item.name, "identity_no": item.identity_no, "contact": item.contact, "notes": item.notes}


def _evidence_dict(item: EvidenceItemModel):
    return {"id": item.id, "name": item.name, "evidence_type": item.evidence_type, "claim_type": item.claim_type, "source": item.source, "document_date": item.document_date.isoformat() if item.document_date else None, "file_path": item.file_path, "file_sha256": item.file_sha256, "status": item.status, "notes": item.notes}


def _claim_dict(item: ClaimModel):
    return {"id": item.id, "claim_type": item.claim_type, "requested_amount": float(item.requested_amount) if item.requested_amount is not None else None, "input_data": item.input_data, "notes": item.notes}


def _snapshot_dict(item: CalculationSnapshotModel):
    return {"id": item.id, "algorithm_version": item.algorithm_version, "rule_version": item.rule_version, "rule_as_of": item.rule_as_of.isoformat(), "rule_context": item.rule_context, "standard_year": item.standard_year, "standards_snapshot": item.standards_snapshot, "jurisdiction": item.jurisdiction, "input_data": item.input_data, "raw_results": item.raw_results, "payable_results": item.payable_results, "review_output": item.review_output, "review_status": item.review_status, "created_by_id": item.created_by_id, "approved_by_id": item.approved_by_id, "created_at": item.created_at.isoformat()}


def _task_dict(item: ReviewTaskModel):
    return {"id": item.id, "calculation_snapshot_id": item.calculation_snapshot_id, "title": item.title, "description": item.description, "status": item.status, "assigned_to_id": item.assigned_to_id, "created_by_id": item.created_by_id, "created_at": item.created_at.isoformat(), "completed_at": item.completed_at.isoformat() if item.completed_at else None}
