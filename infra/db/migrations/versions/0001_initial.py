"""initial schema with postgis extensions"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("location_geom", Geometry(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_versions_project_id", "versions", ["project_id"], if_not_exists=True)

    op.create_table(
        "files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("path_original", sa.Text(), nullable=True),
        sa.Column("path_dxf", sa.Text(), nullable=True),
        sa.Column("read_only", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("width", sa.Numeric(), nullable=True),
        sa.Column("height", sa.Numeric(), nullable=True),
        sa.Column("layer_count", sa.Integer(), nullable=True),
        sa.Column("entity_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_check_constraint("ck_files_type", "files", "type in ('dwg','dxf','pdf','img','doc')")
    op.create_index("idx_files_version_id", "files", ["version_id"], if_not_exists=True)

    op.create_table(
        "conversion_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("tool_version", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("width", sa.Numeric(), nullable=True),
        sa.Column("height", sa.Numeric(), nullable=True),
        sa.Column("layer_count", sa.Integer(), nullable=True),
        sa.Column("entity_count", sa.Integer(), nullable=True),
    )
    op.create_check_constraint("ck_conversion_logs_status", "conversion_logs", "status in ('pending','success','failed')")
    op.create_index("idx_conversion_logs_file_id", "conversion_logs", ["file_id"], if_not_exists=True)

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
        "type in ('LINE','POLYLINE','LWPOLYLINE','CIRCLE','ARC','TEXT','MTEXT','HATCH','BLOCK','INSERT')",
    )
    op.create_index("idx_dxf_entities_raw_file_id", "dxf_entities_raw", ["file_id"], if_not_exists=True)
    op.create_index("idx_dxf_entities_raw_geom", "dxf_entities_raw", ["geom"], postgresql_using="gist", if_not_exists=True)

    op.create_table(
        "semantic_objects",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(), nullable=True),
        sa.Column("source_rule", sa.Text(), nullable=True),
        sa.Column("geom", Geometry(geometry_type="GEOMETRY", srid=0), nullable=True),
        sa.Column("properties", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_check_constraint(
        "ck_semantic_objects_kind",
        "semantic_objects",
        "kind in ('space','wall','door','window','core','stairs','elevator')",
    )
    op.create_index("idx_semantic_objects_file_id", "semantic_objects", ["file_id"], if_not_exists=True)
    op.create_index("idx_semantic_objects_geom", "semantic_objects", ["geom"], postgresql_using="gist", if_not_exists=True)

    op.create_table(
        "project_stats",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("total_area", sa.Numeric(), nullable=True),
        sa.Column("room_count", sa.Integer(), nullable=True),
        sa.Column("floor_count", sa.Integer(), nullable=True),
        sa.Column("extraction_status", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "qa_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("sources", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_qa_history_project_id", "qa_history", ["project_id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("idx_qa_history_project_id", table_name="qa_history")
    op.drop_table("qa_history")
    op.drop_table("project_stats")
    op.drop_index("idx_semantic_objects_geom", table_name="semantic_objects")
    op.drop_index("idx_semantic_objects_file_id", table_name="semantic_objects")
    op.drop_table("semantic_objects")
    op.drop_index("idx_dxf_entities_raw_geom", table_name="dxf_entities_raw")
    op.drop_index("idx_dxf_entities_raw_file_id", table_name="dxf_entities_raw")
    op.drop_table("dxf_entities_raw")
    op.drop_index("idx_conversion_logs_file_id", table_name="conversion_logs")
    op.drop_table("conversion_logs")
    op.drop_index("idx_files_version_id", table_name="files")
    op.drop_check_constraint("files", "ck_files_type")
    op.drop_table("files")
    op.drop_index("idx_versions_project_id", table_name="versions")
    op.drop_table("versions")
    op.drop_table("projects")
    op.execute("DROP EXTENSION IF EXISTS postgis")
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
