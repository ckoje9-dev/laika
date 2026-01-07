"""add dxf parse sections table."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_add_dxf_parse_sections"
down_revision = "0002_expand_dxf_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dxf_parse_sections",
        sa.Column("file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("header", postgresql.JSONB(), nullable=True),
        sa.Column("classes", postgresql.JSONB(), nullable=True),
        sa.Column("tables", postgresql.JSONB(), nullable=True),
        sa.Column("blocks", postgresql.JSONB(), nullable=True),
        sa.Column("entities", postgresql.JSONB(), nullable=True),
        sa.Column("objects", postgresql.JSONB(), nullable=True),
        sa.Column("thumbnail", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dxf_parse_sections")
