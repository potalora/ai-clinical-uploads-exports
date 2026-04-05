"""add smart extraction columns and cross references table

Revision ID: ca666e207db0
Revises: a1b2c3d4e5f6
Create Date: 2026-04-04 21:11:26.266505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ca666e207db0'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create cross-references table
    op.create_table('record_cross_references',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('document_record_id', sa.UUID(), nullable=False),
    sa.Column('referenced_record_id', sa.UUID(), nullable=False),
    sa.Column('reference_type', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['document_record_id'], ['health_records.id'], ),
    sa.ForeignKeyConstraint(['referenced_record_id'], ['health_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # Add new columns to health_records
    op.add_column('health_records', sa.Column('source_section', sa.Text(), nullable=True))
    op.add_column('health_records', sa.Column('linked_encounter_id', sa.UUID(), nullable=True))
    op.add_column('health_records', sa.Column('merge_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key('fk_health_records_linked_encounter', 'health_records', 'health_records', ['linked_encounter_id'], ['id'])

    # Add new columns to uploaded_files
    op.add_column('uploaded_files', sa.Column('extraction_sections', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('uploaded_files', sa.Column('document_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('uploaded_files', sa.Column('dedup_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # Manual indexes
    op.create_index(
        "ix_health_records_linked_encounter",
        "health_records",
        ["linked_encounter_id"],
        postgresql_where=text("linked_encounter_id IS NOT NULL"),
    )
    op.create_index(
        "ix_health_records_source_file_section",
        "health_records",
        ["source_file_id", "source_section"],
        postgresql_where=text("source_file_id IS NOT NULL"),
    )
    op.create_index(
        "ix_cross_ref_pair",
        "record_cross_references",
        ["document_record_id", "referenced_record_id"],
        unique=True,
    )
    op.create_index(
        "ix_cross_ref_referenced",
        "record_cross_references",
        ["referenced_record_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop manual indexes
    op.drop_index("ix_cross_ref_referenced", table_name="record_cross_references")
    op.drop_index("ix_cross_ref_pair", table_name="record_cross_references")
    op.drop_index("ix_health_records_source_file_section", table_name="health_records")
    op.drop_index("ix_health_records_linked_encounter", table_name="health_records")

    # Drop new columns from uploaded_files
    op.drop_column('uploaded_files', 'dedup_summary')
    op.drop_column('uploaded_files', 'document_metadata')
    op.drop_column('uploaded_files', 'extraction_sections')

    # Drop new columns from health_records
    op.drop_constraint('fk_health_records_linked_encounter', 'health_records', type_='foreignkey')
    op.drop_column('health_records', 'merge_metadata')
    op.drop_column('health_records', 'linked_encounter_id')
    op.drop_column('health_records', 'source_section')

    # Drop cross-references table
    op.drop_table('record_cross_references')
