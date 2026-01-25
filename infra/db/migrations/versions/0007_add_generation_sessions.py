"""Add generation sessions table for AI drawing generation

Revision ID: 0007_add_generation_sessions
Revises: 0006_add_pgvector
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_add_generation_sessions"
down_revision = "0006_add_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 생성 세션 테이블
    op.create_table(
        "generation_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("conversation_history", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # 생성 버전 테이블 (세션 내 각 생성/수정 버전)
    op.create_table(
        "generation_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("generation_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("schema_json", postgresql.JSONB(), nullable=False),
        sa.Column("validation_result", postgresql.JSONB(), nullable=True),
        sa.Column("dxf_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # 인덱스
    op.create_index("idx_generation_sessions_project_id", "generation_sessions", ["project_id"])
    op.create_index("idx_generation_versions_session_id", "generation_versions", ["session_id"])


def downgrade() -> None:
    op.drop_index("idx_generation_versions_session_id", table_name="generation_versions")
    op.drop_index("idx_generation_sessions_project_id", table_name="generation_sessions")
    op.drop_table("generation_versions")
    op.drop_table("generation_sessions")
