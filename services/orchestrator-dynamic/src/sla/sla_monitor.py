"""
SLA Monitor - Monitoramento em Tempo Real de SLA

Responsável por verificar deadlines de tickets e consultar error budgets
via SLA Management System API.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class SLAMonitor:
    """
    Monitor de SLA para verificação proativa de deadlines e budgets.

    Responsabilidades:
    - Verificar deadlines de tickets individuais e workflows
    - Consultar error budgets via SLA Management System API
    - Calcular tempo restante até deadline
    - Determinar se deadline está próximo (>80% consumido)
    - Cache de budgets em Redis para reduzir chamadas API
    """

    def __init__(self, config, redis_client, metrics):
        """
        Inicializar SLA Monitor.

        Args:
            config: Configurações do orchestrator (OrchestratorSettings)
            redis_client: Cliente Redis para cache
            metrics: Instância de OrchestratorMetrics
        """
        self.config = config
        self.redis = redis_client
        self.metrics = metrics
        self.http_client: Optional[httpx.AsyncClient] = None
        self.base_url = f"http://{config.sla_management_host}:{config.sla_management_port}"

    async def initialize(self):
        """Inicializar cliente HTTP."""
        self.http_client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.config.sla_management_timeout_seconds
        )
        logger.info(
            "sla_monitor_initialized",
            base_url=self.base_url,
            timeout=self.config.sla_management_timeout_seconds
        )

    async def check_ticket_deadline(self, ticket: Dict) -> Dict:
        """
        Verificar deadline de ticket individual.

        Args:
            ticket: Dict com campos 'sla.deadline', 'created_at', 'ticket_id'

        Returns:
            Dict com:
            - deadline_approaching: bool (se >80% do tempo consumido)
            - remaining_seconds: float (tempo restante até deadline)
            - percent_consumed: float (percentual do tempo já consumido)
            - sla_deadline: int (deadline em ms, None se ausente)
        """
        start_time = time.time()

        try:
            sla = ticket.get('sla', {})
            deadline_ms = sla.get('deadline')
            created_at_ms = ticket.get('created_at')

            if not deadline_ms or not created_at_ms:
                logger.warning(
                    "ticket_missing_sla_fields",
                    ticket_id=ticket.get('ticket_id'),
                    has_deadline=bool(deadline_ms),
                    has_created_at=bool(created_at_ms)
                )
                return {
                    'deadline_approaching': False,
                    'remaining_seconds': 0,
                    'percent_consumed': 0,
                    'sla_deadline': None
                }

            # Calcular tempo total e tempo consumido
            now_ms = datetime.now().timestamp() * 1000
            total_time_ms = deadline_ms - created_at_ms
            elapsed_time_ms = now_ms - created_at_ms
            remaining_ms = deadline_ms - now_ms

            # Calcular percentual consumido
            percent_consumed = elapsed_time_ms / total_time_ms if total_time_ms > 0 else 0
            percent_consumed = max(0, min(1, percent_consumed))  # Clamp entre 0 e 1

            # Verificar se deadline está próximo (threshold padrão 80%)
            deadline_approaching = percent_consumed >= self.config.sla_deadline_warning_threshold

            result = {
                'deadline_approaching': deadline_approaching,
                'remaining_seconds': remaining_ms / 1000,
                'percent_consumed': percent_consumed,
                'sla_deadline': deadline_ms
            }

            if deadline_approaching:
                logger.warning(
                    "deadline_approaching_detected",
                    ticket_id=ticket.get('ticket_id'),
                    remaining_seconds=result['remaining_seconds'],
                    percent_consumed=percent_consumed
                )

            # Registrar métrica de duração
            duration = time.time() - start_time
            self.metrics.record_sla_check_duration('deadline', duration)

            return result

        except Exception as e:
            logger.error(
                "deadline_check_failed",
                ticket_id=ticket.get('ticket_id'),
                error=str(e)
            )
            self.metrics.record_sla_monitor_error('deadline_check')
            return {
                'deadline_approaching': False,
                'remaining_seconds': 0,
                'percent_consumed': 0,
                'sla_deadline': None
            }

    async def check_workflow_sla(self, workflow_id: str, tickets: List[Dict]) -> Dict:
        """
        Verificar SLA de workflow completo agregando todos os tickets.

        Args:
            workflow_id: ID do workflow
            tickets: Lista de tickets do workflow

        Returns:
            Dict com:
            - deadline_approaching: bool (se algum ticket está próximo do deadline)
            - critical_tickets: List[str] (IDs dos tickets críticos)
            - remaining_seconds: float (menor tempo restante entre todos os tickets)
            - ticket_deadline_data: Dict[str, Dict] (dados de deadline por ticket_id)
        """
        start_time = time.time()

        try:
            critical_tickets = []
            min_remaining_seconds = float('inf')
            any_deadline_approaching = False
            ticket_deadline_data = {}

            for ticket_wrapper in tickets:
                ticket = ticket_wrapper.get('ticket', {})
                ticket_id = ticket.get('ticket_id')
                check_result = await self.check_ticket_deadline(ticket)

                # Armazenar dados de deadline por ticket
                if ticket_id:
                    ticket_deadline_data[ticket_id] = check_result

                if check_result['deadline_approaching']:
                    any_deadline_approaching = True
                    critical_tickets.append(ticket_id)

                if check_result['remaining_seconds'] < min_remaining_seconds:
                    min_remaining_seconds = check_result['remaining_seconds']

            # Se nenhum ticket foi processado, usar 0
            if min_remaining_seconds == float('inf'):
                min_remaining_seconds = 0

            result = {
                'deadline_approaching': any_deadline_approaching,
                'critical_tickets': critical_tickets,
                'remaining_seconds': min_remaining_seconds,
                'ticket_deadline_data': ticket_deadline_data
            }

            logger.info(
                "workflow_sla_checked",
                workflow_id=workflow_id,
                tickets_count=len(tickets),
                critical_tickets_count=len(critical_tickets),
                remaining_seconds=min_remaining_seconds
            )

            # Registrar métrica de duração
            duration = time.time() - start_time
            self.metrics.record_sla_check_duration('workflow', duration)

            return result

        except Exception as e:
            logger.error(
                "workflow_sla_check_failed",
                workflow_id=workflow_id,
                error=str(e)
            )
            self.metrics.record_sla_monitor_error('workflow_check')
            return {
                'deadline_approaching': False,
                'critical_tickets': [],
                'remaining_seconds': 0,
                'ticket_deadline_data': {}
            }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True
    )
    async def _fetch_budget_from_api(self, service_name: str) -> Optional[Dict]:
        """
        Consultar budget via API com retry.

        Args:
            service_name: Nome do serviço

        Returns:
            Dict com dados do budget ou None em caso de erro
        """
        if not self.http_client:
            raise RuntimeError("HTTP client not initialized. Call initialize() first.")

        try:
            response = await self.http_client.get(
                f"/api/v1/budgets",
                params={"service_name": service_name}
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.warning(
                "sla_api_http_error",
                service_name=service_name,
                status_code=e.response.status_code,
                error=str(e)
            )
            raise
        except httpx.RequestError as e:
            logger.warning(
                "sla_api_request_error",
                service_name=service_name,
                error=str(e)
            )
            raise

    async def get_service_budget(self, service_name: str) -> Optional[Dict]:
        """
        Consultar error budget do serviço via API com cache Redis.

        Args:
            service_name: Nome do serviço

        Returns:
            Dict com:
            - error_budget_remaining: float (0.0 a 1.0)
            - status: str (HEALTHY/WARNING/CRITICAL/EXHAUSTED)
            - burn_rates: List[Dict] (taxas de consumo em diferentes janelas)
            ou None em caso de erro
        """
        start_time = time.time()
        cache_key = f"sla:budget:{service_name}"

        try:
            # Verificar cache Redis
            if self.redis:
                try:
                    cached = await self.redis.get(cache_key)
                    if cached:
                        import json
                        logger.debug(
                            "budget_cache_hit",
                            service_name=service_name
                        )
                        return json.loads(cached)
                except Exception as e:
                    logger.warning(
                        "redis_cache_error",
                        cache_key=cache_key,
                        error=str(e)
                    )
                    self.metrics.record_sla_monitor_error('cache_error')

            # Consultar API
            budget_data = await self._fetch_budget_from_api(service_name)

            if budget_data and self.redis:
                # Cachear resultado
                try:
                    import json
                    await self.redis.setex(
                        cache_key,
                        self.config.sla_management_cache_ttl_seconds,
                        json.dumps(budget_data)
                    )
                except Exception as e:
                    logger.warning(
                        "redis_cache_set_error",
                        cache_key=cache_key,
                        error=str(e)
                    )

            # Registrar métrica de duração
            duration = time.time() - start_time
            self.metrics.record_sla_check_duration('budget', duration)

            return budget_data

        except Exception as e:
            logger.error(
                "budget_fetch_failed",
                service_name=service_name,
                error=str(e)
            )
            self.metrics.record_sla_monitor_error('api_error')
            # Fail-open: retornar None para não bloquear workflow
            return None

    async def check_budget_threshold(
        self,
        service_name: str,
        threshold: float = None
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Verificar se budget está abaixo do threshold.

        Args:
            service_name: Nome do serviço
            threshold: Threshold de alerta (padrão 0.2 = 20%)

        Returns:
            Tupla (is_critical, budget_data):
            - is_critical: bool (True se budget < threshold)
            - budget_data: Dict com dados do budget ou None
        """
        if threshold is None:
            threshold = self.config.sla_budget_critical_threshold

        budget_data = await self.get_service_budget(service_name)

        if not budget_data:
            # Sem dados de budget, assumir não crítico (fail-open)
            return False, None

        error_budget_remaining = budget_data.get('error_budget_remaining', 1.0)
        is_critical = error_budget_remaining < threshold

        if is_critical:
            logger.warning(
                "budget_critical_threshold_exceeded",
                service_name=service_name,
                budget_remaining=error_budget_remaining,
                threshold=threshold,
                status=budget_data.get('status')
            )

        return is_critical, budget_data

    async def close(self):
        """Fechar cliente HTTP gracefully."""
        if self.http_client:
            await self.http_client.aclose()
            logger.info("sla_monitor_closed")
