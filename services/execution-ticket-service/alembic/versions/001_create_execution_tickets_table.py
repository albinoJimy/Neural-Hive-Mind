"""Create execution_tickets table

Revision ID: 001
Revises:
Create Date: 2025-10-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create execution_tickets table with all fields and indexes."""

    # Criar tabela execution_tickets
    op.create_table(
        'execution_tickets',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('ticket_id', sa.String(length=36), nullable=False),
        sa.Column('plan_id', sa.String(length=36), nullable=False),
        sa.Column('intent_id', sa.String(length=36), nullable=False),
        sa.Column('decision_id', sa.String(length=36), nullable=False),
        sa.Column('correlation_id', sa.String(length=36), nullable=True),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.Column('span_id', sa.String(length=32), nullable=True),
        sa.Column('task_id', sa.String(length=255), nullable=False),
        sa.Column('task_type', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('dependencies', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('risk_band', sa.String(length=20), nullable=False),
        sa.Column('sla', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('qos', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('required_capabilities', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('security_level', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('started_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('completed_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('estimated_duration_ms', sa.BigInteger(), nullable=True),
        sa.Column('actual_duration_ms', sa.BigInteger(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('compensation_ticket_id', sa.String(length=36), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('hash', sa.String(length=64), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticket_id', name='uq_ticket_id'),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'COMPENSATING', 'COMPENSATED')",
            name='chk_status'
        ),
        sa.CheckConstraint('retry_count >= 0', name='chk_retry_count'),
        sa.CheckConstraint('completed_at IS NULL OR completed_at >= started_at', name='chk_completed_after_started'),
        schema='public'
    )

    # Criar índices
    op.create_index('idx_ticket_id', 'execution_tickets', ['ticket_id'], unique=True, schema='public')
    op.create_index('idx_plan_id', 'execution_tickets', ['plan_id'], unique=False, schema='public')
    op.create_index('idx_intent_id', 'execution_tickets', ['intent_id'], unique=False, schema='public')
    op.create_index('idx_status', 'execution_tickets', ['status'], unique=False, schema='public')
    op.create_index('idx_created_at', 'execution_tickets', ['created_at'], unique=False, schema='public')
    op.create_index('idx_status_priority', 'execution_tickets', ['status', 'priority'], unique=False, schema='public')

    # Criar trigger para atualizar updated_at automaticamente
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    op.execute("""
        CREATE TRIGGER update_execution_tickets_updated_at
        BEFORE UPDATE ON execution_tickets
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    """Drop execution_tickets table and related objects."""

    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS update_execution_tickets_updated_at ON execution_tickets")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # Drop índices
    op.drop_index('idx_status_priority', table_name='execution_tickets', schema='public')
    op.drop_index('idx_created_at', table_name='execution_tickets', schema='public')
    op.drop_index('idx_status', table_name='execution_tickets', schema='public')
    op.drop_index('idx_intent_id', table_name='execution_tickets', schema='public')
    op.drop_index('idx_plan_id', table_name='execution_tickets', schema='public')
    op.drop_index('idx_ticket_id', table_name='execution_tickets', schema='public')

    # Drop tabela
    op.drop_table('execution_tickets', schema='public')
