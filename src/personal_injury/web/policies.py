from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from personal_injury.domain.models import UserRole
from personal_injury.infrastructure.database import CaseMemberModel, CaseModel, UserModel


def case_query(db: Session, user: UserModel):
    """Return only cases visible to the current firm user."""
    query = db.query(CaseModel)
    if user.role != UserRole.ADMIN.value:
        query = query.outerjoin(
            CaseMemberModel,
            CaseMemberModel.case_id == CaseModel.id,
        ).filter(
            or_(
                CaseModel.responsible_lawyer_id == user.id,
                CaseMemberModel.user_id == user.id,
            )
        )
    return query.distinct()


def get_case(case_id: str, db: Session, user: UserModel) -> CaseModel:
    case = case_query(db, user).filter(CaseModel.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在或无权访问")
    return case
