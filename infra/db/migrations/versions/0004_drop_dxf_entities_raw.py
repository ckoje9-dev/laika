"""drop dxf_entities_raw table."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

revision = "0004_drop_dxf_entities_raw"
down_revision = "0003_add_dxf_parse_sections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_dxf_entities_raw_geom", table_name="dxf_entities_raw")
    op.drop_index("idx_dxf_entities_raw_file_id", table_name="dxf_entities_raw")
    op.drop_constraint("ck_dxf_entities_raw_type", "dxf_entities_raw", type_="check")
    op.drop_table("dxf_entities_raw")


def downgrade() -> None:
    op.create_table(
        "dxf_entities_raw",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("layer", sa.Text(), nullable=True),
        sa.Column("geom", Geometry(geometry_type="GEOMETRY", srid=0), nullable=True),
        sa.Column("bbox", Geometry(geometry_type="GEOMETRY", srid=0), nullable=True),
        sa.Column("length", sa.Numeric(), nullable=True),
        sa.Column("area", sa.Numeric(), nullable=True),
        sa.Column("properties", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_check_constraint(
        "ck_dxf_entities_raw_type",
        "dxf_entities_raw",
        "type in ('LINE','POLYLINE','LWPOLYLINE','CIRCLE','ARC','ELLIPSE','TEXT','MTEXT','HATCH','DIMENSION','BLOCK','INSERT')",
    )
    op.create_index("idx_dxf_entities_raw_file_id", "dxf_entities_raw", ["file_id"], if_not_exists=True)
    op.create_index("idx_dxf_entities_raw_geom", "dxf_entities_raw", ["geom"], postgresql_using="gist", if_not_exists=True)
