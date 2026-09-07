"""add_knowledge_base_embeddings_table

Revision ID: 718625de2a8d
Revises: 42b9468b7eb5
Create Date: 2026-09-07 20:30:57.775169

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = '718625de2a8d'
down_revision: Union[str, None] = '42b9468b7eb5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('knowledge_base_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('source_type', sa.Enum('DELAY_REASON', 'PRODUCTIVITY_BENCHMARK', 'GLOSSARY_MAPPING', 'WBS_NODE', 'PROJECT_SUMMARY', 'CLOSED_PROJECT_SUMMARY', name='knowledgesourcetype'), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('content_text', sa.Text(), nullable=False),
        sa.Column('content_metadata', sa.Text(), nullable=True),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(dim=1536), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_base_embeddings_id'), 'knowledge_base_embeddings', ['id'], unique=False)
    op.create_index('ix_knowledge_base_embeddings_org_source', 'knowledge_base_embeddings', ['organization_id', 'source_type'], unique=False)
    op.create_index('ix_knowledge_base_embeddings_project_source', 'knowledge_base_embeddings', ['project_id', 'source_type'], unique=False)
    op.create_index('ix_knowledge_base_embeddings_source_lookup', 'knowledge_base_embeddings', ['source_type', 'source_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_knowledge_base_embeddings_source_lookup', table_name='knowledge_base_embeddings')
    op.drop_index('ix_knowledge_base_embeddings_project_source', table_name='knowledge_base_embeddings')
    op.drop_index('ix_knowledge_base_embeddings_org_source', table_name='knowledge_base_embeddings')
    op.drop_index(op.f('ix_knowledge_base_embeddings_id'), table_name='knowledge_base_embeddings')
    op.drop_table('knowledge_base_embeddings')
    op.execute('DROP TYPE IF EXISTS knowledgesourcetype')