"""
Lineage Tracker
"""
import structlog
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import uuid

from prometheus_client import Counter, Histogram

logger = structlog.get_logger(__name__)

# Métricas Prometheus
LINEAGE_INTEGRITY_CHECKS = Counter(
    'memory_lineage_integrity_checks_total',
    'Total de verificações de integridade de lineage',
    ['result']
)

LINEAGE_VALIDATION_DURATION = Histogram(
    'memory_lineage_validation_duration_seconds',
    'Duração da validação de integridade de lineage',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)


class LineageTracker:
    """Track data provenance and transformations"""

    def __init__(self, mongodb_client, neo4j_client, settings):
        self.mongodb = mongodb_client
        self.neo4j = neo4j_client
        self.settings = settings

    async def track_lineage(
        self,
        entity_id: str,
        entity_type: str,
        source_ids: List[str],
        transformation_type: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Register data lineage

        Args:
            entity_id: ID of entity
            entity_type: Type (intent, plan, decision, execution)
            source_ids: List of source IDs
            transformation_type: Type (derived, aggregated, filtered, enriched)
            metadata: Transformation metadata

        Returns:
            lineage_id
        """
        lineage_id = str(uuid.uuid4())

        try:
            # Persist in MongoDB
            lineage_doc = {
                'lineage_id': lineage_id,
                'entity_id': entity_id,
                'entity_type': entity_type,
                'source_ids': source_ids,
                'transformation_type': transformation_type,
                'timestamp': datetime.utcnow(),
                'metadata': metadata
            }

            await self.mongodb.insert_one(
                collection=self.settings.mongodb_lineage_collection,
                document=lineage_doc
            )

            # Create relationships in Neo4j
            for source_id in source_ids:
                query = """
                    MERGE (source {id: $source_id})
                    MERGE (entity {id: $entity_id, type: $entity_type})
                    MERGE (source)-[r:DERIVED_FROM]->(entity)
                    SET r.transformation_type = $transformation_type,
                        r.lineage_id = $lineage_id,
                        r.timestamp = datetime($timestamp)
                """
                await self.neo4j.run_query(query, {
                    'source_id': source_id,
                    'entity_id': entity_id,
                    'entity_type': entity_type,
                    'transformation_type': transformation_type,
                    'lineage_id': lineage_id,
                    'timestamp': datetime.utcnow().isoformat()
                })

            logger.info("Lineage tracked", lineage_id=lineage_id, entity_id=entity_id)
            return lineage_id

        except Exception as e:
            logger.error("Failed to track lineage", error=str(e), entity_id=entity_id)
            raise

    async def get_lineage_tree(
        self,
        entity_id: str,
        direction: str = 'upstream',
        depth: int = 3
    ) -> Dict[str, Any]:
        """
        Get lineage tree

        Args:
            entity_id: Entity ID
            direction: 'upstream', 'downstream', 'both'
            depth: Maximum depth

        Returns:
            Lineage tree structure
        """
        try:
            # Get metadata from MongoDB
            lineage_meta = await self.mongodb.find_one(
                collection=self.settings.mongodb_lineage_collection,
                filter={'entity_id': entity_id}
            )

            # Get graph from Neo4j
            if direction == 'upstream':
                query = """
                    MATCH path = (source)-[:DERIVED_FROM*1..{depth}]->(entity {{id: $entity_id}})
                    RETURN source, path
                    LIMIT 100
                """.format(depth=depth)
            elif direction == 'downstream':
                query = """
                    MATCH path = (entity {{id: $entity_id}})-[:DERIVED_FROM*1..{depth}]->(derived)
                    RETURN derived, path
                    LIMIT 100
                """.format(depth=depth)
            else:  # both
                query = """
                    MATCH path = (entity {{id: $entity_id}})-[:DERIVED_FROM*1..{depth}]-(related)
                    RETURN related, path
                    LIMIT 100
                """.format(depth=depth)

            graph_result = await self.neo4j.run_query(query, {'entity_id': entity_id})

            return {
                'entity_id': entity_id,
                'direction': direction,
                'depth': depth,
                'metadata': lineage_meta or {},
                'graph': graph_result,
                'source_count': len(lineage_meta.get('source_ids', [])) if lineage_meta else 0
            }

        except Exception as e:
            logger.error("Failed to get lineage tree", error=str(e), entity_id=entity_id)
            return {'entity_id': entity_id, 'metadata': {}, 'graph': []}

    async def get_lineage_path(
        self,
        source_id: str,
        target_id: str
    ) -> List[Dict]:
        """
        Find shortest path between source and target

        Returns:
            List of transformations in path
        """
        try:
            query = """
                MATCH path = shortestPath((source {{id: $source_id}})-[:DERIVED_FROM*]->(target {{id: $target_id}}))
                RETURN [rel in relationships(path) | {{
                    type: type(rel),
                    transformation_type: rel.transformation_type,
                    lineage_id: rel.lineage_id
                }}] as transformations
            """

            result = await self.neo4j.run_query(query, {
                'source_id': source_id,
                'target_id': target_id
            })

            return result[0]['transformations'] if result else []

        except Exception as e:
            logger.error("Failed to get lineage path", error=str(e),
                        source_id=source_id, target_id=target_id)
            return []

    async def validate_lineage_integrity(self, entity_id: str) -> bool:
        """
        Valida integridade do lineage

        Verificações:
        - Todos os source_ids existem
        - Sem ciclos no grafo
        - Timestamps são consistentes (sources criados antes da entidade)
        - Metadados estão completos
        """
        import time
        start_time = time.time()

        try:
            # Get lineage metadata
            lineage = await self.mongodb.find_one(
                collection=self.settings.mongodb_lineage_collection,
                filter={'entity_id': entity_id}
            )

            if not lineage:
                logger.warning("No lineage found", entity_id=entity_id)
                LINEAGE_INTEGRITY_CHECKS.labels(result='failed_missing').inc()
                return False

            # Check source_ids exist
            source_ids = lineage.get('source_ids', [])
            for source_id in source_ids:
                source_exists = await self.mongodb.find_one(
                    collection=self.settings.mongodb_lineage_collection,
                    filter={'entity_id': source_id}
                )
                if not source_exists:
                    logger.warning("Source ID not found", source_id=source_id)
                    LINEAGE_INTEGRITY_CHECKS.labels(result='failed_missing').inc()
                    return False

            # Check for cycles in Neo4j
            query = """
                MATCH (entity {{id: $entity_id}})
                MATCH path = (entity)-[:DERIVED_FROM*]->(entity)
                RETURN count(path) as cycle_count
            """
            result = await self.neo4j.run_query(query, {'entity_id': entity_id})
            if result and result[0]['cycle_count'] > 0:
                logger.error("Cycle detected in lineage", entity_id=entity_id)
                LINEAGE_INTEGRITY_CHECKS.labels(result='failed_cycle').inc()
                return False

            # Verificação de consistência de timestamps
            entity_timestamp = lineage.get('timestamp')
            if not entity_timestamp:
                logger.warning(
                    "Entidade sem timestamp",
                    entity_id=entity_id
                )
                LINEAGE_INTEGRITY_CHECKS.labels(result='failed_timestamp').inc()
                return False

            # Normaliza timestamp para datetime se for string
            if isinstance(entity_timestamp, str):
                try:
                    entity_timestamp = datetime.fromisoformat(entity_timestamp.replace('Z', '+00:00'))
                except ValueError:
                    logger.warning(
                        "Formato de timestamp inválido na entidade",
                        entity_id=entity_id,
                        timestamp=entity_timestamp
                    )
                    LINEAGE_INTEGRITY_CHECKS.labels(result='failed_timestamp').inc()
                    return False

            # Tolerância de 1 segundo para clock skew
            tolerance = timedelta(seconds=1)

            for source_id in source_ids:
                source_lineage = await self.mongodb.find_one(
                    collection=self.settings.mongodb_lineage_collection,
                    filter={'entity_id': source_id}
                )

                if not source_lineage:
                    continue

                source_timestamp = source_lineage.get('timestamp')
                if not source_timestamp:
                    logger.warning(
                        "Source sem timestamp",
                        source_id=source_id,
                        entity_id=entity_id
                    )
                    LINEAGE_INTEGRITY_CHECKS.labels(result='failed_timestamp').inc()
                    return False

                # Normaliza timestamp da source
                if isinstance(source_timestamp, str):
                    try:
                        source_timestamp = datetime.fromisoformat(source_timestamp.replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(
                            "Formato de timestamp inválido na source",
                            source_id=source_id,
                            timestamp=source_timestamp
                        )
                        LINEAGE_INTEGRITY_CHECKS.labels(result='failed_timestamp').inc()
                        return False

                # Valida: source deve ter sido criada antes da entidade (com tolerância)
                if source_timestamp > (entity_timestamp + tolerance):
                    logger.warning(
                        "Violação de consistência temporal: source criada após entidade",
                        entity_id=entity_id,
                        entity_timestamp=entity_timestamp.isoformat() if hasattr(entity_timestamp, 'isoformat') else str(entity_timestamp),
                        source_id=source_id,
                        source_timestamp=source_timestamp.isoformat() if hasattr(source_timestamp, 'isoformat') else str(source_timestamp)
                    )
                    LINEAGE_INTEGRITY_CHECKS.labels(result='failed_timestamp').inc()
                    return False

            # Todas as validações passaram
            LINEAGE_INTEGRITY_CHECKS.labels(result='passed').inc()
            logger.info("Lineage integrity validated", entity_id=entity_id)
            return True

        except Exception as e:
            logger.error("Lineage integrity validation failed", error=str(e), entity_id=entity_id)
            LINEAGE_INTEGRITY_CHECKS.labels(result='failed_error').inc()
            return False

        finally:
            duration = time.time() - start_time
            LINEAGE_VALIDATION_DURATION.observe(duration)

    async def get_impact_analysis(self, entity_id: str) -> Dict[str, Any]:
        """
        Analyze downstream impact

        Returns:
            Impact analysis (total impacted, critical impacted, etc.)
        """
        try:
            query = """
                MATCH (entity {{id: $entity_id}})-[:DERIVED_FROM*1..5]->(derived)
                RETURN count(DISTINCT derived) as total_impacted,
                       collect(DISTINCT derived.id) as impacted_ids
            """

            result = await self.neo4j.run_query(query, {'entity_id': entity_id})

            if not result:
                return {'total_impacted': 0, 'critical_impacted': 0, 'impacted_entities': []}

            total_impacted = result[0]['total_impacted']
            impacted_ids = result[0]['impacted_ids']

            # Identificar entidades críticas baseado em:
            # 1. Classificação de dados (critical, high)
            # 2. Tipo de entidade (cognitive_plan, consensus_decision)
            critical_query = """
                MATCH (e {id: $entity_id})-[:DERIVED_FROM*1..5]->(derived)
                WHERE derived.classification IN ['critical', 'high']
                   OR derived.type IN ['cognitive_plan', 'consensus_decision', 'cognitive_ledger']
                RETURN collect(DISTINCT derived.id) as critical_ids
            """
            critical_result = await self.neo4j.run_query(critical_query, {'entity_id': entity_id})

            # Usar set para unificar IDs críticos e evitar duplicidade
            critical_ids_set = set()

            if critical_result and len(critical_result) > 0:
                critical_ids_set.update(critical_result[0].get('critical_ids', []))

            # Buscar entidades com alta contagem de dependências (>10 derivações = crítico)
            high_dependency_query = """
                MATCH (e {id: $entity_id})-[:DERIVED_FROM*1..5]->(derived)
                WITH derived, size((derived)-[:DERIVED_FROM]->()) as dep_count
                WHERE dep_count > 10
                RETURN collect(DISTINCT derived.id) as high_dep_ids
            """
            high_dep_result = await self.neo4j.run_query(high_dependency_query, {'entity_id': entity_id})

            if high_dep_result and len(high_dep_result) > 0:
                # Adiciona IDs de alta dependência ao conjunto unificado
                critical_ids_set.update(high_dep_result[0].get('high_dep_ids', []))

            # critical_impacted é o tamanho do conjunto unificado (sem duplicatas)
            critical_entities = list(critical_ids_set)
            critical_impacted = len(critical_entities)

            return {
                'entity_id': entity_id,
                'total_impacted': total_impacted,
                'critical_impacted': critical_impacted,
                'critical_entities': critical_entities,
                'impacted_entities': impacted_ids
            }

        except Exception as e:
            logger.error("Impact analysis failed", error=str(e), entity_id=entity_id)
            return {'total_impacted': 0, 'critical_impacted': 0, 'impacted_entities': []}
