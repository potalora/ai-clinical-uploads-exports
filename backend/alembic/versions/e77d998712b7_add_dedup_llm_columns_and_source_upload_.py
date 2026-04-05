"""add dedup LLM columns and source upload tracking

Revision ID: e77d998712b7
Revises: ca666e207db0
Create Date: 2026-04-05 02:10:03.332772

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e77d998712b7'
down_revision: Union[str, Sequence[str], None] = 'ca666e207db0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('dedup_candidates', sa.Column('llm_classification', sa.Text(), nullable=True))
    op.add_column('dedup_candidates', sa.Column('llm_confidence', sa.Float(), nullable=True))
    op.add_column('dedup_candidates', sa.Column('llm_explanation', sa.Text(), nullable=True))
    op.add_column('dedup_candidates', sa.Column('field_diff', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('dedup_candidates', sa.Column('auto_resolved', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('dedup_candidates', sa.Column('source_upload_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        None, 'dedup_candidates', 'uploaded_files', ['source_upload_id'], ['id']
    )
    op.create_index(
        "ix_dedup_source_upload",
        "dedup_candidates",
        ["source_upload_id"],
        postgresql_where=sa.text("source_upload_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_dedup_source_upload", table_name="dedup_candidates")
    op.drop_constraint(None, 'dedup_candidates', type_='foreignkey')
    op.drop_column('dedup_candidates', 'source_upload_id')
    op.drop_column('dedup_candidates', 'auto_resolved')
    op.drop_column('dedup_candidates', 'field_diff')
    op.drop_column('dedup_candidates', 'llm_explanation')
    op.drop_column('dedup_candidates', 'llm_confidence')
    op.drop_column('dedup_candidates', 'llm_classification')
