"""
Cliente Redis para gerenciar feromônios digitais COM FALLBACK MONGODB.

Gap P0-3: State Divergence - Redis primário sem fallback MongoDB

Implementa fallback para MongoDB quando Redis falha:
- READ: Tenta Redis → falha → busca MongoDB → retorna
- WRITE: Escreve em AMBOS (Redis + MongoDB)
- BACKGROUND: Task sincroniza MongoDB → Redis
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

import structlog
from src.models.pheromone_signal import PheromoneSignal, PheromoneType

from neural_hive_domain import DomainMapper, UnifiedDomain

logger = structlog.get_logger()


class PheromoneClient:
    """
    Cliente Redis para gerenciar feromônios digitais COM FALLBACK MONGODB.

    Gap P0-3: Implementa fallback para MongoDB quando Redis falha.
    """

    def __init__(self, redis_client, config, fallback_storage=None):
        """
        Inicializa cliente de feromônios.

        Args:
            redis_client: Cliente Redis async ou FallbackRedisWrapper
            config: Configurações do consensus-engine
            fallback_storage: Opcional, instância de FallbackStorage
        """
        self.redis = redis_client
        self.config = config
        self._fallback_storage = fallback_storage
        self._using_fallback = fallback_storage is not None

        # Collection MongoDB para feromônios
        self._pheromone_collection = "pheromone_signals"

        logger.info(
            "Pheromone client inicializado",
            fallback_enabled=self._using_fallback,
        )

    async def publish_pheromone(
        self,
        specialist_type: str,
        domain: Union[str, UnifiedDomain],
        pheromone_type: PheromoneType,
        strength: float,
        plan_id: str,
        intent_id: str,
        decision_id: Optional[str] = None,
    ) -> str:
        """
        Publica feromônio no Redis usando chave padronizada via DomainMapper.

        Gap P0-3: Escreve em AMBOS Redis e MongoDB.
        """
        # Criar PheromoneSignal
        signal = PheromoneSignal(
            specialist_type=specialist_type,
            domain=domain,
            pheromone_type=pheromone_type,
            strength=strength,
            plan_id=plan_id,
            intent_id=intent_id,
            decision_id=decision_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.config.pheromone_ttl),
            decay_rate=self.config.pheromone_decay_rate,
        )

        # Salvar no Redis com TTL
        key = signal.get_redis_key()
        signal_json = json.dumps(signal.model_dump(mode="json"))

        # Gap P0-3: Escrever em AMBOS
        redis_ok = False
        mongo_ok = False

        # 1. Escrever no Redis
        try:
            await self.redis.set(key, signal_json, ex=self.config.pheromone_ttl)
            redis_ok = True
        except Exception as e:
            self._log_redis_failure("publish_pheromone", key, error=str(e))

        # 2. Adicionar à lista de feromônios ativos
        list_key = f"pheromones:active:{specialist_type}:{domain}"
        try:
            await self.redis.lpush(list_key, signal.signal_id)
            await self.redis.expire(list_key, self.config.pheromone_ttl)
        except Exception as e:
            self._log_redis_failure("lpush_active_list", list_key, error=str(e))

        # 3. Persistir no MongoDB (Gap P0-3)
        if self._fallback_storage:
            try:
                await self._save_pheromone_to_mongodb(signal)
                mongo_ok = True
            except Exception as e:
                logger.error("Erro ao salvar feromônio no MongoDB", signal_id=signal.signal_id, error=str(e))

        logger.info(
            "Feromônio publicado",
            specialist_type=specialist_type,
            domain=domain,
            pheromone_type=pheromone_type.value,
            strength=strength,
            signal_id=signal.signal_id,
            redis_ok=redis_ok,
            mongo_ok=mongo_ok,
        )

        return signal.signal_id

    async def get_pheromone_strength(
        self, specialist_type: str, domain: Union[str, UnifiedDomain], pheromone_type: PheromoneType
    ) -> float:
        """
        Consulta força atual de feromônio (com decay) usando chave padronizada.

        Filtra por specialist_type usando a lista de feromônios ativos para
        garantir que apenas sinais do especialista correto sejam agregados.

        Gap P0-3: Com fallback para MongoDB.
        """
        # Normalizar domain para UnifiedDomain se necessário
        if isinstance(domain, str):
            normalized_domain = DomainMapper.normalize(domain, "intent_envelope")
        else:
            normalized_domain = domain

        # Usar a lista de feromônios ativos para filtrar por specialist_type
        list_key = f"pheromones:active:{specialist_type}:{normalized_domain.value}"

        # Obter signal_ids do especialista específico
        signal_ids = await self._get_active_signal_ids(list_key)

        if not signal_ids:
            return 0.0

        # Agregar força apenas dos feromônios do especialista específico
        total_strength = 0.0
        count = 0

        for signal_id in signal_ids:
            # Decodificar signal_id se necessário (Redis pode retornar bytes)
            if isinstance(signal_id, bytes):
                signal_id = signal_id.decode("utf-8")

            # Construir a chave Redis usando DomainMapper
            key = DomainMapper.to_pheromone_key(
                domain=normalized_domain,
                layer="consensus",
                pheromone_type=pheromone_type.value,
                id=signal_id,
            )

            signal = await self._get_pheromone_signal(key, signal_id)
            if signal and signal.pheromone_type == pheromone_type:
                total_strength += signal.calculate_current_strength()
                count += 1

        return total_strength / count if count > 0 else 0.0

    async def get_aggregated_pheromone(
        self, specialist_type: str, domain: Union[str, UnifiedDomain]
    ) -> dict[str, float]:
        """
        Agrega feromônios de todos os tipos para um especialista + domínio.

        Gap P0-3: Com fallback para MongoDB.
        """
        success_strength = await self.get_pheromone_strength(
            specialist_type, domain, PheromoneType.SUCCESS
        )
        failure_strength = await self.get_pheromone_strength(
            specialist_type, domain, PheromoneType.FAILURE
        )
        warning_strength = await self.get_pheromone_strength(
            specialist_type, domain, PheromoneType.WARNING
        )

        # Calcular força líquida (success - failure - warning*0.5)
        net_strength = success_strength - failure_strength - (warning_strength * 0.5)
        net_strength = max(0.0, min(1.0, net_strength))  # Normalizar

        return {
            "success": success_strength,
            "failure": failure_strength,
            "warning": warning_strength,
            "net_strength": net_strength,
        }

    async def calculate_dynamic_weight(
        self, specialist_type: str, domain: Union[str, UnifiedDomain], base_weight: float = 0.2
    ) -> float:
        """
        Calcula peso dinâmico baseado em feromônios.

        Gap P0-3: Com fallback para MongoDB.
        """
        pheromones = await self.get_aggregated_pheromone(specialist_type, domain)

        # Ajustar peso base com feromônios
        adjusted_weight = base_weight * (1.0 + pheromones["net_strength"])

        # Normalizar para [0.05, 0.4] (evitar pesos extremos)
        adjusted_weight = max(0.05, min(0.4, adjusted_weight))

        logger.debug(
            "Peso dinâmico calculado",
            specialist_type=specialist_type,
            domain=domain,
            base_weight=base_weight,
            net_strength=pheromones["net_strength"],
            adjusted_weight=adjusted_weight,
        )

        return adjusted_weight

    async def cleanup_expired_pheromones(self):
        """
        Limpa feromônios expirados (executar periodicamente).

        Gap P0-3: Limpa AMBOS Redis e MongoDB.
        """
        # Redis TTL já cuida da expiração automática
        # MongoDB precisa de limpeza manual via TTL index

    async def _get_active_signal_ids(self, list_key: str) -> list:
        """
        Obtém lista de signal_ids ativos.

        Gap P0-3: Com fallback para MongoDB.
        """
        try:
            signal_ids = await self.redis.lrange(list_key, 0, -1)
            return signal_ids
        except Exception as e:
            self._log_redis_failure("lrange_active_list", list_key, error=str(e))

            # Gap P0-3: Fallback para MongoDB
            if self._fallback_storage:
                return await self._get_active_signal_ids_from_mongodb(list_key)

            return []

    async def _get_pheromone_signal(self, key: str, signal_id: str) -> Optional[PheromoneSignal]:
        """
        Obtém sinal de feromônio.

        Gap P0-3: Com fallback para MongoDB.
        """
        try:
            signal_json = await self.redis.get(key)
            if signal_json:
                signal_data = json.loads(signal_json)
                return PheromoneSignal(**signal_data)
        except Exception as e:
            self._log_redis_failure("get_pheromone_signal", key, error=str(e))

        # Gap P0-3: Fallback para MongoDB
        if self._fallback_storage:
            return await self._get_pheromone_signal_from_mongodb(signal_id)

        return None

    async def _save_pheromone_to_mongodb(self, signal: PheromoneSignal):
        """
        Salva feromônio no MongoDB para persistência.

        Gap P0-3: Implementação do fallback.
        """
        if not self._fallback_storage:
            return

        try:
            collection = self._fallback_storage.mongodb.db[self._pheromone_collection]

            document = signal.model_dump(mode="json")
            document["_id"] = signal.signal_id
            document["immutable"] = True

            await collection.update_one(
                {"signal_id": signal.signal_id},
                {"$set": document},
                upsert=True
            )

            logger.debug("Feromônio salvo no MongoDB", signal_id=signal.signal_id)

        except Exception as e:
            logger.error("Erro ao salvar feromônio no MongoDB", signal_id=signal.signal_id, error=str(e))
            raise

    async def _get_active_signal_ids_from_mongodb(self, list_key: str) -> list:
        """
        Obtém signal_ids do MongoDB como fallback.

        Gap P0-3: Implementação do fallback.
        """
        if not self._fallback_storage:
            return []

        try:
            # Parse list_key para obter specialist_type e domain
            # Formato: pheromones:active:{specialist_type}:{domain}
            parts = list_key.split(":")
            if len(parts) < 4:
                return []

            specialist_type = parts[2]
            domain = parts[3]

            collection = self._fallback_storage.mongodb.db[self._pheromone_collection]

            # Buscar sinais não expirados para este especialista/domínio
            cursor = collection.find({
                "specialist_type": specialist_type,
                "domain": domain,
                "expires_at": {"$gt": datetime.now(timezone.utc)},
            })

            signal_ids = []
            async for doc in cursor:
                signal_ids.append(doc["signal_id"])

            if signal_ids:
                logger.info(
                    "Fallback MongoDB: signal_ids recuperados",
                    list_key=list_key,
                    count=len(signal_ids),
                )

            return signal_ids

        except Exception as e:
            logger.error("Erro ao buscar signal_ids do MongoDB fallback", list_key=list_key, error=str(e))
            return []

    async def _get_pheromone_signal_from_mongodb(self, signal_id: str) -> Optional[PheromoneSignal]:
        """
        Obtém sinal do MongoDB como fallback.

        Gap P0-3: Implementação do fallback.
        """
        if not self._fallback_storage:
            return None

        try:
            collection = self._fallback_storage.mongodb.db[self._pheromone_collection]

            doc = await collection.find_one({"signal_id": signal_id})
            if doc:
                # Verificar expiração
                if doc.get("expires_at"):
                    if doc["expires_at"] < datetime.now(timezone.utc):
                        return None

                return PheromoneSignal(**doc)

            return None

        except Exception as e:
            logger.error("Erro ao buscar sinal do MongoDB fallback", signal_id=signal_id, error=str(e))
            return None

    def _log_redis_failure(self, operation: str, key: str, error: str):
        """Log de falha Redis Gap P0-3"""
        if self._fallback_storage:
            logger.warning(
                f"Pheromone {operation}: Redis falhou, usando MongoDB fallback",
                key=key,
                error=error,
            )
        else:
            logger.warning(
                f"Pheromone {operation}: Redis falhou",
                key=key,
                error=error,
            )
