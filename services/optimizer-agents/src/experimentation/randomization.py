# -*- coding: utf-8 -*-
"""
Estrategias de randomizacao para testes A/B.

Implementa tres estrategias de randomizacao:
- RandomRandomizer: Randomizacao simples baseada em hash
- StratifiedRandomizer: Randomizacao estratificada por atributo
- BlockedRandomizer: Randomizacao em blocos balanceados
"""

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


class RandomizationStrategyType(str, Enum):
    """Tipos de estrategia de randomizacao."""
    RANDOM = "RANDOM"
    STRATIFIED = "STRATIFIED"
    BLOCKED = "BLOCKED"


class Group(str, Enum):
    """Grupos de experimento."""
    CONTROL = "control"
    TREATMENT = "treatment"


class BaseRandomizer(ABC):
    """Classe base para randomizadores."""

    def __init__(self, redis_client=None):
        self.redis_client = redis_client

    @abstractmethod
    async def assign(
        self,
        entity_id: str,
        experiment_id: str,
        traffic_split: float = 0.5,
        **kwargs,
    ) -> Group:
        """
        Atribuir entidade a um grupo.

        Args:
            entity_id: Identificador unico da entidade
            experiment_id: Identificador do experimento
            traffic_split: Proporcao de trafego para treatment (0.0 a 1.0)

        Returns:
            Grupo atribuido (control ou treatment)
        """
        pass

    async def _get_cached_assignment(self, experiment_id: str, entity_id: str) -> Optional[Group]:
        """Recuperar atribuicao cacheada do Redis."""
        if not self.redis_client:
            return None

        key = f"ab_test:{experiment_id}:assignments:{entity_id}"
        try:
            cached = await self.redis_client.get(key)
            if cached:
                data = json.loads(cached)
                return Group(data["group"])
        except Exception as e:
            logger.warning("failed_to_get_cached_assignment", error=str(e))

        return None

    async def _cache_assignment(
        self,
        experiment_id: str,
        entity_id: str,
        group: Group,
        ttl_seconds: int = 604800,  # 7 dias
    ) -> None:
        """Armazenar atribuicao no Redis."""
        if not self.redis_client:
            return

        key = f"ab_test:{experiment_id}:assignments:{entity_id}"
        data = {
            "group": group.value,
            "assigned_at": datetime.utcnow().isoformat(),
        }

        try:
            await self.redis_client.setex(key, ttl_seconds, json.dumps(data))
        except Exception as e:
            logger.warning("failed_to_cache_assignment", error=str(e))


class RandomRandomizer(BaseRandomizer):
    """
    Randomizacao simples baseada em hash determinístico.

    Usa hash do entity_id + experiment_id para garantir
    atribuicoes consistentes e deterministicas.
    """

    async def assign(
        self,
        entity_id: str,
        experiment_id: str,
        traffic_split: float = 0.5,
        **kwargs,
    ) -> Group:
        """
        Atribuir entidade usando hash deterministico.

        A atribuicao e baseada em:
        hash(entity_id + experiment_id) % 100 < traffic_split * 100
        """
        # Verificar cache primeiro
        cached = await self._get_cached_assignment(experiment_id, entity_id)
        if cached:
            return cached

        # Calcular hash deterministico
        hash_input = f"{entity_id}:{experiment_id}"
        hash_value = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        bucket = hash_value % 100

        # Atribuir grupo baseado no traffic_split
        group = Group.TREATMENT if bucket < (traffic_split * 100) else Group.CONTROL

        # Cache no Redis
        await self._cache_assignment(experiment_id, entity_id, group)

        logger.debug(
            "random_assignment",
            entity_id=entity_id,
            experiment_id=experiment_id,
            group=group.value,
            bucket=bucket,
        )

        return group


class StratifiedRandomizer(BaseRandomizer):
    """
    Randomizacao estratificada por atributo.

    Mantem balanceamento dentro de cada estrato (ex: regiao, tipo de usuario).
    Garante que cada estrato tenha distribuicao similar entre grupos.
    """

    async def assign(
        self,
        entity_id: str,
        experiment_id: str,
        traffic_split: float = 0.5,
        strata_key: str = "default",
        **kwargs,
    ) -> Group:
        """
        Atribuir entidade usando estratificacao.

        Args:
            strata_key: Chave do estrato (ex: "region:us-east", "user_type:premium")
        """
        # Verificar cache primeiro
        cached = await self._get_cached_assignment(experiment_id, entity_id)
        if cached:
            return cached

        # Obter contadores do estrato
        control_count, treatment_count = await self._get_strata_counts(experiment_id, strata_key)

        # Calcular proporcao desejada
        total = control_count + treatment_count
        if total == 0:
            # Primeiro participante do estrato - usar randomizacao simples
            hash_input = f"{entity_id}:{experiment_id}:{strata_key}"
            hash_value = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
            group = Group.TREATMENT if (hash_value % 100) < (traffic_split * 100) else Group.CONTROL
        else:
            # Calcular proporcao atual de treatment
            current_treatment_ratio = treatment_count / total
            target_treatment_ratio = traffic_split

            # Se treatment esta subrepresentado, atribuir ao treatment
            if current_treatment_ratio < target_treatment_ratio:
                group = Group.TREATMENT
            else:
                group = Group.CONTROL

        # Atualizar contadores do estrato
        await self._increment_strata_count(experiment_id, strata_key, group)

        # Cache no Redis
        await self._cache_assignment(experiment_id, entity_id, group)

        logger.debug(
            "stratified_assignment",
            entity_id=entity_id,
            experiment_id=experiment_id,
            strata_key=strata_key,
            group=group.value,
            control_count=control_count,
            treatment_count=treatment_count,
        )

        return group

    async def _get_strata_counts(self, experiment_id: str, strata_key: str) -> Tuple[int, int]:
        """Obter contadores do estrato."""
        if not self.redis_client:
            return 0, 0

        control_key = f"ab_test:{experiment_id}:strata:{strata_key}:control_count"
        treatment_key = f"ab_test:{experiment_id}:strata:{strata_key}:treatment_count"

        try:
            control_count = await self.redis_client.get(control_key)
            treatment_count = await self.redis_client.get(treatment_key)

            return (
                int(control_count) if control_count else 0,
                int(treatment_count) if treatment_count else 0,
            )
        except Exception as e:
            logger.warning("failed_to_get_strata_counts", error=str(e))
            return 0, 0

    async def _increment_strata_count(self, experiment_id: str, strata_key: str, group: Group) -> None:
        """Incrementar contador do estrato."""
        if not self.redis_client:
            return

        key = f"ab_test:{experiment_id}:strata:{strata_key}:{group.value}_count"

        try:
            await self.redis_client.incr(key)
        except Exception as e:
            logger.warning("failed_to_increment_strata_count", error=str(e))


