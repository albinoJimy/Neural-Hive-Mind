import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver
from typing import Any, Dict, List, Optional

from ..config import Settings
from ..models import StrategicDecision


logger = structlog.get_logger()


class Neo4jClient:
    """Cliente Neo4j para consultas estratégicas ao knowledge graph"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.driver: Optional[AsyncDriver] = None

    async def initialize(self) -> None:
        """Conectar ao Neo4j"""
        try:
            self.driver = AsyncGraphDatabase.driver(
                self.settings.NEO4J_URI,
                auth=(self.settings.NEO4J_USER, self.settings.NEO4J_PASSWORD),
                max_connection_pool_size=self.settings.NEO4J_MAX_CONNECTION_POOL_SIZE
            )

            # Verificar conectividade
            await self.driver.verify_connectivity()
            logger.info("neo4j_initialized")

        except Exception as e:
            logger.error("neo4j_initialization_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Fechar driver Neo4j"""
        if self.driver:
            await self.driver.close()
            logger.info("neo4j_closed")

    async def query_strategic_context(self, plan_ids: List[str]) -> Dict[str, Any]:
        """Consultar contexto estratégico de múltiplos planos"""
        try:
            async with self.driver.session(database=self.settings.NEO4J_DATABASE) as session:
                query = """
                MATCH (p:CognitivePlan)
                WHERE p.plan_id IN $plan_ids
                OPTIONAL MATCH (p)-[:DEPENDS_ON]->(dep:CognitivePlan)
                OPTIONAL MATCH (p)-[:HAS_PRIORITY]->(priority:Priority)
                RETURN p, collect(dep) as dependencies, priority
                LIMIT 100
                """

                result = await session.run(query, plan_ids=plan_ids)
                records = await result.data()

                context = {
                    "plans": [],
                    "dependencies": [],
                    "priorities": []
                }

                for record in records:
                    if record.get('p'):
                        context["plans"].append(dict(record['p']))
                    if record.get('dependencies'):
                        context["dependencies"].extend([dict(d) for d in record['dependencies']])
                    if record.get('priority'):
                        context["priorities"].append(dict(record['priority']))

                return context

        except Exception as e:
            logger.error("strategic_context_query_failed", error=str(e))
            return {}

    async def get_plan_dependencies(self, plan_id: str) -> List[Dict[str, Any]]:
        """Obter grafo de dependências de um plano"""
        try:
            async with self.driver.session(database=self.settings.NEO4J_DATABASE) as session:
                query = """
                MATCH path = (p:CognitivePlan {plan_id: $plan_id})-[:DEPENDS_ON*1..3]->(dep)
                RETURN path
                LIMIT 50
                """

                result = await session.run(query, plan_id=plan_id)
                records = await result.data()

                dependencies = []
                for record in records:
                    if 'path' in record:
                        dependencies.append(record['path'])

                return dependencies

        except Exception as e:
            logger.error("plan_dependencies_query_failed", plan_id=plan_id, error=str(e))
            return []

    async def get_domain_conflicts(self, domains: List[str]) -> List[Dict[str, Any]]:
        """Identificar conflitos históricos entre domínios"""
        try:
            async with self.driver.session(database=self.settings.NEO4J_DATABASE) as session:
                query = """
                MATCH (d1:Domain)-[r:CONFLICTS_WITH]->(d2:Domain)
                WHERE d1.name IN $domains AND d2.name IN $domains
                RETURN d1, r, d2, r.severity as severity
                ORDER BY r.severity DESC
                LIMIT 20
                """

                result = await session.run(query, domains=domains)
                records = await result.data()

                conflicts = []
                for record in records:
                    conflicts.append({
                        'domain1': dict(record['d1']),
                        'domain2': dict(record['d2']),
                        'relationship': dict(record['r']),
                        'severity': record.get('severity', 0.0)
                    })

                return conflicts

        except Exception as e:
            logger.error("domain_conflicts_query_failed", error=str(e))
            return []

    async def get_success_patterns(self, domain: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Buscar padrões de sucesso para um domínio"""
        try:
            async with self.driver.session(database=self.settings.NEO4J_DATABASE) as session:
                query = """
                MATCH (d:Domain {name: $domain})-[:HAS_PATTERN]->(p:SuccessPattern)
                RETURN p
                ORDER BY p.success_rate DESC, p.usage_count DESC
                LIMIT $limit
                """

                result = await session.run(query, domain=domain, limit=limit)
                records = await result.data()

                patterns = [dict(record['p']) for record in records if 'p' in record]
                return patterns

        except Exception as e:
            logger.error("success_patterns_query_failed", domain=domain, error=str(e))
            return []

    async def get_critical_paths(self) -> List[Dict[str, Any]]:
        """Identificar caminhos críticos no grafo de execução"""
        try:
            async with self.driver.session(database=self.settings.NEO4J_DATABASE) as session:
                query = """
                MATCH path = (start:CognitivePlan)-[:DEPENDS_ON*]->(end:CognitivePlan)
                WHERE NOT (start)<-[:DEPENDS_ON]-() AND NOT (end)-[:DEPENDS_ON]->()
                WITH path, length(path) as pathLength
                ORDER BY pathLength DESC
                LIMIT 10
                RETURN path, pathLength
                """

                result = await session.run(query)
                records = await result.data()

                critical_paths = []
                for record in records:
                    critical_paths.append({
                        'path': record.get('path'),
                        'length': record.get('pathLength', 0)
                    })

                return critical_paths

        except Exception as e:
            logger.error("critical_paths_query_failed", error=str(e))
            return []

    async def record_strategic_decision(self, decision: StrategicDecision) -> None:
        """Registrar decisão no grafo para análise futura"""
        try:
            async with self.driver.session(database=self.settings.NEO4J_DATABASE) as session:
                query = """
                CREATE (d:StrategicDecision {
                    decision_id: $decision_id,
                    decision_type: $decision_type,
                    confidence_score: $confidence_score,
                    risk_score: $risk_score,
                    created_at: $created_at
                })
                RETURN d
                """

                await session.run(
                    query,
                    decision_id=decision.decision_id,
                    decision_type=decision.decision_type.value,
                    confidence_score=decision.confidence_score,
                    risk_score=decision.risk_assessment.risk_score,
                    created_at=decision.created_at
                )

                logger.info("strategic_decision_recorded_in_neo4j", decision_id=decision.decision_id)

        except Exception as e:
            logger.error("strategic_decision_record_failed", decision_id=decision.decision_id, error=str(e))

    async def list_active_conflicts(self) -> List[Dict[str, Any]]:
        """Listar conflitos ativos entre decisões"""
        try:
            async with self.driver.session(database=self.settings.NEO4J_DATABASE) as session:
                query = """
                MATCH (d:Decision)-[:CONFLICTS_WITH]->(d2:Decision)
                WHERE d.resolved = false
                RETURN d.decision_id as decision_id, d2.decision_id as conflicts_with, d.created_at as created_at
                LIMIT 50
                """

                result = await session.run(query)
                records = await result.data()

                conflicts = []
                for record in records:
                    conflicts.append({
                        'decision_id': record.get('decision_id'),
                        'conflicts_with': record.get('conflicts_with'),
                        'created_at': record.get('created_at')
                    })

                return conflicts

        except Exception as e:
            logger.error("list_active_conflicts_failed", error=str(e))
            return []
