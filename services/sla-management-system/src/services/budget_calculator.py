"""
Serviço para cálculo de error budgets.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
import structlog

from ..config.settings import CalculatorSettings
from ..clients.prometheus_client import PrometheusClient
from ..clients.postgresql_client import PostgreSQLClient
from ..clients.redis_client import RedisClient
from ..clients.kafka_producer import KafkaProducerClient
from ..models.slo_definition import SLODefinition
from ..models.error_budget import ErrorBudget, BudgetStatus, BurnRate, BurnRateLevel


class BudgetCalculator:
    """Calculador de error budgets."""

    def __init__(
        self,
        prometheus_client: PrometheusClient,
        postgresql_client: PostgreSQLClient,
        redis_client: RedisClient,
        kafka_producer: KafkaProducerClient,
        settings: CalculatorSettings
    ):
        self.prometheus_client = prometheus_client
        self.postgresql_client = postgresql_client
        self.redis_client = redis_client
        self.kafka_producer = kafka_producer
        self.settings = settings
        self.logger = structlog.get_logger(__name__)
        self._running = False

    async def calculate_budget(self, slo: SLODefinition) -> ErrorBudget:
        """Calcula error budget para um SLO."""
        try:
            start_time = datetime.utcnow()

            # Passo 1: Buscar SLI atual via Prometheus
            sli_value = await self.prometheus_client.calculate_sli(
                slo,
                window_days=slo.window_days
            )

            # Passo 2: Calcular error budget
            error_budget_total = (1 - slo.target) * 100

            if error_budget_total == 0:
                # Target é 100% (1.0), não há error budget disponível
                error_budget_consumed = 0
                error_budget_remaining = 0
                status = BudgetStatus.EXHAUSTED
            else:
                error_actual = (1 - sli_value) * 100
                error_budget_consumed = (error_actual / error_budget_total) * 100
                error_budget_remaining = max(0, 100 - error_budget_consumed)
                # Passo 4: Determinar status
                status = self._determine_status(error_budget_remaining)

            # Passo 3: Calcular burn rates
            burn_rates = await self._calculate_burn_rates(slo.service_name)

            # Passo 5: Contar violações (simplificado)
            violations_count = 0  # TODO: Query Prometheus para alertas

            # Passo 6: Criar objeto ErrorBudget
            window_end = datetime.utcnow()
            window_start = window_end - timedelta(days=slo.window_days)

            budget = ErrorBudget(
                slo_id=slo.slo_id,
                service_name=slo.service_name,
                calculated_at=datetime.utcnow(),
                window_start=window_start,
                window_end=window_end,
                sli_value=sli_value,
                slo_target=slo.target,
                error_budget_total=error_budget_total,
                error_budget_consumed=error_budget_consumed,
                error_budget_remaining=error_budget_remaining,
                status=status,
                burn_rates=burn_rates,
                violations_count=violations_count
            )

            # Passo 7: Persistir no PostgreSQL
            await self.postgresql_client.save_budget(budget)

            # Passo 8: Cachear no Redis
            await self.redis_client.cache_budget(slo.slo_id, budget)

            # Passo 9: Publicar evento Kafka
            await self.kafka_producer.publish_budget_update(budget)

            duration = (datetime.utcnow() - start_time).total_seconds()
            self.logger.info(
                "budget_calculated",
                slo_id=slo.slo_id,
                service=slo.service_name,
                remaining=error_budget_remaining,
                status=status.value,
                duration=duration
            )

            return budget

        except Exception as e:
            self.logger.error(
                "budget_calculation_failed",
                slo_id=slo.slo_id,
                error=str(e)
            )
            raise

    async def calculate_all_budgets(self) -> List[ErrorBudget]:
        """Calcula budget para todos os SLOs ativos."""
        slos = await self.postgresql_client.list_slos(enabled_only=True)

        tasks = [self.calculate_budget(slo) for slo in slos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        budgets = []
        for result in results:
            if isinstance(result, ErrorBudget):
                budgets.append(result)
            elif isinstance(result, Exception):
                self.logger.error("budget_calculation_error", error=str(result))

        return budgets

    async def get_budget(
        self,
        slo_id: str,
        use_cache: bool = True
    ) -> Optional[ErrorBudget]:
        """Busca budget (cache → PostgreSQL → calcula novo)."""
        # Tentar cache
        if use_cache:
            budget = await self.redis_client.get_cached_budget(slo_id)
            if budget:
                return budget

        # Tentar PostgreSQL
        budget = await self.postgresql_client.get_latest_budget(slo_id)
        if budget:
            # Cachear para próximas consultas
            await self.redis_client.cache_budget(slo_id, budget)
            return budget

        # Calcular novo
        slo = await self.postgresql_client.get_slo(slo_id)
        if slo:
            return await self.calculate_budget(slo)

        return None

    async def recalculate_budget(self, slo_id: str) -> ErrorBudget:
        """Força recálculo ignorando cache."""
        await self.redis_client.invalidate_budget(slo_id)
        slo = await self.postgresql_client.get_slo(slo_id)
        if not slo:
            raise ValueError(f"SLO {slo_id} not found")
        return await self.calculate_budget(slo)

    async def run_periodic_calculation(self) -> None:
        """Loop infinito de cálculo periódico."""
        self._running = True
        self.logger.info("periodic_calculation_started")

        while self._running:
            try:
                start_time = datetime.utcnow()
                budgets = await self.calculate_all_budgets()
                duration = (datetime.utcnow() - start_time).total_seconds()

                self.logger.info(
                    "periodic_calculation_completed",
                    budgets_calculated=len(budgets),
                    duration=duration
                )

                await asyncio.sleep(self.settings.calculation_interval_seconds)

            except Exception as e:
                self.logger.error("periodic_calculation_error", error=str(e))
                await asyncio.sleep(self.settings.calculation_interval_seconds)

    def stop_periodic_calculation(self):
        """Para loop periódico."""
        self._running = False
        self.logger.info("periodic_calculation_stopped")

    async def _calculate_burn_rates(self, service_name: str) -> List[BurnRate]:
        """Calcula burn rates para diferentes janelas."""
        burn_rates = []
        windows = [1, 6, 24]  # horas

        for window_hours in windows:
            rate = await self.prometheus_client.calculate_burn_rate(
                service_name,
                window_hours,
                baseline_days=self.settings.error_budget_window_days
            )

            level = self._classify_burn_rate(rate)
            exhaustion_hours = None

            # Estimar tempo até esgotar
            if rate > 0:
                # Simplificado: assumir consumo linear
                exhaustion_hours = (100 / rate) * window_hours

            burn_rates.append(BurnRate(
                window_hours=window_hours,
                rate=rate,
                level=level,
                estimated_exhaustion_hours=exhaustion_hours
            ))

        return burn_rates

    def _classify_burn_rate(self, rate: float) -> BurnRateLevel:
        """Classifica burn rate em níveis."""
        if rate >= self.settings.burn_rate_fast_threshold:
            return BurnRateLevel.CRITICAL
        elif rate >= self.settings.burn_rate_slow_threshold:
            return BurnRateLevel.FAST
        elif rate >= 2:
            return BurnRateLevel.ELEVATED
        else:
            return BurnRateLevel.NORMAL

    def _determine_status(self, remaining_percent: float) -> BudgetStatus:
        """Determina status baseado em remaining %."""
        if remaining_percent > 50:
            return BudgetStatus.HEALTHY
        elif remaining_percent > 20:
            return BudgetStatus.WARNING
        elif remaining_percent > 10:
            return BudgetStatus.CRITICAL
        else:
            return BudgetStatus.EXHAUSTED
