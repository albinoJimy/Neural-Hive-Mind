#!/usr/bin/env python3
"""
Script para criação automática de partições futuras para tabela error_budgets.
Executar mensalmente via CronJob para garantir partições disponíveis.

Nota: Este script assume que a tabela error_budgets é particionada.
A migração 001_add_budget_history_partitioning.sql deve ser aplicada primeiro.
"""

import asyncio
import asyncpg
import os
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)

# Nome da tabela parent particionada (após swap da migração)
PARENT_TABLE = "error_budgets"


async def create_partitions_for_next_months(months: int = 3):
    """
    Cria partições para os próximos N meses.

    Args:
        months: Número de meses futuros para criar partições

    Raises:
        RuntimeError: Se a tabela error_budgets não for particionada
    """
    # Configuração do PostgreSQL via variáveis de ambiente
    pg_config = {
        'host': os.getenv('POSTGRESQL_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRESQL_PORT', '5432')),
        'database': os.getenv('POSTGRESQL_DATABASE', 'sla_management'),
        'user': os.getenv('POSTGRESQL_USER', 'postgres'),
        'password': os.getenv('POSTGRESQL_PASSWORD', '')
    }

    try:
        conn = await asyncpg.connect(**pg_config)
        logger.info("postgresql_connected", host=pg_config['host'])

        # Verificar se a tabela parent é particionada
        is_partitioned = await conn.fetchval('''
            SELECT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_partitioned_table pt ON c.oid = pt.partrelid
                WHERE c.relname = $1
            )
        ''', PARENT_TABLE)

        if not is_partitioned:
            logger.error(
                "table_not_partitioned",
                table=PARENT_TABLE,
                hint="Execute a migração 001_add_budget_history_partitioning.sql primeiro"
            )
            await conn.close()
            raise RuntimeError(
                f"Tabela {PARENT_TABLE} não é particionada. "
                "Execute a migração de particionamento primeiro."
            )

        logger.info("table_is_partitioned", table=PARENT_TABLE)

        # Calcular meses futuros a partir do próximo mês
        current_date = datetime.utcnow().replace(day=1)
        next_month = current_date + timedelta(days=32)
        next_month = next_month.replace(day=1)

        partitions_created = 0

        for i in range(months):
            target_month = next_month + timedelta(days=32 * i)
            target_month = target_month.replace(day=1)

            partition_name = f"error_budgets_y{target_month.year}m{target_month.month:02d}"
            start_date = target_month
            end_date = (target_month + timedelta(days=32)).replace(day=1)

            # Verificar se partição já existe
            exists = await conn.fetchval('''
                SELECT EXISTS (
                    SELECT 1 FROM pg_class
                    WHERE relname = $1 AND relkind = 'r'
                )
            ''', partition_name)

            if exists:
                logger.info("partition_already_exists", partition=partition_name)
                continue

            # Criar partição na tabela parent correta
            try:
                await conn.execute(f'''
                    CREATE TABLE IF NOT EXISTS {partition_name}
                    PARTITION OF {PARENT_TABLE}
                    FOR VALUES FROM ('{start_date.strftime("%Y-%m-%d")}')
                    TO ('{end_date.strftime("%Y-%m-%d")}')
                ''')

                # Criar índices na nova partição (mesmo padrão da migração)
                await conn.execute(f'''
                    CREATE INDEX IF NOT EXISTS idx_{partition_name}_slo_calc_status
                    ON {partition_name}(slo_id, calculated_at DESC, status)
                ''')

                await conn.execute(f'''
                    CREATE INDEX IF NOT EXISTS idx_{partition_name}_service_calc
                    ON {partition_name}(service_name, calculated_at DESC)
                ''')

                partitions_created += 1
                logger.info(
                    "partition_created",
                    partition=partition_name,
                    parent_table=PARENT_TABLE,
                    start=start_date.strftime("%Y-%m-%d"),
                    end=end_date.strftime("%Y-%m-%d")
                )
            except Exception as e:
                logger.error(
                    "partition_creation_failed",
                    partition=partition_name,
                    error=str(e)
                )

        await conn.close()
        logger.info(
            "partition_creation_completed",
            partitions_created=partitions_created,
            months_checked=months
        )
        return partitions_created

    except Exception as e:
        logger.error("partition_script_failed", error=str(e))
        raise


async def main():
    """Ponto de entrada principal."""
    months = int(os.getenv('PARTITION_MONTHS_AHEAD', '3'))
    await create_partitions_for_next_months(months)


if __name__ == "__main__":
    asyncio.run(main())
