"""
Testes de integração com OPA Server real via Docker.

Requer Docker instalado e acessível.
"""
import pytest
import asyncio
import subprocess
import time
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path

from src.policies import OPAClient, PolicyValidator
from src.policies.opa_client import OPAConnectionError, OPAPolicyNotFoundError
from src.config.settings import OrchestratorSettings


@pytest.fixture(scope="module")
def opa_container():
    """
    Inicia container OPA com políticas carregadas.

    Yields:
        Container ID
    """
    # Caminho para políticas Rego
    policies_dir = Path(__file__).parent.parent.parent.parent.parent / "policies" / "rego" / "orchestrator"

    if not policies_dir.exists():
        pytest.skip(f"Diretório de políticas não encontrado: {policies_dir}")

    # Verificar se Docker está disponível
    try:
        subprocess.run(
            ["docker", "--version"],
            check=True,
            capture_output=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker não disponível")

    # Parar container anterior se existir
    subprocess.run(
        ["docker", "rm", "-f", "opa-test"],
        capture_output=True
    )

    # Iniciar container OPA
    cmd = [
        "docker", "run",
        "--name", "opa-test",
        "-d",
        "-p", "8181:8181",
        "-v", f"{policies_dir}:/policies:ro",
        "openpolicyagent/opa:0.58.0",
        "run", "--server", "--addr=0.0.0.0:8181", "/policies"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        pytest.skip(f"Falha ao iniciar OPA container: {result.stderr}")

    container_id = result.stdout.strip()

    # Aguardar OPA estar pronto
    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                ["docker", "exec", "opa-test", "curl", "-s", "http://localhost:8181/health"],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                break
        except subprocess.TimeoutExpired:
            pass

        time.sleep(1)
    else:
        # Cleanup em caso de falha
        subprocess.run(["docker", "rm", "-f", "opa-test"], capture_output=True)
        pytest.skip("OPA container não ficou pronto a tempo")

    # Aguardar mais um pouco para garantir
    time.sleep(2)

    yield container_id

    # Cleanup
    subprocess.run(["docker", "rm", "-f", "opa-test"], capture_output=True)


@pytest.fixture
def real_opa_config(opa_container):
    """Fixture com configurações para OPA real."""
    from unittest.mock import Mock

    config = Mock(spec=OrchestratorSettings)
    config.opa_host = 'localhost'
    config.opa_port = 8181
    config.opa_timeout_seconds = 5
    config.opa_retry_attempts = 3
    config.opa_cache_ttl_seconds = 30
    config.opa_fail_open = False
    config.opa_circuit_breaker_enabled = True
    config.opa_circuit_breaker_failure_threshold = 5
    config.opa_circuit_breaker_reset_timeout = 60
    config.opa_policy_resource_limits = 'neuralhive/orchestrator/resource_limits'
    config.opa_policy_sla_enforcement = 'neuralhive/orchestrator/sla_enforcement'
    config.opa_policy_feature_flags = 'neuralhive/orchestrator/feature_flags'
    config.opa_max_concurrent_tickets = 100
    config.opa_allowed_capabilities = ['code_generation', 'deployment', 'testing', 'validation']
    config.opa_resource_limits = {'max_cpu': '4000m', 'max_memory': '8Gi'}

    return config


@pytest.fixture
async def real_opa_client(real_opa_config):
    """Fixture com OPAClient conectado a OPA real."""
    client = OPAClient(real_opa_config)
    await client.initialize()
    yield client
    await client.close()


class TestOPARealServerResourceLimits:
    """Testes de resource_limits com OPA real."""

    @pytest.mark.asyncio
    async def test_valid_ticket_within_limits(self, real_opa_client):
        """Testa ticket válido dentro dos limites."""
        input_data = {
            "resource": {
                "ticket_id": "test-123",
                "risk_band": "high",
                "sla": {
                    "timeout_ms": 60000,  # 1min (dentro do limite de 1h para high)
                    "max_retries": 3
                },
                "estimated_duration_ms": 30000,
                "required_capabilities": ["code_generation"]
            },
            "parameters": {
                "allowed_capabilities": ["code_generation", "deployment", "testing"],
                "max_concurrent_tickets": 100
            },
            "context": {
                "total_tickets": 50
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/resource_limits',
            {'input': input_data}
        )

        assert 'result' in result
        assert result['result']['allow'] is True
        assert len(result['result']['violations']) == 0

    @pytest.mark.asyncio
    async def test_timeout_exceeds_maximum(self, real_opa_client):
        """Testa violação de timeout máximo."""
        input_data = {
            "resource": {
                "ticket_id": "test-456",
                "risk_band": "high",
                "sla": {
                    "timeout_ms": 7200000,  # 2h (excede limite de 1h para high)
                    "max_retries": 3
                },
                "estimated_duration_ms": 30000,
                "required_capabilities": ["code_generation"]
            },
            "parameters": {
                "allowed_capabilities": ["code_generation"],
                "max_concurrent_tickets": 100
            },
            "context": {
                "total_tickets": 50
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/resource_limits',
            {'input': input_data}
        )

        assert 'result' in result
        assert result['result']['allow'] is False
        assert len(result['result']['violations']) > 0

        # Encontrar violação de timeout
        timeout_violation = next(
            (v for v in result['result']['violations'] if v['rule'] == 'timeout_exceeds_maximum'),
            None
        )
        assert timeout_violation is not None
        assert timeout_violation['severity'] == 'high'

    @pytest.mark.asyncio
    async def test_retries_exceed_maximum(self, real_opa_client):
        """Testa violação de max retries."""
        input_data = {
            "resource": {
                "ticket_id": "test-789",
                "risk_band": "medium",
                "sla": {
                    "timeout_ms": 60000,
                    "max_retries": 10  # Excede limite de 2 para medium
                },
                "estimated_duration_ms": 30000,
                "required_capabilities": ["testing"]
            },
            "parameters": {
                "allowed_capabilities": ["testing"],
                "max_concurrent_tickets": 100
            },
            "context": {
                "total_tickets": 50
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/resource_limits',
            {'input': input_data}
        )

        assert result['result']['allow'] is False

        retry_violation = next(
            (v for v in result['result']['violations'] if v['rule'] == 'retries_exceed_maximum'),
            None
        )
        assert retry_violation is not None
        assert retry_violation['severity'] == 'medium'

    @pytest.mark.asyncio
    async def test_capability_not_allowed(self, real_opa_client):
        """Testa violação de capability não permitida."""
        input_data = {
            "resource": {
                "ticket_id": "test-999",
                "risk_band": "low",
                "sla": {
                    "timeout_ms": 60000,
                    "max_retries": 1
                },
                "estimated_duration_ms": 30000,
                "required_capabilities": ["malicious_capability"]  # Não permitida
            },
            "parameters": {
                "allowed_capabilities": ["code_generation", "testing"],
                "max_concurrent_tickets": 100
            },
            "context": {
                "total_tickets": 50
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/resource_limits',
            {'input': input_data}
        )

        assert result['result']['allow'] is False

        cap_violation = next(
            (v for v in result['result']['violations'] if v['rule'] == 'capabilities_not_allowed'),
            None
        )
        assert cap_violation is not None
        assert cap_violation['severity'] == 'high'


class TestOPARealServerSLAEnforcement:
    """Testes de sla_enforcement com OPA real."""

    @pytest.mark.asyncio
    async def test_valid_sla(self, real_opa_client):
        """Testa SLA válido."""
        current_time = int(datetime.now().timestamp() * 1000)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        input_data = {
            "resource": {
                "ticket_id": "sla-123",
                "risk_band": "critical",
                "sla": {
                    "timeout_ms": 120000,
                    "deadline": deadline
                },
                "qos": {
                    "delivery_mode": "EXACTLY_ONCE",
                    "consistency": "STRONG"
                },
                "priority": "CRITICAL",
                "estimated_duration_ms": 60000
            },
            "context": {
                "current_time": current_time
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/sla_enforcement',
            {'input': input_data}
        )

        assert result['result']['allow'] is True
        assert len(result['result']['violations']) == 0

    @pytest.mark.asyncio
    async def test_deadline_in_past(self, real_opa_client):
        """Testa violação de deadline no passado."""
        current_time = int(datetime.now().timestamp() * 1000)
        deadline = int((datetime.now() - timedelta(hours=1)).timestamp() * 1000)

        input_data = {
            "resource": {
                "ticket_id": "sla-456",
                "risk_band": "high",
                "sla": {
                    "timeout_ms": 60000,
                    "deadline": deadline  # No passado
                },
                "qos": {
                    "delivery_mode": "EXACTLY_ONCE",
                    "consistency": "STRONG"
                },
                "priority": "HIGH",
                "estimated_duration_ms": 30000
            },
            "context": {
                "current_time": current_time
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/sla_enforcement',
            {'input': input_data}
        )

        assert result['result']['allow'] is False

        deadline_violation = next(
            (v for v in result['result']['violations'] if v['rule'] == 'deadline_in_past'),
            None
        )
        assert deadline_violation is not None
        assert deadline_violation['severity'] == 'critical'

    @pytest.mark.asyncio
    async def test_qos_mismatch_critical(self, real_opa_client):
        """Testa violação de QoS para risk_band critical."""
        current_time = int(datetime.now().timestamp() * 1000)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        input_data = {
            "resource": {
                "ticket_id": "sla-789",
                "risk_band": "critical",
                "sla": {
                    "timeout_ms": 120000,
                    "deadline": deadline
                },
                "qos": {
                    "delivery_mode": "AT_LEAST_ONCE",  # Deveria ser EXACTLY_ONCE
                    "consistency": "STRONG"
                },
                "priority": "CRITICAL",
                "estimated_duration_ms": 60000
            },
            "context": {
                "current_time": current_time
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/sla_enforcement',
            {'input': input_data}
        )

        assert result['result']['allow'] is False

        qos_violation = next(
            (v for v in result['result']['violations'] if v['rule'] == 'qos_mismatch_risk_band'),
            None
        )
        assert qos_violation is not None
        assert qos_violation['severity'] == 'critical'


class TestOPARealServerFeatureFlags:
    """Testes de feature_flags com OPA real."""

    @pytest.mark.asyncio
    async def test_enable_intelligent_scheduler_critical(self, real_opa_client):
        """Testa habilitação do intelligent scheduler para critical."""
        input_data = {
            "resource": {
                "ticket_id": "ff-123",
                "risk_band": "critical"
            },
            "flags": {
                "intelligent_scheduler_enabled": True,
                "scheduler_namespaces": ["production", "staging"],
                "burst_capacity_enabled": False,
                "predictive_allocation_enabled": False,
                "auto_scaling_enabled": False
            },
            "context": {
                "namespace": "production",
                "current_load": 0.5,
                "tenant_id": "tenant-1",
                "queue_depth": 50,
                "current_time": int(datetime.now().timestamp() * 1000),
                "model_accuracy": 0.9
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/feature_flags',
            {'input': input_data}
        )

        assert 'result' in result
        assert result['result']['enable_intelligent_scheduler'] is True

    @pytest.mark.asyncio
    async def test_burst_capacity_premium_tenant(self, real_opa_client):
        """Testa habilitação de burst capacity para tenant premium."""
        input_data = {
            "resource": {
                "ticket_id": "ff-456",
                "risk_band": "high"
            },
            "flags": {
                "intelligent_scheduler_enabled": False,
                "burst_capacity_enabled": True,
                "burst_threshold": 0.8,
                "premium_tenants": ["tenant-premium"],
                "predictive_allocation_enabled": False,
                "auto_scaling_enabled": False
            },
            "context": {
                "namespace": "production",
                "current_load": 0.6,  # Abaixo do threshold
                "tenant_id": "tenant-premium",
                "queue_depth": 50,
                "current_time": int(datetime.now().timestamp() * 1000)
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/feature_flags',
            {'input': input_data}
        )

        assert result['result']['enable_burst_capacity'] is True


class TestOPARealServerBatchEvaluation:
    """Testes de batch evaluation com OPA real."""

    @pytest.mark.asyncio
    async def test_batch_evaluate_multiple_policies(self, real_opa_client):
        """Testa avaliação em batch de múltiplas políticas."""
        current_time = int(datetime.now().timestamp() * 1000)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        # Input comum
        resource = {
            "ticket_id": "batch-123",
            "risk_band": "high",
            "sla": {
                "timeout_ms": 120000,
                "deadline": deadline,
                "max_retries": 3
            },
            "qos": {
                "delivery_mode": "EXACTLY_ONCE",
                "consistency": "STRONG"
            },
            "priority": "HIGH",
            "estimated_duration_ms": 60000,
            "required_capabilities": ["code_generation"]
        }

        evaluations = [
            # Resource limits
            (
                'neuralhive/orchestrator/resource_limits',
                {
                    'input': {
                        'resource': resource,
                        'parameters': {
                            'allowed_capabilities': ['code_generation'],
                            'max_concurrent_tickets': 100
                        },
                        'context': {
                            'total_tickets': 50
                        }
                    }
                }
            ),
            # SLA enforcement
            (
                'neuralhive/orchestrator/sla_enforcement',
                {
                    'input': {
                        'resource': resource,
                        'context': {
                            'current_time': current_time
                        }
                    }
                }
            ),
            # Feature flags
            (
                'neuralhive/orchestrator/feature_flags',
                {
                    'input': {
                        'resource': resource,
                        'flags': {
                            'intelligent_scheduler_enabled': True,
                            'scheduler_namespaces': ['production'],
                            'burst_capacity_enabled': False,
                            'predictive_allocation_enabled': False,
                            'auto_scaling_enabled': False
                        },
                        'context': {
                            'namespace': 'production',
                            'current_load': 0.5,
                            'tenant_id': 'tenant-1',
                            'queue_depth': 50,
                            'current_time': current_time,
                            'model_accuracy': 0.9
                        }
                    }
                }
            )
        ]

        results = await real_opa_client.batch_evaluate(evaluations)

        assert len(results) == 3

        # Validar resource_limits
        assert results[0]['result']['allow'] is True
        assert results[0]['policy_path'] == 'neuralhive/orchestrator/resource_limits'

        # Validar sla_enforcement
        assert results[1]['result']['allow'] is True
        assert results[1]['policy_path'] == 'neuralhive/orchestrator/sla_enforcement'

        # Validar feature_flags
        assert results[2]['result']['enable_intelligent_scheduler'] is True
        assert results[2]['policy_path'] == 'neuralhive/orchestrator/feature_flags'


class TestOPARealServerPolicyValidator:
    """Testes de PolicyValidator com OPA real."""

    @pytest.mark.asyncio
    async def test_validate_execution_ticket_success(self, real_opa_client, real_opa_config):
        """Testa validação completa de ticket com sucesso."""
        validator = PolicyValidator(real_opa_client, real_opa_config)

        current_time = datetime.now()
        deadline = current_time + timedelta(hours=1)

        ticket = {
            'ticket_id': 'val-123',
            'risk_band': 'high',
            'sla': {
                'timeout_ms': 120000,
                'deadline': int(deadline.timestamp() * 1000),
                'max_retries': 3
            },
            'qos': {
                'delivery_mode': 'EXACTLY_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 60000,
            'namespace': 'production'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is True
        assert len(result.violations) == 0
        assert 'resource_limits' in result.policy_decisions
        assert 'sla_enforcement' in result.policy_decisions
        assert 'feature_flags' in result.policy_decisions

    @pytest.mark.asyncio
    async def test_validate_execution_ticket_violations(self, real_opa_client, real_opa_config):
        """Testa validação de ticket com violações."""
        validator = PolicyValidator(real_opa_client, real_opa_config)

        # Ticket com múltiplas violações
        ticket = {
            'ticket_id': 'val-456',
            'risk_band': 'high',
            'sla': {
                'timeout_ms': 7200000,  # Excede limite de 1h para high
                'deadline': int((datetime.now() - timedelta(hours=1)).timestamp() * 1000),  # No passado
                'max_retries': 10  # Excede limite de 3 para high
            },
            'qos': {
                'delivery_mode': 'AT_LEAST_ONCE',  # Deveria ser EXACTLY_ONCE
                'consistency': 'STRONG'
            },
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 60000,
            'namespace': 'production'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is False
        assert len(result.violations) > 0

        # Verificar que há violações de múltiplas políticas
        policies_with_violations = set(v.policy_name for v in result.violations)
        assert 'resource_limits' in policies_with_violations
        assert 'sla_enforcement' in policies_with_violations


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
