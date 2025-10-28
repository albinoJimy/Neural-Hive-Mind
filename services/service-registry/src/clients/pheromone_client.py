import redis
import structlog
from typing import Dict, Optional
from src.models import AgentType


logger = structlog.get_logger()


class PheromoneClient:
    """Cliente para integração com feromônios digitais"""

    def __init__(self, cluster_nodes: list[str], password: str = ""):
        self.cluster_nodes = cluster_nodes
        self.password = password
        self.redis_client: Optional[redis.Redis] = None

    async def initialize(self) -> None:
        """Inicializa conexão com Redis"""
        try:
            # Parse first node
            host, port = self.cluster_nodes[0].split(":")
            self.redis_client = redis.Redis(
                host=host,
                port=int(port),
                password=self.password,
                decode_responses=True
            )

            # Test connection
            self.redis_client.ping()
            logger.info("pheromone_client_initialized", nodes=self.cluster_nodes)

        except Exception as e:
            logger.error("pheromone_client_initialization_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Fecha conexão com Redis"""
        if self.redis_client:
            self.redis_client.close()
            logger.info("pheromone_client_closed")

    async def get_agent_pheromone_score(
        self,
        agent_id: str,
        agent_type: AgentType,
        domain: str = "default"
    ) -> float:
        """
        Calcula score de feromônio normalizado [0.0-1.0] para o agente.

        Baseado na implementação de consensus-engine/src/clients/pheromone_client.py
        """
        try:
            # Chaves Redis para feromônios agregados
            success_key = f"pheromone:{domain}:{agent_type.value.lower()}:{agent_id}:success"
            failure_key = f"pheromone:{domain}:{agent_type.value.lower()}:{agent_id}:failure"
            warning_key = f"pheromone:{domain}:{agent_type.value.lower()}:{agent_id}:warning"

            # Buscar valores (com fallback para 0)
            success = float(self.redis_client.get(success_key) or 0.0)
            failure = float(self.redis_client.get(failure_key) or 0.0)
            warning = float(self.redis_client.get(warning_key) or 0.0)

            # Calcular score normalizado
            total = success + failure + warning
            if total == 0:
                return 0.5  # Score neutro para agentes sem histórico

            # Pesos: success (+), warning (neutro), failure (-)
            weighted_score = (success * 1.0 + warning * 0.5 + failure * 0.0) / total

            logger.debug(
                "pheromone_score_calculated",
                agent_id=agent_id,
                agent_type=agent_type.value,
                success=success,
                failure=failure,
                warning=warning,
                score=weighted_score
            )

            return weighted_score

        except Exception as e:
            logger.error(
                "get_pheromone_score_failed",
                agent_id=agent_id,
                error=str(e)
            )
            # Retornar score neutro em caso de erro
            return 0.5

    async def publish_agent_pheromone(
        self,
        agent_id: str,
        agent_type: AgentType,
        pheromone_type: str,  # "success", "failure", "warning"
        strength: float = 1.0,
        domain: str = "default"
    ) -> bool:
        """
        Publica feromônio para o agente após execução.

        Args:
            agent_id: ID do agente
            agent_type: Tipo do agente
            pheromone_type: Tipo de feromônio (success/failure/warning)
            strength: Força do feromônio [0.0-1.0]
            domain: Domínio do feromônio
        """
        try:
            key = f"pheromone:{domain}:{agent_type.value.lower()}:{agent_id}:{pheromone_type}"

            # Incrementar contador de feromônio
            self.redis_client.incrbyfloat(key, strength)

            # Definir TTL de 24h para evitar acumulação indefinida
            self.redis_client.expire(key, 86400)

            logger.info(
                "pheromone_published",
                agent_id=agent_id,
                agent_type=agent_type.value,
                pheromone_type=pheromone_type,
                strength=strength
            )

            return True

        except Exception as e:
            logger.error(
                "publish_pheromone_failed",
                agent_id=agent_id,
                error=str(e)
            )
            return False

    async def get_aggregated_pheromones(
        self,
        agent_type: AgentType,
        domain: str = "default"
    ) -> Dict[str, float]:
        """
        Retorna feromônios agregados para todos os agentes de um tipo.

        Returns:
            Dict[agent_id, pheromone_score]
        """
        try:
            pattern = f"pheromone:{domain}:{agent_type.value.lower()}:*:success"
            scores = {}

            for key in self.redis_client.scan_iter(match=pattern):
                # Extrair agent_id da chave
                parts = key.split(":")
                if len(parts) >= 4:
                    agent_id = parts[3]
                    score = await self.get_agent_pheromone_score(
                        agent_id,
                        agent_type,
                        domain
                    )
                    scores[agent_id] = score

            logger.info(
                "aggregated_pheromones_retrieved",
                agent_type=agent_type.value,
                count=len(scores)
            )

            return scores

        except Exception as e:
            logger.error(
                "get_aggregated_pheromones_failed",
                agent_type=agent_type.value,
                error=str(e)
            )
            return {}
