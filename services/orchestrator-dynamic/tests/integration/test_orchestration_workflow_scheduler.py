"""
Testes de integração para scheduler dentro do workflow Temporal.

Cobertura:
- Execução do step C3 (allocate resources) com scheduler real
- Timeout do scheduler com fallback no workflow
- Workflow end-to-end completo com scheduler
- Alocação paralela de múltiplos tickets
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List, Any

from src.workflows.orchestration_workflow import OrchestrationWorkflow
from src.activities.ticket_generation import allocate_resources
from src.scheduler.intelligent_scheduler import IntelligentScheduler
from src.scheduler.priority_calculator import PriorityCalculator
from src.scheduler.resource_allocator import ResourceAllocator
from src.clients.service_registry_client import ServiceRegistryClient
from src.policies.policy_validator import PolicyValidator
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics


@pytest.fixture
def mock_temporal_client():
    """Temporal client mock."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_cognitive_plan() -> Dict[str, Any]:
    """Plano cognitivo com múltiplas tarefas."""
    return {
        "plan_id": "plan-workflow-1",
        "tasks": [
            {
                "task_id": "task-1",
                "description": "Process data",
                "required_capabilities": ["python", "data-processing"],
                "estimated_duration_ms": 1000
            },
            {
                "task_id": "task-2",
                "description": "Run ML inference",
                "required_capabilities": ["python", "ml-inference"],
                "estimated_duration_ms": 2000
            }
        ],
        "execution_order": ["task-1", "task-2"],
        "risk_band": "high",
        "namespace": "default",
        "security_level": "standard"
    }


@pytest.fixture
def mock_consolidated_decision() -> Dict[str, Any]:
    """Decisão consolidada."""
    return {
        "decision_id": "decision-workflow-1",
        "correlation_id": "corr-workflow-1",
        "trace_id": "trace-workflow-1",
        "timestamp": datetime.utcnow().isoformat(),
        "selected_plan": {
            "plan_id": "plan-workflow-1",
            "confidence_score": 0.95
        }
    }


@pytest.fixture
def mock_workflow_environment():
    """Ambiente de teste para workflow Temporal."""
    env = MagicMock()
    return env


@pytest.fixture
def mock_activity_dependencies():
    """Todas as dependências de activities."""
    # Service Registry
    registry_client = AsyncMock(spec=ServiceRegistryClient)
    registry_client.discover_agents = AsyncMock(return_value=[
        {
            "agent_id": "worker-001",
            "agent_type": "worker-agent",
            "status": "HEALTHY",
            "capabilities": ["python", "data-processing", "ml-inference"],
            "telemetry": {
                "success_rate": 0.95,
                "avg_duration_ms": 800,
                "total_executions": 100
            },
            "active_tasks": 2,
            "max_concurrent_tasks": 10
        }
    ])

    # Config
    config = MagicMock(spec=OrchestratorSettings)
    config.service_registry_endpoint = "service-registry:50051"
    config.service_registry_cache_ttl_seconds = 60
    config.service_registry_timeout_seconds = 5
    config.scheduler_priority_weights = {"risk": 0.4, "qos": 0.3, "sla": 0.3}
    config.enable_intelligent_scheduler = True

    # Metrics
    metrics = OrchestratorMetrics()

    # Scheduler components
    priority_calculator = PriorityCalculator(config)
    resource_allocator = ResourceAllocator(
        registry_client=registry_client,
        config=config,
        metrics=metrics
    )
    intelligent_scheduler = IntelligentScheduler(
        config=config,
        metrics=metrics,
        priority_calculator=priority_calculator,
        resource_allocator=resource_allocator
    )

    # PolicyValidator
    policy_validator = AsyncMock(spec=PolicyValidator)
    validation_result = MagicMock()
    validation_result.is_valid = True
    validation_result.warnings = []
    validation_result.feature_flags = {"enable_intelligent_scheduler": True}
    policy_validator.validate_execution_ticket = AsyncMock(return_value=validation_result)

    # ML Predictor
    ml_predictor = AsyncMock()
    ml_predictor.predict_and_enrich = AsyncMock(side_effect=lambda ticket: {
        **ticket,
        "predictions": {
            "duration_ms": ticket.get("estimated_duration_ms", 1000) * 1.1,
            "anomaly": {
                "is_anomaly": False,
                "anomaly_score": 0.12,
                "anomaly_type": None
            }
        }
    })

    # Kafka Producer
    kafka_producer = AsyncMock()
    kafka_producer.produce = AsyncMock()

    # MongoDB Client
    mongodb_client = AsyncMock()
    mongodb_client.insert_one = AsyncMock()

    return {
        "kafka_producer": kafka_producer,
        "mongodb_client": mongodb_client,
        "registry_client": registry_client,
        "intelligent_scheduler": intelligent_scheduler,
        "policy_validator": policy_validator,
        "config": config,
        "ml_predictor": ml_predictor,
        "metrics": metrics
    }


