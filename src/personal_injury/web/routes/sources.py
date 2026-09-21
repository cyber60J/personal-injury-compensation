from __future__ import annotations

import hashlib
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from personal_injury.infrastructure.database import (
    AuditLogModel,
    CaseModel,
    LegalSourceModel,
    StatisticalStandardModel,
    UserModel,
    utcnow,
)
from personal_injury.web.deps import get_current_user, get_db, role_required
from personal_injury.web.policies import case_query, get_case
from personal_injury.domain.models import ApprovalRequest, UserRole


router = APIRouter(tags=["sources"])

_REVIEW_REASON_LABELS = {
    "missing_urban_population": "未明确城镇居民口径",
    "missing_per_capita_scope": "未明确人均口径",
    "conflicting_ownership": "私营与非私营单位口径冲突",
    "conflicting_employment_scope": "就业人员与在岗职工口径冲突",
    "incomplete_industry_scope": "居民服务、修理和其他服务业范围不完整",
    "service_requires_non_private_units": "行业工资尚未确认非私营单位口径",
    "service_requires_employed_persons": "行业工资尚未确认就业人员口径",
    "on_duty_ownership_subgroup_not_total": "在岗职工数据仅覆盖部分单位性质，不能作为全部单位数据",
    "missing_employment_scope": "未明确就业人员或在岗职工口径",
    "missing_urban_units_scope": "未明确城镇单位口径",
    "missing_annual_wage_scope": "未明确年平均工资口径",
    "ambiguous_statistical_year": "原文包含多个年度，尚未确定数值所属年度",
    "missing_statistical_year": "未找到统计年度",
    "statistical_year_mismatch": "原文统计年度与目标年度不一致",
    "region_mismatch": "原文地区与目标地区不一致",
    "ambiguous_region": "原文包含多个地区，尚未确定数值所属地区",
    "missing_region": "未找到统计地区",
    "missing_or_ambiguous_unit": "单位缺失或存在多种单位",
    "amount_out_of_range": "数值超出预期范围",
    "relative_year_without_base": "原文使用上年等相对年度，但无法确定基准年",
    "conflicting_values": "同一指标存在多个不同数值",
    "nested_table_requires_review": "嵌套表格需人工核实行列关系",
    "needs_ocr": "扫描页需要文字识别和人工核实",
    "document_size_limit": "原文超过自动处理大小限制",
    "unsupported_document_format": "原文格式暂不支持自动抽取",
    "document_extraction_failed": "原文自动抽取失败，请人工核实",
}


def _review_message(value) -> str:
    message = str(value)
    code, separator, context = message.partition(":")
    label = _REVIEW_REASON_LABELS.get(code)
    if not label:
        return message
    if code == "needs_ocr" and separator:
        return label + "（" + context.strip().replace("page ", "第 ") + " 页）"
    return label


def _record_evidence(item: StatisticalStandardModel) -> tuple[dict, dict]:
    record = item.source_record if isinstance(item.source_record, dict) else {}
    evidence = record.get("evidence")
    return record, evidence if isinstance(evidence, dict) else {}


def _review_findings(item: StatisticalStandardModel) -> tuple[list[str], list[str]]:
    record, evidence = _record_evidence(item)
    warnings: list[str] = []
    blockers: list[str] = []
    if item.status == "invalidated":
        blockers.append("该标准已因新采集结果失效，请重新采集并导入唯一确认的数值")
    region = evidence.get("region")
    if region and str(region).strip() != item.region:
        blockers.append("原文地区与统计标准地区不一致，请修正采集记录后重新导入")
    year = evidence.get("statistical_year")
    if year is not None and str(year).strip() and str(year).strip() != str(item.year):
        blockers.append("原文统计年度与统计标准年度不一致，请修正采集记录后重新导入")
    if record.get("collector_status") != "已提取":
        warnings.append("采集状态不是已提取")
    if evidence.get("source_domain_verified") is not True:
        warnings.append("来源域名未经验证")
    if evidence.get("transport_secure") is not True:
        warnings.append("来源未使用HTTPS")
    if evidence.get("validation_status") != "verified":
        warnings.append("抽取证据尚未通过校验（旧数据也需人工核实）")
    required = {
        "region": "原文地区", "statistical_year": "原文统计年度", "scope": "统计口径",
        "raw_value": "原始数值", "raw_unit": "原始单位", "unit": "换算后单位",
        "snippet": "原文片段", "locator": "原文位置", "extractor_version": "抽取版本",
    }
    missing = [label for key, label in required.items()
               if evidence.get(key) is None or evidence.get(key) == ""
               or evidence.get(key) == {} or evidence.get(key) == []]
    if missing:
        warnings.append("证据缺少：" + "、".join(missing))
    if evidence.get("conflicts"):
        warnings.append("存在冲突候选值")
    for messages in (evidence.get("review_reasons"), record.get("extraction_warnings")):
        if isinstance(messages, list):
            warnings.extend(_review_message(message) for message in messages if message)
        elif messages:
            warnings.append(_review_message(messages))
    return list(dict.fromkeys(warnings)), blockers


