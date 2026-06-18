"""Add unique constraint (plan_id, task_id) to execution_tickets

Idempotência de geração de tickets: um plano só pode ter UM ticket por task_id.
Impede a duplicação observada em E2E (16=2x8) quando o workflow Temporal e o
fallback do orchestrator (_extract_tickets_from_plan) geram ambos o conjunto de
tickets para o mesmo plano.

A migração limpa PRIMEIRO os duplicados existentes (mantém o ticket mais antigo
por (plan_id, task_id)) antes de criar a constraint — senão a criação falharia
numa tabela com duplicados (como aconteceu com o índice único do consensus).

Revision ID: 002
Revises: 001
Create Date: 2026-06-18

"""

from collections.abc import Sequence
from typing import Union

from alembic import op

# revision identifiers
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "uq_execution_tickets_plan_task"


def upgrade() -> None:
    """Limpa duplicados e cria a constraint única (plan_id, task_id)."""
    # 1. Apagar duplicados, mantendo a linha de menor id (mais antiga) por par.
    op.execute(
        """
        DELETE FROM public.execution_tickets t
        USING public.execution_tickets d
        WHERE t.plan_id = d.plan_id
          AND t.task_id = d.task_id
          AND t.id > d.id;
        """
    )
    # 2. Criar a constraint única.
    op.create_unique_constraint(
        CONSTRAINT_NAME,
        "execution_tickets",
        ["plan_id", "task_id"],
        schema="public",
    )


def downgrade() -> None:
    """Remove a constraint única (plan_id, task_id)."""
    op.drop_constraint(
        CONSTRAINT_NAME,
        "execution_tickets",
        schema="public",
        type_="unique",
    )
