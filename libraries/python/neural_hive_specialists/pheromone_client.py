"""
Pheromone Client for Neural Hive Specialists.

Este cliente permite que especialistas publiquem e leiam feromônios
digitais para comunicação assíncrona entre especialistas.
"""

import json
import uuid
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta
import structlog

try:
    from redis.asyncio import Redis as AsyncRedis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    AsyncRedis = None

from neural_hive_domain import DomainMapper, UnifiedDomain


class PheromoneType:
    """Tipo de feromônio digital."""
    SUCCESS = 'success'
    FAILURE = 'failure'
    WARNING = 'warning'


class PheromoneSignal:
    """Sinal de feromônio digital."""

    def __init__(
        self,
        specialist_type: str,
        domain: Union[str, UnifiedDomain],
        pheromone_type: str,
        strength: float,
        plan_id: str,
        intent_id: str,
        decision_id: Optional[str] = None,
        ttl_seconds: int = 3600,
        decay_rate: float = 0.1,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.signal_id = str(uuid.uuid4())
        self.specialist_type = specialist_type
        self.domain = DomainMapper.normalize(domain, 'intent_envelope') if isinstance(domain, str) else domain
        self.pheromone_type = pheromone_type
        self.strength = max(0.0, min(1.0, strength))
        self.plan_id = plan_id
        self.intent_id = intent_id
        self.decision_id = decision_id
        self.created_at = datetime.utcnow()
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)
        self.decay_rate = decay_rate
        self.metadata = metadata or {}

    def get_redis_key(self) -> str:
        """Gera chave Redis padronizada."""
        return DomainMapper.to_pheromone_key(
            domain=self.domain,
            layer='consensus',
            pheromone_type=self.pheromone_type,
            id=self.signal_id
        )

    def calculate_current_strength(self) -> float:
        """Calcula força atual considerando decay temporal."""
        elapsed_hours = (datetime.utcnow() - self.created_at).total_seconds() / 3600
        decayed_strength = self.strength * ((1 - self.decay_rate) ** elapsed_hours)
        return max(0.0, decayed_strength)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário serializável."""
        return {
            'signal_id': self.signal_id,
            'specialist_type': self.specialist_type,
            'domain': self.domain.value if hasattr(self.domain, 'value') else str(self.domain),
            'pheromone_type': self.pheromone_type,
            'strength': self.strength,
            'plan_id': self.plan_id,
            'intent_id': self.intent_id,
            'decision_id': self.decision_id,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'decay_rate': self.decay_rate,
            'metadata': self.metadata
        }


logger = structlog.get_logger()


class PheromoneClient:
    """
    Cliente Redis para gerenciar feromônios digitais.

    Permite que especialistas publiquem sinais de sucesso/falha/aviso
    que outros especialistas podem usar para informar suas decisões.
    """

    def __init__(
        self,
        redis_cluster_nodes: str,
        redis_password: Optional[str] = None,
        redis_ssl_enabled: bool = False,
        pheromone_ttl: int = 3600,
        pheromone_decay_rate: float = 0.1
    ):
        """
        Inicializa cliente de feromônios.

        Args:
            redis_cluster_nodes: Nós do cluster Redis
            redis_password: Senha do Redis
            redis_ssl_enabled: Habilitar TLS
            pheromone_ttl: TTL padrão para feromônios (segundos)
            pheromone_decay_rate: Taxa de decay por hora
        """
        self.redis_cluster_nodes = redis_cluster_nodes
        self.redis_password = redis_password
        self.redis_ssl_enabled = redis_ssl_enabled
        self.pheromone_ttl = pheromone_ttl
        self.pheromone_decay_rate = pheromone_decay_rate

        # Parse host(s) from redis_cluster_nodes
        self.redis_hosts = self._parse_redis_hosts(redis_cluster_nodes)

        # Redis client será inicializado lazy
        self._redis = None

        logger.info(
            "PheromoneClient initialized",
            redis_nodes=redis_cluster_nodes,
            ssl_enabled=redis_ssl_enabled,
            ttl=pheromone_ttl
        )

    def _parse_redis_hosts(self, cluster_nodes: str) -> list:
        """Parse string de nós Redis para lista."""
        # Formato esperado: "host1:port,host2:port" ou "host:port"
        if ',' in cluster_nodes:
            return cluster_nodes.split(',')
        return [cluster_nodes]

    async def _get_redis(self) -> AsyncRedis:
        """Obtém ou cria cliente Redis async."""
        if self._redis is None:
            if not REDIS_AVAILABLE:
                raise ImportError("redis.asyncio not available. Install: pip install redis[hiredis]")

            # Criar conexão Redis
            kwargs = {
                'decode_responses': True,
                'socket_timeout': 5,
                'socket_connect_timeout': 5
            }

            if self.redis_password:
                kwargs['password'] = self.redis_password

            if self.redis_ssl_enabled:
                kwargs['ssl'] = True
                kwargs['ssl_check_hostname'] = False
                kwargs['ssl_cert_reqs'] = 'none'

            # Tentar conexão com cluster
            if len(self.redis_hosts) > 1:
                kwargs['startup_nodes'] = [
                    {'host': h.split(':')[0], 'port': int(h.split(':')[1])}
                    for h in self.redis_hosts
                ]
            else:
                host, port = self.redis_hosts[0].split(':')
                kwargs['host'] = host
                kwargs['port'] = int(port) if ':' in self.redis_hosts[0] else 6379

            self._redis = AsyncRedis(**kwargs)

        return self._redis

    async def publish_pheromone(
        self,
        specialist_type: str,
        domain: Union[str, UnifiedDomain],
        pheromone_type: str,
        strength: float,
        plan_id: str,
        intent_id: str,
        decision_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Publica feromônio no Redis.

        Args:
            specialist_type: Tipo do especialista
            domain: Domínio da avaliação
            pheromone_type: Tipo do feromônio (success, failure, warning)
            strength: Força do sinal (0.0 a 1.0)
            plan_id: ID do plano
            intent_id: ID da intenção
            decision_id: ID da decisão (opcional)
            metadata: Metadados adicionais

        Returns:
            signal_id: ID do sinal criado
        """
        # Criar sinal
        signal = PheromoneSignal(
            specialist_type=specialist_type,
            domain=domain,
            pheromone_type=pheromone_type,
            strength=strength,
            plan_id=plan_id,
            intent_id=intent_id,
            decision_id=decision_id,
            ttl_seconds=self.pheromone_ttl,
            decay_rate=self.pheromone_decay_rate,
            metadata=metadata
        )

        # Obter cliente Redis
        redis = await self._get_redis()

        # Salvar no Redis
        key = signal.get_redis_key()
        signal_json = json.dumps(signal.to_dict())

        await redis.set(
            key,
            signal_json,
            ex=self.pheromone_ttl
        )

        # Adicionar à lista de feromônios ativos
        list_key = f'pheromones:active:{specialist_type}:{signal.domain.value}'
        await redis.lpush(list_key, signal.signal_id)
        await redis.expire(list_key, self.pheromone_ttl)

        logger.info(
            "Pheromone published",
            specialist_type=specialist_type,
            domain=signal.domain.value,
            pheromone_type=pheromone_type,
            strength=strength,
            signal_id=signal.signal_id
        )

        return signal.signal_id

    async def get_pheromone_strength(
        self,
        specialist_type: str,
        domain: Union[str, UnifiedDomain],
        pheromone_type: str
    ) -> float:
        """
        Consulta força atual de feromônio com decay.

        Args:
            specialist_type: Tipo do especialista
            domain: Domínio da avaliação
            pheromone_type: Tipo do feromônio

        Returns:
            Força agregada dos feromônios (0.0 a 1.0)
        """
        # Normalizar domain
        if isinstance(domain, str):
            normalized_domain = DomainMapper.normalize(domain, 'intent_envelope')
        else:
            normalized_domain = domain

        # Obter cliente Redis
        redis = await self._get_redis()

        # Obter lista de feromônios ativos
        list_key = f'pheromones:active:{specialist_type}:{normalized_domain.value}'
        signal_ids = await redis.lrange(list_key, 0, -1)

        if not signal_ids:
            return 0.0

        # Agregar força
        total_strength = 0.0
        count = 0

        for signal_id in signal_ids:
            if isinstance(signal_id, bytes):
                signal_id = signal_id.decode('utf-8')

            key = DomainMapper.to_pheromone_key(
                domain=normalized_domain,
                layer='consensus',
                pheromone_type=pheromone_type,
                id=signal_id
            )

            signal_json = await redis.get(key)
            if signal_json:
                signal_data = json.loads(signal_json)
                if signal_data.get('pheromone_type') == pheromone_type:
                    # Calcular força atual
                    created_at = datetime.fromisoformat(signal_data['created_at'])
                    elapsed_hours = (datetime.utcnow() - created_at).total_seconds() / 3600
                    strength = signal_data['strength']
                    decay_rate = signal_data.get('decay_rate', self.pheromone_decay_rate)
                    decayed = strength * ((1 - decay_rate) ** elapsed_hours)
                    total_strength += max(0.0, decayed)
                    count += 1

        return total_strength / count if count > 0 else 0.0

    async def get_aggregated_pheromone(
        self,
        specialist_type: str,
        domain: Union[str, UnifiedDomain]
    ) -> Dict[str, float]:
        """
        Agrega feromônios de todos os tipos para um especialista.

        Args:
            specialist_type: Tipo do especialista
            domain: Domínio da avaliação

        Returns:
            Dicionário com success, failure, warning e net_strength
        """
        success = await self.get_pheromone_strength(specialist_type, domain, PheromoneType.SUCCESS)
        failure = await self.get_pheromone_strength(specialist_type, domain, PheromoneType.FAILURE)
        warning = await self.get_pheromone_strength(specialist_type, domain, PheromoneType.WARNING)

        # Calcular força líquida
        net_strength = success - failure - (warning * 0.5)
        net_strength = max(0.0, min(1.0, net_strength))

        return {
            'success': success,
            'failure': failure,
            'warning': warning,
            'net_strength': net_strength
        }

    async def close(self):
        """Fecha conexão Redis."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
