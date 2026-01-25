"""Add pgvector extension and vector columns

Revision ID: 0006_add_pgvector
Revises: 0005_update_semantic_objects_kind
Create Date: 2026-01-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006_add_pgvector"
down_revision = "0005_semantic_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Install pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Add embedding column to semantic_objects table
    op.execute("""
        ALTER TABLE semantic_objects
        ADD COLUMN IF NOT EXISTS embedding vector(384)
    """)

    # Create index for vector similarity search using ivfflat
    # ivfflat is faster for approximate nearest neighbor search
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_semantic_objects_embedding
        ON semantic_objects
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)


def downgrade() -> None:
    # Drop index first
    op.execute("DROP INDEX IF EXISTS idx_semantic_objects_embedding")

    # Drop vector column
    op.execute("ALTER TABLE semantic_objects DROP COLUMN IF EXISTS embedding")

    # Drop pgvector extension
    op.execute("DROP EXTENSION IF EXISTS vector")
