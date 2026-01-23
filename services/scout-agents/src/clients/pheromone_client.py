"""Cliente para publicação de feromônios digitais"""
import json
from datetime import datetime
from typing import Optional
import structlog
import redis.asyncio as redis

from neural_hive_domain import DomainMapper, UnifiedDomain

from ..models.scout_signal import ScoutSignal
from ..config import get_settings

logger = structlog.get_logger()


class PheromoneClient:
    """Cliente para publicar feromônios digitais no Redis"""

    def __init__(self):
        self.settings = get_settings()
        self.redis_client: Optional[redis.Redis] = None
        self.enabled = self.settings.pheromone.enabled
        self.ttl = self.settings.pheromone.ttl
        self.decay_rate = self.settings.pheromone.decay_rate

    async def start(self):
        """Inicializa conexão com Redis"""
        if not self.enabled:
            logger.info("pheromone_client_disabled")
            return

        try:
            # Conecta ao Redis usando configuração
            self.redis_client = await redis.from_url(
                self.settings.pheromone.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("pheromone_client_started")
        except Exception as e:
            logger.error("pheromone_client_start_failed", error=str(e))
            raise

    async def stop(self):
        """Encerra conexão com Redis"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("pheromone_client_stopped")

    async def publish_pheromone(self, signal: ScoutSignal) -> bool:
        """
        Publica feromônio digital para um sinal

        Args:
            signal: Sinal de exploração

        Returns:
            bool: Sucesso da publicação
        """
        if not self.enabled or not self.redis_client:
            return False

        try:
            # Calcula intensidade inicial baseada em prioridade e curiosidade
            initial_intensity = (
                signal.calculate_priority() * 0.6 +
                signal.curiosity_score * 0.4
            )

            # Cria entrada de feromônio
            pheromone_data = {
                'signal_id': signal.signal_id,
                'scout_agent_id': signal.scout_agent_id,
                'domain': signal.exploration_domain.value,
                'channel': signal.source.channel.value,
                'signal_type': signal.signal_type.value,
                'intensity': initial_intensity,
                'decay_rate': self.decay_rate,
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat(),
                'metadata': {
                    'curiosity_score': signal.curiosity_score,
                    'confidence': signal.confidence,
                    'relevance_score': signal.relevance_score,
                    'risk_score': signal.risk_score
                }
            }

            # Chave Redis padronizada via DomainMapper
            # Formato: pheromone:exploration:{domain}:{signal_type}:{signal_id}
            redis_key = DomainMapper.to_pheromone_key(
                domain=signal.exploration_domain,  # Já é UnifiedDomain
                layer='exploration',
                pheromone_type=signal.signal_type.value,
                id=signal.signal_id
            )

            # Armazena com TTL
            await self.redis_client.setex(
                redis_key,
                self.ttl,
                json.dumps(pheromone_data)
            )

            logger.debug(
                "pheromone_published",
                signal_id=signal.signal_id,
                redis_key=redis_key,
                intensity=initial_intensity,
                ttl=self.ttl
            )

            return True

        except Exception as e:
            logger.error(
                "pheromone_publish_failed",
                signal_id=signal.signal_id,
                error=str(e)
            )
            return False

    async def get_pheromone_intensity(
        self,
        domain: str,
        signal_type: str,
        signal_id: str
    ) -> Optional[float]:
        """
        Obtém intensidade atual de um feromônio com decay aplicado

        Args:
            domain: Domínio de exploração
            signal_type: Tipo de sinal
            signal_id: ID do sinal

        Returns:
            float: Intensidade atual ou None se não existir
        """
        if not self.enabled or not self.redis_client:
            return None

        try:
            # Normalizar domain para UnifiedDomain e gerar chave padronizada
            normalized_domain = DomainMapper.normalize(domain, 'scout_signal')
            redis_key = DomainMapper.to_pheromone_key(
                domain=normalized_domain,
                layer='exploration',
                pheromone_type=signal_type,
                id=signal_id
            )
            data_str = await self.redis_client.get(redis_key)

            if not data_str:
                return None

            data = json.loads(data_str)

            # Calcula decay baseado no tempo decorrido
            created_at = datetime.fromisoformat(data['created_at'])
            elapsed_hours = (datetime.utcnow() - created_at).total_seconds() / 3600

            # Aplicar decay exponencial
            initial_intensity = data['intensity']
            current_intensity = initial_intensity * (
                (1 - self.decay_rate) ** elapsed_hours
            )

            return max(current_intensity, 0.0)

        except Exception as e:
            logger.error(
                "pheromone_read_failed",
                signal_id=signal_id,
                error=str(e)
            )
            return None
