"""Create the initial personal injury case schema.

Revision ID: 0001_initial
Revises: None
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_users_username", "users", ["username"], unique=True)
    _index("ix_users_role", "users", ["role"])

    op.create_table(
        "session_tokens",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_session_tokens_user_id", "session_tokens", ["user_id"])
    _index("ix_session_tokens_token_hash", "session_tokens", ["token_hash"], unique=True)
    _index("ix_session_tokens_expires_at", "session_tokens", ["expires_at"])

    op.create_table(
        "cases",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("case_number", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("case_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("jurisdiction", sa.String(200), nullable=True),
        sa.Column("statistical_region", sa.String(120), nullable=True),
        sa.Column("incident_date", sa.Date(), nullable=True),
        sa.Column("first_instance_debate_end_date", sa.Date(), nullable=True),
        sa.Column("final_judgment_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("responsible_lawyer_id", sa.String(36), nullable=True),
        sa.Column("created_by_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["responsible_lawyer_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_cases_case_number", "cases", ["case_number"], unique=True)
    _index("ix_cases_case_type", "cases", ["case_type"])
    _index("ix_cases_status", "cases", ["status"])
    _index("ix_cases_statistical_region", "cases", ["statistical_region"])
    _index("ix_cases_responsible_lawyer_id", "cases", ["responsible_lawyer_id"])
    _index("ix_cases_created_by_id", "cases", ["created_by_id"])

    op.create_table(
        "case_members",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("member_role", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "user_id", name="uq_case_member"),
    )
    _index("ix_case_members_case_id", "case_members", ["case_id"])
    _index("ix_case_members_user_id", "case_members", ["user_id"])

    op.create_table(
        "parties",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("identity_no", sa.String(80), nullable=True),
        sa.Column("contact", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_parties_case_id", "parties", ["case_id"])

    op.create_table(
        "evidence_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("evidence_type", sa.String(80), nullable=False),
        sa.Column("claim_type", sa.String(80), nullable=True),
        sa.Column("source", sa.String(200), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_evidence_items_case_id", "evidence_items", ["case_id"])
    _index("ix_evidence_items_claim_type", "evidence_items", ["claim_type"])
    _index("ix_evidence_items_status", "evidence_items", ["status"])
    _index("ix_evidence_items_created_by_id", "evidence_items", ["created_by_id"])

    op.create_table(
        "claims",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("claim_type", sa.String(80), nullable=False),
        sa.Column("requested_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_claims_case_id", "claims", ["case_id"])
    _index("ix_claims_claim_type", "claims", ["claim_type"])
    _index("ix_claims_created_by_id", "claims", ["created_by_id"])

    op.create_table(
        "calculation_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("algorithm_version", sa.String(80), nullable=False),
        sa.Column("rule_version", sa.String(80), nullable=False),
        sa.Column("rule_as_of", sa.Date(), nullable=False),
        sa.Column("rule_context", sa.JSON(), nullable=False),
        sa.Column("standard_year", sa.Integer(), nullable=True),
        sa.Column("standards_snapshot", sa.JSON(), nullable=False),
        sa.Column("jurisdiction", sa.String(200), nullable=True),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("raw_results", sa.JSON(), nullable=False),
        sa.Column("payable_results", sa.JSON(), nullable=False),
        sa.Column("review_output", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(30), nullable=False),
        sa.Column("created_by_id", sa.String(36), nullable=False),
        sa.Column("approved_by_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_calculation_snapshots_case_id", "calculation_snapshots", ["case_id"])
    _index("ix_calculation_snapshots_rule_version", "calculation_snapshots", ["rule_version"])
    _index("ix_calculation_snapshots_review_status", "calculation_snapshots", ["review_status"])
    _index("ix_calculation_snapshots_created_by_id", "calculation_snapshots", ["created_by_id"])

    op.create_table(
        "legal_sources",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("verification_status", sa.String(30), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("verified_by_id", sa.String(36), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_legal_sources_source_key", "legal_sources", ["source_key"], unique=True)

    op.create_table(
        "statistical_standards",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("region", sa.String(120), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(120), nullable=False),
        sa.Column("value", sa.Numeric(18, 2), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=True),
        sa.Column("source_title", sa.String(300), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("publish_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("source_record", sa.JSON(), nullable=False),
        sa.Column("confirmed_by_id", sa.String(36), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["confirmed_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region", "year", "field_name", name="uq_statistical_standard"),
    )
    _index("ix_statistical_standards_region", "statistical_standards", ["region"])
    _index("ix_statistical_standards_year", "statistical_standards", ["year"])
    _index("ix_statistical_standards_field_name", "statistical_standards", ["field_name"])
    _index("ix_statistical_standards_source_key", "statistical_standards", ["source_key"])
    _index("ix_statistical_standards_status", "statistical_standards", ["status"])

    op.create_table(
        "review_tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("calculation_snapshot_id", sa.String(36), nullable=True),
        sa.Column("claim_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("assigned_to_id", sa.String(36), nullable=True),
        sa.Column("created_by_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["calculation_snapshot_id"], ["calculation_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_review_tasks_case_id", "review_tasks", ["case_id"])
    _index("ix_review_tasks_calculation_snapshot_id", "review_tasks", ["calculation_snapshot_id"])
    _index("ix_review_tasks_status", "review_tasks", ["status"])
    _index("ix_review_tasks_created_by_id", "review_tasks", ["created_by_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("case_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    _index("ix_audit_logs_case_id", "audit_logs", ["case_id"])
    _index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    for table_name in (
        "audit_logs",
        "review_tasks",
        "statistical_standards",
        "legal_sources",
        "calculation_snapshots",
        "claims",
        "evidence_items",
        "parties",
        "case_members",
        "cases",
        "session_tokens",
        "users",
    ):
        op.drop_table(table_name)
