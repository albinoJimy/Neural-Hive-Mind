"""
Biblioteca de Cenários de Chaos Engineering.

Fornece cenários pré-definidos para testes comuns de resiliência,
cada um configurado para validar playbooks específicos.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog

from ..chaos_models import (
    ChaosExperiment,
    ChaosExperimentStatus,
    FaultInjection,
    FaultParameters,
    FaultType,
    RollbackStrategy,
    ScenarioConfig,
    TargetSelector,
    ValidationCriteria,
)
from ..chaos_config import (
    PLAYBOOK_FAULT_MAPPING,
    get_default_timeout,
)

logger = structlog.get_logger(__name__)


class ScenarioLibrary:
    """
    Biblioteca de cenários pré-definidos para Chaos Engineering.

    Cada cenário representa um teste comum de resiliência e está
    configurado para validar playbooks específicos do Self-Healing Engine.
    """

    def __init__(self):
        """Inicializa a biblioteca de cenários."""
        self._scenarios = {
            "pod_failure": self.pod_failure_scenario,
            "network_partition": self.network_partition_scenario,
            "resource_exhaustion": self.resource_exhaustion_scenario,
            "cascading_failure": self.cascading_failure_scenario,
            "slow_dependency": self.slow_dependency_scenario,
        }

    def list_scenarios(self) -> List[str]:
        """Lista todos os cenários disponíveis."""
        return list(self._scenarios.keys())

    def get_scenario_info(self, scenario_name: str) -> Optional[Dict[str, Any]]:
        """Retorna informações sobre um cenário específico."""
        scenarios_info = {
            "pod_failure": {
                "name": "Pod Failure",
                "description": "Simula falha de pod para validar recuperação automática",
                "playbook": "restart-pod",
                "fault_types": [FaultType.POD_KILL],
                "typical_duration": 180,
                "risk_level": "low"
            },
            "network_partition": {
                "name": "Network Partition",
                "description": "Simula particionamento de rede entre serviços",
                "playbook": "check-network-connectivity",
                "fault_types": [FaultType.NETWORK_PARTITION],
                "typical_duration": 300,
                "risk_level": "medium"
            },
            "resource_exhaustion": {
                "name": "Resource Exhaustion",
                "description": "Simula esgotamento de CPU/memória para testar auto-scaling",
                "playbook": "scale-up-deployment",
                "fault_types": [FaultType.CPU_STRESS, FaultType.MEMORY_STRESS],
                "typical_duration": 300,
                "risk_level": "medium"
            },
            "cascading_failure": {
                "name": "Cascading Failure",
                "description": "Simula falha em cadeia para testar circuit breakers",
                "playbook": None,
                "fault_types": [FaultType.POD_KILL, FaultType.HTTP_ERROR],
                "typical_duration": 600,
                "risk_level": "high"
            },
            "slow_dependency": {
                "name": "Slow Dependency",
                "description": "Simula dependência lenta para testar timeouts e fallbacks",
                "playbook": None,
                "fault_types": [FaultType.HTTP_DELAY, FaultType.NETWORK_LATENCY],
                "typical_duration": 180,
                "risk_level": "low"
            }
        }
        return scenarios_info.get(scenario_name)

    def create_scenario(
        self,
        scenario_name: str,
        config: ScenarioConfig,
    ) -> ChaosExperiment:
        """
        Cria experimento a partir de um cenário pré-definido.

        Args:
            scenario_name: Nome do cenário
            config: Configuração do cenário

        Returns:
            ChaosExperiment configurado

        Raises:
            ValueError: Se cenário não existe
        """
        if scenario_name not in self._scenarios:
            raise ValueError(
                f"Cenário '{scenario_name}' não encontrado. "
                f"Disponíveis: {self.list_scenarios()}"
            )

        scenario_func = self._scenarios[scenario_name]
        return scenario_func(config)

    def pod_failure_scenario(self, config: ScenarioConfig) -> ChaosExperiment:
        """
        Cenário: Simula falha de pod + valida playbook restart_pod.

        Este cenário:
        1. Mata um ou mais pods do serviço alvo
        2. Aguarda detecção pelo Self-Healing Engine
        3. Valida execução do playbook restart-pod
        4. Mede tempo de recuperação
        """
        target = TargetSelector(
            namespace=config.target_namespace,
            service_name=config.target_service,
            labels={"app": config.target_service},
            percentage=config.custom_parameters.get("pod_percentage", 50)
        )

        injection = FaultInjection(
            fault_type=FaultType.POD_KILL,
            target=target,
            parameters=FaultParameters(),
            duration_seconds=get_default_timeout("pod_kill"),
        )

        criteria = ValidationCriteria(
            max_recovery_time_seconds=config.custom_parameters.get(
                "max_recovery_time", 180
            ),
            min_availability_percent=config.custom_parameters.get(
                "min_availability", 99.0
            ),
            max_error_rate_percent=config.custom_parameters.get(
                "max_error_rate", 5.0
            ),
            required_playbook=config.playbook_to_validate or "restart-pod"
        )

        return ChaosExperiment(
            name=f"Pod Failure - {config.target_service}",
            description=config.description,
            environment=config.custom_parameters.get("environment", "staging"),
            fault_injections=[injection],
            validation_criteria=criteria,
            rollback_strategy=RollbackStrategy.AUTOMATIC,
            timeout_seconds=300,
            blast_radius_limit=config.custom_parameters.get("blast_radius_limit", 3),
            metadata={
                "scenario": "pod_failure",
                "target_service": config.target_service,
            }
        )

    def network_partition_scenario(self, config: ScenarioConfig) -> ChaosExperiment:
        """
        Cenário: Particionamento de rede entre serviços.

        Este cenário:
        1. Cria NetworkPolicy bloqueando tráfego
        2. Observa comportamento de circuit breakers
        3. Valida reconexão após remoção da partição
        4. Mede impacto em latência e erros
        """
        target = TargetSelector(
            namespace=config.target_namespace,
            service_name=config.target_service,
            labels={"app": config.target_service},
        )

        injection = FaultInjection(
            fault_type=FaultType.NETWORK_PARTITION,
            target=target,
            parameters=FaultParameters(),
            duration_seconds=config.custom_parameters.get("partition_duration", 60),
        )

        criteria = ValidationCriteria(
            max_recovery_time_seconds=config.custom_parameters.get(
                "max_recovery_time", 120
            ),
            min_availability_percent=config.custom_parameters.get(
                "min_availability", 95.0  # Menor pois há partição
            ),
            max_error_rate_percent=config.custom_parameters.get(
                "max_error_rate", 20.0
            ),
            required_playbook=config.playbook_to_validate
        )

        return ChaosExperiment(
            name=f"Network Partition - {config.target_service}",
            description=config.description,
            environment=config.custom_parameters.get("environment", "staging"),
            fault_injections=[injection],
            validation_criteria=criteria,
            rollback_strategy=RollbackStrategy.AUTOMATIC,
            timeout_seconds=300,
            blast_radius_limit=config.custom_parameters.get("blast_radius_limit", 5),
            metadata={
                "scenario": "network_partition",
                "target_service": config.target_service,
            }
        )

    def resource_exhaustion_scenario(self, config: ScenarioConfig) -> ChaosExperiment:
        """
        Cenário: Esgotamento de recursos (CPU/Memory).

        Este cenário:
        1. Aplica stress de CPU ou memória
        2. Observa triggering de HPA/VPA
        3. Valida execução do playbook scale-up
        4. Mede tempo de resposta do auto-scaling
        """
        resource_type = config.custom_parameters.get("resource_type", "cpu")
        target = TargetSelector(
            namespace=config.target_namespace,
            service_name=config.target_service,
            labels={"app": config.target_service},
            percentage=100  # Stress em todos os pods
        )

        if resource_type == "memory":
            fault_type = FaultType.MEMORY_STRESS
            params = FaultParameters(
                memory_bytes=config.custom_parameters.get(
                    "memory_bytes", 512 * 1024 * 1024  # 512MB
                )
            )
        else:
            fault_type = FaultType.CPU_STRESS
            params = FaultParameters(
                cpu_cores=config.custom_parameters.get("cpu_cores", 2),
                cpu_load_percent=config.custom_parameters.get("cpu_load", 80)
            )

        injection = FaultInjection(
            fault_type=fault_type,
            target=target,
            parameters=params,
            duration_seconds=config.custom_parameters.get("stress_duration", 120),
        )

        criteria = ValidationCriteria(
            max_recovery_time_seconds=config.custom_parameters.get(
                "max_recovery_time", 300
            ),
            min_availability_percent=config.custom_parameters.get(
                "min_availability", 99.0
            ),
            max_error_rate_percent=config.custom_parameters.get(
                "max_error_rate", 5.0
            ),
            max_latency_p95_ms=config.custom_parameters.get(
                "max_latency_p95", 1000
            ),
            required_playbook=config.playbook_to_validate or "scale-up-deployment"
        )

        return ChaosExperiment(
            name=f"Resource Exhaustion ({resource_type}) - {config.target_service}",
            description=config.description,
            environment=config.custom_parameters.get("environment", "staging"),
            fault_injections=[injection],
            validation_criteria=criteria,
            rollback_strategy=RollbackStrategy.AUTOMATIC,
            timeout_seconds=600,
            blast_radius_limit=config.custom_parameters.get("blast_radius_limit", 5),
            metadata={
                "scenario": "resource_exhaustion",
                "resource_type": resource_type,
                "target_service": config.target_service,
            }
        )

    def cascading_failure_scenario(self, config: ScenarioConfig) -> ChaosExperiment:
        """
        Cenário: Falha em cadeia para testar circuit breakers.

        Este cenário:
        1. Mata pods de um serviço dependência
        2. Adiciona erros HTTP no serviço
        3. Observa propagação e contenção
        4. Valida que circuit breakers são acionados
        """
        dependency_service = config.custom_parameters.get(
            "dependency_service",
            f"{config.target_service}-db"
        )

        target_main = TargetSelector(
            namespace=config.target_namespace,
            service_name=config.target_service,
            labels={"app": config.target_service},
        )

        target_dependency = TargetSelector(
            namespace=config.target_namespace,
            service_name=dependency_service,
            labels={"app": dependency_service},
        )

        # Primeira injeção: matar pods da dependência
        injection1 = FaultInjection(
            fault_type=FaultType.POD_KILL,
            target=target_dependency,
            parameters=FaultParameters(),
            duration_seconds=30,
        )

        # Segunda injeção: erros HTTP no serviço principal
        injection2 = FaultInjection(
            fault_type=FaultType.HTTP_ERROR,
            target=target_main,
            parameters=FaultParameters(
                http_status_code=503,
            ),
            duration_seconds=60,
        )

        criteria = ValidationCriteria(
            max_recovery_time_seconds=config.custom_parameters.get(
                "max_recovery_time", 300
            ),
            min_availability_percent=config.custom_parameters.get(
                "min_availability", 90.0  # Mais relaxado para cascading
            ),
            max_error_rate_percent=config.custom_parameters.get(
                "max_error_rate", 30.0
            ),
            required_playbook=config.playbook_to_validate
        )

        return ChaosExperiment(
            name=f"Cascading Failure - {config.target_service}",
            description=config.description,
            environment=config.custom_parameters.get("environment", "staging"),
            fault_injections=[injection1, injection2],
            validation_criteria=criteria,
            rollback_strategy=RollbackStrategy.AUTOMATIC,
            timeout_seconds=600,
            blast_radius_limit=config.custom_parameters.get("blast_radius_limit", 5),
            metadata={
                "scenario": "cascading_failure",
                "target_service": config.target_service,
                "dependency_service": dependency_service,
            }
        )

    def slow_dependency_scenario(self, config: ScenarioConfig) -> ChaosExperiment:
        """
        Cenário: Dependência lenta para testar timeouts e fallbacks.

        Este cenário:
        1. Adiciona latência em chamadas para dependência
        2. Observa comportamento de timeouts
        3. Valida acionamento de fallbacks
        4. Mede degradação de performance
        """
        target = TargetSelector(
            namespace=config.target_namespace,
            service_name=config.target_service,
            labels={"app": config.target_service},
            percentage=config.custom_parameters.get("affected_percentage", 50)
        )

        latency_ms = config.custom_parameters.get("latency_ms", 2000)
        jitter_ms = config.custom_parameters.get("jitter_ms", 500)

        injection = FaultInjection(
            fault_type=FaultType.HTTP_DELAY,
            target=target,
            parameters=FaultParameters(
                http_delay_ms=latency_ms,
            ),
            duration_seconds=config.custom_parameters.get("delay_duration", 120),
        )

        criteria = ValidationCriteria(
            max_recovery_time_seconds=config.custom_parameters.get(
                "max_recovery_time", 60
            ),
            min_availability_percent=config.custom_parameters.get(
                "min_availability", 99.0
            ),
            max_error_rate_percent=config.custom_parameters.get(
                "max_error_rate", 10.0
            ),
            max_latency_p95_ms=config.custom_parameters.get(
                "max_latency_p95",
                latency_ms + 1000  # Latência injetada + buffer
            ),
            required_playbook=config.playbook_to_validate
        )

        return ChaosExperiment(
            name=f"Slow Dependency - {config.target_service}",
            description=config.description,
            environment=config.custom_parameters.get("environment", "staging"),
            fault_injections=[injection],
            validation_criteria=criteria,
            rollback_strategy=RollbackStrategy.AUTOMATIC,
            timeout_seconds=300,
            blast_radius_limit=config.custom_parameters.get("blast_radius_limit", 5),
            metadata={
                "scenario": "slow_dependency",
                "target_service": config.target_service,
                "injected_latency_ms": latency_ms,
            }
        )

    def create_custom_scenario(
        self,
        name: str,
        description: str,
        fault_injections: List[FaultInjection],
        validation_criteria: ValidationCriteria,
        environment: str = "staging",
        rollback_strategy: RollbackStrategy = RollbackStrategy.AUTOMATIC,
        timeout_seconds: int = 600,
        blast_radius_limit: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChaosExperiment:
        """
        Cria um cenário customizado.

        Args:
            name: Nome do experimento
            description: Descrição
            fault_injections: Lista de injeções de falha
            validation_criteria: Critérios de validação
            environment: Ambiente de execução
            rollback_strategy: Estratégia de rollback
            timeout_seconds: Timeout total
            blast_radius_limit: Limite de blast radius
            metadata: Metadados adicionais

        Returns:
            ChaosExperiment configurado
        """
        return ChaosExperiment(
            name=name,
            description=description,
            environment=environment,
            fault_injections=fault_injections,
            validation_criteria=validation_criteria,
            rollback_strategy=rollback_strategy,
            timeout_seconds=timeout_seconds,
            blast_radius_limit=blast_radius_limit,
            metadata=metadata or {"scenario": "custom"}
        )

    def get_recommended_scenarios(
        self,
        service_type: str,
    ) -> List[str]:
        """
        Retorna cenários recomendados para um tipo de serviço.

        Args:
            service_type: Tipo de serviço (api, worker, database, cache)

        Returns:
            Lista de nomes de cenários recomendados
        """
        recommendations = {
            "api": ["pod_failure", "slow_dependency", "network_partition"],
            "worker": ["pod_failure", "resource_exhaustion"],
            "database": ["network_partition", "resource_exhaustion"],
            "cache": ["pod_failure", "resource_exhaustion"],
            "gateway": ["pod_failure", "slow_dependency", "cascading_failure"],
        }

        return recommendations.get(service_type, ["pod_failure"])
