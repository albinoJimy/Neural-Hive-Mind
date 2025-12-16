"""
Interface de alto nível para validação de políticas OPA.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import structlog

from .opa_client import OPAClient, OPAConnectionError, OPAPolicyNotFoundError, OPAEvaluationError
from ..observability.metrics import get_metrics

logger = structlog.get_logger(__name__)


@dataclass
class PolicyViolation:
    """Violação de política (blocking)."""

    policy_name: str
    rule: str
    message: str
    severity: str  # critical, high, medium, low
    field: Optional[str] = None
    expected: Optional[Any] = None
    actual: Optional[Any] = None


@dataclass
class PolicyWarning:
    """Aviso de política (non-blocking)."""

    policy_name: str
    rule: str
    message: str


@dataclass
class ValidationResult:
    """Resultado de validação de políticas."""

    valid: bool
    violations: List[PolicyViolation] = field(default_factory=list)
    warnings: List[PolicyWarning] = field(default_factory=list)
    policy_decisions: Dict[str, Any] = field(default_factory=dict)  # indexado por policy_path; entradas especiais como 'feature_flags' podem ser adicionadas
    evaluated_at: datetime = field(default_factory=datetime.now)
    evaluation_duration_ms: float = 0.0


class PolicyValidator:
    """Interface de alto nível para validação de políticas."""

    def __init__(self, opa_client: OPAClient, config, redis_client=None):
        """
        Inicializar PolicyValidator.

        Args:
            opa_client: Cliente OPA inicializado
            config: OrchestratorSettings
        """
        self.opa_client = opa_client
        self.config = config
        self.redis_client = redis_client
        self.metrics = get_metrics()

        logger.info("PolicyValidator inicializado")

    async def validate_cognitive_plan(self, plan: dict) -> ValidationResult:
        """
        Validar plano completo contra políticas.

        Args:
            plan: Plano cognitivo a validar

        Returns:
            ValidationResult com violações e warnings
        """
        start_time = datetime.now()

        try:
            # Construir contexto para validação
            context = {
                'plan_id': plan.get('plan_id', 'unknown'),
                'total_tickets': len(plan.get('tasks', [])),
                'namespace': plan.get('namespace', 'default'),
                'current_time': int(datetime.now().timestamp() * 1000)
            }

            # Construir input OPA
            opa_input = self._build_opa_input(plan, context)

            # Adicionar parâmetros de políticas
            opa_input['input']['parameters'] = {
                'max_concurrent_tickets': self.config.opa_max_concurrent_tickets,
                'allowed_capabilities': self.config.opa_allowed_capabilities,
                'resource_limits': self.config.opa_resource_limits
            }

            # Avaliar políticas em paralelo
            evaluations = [
                (self.config.opa_policy_resource_limits, opa_input),
                (self.config.opa_policy_sla_enforcement, opa_input)
            ]

            results = await self.opa_client.batch_evaluate(evaluations)

            # Agregar resultados
            validation_result = self._aggregate_results(results)

            # Calcular duração
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            validation_result.evaluation_duration_ms = duration_ms

            # Registrar métricas OPA para cada política avaliada
            for result in results:
                if 'error' not in result:
                    policy_path = result.get('policy_path', 'unknown')
                    policy_result = result.get('result', {})
                    # Determinar resultado: allowed se sem violações, denied se há violações
                    has_violations = len(policy_result.get('violations', [])) > 0
                    result_status = 'denied' if has_violations else 'allowed'
                    self.metrics.record_opa_validation(policy_path, result_status, duration_ms / 1000.0)

            # Registrar violações
            for violation in validation_result.violations:
                self.metrics.record_opa_rejection(
                    violation.policy_name,
                    violation.rule,
                    violation.severity
                )

            # Registrar warnings
            for warning in validation_result.warnings:
                self.metrics.record_opa_warning(
                    warning.policy_name,
                    warning.rule
                )

            logger.info(
                "Plano cognitivo validado",
                plan_id=context['plan_id'],
                valid=validation_result.valid,
                violations_count=len(validation_result.violations),
                warnings_count=len(validation_result.warnings),
                duration_ms=duration_ms
            )

            return validation_result

        except Exception as e:
            logger.error(
                "Erro ao validar plano cognitivo",
                error=str(e),
                exc_info=True
            )

            # Registrar erro OPA
            if isinstance(e, OPAConnectionError):
                if 'Timeout' in str(e):
                    self.metrics.record_opa_error('timeout')
                else:
                    self.metrics.record_opa_error('connection')
            elif isinstance(e, OPAPolicyNotFoundError):
                self.metrics.record_opa_error('policy_not_found')
            elif isinstance(e, OPAEvaluationError):
                self.metrics.record_opa_error('evaluation_error')
            else:
                self.metrics.record_opa_error('unknown')

            # Se fail-closed, retornar resultado inválido
            if not self.config.opa_fail_open:
                return ValidationResult(
                    valid=False,
                    violations=[PolicyViolation(
                        policy_name='system',
                        rule='evaluation_error',
                        message=f'Erro na avaliação de políticas: {str(e)}',
                        severity='critical'
                    )],
                    evaluation_duration_ms=(datetime.now() - start_time).total_seconds() * 1000
                )

            # Se fail-open, retornar resultado válido
            logger.warning("Fail-open ativado, permitindo plano apesar de erro OPA")
            return ValidationResult(
                valid=True,
                warnings=[PolicyWarning(
                    policy_name='system',
                    rule='evaluation_error',
                    message=f'Erro na avaliação de políticas (fail-open): {str(e)}'
                )],
                evaluation_duration_ms=(datetime.now() - start_time).total_seconds() * 1000
            )

    async def validate_execution_ticket(self, ticket: dict) -> ValidationResult:
        """
        Validar ticket individual contra políticas.

        Args:
            ticket: Execution ticket a validar

        Returns:
            ValidationResult com violações, warnings e feature flags
        """
        start_time = datetime.now()

        try:
            # Construir contexto para validação
            context = {
                'ticket_id': ticket.get('ticket_id', 'unknown'),
                'namespace': ticket.get('namespace', 'default'),
                'current_time': int(datetime.now().timestamp() * 1000),
                'tenant_id': ticket.get('tenant_id', 'default'),
                'user_id': ticket.get('user_id', 'system'),
                'jwt_token': ticket.get('jwt_token'),
                'source_ip': ticket.get('source_ip', 'unknown'),
                'request_count_last_minute': await self._get_request_count(ticket.get('tenant_id', 'default'))
            }

            # Construir input OPA
            opa_input = self._build_opa_input(ticket, context)

            # Adicionar parâmetros de políticas
            opa_input['input']['parameters'] = {
                'max_concurrent_tickets': self.config.opa_max_concurrent_tickets,
                'allowed_capabilities': self.config.opa_allowed_capabilities,
                'resource_limits': self.config.opa_resource_limits
            }

            # Adicionar flags para feature flags policy (ler de configuração)
            opa_input['input']['flags'] = {
                'intelligent_scheduler_enabled': self.config.opa_intelligent_scheduler_enabled,
                'burst_capacity_enabled': self.config.opa_burst_capacity_enabled,
                'burst_threshold': self.config.opa_burst_threshold,
                'predictive_allocation_enabled': self.config.opa_predictive_allocation_enabled,
                'auto_scaling_enabled': self.config.opa_auto_scaling_enabled,
                'scheduler_namespaces': self.config.opa_scheduler_namespaces,
                'premium_tenants': self.config.opa_premium_tenants
            }

            # NOVO: Adicionar parâmetros de segurança
            opa_input['input']['security'] = {
                'spiffe_enabled': self.config.spiffe_enabled,
                'trust_domain': self.config.spiffe_trust_domain,
                'allowed_tenants': self.config.opa_allowed_tenants,
                'rbac_roles': self.config.opa_rbac_roles,
                'data_residency_regions': self.config.opa_data_residency_regions,
                'tenant_rate_limits': self.config.opa_tenant_rate_limits,
                'global_rate_limit': self.config.opa_global_rate_limit,
                'default_tenant_rate_limit': self.config.opa_default_tenant_rate_limit
            }

            # Avaliar políticas em paralelo
            evaluations = [
                (self.config.opa_policy_resource_limits, opa_input),
                (self.config.opa_policy_sla_enforcement, opa_input),
                (self.config.opa_policy_feature_flags, opa_input)
            ]

            # NOVO: Adicionar security constraints se habilitado
            if self.config.opa_security_enabled:
                evaluations.append((self.config.opa_policy_security_constraints, opa_input))

            results = await self.opa_client.batch_evaluate(evaluations)

            # Agregar resultados
            validation_result = self._aggregate_results(results)

            # Extrair feature flags do resultado da terceira política
            if len(results) > 2 and 'result' in results[2]:
                validation_result.policy_decisions['feature_flags'] = results[2]['result']

            # NOVO: Extrair security context se disponível
            if len(results) > 3 and 'result' in results[3]:
                validation_result.policy_decisions['security_context'] = results[3]['result'].get('security_context', {})

            # Calcular duração
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            validation_result.evaluation_duration_ms = duration_ms

            # Registrar métricas OPA para cada política avaliada
            for result in results:
                if 'error' not in result:
                    policy_path = result.get('policy_path', 'unknown')
                    policy_result = result.get('result', {})
                    # Determinar resultado: allowed se sem violações, denied se há violações
                    has_violations = len(policy_result.get('violations', [])) > 0
                    result_status = 'denied' if has_violations else 'allowed'
                    self.metrics.record_opa_validation(policy_path, result_status, duration_ms / 1000.0)

            # Registrar violações
            for violation in validation_result.violations:
                self.metrics.record_opa_rejection(
                    violation.policy_name,
                    violation.rule,
                    violation.severity
                )

                # NOVO: Registrar violações de segurança
                if violation.policy_name == 'security_constraints':
                    self.metrics.record_security_violation(
                        context['tenant_id'],
                        violation.rule,
                        violation.severity
                    )
                    if violation.rule == 'cross_tenant_access':
                        self.metrics.record_tenant_isolation_violation(
                            context['tenant_id'],
                            context['tenant_id']
                        )
                    elif violation.rule in ['missing_authentication', 'invalid_jwt']:
                        self.metrics.record_authentication_failure(
                            context['tenant_id'],
                            violation.rule
                        )
                    elif violation.rule == 'insufficient_permissions':
                        denied_capability = ''
                        if isinstance(ticket.get('required_capabilities'), list) and ticket['required_capabilities']:
                            denied_capability = str(ticket['required_capabilities'][0])
                        self.metrics.record_authorization_denial(
                            context['tenant_id'],
                            context.get('user_id', 'unknown'),
                            denied_capability
                        )
                    elif violation.rule == 'pii_handling_violation':
                        self.metrics.record_data_governance_violation(
                            context['tenant_id'],
                            violation.rule
                        )
                    elif violation.rule == 'tenant_rate_limit_exceeded':
                        self.metrics.record_rate_limit_exceeded(
                            context['tenant_id'],
                            'tenant'
                        )

            # Registrar warnings
            for warning in validation_result.warnings:
                self.metrics.record_opa_warning(
                    warning.policy_name,
                    warning.rule
                )

            logger.info(
                "Ticket de execução validado",
                ticket_id=context['ticket_id'],
                valid=validation_result.valid,
                violations_count=len(validation_result.violations),
                warnings_count=len(validation_result.warnings),
                duration_ms=duration_ms
            )

            return validation_result

        except Exception as e:
            logger.error(
                "Erro ao validar ticket de execução",
                error=str(e),
                exc_info=True
            )

            # Registrar erro OPA
            if isinstance(e, OPAConnectionError):
                if 'Timeout' in str(e):
                    self.metrics.record_opa_error('timeout')
                else:
                    self.metrics.record_opa_error('connection')
            elif isinstance(e, OPAPolicyNotFoundError):
                self.metrics.record_opa_error('policy_not_found')
            elif isinstance(e, OPAEvaluationError):
                self.metrics.record_opa_error('evaluation_error')
            else:
                self.metrics.record_opa_error('unknown')

            # Se fail-closed, retornar resultado inválido
            if not self.config.opa_fail_open:
                return ValidationResult(
                    valid=False,
                    violations=[PolicyViolation(
                        policy_name='system',
                        rule='evaluation_error',
                        message=f'Erro na avaliação de políticas: {str(e)}',
                        severity='critical'
                    )],
                    evaluation_duration_ms=(datetime.now() - start_time).total_seconds() * 1000
                )

            # Se fail-open, retornar resultado válido com feature flags default
            logger.warning("Fail-open ativado, permitindo ticket apesar de erro OPA")
            return ValidationResult(
                valid=True,
                warnings=[PolicyWarning(
                    policy_name='system',
                    rule='evaluation_error',
                    message=f'Erro na avaliação de políticas (fail-open): {str(e)}'
                )],
                policy_decisions={
                    'feature_flags': {
                        'enable_intelligent_scheduler': True,
                        'enable_burst_capacity': False,
                        'enable_predictive_allocation': False,
                        'enable_auto_scaling': False
                    }
                },
                evaluation_duration_ms=(datetime.now() - start_time).total_seconds() * 1000
            )

    async def validate_resource_allocation(
        self,
        ticket: dict,
        agent_info: dict
    ) -> ValidationResult:
        """
        Validar alocação de recursos considerando capacidade do agente.
        Esta validação é chamada em C3 (ticket_generation.allocate_resources) logo após
        o IntelligentScheduler.schedule_ticket selecionar um agente e antes de finalizar
        a alocação.

        Args:
            ticket: Execution ticket
            agent_info: Informações do agente candidato

        Returns:
            ValidationResult

        Exemplo de uso:
            agent_info = {
                'agent_id': 'worker-123',
                'agent_type': 'worker-agent',
                'capacity': {'cpu': '500m', 'memory': '512Mi'}
            }
            ticket['allocation_metadata'] = {'agent_id': 'worker-123', 'agent_type': 'worker-agent'}
            result = await policy_validator.validate_resource_allocation(ticket, agent_info)

        Políticas avaliadas:
            - resource_limits.rego
                - timeout_exceeds_maximum
                - capabilities_not_allowed
                - concurrent_tickets_limit
        """
        start_time = datetime.now()

        try:
            # Construir contexto incluindo info do agente
            context = {
                'ticket_id': ticket.get('ticket_id', 'unknown'),
                'agent_id': agent_info.get('agent_id', 'unknown'),
                'agent_capacity': agent_info.get('capacity', {}),
                'current_time': int(datetime.now().timestamp() * 1000),
                'total_tickets': ticket.get('total_tickets', 0),
                'agent': agent_info
            }

            # Construir input OPA com o ticket como recurso (compatível com resource_limits.rego)
            opa_input = self._build_opa_input(ticket, context)

            # Adicionar parâmetros
            opa_input['input']['parameters'] = {
                'allowed_capabilities': self.config.opa_allowed_capabilities,
                'resource_limits': self.config.opa_resource_limits,
                'max_concurrent_tickets': self.config.opa_max_concurrent_tickets
            }

            # Avaliar política de resource limits
            result = await self.opa_client.evaluate_policy(
                self.config.opa_policy_resource_limits,
                opa_input
            )

            # Agregar resultado
            validation_result = self._aggregate_results([result])

            # Calcular duração
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            validation_result.evaluation_duration_ms = duration_ms

            # Registrar métricas OPA
            if 'error' not in result:
                policy_path = result.get('policy_path', 'unknown')
                policy_result = result.get('result', {})
                has_violations = len(policy_result.get('violations', [])) > 0
                result_status = 'denied' if has_violations else 'allowed'
                self.metrics.record_opa_validation(policy_path, result_status, duration_ms / 1000.0)

            # Registrar violações
            for violation in validation_result.violations:
                self.metrics.record_opa_rejection(
                    violation.policy_name,
                    violation.rule,
                    violation.severity
                )

            # Registrar warnings
            for warning in validation_result.warnings:
                self.metrics.record_opa_warning(
                    warning.policy_name,
                    warning.rule
                )

            logger.info(
                "Alocação de recursos validada",
                ticket_id=context['ticket_id'],
                agent_id=context['agent_id'],
                valid=validation_result.valid,
                duration_ms=duration_ms
            )

            return validation_result

        except Exception as e:
            logger.error(
                "Erro ao validar alocação de recursos",
                error=str(e),
                exc_info=True
            )

            # Registrar erro OPA
            if isinstance(e, OPAConnectionError):
                if 'Timeout' in str(e):
                    self.metrics.record_opa_error('timeout')
                else:
                    self.metrics.record_opa_error('connection')
            elif isinstance(e, OPAPolicyNotFoundError):
                self.metrics.record_opa_error('policy_not_found')
            elif isinstance(e, OPAEvaluationError):
                self.metrics.record_opa_error('evaluation_error')
            else:
                self.metrics.record_opa_error('unknown')

            if not self.config.opa_fail_open:
                return ValidationResult(
                    valid=False,
                    violations=[PolicyViolation(
                        policy_name='system',
                        rule='evaluation_error',
                        message=f'Erro na avaliação de políticas: {str(e)}',
                        severity='critical'
                    )],
                    evaluation_duration_ms=(datetime.now() - start_time).total_seconds() * 1000
                )

            return ValidationResult(
                valid=True,
                warnings=[PolicyWarning(
                    policy_name='system',
                    rule='evaluation_error',
                    message=f'Erro na avaliação de políticas (fail-open): {str(e)}'
                )],
                evaluation_duration_ms=(datetime.now() - start_time).total_seconds() * 1000
            )

    async def _get_request_count(self, tenant_id: str) -> int:
        """
        Obter contagem de requests do tenant no último minuto via Redis.
        """
        try:
            if not tenant_id:
                return 0

            # Se configuração de Redis não estiver disponível, fail-open
            if not hasattr(self.config, 'redis_cluster_nodes') or not getattr(self.config, 'redis_cluster_nodes', None):
                return 0

            # Inicializa redis client sob demanda
            if self.redis_client is None:
                try:
                    from src.clients.redis_client import get_redis_client
                    self.redis_client = await get_redis_client(self.config)
                except Exception as redis_err:
                    logger.warning("redis_client_initialization_failed_for_requests", error=str(redis_err))
                    self.redis_client = None

            if self.redis_client is None:
                return 0

            key = f"orchestration:tenant_requests_last_minute:{tenant_id}"
            value = await self.redis_client.get(key)
            if value is None:
                return 0

            return int(value)

        except Exception as e:
            logger.warning(
                "Erro ao obter request count",
                tenant_id=tenant_id,
                error=str(e)
            )
            return 0

    def _build_opa_input(self, data: dict, context: dict) -> dict:
        """
        Construir input OPA com estrutura padronizada.

        Args:
            data: Dados do recurso (plan, ticket, etc)
            context: Contexto adicional

        Returns:
            Input formatado para OPA
        """
        return {
            'input': {
                'resource': data,
                'context': context
            }
        }

    def _aggregate_results(self, results: List[dict]) -> ValidationResult:
        """
        Agregar resultados de múltiplas políticas.

        Args:
            results: Lista de resultados de avaliação OPA

        Returns:
            ValidationResult agregado
        """
        all_violations = []
        all_warnings = []
        policy_decisions = {}

        for result in results:
            # Pular resultados com erro
            if 'error' in result:
                continue

            # Extrair resultado da política
            policy_result = result.get('result', {})

            # Extrair violações
            violations = policy_result.get('violations', [])
            for violation in violations:
                all_violations.append(PolicyViolation(
                    policy_name=violation.get('policy', 'unknown'),
                    rule=violation.get('rule', 'unknown'),
                    message=violation.get('msg', violation.get('message', '')),
                    severity=violation.get('severity', 'medium'),
                    field=violation.get('field'),
                    expected=violation.get('expected'),
                    actual=violation.get('actual')
                ))

            # Extrair warnings
            warnings = policy_result.get('warnings', [])
            for warning in warnings:
                all_warnings.append(PolicyWarning(
                    policy_name=warning.get('policy', 'unknown'),
                    rule=warning.get('rule', 'unknown'),
                    message=warning.get('msg', warning.get('message', ''))
                ))

            # Armazenar decisão completa
            policy_path = result.get('policy_path', 'unknown')
            policy_decisions[policy_path] = policy_result

        # Priorizar violações críticas
        all_violations.sort(
            key=lambda v: {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}.get(v.severity, 4)
        )

        return ValidationResult(
            valid=len(all_violations) == 0,
            violations=all_violations,
            warnings=all_warnings,
            policy_decisions=policy_decisions
        )
