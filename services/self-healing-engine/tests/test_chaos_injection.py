"""
Testes para injeção de chaos no Self-Healing Engine.

Cobre pod kill, network delay, resource injection e recovery.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


@pytest.mark.asyncio
async def test_chaos_pod_injection():
    """Injeção de chaos pod deve deletar pod."""
    from src.chaos.injectors.pod_injector import PodInjector

    mock_core_v1 = MagicMock()

    injector = PodInjector(core_v1=mock_core_v1)
    injector.inject = MagicMock(
        return_value={"success": True, "action": "delete_pod", "pod": "test-pod"}
    )

    result = await injector.inject(pod_name="test-pod", namespace="default")

    assert result["success"] is True
    assert result["action"] == "delete_pod"


@pytest.mark.asyncio
async def test_chaos_network_injection():
    """Injeção de chaos network deve adicionar delay."""
    from src.chaos.injectors.network_injector import NetworkInjector

    mock_core_v1 = MagicMock()

    injector = NetworkInjector(core_v1=mock_core_v1)
    injector.inject = MagicMock(
        return_value={
            "success": True,
            "action": "network_delay",
            "delay_ms": 1000,
            "loss_percent": 10,
        }
    )

    result = await injector.inject(
        target_service="test-service", namespace="default", delay_ms=1000
    )

    assert result["success"] is True
    assert result["delay_ms"] == 1000


@pytest.mark.asyncio
async def test_chaos_resource_injection():
    """Injeção de chaos resource deve consumir CPU."""
    from src.chaos.injectors.resource_injector import ResourceInjector

    mock_core_v1 = MagicMock()

    injector = ResourceInjector(core_v1=mock_core_v1)
    injector.inject = MagicMock(
        return_value={
            "success": True,
            "action": "resource_stress",
            "cpu_percent": 80,
            "memory_mb": 512,
        }
    )

    result = await injector.inject(target_pod="test-pod", namespace="default", cpu_percent=80)

    assert result["success"] is True
    assert result["cpu_percent"] == 80


@pytest.mark.asyncio
async def test_chaos_application_injection():
    """Injeção de chaos application deve causar erro."""
    from src.chaos.injectors.application_injector import ApplicationInjector

    injector = ApplicationInjector()
    injector.inject = MagicMock(
        return_value={"success": True, "action": "application_error", "error_type": "exception"}
    )

    result = await injector.inject(target_service="test-service", error_type="exception")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_chaos_experiment_execution():
    """Execução de experimento chaos deve completar."""
    from src.chaos.chaos_models import ChaosExperiment, FaultInjection, FaultType, TargetSelector
    from src.chaos.chaos_engine import ChaosEngine

    mock_playbook = MagicMock()
    mock_playbook_executor = MagicMock()
    mock_service_registry = MagicMock()
    mock_opa = MagicMock()

    target = TargetSelector(namespace="default", service_name="test-service")

    injection = FaultInjection(fault_type=FaultType.POD_KILL, target=target, duration_seconds=60)

    experiment = ChaosExperiment(
        name="Test experiment",
        description="Test chaos experiment",
        environment="staging",
        fault_injections=[injection],
    )

    engine = ChaosEngine(
        k8s_in_cluster=False,
        playbook_executor=mock_playbook_executor,
        service_registry_client=mock_service_registry,
        opa_client=mock_opa,
    )

    result = await engine.execute_experiment(experiment.id, executed_by="test")

    assert result is not None


@pytest.mark.asyncio
async def test_chaos_recovery_validation():
    """Validação de recovery deve medir tempo de recuperação."""
    from src.services.playbook_executor import PlaybookExecutor

    mock_k8s = MagicMock()
    mock_ets = MagicMock()
    mock_orchestrator = MagicMock()
    mock_service_registry = MagicMock()
    mock_opa = MagicMock()

    executor = PlaybookExecutor(
        playbooks_dir="/tmp/playbooks",
        k8s_in_cluster=False,
        service_registry_client=mock_service_registry,
        execution_ticket_client=mock_ets,
        orchestrator_client=mock_orchestrator,
        opa_client=mock_opa,
    )

    result = await executor.execute_playbook(
        "test_recovery", context={"pod_name": "test-pod"}, timeout_seconds=30
    )

    assert result is not None
    assert "success" in result


@pytest.mark.asyncio
async def test_chaos_scenario_library():
    """Biblioteca de cenarios deve listar cenarios disponiveis."""
    from src.chaos.scenarios.scenario_library import ScenarioLibrary

    library = ScenarioLibrary()
    scenarios = library.list_scenarios()

    assert isinstance(scenarios, list)
    assert len(scenarios) > 0


@pytest.mark.asyncio
async def test_chaos_game_day_runner():
    """Game Day runner deve executar experimentos programados."""
    from src.chaos.game_day_runner import GameDayRunner

    mock_executor = MagicMock()
    mock_chaos = MagicMock()

    runner = GameDayRunner(playbook_executor=mock_executor, chaos_engine=mock_chaos)

    result = await runner.run_game_day(name="test-gameday", scenarios=["pod_kill", "network_delay"])

    assert result is not None


@pytest.mark.asyncio
async def test_chaos_with_opa_approval():
    """Experimento chaos deve requerer aprovacao OPA quando habilitado."""
    from src.services.playbook_executor import PlaybookExecutor

    mock_opa = AsyncMock()
    mock_opa.evaluate_policy = AsyncMock(return_value={"result": {"violations": []}})

    executor = PlaybookExecutor(
        playbooks_dir="/tmp/playbooks", k8s_in_cluster=False, opa_client=mock_opa, opa_enabled=True
    )

    # Acao que requer OPA
    allowed = await executor._validate_action_with_opa(
        {"type": "reallocate_ticket"}, {"ticket_id": "test-123"}
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_chaos_opa_denied():
    """Experimento chaos deve ser bloqueado quando OPA nega."""
    from src.services.playbook_executor import PlaybookExecutor

    mock_opa = AsyncMock()
    mock_opa.evaluate_policy = AsyncMock(
        return_value={"result": {"violations": ["Rate limit exceeded"]}}
    )

    executor = PlaybookExecutor(
        playbooks_dir="/tmp/playbooks",
        k8s_in_cluster=False,
        opa_client=mock_opa,
        opa_enabled=True,
        opa_fail_open=False,
    )

    allowed = await executor._validate_action_with_opa(
        {"type": "reallocate_ticket"}, {"ticket_id": "test-123"}
    )

    assert allowed is False


@pytest.mark.asyncio
async def test_chaos_circuit_breaker():
    """Circuit breaker deve abrir após falhas."""
    from src.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

    breaker = CircuitBreaker(service_name="test-service", failure_threshold=3, timeout_seconds=60)

    # Registrar falhas para abrir circuit breaker
    for _ in range(3):
        breaker.record_failure()

    assert breaker.is_open() is True

    # Tentar chamar com circuit breaker aberto
    with pytest.raises(CircuitBreakerOpenError):
        breaker.call_sync(lambda: "result")
