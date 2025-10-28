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
        self.batch_size = int(os.getenv('BATCH_SIZE', '1000'))
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
            row = self._prepare_row(doc)
            if row:
                rows.append(row)

        if rows:
            await self.clickhouse_client.insert_batch(table_name, rows)

    def _prepare_row(self, document: Dict) -> Dict:
        """
        Prepara documento MongoDB para inserção no ClickHouse

        Args:
            document: Documento do MongoDB

        Returns:
            Linha formatada para ClickHouse
        """
        # Remove _id do MongoDB
        doc = document.copy()
        doc.pop('_id', None)

        # Converte datetime para string ISO
        for key, value in doc.items():
            if isinstance(value, datetime):
                doc[key] = value.isoformat()

        return doc

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