class BlockedRandomizer(BaseRandomizer):
    """
    Randomizacao em blocos balanceados.

    Garante que dentro de cada bloco de tamanho fixo,
    a distribuicao seja exatamente balanceada.
    Util para experimentos com poucos participantes.
    """

    async def assign(
        self,
        entity_id: str,
        experiment_id: str,
        traffic_split: float = 0.5,
        block_size: int = 10,
        **kwargs,
    ) -> Group:
        """
        Atribuir entidade usando blocos balanceados.

        Args:
            block_size: Tamanho do bloco (deve ser multiplo de 2 para 50/50)
        """
        # Verificar cache primeiro
        cached = await self._get_cached_assignment(experiment_id, entity_id)
        if cached:
            return cached

        # Obter ou criar bloco atual
        block = await self._get_or_create_block(experiment_id, block_size, traffic_split)

        # Obter proximo slot do bloco
        group = await self._get_next_slot(experiment_id, block)

        # Cache no Redis
        await self._cache_assignment(experiment_id, entity_id, group)

        logger.debug(
            "blocked_assignment",
            entity_id=entity_id,
            experiment_id=experiment_id,
            group=group.value,
            block_size=block_size,
        )

        return group

    async def _get_or_create_block(
        self,
        experiment_id: str,
        block_size: int,
        traffic_split: float,
    ) -> List[Group]:
        """Obter ou criar bloco de atribuicoes."""
        if not self.redis_client:
            # Sem Redis, criar bloco novo
            return self._create_shuffled_block(block_size, traffic_split)

        block_key = f"ab_test:{experiment_id}:current_block"

        try:
            cached_block = await self.redis_client.get(block_key)
            if cached_block:
                data = json.loads(cached_block)
                if data:
                    return [Group(g) for g in data]
        except Exception as e:
            logger.warning("failed_to_get_block", error=str(e))

        # Criar novo bloco
        new_block = self._create_shuffled_block(block_size, traffic_split)
        await self._save_block(experiment_id, new_block)

        return new_block

    def _create_shuffled_block(self, block_size: int, traffic_split: float) -> List[Group]:
        """Criar bloco embaralhado."""
        import random

        treatment_count = int(block_size * traffic_split)
        control_count = block_size - treatment_count

        block = (
            [Group.TREATMENT] * treatment_count +
            [Group.CONTROL] * control_count
        )

        # Embaralhar usando seed baseado em timestamp para variabilidade
        random.shuffle(block)

        return block

    async def _get_next_slot(self, experiment_id: str, block: List[Group]) -> Group:
        """Obter proximo slot do bloco."""
        if not block:
            return Group.CONTROL

        group = block.pop(0)

        # Atualizar bloco no Redis
        await self._save_block(experiment_id, block)

        return group

    async def _save_block(self, experiment_id: str, block: List[Group]) -> None:
        """Salvar bloco no Redis."""
        if not self.redis_client:
            return

        block_key = f"ab_test:{experiment_id}:current_block"

        try:
            block_data = [g.value for g in block]
            await self.redis_client.setex(block_key, 86400, json.dumps(block_data))  # 24h TTL
        except Exception as e:
            logger.warning("failed_to_save_block", error=str(e))


def get_randomizer(
    strategy: RandomizationStrategyType,
    redis_client=None,
) -> BaseRandomizer:
    """
    Factory para obter randomizador baseado na estrategia.

    Args:
        strategy: Tipo de estrategia de randomizacao
        redis_client: Cliente Redis para caching

    Returns:
        Instancia do randomizador apropriado
    """
    randomizers = {
        RandomizationStrategyType.RANDOM: RandomRandomizer,
        RandomizationStrategyType.STRATIFIED: StratifiedRandomizer,
        RandomizationStrategyType.BLOCKED: BlockedRandomizer,
    }

    randomizer_class = randomizers.get(strategy, RandomRandomizer)
    return randomizer_class(redis_client=redis_client)
