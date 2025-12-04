"""Add organizational features: extended models, views, threads, decisions, FAQ, user profiles

Revision ID: 001_org_features
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_org_features'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new fields to agenda_items table
    op.add_column('agenda_items', sa.Column('raw_snippet', sa.Text(), nullable=True))
    op.add_column('agenda_items', sa.Column('workspace_id', sa.String(length=50), nullable=True))
    op.add_column('agenda_items', sa.Column('source_message_ts', sa.String(length=50), nullable=True))
    op.add_column('agenda_items', sa.Column('requestor_user_id', sa.String(length=50), nullable=True))
    op.add_column('agenda_items', sa.Column('requestor_user_name', sa.String(length=100), nullable=True))
    op.add_column('agenda_items', sa.Column('created_by_user_id', sa.String(length=50), nullable=True))
    op.add_column('agenda_items', sa.Column('project', sa.String(length=200), nullable=True))
    op.add_column('agenda_items', sa.Column('topic', sa.String(length=200), nullable=True))
    op.add_column('agenda_items', sa.Column('labels', sa.String(length=500), nullable=True))
    op.add_column('agenda_items', sa.Column('due_at', sa.DateTime(), nullable=True))
    
    # Update enum types to include new values
    # Note: PostgreSQL enum alterations require special handling
    op.execute("ALTER TYPE itemtype ADD VALUE IF NOT EXISTS 'note'")
    op.execute("ALTER TYPE itemtype ADD VALUE IF NOT EXISTS 'announcement'")
    op.execute("ALTER TYPE itemstatus ADD VALUE IF NOT EXISTS 'stale'")
    op.execute("ALTER TYPE itemstatus ADD VALUE IF NOT EXISTS 'done'")

    # Create user_profiles table
    op.create_table(
        'user_profiles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('workspace_id', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=False),
        sa.Column('user_name', sa.String(length=100), nullable=True),
        sa.Column('user_email', sa.String(length=200), nullable=True),
        sa.Column('notification_preferences', sa.Text(), nullable=True),
        sa.Column('focus_mode_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('focus_mode_settings', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )

    # Create workspace_configs table
    op.create_table(
        'workspace_configs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('workspace_id', sa.String(length=50), nullable=False),
        sa.Column('workspace_name', sa.String(length=200), nullable=True),
        sa.Column('watched_channels', sa.Text(), nullable=True),
        sa.Column('important_channels', sa.Text(), nullable=True),
        sa.Column('ignored_channels', sa.Text(), nullable=True),
        sa.Column('config', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id')
    )

    # Create views table
    op.create_table(
        'views',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('workspace_id', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_predefined', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('filters', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create thread_titles table
    op.create_table(
        'thread_titles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('workspace_id', sa.String(length=50), nullable=False),
        sa.Column('channel_id', sa.String(length=50), nullable=False),
        sa.Column('thread_ts', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('inferred_by', sa.String(length=50), nullable=True),
        sa.Column('last_activity_at', sa.DateTime(), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('thread_ts')
    )

    # Create decisions table
    op.create_table(
        'decisions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('workspace_id', sa.String(length=50), nullable=False),
        sa.Column('agenda_item_id', sa.String(length=36), nullable=True),
        sa.Column('thread_ts', sa.String(length=50), nullable=True),
        sa.Column('channel_id', sa.String(length=50), nullable=True),
        sa.Column('decision_message_ts', sa.String(length=50), nullable=True),
        sa.Column('decision_text', sa.Text(), nullable=False),
        sa.Column('project', sa.String(length=200), nullable=True),
        sa.Column('involved_user_ids', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agenda_item_id'], ['agenda_items.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create faq_answers table
    op.create_table(
        'faq_answers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('workspace_id', sa.String(length=50), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('source_thread_ts', sa.String(length=50), nullable=True),
        sa.Column('source_channel_id', sa.String(length=50), nullable=True),
        sa.Column('source_message_ts', sa.String(length=50), nullable=True),
        sa.Column('tags', sa.String(length=500), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_canonical', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for better query performance
    op.create_index('ix_agenda_items_workspace_id', 'agenda_items', ['workspace_id'])
    op.create_index('ix_agenda_items_assigned_to', 'agenda_items', ['assigned_to_user_id'])
    op.create_index('ix_agenda_items_requestor', 'agenda_items', ['requestor_user_id'])
    op.create_index('ix_agenda_items_project', 'agenda_items', ['project'])
    op.create_index('ix_agenda_items_thread_ts', 'agenda_items', ['source_thread_ts'])
    op.create_index('ix_views_workspace_user', 'views', ['workspace_id', 'user_id'])
    op.create_index('ix_thread_titles_thread_ts', 'thread_titles', ['thread_ts'])
    op.create_index('ix_decisions_thread_ts', 'decisions', ['thread_ts'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_decisions_thread_ts', table_name='decisions')
    op.drop_index('ix_thread_titles_thread_ts', table_name='thread_titles')
    op.drop_index('ix_views_workspace_user', table_name='views')
    op.drop_index('ix_agenda_items_thread_ts', table_name='agenda_items')
    op.drop_index('ix_agenda_items_project', table_name='agenda_items')
    op.drop_index('ix_agenda_items_requestor', table_name='agenda_items')
    op.drop_index('ix_agenda_items_assigned_to', table_name='agenda_items')
    op.drop_index('ix_agenda_items_workspace_id', table_name='agenda_items')

    # Drop tables
    op.drop_table('faq_answers')
    op.drop_table('decisions')
    op.drop_table('thread_titles')
    op.drop_table('views')
    op.drop_table('workspace_configs')
    op.drop_table('user_profiles')

    # Remove columns from agenda_items
    op.drop_column('agenda_items', 'due_at')
    op.drop_column('agenda_items', 'labels')
    op.drop_column('agenda_items', 'topic')
    op.drop_column('agenda_items', 'project')
    op.drop_column('agenda_items', 'created_by_user_id')
    op.drop_column('agenda_items', 'requestor_user_name')
    op.drop_column('agenda_items', 'requestor_user_id')
    op.drop_column('agenda_items', 'source_message_ts')
    op.drop_column('agenda_items', 'workspace_id')
    op.drop_column('agenda_items', 'raw_snippet')

    # Note: Enum value removal is complex in PostgreSQL and may require manual intervention

