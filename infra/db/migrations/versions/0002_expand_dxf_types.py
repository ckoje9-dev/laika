"""expand allowed dxf entity types to include dimension and ellipse."""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_expand_dxf_types"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 기존 제약 삭제 후 확장된 타입으로 재생성
    op.drop_constraint("ck_dxf_entities_raw_type", "dxf_entities_raw", type_="check")
    op.create_check_constraint(
        "ck_dxf_entities_raw_type",
        "dxf_entities_raw",
        "type in ('LINE','POLYLINE','LWPOLYLINE','CIRCLE','ARC','ELLIPSE','TEXT','MTEXT','HATCH','DIMENSION','BLOCK','INSERT')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_dxf_entities_raw_type", "dxf_entities_raw", type_="check")
    op.create_check_constraint(
        "ck_dxf_entities_raw_type",
        "dxf_entities_raw",
        "type in ('LINE','POLYLINE','LWPOLYLINE','CIRCLE','ARC','TEXT','MTEXT','HATCH','BLOCK','INSERT')",
    )