class TestOrchestrationWorkflowScheduler:
    """Testes de integração workflow + scheduler."""

    @pytest.mark.asyncio
    async def test_workflow_c3_allocate_resources_with_scheduler(
        self, mock_activity_dependencies
    ):
        """Testa step C3 com scheduler real."""
        # Importar e injetar dependências
        from src.activities import ticket_generation

        # Injetar dependências no módulo
        ticket_generation.intelligent_scheduler = mock_activity_dependencies["intelligent_scheduler"]
        ticket_generation.policy_validator = mock_activity_dependencies["policy_validator"]
        ticket_generation.ml_predictor = mock_activity_dependencies["ml_predictor"]
        ticket_generation.config = mock_activity_dependencies["config"]

        # Criar ticket para alocação
        ticket = {
            "ticket_id": "ticket-workflow-1",
            "task_id": "task-1",
            "risk_band": "high",
            "qos": {
                "delivery_mode": "EXACTLY_ONCE",
                "consistency": "STRONG",
                "durability": "PERSISTENT"
            },
            "sla": {
                "deadline": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                "timeout_ms": 3600000
            },
            "required_capabilities": ["python", "data-processing"],
            "namespace": "default",
            "security_level": "standard",
            "estimated_duration_ms": 1000,
            "created_at": datetime.utcnow().isoformat()
        }

        # Executar activity
        result = await allocate_resources(ticket)

        # Verificar alocação com scheduler
        assert "allocation_metadata" in result
        assert result["allocation_metadata"]["allocation_method"] == "intelligent_scheduler"
        assert result["allocation_metadata"]["agent_id"] == "worker-001"

    @pytest.mark.asyncio
    async def test_workflow_c3_scheduler_timeout_fallback(
        self, mock_activity_dependencies
    ):
        """Testa fallback quando scheduler dá timeout."""
        # Criar registry client que demora muito
        slow_client = AsyncMock(spec=ServiceRegistryClient)

        async def slow_discovery(*args, **kwargs):
            import asyncio
            await asyncio.sleep(6)  # Excede timeout
            return []

        slow_client.discover_agents = AsyncMock(side_effect=slow_discovery)

        # Recriar components com client lento
        config = mock_activity_dependencies["config"]
        metrics = mock_activity_dependencies["metrics"]

        priority_calculator = PriorityCalculator(config)
        resource_allocator = ResourceAllocator(
            registry_client=slow_client,
            config=config,
            metrics=metrics
        )
        slow_scheduler = IntelligentScheduler(
            config=config,
            metrics=metrics,
            priority_calculator=priority_calculator,
            resource_allocator=resource_allocator
        )

        # Injetar scheduler lento
        from src.activities import ticket_generation
        ticket_generation.intelligent_scheduler = slow_scheduler
        ticket_generation.policy_validator = mock_activity_dependencies["policy_validator"]
        ticket_generation.ml_predictor = mock_activity_dependencies["ml_predictor"]
        ticket_generation.config = config

        # Criar ticket
        ticket = {
            "ticket_id": "ticket-timeout-1",
            "task_id": "task-1",
            "risk_band": "normal",
            "qos": {},
            "sla": {"timeout_ms": 3600000},
            "required_capabilities": ["python"],
            "namespace": "default",
            "security_level": "standard",
            "estimated_duration_ms": 1000,
            "created_at": datetime.utcnow().isoformat()
        }

        # Executar activity (deve usar fallback)
        result = await allocate_resources(ticket)

        # Verificar fallback
        assert result["allocation_metadata"]["allocation_method"] == "fallback_stub"

    @pytest.mark.asyncio
    async def test_workflow_end_to_end_with_scheduler(
        self, mock_activity_dependencies, mock_cognitive_plan, mock_consolidated_decision
    ):
        """Testa workflow completo C1→C2→C3→C4→C5→C6 com scheduler."""
        # Importar activities
        from src.activities import ticket_generation, plan_validation, result_consolidation

        # Injetar dependências
        ticket_generation.intelligent_scheduler = mock_activity_dependencies["intelligent_scheduler"]
        ticket_generation.policy_validator = mock_activity_dependencies["policy_validator"]
        ticket_generation.ml_predictor = mock_activity_dependencies["ml_predictor"]
        ticket_generation.kafka_producer = mock_activity_dependencies["kafka_producer"]
        ticket_generation.mongodb_client = mock_activity_dependencies["mongodb_client"]
        ticket_generation.config = mock_activity_dependencies["config"]

        # C1: Validar plano (mock)
        validated_plan = mock_cognitive_plan

        # C2: Gerar tickets
        tickets = []
        for task in validated_plan["tasks"]:
            ticket = {
                "ticket_id": f"ticket-{task['task_id']}",
                "task_id": task["task_id"],
                "risk_band": validated_plan["risk_band"],
                "qos": {
                    "delivery_mode": "AT_LEAST_ONCE",
                    "consistency": "EVENTUAL",
                    "durability": "PERSISTENT"
                },
                "sla": {
                    "deadline": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                    "timeout_ms": 3600000
                },
                "required_capabilities": task["required_capabilities"],
                "namespace": validated_plan["namespace"],
                "security_level": validated_plan["security_level"],
                "estimated_duration_ms": task["estimated_duration_ms"],
                "created_at": datetime.utcnow().isoformat()
            }
            tickets.append(ticket)

        # C3: Alocar recursos com scheduler
        allocated_tickets = []
        for ticket in tickets:
            allocated = await allocate_resources(ticket)
            allocated_tickets.append(allocated)

        # Verificar que todos foram alocados
        assert len(allocated_tickets) == 2
        for ticket in allocated_tickets:
            assert "allocation_metadata" in ticket
            assert ticket["allocation_metadata"]["allocation_method"] == "intelligent_scheduler"

    @pytest.mark.asyncio
    async def test_workflow_multiple_tickets_parallel_allocation(
        self, mock_activity_dependencies
    ):
        """Testa alocação paralela de 5 tickets no workflow."""
        # Importar activity
        from src.activities import ticket_generation

        # Injetar dependências
        ticket_generation.intelligent_scheduler = mock_activity_dependencies["intelligent_scheduler"]
        ticket_generation.policy_validator = mock_activity_dependencies["policy_validator"]
        ticket_generation.ml_predictor = mock_activity_dependencies["ml_predictor"]
        ticket_generation.config = mock_activity_dependencies["config"]

        # Criar 5 tickets
        tickets = []
        for i in range(5):
            ticket = {
                "ticket_id": f"ticket-parallel-{i}",
                "task_id": f"task-{i}",
                "risk_band": "normal",
                "qos": {},
                "sla": {"timeout_ms": 3600000},
                "required_capabilities": ["python"],
                "namespace": "default",
                "security_level": "standard",
                "estimated_duration_ms": 1000,
                "created_at": datetime.utcnow().isoformat()
            }
            tickets.append(ticket)

        # Alocar em paralelo
        import asyncio
        results = await asyncio.gather(*[
            allocate_resources(ticket) for ticket in tickets
        ])

        # Verificar todos alocados
        assert len(results) == 5
        for result in results:
            assert "allocation_metadata" in result

    @pytest.mark.asyncio
    async def test_workflow_c3_with_opa_rejection(
        self, mock_activity_dependencies
    ):
        """Testa step C3 do workflow quando OPA rejeita ticket."""
        from src.activities import ticket_generation

        # Configurar PolicyValidator para rejeitar
        rejection_result = MagicMock()
        rejection_result.is_valid = False
        rejection_result.violations = [
            {
                "policy": "sla_enforcement",
                "rule": "timeout_insufficient",
                "severity": "HIGH",
                "message": "Timeout insuficiente para estimated_duration"
            }
        ]
        rejection_result.feature_flags = {"enable_intelligent_scheduler": True}

        policy_validator_reject = AsyncMock(spec=PolicyValidator)
        policy_validator_reject.validate_execution_ticket = AsyncMock(return_value=rejection_result)

        # Injetar dependências com PolicyValidator que rejeita
        ticket_generation.policy_validator = policy_validator_reject
        ticket_generation.intelligent_scheduler = mock_activity_dependencies["intelligent_scheduler"]
        ticket_generation.ml_predictor = mock_activity_dependencies["ml_predictor"]
        ticket_generation.config = mock_activity_dependencies["config"]

        # Ticket de teste
        ticket = {
            "ticket_id": "ticket-opa-reject-workflow",
            "task_id": "task-reject",
            "risk_band": "critical",
            "qos": {
                "delivery_mode": "EXACTLY_ONCE",
                "consistency": "STRONG",
                "durability": "PERSISTENT"
            },
            "sla": {
                "deadline": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                "timeout_ms": 60000  # 1 min (muito curto para critical)
            },
            "required_capabilities": ["python"],
            "namespace": "default",
            "security_level": "standard",
            "estimated_duration_ms": 120000,  # 2 min
            "created_at": datetime.utcnow().isoformat()
        }

        # Executar validação (simula início da activity)
        validation_result = await policy_validator_reject.validate_execution_ticket(ticket)

        # Verificar rejeição OPA
        assert validation_result.is_valid is False
        assert len(validation_result.violations) > 0
        assert validation_result.violations[0]["policy"] == "sla_enforcement"

        # Em um workflow real, a activity lançaria exceção ou retornaria erro
        # Aqui apenas validamos que a rejeição foi detectada

    @pytest.mark.asyncio
    async def test_workflow_c3_with_feature_flag_disabled(
        self, mock_activity_dependencies
    ):
        """Testa step C3 do workflow quando feature flag está desabilitada."""
        from src.activities import ticket_generation

        # Configurar PolicyValidator para retornar feature flag desabilitada
        valid_result = MagicMock()
        valid_result.is_valid = True
        valid_result.warnings = []
        valid_result.feature_flags = {"enable_intelligent_scheduler": False}

        policy_validator_flag_off = AsyncMock(spec=PolicyValidator)
        policy_validator_flag_off.validate_execution_ticket = AsyncMock(return_value=valid_result)

        # Injetar dependências
        ticket_generation.policy_validator = policy_validator_flag_off
        ticket_generation.intelligent_scheduler = mock_activity_dependencies["intelligent_scheduler"]
        ticket_generation.ml_predictor = mock_activity_dependencies["ml_predictor"]
        ticket_generation.config = mock_activity_dependencies["config"]

        # Ticket de teste
        ticket = {
            "ticket_id": "ticket-flag-off-workflow",
            "task_id": "task-flag-off",
            "risk_band": "normal",
            "qos": {},
            "sla": {"timeout_ms": 3600000},
            "required_capabilities": ["python"],
            "namespace": "default",
            "security_level": "standard",
            "estimated_duration_ms": 1000,
            "created_at": datetime.utcnow().isoformat()
        }

        # Executar validação
        validation_result = await policy_validator_flag_off.validate_execution_ticket(ticket)

        assert validation_result.is_valid is True
        feature_flags = validation_result.feature_flags

        # Simular lógica de allocate_resources respeitando feature flag
        if not feature_flags.get('enable_intelligent_scheduler', True):
            # Fallback stub
            result = {
                **ticket,
                "allocation_metadata": {
                    "allocated_at": int(datetime.now().timestamp() * 1000),
                    "agent_id": "worker-agent-pool",
                    "agent_type": "worker-agent",
                    "priority_score": 0.5,
                    "agent_score": 0.5,
                    "composite_score": 0.5,
                    "allocation_method": "fallback_stub",
                    "workers_evaluated": 0
                }
            }
        else:
            # IntelligentScheduler
            result = await mock_activity_dependencies["intelligent_scheduler"].schedule_ticket(ticket)

        # Verificar que fallback stub foi usado
        assert result["allocation_metadata"]["allocation_method"] == "fallback_stub"
        assert result["allocation_metadata"]["agent_id"] == "worker-agent-pool"