def _archive_sha256(item: StatisticalStandardModel) -> str | None:
    _, evidence = _record_evidence(item)
    digest = evidence.get("archive_sha256") or evidence.get("content_sha256")
    return digest.lower() if isinstance(digest, str) and re.fullmatch(r"[a-fA-F0-9]{64}", digest) else None


def _public_record(value):
    """Storage paths are an internal detail; originals are served by the authorized API."""
    if isinstance(value, dict):
        result = {key: _public_record(item) for key, item in value.items()
                  if key not in {"archive_path", "archive_metadata_path", "local_path", "file_path", "download_path"}}
        if isinstance(value.get("review_reasons"), list):
            result["review_messages"] = [_review_message(item) for item in value["review_reasons"]]
        return result
    if isinstance(value, list):
        return [_public_record(item) for item in value]
    return value


def _source_dict(item: LegalSourceModel) -> dict:
    return {
        "id": item.id,
        "source_key": item.source_key,
        "title": item.title,
        "url": item.url,
        "source_type": item.source_type,
        "effective_from": item.effective_from.isoformat() if item.effective_from else None,
        "effective_to": item.effective_to.isoformat() if item.effective_to else None,
        "verification_status": item.verification_status,
        "content_sha256": item.content_sha256,
        "verified_by_id": item.verified_by_id,
        "verified_at": item.verified_at.isoformat() if item.verified_at else None,
        "notes": item.notes,
    }


def _standard_dict(item: StatisticalStandardModel) -> dict:
    warnings, blockers = _review_findings(item)
    return {
        "id": item.id,
        "region": item.region,
        "year": item.year,
        "field_name": item.field_name,
        "value": float(item.value),
        "source_key": item.source_key,
        "source_title": item.source_title,
        "source_url": item.source_url,
        "publish_date": item.publish_date.isoformat() if item.publish_date else None,
        "status": item.status,
        "source_record": _public_record(item.source_record),
        "review_warnings": warnings,
        "approval_blockers": blockers,
        "archive_url": f"/api/statistical-standards/{item.id}/original" if _archive_sha256(item) else None,
        "confirmed_by_id": item.confirmed_by_id,
        "confirmed_at": item.confirmed_at.isoformat() if item.confirmed_at else None,
    }


