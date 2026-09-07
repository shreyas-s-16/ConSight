"""fix_embedding_dimension_to_384

Revision ID: 0485e099ea4f
Revises: 718625de2a8d
Create Date: 2026-09-07 22:29:40.589485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy
from alembic.runtime.environment import EnvironmentContext


# revision identifiers, used by Alembic.
revision: str = '0485e099ea4f'
down_revision: Union[str, None] = '718625de2a8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get the database dialect
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == 'postgresql':
        # PostgreSQL: change vector dimension
        op.execute('ALTER TABLE knowledge_base_embeddings ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384)')
    elif dialect_name == 'sqlite':
        # SQLite: recreate table with new dimension
        # First, create new table
        op.create_table('knowledge_base_embeddings_new',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('organization_id', sa.Integer(), nullable=False),
            sa.Column('project_id', sa.Integer(), nullable=True),
            sa.Column('source_type', sa.Enum('DELAY_REASON', 'PRODUCTIVITY_BENCHMARK', 'GLOSSARY_MAPPING', 'WBS_NODE', 'PROJECT_SUMMARY', 'CLOSED_PROJECT_SUMMARY', name='knowledgesourcetype'), nullable=False),
            sa.Column('source_id', sa.Integer(), nullable=False),
            sa.Column('content_text', sa.Text(), nullable=False),
            sa.Column('content_metadata', sa.Text(), nullable=True),
            sa.Column('embedding', pgvector.sqlalchemy.Vector(dim=384), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_knowledge_base_embeddings_new_id'), 'knowledge_base_embeddings_new', ['id'], unique=False)
        op.create_index('ix_knowledge_base_embeddings_new_org_source', 'knowledge_base_embeddings_new', ['organization_id', 'source_type'], unique=False)
        op.create_index('ix_knowledge_base_embeddings_new_project_source', 'knowledge_base_embeddings_new', ['project_id', 'source_type'], unique=False)
        op.create_index('ix_knowledge_base_embeddings_new_source_lookup', 'knowledge_base_embeddings_new', ['source_type', 'source_id'], unique=True)

        # Copy data (embeddings will be None since we can't convert dimensions in SQLite)
        op.execute('''
            INSERT INTO knowledge_base_embeddings_new (id, organization_id, project_id, source_type, source_id, content_text, content_metadata, embedding, created_at, updated_at)
            SELECT id, organization_id, project_id, source_type, source_id, content_text, content_metadata, NULL, created_at, updated_at
            FROM knowledge_base_embeddings
        ''')

        # Drop old table and rename new
        op.drop_index('ix_knowledge_base_embeddings_source_lookup', table_name='knowledge_base_embeddings')
        op.drop_index('ix_knowledge_base_embeddings_project_source', table_name='knowledge_base_embeddings')
        op.drop_index('ix_knowledge_base_embeddings_org_source', table_name='knowledge_base_embeddings')
        op.drop_index(op.f('ix_knowledge_base_embeddings_id'), table_name='knowledge_base_embeddings')
        op.drop_table('knowledge_base_embeddings')
        op.rename_table('knowledge_base_embeddings_new', 'knowledge_base_embeddings')


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == 'postgresql':
        op.execute('ALTER TABLE knowledge_base_embeddings ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536)')
    elif dialect_name == 'sqlite':
        # SQLite: recreate table with original dimension
        op.create_table('knowledge_base_embeddings_old',
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
        op.create_index(op.f('ix_knowledge_base_embeddings_old_id'), 'knowledge_base_embeddings_old', ['id'], unique=False)
        op.create_index('ix_knowledge_base_embeddings_old_org_source', 'knowledge_base_embeddings_old', ['organization_id', 'source_type'], unique=False)
        op.create_index('ix_knowledge_base_embeddings_old_project_source', 'knowledge_base_embeddings_old', ['project_id', 'source_type'], unique=False)
        op.create_index('ix_knowledge_base_embeddings_old_source_lookup', 'knowledge_base_embeddings_old', ['source_type', 'source_id'], unique=True)

        op.execute('''
            INSERT INTO knowledge_base_embeddings_old (id, organization_id, project_id, source_type, source_id, content_text, content_metadata, embedding, created_at, updated_at)
            SELECT id, organization_id, project_id, source_type, source_id, content_text, content_metadata, NULL, created_at, updated_at
            FROM knowledge_base_embeddings
        ''')

        op.drop_index('ix_knowledge_base_embeddings_source_lookup', table_name='knowledge_base_embeddings')
        op.drop_index('ix_knowledge_base_embeddings_project_source', table_name='knowledge_base_embeddings')
        op.drop_index('ix_knowledge_base_embeddings_org_source', table_name='knowledge_base_embeddings')
        op.drop_index(op.f('ix_knowledge_base_embeddings_id'), table_name='knowledge_base_embeddings')
        op.drop_table('knowledge_base_embeddings')
        op.rename_table('knowledge_base_embeddings_old', 'knowledge_base_embeddings')