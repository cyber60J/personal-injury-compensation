from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Generator, Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30), default="assistant", index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionTokenModel(Base):
    __tablename__ = "session_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CaseModel(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    case_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    statistical_region: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    incident_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    first_instance_debate_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    final_judgment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    responsible_lawyer_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CaseMemberModel(Base):
    __tablename__ = "case_members"
    __table_args__ = (UniqueConstraint("case_id", "user_id", name="uq_case_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    member_role: Mapped[str] = mapped_column(String(30), default="assistant")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PartyModel(Base):
    __tablename__ = "parties"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    identity_no: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    contact: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceItemModel(Base):
    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    evidence_type: Mapped[str] = mapped_column(String(80), default="other")
    claim_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    document_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="collected", index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClaimModel(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    claim_type: Mapped[str] = mapped_column(String(80), index=True)
    requested_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CalculationSnapshotModel(Base):
    __tablename__ = "calculation_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    algorithm_version: Mapped[str] = mapped_column(String(80))
    rule_version: Mapped[str] = mapped_column(String(80), index=True)
    rule_as_of: Mapped[date] = mapped_column(Date)
    rule_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    standard_year: Mapped[Optional[int]] = mapped_column(nullable=True)
    standards_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    raw_results: Mapped[dict[str, Any]] = mapped_column(JSON)
    payable_results: Mapped[dict[str, Any]] = mapped_column(JSON)
    review_output: Mapped[dict[str, Any]] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    approved_by_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class LegalSourceModel(Base):
    __tablename__ = "legal_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000))
    source_type: Mapped[str] = mapped_column(String(50), default="official")
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), default="pending")
    content_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    verified_by_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StatisticalStandardModel(Base):
    __tablename__ = "statistical_standards"
    __table_args__ = (UniqueConstraint("region", "year", "field_name", name="uq_statistical_standard"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    region: Mapped[str] = mapped_column(String(120), index=True)
    year: Mapped[int] = mapped_column(index=True)
    field_name: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    source_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    source_title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    publish_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    source_record: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confirmed_by_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewTaskModel(Base):
    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    calculation_snapshot_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("calculation_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    claim_id: Mapped[Optional[str]] = mapped_column(ForeignKey("claims.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    assigned_to_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    case_id: Mapped[Optional[str]] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def create_engine_for_url(database_url: str):
    connect_args = {}
    engine = None
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if database_url.startswith("sqlite:///") and not database_url.endswith(":memory:"):
            sqlite_path = database_url.removeprefix("sqlite:///").split("?", 1)[0]
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        if database_url.endswith(":memory:") or database_url.endswith("sqlite://"):
            from sqlalchemy.pool import StaticPool
            engine = create_engine(database_url, connect_args=connect_args, poolclass=StaticPool)
        else:
            engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()
        return engine
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def create_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(engine) -> None:
    Base.metadata.create_all(bind=engine)


def get_db(session_factory) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