@router.get("/api/legal-sources")
def list_legal_sources(
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    return [_source_dict(item) for item in db.query(LegalSourceModel).order_by(LegalSourceModel.source_key).all()]


@router.post("/api/legal-sources/{source_id}/verify")
def verify_legal_source(
    source_id: str,
    db: Session = Depends(get_db),
    user: UserModel = Depends(role_required(UserRole.ADMIN, UserRole.LAWYER)),
):
    source = db.query(LegalSourceModel).filter(LegalSourceModel.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="法律来源不存在")
    source.verification_status = "verified"
    source.verified_by_id = user.id
    source.verified_at = utcnow()
    db.add(AuditLogModel(
        actor_id=user.id,
        action="legal_source_verified",
        entity_type="legal_source",
        entity_id=source.id,
        details={"source_key": source.source_key},
    ))
    db.commit()
    return _source_dict(source)


@router.get("/api/statistical-standards")
def list_statistical_standards(
    region: str | None = None,
    year: int | None = None,
    include_pending: bool = True,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    query = db.query(StatisticalStandardModel)
    if region:
        query = query.filter(StatisticalStandardModel.region == region)
    if year:
        query = query.filter(StatisticalStandardModel.year == year)
    if not include_pending:
        query = query.filter(StatisticalStandardModel.status == "approved")
    return [_standard_dict(item) for item in query.order_by(StatisticalStandardModel.year.desc()).all()]


@router.get("/api/statistical-standards/{standard_id}/original")
def download_statistical_original(
    standard_id: str,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    from personal_injury.collection.source_archive import ArchiveStore

    standard = db.query(StatisticalStandardModel).filter(StatisticalStandardModel.id == standard_id).first()
    if not standard:
        raise HTTPException(status_code=404, detail="统计标准不存在")
    digest = _archive_sha256(standard)
    if not digest:
        raise HTTPException(status_code=404, detail="尚未登记原文归档")
    try:
        path = ArchiveStore().resolve(digest)
        if path is None:
            raise HTTPException(status_code=404, detail="原文归档不存在或完整性校验失败")
        content = path.read_bytes()
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="原文归档不可用") from None
    # Return exactly the bytes that were checked, including if a file changes after resolve().
    if hashlib.sha256(content).hexdigest() != digest:
        raise HTTPException(status_code=409, detail="原文归档完整性校验失败，请重新采集")
    _, evidence = _record_evidence(standard)
    content_type = str(evidence.get("content_type") or evidence.get("source_content_type") or "").split(";", 1)[0].strip().lower()
    suffix = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-excel": ".xls",
        "text/csv": ".csv", "text/html": ".html", "text/plain": ".txt",
        "application/json": ".json",
    }.get(content_type, path.suffix.lower())
    if suffix not in {".pdf", ".xlsx", ".xls", ".csv", ".html", ".htm", ".txt", ".json"}:
        suffix = ".bin"
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="source-{digest[:16]}{suffix}"'},
    )


@router.post("/api/statistical-standards/{standard_id}/approve")
def approve_statistical_standard(
    standard_id: str,
    payload: ApprovalRequest | None = None,
    db: Session = Depends(get_db),
    user: UserModel = Depends(role_required(UserRole.ADMIN, UserRole.LAWYER)),
):
    standard = db.query(StatisticalStandardModel).filter(StatisticalStandardModel.id == standard_id).first()
    if not standard:
        raise HTTPException(status_code=404, detail="统计标准不存在")
    if standard.status == "approved":
        raise HTTPException(status_code=409, detail="统计标准已经批准")
    warnings, blockers = _review_findings(standard)
    if blockers:
        raise HTTPException(status_code=422, detail="；".join(blockers))
    reason = payload.reason.strip() if payload and payload.reason else None
    if warnings and not reason:
        raise HTTPException(
            status_code=422,
            detail="来源存在需人工说明的问题：" + "；".join(warnings),
        )
    standard.status = "approved"
    standard.confirmed_by_id = user.id
    standard.confirmed_at = utcnow()
    db.add(AuditLogModel(
        actor_id=user.id,
        action="statistical_standard_approved",
        entity_type="statistical_standard",
        entity_id=standard.id,
        details={
            "region": standard.region,
            "year": standard.year,
            "field_name": standard.field_name,
            "source_warnings": warnings,
            "reason": reason,
        },
    ))
    db.commit()
    return _standard_dict(standard)


@router.get("/api/audit-logs")
def list_audit_logs(
    case_id: str | None = None,
    db: Session = Depends(get_db),
    user: UserModel = Depends(role_required(UserRole.ADMIN, UserRole.LAWYER)),
):
    query = db.query(AuditLogModel)
    if case_id:
        get_case(case_id, db, user)
        query = query.filter(AuditLogModel.case_id == case_id)
    elif user.role != UserRole.ADMIN.value:
        visible_case_ids = case_query(db, user).with_entities(CaseModel.id)
        query = query.filter(
            or_(
                AuditLogModel.case_id.in_(visible_case_ids),
                AuditLogModel.case_id.is_(None) & (AuditLogModel.actor_id == user.id),
            )
        )
    return [
        {
            "id": item.id,
            "actor_id": item.actor_id,
            "case_id": item.case_id,
            "action": item.action,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "details": item.details,
            "created_at": item.created_at.isoformat(),
        }
        for item in query.order_by(AuditLogModel.created_at.desc()).limit(500).all()
    ]
