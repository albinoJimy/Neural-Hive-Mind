"""
Motor de alertas proativos para SLA Management System.

Monitora continuamente SLOs e error budgets, detectando anomalias
e despachando alertas para múltiplos canais.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

import structlog

from ..clients.postgresql_client import PostgreSQLClient
from ..clients.redis_client import RedisClient
from ..models.alert_rule import (
    Alert,
    AlertChannel,
    AlertCondition,
    AlertConditionType,
    AlertRule,
    AlertSeverity,
    AlertStatistics,
)
from ..models.error_budget import BudgetStatus, ErrorBudget
from .alert_dispatcher import AlertDispatcher

logger = structlog.get_logger(__name__)


class AlertEngine:
    """
    Motor de alertas proativos.

    Monitora continuamente os SLOs e error budgets, avaliando regras
    de alerta e despachando notificações quando condições são atendidas.
    """

    def __init__(
        self,
        postgresql_client: PostgreSQLClient,
        redis_client: RedisClient,
        alert_dispatcher: AlertDispatcher,
        check_interval_seconds: int = 60,
        retention_days: int = 30,
    ):
        self.postgresql_client = postgresql_client
        self.redis_client = redis_client
        self.alert_dispatcher = alert_dispatcher
        self.check_interval_seconds = check_interval_seconds
        self.retention_days = retention_days

        self.logger = logger
        self._running = False
        self._monitoring_task: Optional[asyncio.Task] = None

        # Cache de regras e alertas
        self._rules: dict[str, AlertRule] = {}
        self._last_alert_times: dict[str, datetime] = {}

    async def start(self):
        """Inicia o motor de alertas."""
        if self._running:
            self.logger.warning("alert_engine_already_running")
            return

        self._running = True
        self.logger.info("alert_engine_starting")

        # Carregar regras do banco
        await self._load_rules()

        # Iniciar monitoramento em background
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())

        self.logger.info("alert_engine_started")

    async def stop(self):
        """Para o motor de alertas."""
        if not self._running:
            return

        self._running = False
        self.logger.info("alert_engine_stopping")

        # Cancelar tarefa de monitoramento
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        self.logger.info("alert_engine_stopped")

    async def _monitoring_loop(self):
        """Loop de monitoramento contínuo."""
        self.logger.info("monitoring_loop_started")

        while self._running:
            try:
                start_time = datetime.now(UTC)

                # Executar ciclo de monitoramento
                await self._monitoring_cycle()

                # Calcular duração e esperar próximo ciclo
                duration = (datetime.now(UTC) - start_time).total_seconds()
                sleep_time = max(0, self.check_interval_seconds - duration)

                await asyncio.sleep(sleep_time)

            except Exception as e:
                self.logger.error("monitoring_cycle_error", error=str(e))
                await asyncio.sleep(self.check_interval_seconds)

    async def _monitoring_cycle(self):
        """Executa um ciclo completo de monitoramento."""
        # Buscar todos os SLOs ativos
        slos = await self.postgresql_client.list_slos(enabled_only=True)

        if not slos:
            self.logger.debug("no_active_slos_to_monitor")
            return

        # Buscar budgets atuais (com cache se disponível)
        budgets = []
        for slo in slos:
            try:
                budget = await self.redis_client.get_cached_budget(slo.slo_id)
                if not budget:
                    budget = await self.postgresql_client.get_latest_budget(slo.slo_id)
                if budget:
                    budgets.append(budget)
            except Exception as e:
                self.logger.warning("budget_fetch_failed", slo_id=slo.slo_id, error=str(e))

        # Avaliar regras para cada budget
        for budget in budgets:
            await self._evaluate_rules_for_budget(budget)

        # Limpar alertas antigos
        await self._cleanup_old_alerts()

    async def _evaluate_rules_for_budget(self, budget: ErrorBudget):
        """Avalia todas as regras aplicáveis a um budget."""
        for rule_id, rule in self._rules.items():
            if not rule.enabled:
                continue

            # Verificar filtro de service/slo_id
            if rule.condition.service_name and rule.condition.service_name != budget.service_name:
                continue
            if rule.condition.slo_id and rule.condition.slo_id != budget.slo_id:
                continue

            # Verificar cooldown
            if await self._is_in_cooldown(rule_id):
                continue

            # Avaliar condição
            should_alert = await self._evaluate_condition(rule.condition, budget)

            if should_alert:
                await self._trigger_alert(rule, budget)

    async def _evaluate_condition(self, condition: AlertCondition, budget: ErrorBudget) -> bool:
        """Avalia uma condição de alerta."""
        try:
            if condition.condition_type == AlertConditionType.BUDGET_BELOW_THRESHOLD:
                # Budget restante abaixo do threshold
                return budget.error_budget_remaining < condition.threshold

            elif condition.condition_type == AlertConditionType.BURN_RATE_EXCEEDS:
                # Burn rate acima do threshold
                window_hours = condition.window_hours or 1
                for burn_rate in budget.burn_rates:
                    if burn_rate.window_hours == window_hours:
                        return burn_rate.rate > condition.threshold
                return False

            elif condition.condition_type == AlertConditionType.SLO_VIOLATION_COUNT:
                # Número de violações acima do threshold
                return budget.violations_count > int(condition.threshold)

            elif condition.condition_type == AlertConditionType.STATUS_CHANGE:
                # Status mudou para algo crítico
                critical_statuses = [BudgetStatus.CRITICAL, BudgetStatus.EXHAUSTED]
                return budget.status in critical_statuses

            elif condition.condition_type == AlertConditionType.PREDICTIVE_EXHAUSTION:
                # Previsão de esgotamento baseado em burn rate
                for burn_rate in budget.burn_rates:
                    if burn_rate.estimated_exhaustion_hours:
                        # Se vai esgotar em menos que o threshold (em horas)
                        return burn_rate.estimated_exhaustion_hours < condition.threshold
                return False

            return False

        except Exception as e:
            self.logger.error(
                "condition_evaluation_failed", condition_type=condition.condition_type, error=str(e)
            )
            return False

    async def _trigger_alert(self, rule: AlertRule, budget: ErrorBudget):
        """Dispara um alerta."""
        alert_id = str(uuid.uuid4())

        # Criar mensagem baseada na condição
        title, message, details = self._create_alert_message(rule, budget)

        alert = Alert(
            alert_id=alert_id,
            rule_id=rule.rule_id,
            rule_name=rule.name,
            severity=rule.severity,
            title=title,
            message=message,
            details=details,
            slo_id=budget.slo_id,
            service_name=budget.service_name,
            triggered_at=datetime.now(UTC),
        )

        # Despachar para canais configurados
        dispatch_results = await self.alert_dispatcher.dispatch(
            alert=alert, channels=rule.channels, channel_config=rule.channel_config
        )

        # Atualizar alerta com canais despachados
        alert.dispatched_channels = [r.channel for r in dispatch_results if r.success]
        alert.dispatch_errors = {
            r.channel.value: r.error_message
            for r in dispatch_results
            if not r.success and r.error_message
        }

        # Salvar alerta no banco
        await self.postgresql_client.save_alert(alert)

        # Atualizar última trigger da regra
        self._last_alert_times[rule.rule_id] = datetime.now(UTC)
        await self._update_rule_last_triggered(rule.rule_id)

        self.logger.info(
            "alert_triggered",
            alert_id=alert_id,
            rule_id=rule.rule_id,
            slo_id=budget.slo_id,
            severity=rule.severity.value,
            dispatched_channels=len(alert.dispatched_channels),
            errors=len(alert.dispatch_errors),
        )

    def _create_alert_message(
        self, rule: AlertRule, budget: ErrorBudget
    ) -> tuple[str, str, dict[str, Any]]:
        """Cria mensagem de alerta."""
        # Lidar com condition_type que pode ser enum ou string
        condition_type_value = rule.condition.condition_type
        if isinstance(condition_type_value, str):
            condition_type = condition_type_value
        else:
            condition_type = condition_type_value.value

        if condition_type == "budget_below_threshold":
            title = f"Error Budget Crítico: {budget.service_name}"
            message = (
                f"Error budget restante de {budget.error_budget_remaining:.2f}% "
                f"está abaixo do threshold de {rule.condition.threshold}%."
            )
            details = {
                "budget_remaining": f"{budget.error_budget_remaining:.2f}%",
                "threshold": f"{rule.condition.threshold}%",
                "sli_value": f"{budget.sli_value:.4f}",
                "slo_target": f"{budget.slo_target:.4f}",
            }

        elif condition_type == "burn_rate_exceeds":
            title = f"Alto Burn Rate: {budget.service_name}"
            message = (
                f"Burn rate de {budget.service_name} excede threshold. "
                f"O error budget pode se esgotar em breve."
            )
            burn_rate_info = next(
                (
                    br
                    for br in budget.burn_rates
                    if br.window_hours == (rule.condition.window_hours or 1)
                ),
                budget.burn_rates[0] if budget.burn_rates else None,
            )
            details = {
                "burn_rate": f"{burn_rate_info.rate:.2f}x" if burn_rate_info else "N/A",
                "threshold": f"{rule.condition.threshold}x",
                "window_hours": rule.condition.window_hours or 1,
                "estimated_exhaustion_hours": (
                    f"{burn_rate_info.estimated_exhaustion_hours:.1f}"
                    if burn_rate_info and burn_rate_info.estimated_exhaustion_hours
                    else "N/A"
                ),
            }

        elif condition_type == "slo_violation_count":
            title = f"Múltiplas Violações SLO: {budget.service_name}"
            message = (
                f"{budget.violations_count} violações detectadas nas últimas 24h, "
                f"acima do threshold de {int(rule.condition.threshold)}."
            )
            details = {
                "violations_count": budget.violations_count,
                "threshold": int(rule.condition.threshold),
            }

        elif condition_type == "status_change":
            title = f"Status Crítico: {budget.service_name}"
            message = (
                f"Error budget status mudou para {budget.status.value}. "
                f"Ação imediata pode ser necessária."
            )
            details = {
                "status": budget.status.value,
                "budget_remaining": f"{budget.error_budget_remaining:.2f}%",
            }

        else:  # predictive_exhaustion
            title = f"Previsão de Esgotamento: {budget.service_name}"
            message = (
                "Com o burn rate atual, o error budget será esgotado em breve. "
                "Ação preventiva recomendada."
            )
            details = {
                "predicted_exhaustion_hours": "ver burn rates",
                "budget_remaining": f"{budget.error_budget_remaining:.2f}%",
            }

        # Adicionar informações gerais
        details.update(
            {
                "slo_id": budget.slo_id,
                "service_name": budget.service_name,
                "current_sli": f"{budget.sli_value:.4f}",
                "slo_target": f"{budget.slo_target:.4f}",
            }
        )

        return title, message, details

    async def _is_in_cooldown(self, rule_id: str) -> bool:
        """Verifica se regra está em cooldown."""
        last_triggered = self._last_alert_times.get(rule_id)
        if not last_triggered:
            # Buscar do Redis
            cached = await self.redis_client.client.get(f"alert:last_triggered:{rule_id}")
            if cached:
                last_triggered = datetime.fromisoformat(cached)
                self._last_alert_times[rule_id] = last_triggered
            else:
                return False

        rule = self._rules.get(rule_id)
        if not rule:
            return False

        cooldown_until = last_triggered + timedelta(minutes=rule.cooldown_minutes)
        return datetime.now(UTC) < cooldown_until

    async def _update_rule_last_triggered(self, rule_id: str):
        """Atualiza timestamp da última trigger da regra."""
        now = datetime.now(UTC)
        await self.redis_client.client.setex(
            f"alert:last_triggered:{rule_id}", 86400, now.isoformat()  # 24 horas
        )

    async def _load_rules(self):
        """Carrega regras do banco de dados."""
        try:
            # TODO: Implementar list_rules no PostgreSQLClient
            # Por enquanto, criar regras padrão
            self._create_default_rules()
            self.logger.info("alert_rules_loaded", count=len(self._rules))
        except Exception as e:
            self.logger.error("failed_to_load_rules", error=str(e))
            self._create_default_rules()

    def _create_default_rules(self):
        """Cria regras de alerta padrão."""
        default_rules = [
            AlertRule(
                rule_id="budget-critical",
                name="Error Budget Crítico",
                description="Alerta quando error budget cai abaixo de 20%",
                condition=AlertCondition(
                    condition_type=AlertConditionType.BUDGET_BELOW_THRESHOLD,
                    threshold=20.0,
                ),
                severity=AlertSeverity.CRITICAL,
                channels=[AlertChannel.SLACK, AlertChannel.ALERTMANAGER],
                cooldown_minutes=30,
                created_at=datetime.now(UTC),
            ),
            AlertRule(
                rule_id="budget-exhausted",
                name="Error Budget Esgotado",
                description="Alerta quando error budget é esgotado",
                condition=AlertCondition(
                    condition_type=AlertConditionType.BUDGET_BELOW_THRESHOLD,
                    threshold=5.0,
                ),
                severity=AlertSeverity.EMERGENCY,
                channels=[AlertChannel.SLACK, AlertChannel.PAGERDUTY, AlertChannel.ALERTMANAGER],
                cooldown_minutes=15,
                created_at=datetime.now(UTC),
            ),
            AlertRule(
                rule_id="burn-rate-critical",
                name="Burn Rate Crítico",
                description="Alerta quando burn rate de 1h excede 10x",
                condition=AlertCondition(
                    condition_type=AlertConditionType.BURN_RATE_EXCEEDS,
                    threshold=10.0,
                    window_hours=1,
                ),
                severity=AlertSeverity.CRITICAL,
                channels=[AlertChannel.SLACK],
                cooldown_minutes=60,
                created_at=datetime.now(UTC),
            ),
            AlertRule(
                rule_id="status-warning",
                name="Status de Warning",
                description="Alerta quando budget status muda para WARNING",
                condition=AlertCondition(
                    condition_type=AlertConditionType.STATUS_CHANGE,
                    threshold=0,
                ),
                severity=AlertSeverity.WARNING,
                channels=[AlertChannel.SLACK],
                cooldown_minutes=120,
                created_at=datetime.now(UTC),
            ),
            AlertRule(
                rule_id="violations-high",
                name="Muitas Violações",
                description="Alerta quando há mais de 10 violações em 24h",
                condition=AlertCondition(
                    condition_type=AlertConditionType.SLO_VIOLATION_COUNT,
                    threshold=10,
                ),
                severity=AlertSeverity.WARNING,
                channels=[AlertChannel.SLACK],
                cooldown_minutes=180,
                created_at=datetime.now(UTC),
            ),
        ]

        for rule in default_rules:
            self._rules[rule.rule_id] = rule

    async def _cleanup_old_alerts(self):
        """Remove alertas antigos do banco."""
        try:
            cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
            # TODO: Implementar cleanup_alerts no PostgreSQLClient
            # await self.postgresql_client.cleanup_alerts(cutoff)
            self.logger.debug("old_alerts_cleaned", cutoff=cutoff.isoformat())
        except Exception as e:
            self.logger.error("cleanup_alerts_failed", error=str(e))

    # -------------------------------------------------------------------------
    # API Methods
    # -------------------------------------------------------------------------

    async def create_rule(self, rule: AlertRule) -> AlertRule:
        """Cria uma nova regra de alerta."""
        # Gerar ID se não fornecido
        if not rule.rule_id:
            rule.rule_id = f"rule-{uuid.uuid4().hex[:8]}"

        rule.created_at = datetime.now(UTC)
        self._rules[rule.rule_id] = rule

        # TODO: Persistir no banco
        self.logger.info("alert_rule_created", rule_id=rule.rule_id)

        return rule

    async def update_rule(self, rule_id: str, updates: dict[str, Any]) -> Optional[AlertRule]:
        """Atualiza uma regra existente."""
        rule = self._rules.get(rule_id)
        if not rule:
            return None

        # Atualizar campos
        for key, value in updates.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        rule.updated_at = datetime.now(UTC)

        # TODO: Persistir no banco
        self.logger.info("alert_rule_updated", rule_id=rule_id)

        return rule

    async def delete_rule(self, rule_id: str) -> bool:
        """Remove uma regra."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            # TODO: Remover do banco
            self.logger.info("alert_rule_deleted", rule_id=rule_id)
            return True
        return False

    async def list_rules(self) -> list[AlertRule]:
        """Lista todas as regras."""
        return list(self._rules.values())

    async def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Busca uma regra por ID."""
        return self._rules.get(rule_id)

    async def list_alerts(
        self,
        limit: int = 100,
        severity: Optional[AlertSeverity] = None,
        slo_id: Optional[str] = None,
        service_name: Optional[str] = None,
    ) -> list[Alert]:
        """Lista alertas com filtros."""
        # TODO: Implementar list_alerts no PostgreSQLClient
        return []

    async def get_alert_statistics(self) -> AlertStatistics:
        """Retorna estatísticas de alertas."""
        # TODO: Implementar contagem real no banco
        return AlertStatistics(
            total_rules=len(self._rules),
            active_rules=sum(1 for r in self._rules.values() if r.enabled),
            total_alerts=0,
            alerts_by_severity={},
            alerts_by_channel={},
            recent_alerts=[],
        )

    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> Optional[Alert]:
        """Reconhece um alerta."""
        # TODO: Buscar e atualizar alerta no banco
        self.logger.info("alert_acknowledged", alert_id=alert_id, by=acknowledged_by)
        return None

    async def resolve_alert(self, alert_id: str, resolved_by: str) -> Optional[Alert]:
        """Marca alerta como resolvido."""
        # TODO: Buscar e atualizar alerta no banco
        self.logger.info("alert_resolved", alert_id=alert_id, by=resolved_by)
        return None
