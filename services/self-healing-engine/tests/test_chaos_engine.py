"""
Testes para o módulo de Chaos Engineering.

Testa os componentes principais:
- ChaosEngine
- FaultInjectors
- Validators
- ScenarioLibrary
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.chaos.chaos_models import (
    ChaosExperiment,
    ChaosExperimentRequest,
    ChaosExperimentStatus,
    FaultInjection,
    FaultParameters,
    FaultType,
    RollbackStrategy,
    ScenarioConfig,
    TargetSelector,
    ValidationCriteria,
    ValidationResult,
)
from src.chaos.chaos_engine import ChaosEngine
from src.chaos.scenarios.scenario_library import ScenarioLibrary
from src.chaos.injectors.base_injector import InjectionResult


class TestChaosModels:
    """Testes para os modelos Pydantic de chaos."""

    def test_target_selector_defaults(self):
        """Testa valores default do TargetSelector."""
        target = TargetSelector(namespace="default")
        assert target.namespace == "default"
        assert target.percentage == 100
        assert target.labels == {}

    def test_fault_parameters_defaults(self):
        """Testa valores default do FaultParameters."""
        params = FaultParameters()
        assert params.latency_ms is None
        assert params.cpu_cores is None

    def test_validation_criteria_defaults(self):
        """Testa valores default do ValidationCriteria."""
        criteria = ValidationCriteria()
        assert criteria.max_recovery_time_seconds == 300
        assert criteria.min_availability_percent == 99.0
        assert criteria.max_error_rate_percent == 5.0

    def test_fault_injection_creation(self):
        """Testa criação de FaultInjection."""
        target = TargetSelector(
            namespace="test-ns",
            service_name="test-service"
        )
        injection = FaultInjection(
            fault_type=FaultType.POD_KILL,
            target=target,
            duration_seconds=60
        )
        assert injection.fault_type == FaultType.POD_KILL
        assert injection.target.namespace == "test-ns"
        assert injection.duration_seconds == 60

    def test_chaos_experiment_creation(self):
        """Testa criação de ChaosExperiment."""
        target = TargetSelector(namespace="default")
        injection = FaultInjection(
            fault_type=FaultType.POD_KILL,
            target=target
        )
        experiment = ChaosExperiment(
            name="Test Experiment",
            description="Test description",
            environment="staging",
            fault_injections=[injection]
        )
        assert experiment.name == "Test Experiment"
        assert experiment.status == ChaosExperimentStatus.PLANNED
        assert len(experiment.fault_injections) == 1

    def test_chaos_experiment_request(self):
        """Testa ChaosExperimentRequest."""
        target = TargetSelector(
            namespace="default",
            service_name="test-service"
        )
        injection = FaultInjection(
            fault_type=FaultType.POD_KILL,
            target=target
        )
        request = ChaosExperimentRequest(
            name="Test",
            description="Test",
            environment="staging",
            fault_injections=[injection]
        )
        assert request.fault_injections[0].target.service_name == "test-service"


class TestScenarioLibrary:
    """Testes para a biblioteca de cenários."""

    def setup_method(self):
        """Setup para cada teste."""
        self.library = ScenarioLibrary()

    def test_list_scenarios(self):
        """Testa listagem de cenários."""
        scenarios = self.library.list_scenarios()
        assert "pod_failure" in scenarios
        assert "network_partition" in scenarios
        assert "resource_exhaustion" in scenarios
        assert "cascading_failure" in scenarios
        assert "slow_dependency" in scenarios

    def test_get_scenario_info(self):
        """Testa obtenção de informações de cenário."""
        info = self.library.get_scenario_info("pod_failure")
        assert info is not None
        assert info["name"] == "Pod Failure"
        assert "playbook" in info
        assert info["risk_level"] == "low"

    def test_get_scenario_info_invalid(self):
        """Testa cenário inexistente."""
        info = self.library.get_scenario_info("invalid_scenario")
        assert info is None

    def test_pod_failure_scenario(self):
        """Testa criação de cenário pod_failure."""
        config = ScenarioConfig(
            name="Test Pod Failure",
            description="Test description",
            target_service="worker-agents",
            target_namespace="neural-hive-execution"
        )
        experiment = self.library.pod_failure_scenario(config)
        assert experiment.name == "Pod Failure - worker-agents"
        assert len(experiment.fault_injections) == 1
        assert experiment.fault_injections[0].fault_type == FaultType.POD_KILL

    def test_network_partition_scenario(self):
        """Testa criação de cenário network_partition."""
        config = ScenarioConfig(
            name="Test Network Partition",
            description="Test description",
            target_service="consensus-engine",
            target_namespace="neural-hive-orchestration"
        )
        experiment = self.library.network_partition_scenario(config)
        assert experiment.name == "Network Partition - consensus-engine"
        assert experiment.fault_injections[0].fault_type == FaultType.NETWORK_PARTITION

    def test_resource_exhaustion_scenario_cpu(self):
        """Testa cenário resource_exhaustion com CPU."""
        config = ScenarioConfig(
            name="Test CPU Stress",
            description="Test description",
            target_service="optimizer-agents",
            target_namespace="neural-hive-orchestration",
            custom_parameters={"resource_type": "cpu"}
        )
        experiment = self.library.resource_exhaustion_scenario(config)
        assert experiment.fault_injections[0].fault_type == FaultType.CPU_STRESS

    def test_resource_exhaustion_scenario_memory(self):
        """Testa cenário resource_exhaustion com memória."""
        config = ScenarioConfig(
            name="Test Memory Stress",
            description="Test description",
            target_service="optimizer-agents",
            target_namespace="neural-hive-orchestration",
            custom_parameters={"resource_type": "memory"}
        )
        experiment = self.library.resource_exhaustion_scenario(config)
        assert experiment.fault_injections[0].fault_type == FaultType.MEMORY_STRESS

    def test_cascading_failure_scenario(self):
        """Testa cenário cascading_failure."""
        config = ScenarioConfig(
            name="Test Cascading",
            description="Test description",
            target_service="gateway-intencoes",
            target_namespace="neural-hive-execution"
        )
        experiment = self.library.cascading_failure_scenario(config)
        assert len(experiment.fault_injections) == 2
        fault_types = [i.fault_type for i in experiment.fault_injections]
        assert FaultType.POD_KILL in fault_types
        assert FaultType.HTTP_ERROR in fault_types

    def test_slow_dependency_scenario(self):
        """Testa cenário slow_dependency."""
        config = ScenarioConfig(
            name="Test Slow Dependency",
            description="Test description",
            target_service="mcp-tool-catalog",
            target_namespace="neural-hive-mcp",
            custom_parameters={"latency_ms": 3000}
        )
        experiment = self.library.slow_dependency_scenario(config)
        assert experiment.fault_injections[0].fault_type == FaultType.HTTP_DELAY

    def test_create_scenario_valid(self):
        """Testa criação de cenário válido."""
        config = ScenarioConfig(
            name="Test",
            description="Test",
            target_service="test-service",
            target_namespace="default"
        )
        experiment = self.library.create_scenario("pod_failure", config)
        assert experiment is not None

    def test_create_scenario_invalid(self):
        """Testa criação de cenário inválido."""
        config = ScenarioConfig(
            name="Test",
            description="Test",
            target_service="test-service",
            target_namespace="default"
        )
        with pytest.raises(ValueError):
            self.library.create_scenario("invalid_scenario", config)

    def test_get_recommended_scenarios(self):
        """Testa recomendações de cenários por tipo de serviço."""
        api_scenarios = self.library.get_recommended_scenarios("api")
        assert "pod_failure" in api_scenarios
        assert "slow_dependency" in api_scenarios

        worker_scenarios = self.library.get_recommended_scenarios("worker")
        assert "pod_failure" in worker_scenarios
        assert "resource_exhaustion" in worker_scenarios

    def test_custom_scenario(self):
        """Testa criação de cenário customizado."""
        target = TargetSelector(
            namespace="custom-ns",
            service_name="custom-service"
        )
        injection = FaultInjection(
            fault_type=FaultType.HTTP_ERROR,
            target=target,
            parameters=FaultParameters(http_status_code=503)
        )
        criteria = ValidationCriteria(
            max_recovery_time_seconds=120
        )
        experiment = self.library.create_custom_scenario(
            name="Custom Scenario",
            description="Custom test",
            fault_injections=[injection],
            validation_criteria=criteria
        )
        assert experiment.name == "Custom Scenario"
        assert experiment.metadata["scenario"] == "custom"


class TestChaosEngine:
    """Testes para o ChaosEngine."""

    @pytest.fixture
    def mock_k8s_client(self):
        """Mock do cliente Kubernetes."""
        with patch("kubernetes.client.CoreV1Api") as mock:
            yield mock

    @pytest.fixture
    def mock_k8s_apps_client(self):
        """Mock do cliente Kubernetes Apps."""
        with patch("kubernetes.client.AppsV1Api") as mock:
            yield mock

    @pytest.fixture
    def chaos_engine(self, mock_k8s_client, mock_k8s_apps_client):
        """Fixture do ChaosEngine."""
        engine = ChaosEngine(
            k8s_in_cluster=False,
            playbook_executor=None,
            service_registry_client=None,
            opa_client=None,
            max_concurrent_experiments=3,
            default_timeout_seconds=600,
            require_opa_approval=False,
            blast_radius_limit=5
        )
        return engine

    def test_engine_initialization(self, chaos_engine):
        """Testa inicialização do engine."""
        assert chaos_engine.max_concurrent_experiments == 3
        assert chaos_engine.default_timeout_seconds == 600
        assert chaos_engine.require_opa_approval is False
        assert chaos_engine.blast_radius_limit == 5

    def test_list_scenarios(self, chaos_engine):
        """Testa listagem de cenários via engine."""
        scenarios = chaos_engine.list_scenarios()
        assert len(scenarios) > 0
        assert "pod_failure" in scenarios

    def test_get_scenario_info(self, chaos_engine):
        """Testa obtenção de info de cenário via engine."""
        info = chaos_engine.get_scenario_info("pod_failure")
        assert info is not None
        assert "name" in info

    def test_get_active_experiments_empty(self, chaos_engine):
        """Testa lista vazia de experimentos ativos."""
        experiments = chaos_engine.get_active_experiments()
        assert len(experiments) == 0


class TestInjectionResult:
    """Testes para InjectionResult."""

    def test_injection_result_success(self):
        """Testa resultado de injeção bem sucedida."""
        result = InjectionResult(
            success=True,
            fault_type=FaultType.POD_KILL,
            target_namespace="default",
            target_service="test-service",
            affected_resources=["pod-1", "pod-2"],
            injection_id="inj-123"
        )
        assert result.success is True
        assert len(result.affected_resources) == 2

    def test_injection_result_failure(self):
        """Testa resultado de injeção falhada."""
        result = InjectionResult(
            success=False,
            fault_type=FaultType.NETWORK_PARTITION,
            target_namespace="default",
            target_service="test-service",
            error_message="Permission denied"
        )
        assert result.success is False
        assert result.error_message == "Permission denied"


class TestValidationCriteria:
    """Testes para critérios de validação."""

    def test_validation_criteria_custom(self):
        """Testa critérios customizados."""
        criteria = ValidationCriteria(
            max_recovery_time_seconds=60,
            min_availability_percent=95.0,
            max_error_rate_percent=10.0,
            max_latency_p95_ms=500,
            required_playbook="restart-pod"
        )
        assert criteria.max_recovery_time_seconds == 60
        assert criteria.min_availability_percent == 95.0
        assert criteria.required_playbook == "restart-pod"


class TestValidationResult:
    """Testes para resultados de validação."""

    def test_validation_result_passed(self):
        """Testa resultado de validação passou."""
        result = ValidationResult(
            playbook_name="test-playbook",
            success=True,
            criteria_met={
                "recovery_time": True,
                "availability": True
            },
            recovery_time_seconds=45.0,
            availability_percent=99.5
        )
        assert result.success is True
        assert len(result.criteria_met) == 2

    def test_validation_result_failed(self):
        """Testa resultado de validação falhou."""
        result = ValidationResult(
            playbook_name="test-playbook",
            success=False,
            criteria_met={
                "recovery_time": False,
                "availability": True
            },
            recovery_time_seconds=180.0,
            availability_percent=98.0,
            observations=["Tempo de recuperação excedeu limite"]
        )
        assert result.success is False
        assert result.criteria_met["recovery_time"] is False
        assert len(result.observations) == 1


class TestChaosExperimentStatus:
    """Testes para status de experimento."""

    def test_status_values(self):
        """Testa valores de status."""
        assert ChaosExperimentStatus.PLANNED.value == "PLANNED"
        assert ChaosExperimentStatus.INJECTING.value == "INJECTING"
        assert ChaosExperimentStatus.VALIDATING.value == "VALIDATING"
        assert ChaosExperimentStatus.RECOVERING.value == "RECOVERING"
        assert ChaosExperimentStatus.COMPLETED.value == "COMPLETED"
        assert ChaosExperimentStatus.FAILED.value == "FAILED"
        assert ChaosExperimentStatus.ROLLED_BACK.value == "ROLLED_BACK"
        assert ChaosExperimentStatus.CANCELLED.value == "CANCELLED"


class TestFaultTypes:
    """Testes para tipos de falha."""

    def test_network_fault_types(self):
        """Testa tipos de falha de rede."""
        assert FaultType.NETWORK_LATENCY.value == "network_latency"
        assert FaultType.NETWORK_PACKET_LOSS.value == "network_packet_loss"
        assert FaultType.NETWORK_PARTITION.value == "network_partition"
        assert FaultType.NETWORK_BANDWIDTH_LIMIT.value == "network_bandwidth_limit"

    def test_pod_fault_types(self):
        """Testa tipos de falha de pod."""
        assert FaultType.POD_KILL.value == "pod_kill"
        assert FaultType.CONTAINER_KILL.value == "container_kill"
        assert FaultType.CONTAINER_PAUSE.value == "container_pause"
        assert FaultType.POD_EVICT.value == "pod_evict"

    def test_resource_fault_types(self):
        """Testa tipos de falha de recursos."""
        assert FaultType.CPU_STRESS.value == "cpu_stress"
        assert FaultType.MEMORY_STRESS.value == "memory_stress"
        assert FaultType.DISK_FILL.value == "disk_fill"
        assert FaultType.FD_EXHAUST.value == "fd_exhaust"

    def test_application_fault_types(self):
        """Testa tipos de falha de aplicação."""
        assert FaultType.HTTP_ERROR.value == "http_error"
        assert FaultType.HTTP_DELAY.value == "http_delay"
        assert FaultType.CIRCUIT_BREAKER_TRIGGER.value == "circuit_breaker_trigger"


class TestRollbackStrategy:
    """Testes para estratégias de rollback."""

    def test_rollback_strategies(self):
        """Testa valores de estratégia de rollback."""
        assert RollbackStrategy.AUTOMATIC.value == "automatic"
        assert RollbackStrategy.MANUAL.value == "manual"
        assert RollbackStrategy.TIMEOUT.value == "timeout"
        assert RollbackStrategy.NONE.value == "none"
