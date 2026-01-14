"""
Chaos Engine - Orquestrador principal de experimentos de Chaos Engineering.

Coordena a execução de experimentos, injeção de falhas, validação de
playbooks e geração de relatórios.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from time import perf_counter
import structlog
from prometheus_client import Counter, Gauge, Histogram, REGISTRY

from neural_hive_observability import get_tracer
from neural_hive_resilience import MonitoredCircuitBreaker

from .chaos_models import (
    ChaosExperiment,
    ChaosExperimentStatus,
    ChaosExperimentRequest,
    ChaosExperimentResponse,
    ExperimentReport,
    FaultInjection,
    ScenarioConfig,
    ValidationResult,
)
from .chaos_config import (
    BLAST_RADIUS_LIMITS,
    CRITICAL_SERVICES,
    KAFKA_TOPICS,
    OPA_POLICIES,
    PROTECTED_NAMESPACES,
    RETRY_CONFIG,
    get_blast_radius_limit,
    is_business_hours,
    is_critical_service,
    is_protected_namespace,
)
from .injectors import (
    ApplicationFaultInjector,
    BaseFaultInjector,
    NetworkFaultInjector,
    PodFaultInjector,
    ResourceFaultInjector,
)
from .validators import HealthValidator, PlaybookValidator
from .scenarios import ScenarioLibrary

logger = structlog.get_logger(__name__)


def _get_or_create_metric(metric_class, name, description, labels=None, **kwargs):
    """
    Retorna metrica existente ou cria nova se nao existir.

    Verifica primeiro no REGISTRY para evitar duplicacao.
    """
    # Verificar se metrica ja existe no registry usando as chaves do dicionario
    # O registry usa os nomes das metricas como chaves
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]

    # Para Counter, verificar tambem a versao base (sem _total)
    base_name = name.replace('_total', '') if name.endswith('_total') else name
    if base_name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[base_name]

    # Metrica nao existe, criar nova
    try:
        if labels:
            return metric_class(name, description, labels, **kwargs)
        return metric_class(name, description, **kwargs)
    except ValueError:
        # Fallback: buscar por _name do collector
        for collector in list(REGISTRY._names_to_collectors.values()):
            if hasattr(collector, '_name') and collector._name == name:
                return collector
        raise


# Métricas Prometheus (singleton pattern)
EXPERIMENTS_TOTAL = _get_or_create_metric(
    Counter, 'chaos_experiments_total',
    'Total de experimentos de chaos executados',
    ['experiment_type', 'status', 'environment']
)

ACTIVE_EXPERIMENTS = _get_or_create_metric(
    Gauge, 'chaos_active_experiments',
    'Número de experimentos ativos'
)

EXPERIMENT_DURATION = _get_or_create_metric(
    Histogram, 'chaos_experiment_duration_seconds',
    'Duração total do experimento',
    ['experiment_type', 'status'],
    buckets=[30, 60, 120, 300, 600, 1200, 1800, 3600]
)

BLAST_RADIUS = _get_or_create_metric(
    Gauge, 'chaos_experiment_blast_radius',
    'Número de pods afetados pelo experimento',
    ['experiment_id']
)

EXPERIMENT_START_TIMESTAMP = _get_or_create_metric(
    Gauge, 'chaos_experiment_start_timestamp',
    'Timestamp de início do experimento',
    ['experiment_id', 'experiment_name']
)

EXPERIMENT_COMPLETED_TOTAL = _get_or_create_metric(
    Counter, 'chaos_experiment_completed_total',
    'Total de experimentos completados',
    ['success', 'experiment_type', 'environment']
)

BLAST_RADIUS_CURRENT = _get_or_create_metric(
    Gauge, 'chaos_blast_radius_current',
    'Blast radius atual do experimento em execução',
    ['experiment_id']
)

POLICY_VIOLATIONS_TOTAL = _get_or_create_metric(
    Counter, 'chaos_policy_violations_total',
    'Total de violações de políticas OPA',
    ['violation', 'environment']
)

PLAYBOOK_VALIDATION_TOTAL = _get_or_create_metric(
    Counter, 'chaos_playbook_validation_total',
    'Total de validações de playbooks',
    ['playbook', 'result']
)

PLAYBOOK_RECOVERY_DURATION = _get_or_create_metric(
    Gauge, 'chaos_playbook_recovery_duration_seconds',
    'Tempo de recuperação do playbook em segundos',
    ['playbook']
)

GAME_DAY_SCENARIOS_TOTAL = _get_or_create_metric(
    Gauge, 'chaos_game_day_scenarios_total',
    'Total de cenários no Game Day',
    ['game_day_id']
)

GAME_DAY_SCENARIOS_FAILED = _get_or_create_metric(
    Gauge, 'chaos_game_day_scenarios_failed',
    'Número de cenários falhados no Game Day',
    ['game_day_id']
)

GAME_DAY_DURATION = _get_or_create_metric(
    Gauge, 'chaos_game_day_duration_seconds',
    'Duração do Game Day em segundos',
    ['game_day_id']
)

GAME_DAY_INFO = _get_or_create_metric(
    Gauge, 'chaos_game_day_info',
    'Informações do Game Day',
    ['game_day_id', 'scenarios_total', 'scenarios_passed', 'scenarios_failed', 'success_rate']
)

EXPERIMENT_OUTSIDE_MAINTENANCE_WINDOW = _get_or_create_metric(
    Gauge, 'chaos_experiment_outside_maintenance_window',
    'Experimentos executando fora da janela de manutenção',
    ['experiment_id']
)


class ChaosEngine:
    """
    Orquestrador principal de experimentos de Chaos Engineering.

    Responsável por:
    - Coordenar execução de experimentos
    - Gerenciar injetores de falha
    - Validar experimentos com OPA
    - Integrar com PlaybookExecutor para validação
    - Gerar relatórios e métricas
    """

    def __init__(
        self,
        k8s_in_cluster: bool = True,
        playbook_executor=None,
        service_registry_client=None,
        opa_client=None,
        mongodb_client=None,
        kafka_producer=None,
        prometheus_client=None,
        sla_management_client=None,
        max_concurrent_experiments: int = 3,
        default_timeout_seconds: int = 600,
        require_opa_approval: bool = True,
        blast_radius_limit: int = 5,
    ):
        """
        Inicializa o Chaos Engine.

        Args:
            k8s_in_cluster: Se está rodando dentro do cluster K8s
            playbook_executor: Executor de playbooks do Self-Healing Engine
            service_registry_client: Cliente do Service Registry
            opa_client: Cliente OPA para validação de políticas
            mongodb_client: Cliente MongoDB para persistência
            kafka_producer: Producer Kafka para eventos
            prometheus_client: Cliente Prometheus para queries
            sla_management_client: Cliente do SLA Management System
            max_concurrent_experiments: Máximo de experimentos simultâneos
            default_timeout_seconds: Timeout padrão para experimentos
            require_opa_approval: Se requer aprovação OPA
            blast_radius_limit: Limite padrão de blast radius
        """
        self.k8s_in_cluster = k8s_in_cluster
        self.playbook_executor = playbook_executor
        self.service_registry_client = service_registry_client
        self.opa_client = opa_client
        self.mongodb_client = mongodb_client
        self.kafka_producer = kafka_producer
        self.prometheus_client = prometheus_client
        self.sla_management_client = sla_management_client

        self.max_concurrent_experiments = max_concurrent_experiments
        self.default_timeout_seconds = default_timeout_seconds
        self.require_opa_approval = require_opa_approval
        self.default_blast_radius_limit = blast_radius_limit

        # Kubernetes API clients
        self.k8s_core_v1 = None
        self.k8s_apps_v1 = None
        self.k8s_networking_v1 = None
        self.k8s_custom_objects = None

        # Injetores de falha
        self.injectors: Dict[str, BaseFaultInjector] = {}

        # Validadores
        self.playbook_validator: Optional[PlaybookValidator] = None
        self.health_validator: Optional[HealthValidator] = None

        # Biblioteca de cenários
        self.scenario_library = ScenarioLibrary()

        # Estado
        self._active_experiments: Dict[str, ChaosExperiment] = {}
        self._experiment_semaphore: Optional[asyncio.Semaphore] = None

        # Cache em memória para experimentos quando MongoDB não está disponível
        self._experiment_cache: Dict[str, ChaosExperiment] = {}

        # Circuit breaker para operações de chaos
        self._circuit_breaker = MonitoredCircuitBreaker(
            service_name="chaos-engine",
            circuit_name="experiment-execution",
            fail_max=5,
            reset_timeout=60
        )

        logger.info(
            "chaos_engine.created",
            max_concurrent=max_concurrent_experiments,
            require_opa=require_opa_approval,
            blast_radius_limit=blast_radius_limit
        )

    async def initialize(self):
        """Inicializa clientes Kubernetes e injetores."""
        try:
            from kubernetes import client, config

            if self.k8s_in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config()

            self.k8s_core_v1 = client.CoreV1Api()
            self.k8s_apps_v1 = client.AppsV1Api()
            self.k8s_networking_v1 = client.NetworkingV1Api()
            self.k8s_custom_objects = client.CustomObjectsApi()

            # Inicializar injetores
            self.injectors = {
                "network": NetworkFaultInjector(
                    k8s_core_v1=self.k8s_core_v1,
                    k8s_apps_v1=self.k8s_apps_v1,
                    k8s_networking_v1=self.k8s_networking_v1,
                    opa_client=self.opa_client,
                ),
                "pod": PodFaultInjector(
                    k8s_core_v1=self.k8s_core_v1,
                    k8s_apps_v1=self.k8s_apps_v1,
                    opa_client=self.opa_client,
                ),
                "resource": ResourceFaultInjector(
                    k8s_core_v1=self.k8s_core_v1,
                    k8s_apps_v1=self.k8s_apps_v1,
                    opa_client=self.opa_client,
                ),
                "application": ApplicationFaultInjector(
                    k8s_core_v1=self.k8s_core_v1,
                    k8s_apps_v1=self.k8s_apps_v1,
                    k8s_custom_objects=self.k8s_custom_objects,
                    opa_client=self.opa_client,
                ),
            }

            # Inicializar validadores
            self.playbook_validator = PlaybookValidator(
                playbook_executor=self.playbook_executor,
                prometheus_client=self.prometheus_client,
                sla_management_client=self.sla_management_client,
            )

            self.health_validator = HealthValidator(
                service_registry_client=self.service_registry_client,
                sla_management_client=self.sla_management_client,
                prometheus_client=self.prometheus_client,
            )
            await self.health_validator.initialize()

            # Semáforo para controle de concorrência
            self._experiment_semaphore = asyncio.Semaphore(
                self.max_concurrent_experiments
            )

            logger.info("chaos_engine.initialized", in_cluster=self.k8s_in_cluster)

        except Exception as e:
            logger.error("chaos_engine.initialization_failed", error=str(e))
            raise

    async def close(self):
        """Fecha recursos e executa cleanup."""
        # Rollback de experimentos ativos
        for experiment_id in list(self._active_experiments.keys()):
            try:
                await self.rollback_experiment(experiment_id)
            except Exception as e:
                logger.error(
                    "chaos_engine.cleanup_rollback_failed",
                    experiment_id=experiment_id,
                    error=str(e)
                )

        # Fechar validadores
        if self.health_validator:
            await self.health_validator.close()

        logger.info("chaos_engine.closed")

    async def create_experiment(
        self,
        request: ChaosExperimentRequest,
    ) -> ChaosExperimentResponse:
        """
        Cria um novo experimento de chaos.

        Args:
            request: Requisição de criação de experimento

        Returns:
            Response com ID e status do experimento
        """
        experiment = ChaosExperiment(
            name=request.name,
            description=request.description,
            environment=request.environment,
            fault_injections=request.fault_injections,
            validation_criteria=request.validation_criteria,
            rollback_strategy=request.rollback_strategy,
            timeout_seconds=request.timeout_seconds,
            blast_radius_limit=request.blast_radius_limit,
            approved_by=request.approved_by,
            metadata=request.metadata,
        )

        # Persistir no MongoDB ou usar cache em memória como fallback
        if self.mongodb_client:
            await self._persist_experiment(experiment)
        else:
            # Armazenar em cache quando MongoDB não está disponível
            self._experiment_cache[experiment.id] = experiment
            logger.warning(
                "chaos_engine.using_memory_cache",
                experiment_id=experiment.id,
                note="MongoDB indisponível, usando cache em memória"
            )

        logger.info(
            "chaos_engine.experiment_created",
            experiment_id=experiment.id,
            name=experiment.name
        )

        return ChaosExperimentResponse(
            experiment_id=experiment.id,
            status=experiment.status,
            message="Experimento criado com sucesso",
            estimated_duration_seconds=experiment.timeout_seconds
        )

    async def execute_experiment(
        self,
        experiment_id: str,
        executed_by: Optional[str] = None,
    ) -> ExperimentReport:
        """
        Executa um experimento de chaos.

        Args:
            experiment_id: ID do experimento a executar
            executed_by: Identificador do executor

        Returns:
            Relatório completo do experimento
        """
        # Buscar experimento
        experiment = await self._get_experiment(experiment_id)
        if not experiment:
            raise ValueError(f"Experimento não encontrado: {experiment_id}")

        # Validar com OPA
        if self.require_opa_approval:
            allowed, violations = await self._validate_with_opa(experiment)
            if not allowed:
                experiment.status = ChaosExperimentStatus.FAILED
                await self._update_experiment_status(experiment)
                raise PermissionError(
                    f"Experimento bloqueado por política OPA: {violations}"
                )

        # Adquirir semáforo
        async with self._experiment_semaphore:
            return await self._execute_experiment_internal(experiment, executed_by)

    async def _execute_experiment_internal(
        self,
        experiment: ChaosExperiment,
        executed_by: Optional[str],
    ) -> ExperimentReport:
        """Execução interna do experimento."""
        start_time = perf_counter()
        experiment.started_at = datetime.utcnow()
        experiment.executed_by = executed_by
        experiment.status = ChaosExperimentStatus.INJECTING

        self._active_experiments[experiment.id] = experiment
        ACTIVE_EXPERIMENTS.inc()

        # Registrar timestamp de início para detecção de experimentos travados
        EXPERIMENT_START_TIMESTAMP.labels(
            experiment_id=experiment.id,
            experiment_name=experiment.name
        ).set_to_current_time()

        # Verificar se está fora da janela de manutenção
        if not is_business_hours():
            EXPERIMENT_OUTSIDE_MAINTENANCE_WINDOW.labels(
                experiment_id=experiment.id
            ).set(0)
        else:
            # Se não é fora de business hours, pode estar fora da janela de manutenção
            EXPERIMENT_OUTSIDE_MAINTENANCE_WINDOW.labels(
                experiment_id=experiment.id
            ).set(1 if experiment.environment == "production" else 0)

        tracer = get_tracer()
        injection_results = []
        validation_results = []
        total_blast_radius = 0

        try:
            with tracer.start_as_current_span("chaos.experiment.execute") as span:
                span.set_attribute("chaos.experiment_id", experiment.id)
                span.set_attribute("chaos.experiment_name", experiment.name)

                # Publicar evento de início
                await self._publish_event("experiment_started", experiment)

                # Fase 1: Injetar falhas
                logger.info(
                    "chaos_engine.injecting_faults",
                    experiment_id=experiment.id,
                    injection_count=len(experiment.fault_injections)
                )

                for injection in experiment.fault_injections:
                    injector = self._get_injector_for_fault(injection.fault_type)
                    if not injector:
                        logger.warning(
                            "chaos_engine.no_injector",
                            fault_type=injection.fault_type
                        )
                        continue

                    # Verificar blast radius
                    blast_radius = await injector.get_blast_radius(injection.target)
                    if blast_radius + total_blast_radius > experiment.blast_radius_limit:
                        logger.warning(
                            "chaos_engine.blast_radius_exceeded",
                            current=total_blast_radius,
                            additional=blast_radius,
                            limit=experiment.blast_radius_limit
                        )
                        continue

                    result = await injector.inject(injection)
                    injection_results.append(result)

                    if result.success:
                        total_blast_radius += result.blast_radius
                        BLAST_RADIUS.labels(
                            experiment_id=experiment.id
                        ).set(total_blast_radius)
                        # Atualizar métrica de blast radius atual
                        BLAST_RADIUS_CURRENT.labels(
                            experiment_id=experiment.id
                        ).set(total_blast_radius)

                # Fase 2: Aguardar propagação e validar
                experiment.status = ChaosExperimentStatus.VALIDATING
                await self._update_experiment_status(experiment)

                logger.info(
                    "chaos_engine.validating",
                    experiment_id=experiment.id
                )

                # Aguardar tempo para falha propagar
                await asyncio.sleep(10)

                # Validar playbooks se configurado
                if (experiment.validation_criteria.required_playbook and
                        self.playbook_validator):

                    for injection in experiment.fault_injections:
                        context = {
                            "experiment_id": experiment.id,
                            "service_name": injection.target.service_name,
                            "namespace": injection.target.namespace,
                        }

                        validation = await self.playbook_validator.validate_playbook_effectiveness(
                            experiment.validation_criteria.required_playbook,
                            injection,
                            experiment.validation_criteria,
                            context
                        )
                        validation_results.append(validation)

                        # Registrar métricas de validação de playbook
                        playbook_name = experiment.validation_criteria.required_playbook
                        PLAYBOOK_VALIDATION_TOTAL.labels(
                            playbook=playbook_name,
                            result="passed" if validation.success else "failed"
                        ).inc()

                        if validation.recovery_time_seconds is not None:
                            PLAYBOOK_RECOVERY_DURATION.labels(
                                playbook=playbook_name
                            ).set(validation.recovery_time_seconds)

                # Fase 3: Recuperação
                experiment.status = ChaosExperimentStatus.RECOVERING
                await self._update_experiment_status(experiment)

                logger.info(
                    "chaos_engine.recovering",
                    experiment_id=experiment.id
                )

                # Rollback de todas as injeções
                await self._rollback_all_injections(experiment)

                # Aguardar recuperação
                if self.health_validator and experiment.fault_injections:
                    first_injection = experiment.fault_injections[0]
                    if first_injection.target.service_name:
                        await self.health_validator.wait_for_healthy(
                            first_injection.target.service_name,
                            first_injection.target.namespace,
                            timeout_seconds=experiment.validation_criteria.max_recovery_time_seconds
                        )

                # Determinar resultado
                all_validations_passed = all(
                    v.success for v in validation_results
                ) if validation_results else True

                experiment.status = (
                    ChaosExperimentStatus.COMPLETED
                    if all_validations_passed
                    else ChaosExperimentStatus.FAILED
                )
                experiment.completed_at = datetime.utcnow()

        except Exception as e:
            logger.error(
                "chaos_engine.experiment_failed",
                experiment_id=experiment.id,
                error=str(e)
            )
            experiment.status = ChaosExperimentStatus.FAILED
            experiment.completed_at = datetime.utcnow()

            # Rollback de emergência
            await self._rollback_all_injections(experiment)

        finally:
            duration = perf_counter() - start_time
            ACTIVE_EXPERIMENTS.dec()
            self._active_experiments.pop(experiment.id, None)

            EXPERIMENTS_TOTAL.labels(
                experiment_type=experiment.metadata.get("scenario", "custom"),
                status=experiment.status.value,
                environment=experiment.environment
            ).inc()

            EXPERIMENT_DURATION.labels(
                experiment_type=experiment.metadata.get("scenario", "custom"),
                status=experiment.status.value
            ).observe(duration)

            # Registrar métrica de experimento completado
            is_success = experiment.status == ChaosExperimentStatus.COMPLETED
            EXPERIMENT_COMPLETED_TOTAL.labels(
                success="true" if is_success else "false",
                experiment_type=experiment.metadata.get("scenario", "custom"),
                environment=experiment.environment
            ).inc()

            # Limpar métricas de timestamp e blast radius ao finalizar
            EXPERIMENT_START_TIMESTAMP.remove(experiment.id, experiment.name)
            BLAST_RADIUS_CURRENT.remove(experiment.id)
            EXPERIMENT_OUTSIDE_MAINTENANCE_WINDOW.remove(experiment.id)

            await self._update_experiment_status(experiment)
            await self._publish_event("experiment_completed", experiment)

        # Gerar relatório
        report = self._generate_report(
            experiment,
            injection_results,
            validation_results,
            total_blast_radius,
            duration
        )

        # Persistir relatório
        if self.mongodb_client:
            await self._persist_report(report)

        return report

    async def rollback_experiment(self, experiment_id: str) -> bool:
        """
        Executa rollback manual de um experimento.

        Args:
            experiment_id: ID do experimento

        Returns:
            True se rollback bem-sucedido
        """
        experiment = self._active_experiments.get(experiment_id)
        if not experiment:
            experiment = await self._get_experiment(experiment_id)

        if not experiment:
            raise ValueError(f"Experimento não encontrado: {experiment_id}")

        logger.info(
            "chaos_engine.manual_rollback",
            experiment_id=experiment_id
        )

        success = await self._rollback_all_injections(experiment)

        if success:
            experiment.status = ChaosExperimentStatus.ROLLED_BACK
            experiment.completed_at = datetime.utcnow()
            await self._update_experiment_status(experiment)
            self._active_experiments.pop(experiment_id, None)
            ACTIVE_EXPERIMENTS.dec()

        return success

    async def get_experiment_status(
        self,
        experiment_id: str
    ) -> Optional[ChaosExperiment]:
        """Retorna status atual de um experimento."""
        if experiment_id in self._active_experiments:
            return self._active_experiments[experiment_id]
        return await self._get_experiment(experiment_id)

    def list_scenarios(self) -> List[str]:
        """Lista cenários disponíveis."""
        return self.scenario_library.list_scenarios()

    def get_scenario_info(self, scenario_name: str) -> Optional[Dict[str, Any]]:
        """Retorna informações sobre um cenário."""
        return self.scenario_library.get_scenario_info(scenario_name)

    async def execute_scenario(
        self,
        scenario_name: str,
        config: ScenarioConfig,
        executed_by: Optional[str] = None,
        executor_role: str = "chaos-engineer",
        executor_groups: Optional[List[str]] = None,
    ) -> ExperimentReport:
        """
        Executa um cenário pré-definido.

        Aplica validação OPA e controle de concorrência, igual ao execute_experiment.

        Args:
            scenario_name: Nome do cenário
            config: Configuração do cenário
            executed_by: Identificador do executor
            executor_role: Role do executor para validação OPA
            executor_groups: Grupos do executor para validação OPA

        Returns:
            Relatório do experimento
        """
        experiment = self.scenario_library.create_scenario(scenario_name, config)

        # Persistir experimento
        if self.mongodb_client:
            await self._persist_experiment(experiment)

        # Validar com OPA (igual ao execute_experiment)
        if self.require_opa_approval:
            allowed, violations = await self._validate_with_opa(
                experiment,
                executor_name=executed_by,
                executor_role=executor_role,
                executor_groups=executor_groups,
            )
            if not allowed:
                experiment.status = ChaosExperimentStatus.FAILED
                await self._update_experiment_status(experiment)
                raise PermissionError(
                    f"Cenário bloqueado por política OPA: {violations}"
                )

        # Adquirir semáforo para controle de concorrência (igual ao execute_experiment)
        async with self._experiment_semaphore:
            return await self._execute_experiment_internal(experiment, executed_by)

    async def validate_playbook(
        self,
        playbook_name: str,
        scenario_name: str,
        target_service: str,
        target_namespace: str = "default",
    ) -> ValidationResult:
        """
        Valida um playbook específico usando um cenário.

        Args:
            playbook_name: Nome do playbook a validar
            scenario_name: Cenário a usar para validação
            target_service: Serviço alvo
            target_namespace: Namespace do serviço

        Returns:
            Resultado da validação
        """
        config = ScenarioConfig(
            name=f"Validação de {playbook_name}",
            description=f"Validação automatizada do playbook {playbook_name}",
            target_service=target_service,
            target_namespace=target_namespace,
            playbook_to_validate=playbook_name,
        )

        report = await self.execute_scenario(scenario_name, config)

        if report.validations:
            return report.validations[0]

        return ValidationResult(
            playbook_name=playbook_name,
            success=report.status == ChaosExperimentStatus.COMPLETED,
            observations=["Validação concluída via execução de cenário"],
        )

    def get_active_experiments(self) -> List[ChaosExperiment]:
        """Retorna lista de experimentos ativos."""
        return list(self._active_experiments.values())

    async def _validate_with_opa(
        self,
        experiment: ChaosExperiment,
        executor_name: Optional[str] = None,
        executor_role: str = "unknown",
        executor_groups: Optional[List[str]] = None,
    ) -> tuple[bool, List[str]]:
        """
        Valida experimento com políticas OPA.

        O input deve ter o formato esperado pelo Rego:
        - input.experiment: dados do experimento
        - input.executor: dados do executor
        - input.approval: dados de aprovação
        """
        if not self.opa_client:
            logger.warning(
                "chaos_engine.opa_client_unavailable",
                experiment_id=experiment.id
            )
            return True, []

        try:
            # Construir fault_injections com estrutura completa para o OPA
            fault_injections_for_opa = []
            for injection in experiment.fault_injections:
                fault_injections_for_opa.append({
                    "id": injection.id,
                    "fault_type": injection.fault_type.value,
                    "target": {
                        "namespace": injection.target.namespace,
                        "service_name": injection.target.service_name,
                        "labels": injection.target.labels,
                        "deployment_name": injection.target.deployment_name,
                        "percentage": injection.target.percentage,
                    },
                    "parameters": injection.parameters.model_dump(),
                    "duration_seconds": injection.duration_seconds,
                })

            # Construir input no formato esperado pelo Rego policy
            opa_input = {
                "input": {
                    "experiment": {
                        "id": experiment.id,
                        "name": experiment.name,
                        "environment": experiment.environment,
                        "blast_radius_limit": experiment.blast_radius_limit,
                        "fault_injections": fault_injections_for_opa,
                        "rollback_strategy": experiment.rollback_strategy.value,
                        "timeout_seconds": experiment.timeout_seconds,
                    },
                    "executor": {
                        "name": executor_name or experiment.executed_by or "unknown",
                        "role": executor_role,
                        "groups": executor_groups or [],
                    },
                    "approval": {
                        "opa_approved": experiment.approved_by is not None,
                        "approved_by": experiment.approved_by or "",
                        "business_hours_override": experiment.metadata.get(
                            "business_hours_override", False
                        ),
                    },
                }
            }

            result = await self.opa_client.evaluate_policy(
                OPA_POLICIES["experiment_validation"],
                opa_input
            )

            violations = result.get("result", {}).get("violations", [])

            # Registrar métricas de violações de política
            if violations:
                for violation in violations:
                    violation_rule = violation.get("rule", "unknown") if isinstance(violation, dict) else str(violation)
                    POLICY_VIOLATIONS_TOTAL.labels(
                        violation=violation_rule,
                        environment=experiment.environment
                    ).inc()

            return len(violations) == 0, violations

        except Exception as e:
            logger.error(
                "chaos_engine.opa_validation_failed",
                experiment_id=experiment.id,
                error=str(e)
            )
            # Fail-open
            return True, []

    def _get_injector_for_fault(self, fault_type) -> Optional[BaseFaultInjector]:
        """Retorna o injetor apropriado para o tipo de falha."""
        fault_type_str = fault_type.value if hasattr(fault_type, 'value') else str(fault_type)

        if fault_type_str.startswith("network"):
            return self.injectors.get("network")
        elif fault_type_str.startswith("pod") or fault_type_str.startswith("container"):
            return self.injectors.get("pod")
        elif fault_type_str in ["cpu_stress", "memory_stress", "disk_fill", "fd_exhaust"]:
            return self.injectors.get("resource")
        elif fault_type_str.startswith("http") or fault_type_str == "circuit_breaker_trigger":
            return self.injectors.get("application")

        return None

    async def _rollback_all_injections(self, experiment: ChaosExperiment) -> bool:
        """Rollback de todas as injeções de um experimento."""
        success = True

        for injection in experiment.fault_injections:
            if injection.status != "active":
                continue

            injector = self._get_injector_for_fault(injection.fault_type)
            if not injector:
                continue

            try:
                result = await injector.rollback(injection.id)
                if not result.success:
                    success = False
                    logger.warning(
                        "chaos_engine.rollback_failed",
                        injection_id=injection.id,
                        error=result.error_message
                    )
            except Exception as e:
                success = False
                logger.error(
                    "chaos_engine.rollback_error",
                    injection_id=injection.id,
                    error=str(e)
                )

        return success

    def _generate_report(
        self,
        experiment: ChaosExperiment,
        injection_results: List[Any],
        validation_results: List[ValidationResult],
        blast_radius: int,
        duration: float,
    ) -> ExperimentReport:
        """Gera relatório do experimento."""
        # Determinar resultado
        if experiment.status == ChaosExperimentStatus.COMPLETED:
            outcome = "success"
            failure_reason = None
        else:
            outcome = "failure"
            # Identificar razão da falha
            failed_validations = [v for v in validation_results if not v.success]
            if failed_validations:
                failure_reason = f"Validações falharam: {[v.playbook_name for v in failed_validations]}"
            else:
                failure_reason = "Falha durante execução do experimento"

        # Gerar recomendações
        recommendations = self._generate_recommendations(
            experiment,
            validation_results,
            blast_radius
        )

        # Coletar playbooks trigados
        playbooks_triggered = list(set(
            v.playbook_name for v in validation_results
        ))

        return ExperimentReport(
            experiment_id=experiment.id,
            experiment_name=experiment.name,
            environment=experiment.environment,
            start_time=experiment.started_at or datetime.utcnow(),
            end_time=experiment.completed_at or datetime.utcnow(),
            duration_seconds=duration,
            status=experiment.status,
            fault_injections=experiment.fault_injections,
            validations=validation_results,
            blast_radius=blast_radius,
            playbooks_triggered=playbooks_triggered,
            outcome=outcome,
            failure_reason=failure_reason,
            recommendations=recommendations,
            metrics_summary={
                "total_injections": len(experiment.fault_injections),
                "successful_injections": sum(
                    1 for r in injection_results if r.success
                ),
                "total_validations": len(validation_results),
                "passed_validations": sum(
                    1 for v in validation_results if v.success
                ),
            }
        )

    def _generate_recommendations(
        self,
        experiment: ChaosExperiment,
        validation_results: List[ValidationResult],
        blast_radius: int,
    ) -> List[str]:
        """Gera recomendações baseadas nos resultados."""
        recommendations = []

        # Análise de validações
        failed_validations = [v for v in validation_results if not v.success]

        for validation in failed_validations:
            if validation.recovery_time_seconds:
                if validation.recovery_time_seconds > 300:
                    recommendations.append(
                        f"Tempo de recuperação para '{validation.playbook_name}' "
                        f"({validation.recovery_time_seconds:.0f}s) está alto. "
                        "Considere otimizar o playbook."
                    )

            for criterion, met in validation.criteria_met.items():
                if not met:
                    if criterion == "availability":
                        recommendations.append(
                            "Disponibilidade abaixo do esperado durante recuperação. "
                            "Considere adicionar réplicas ou melhorar health checks."
                        )
                    elif criterion == "error_rate":
                        recommendations.append(
                            "Taxa de erros elevada durante recuperação. "
                            "Verifique circuit breakers e retry policies."
                        )

        # Análise de blast radius
        if blast_radius > experiment.blast_radius_limit * 0.8:
            recommendations.append(
                f"Blast radius ({blast_radius}) próximo do limite "
                f"({experiment.blast_radius_limit}). "
                "Considere aumentar réplicas para maior resiliência."
            )

        if not recommendations:
            recommendations.append(
                "Experimento concluído com sucesso. "
                "Sistema demonstrou boa resiliência."
            )

        return recommendations

    async def _get_experiment(
        self,
        experiment_id: str
    ) -> Optional[ChaosExperiment]:
        """
        Busca experimento primeiro no cache em memória, depois no MongoDB.

        Permite operação sem MongoDB usando o cache em memória como fallback.
        """
        # Verificar primeiro no cache em memória
        if experiment_id in self._experiment_cache:
            logger.debug(
                "chaos_engine.experiment_from_cache",
                experiment_id=experiment_id
            )
            return self._experiment_cache[experiment_id]

        # Verificar experimentos ativos
        if experiment_id in self._active_experiments:
            return self._active_experiments[experiment_id]

        # Fallback para MongoDB se disponível
        if not self.mongodb_client:
            logger.warning(
                "chaos_engine.no_mongodb_no_cache",
                experiment_id=experiment_id,
                note="Experimento não encontrado no cache e MongoDB indisponível"
            )
            return None

        try:
            doc = await self.mongodb_client.find_one(
                "chaos_experiments",
                {"id": experiment_id}
            )
            if doc:
                return ChaosExperiment(**doc)
        except Exception as e:
            logger.error(
                "chaos_engine.get_experiment_failed",
                experiment_id=experiment_id,
                error=str(e)
            )

        return None

    async def _persist_experiment(self, experiment: ChaosExperiment):
        """Persiste experimento no MongoDB."""
        if not self.mongodb_client:
            return

        try:
            await self.mongodb_client.insert_one(
                "chaos_experiments",
                experiment.model_dump(mode="json")
            )
        except Exception as e:
            logger.error(
                "chaos_engine.persist_experiment_failed",
                experiment_id=experiment.id,
                error=str(e)
            )

    async def _update_experiment_status(self, experiment: ChaosExperiment):
        """Atualiza status do experimento no MongoDB."""
        if not self.mongodb_client:
            return

        try:
            await self.mongodb_client.update_one(
                "chaos_experiments",
                {"id": experiment.id},
                {"$set": experiment.model_dump(mode="json")}
            )
        except Exception as e:
            logger.error(
                "chaos_engine.update_experiment_failed",
                experiment_id=experiment.id,
                error=str(e)
            )

    async def _persist_report(self, report: ExperimentReport):
        """Persiste relatório no MongoDB."""
        if not self.mongodb_client:
            return

        try:
            await self.mongodb_client.insert_one(
                "chaos_reports",
                report.model_dump(mode="json")
            )
        except Exception as e:
            logger.error(
                "chaos_engine.persist_report_failed",
                experiment_id=report.experiment_id,
                error=str(e)
            )

    async def _publish_event(
        self,
        event_type: str,
        experiment: ChaosExperiment
    ):
        """Publica evento no Kafka."""
        if not self.kafka_producer:
            return

        try:
            event = {
                "event_type": event_type,
                "experiment_id": experiment.id,
                "experiment_name": experiment.name,
                "status": experiment.status.value,
                "environment": experiment.environment,
                "timestamp": datetime.utcnow().isoformat(),
            }

            await self.kafka_producer.send(
                KAFKA_TOPICS["experiments"],
                event
            )
        except Exception as e:
            logger.warning(
                "chaos_engine.publish_event_failed",
                event_type=event_type,
                error=str(e)
            )
