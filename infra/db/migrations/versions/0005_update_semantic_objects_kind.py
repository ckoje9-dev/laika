"""expand semantic_objects.kind check constraint"""
from __future__ import annotations

from alembic import op

revision = "0005_semantic_kind"
down_revision = "0004_drop_dxf_entities_raw"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_semantic_objects_kind", "semantic_objects", type_="check")
    op.create_check_constraint(
        "ck_semantic_objects_kind",
        "semantic_objects",
        "kind in ("
        "'space','wall','door','window','core','stairs','elevator',"
        "'border','dimension','symbol','text','axis','axis_summary',"
        "'column','steel_column','concrete','furniture','finish','block',"
        "'concrete_column'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint("ck_semantic_objects_kind", "semantic_objects", type_="check")
    op.create_check_constraint(
        "ck_semantic_objects_kind",
        "semantic_objects",
        "kind in ('space','wall','door','window','core','stairs','elevator')",
    )
