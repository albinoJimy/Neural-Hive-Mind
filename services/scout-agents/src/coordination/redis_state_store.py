"""
RedisStateStore - Compartilhamento de estado entre scouts via Redis.

Responsável por:
- Armazenar estado de exploração
- Compartilhar progresso entre scouts
- Sincronizar descobertas
- Gerenciar locks para evitar trabalho duplicado
"""
import json
from datetime import datetime
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis_not_available")


class RedisStateStore:
    """Armazena estado compartilhado em Redis."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "scout_agents:",
        ttl: int = 3600,
    ):
        """
        Inicializa RedisStateStore.

        Args:
            redis_url: URL do Redis
            key_prefix: Prefixo para chaves
            ttl: Time to live padrão (segundos)
        """
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.ttl = ttl
        self._redis: Optional[aioredis.Redis] = None

    async def start(self):
        """Inicia conexão com Redis."""
        if not REDIS_AVAILABLE:
            logger.warning("redis_unavailable", message="Using in-memory fallback")
            return

        try:
            self._redis = await aioredis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            await self._redis.ping()

            logger.info("redis_connected", url=self.redis_url)

        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            self._redis = None

    async def stop(self):
        """Fecha conexão com Redis."""
        if self._redis:
            await self._redis.close()
            logger.info("redis_disconnected")

    def _make_key(self, *parts: str) -> str:
        """Cria chave Redis com prefixo."""
        # Garantir separador adequado
        if self.key_prefix.endswith(":"):
            return self.key_prefix + ":".join(parts)
        else:
            return self.key_prefix + ":" + ":".join(parts)

    async def set_task_progress(self, scout_id: str, task_id: str, progress: Dict):
        """
        Armazena progresso de tarefa.

        Args:
            scout_id: ID do scout
            task_id: ID da tarefa
            progress: Dict de progresso
        """
        key = self._make_key("task", task_id)
        data = {
            "scout_id": scout_id,
            "progress": progress,
            "updated_at": datetime.now().isoformat(),
        }

        if self._redis:
            await self._redis.setex(key, self.ttl, json.dumps(data))

        logger.debug("task_progress_stored", task_id=task_id)

    async def get_task_progress(self, task_id: str) -> Optional[Dict]:
        """
        Recupera progresso de tarefa.

        Args:
            task_id: ID da tarefa

        Returns:
            Dict de progresso ou None
        """
        key = self._make_key("task", task_id)

        if self._redis:
            data = await self._redis.get(key)
            if data:
                return json.loads(data)

        return None

    async def mark_file_explored(self, filepath: str, scout_id: str, exploration_id: str):
        """
        Marca arquivo como explorado.

        Args:
            filepath: Caminho do arquivo
            scout_id: ID do scout que explorou
            exploration_id: ID da exploração
        """
        key = self._make_key("explored", exploration_id)
        data = {
            "filepath": filepath,
            "scout_id": scout_id,
            "explored_at": datetime.now().isoformat(),
        }

        if self._redis:
            await self._redis.hset(key, filepath, json.dumps(data))
            await self._redis.expire(key, self.ttl)

        logger.debug("file_marked_explored", filepath=filepath)

    async def is_file_explored(self, filepath: str, exploration_id: str) -> bool:
        """
        Verifica se arquivo foi explorado.

        Args:
            filepath: Caminho do arquivo
            exploration_id: ID da exploração

        Returns:
            True se já explorado
        """
        key = self._make_key("explored", exploration_id)

        if self._redis:
            return await self._redis.hexists(key, filepath)

        return False

    async def acquire_lock(self, resource: str, scout_id: str, ttl: int = 60) -> bool:
        """
        Tenta adquirir lock para recurso.

        Args:
            resource: Identificador do recurso
            scout_id: ID do scout
            ttl: Tempo de vida do lock (segundos)

        Returns:
            True se lock adquirido
        """
        key = self._make_key("lock", resource)
        lock_value = f"{scout_id}:{datetime.now().timestamp()}"

        if self._redis:
            # SET NX (apenas se não existe)
            acquired = await self._redis.set(key, lock_value, nx=True, ex=ttl)

            if acquired:
                logger.debug("lock_acquired", resource=resource, scout_id=scout_id)

            return acquired

        return True  # Fallback: sempre retorna True sem Redis

    async def release_lock(self, resource: str, scout_id: str):
        """
        Libera lock de recurso.

        Args:
            resource: Identificador do recurso
            scout_id: ID do scout
        """
        key = self._make_key("lock", resource)

        if self._redis:
            # Verificar se é o dono do lock
            current_value = await self._redis.get(key)
            expected_prefix = f"{scout_id}:"

            if current_value and current_value.startswith(expected_prefix):
                await self._redis.delete(key)
                logger.debug("lock_released", resource=resource, scout_id=scout_id)

    async def publish_discovery(self, exploration_id: str, discovery: Dict):
        """
        Publica descoberta para outros scouts.

        Args:
            exploration_id: ID da exploração
            discovery: Dict da descoberta
        """
        key = self._make_key("discoveries", exploration_id)
        data = {"discovery": discovery, "published_at": datetime.now().isoformat()}

        if self._redis:
            # Adicionar a lista
            await self._redis.lpush(key, json.dumps(data))
            # Manter apenas últimos 1000
            await self._redis.ltrim(key, 0, 999)
            await self._redis.expire(key, self.ttl)

        logger.debug("discovery_published", exploration_id=exploration_id)

    async def get_discoveries(self, exploration_id: str, limit: int = 100) -> List[Dict]:
        """
        Recupera descobertas de uma exploração.

        Args:
            exploration_id: ID da exploração
            limit: Máximo de descobertas

        Returns:
            Lista de descobertas
        """
        key = self._make_key("discoveries", exploration_id)

        if self._redis:
            raw_data = await self._redis.lrange(key, 0, limit - 1)
            return [json.loads(d) for d in raw_data]

        return []

    async def set_scout_state(self, scout_id: str, state: Dict):
        """
        Armazena estado de um scout.

        Args:
            scout_id: ID do scout
            state: Dict de estado
        """
        key = self._make_key("scout_state", scout_id)
        state["updated_at"] = datetime.now().isoformat()

        if self._redis:
            await self._redis.setex(key, self.ttl, json.dumps(state))

        logger.debug("scout_state_stored", scout_id=scout_id)

    async def get_scout_state(self, scout_id: str) -> Optional[Dict]:
        """
        Recupera estado de um scout.

        Args:
            scout_id: ID do scout

        Returns:
            Dict de estado ou None
        """
        key = self._make_key("scout_state", scout_id)

        if self._redis:
            data = await self._redis.get(key)
            if data:
                return json.loads(data)

        return None

    async def get_all_scout_states(self) -> Dict[str, Dict]:
        """
        Recupera estados de todos os scouts.

        Returns:
            Dict {scout_id: state}
        """
        states = {}

        if self._redis:
            pattern = self._make_key("scout_state", "*")
            keys = []

            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)

            for key in keys:
                data = await self._redis.get(key)
                if data:
                    state = json.loads(data)
                    scout_id = key.split(":")[-1]
                    states[scout_id] = state

        return states

    async def increment_counter(self, name: str, delta: int = 1) -> int:
        """
        Incrementa contador compartilhado.

        Args:
            name: Nome do contador
            delta: Valor a incrementar

        Returns:
            Novo valor do contador
        """
        key = self._make_key("counter", name)

        if self._redis:
            return await self._redis.incrby(key, delta)

        return delta  # Fallback

    async def get_counter(self, name: str) -> int:
        """
        Recupera valor de contador.

        Args:
            name: Nome do contador

        Returns:
            Valor do contador
        """
        key = self._make_key("counter", name)

        if self._redis:
            value = await self._redis.get(key)
            return int(value) if value else 0

        return 0

    async def cleanup_expired(self, exploration_id: str):
        """
        Limpa dados expirados de uma exploração.

        Args:
            exploration_id: ID da exploração
        """
        # Remove locks expirados
        if self._redis:
            pattern = self._make_key("lock", "*")
            async for key in self._redis.scan_iter(match=pattern):
                ttl = await self._redis.ttl(key)
                if ttl == -1:  # Sem expiração
                    await self._redis.expire(key, 300)  # 5 minutos

        logger.info("cleanup_completed", exploration_id=exploration_id)
