"""
AffinityTracker - Rastreia alocações para affinity/anti-affinity de tickets.

Mantém cache Redis de alocações por plan_id, intent_id e tickets críticos
para permitir co-location inteligente e distribuição de fault tolerance.
"""
import time
from typing import Dict, Optional, Set
import structlog

from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics

logger = structlog.get_logger(__name__)


class AffinityTracker:
    """
    Rastreador de afinidade para alocação de tickets.

    Responsável por:
    - Rastrear alocações por plan_id (data locality)
    - Rastrear alocações por intent_id (workflow affinity)
    - Rastrear tickets críticos por worker (anti-affinity)
    - Fail-open: Retornar dados vazios se Redis falhar
    """

    # Prefixos de chave Redis
    KEY_PREFIX_PLAN = 'affinity:plan:'
    KEY_PREFIX_INTENT = 'affinity:intent:'
    KEY_PREFIX_CRITICAL = 'affinity:worker:critical:'

    def __init__(
        self,
        redis_client,
        config: OrchestratorSettings,
        metrics: OrchestratorMetrics
    ):
        """
        Inicializa o tracker.

        Args:
            redis_client: Cliente Redis assíncrono
            config: Configurações do orchestrator
            metrics: Instância de métricas
        """
        self.redis_client = redis_client
        self.config = config
        self.metrics = metrics
        self.logger = logger.bind(component='affinity_tracker')

        # Configuração de TTL (default 4 horas, alinhado com SLA deadline)
        self.cache_ttl_seconds = getattr(
            config, 'scheduler_affinity_cache_ttl_seconds', 14400
        )

        # Risk bands e priorities que ativam anti-affinity
        self.anti_affinity_risk_bands = getattr(
            config, 'scheduler_affinity_anti_affinity_risk_bands',
            ['critical', 'high']
        )
        self.anti_affinity_priorities = getattr(
            config, 'scheduler_affinity_anti_affinity_priorities',
            ['CRITICAL', 'HIGH']
        )

    async def get_plan_allocations(self, plan_id: Optional[str]) -> Dict[str, int]:
        """
        Retorna contagem de tickets alocados por worker para um plan_id.

        Args:
            plan_id: ID do plano

        Returns:
            Dict {worker_id: ticket_count} ou {} se Redis falhar
        """
        if not plan_id or not self.redis_client:
            return {}

        start_time = time.time()
        key = f'{self.KEY_PREFIX_PLAN}{plan_id}'

        try:
            result = await self.redis_client.hgetall(key)

            duration_ms = (time.time() - start_time) * 1000
            self.metrics.record_affinity_cache_operation('get_plan', 'success')

            # Converter valores para int
            allocations = {k: int(v) for k, v in result.items()} if result else {}

            self.logger.debug(
                'plan_allocations_retrieved',
                plan_id=plan_id,
                workers_count=len(allocations),
                duration_ms=round(duration_ms, 2)
            )

            return allocations

        except Exception as e:
            self.logger.warning(
                'plan_allocations_fetch_failed',
                plan_id=plan_id,
                error=str(e)
            )
            self.metrics.record_affinity_cache_operation('get_plan', 'failure')
            return {}

    async def get_intent_allocations(self, intent_id: Optional[str]) -> Dict[str, int]:
        """
        Retorna contagem de tickets alocados por worker para um intent_id.

        Args:
            intent_id: ID do intent

        Returns:
            Dict {worker_id: ticket_count} ou {} se Redis falhar
        """
        if not intent_id or not self.redis_client:
            return {}

        start_time = time.time()
        key = f'{self.KEY_PREFIX_INTENT}{intent_id}'

        try:
            result = await self.redis_client.hgetall(key)

            duration_ms = (time.time() - start_time) * 1000
            self.metrics.record_affinity_cache_operation('get_intent', 'success')

            allocations = {k: int(v) for k, v in result.items()} if result else {}

            self.logger.debug(
                'intent_allocations_retrieved',
                intent_id=intent_id,
                workers_count=len(allocations),
                duration_ms=round(duration_ms, 2)
            )

            return allocations

        except Exception as e:
            self.logger.warning(
                'intent_allocations_fetch_failed',
                intent_id=intent_id,
                error=str(e)
            )
            self.metrics.record_affinity_cache_operation('get_intent', 'failure')
            return {}

    async def get_critical_tickets_on_worker(self, worker_id: str) -> Set[str]:
        """
        Retorna set de ticket_ids críticos alocados em um worker.

        Args:
            worker_id: ID do worker

        Returns:
            Set de ticket_ids ou set vazio se Redis falhar
        """
        if not worker_id or not self.redis_client:
            return set()

        start_time = time.time()
        key = f'{self.KEY_PREFIX_CRITICAL}{worker_id}'

        try:
            result = await self.redis_client.smembers(key)

            duration_ms = (time.time() - start_time) * 1000
            self.metrics.record_affinity_cache_operation('get_critical', 'success')

            tickets = set(result) if result else set()

            self.logger.debug(
                'critical_tickets_retrieved',
                worker_id=worker_id,
                tickets_count=len(tickets),
                duration_ms=round(duration_ms, 2)
            )

            return tickets

        except Exception as e:
            self.logger.warning(
                'critical_tickets_fetch_failed',
                worker_id=worker_id,
                error=str(e)
            )
            self.metrics.record_affinity_cache_operation('get_critical', 'failure')
            return set()

    async def record_allocation(self, ticket: Dict, worker_id: str) -> bool:
        """
        Registra uma alocação de ticket para um worker.

        Atualiza:
        - Contagem de tickets por plan_id
        - Contagem de tickets por intent_id
        - Set de tickets críticos (se aplicável)

        Args:
            ticket: Ticket sendo alocado
            worker_id: ID do worker que receberá o ticket

        Returns:
            True se registro bem-sucedido, False caso contrário
        """
        if not ticket or not worker_id or not self.redis_client:
            return False

        start_time = time.time()
        plan_id = ticket.get('plan_id')
        intent_id = ticket.get('intent_id')
        ticket_id = ticket.get('ticket_id', 'unknown')
        risk_band = ticket.get('risk_band', '')
        priority = ticket.get('priority', '')

        try:
            # Pipeline para operações atômicas
            pipe = self.redis_client.pipeline()

            # Incrementar contagem por plan_id
            if plan_id:
                plan_key = f'{self.KEY_PREFIX_PLAN}{plan_id}'
                pipe.hincrby(plan_key, worker_id, 1)
                pipe.expire(plan_key, self.cache_ttl_seconds)

            # Incrementar contagem por intent_id
            if intent_id:
                intent_key = f'{self.KEY_PREFIX_INTENT}{intent_id}'
                pipe.hincrby(intent_key, worker_id, 1)
                pipe.expire(intent_key, self.cache_ttl_seconds)

            # Adicionar ao set de críticos se aplicável
            is_critical = (
                risk_band.lower() in [rb.lower() for rb in self.anti_affinity_risk_bands] or
                priority.upper() in [p.upper() for p in self.anti_affinity_priorities]
            )

            if is_critical:
                critical_key = f'{self.KEY_PREFIX_CRITICAL}{worker_id}'
                pipe.sadd(critical_key, ticket_id)
                pipe.expire(critical_key, self.cache_ttl_seconds)

            await pipe.execute()

            duration_ms = (time.time() - start_time) * 1000
            self.metrics.record_affinity_cache_operation('record', 'success')

            self.logger.debug(
                'allocation_recorded',
                ticket_id=ticket_id,
                worker_id=worker_id,
                plan_id=plan_id,
                intent_id=intent_id,
                is_critical=is_critical,
                duration_ms=round(duration_ms, 2)
            )

            return True

        except Exception as e:
            self.logger.warning(
                'allocation_record_failed',
                ticket_id=ticket_id,
                worker_id=worker_id,
                error=str(e)
            )
            self.metrics.record_affinity_cache_operation('record', 'failure')
            return False

    async def cleanup_completed_ticket(
        self,
        ticket_id: str,
        plan_id: Optional[str],
        intent_id: Optional[str],
        worker_id: str
    ) -> bool:
        """
        Remove ticket completado do cache de affinity.

        Args:
            ticket_id: ID do ticket completado
            plan_id: ID do plano (opcional)
            intent_id: ID do intent (opcional)
            worker_id: ID do worker que executou

        Returns:
            True se cleanup bem-sucedido, False caso contrário
        """
        if not ticket_id or not worker_id or not self.redis_client:
            return False

        start_time = time.time()

        try:
            pipe = self.redis_client.pipeline()

            # Decrementar contagem por plan_id
            if plan_id:
                plan_key = f'{self.KEY_PREFIX_PLAN}{plan_id}'
                pipe.hincrby(plan_key, worker_id, -1)

            # Decrementar contagem por intent_id
            if intent_id:
                intent_key = f'{self.KEY_PREFIX_INTENT}{intent_id}'
                pipe.hincrby(intent_key, worker_id, -1)

            # Remover do set de críticos
            critical_key = f'{self.KEY_PREFIX_CRITICAL}{worker_id}'
            pipe.srem(critical_key, ticket_id)

            await pipe.execute()

            duration_ms = (time.time() - start_time) * 1000
            self.metrics.record_affinity_cache_operation('cleanup', 'success')

            self.logger.debug(
                'ticket_cleanup_completed',
                ticket_id=ticket_id,
                worker_id=worker_id,
                plan_id=plan_id,
                intent_id=intent_id,
                duration_ms=round(duration_ms, 2)
            )

            return True

        except Exception as e:
            self.logger.warning(
                'ticket_cleanup_failed',
                ticket_id=ticket_id,
                worker_id=worker_id,
                error=str(e)
            )
            self.metrics.record_affinity_cache_operation('cleanup', 'failure')
            return False

    def is_ticket_critical(self, ticket: Dict) -> bool:
        """
        Verifica se um ticket deve ser tratado como crítico para anti-affinity.

        Args:
            ticket: Ticket a verificar

        Returns:
            True se ticket é crítico, False caso contrário
        """
        risk_band = ticket.get('risk_band', '')
        priority = ticket.get('priority', '')

        return (
            risk_band.lower() in [rb.lower() for rb in self.anti_affinity_risk_bands] or
            priority.upper() in [p.upper() for p in self.anti_affinity_priorities]
        )
