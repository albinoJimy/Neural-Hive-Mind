"""
Retention Policy Manager

Gerencia políticas de retenção e TTL nas camadas de memória.
"""
import structlog
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List

logger = structlog.get_logger(__name__)


class RetentionPolicyManager:
    """Gerencia TTL e políticas de retenção nas camadas de memória"""

    def __init__(self, settings, mongodb_client=None, clickhouse_client=None, neo4j_client=None):
        self.settings = settings
        self.mongodb = mongodb_client
        self.clickhouse = clickhouse_client
        self.neo4j = neo4j_client
        self.policies = self._load_policies()

    def _load_policies(self) -> Dict[str, Dict]:
        """
        Load retention policies from settings

        Structure:
        {
            'redis': {'ttl_seconds': 300, 'max_ttl_seconds': 900},
            'mongodb': {'retention_days': 30, 'cleanup_enabled': True},
            'clickhouse': {'retention_months': 18, 'partition_by': 'month'},
            'neo4j': {'versioning_enabled': True, 'max_versions': 10}
        }
        """
        return {
            'redis': {
                'default_ttl_seconds': self.settings.redis_default_ttl,
                'max_ttl_seconds': self.settings.redis_max_ttl,
                'data_types': {
                    'context': 300,
                    'query_cache': 600,
                    'session': 900
                }
            },
            'mongodb': {
                'default_retention_days': self.settings.mongodb_retention_days,
                'cleanup_enabled': True,
                'data_types': {
                    'operational_context': 30,
                    'cognitive_ledger': 365,  # 1 ano para auditoria
                    'specialist_opinions': 90,
                    'consensus_decisions': 365,
                    'data_quality_metrics': 90,
                    'data_lineage': 730  # 2 anos
                }
            },
            'clickhouse': {
                'default_retention_months': self.settings.clickhouse_retention_months,
                'partition_by': 'month',
                'data_types': {
                    'cognitive_plans_history': 18,
                    'consensus_decisions_history': 24,  # 2 anos
                    'telemetry_events': 12,
                    'audit_events': 60  # 5 anos
                }
            },
            'neo4j': {
                'versioning_enabled': True,
                'max_versions_per_ontology': 10,
                'archive_old_versions': True
            }
        }

    def get_ttl_for_data_type(
        self,
        data_type: str,
        layer: str
    ) -> int:
        """
        Get TTL for specific data type and layer

        Returns:
            TTL in appropriate units (seconds for Redis, days for MongoDB, months for ClickHouse)
        """
        if layer not in self.policies:
            logger.warning("Unknown layer", layer=layer)
            return 0

        layer_policy = self.policies[layer]
        data_types = layer_policy.get('data_types', {})

        # Check for specific data type override
        if data_type in data_types:
            return data_types[data_type]

        # Fallback to default
        if layer == 'redis':
            return layer_policy.get('default_ttl_seconds', 300)
        elif layer == 'mongodb':
            return layer_policy.get('default_retention_days', 30)
        elif layer == 'clickhouse':
            return layer_policy.get('default_retention_months', 18)

        return 0

    def should_cleanup(
        self,
        data_type: str,
        layer: str,
        timestamp: datetime
    ) -> bool:
        """
        Check if data should be removed based on retention policy
        """
        ttl = self.get_ttl_for_data_type(data_type, layer)
        if ttl == 0:
            return False

        age = datetime.utcnow() - timestamp

        if layer == 'redis':
            return age.total_seconds() > ttl
        elif layer == 'mongodb':
            return age.days > ttl
        elif layer == 'clickhouse':
            return age.days > (ttl * 30)  # Convert months to days

        return False

    async def enforce_retention(
        self,
        layer: str,
        dry_run: bool = False
    ) -> Dict[str, int]:
        """
        Enforce retention policies for a layer

        Args:
            layer: Layer name (mongodb, clickhouse, neo4j)
            dry_run: If True, only count records to delete

        Returns:
            Dict with deletion counts
        """
        results = {}

        try:
            if layer == 'mongodb':
                results['mongodb_deleted'] = await self._cleanup_mongodb(dry_run)
            elif layer == 'clickhouse':
                results['clickhouse_deleted'] = await self._cleanup_clickhouse(dry_run)
            elif layer == 'neo4j':
                results['neo4j_versions_pruned'] = await self._cleanup_neo4j(dry_run)
            else:
                logger.warning("Unknown layer for cleanup", layer=layer)

            logger.info("Retention enforcement completed", layer=layer, dry_run=dry_run, results=results)
            return results

        except Exception as e:
            logger.error("Retention enforcement failed", error=str(e), layer=layer)
            return results

    async def _cleanup_mongodb(self, dry_run: bool) -> int:
        """
        Remove documentos antigos do MongoDB baseado nas políticas de retenção.

        Args:
            dry_run: Se True, apenas conta registros sem deletar

        Returns:
            Número de documentos removidos (ou que seriam removidos em dry_run)
        """
        if not self.mongodb:
            logger.warning("MongoDB client não configurado para cleanup")
            return 0

        total_deleted = 0
        collections = [
            ('operational_context', 'operational_context'),
            ('data_lineage', 'data_lineage'),
            ('data_quality_metrics', 'data_quality_metrics')
        ]

        for collection_name, data_type in collections:
            try:
                retention_days = self.get_ttl_for_data_type(data_type, 'mongodb')
                cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

                filter_query = {'created_at': {'$lt': cutoff_date}}

                if dry_run:
                    count = await self.mongodb.count_documents(collection_name, filter_query)
                    logger.info(
                        "[DRY-RUN] Documentos a serem removidos",
                        collection=collection_name,
                        count=count,
                        cutoff_date=cutoff_date.isoformat()
                    )
                    total_deleted += count
                else:
                    deleted = await self.mongodb.delete_many(collection_name, filter_query)
                    logger.info(
                        "Documentos removidos",
                        collection=collection_name,
                        count=deleted,
                        cutoff_date=cutoff_date.isoformat()
                    )
                    total_deleted += deleted

            except Exception as e:
                logger.error(
                    "Erro no cleanup do MongoDB",
                    collection=collection_name,
                    error=str(e)
                )

        return total_deleted

    async def _cleanup_clickhouse(self, dry_run: bool) -> int:
        """
        Remove dados antigos do ClickHouse.

        Nota: ClickHouse tem TTL nativo, mas podemos forçar cleanup manual.

        Args:
            dry_run: Se True, apenas conta registros sem deletar

        Returns:
            Número de registros removidos (ou que seriam removidos em dry_run)
        """
        if not self.clickhouse:
            logger.warning("ClickHouse client não configurado para cleanup")
            return 0

        total_deleted = 0
        tables = [
            ('cognitive_plans_history', 'cognitive_plans_history'),
            ('consensus_decisions_history', 'consensus_decisions_history'),
            ('specialist_opinions_history', 'specialist_opinions_history'),
            ('telemetry_events', 'telemetry_events')
        ]

        for table_name, data_type in tables:
            try:
                retention_months = self.get_ttl_for_data_type(data_type, 'clickhouse')
                cutoff_date = datetime.utcnow() - timedelta(days=retention_months * 30)

                if dry_run:
                    count_query = f"""
                        SELECT count(*) as count
                        FROM {self.clickhouse.database}.{table_name}
                        WHERE created_at < %(cutoff_date)s
                    """
                    result = self.clickhouse.client.query(
                        count_query,
                        parameters={'cutoff_date': cutoff_date}
                    )
                    count = result.result_rows[0][0] if result.result_rows else 0
                    logger.info(
                        "[DRY-RUN] Registros a serem removidos",
                        table=table_name,
                        count=count,
                        cutoff_date=cutoff_date.isoformat()
                    )
                    total_deleted += count
                else:
                    # ClickHouse DELETE é assíncrono via ALTER TABLE
                    delete_query = f"""
                        ALTER TABLE {self.clickhouse.database}.{table_name}
                        DELETE WHERE created_at < %(cutoff_date)s
                    """
                    self.clickhouse.client.command(
                        delete_query,
                        parameters={'cutoff_date': cutoff_date}
                    )
                    logger.info(
                        "Cleanup iniciado para tabela",
                        table=table_name,
                        cutoff_date=cutoff_date.isoformat()
                    )
                    # ClickHouse não retorna contagem em DELETE

            except Exception as e:
                logger.error(
                    "Erro no cleanup do ClickHouse",
                    table=table_name,
                    error=str(e)
                )

        return total_deleted

    async def _cleanup_neo4j(self, dry_run: bool) -> int:
        """
        Remove versões antigas de ontologias no Neo4j.

        Mantém apenas max_versions_per_ontology versões de cada ontologia.

        Args:
            dry_run: Se True, apenas conta versões sem deletar

        Returns:
            Número de versões removidas (ou que seriam removidas em dry_run)
        """
        if not self.neo4j:
            logger.warning("Neo4j client não configurado para cleanup")
            return 0

        max_versions = self.policies['neo4j']['max_versions_per_ontology']
        total_pruned = 0

        try:
            # Encontra ontologias com mais versões que o limite
            query = """
                MATCH (o:Ontology)
                WITH o.name as ontology_name, collect(o) as versions
                WHERE size(versions) > $max_versions
                RETURN ontology_name, size(versions) as version_count
                ORDER BY ontology_name
            """
            results = await self.neo4j.run_query(query, {'max_versions': max_versions})

            for record in results:
                ontology_name = record['ontology_name']
                version_count = record['version_count']
                versions_to_delete = version_count - max_versions

                if dry_run:
                    logger.info(
                        "[DRY-RUN] Versões a serem removidas",
                        ontology=ontology_name,
                        count=versions_to_delete,
                        current=version_count,
                        max_allowed=max_versions
                    )
                    total_pruned += versions_to_delete
                else:
                    # Remove versões mais antigas, mantendo as mais recentes
                    delete_query = """
                        MATCH (o:Ontology {name: $ontology_name})
                        WITH o ORDER BY o.created_at DESC
                        SKIP $max_versions
                        DETACH DELETE o
                    """
                    await self.neo4j.run_query(delete_query, {
                        'ontology_name': ontology_name,
                        'max_versions': max_versions
                    })
                    logger.info(
                        "Versões removidas",
                        ontology=ontology_name,
                        count=versions_to_delete
                    )
                    total_pruned += versions_to_delete

        except Exception as e:
            logger.error("Erro no cleanup do Neo4j", error=str(e))

        return total_pruned
