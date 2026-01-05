#!/usr/bin/env python3
"""
Job de sincronização do MongoDB para o ClickHouse

Sincroniza dados operacionais do MongoDB para armazenamento histórico no ClickHouse.
Roda como CronJob diariamente às 2h UTC.
"""

import asyncio
import os
import sys
import structlog
from datetime import datetime, timedelta
from typing import List, Dict

# Adiciona o diretório raiz ao path para importações
sys.path.insert(0, '/app')

from src.clients.mongodb_client import MongoDBClient
from src.clients.clickhouse_client import ClickHouseClient
from src.config.settings import Settings


logger = structlog.get_logger(__name__)


class MongoToClickHouseSync:
    """Sincronizador MongoDB -> ClickHouse"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.mongodb_client = None
        self.clickhouse_client = None
        # Suporta ambos os nomes de variáveis para retrocompatibilidade
        self.batch_size = int(os.getenv('SYNC_BATCH_SIZE', os.getenv('BATCH_SIZE', '1000')))
        # SYNC_LOOKBACK_HOURS converte horas para dias (arredonda para cima)
        lookback_hours = int(os.getenv('SYNC_LOOKBACK_HOURS', '0'))
        if lookback_hours > 0:
            # Converte horas para dias (mínimo 1 dia)
            self.date_range_days = max(1, (lookback_hours + 23) // 24)
        else:
            self.date_range_days = int(os.getenv('DATE_RANGE_DAYS', '1'))

    async def initialize(self):
        """Inicializa os clientes de banco de dados"""
        logger.info("Inicializando clientes de banco de dados...")

        # MongoDB
        self.mongodb_client = MongoDBClient(
            uri=self.settings.mongodb_uri,
            database=self.settings.mongodb_database
        )
        await self.mongodb_client.initialize()

        # ClickHouse
        self.clickhouse_client = ClickHouseClient(self.settings)
        await self.clickhouse_client.initialize()

        logger.info("Clientes inicializados com sucesso")

    async def sync_collection(self, collection_name: str, table_name: str) -> int:
        """
        Sincroniza uma coleção do MongoDB para uma tabela do ClickHouse

        Args:
            collection_name: Nome da coleção no MongoDB
            table_name: Nome da tabela no ClickHouse

        Returns:
            Número de documentos sincronizados
        """
        logger.info(f"Sincronizando {collection_name} -> {table_name}...")

        # Calcula range de datas
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=self.date_range_days)

        # Query MongoDB
        filter_query = {
            'timestamp': {
                '$gte': start_date,
                '$lt': end_date
            }
        }

        documents = await self.mongodb_client.find(
            collection=collection_name,
            filter=filter_query,
            limit=self.batch_size * 10  # Limite total
        )

        if not documents:
            logger.info(f"Nenhum documento encontrado em {collection_name}")
            return 0

        # Processa em batches
        total_synced = 0
        for i in range(0, len(documents), self.batch_size):
            batch = documents[i:i + self.batch_size]

            # Insere no ClickHouse
            await self._insert_batch(table_name, batch)
            total_synced += len(batch)

            logger.info(
                f"Batch sincronizado",
                collection=collection_name,
                batch_size=len(batch),
                total=total_synced
            )

        logger.info(
            f"Sincronização completa",
            collection=collection_name,
            total_documents=total_synced
        )

        return total_synced

    async def _insert_batch(self, table_name: str, documents: List[Dict]):
        """
        Insere batch de documentos no ClickHouse

        Args:
            table_name: Nome da tabela
            documents: Lista de documentos
        """
        if not documents:
            return

        # Prepara dados para inserção
        rows = []
        for doc in documents:
            row = self._prepare_row(doc, table_name)
            if row:
                rows.append(row)

        if rows:
            column_names = self._get_column_names(table_name)
            await self.clickhouse_client.insert_batch(table_name, rows, column_names)

    def _get_column_names(self, table_name: str) -> List[str]:
        """
        Retorna nomes das colunas para a tabela.

        Args:
            table_name: Nome da tabela

        Returns:
            Lista de nomes de colunas
        """
        table_columns = {
            'operational_context_history': [
                'entity_id', 'data_type', 'created_at', 'data', 'metadata'
            ],
            'data_lineage_history': [
                'entity_id', 'operation', 'created_at', 'source', 'target', 'metadata'
            ],
            'quality_metrics_history': [
                'collection', 'created_at', 'completeness_score',
                'freshness_score', 'consistency_score', 'metadata'
            ]
        }
        return table_columns.get(table_name, ['entity_id', 'created_at', 'data', 'metadata'])

    def _prepare_row(self, document: Dict, table_name: str = None) -> List:
        """
        Prepara documento MongoDB para inserção no ClickHouse

        Args:
            document: Documento do MongoDB
            table_name: Nome da tabela de destino

        Returns:
            Lista de valores para inserção no ClickHouse
        """
        import json

        # Remove _id do MongoDB
        doc = document.copy()
        doc.pop('_id', None)

        # Extrai timestamp
        created_at = doc.get('created_at') or doc.get('timestamp') or datetime.utcnow()
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))

        # Formata baseado na tabela de destino
        if table_name == 'operational_context_history':
            return [
                doc.get('entity_id', ''),
                doc.get('data_type', 'context'),
                created_at,
                json.dumps(doc, default=str),
                json.dumps(doc.get('metadata', {}), default=str)
            ]
        elif table_name == 'data_lineage_history':
            return [
                doc.get('entity_id', ''),
                doc.get('operation', 'UNKNOWN'),
                created_at,
                doc.get('source', ''),
                doc.get('target', ''),
                json.dumps(doc.get('metadata', {}), default=str)
            ]
        elif table_name == 'quality_metrics_history':
            return [
                doc.get('collection', 'unknown'),
                created_at,
                float(doc.get('completeness_score', 0.0)),
                float(doc.get('freshness_score', 0.0)),
                float(doc.get('consistency_score', 0.0)),
                json.dumps(doc.get('metadata', {}), default=str)
            ]
        else:
            # Fallback genérico
            return [
                doc.get('entity_id', ''),
                created_at,
                json.dumps(doc, default=str),
                json.dumps(doc.get('metadata', {}), default=str)
            ]

    async def run(self):
        """Executa sincronização completa"""
        try:
            await self.initialize()

            # Sincroniza coleções principais
            collections_to_sync = [
                ('operational_context', 'operational_context_history'),
                ('data_lineage', 'data_lineage_history'),
                ('data_quality_metrics', 'quality_metrics_history')
            ]

            total_synced = 0
            for mongo_collection, clickhouse_table in collections_to_sync:
                synced = await self.sync_collection(mongo_collection, clickhouse_table)
                total_synced += synced

            logger.info(
                "Sincronização completa",
                total_documents=total_synced,
                collections=len(collections_to_sync)
            )

        except Exception as e:
            logger.error("Erro na sincronização", error=str(e))
            raise

        finally:
            # Cleanup
            if self.mongodb_client:
                await self.mongodb_client.close()
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

    logger.info("Iniciando job de sincronização MongoDB -> ClickHouse")

    # Carrega configurações
    settings = Settings()

    # Executa sincronização
    sync_job = MongoToClickHouseSync(settings)
    await sync_job.run()

    logger.info("Job de sincronização concluído com sucesso")


if __name__ == "__main__":
    asyncio.run(main())
