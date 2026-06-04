"""
Serviço de Fallback Storage para Redis com persistência em MongoDB.

Implementa pattern "Cache-aside com fallback persistente":
- Tenta Redis primeiro (baixa latência)
- Em falha, usa MongoDB como fallback
- Background sync para restaurar Redis quando disponível
- Garante consistência escrevendo em AMBOS (Redis + MongoDB)

Gap P0-3: State Divergence - Redis primário sem fallback MongoDB
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


class FallbackStorage:
    """
    Serviço de fallback para Redis com persistência em MongoDB.

    Workflow:
    1. READ: Tenta Redis → falha → busca MongoDB → retorna
    2. WRITE: Escreve em AMBOS (Redis + MongoDB) para consistência
    3. BACKGROUND: Task que tenta restaurar dados do MongoDB para Redis

    Métricas:
    - Redis hits: leitura bem-sucedida do Redis
    - Fallback hits: leitura do MongoDB após falha Redis
    - Redis failures: contagem de falhas Redis
    - Sync successes: dados restaurados para Redis
    """

    # Collection MongoDB para fallback
    FALLBACK_COLLECTION = "redis_fallback"

    # Chaves que persistem no fallback
    PHEROMONE_KEYS = "pheromone:*"
    CACHE_KEYS = "cache:*"

    def __init__(self, redis_client, mongodb_client, config):
        """
        Inicializa serviço de fallback.

        Args:
            redis_client: Cliente Redis async
            mongodb_client: Cliente MongoDB (motor)
            config: Configurações do consensus-engine
        """
        self.redis = redis_client
        self.mongodb = mongodb_client
        self.config = config

        # Métricas
        self._redis_hits = 0
        self._fallback_hits = 0
        self._redis_failures = 0
        self._sync_successes = 0
        self._sync_failures = 0

        # Controle de background sync
        self._sync_running = False
        self._sync_interval = 60  # segundos

        # Flag para desabilitar Redis (degradação controlada)
        self._redis_enabled = True

        logger.info(
            "Fallback storage inicializado",
            redis_enabled=self._redis_enabled,
            sync_interval=self._sync_interval,
        )

    async def initialize(self):
        """Inicializa índices MongoDB para fallback"""
        try:
            collection = self.mongodb.db[self.FALLBACK_COLLECTION]

            # Índices para performance
            await collection.create_index("key", unique=True)
            await collection.create_index("expires_at")
            await collection.create_index([("key", 1), ("expires_at", 1)])

            # Índice TTL para limpeza automática
            await collection.create_index("expires_at", expireAfterSeconds=0)

            logger.info("Índices de fallback storage criados")
        except Exception as e:
            logger.warning("Erro ao criar índices de fallback", error=str(e))

    async def get(self, key: str) -> Optional[str]:
        """
        Obtém valor do Redis com fallback para MongoDB.

        Args:
            key: Chave do Redis

        Returns:
            Valor como string ou None
        """
        # 1. Tentar Redis primeiro
        if self._redis_enabled:
            try:
                value = await self.redis.get(key)
                if value:
                    self._redis_hits += 1
                    logger.debug("Fallback: Redis hit", key=key)
                    return value
            except Exception as e:
                self._redis_failures += 1
                logger.warning(
                    "Fallback: Redis falhou, usando MongoDB",
                    key=key,
                    error=str(e),
                )

        # 2. Fallback para MongoDB
        value = await self._get_from_mongodb(key)
        if value:
            self._fallback_hits += 1
            logger.info("Fallback: MongoDB hit", key=key)

            # Tentar restaurar no Redis em background
            if self._redis_enabled:
                asyncio.create_task(self._restore_to_redis(key, value))

        return value

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """
        Define valor escrevendo em AMBOS Redis e MongoDB.

        Args:
            key: Chave do Redis
            value: Valor a definir
            ex: Expiração em segundos (opcional)

        Returns:
            True se sucesso em pelo menos um
        """
        success = False
        redis_ok = False
        mongo_ok = False

        # Calcular expiração
        expires_at = None
        if ex:
            expires_at = datetime.now(timezone.utc).replace(
                microsecond=0
            )  # MongoDB precisa sem microsegundos
            expires_at = expires_at + timedelta(seconds=ex)

        # 1. Escrever no Redis
        if self._redis_enabled:
            try:
                await self.redis.set(key, value, ex=ex)
                redis_ok = True
                logger.debug("Fallback: Redis set ok", key=key, ex=ex)
            except Exception as e:
                self._redis_failures += 1
                logger.warning("Fallback: Redis set falhou", key=key, error=str(e))

        # 2. SEMPRE escrever no MongoDB (persistência)
        try:
            await self._set_to_mongodb(key, value, expires_at)
            mongo_ok = True
            logger.debug("Fallback: MongoDB set ok", key=key)
        except Exception as e:
            logger.error("Fallback: MongoDB set falhou", key=key, error=str(e))

        # Sucesso se pelo menos um funcionou
        success = redis_ok or mongo_ok

        if not success:
            logger.error("Fallback: AMBOS Redis e MongoDB falharam", key=key)
            self._redis_failures += 1

        return success

    async def delete(self, key: str) -> bool:
        """
        Remove de AMBOS Redis e MongoDB.

        Args:
            key: Chave a remover

        Returns:
            True se sucesso em pelo menos um
        """
        success = False

        # 1. Deletar do Redis
        if self._redis_enabled:
            try:
                await self.redis.delete(key)
                success = True
                logger.debug("Fallback: Redis delete ok", key=key)
            except Exception as e:
                logger.warning("Fallback: Redis delete falhou", key=key, error=str(e))

        # 2. Deletar do MongoDB
        try:
            await self._delete_from_mongodb(key)
            success = True
            logger.debug("Fallback: MongoDB delete ok", key=key)
        except Exception as e:
            logger.error("Fallback: MongoDB delete falhou", key=key, error=str(e))

        return success

    async def lrange(self, key: str, start: int, end: int) -> list:
        """
        Obtém range de lista com fallback para MongoDB.

        Args:
            key: Chave da lista
            start: Início do range
            end: Fim do range (-1 para todos)

        Returns:
            Lista de valores
        """
        # 1. Tentar Redis primeiro
        if self._redis_enabled:
            try:
                values = await self.redis.lrange(key, start, end)
                if values:
                    self._redis_hits += 1
                    return values
            except Exception as e:
                self._redis_failures += 1
                logger.warning("Fallback: Redis lrange falhou", key=key, error=str(e))

        # 2. Fallback para MongoDB
        return await self._lrange_from_mongodb(key, start, end)

    async def lpush(self, key: str, *values) -> int:
        """
        Adiciona valores ao início da lista em AMBOS.

        Args:
            key: Chave da lista
            *values: Valores a adicionar

        Returns:
            Tamanho da lista após inserção
        """
        redis_len = 0
        mongo_len = 0

        # 1. LPush no Redis
        if self._redis_enabled:
            try:
                redis_len = await self.redis.lpush(key, *values)
            except Exception as e:
                self._redis_failures += 1
                logger.warning("Fallback: Redis lpush falhou", key=key, error=str(e))

        # 2. LPush no MongoDB
        try:
            mongo_len = await self._lpush_to_mongodb(key, *values)
        except Exception as e:
            logger.error("Fallback: MongoDB lpush falhou", key=key, error=str(e))

        # Retornar tamanho do Redis se disponível, senão MongoDB
        return redis_len if redis_len > 0 else mongo_len

    async def expire(self, key: str, seconds: int) -> bool:
        """
        Define expiração em AMBOS.

        Args:
            key: Chave
            seconds: Segundos até expirar

        Returns:
            True se sucesso
        """
        success = False

        # 1. Expirar no Redis
        if self._redis_enabled:
            try:
                await self.redis.expire(key, seconds)
                success = True
            except Exception as e:
                logger.warning("Fallback: Redis expire falhou", key=key, error=str(e))

        # 2. Expirar no MongoDB
        try:
            await self._expire_in_mongodb(key, seconds)
            success = True
        except Exception as e:
            logger.error("Fallback: MongoDB expire falhou", key=key, error=str(e))

        return success

    async def ping(self) -> bool:
        """
        Verifica saúde de AMBOS Redis e MongoDB.

        Returns:
            True se pelo menos um está saudável
        """
        redis_ok = False
        mongo_ok = False

        # Verificar Redis
        if self._redis_enabled:
            try:
                await self.redis.ping()
                redis_ok = True
            except Exception:
                redis_ok = False

        # Verificar MongoDB
        try:
            await self.mongodb.client.admin.command("ping")
            mongo_ok = True
        except Exception:
            mongo_ok = False

        # Se Redis falhar consistentemente, desabilitar temporariamente
        if not redis_ok and self._redis_enabled:
            self._redis_enabled = False
            logger.warning("Redis desabilitado temporariamente devido a falhas")

        # Se MongoDB falhar, é crítico
        if not mongo_ok:
            logger.critical("MongoDB indisponível - fallback não funcionará")

        return redis_ok or mongo_ok

    def disable_redis(self):
        """Desabilita Redis manualmente (degradação controlada)"""
        self._redis_enabled = False
        logger.warning("Redis desabilitado manualmente")

    def enable_redis(self):
        """Habilita Redis novamente"""
        self._redis_enabled = True
        logger.info("Redis habilitado novamente")

    def is_redis_enabled(self) -> bool:
        """Verifica se Redis está habilitado"""
        return self._redis_enabled

    async def start_background_sync(self):
        """Inicia background task para sincronizar MongoDB → Redis"""
        if self._sync_running:
            return

        self._sync_running = True
        asyncio.create_task(self._background_sync_loop())
        logger.info("Background sync iniciado")

    async def stop_background_sync(self):
        """Para background sync"""
        self._sync_running = False
        logger.info("Background sync parado")

    async def _background_sync_loop(self):
        """Loop de background sync"""
        while self._sync_running:
            try:
                if self._redis_enabled:
                    restored = await self._sync_mongodb_to_redis()
                    if restored > 0:
                        self._sync_successes += restored
                        logger.info("Background sync concluído", restored_count=restored)
            except Exception as e:
                self._sync_failures += 1
                logger.error("Erro no background sync", error=str(e))

            await asyncio.sleep(self._sync_interval)

    async def _sync_mongodb_to_redis(self) -> int:
        """
        Sincroniza dados do MongoDB para o Redis.

        Returns:
            Número de chaves restauradas
        """
        try:
            collection = self.mongodb.db[self.FALLBACK_COLLECTION]

            # Buscar dados que ainda não expiraram
            cursor = collection.find({"expires_at": {"$gt": datetime.now(timezone.utc)}})

            restored = 0
            async for doc in cursor:
                key = doc["key"]
                value = doc["value"]

                # Verificar se já existe no Redis
                try:
                    exists = await self.redis.get(key)
                    if not exists:
                        # Restaurar para Redis
                        ttl = None
                        if doc.get("expires_at"):
                            ttl = int(
                                (doc["expires_at"] - datetime.now(timezone.utc)).total_seconds()
                            )
                            if ttl < 0:
                                continue  # Expirado

                        await self.redis.set(key, value, ex=ttl)
                        restored += 1
                except Exception:
                    pass  # Redis ainda indisponível

            return restored

        except Exception as e:
            logger.error("Erro ao sincronizar MongoDB para Redis", error=str(e))
            return 0

    async def _get_from_mongodb(self, key: str) -> Optional[str]:
        """Busca valor do MongoDB"""
        try:
            collection = self.mongodb.db[self.FALLBACK_COLLECTION]
            doc = await collection.find_one({"key": key})

            if doc:
                # Verificar expiração
                if doc.get("expires_at"):
                    if doc["expires_at"] < datetime.now(timezone.utc):
                        # Expirado - deletar e retornar None
                        await collection.delete_one({"key": key})
                        return None

                return doc.get("value")

            return None

        except Exception as e:
            logger.error("Erro ao buscar do MongoDB fallback", key=key, error=str(e))
            return None

    async def _set_to_mongodb(self, key: str, value: str, expires_at: Optional[datetime]) -> bool:
        """Salva valor no MongoDB"""
        try:
            collection = self.mongodb.db[self.FALLBACK_COLLECTION]

            document = {
                "key": key,
                "value": value,
                "updated_at": datetime.now(timezone.utc),
            }

            if expires_at:
                document["expires_at"] = expires_at

            # Upsert
            await collection.update_one({"key": key}, {"$set": document}, upsert=True)

            return True

        except Exception as e:
            logger.error("Erro ao salvar no MongoDB fallback", key=key, error=str(e))
            return False

    async def _delete_from_mongodb(self, key: str) -> bool:
        """Deleta do MongoDB"""
        try:
            collection = self.mongodb.db[self.FALLBACK_COLLECTION]
            await collection.delete_one({"key": key})
            return True
        except Exception as e:
            logger.error("Erro ao deletar do MongoDB fallback", key=key, error=str(e))
            return False

    async def _lrange_from_mongodb(self, key: str, start: int, end: int) -> list:
        """Busca lista do MongoDB"""
        try:
            collection = self.mongodb.db[self.FALLBACK_COLLECTION]
            doc = await collection.find_one({"key": key, "type": "list"})

            if doc and doc.get("items"):
                items = doc["items"]
                # Aplicar range
                if end == -1:
                    return items[start:]
                return items[start : end + 1]

            return []

        except Exception as e:
            logger.error("Erro ao buscar lista do MongoDB fallback", key=key, error=str(e))
            return []

    async def _lpush_to_mongodb(self, key: str, *values) -> int:
        """Adiciona ao início da lista no MongoDB"""
        try:
            collection = self.mongodb.db[self.FALLBACK_COLLECTION]

            # Buscar documento existente
            doc = await collection.find_one({"key": key, "type": "list"})

            items = []
            if doc:
                items = doc.get("items", [])

            # Adicionar novos valores ao início
            for value in reversed(values):
                # Converter bytes para string se necessário
                if isinstance(value, bytes):
                    value = value.decode("utf-8")
                items.insert(0, value)

            # Upsert
            await collection.update_one(
                {"key": key},
                {
                    "$set": {
                        "key": key,
                        "type": "list",
                        "items": items,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )

            return len(items)

        except Exception as e:
            logger.error("Erro ao fazer lpush no MongoDB fallback", key=key, error=str(e))
            return 0

    async def _expire_in_mongodb(self, key: str, seconds: int) -> bool:
        """Define expiração no MongoDB"""
        try:
            collection = self.mongodb.db[self.FALLBACK_COLLECTION]
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)

            await collection.update_one({"key": key}, {"$set": {"expires_at": expires_at}})

            return True

        except Exception as e:
            logger.error("Erro ao definir expiração no MongoDB fallback", key=key, error=str(e))
            return False

    async def _restore_to_redis(self, key: str, value: str):
        """Restaura valor para Redis em background"""
        try:
            # Buscar documento para obter TTL
            collection = self.mongodb.db[self.FALLBACK_COLLECTION]
            doc = await collection.find_one({"key": key})

            ttl = None
            if doc and doc.get("expires_at"):
                ttl = int((doc["expires_at"] - datetime.now(timezone.utc)).total_seconds())
                if ttl < 0:
                    return  # Expirado

            await self.redis.set(key, value, ex=ttl)
            logger.debug("Valor restaurado para Redis", key=key)

        except Exception as e:
            logger.debug("Falha ao restaurar para Redis", key=key, error=str(e))

    def get_metrics(self) -> dict[str, Any]:
        """Retorna métricas do fallback"""
        total_reads = self._redis_hits + self._fallback_hits
        fallback_rate = self._fallback_hits / total_reads if total_reads > 0 else 0.0

        return {
            "redis_enabled": self._redis_enabled,
            "redis_hits": self._redis_hits,
            "fallback_hits": self._fallback_hits,
            "redis_failures": self._redis_failures,
            "sync_successes": self._sync_successes,
            "sync_failures": self._sync_failures,
            "total_reads": total_reads,
            "fallback_rate": fallback_rate,
            "redis_hit_rate": (self._redis_hits / total_reads if total_reads > 0 else 0.0),
        }

    def reset_metrics(self):
        """Reseta métricas"""
        self._redis_hits = 0
        self._fallback_hits = 0
        self._redis_failures = 0
        self._sync_successes = 0
        self._sync_failures = 0
        logger.info("Métricas de fallback resetadas")


class FallbackRedisWrapper:
    """
    Wrapper para cliente Redis que usa FallbackStorage.

    Permite substituir o cliente Redis por este wrapper transparentemente.
    """

    def __init__(self, fallback_storage: FallbackStorage):
        self._fallback = fallback_storage

    async def get(self, key: str) -> Optional[str]:
        return await self._fallback.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        return await self._fallback.set(key, value, ex=ex)

    async def delete(self, key: str) -> bool:
        return await self._fallback.delete(key)

    async def lrange(self, key: str, start: int, end: int) -> list:
        return await self._fallback.lrange(key, start, end)

    async def lpush(self, key: str, *values) -> int:
        return await self._fallback.lpush(key, *values)

    async def expire(self, key: str, seconds: int) -> bool:
        return await self._fallback.expire(key, seconds)

    async def ping(self) -> bool:
        return await self._fallback.ping()

    def close(self):
        """No-op para compatibilidade"""
