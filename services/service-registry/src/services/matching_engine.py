import structlog
from typing import Dict, List, Optional
from src.models import AgentInfo, AgentType, AgentStatus
from src.clients import EtcdClient, PheromoneClient
from prometheus_client import Counter, Histogram

from neural_hive_observability import get_tracer


logger = structlog.get_logger()
tracer = get_tracer()


# Métricas Prometheus
discovery_requests_total = Counter(
    'discovery_requests_total',
    'Total de requisições de discovery',
    ['agent_type']
)

discovery_duration_seconds = Histogram(
    'discovery_duration_seconds',
    'Duração de requisições de discovery'
)

matching_candidates_evaluated = Histogram(
    'matching_candidates_evaluated',
    'Número de candidatos avaliados no matching'
)

agents_matched = Histogram(
    'agents_matched',
    'Número de agentes retornados no matching'
)


class MatchingEngine:
    """Motor de matching inteligente para descoberta de agentes"""

    def __init__(self, etcd_client: EtcdClient, pheromone_client: PheromoneClient):
        self.etcd_client = etcd_client
        self.pheromone_client = pheromone_client

        # Pesos para cálculo de score composto
        self.HEALTH_WEIGHT = 0.4
        self.PHEROMONE_WEIGHT = 0.3
        self.TELEMETRY_WEIGHT = 0.3

    @discovery_duration_seconds.time()
    async def match_agents(
        self,
        capabilities_required: List[str],
        filters: Optional[Dict[str, str]] = None,
        max_results: int = 5,
        agent_type: Optional[AgentType] = None
    ) -> List[AgentInfo]:
        """
        Descobre agentes baseado em capabilities e retorna lista ranqueada.

        Args:
            capabilities_required: Lista de capabilities necessárias
            filters: Filtros adicionais (namespace, cluster, version)
            max_results: Número máximo de resultados
            agent_type: Tipo de agente (opcional, para otimizar busca)

        Returns:
            Lista de AgentInfo ordenada por score (melhor primeiro)
        """
        with tracer.start_as_current_span("match_agents") as span:
            try:
                span.set_attribute("neural.hive.capability.required", ",".join(capabilities_required))
                # Métricas
                if agent_type:
                    discovery_requests_total.labels(agent_type=agent_type.value).inc()
                else:
                    discovery_requests_total.labels(agent_type="all").inc()

                # 1. Listar agentes candidatos
                all_agents = await self.etcd_client.list_agents(agent_type, filters)

                # 2. Filtrar por capabilities (set intersection)
                candidates = self._filter_by_capabilities(all_agents, capabilities_required)

                # 3. Filtrar apenas agentes HEALTHY
                candidates = [a for a in candidates if a.status == AgentStatus.HEALTHY]

                if not candidates:
                    logger.warning(
                        "no_healthy_candidates_found",
                        capabilities_required=capabilities_required,
                        filters=filters
                    )
                    matching_candidates_evaluated.observe(0)
                    agents_matched.observe(0)
                    span.set_attribute("neural.hive.agents.matched", 0)
                    return []

                matching_candidates_evaluated.observe(len(candidates))

                # 4. Calcular scores e ranquear
                ranked_agents = await self._rank_agents(candidates)

                # 5. Retornar top N
                result = ranked_agents[:max_results]

                agents_matched.observe(len(result))
                span.set_attribute("neural.hive.agents.matched", len(result))

                logger.info(
                    "agents_matched_successfully",
                    capabilities_required=capabilities_required,
                    candidates_evaluated=len(candidates),
                    agents_matched=len(result)
                )

                return result

            except Exception as e:
                logger.error("match_agents_failed", error=str(e))
                raise

    def _filter_by_capabilities(
        self,
        agents: List[AgentInfo],
        required_capabilities: List[str]
    ) -> List[AgentInfo]:
        """Filtra agentes que possuem todas as capabilities requeridas"""
        required_set = set(required_capabilities)
        filtered = []

        for agent in agents:
            agent_capabilities = set(agent.capabilities)

            # Verificar se agente possui todas as capabilities necessárias
            if required_set.issubset(agent_capabilities):
                filtered.append(agent)

        logger.debug(
            "capabilities_filter_applied",
            total_agents=len(agents),
            filtered_agents=len(filtered),
            required_capabilities=required_capabilities
        )

        return filtered

    async def _rank_agents(self, agents: List[AgentInfo]) -> List[AgentInfo]:
        """
        Ranqueia agentes baseado em score composto.

        Score = (health_score * 0.4) + (pheromone_score * 0.3) + (telemetry_score * 0.3)
        """
        agent_scores = []

        for agent in agents:
            # 1. Health score (baseado em status)
            health_score = agent.calculate_health_score()

            # 2. Pheromone score (baseado em feromônios digitais)
            pheromone_score = await self.pheromone_client.get_agent_pheromone_score(
                agent_id=str(agent.agent_id),
                agent_type=agent.agent_type,
                domain="default"
            )

            # 3. Telemetry score (baseado em success_rate)
            telemetry_score = agent.telemetry.calculate_score()

            # 4. Calcular score composto
            composite_score = (
                health_score * self.HEALTH_WEIGHT +
                pheromone_score * self.PHEROMONE_WEIGHT +
                telemetry_score * self.TELEMETRY_WEIGHT
            )

            agent_scores.append((agent, composite_score))

            logger.debug(
                "agent_score_calculated",
                agent_id=str(agent.agent_id),
                agent_type=agent.agent_type.value,
                health_score=health_score,
                pheromone_score=pheromone_score,
                telemetry_score=telemetry_score,
                composite_score=composite_score
            )

        # Ordenar por score decrescente (melhor primeiro)
        agent_scores.sort(key=lambda x: x[1], reverse=True)

        # Retornar apenas os agentes (sem scores)
        ranked_agents = [agent for agent, score in agent_scores]

        return ranked_agents
