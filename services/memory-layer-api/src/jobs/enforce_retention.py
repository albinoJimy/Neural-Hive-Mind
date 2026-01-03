#!/usr/bin/env python3
"""
Job de aplicação de políticas de retenção

Aplica políticas de retenção de dados em todas as camadas de memória.
Roda como CronJob diariamente às 3h UTC.

As políticas são carregadas do arquivo YAML montado em /etc/memory-layer/policies/retention-policy.yaml
"""

import asyncio
import os
import sys
import structlog
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Adiciona o diretório raiz ao path para importações
sys.path.insert(0, '/app')

from src.clients.mongodb_client import MongoDBClient
from src.clients.neo4j_client import Neo4jClient
from src.clients.clickhouse_client import ClickHouseClient
from src.config.settings import Settings


logger = structlog.get_logger(__name__)

# Caminho padrão do arquivo de política de retenção
DEFAULT_RETENTION_POLICY_PATH = '/etc/memory-layer/policies/retention-policy.yaml'


def load_retention_policy(policy_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Carrega políticas de retenção do arquivo YAML

    Args:
        policy_path: Caminho do arquivo de política (usa env var ou padrão se não fornecido)

    Returns:
        Dicionário com as políticas de retenção
    """
    if policy_path is None:
        policy_path = os.getenv('RETENTION_POLICY_FILE', DEFAULT_RETENTION_POLICY_PATH)

    policy_file = Path(policy_path)

    if not policy_file.exists():
        logger.warning(
            "Arquivo de política de retenção não encontrado, usando valores padrão",
            path=policy_path
        )
        return get_default_retention_policy()

    try:
        with open(policy_file, 'r') as f:
            policy = yaml.safe_load(f)
            logger.info("Política de retenção carregada do arquivo", path=policy_path)
            return policy
    except Exception as e:
        logger.error(
            "Erro ao carregar política de retenção, usando valores padrão",
            path=policy_path,
            error=str(e)
        )
        return get_default_retention_policy()


def get_default_retention_policy() -> Dict[str, Any]:
    """Retorna política de retenção padrão como fallback"""
    return {
        'version': '1.0',
        'tiers': {
            'hot': {'storage': 'redis', 'max_age_seconds': 300},
            'warm': {'storage': 'mongodb', 'max_age_days': 30},
            'cold': {'storage': 'clickhouse', 'max_age_months': 18}
        },
        'mongodb': {'retention_days': 30},
        'clickhouse': {'retention_months': 18}
    }


class RetentionEnforcer:
    """Aplicador de políticas de retenção"""

    def __init__(self, settings: Settings, policy: Optional[Dict[str, Any]] = None):
        self.settings = settings
        self.dry_run = os.getenv('RETENTION_DRY_RUN', 'false').lower() == 'true'
        self.mongodb_client = None
        self.neo4j_client = None
        self.clickhouse_client = None

        # Carrega política do arquivo YAML ou usa a fornecida
        self.policy = policy if policy is not None else load_retention_policy()

        # Extrai valores de retenção da política
        self.mongodb_retention_days = self.policy.get('mongodb', {}).get(
            'retention_days',
            self.settings.mongodb_retention_days
        )
        self.clickhouse_retention_months = self.policy.get('clickhouse', {}).get(
            'retention_months',
            self.settings.clickhouse_retention_months
        )

        logger.info(
            "RetentionEnforcer inicializado com política",
            mongodb_retention_days=self.mongodb_retention_days,
            clickhouse_retention_months=self.clickhouse_retention_months,
            policy_version=self.policy.get('version', 'unknown')
        )

    async def initialize(self):
        """Inicializa os clientes de banco de dados"""
        logger.info("Inicializando clientes de banco de dados...")

        # MongoDB
        self.mongodb_client = MongoDBClient(
            uri=self.settings.mongodb_uri,
            database=self.settings.mongodb_database
        )
        await self.mongodb_client.initialize()

        # Neo4j
        self.neo4j_client = Neo4jClient(
            uri=self.settings.neo4j_uri,
            user=self.settings.neo4j_user,
            password=self.settings.neo4j_password,
            database=self.settings.neo4j_database
        )
        await self.neo4j_client.initialize()

        # ClickHouse
        self.clickhouse_client = ClickHouseClient(self.settings)
        await self.clickhouse_client.initialize()

        logger.info("Clientes inicializados com sucesso")

    async def enforce_mongodb_retention(self) -> int:
        """
        Aplica política de retenção no MongoDB

        Returns:
            Número de documentos removidos
        """
        logger.info("Aplicando retenção no MongoDB...")

        cutoff_date = datetime.utcnow() - timedelta(days=self.mongodb_retention_days)

        collections = [
            'operational_context',
            'data_lineage',
            'data_quality_metrics'
        ]

        total_deleted = 0
        for collection in collections:
            filter_query = {
                'timestamp': {'$lt': cutoff_date}
            }

            if self.dry_run:
                # Apenas conta documentos que seriam removidos
                count = await self.mongodb_client.count_documents(collection, filter_query)
                logger.info(
                    f"[DRY-RUN] Documentos a remover",
                    collection=collection,
                    count=count
                )
                total_deleted += count
            else:
                # Remove documentos expirados
                deleted = await self.mongodb_client.delete_many(collection, filter_query)
                logger.info(
                    f"Documentos removidos",
                    collection=collection,
                    count=deleted
                )
                total_deleted += deleted

        logger.info(
            "Retenção MongoDB completa",
            total_deleted=total_deleted,
            dry_run=self.dry_run
        )

        return total_deleted

    async def enforce_neo4j_retention(self) -> int:
        """
        Aplica política de retenção no Neo4j

        Returns:
            Número de nós removidos
        """
        logger.info("Aplicando retenção no Neo4j...")

        # Neo4j mantém dados semânticos de longo prazo
        # Apenas remove nós marcados como temporários e expirados
        cutoff_timestamp = int((datetime.utcnow() - timedelta(days=90)).timestamp())

        query = """
        MATCH (n)
        WHERE n.temporary = true AND n.expires_at < $cutoff_timestamp
        RETURN count(n) as count
        """

        if self.dry_run:
            results = await self.neo4j_client.execute_query(
                query,
                {'cutoff_timestamp': cutoff_timestamp}
            )
            count = results[0]['count'] if results else 0
            logger.info(
                "[DRY-RUN] Nós temporários a remover",
                count=count
            )
            return count
        else:
            delete_query = """
            MATCH (n)
            WHERE n.temporary = true AND n.expires_at < $cutoff_timestamp
            DETACH DELETE n
            """
            result = await self.neo4j_client.execute_write(
                delete_query,
                {'cutoff_timestamp': cutoff_timestamp}
            )
            deleted = result.get('nodes_deleted', 0)
            logger.info(
                "Nós temporários removidos",
                count=deleted
            )
            return deleted

    async def enforce_clickhouse_retention(self) -> int:
        """
        Aplica política de retenção no ClickHouse

        Returns:
            Número de linhas removidas
        """
        logger.info("Aplicando retenção no ClickHouse...")

        cutoff_date = datetime.utcnow() - timedelta(days=self.clickhouse_retention_months * 30)

        tables = [
            'operational_context_history',
            'data_lineage_history',
            'quality_metrics_history'
        ]

        total_deleted = 0
        for table in tables:
            if self.dry_run:
                # Conta linhas que seriam removidas
                count_query = f"""
                SELECT count(*) as count
                FROM {table}
                WHERE timestamp < '{cutoff_date.isoformat()}'
                """
                result = await self.clickhouse_client.execute_query(count_query)
                count = result[0]['count'] if result else 0
                logger.info(
                    f"[DRY-RUN] Linhas a remover",
                    table=table,
                    count=count
                )
                total_deleted += count
            else:
                # Remove linhas expiradas
                delete_query = f"""
                ALTER TABLE {table}
                DELETE WHERE timestamp < '{cutoff_date.isoformat()}'
                """
                await self.clickhouse_client.execute_query(delete_query)
                logger.info(
                    f"Linhas removidas de {table}"
                )

        logger.info(
            "Retenção ClickHouse completa",
            total_deleted=total_deleted,
            dry_run=self.dry_run
        )

        return total_deleted

    async def run(self):
        """Executa aplicação de políticas de retenção"""
        try:
            await self.initialize()

            if self.dry_run:
                logger.info("Modo DRY-RUN ativado - nenhum dado será removido")

            # Aplica retenção em cada camada
            mongodb_deleted = await self.enforce_mongodb_retention()
            neo4j_deleted = await self.enforce_neo4j_retention()
            clickhouse_deleted = await self.enforce_clickhouse_retention()

            logger.info(
                "Políticas de retenção aplicadas com sucesso",
                mongodb_deleted=mongodb_deleted,
                neo4j_deleted=neo4j_deleted,
                clickhouse_deleted=clickhouse_deleted,
                total_deleted=mongodb_deleted + neo4j_deleted + clickhouse_deleted,
                dry_run=self.dry_run
            )

        except Exception as e:
            logger.error("Erro ao aplicar políticas de retenção", error=str(e))
            raise

        finally:
            # Cleanup
            if self.mongodb_client:
                await self.mongodb_client.close()
            if self.neo4j_client:
                await self.neo4j_client.close()
            if self.clickhouse_client:
                await self.clickhouse_client.close()


async def main():
    """Função principal"""
    # Configura logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()
        ]
    )

    logger.info("Iniciando job de aplicação de políticas de retenção")

    # Carrega configurações
    settings = Settings()

    # Executa aplicação de políticas
    enforcer = RetentionEnforcer(settings)
    await enforcer.run()

    logger.info("Job de retenção concluído com sucesso")


if __name__ == "__main__":
    asyncio.run(main())
