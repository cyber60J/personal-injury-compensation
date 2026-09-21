from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CaseType(StrEnum):
    TRAFFIC_ACCIDENT = "traffic_accident"
    EMPLOYMENT_SERVICE = "employment_service"
    GENERAL_PERSONAL_INJURY = "general_personal_injury"


class CaseStatus(StrEnum):
    OPEN = "open"
    REVIEW = "review"
    CLOSED = "closed"
    ARCHIVED = "archived"


class UserRole(StrEnum):
    ADMIN = "admin"
    LAWYER = "lawyer"
    ASSISTANT = "assistant"


class EvidenceStatus(StrEnum):
    MISSING = "missing"
    COLLECTED = "collected"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ReviewStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class CaseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    case_number: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    case_type: CaseType = CaseType.GENERAL_PERSONAL_INJURY
    status: CaseStatus = CaseStatus.OPEN
    jurisdiction: Optional[str] = Field(default=None, max_length=200)
    statistical_region: Optional[str] = Field(default=None, max_length=120)
    incident_date: Optional[date] = None
    first_instance_debate_end_date: Optional[date] = None
    final_judgment_date: Optional[date] = None
    description: Optional[str] = None
    responsible_lawyer_id: Optional[str] = None


class CaseRead(CaseCreate):
    id: str
    created_by_id: str
    created_at: str
    updated_at: str


class CaseUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[CaseStatus] = None
    jurisdiction: Optional[str] = Field(default=None, max_length=200)
    statistical_region: Optional[str] = Field(default=None, max_length=120)
    incident_date: Optional[date] = None
    first_instance_debate_end_date: Optional[date] = None
    final_judgment_date: Optional[date] = None
    description: Optional[str] = None
    responsible_lawyer_id: Optional[str] = None


class PartyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    role: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    identity_no: Optional[str] = Field(default=None, max_length=80)
    contact: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None


class CaseMemberCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    member_role: UserRole = UserRole.ASSISTANT


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    evidence_type: str = Field(default="other", max_length=80)
    claim_type: Optional[str] = Field(default=None, max_length=80)
    source: Optional[str] = Field(default=None, max_length=200)
    document_date: Optional[date] = None
    file_path: Optional[str] = Field(default=None, max_length=500)
    file_sha256: Optional[str] = Field(default=None, max_length=64)
    status: EvidenceStatus = EvidenceStatus.COLLECTED
    notes: Optional[str] = None


class ClaimCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    claim_type: str = Field(min_length=1, max_length=80)
    requested_amount: Optional[float] = Field(default=None, ge=0)
    input_data: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    input_data: Dict[str, Any] = Field(default_factory=dict)
    jurisdiction: Optional[str] = Field(default=None, max_length=200)
    standard_year: Optional[int] = Field(default=None, ge=1900, le=2200)
    rule_as_of: Optional[date] = None


class ApprovalRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=256)


class BootstrapRequest(LoginRequest):
    display_name: str = Field(min_length=1, max_length=120)


class UserCreate(LoginRequest):
    display_name: str = Field(min_length=1, max_length=120)
    role: UserRole = UserRole.ASSISTANT


class UserAdminUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    password: Optional[str] = Field(default=None, min_length=8, max_length=256)
    is_active: Optional[bool] = None


class UserRead(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole
    is_active: bool


class TokenRead(BaseModel):
    expires_at: str
    user: UserRead
