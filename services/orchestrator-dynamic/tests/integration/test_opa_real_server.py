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
from unittest.mock import AsyncMock

from src.policies import OPAClient, PolicyValidator
from src.policies.opa_client import OPAConnectionError, OPAPolicyNotFoundError
from src.config.settings import OrchestratorSettings
from src.observability.metrics import get_metrics


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
    config.opa_policy_security_constraints = 'neuralhive/orchestrator/security_constraints'
    config.opa_security_enabled = True
    config.opa_max_concurrent_tickets = 100
    config.opa_allowed_capabilities = ['code_generation', 'deployment', 'testing', 'validation']
    config.opa_resource_limits = {'max_cpu': '4000m', 'max_memory': '8Gi'}
    config.opa_intelligent_scheduler_enabled = True
    config.opa_burst_capacity_enabled = True
    config.opa_burst_threshold = 0.8
    config.opa_predictive_allocation_enabled = True
    config.opa_auto_scaling_enabled = True
    config.opa_scheduler_namespaces = ['production', 'staging', 'beta']
    config.opa_premium_tenants = ['tenant-premium', 'tenant-early-access']
    config.opa_allowed_tenants = ['tenant-1', 'tenant-premium', 'tenant-trusted', 'tenant-early-access']
    config.opa_rbac_roles = {
        'user-admin': ['admin'],
        'user-dev': ['developer'],
        'user-readonly': ['viewer']
    }
    config.opa_data_residency_regions = {'tenant-1': 'us-east-1'}
    config.opa_tenant_rate_limits = {'tenant-1': 5, 'tenant-premium': 20, 'tenant-trusted': 10}
    config.opa_global_rate_limit = 1000
    config.opa_default_tenant_rate_limit = 3
    config.spiffe_enabled = True
    config.spiffe_trust_domain = 'example.com'

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

    @pytest.mark.asyncio
    async def test_predictive_allocation_disabled_when_low_accuracy(self, real_opa_client):
        """Testa predictive allocation desabilitado quando acurácia < 0.85."""
        input_data = {
            "resource": {
                "ticket_id": "ff-789",
                "risk_band": "high"
            },
            "flags": {
                "intelligent_scheduler_enabled": True,
                "burst_capacity_enabled": False,
                "predictive_allocation_enabled": True,
                "auto_scaling_enabled": False,
                "scheduler_namespaces": ["production", "beta"],
                "scaling_threshold": 50
            },
            "context": {
                "namespace": "beta",
                "current_load": 0.4,
                "tenant_id": "tenant-1",
                "queue_depth": 40,
                "current_time": int(datetime.now().timestamp() * 1000),
                "model_accuracy": 0.8
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/feature_flags',
            {'input': input_data}
        )

        assert result['result']['enable_predictive_allocation'] is False

    @pytest.mark.asyncio
    async def test_auto_scaling_disabled_outside_business_hours(self, real_opa_client):
        """Testa auto-scaling desabilitado fora do horário comercial."""
        off_hours_timestamp = int(datetime(2024, 1, 1, 2, 0, 0).timestamp() * 1000)
        input_data = {
            "resource": {
                "ticket_id": "ff-101",
                "risk_band": "medium"
            },
            "flags": {
                "intelligent_scheduler_enabled": False,
                "burst_capacity_enabled": False,
                "predictive_allocation_enabled": False,
                "auto_scaling_enabled": True,
                "scaling_threshold": 200,
                "scheduler_namespaces": ["production"],
                "burst_threshold": 0.9,
                "premium_tenants": []
            },
            "context": {
                "namespace": "production",
                "current_load": 0.2,
                "tenant_id": "tenant-1",
                "queue_depth": 50,
                "current_time": off_hours_timestamp,
                "model_accuracy": 0.92
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/feature_flags',
            {'input': input_data}
        )

        assert result['result']['enable_auto_scaling'] is False

    @pytest.mark.asyncio
    async def test_experimental_features_for_early_access_tenant(self, real_opa_client):
        """Testa experimental features para tenant early access."""
        input_data = {
            "resource": {
                "ticket_id": "ff-202",
                "risk_band": "low"
            },
            "flags": {
                "intelligent_scheduler_enabled": False,
                "burst_capacity_enabled": False,
                "predictive_allocation_enabled": False,
                "auto_scaling_enabled": False,
                "scheduler_namespaces": ["staging"],
                "premium_tenants": ["tenant-early-access"],
                "scaling_threshold": 10
            },
            "context": {
                "namespace": "staging",
                "current_load": 0.1,
                "tenant_id": "tenant-early-access",
                "queue_depth": 1,
                "current_time": int(datetime.now().timestamp() * 1000),
                "model_accuracy": 0.99
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/feature_flags',
            {'input': input_data}
        )

        assert result['result']['enable_experimental_features'] is True

    @pytest.mark.asyncio
    async def test_combined_feature_flags_intelligent_scheduler_and_burst_capacity(self, real_opa_client):
        """Testa combinação intelligent_scheduler + burst_capacity."""
        input_data = {
            "resource": {
                "ticket_id": "ff-303",
                "risk_band": "critical"
            },
            "flags": {
                "intelligent_scheduler_enabled": True,
                "burst_capacity_enabled": True,
                "burst_threshold": 0.9,
                "predictive_allocation_enabled": True,
                "auto_scaling_enabled": False,
                "scheduler_namespaces": ["production"],
                "premium_tenants": ["tenant-premium"],
                "scaling_threshold": 25
            },
            "context": {
                "namespace": "production",
                "current_load": 0.4,
                "tenant_id": "tenant-premium",
                "queue_depth": 120,
                "current_time": int(datetime.now().timestamp() * 1000),
                "model_accuracy": 0.9
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/feature_flags',
            {'input': input_data}
        )

        assert result['result']['enable_intelligent_scheduler'] is True
        assert result['result']['enable_burst_capacity'] is True


class TestOPARealServerSecurityConstraints:
    """Testes de security_constraints com OPA real."""

    @pytest.mark.asyncio
    async def test_cross_tenant_access_violation(self, real_opa_client, real_opa_config):
        """Testa violação de cross-tenant access."""
        validator = PolicyValidator(real_opa_client, real_opa_config)
        future_deadline = int((datetime.now() + timedelta(hours=2)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'sec-123',
            'tenant_id': 'malicious-tenant',
            'namespace': 'production',
            'risk_band': 'high',
            'sla': {
                'timeout_ms': 120000,
                'deadline': future_deadline,
                'max_retries': 1
            },
            'qos': {
                'delivery_mode': 'EXACTLY_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 60000,
            'jwt_token': 'header.payload.signature',
            'user_id': 'user-dev'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is False
        assert any(v.rule == 'cross_tenant_access' for v in result.violations)
        assert any(v.severity == 'critical' for v in result.violations)

    @pytest.mark.asyncio
    async def test_missing_authentication_when_spiffe_enabled(self, real_opa_client, real_opa_config):
        """Testa missing_authentication quando SPIFFE habilitado."""
        real_opa_config.spiffe_enabled = True
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'sec-234',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'high',
            'sla': {
                'timeout_ms': 90000,
                'deadline': deadline,
                'max_retries': 1
            },
            'qos': {
                'delivery_mode': 'EXACTLY_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 45000,
            'user_id': 'user-dev'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is False
        assert any(v.rule == 'missing_authentication' for v in result.violations)

    @pytest.mark.asyncio
    async def test_invalid_jwt_token(self, real_opa_client, real_opa_config):
        """Testa invalid_jwt com token malformado."""
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'sec-345',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'medium',
            'sla': {
                'timeout_ms': 60000,
                'deadline': deadline,
                'max_retries': 1
            },
            'qos': {
                'delivery_mode': 'AT_LEAST_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'NORMAL',
            'required_capabilities': ['testing'],
            'estimated_duration_ms': 30000,
            'jwt_token': 'malformedtoken',
            'user_id': 'user-dev'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is False
        assert any(v.rule == 'invalid_jwt' for v in result.violations)

    @pytest.mark.asyncio
    async def test_insufficient_permissions_for_capability(self, real_opa_client, real_opa_config):
        """Testa insufficient_permissions com usuário sem role."""
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'sec-456',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'medium',
            'sla': {
                'timeout_ms': 60000,
                'deadline': deadline,
                'max_retries': 1
            },
            'qos': {
                'delivery_mode': 'AT_LEAST_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'NORMAL',
            'required_capabilities': ['deployment'],
            'estimated_duration_ms': 30000,
            'jwt_token': 'header.payload.signature',
            'user_id': 'user-readonly'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is False
        assert any(v.rule == 'insufficient_permissions' for v in result.violations)
        assert any(v.severity == 'high' for v in result.violations)

    @pytest.mark.asyncio
    async def test_pii_handling_violation(self, real_opa_client, real_opa_config):
        """Testa violação de PII sem classificação confidencial."""
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'sec-567',
            'tenant_id': 'tenant-trusted',
            'namespace': 'production',
            'risk_band': 'low',
            'sla': {
                'timeout_ms': 60000,
                'deadline': deadline,
                'max_retries': 1
            },
            'qos': {
                'delivery_mode': 'AT_LEAST_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'LOW',
            'required_capabilities': ['testing'],
            'estimated_duration_ms': 30000,
            'contains_pii': True,
            'data_classification': 'public',
            'jwt_token': 'header.payload.signature',
            'user_id': 'user-dev'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is False
        assert any(v.rule == 'pii_handling_violation' for v in result.violations)

    @pytest.mark.asyncio
    async def test_tenant_rate_limit_exceeded(self, real_opa_client, real_opa_config, monkeypatch):
        """Testa rate limit excedido para tenant."""
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        async def fake_request_count(_):
            return 50

        monkeypatch.setattr(validator, '_get_request_count', AsyncMock(side_effect=fake_request_count))

        ticket = {
            'ticket_id': 'sec-678',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'medium',
            'sla': {
                'timeout_ms': 60000,
                'deadline': deadline,
                'max_retries': 1
            },
            'qos': {
                'delivery_mode': 'AT_LEAST_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'NORMAL',
            'required_capabilities': ['testing'],
            'estimated_duration_ms': 30000,
            'jwt_token': 'header.payload.signature',
            'user_id': 'user-dev'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is False
        assert any(v.rule == 'tenant_rate_limit_exceeded' for v in result.violations)


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


class TestOPARealServerEdgeCases:
    """Testes de edge cases de políticas OPA."""

    @pytest.mark.asyncio
    async def test_policy_handles_empty_input(self, real_opa_client):
        """Testa política com input vazio."""
        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/feature_flags',
            {'input': {}}
        )

        assert 'result' in result
        assert result['result']['enable_intelligent_scheduler'] is False
        assert result['result']['enable_burst_capacity'] is False

    @pytest.mark.asyncio
    async def test_optional_fields_missing(self, real_opa_client):
        """Testa política com campos opcionais ausentes."""
        input_data = {
            "resource": {
                "ticket_id": "edge-001",
                "tenant_id": "tenant-1",
                "risk_band": "low",
                "contains_pii": False
            },
            "security": {
                "allowed_tenants": ["tenant-1"],
                "spiffe_enabled": False,
                "tenant_rate_limits": {"tenant-1": 5},
                "default_tenant_rate_limit": 10,
                "global_rate_limit": 100
            },
            "context": {
                "user_id": "user-dev",
                "current_time": int(datetime.now().timestamp() * 1000),
                "request_count_last_minute": 1
            }
        }

        result = await real_opa_client.evaluate_policy(
            'neuralhive/orchestrator/security_constraints',
            {'input': input_data}
        )

        assert result['result']['allow'] is True
        assert len(result['result']['violations']) == 0

    @pytest.mark.asyncio
    async def test_multiple_violations_simultaneously(self, real_opa_client, real_opa_config):
        """Testa múltiplas violações simultâneas."""
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(minutes=10)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'edge-002',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'high',
            'sla': {
                'timeout_ms': 7200000,  # timeout alto
                'deadline': deadline,
                'max_retries': 10  # retries acima do limite
            },
            'qos': {
                'delivery_mode': 'AT_LEAST_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'HIGH',
            'required_capabilities': ['malicious_capability'],
            'estimated_duration_ms': 7200000
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is False
        assert len(result.violations) >= 2
        rules = {v.rule for v in result.violations}
        assert 'timeout_exceeds_maximum' in rules
        assert 'retries_exceed_maximum' in rules or 'capabilities_not_allowed' in rules

    @pytest.mark.asyncio
    async def test_warnings_do_not_block_execution(self, real_opa_client, real_opa_config):
        """Testa que warnings não bloqueiam execução."""
        validator = PolicyValidator(real_opa_client, real_opa_config)
        current_time = int(datetime.now().timestamp() * 1000)
        deadline = current_time + 5000  # deadline próximo para gerar warning

        ticket = {
            'ticket_id': 'edge-003',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'high',
            'sla': {
                'timeout_ms': 30000,
                'deadline': deadline,
                'max_retries': 1
            },
            'qos': {
                'delivery_mode': 'EXACTLY_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 10000,
            'jwt_token': 'header.payload.signature',
            'user_id': 'user-dev'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is True
        assert any(w.rule == 'deadline_approaching_threshold' for w in result.warnings)

    @pytest.mark.asyncio
    async def test_fail_open_when_opa_unavailable(self, real_opa_config, monkeypatch):
        """Testa fail-open quando OPA indisponível."""
        real_opa_config.opa_fail_open = True
        client = OPAClient(real_opa_config)
        await client.initialize()
        validator = PolicyValidator(client, real_opa_config)

        monkeypatch.setattr(
            client,
            'batch_evaluate',
            AsyncMock(side_effect=OPAConnectionError("Connection refused"))
        )

        ticket = {
            'ticket_id': 'edge-004',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'low',
            'sla': {
                'timeout_ms': 60000,
                'deadline': int((datetime.now() + timedelta(hours=1)).timestamp() * 1000),
                'max_retries': 1
            },
            'qos': {
                'delivery_mode': 'AT_LEAST_ONCE',
                'consistency': 'EVENTUAL'
            },
            'priority': 'LOW',
            'required_capabilities': ['testing'],
            'estimated_duration_ms': 10000
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is True
        assert any(w.rule == 'evaluation_error' for w in result.warnings)
        await client.close()


class TestOPARealServerC1Integration:
    """Testes de integração C1 com PolicyValidator."""

    @pytest.mark.asyncio
    async def test_full_cognitive_plan_validation(self, real_opa_client, real_opa_config):
        """Testa validação de plano cognitivo completo."""
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        plan = {
            'plan_id': 'plan-001',
            'namespace': 'production',
            'risk_band': 'high',
            'sla': {'timeout_ms': 120000, 'deadline': deadline, 'max_retries': 2},
            'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
            'priority': 'HIGH',
            'estimated_duration_ms': 60000,
            'required_capabilities': ['code_generation'],
            'tasks': [
                {'task_id': 't1', 'dependencies': []},
                {'task_id': 't2', 'dependencies': ['t1']}
            ],
            'execution_order': ['t1', 't2']
        }

        result = await validator.validate_cognitive_plan(plan)

        assert result.valid is True
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_plan_with_multiple_tasks_and_dependencies(self, real_opa_client, real_opa_config):
        """Testa plano com múltiplas tasks e dependências."""
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=2)).timestamp() * 1000)

        plan = {
            'plan_id': 'plan-002',
            'namespace': 'staging',
            'risk_band': 'medium',
            'sla': {'timeout_ms': 1800000, 'deadline': deadline, 'max_retries': 2},
            'qos': {'delivery_mode': 'AT_LEAST_ONCE', 'consistency': 'STRONG'},
            'priority': 'NORMAL',
            'estimated_duration_ms': 900000,
            'required_capabilities': ['testing'],
            'tasks': [
                {'task_id': 't1', 'dependencies': []},
                {'task_id': 't2', 'dependencies': ['t1']},
                {'task_id': 't3', 'dependencies': ['t1', 't2']}
            ],
            'execution_order': ['t1', 't2', 't3']
        }

        result = await validator.validate_cognitive_plan(plan)

        assert result.valid is True
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_critical_plan_with_qos_requirements(self, real_opa_client, real_opa_config):
        """Testa plano critical com QoS específico."""
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(minutes=45)).timestamp() * 1000)

        plan = {
            'plan_id': 'plan-003',
            'namespace': 'production',
            'risk_band': 'critical',
            'sla': {'timeout_ms': 3000000, 'deadline': deadline, 'max_retries': 3},
            'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
            'priority': 'CRITICAL',
            'estimated_duration_ms': 120000,
            'required_capabilities': ['code_generation'],
            'tasks': [
                {'task_id': 't1', 'dependencies': []},
                {'task_id': 't2', 'dependencies': ['t1']},
                {'task_id': 't3', 'dependencies': ['t2']}
            ],
            'execution_order': ['t1', 't2', 't3']
        }

        result = await validator.validate_cognitive_plan(plan)

        assert result.valid is True
        assert len(result.violations) == 0


class TestOPARealServerResourceAllocation:
    """Testes de validação de alocação pós-scheduler."""

    @pytest.mark.asyncio
    async def test_resource_allocation_within_limits(self, real_opa_client, real_opa_config):
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(minutes=30)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'alloc-001',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'high',
            'sla': {'timeout_ms': 120000, 'deadline': deadline, 'max_retries': 2},
            'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 60000,
            'total_tickets': 10
        }

        agent_info = {'agent_id': 'agent-1', 'capacity': {'cpu': '1000m', 'memory': '1Gi'}}

        result = await validator.validate_resource_allocation(ticket, agent_info)

        assert result.valid is True
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_resource_allocation_timeout_violation(self, real_opa_client, real_opa_config):
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'alloc-002',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'high',
            'sla': {'timeout_ms': 7200000, 'deadline': deadline, 'max_retries': 2},
            'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 60000,
            'total_tickets': 10
        }

        agent_info = {'agent_id': 'agent-1', 'capacity': {'cpu': '1000m', 'memory': '1Gi'}}

        result = await validator.validate_resource_allocation(ticket, agent_info)

        assert result.valid is False
        assert any(v.rule == 'timeout_exceeds_maximum' for v in result.violations)

    @pytest.mark.asyncio
    async def test_resource_allocation_capabilities_violation(self, real_opa_client, real_opa_config):
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'alloc-003',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'medium',
            'sla': {'timeout_ms': 60000, 'deadline': deadline, 'max_retries': 1},
            'qos': {'delivery_mode': 'AT_LEAST_ONCE', 'consistency': 'STRONG'},
            'priority': 'NORMAL',
            'required_capabilities': ['forbidden_capability'],
            'estimated_duration_ms': 30000,
            'total_tickets': 5
        }

        agent_info = {'agent_id': 'agent-1', 'capacity': {'cpu': '1000m', 'memory': '1Gi'}}

        result = await validator.validate_resource_allocation(ticket, agent_info)

        assert result.valid is False
        assert any(v.rule == 'capabilities_not_allowed' for v in result.violations)

    @pytest.mark.asyncio
    async def test_resource_allocation_concurrent_limit_violation(self, real_opa_client, real_opa_config):
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'alloc-004',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'high',
            'sla': {'timeout_ms': 120000, 'deadline': deadline, 'max_retries': 2},
            'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 60000,
            'total_tickets': 200  # acima do max_concurrent_tickets=100
        }

        agent_info = {'agent_id': 'agent-1', 'capacity': {'cpu': '1000m', 'memory': '1Gi'}}

        result = await validator.validate_resource_allocation(ticket, agent_info)

        assert result.valid is False
        assert any(v.rule == 'concurrent_tickets_limit' for v in result.violations)


class TestOPARealServerMetrics:
    """Testes de métricas registradas durante validações."""

    @pytest.mark.asyncio
    async def test_metrics_increment_on_success(self, real_opa_client, real_opa_config):
        """Verifica increment de opa_validations_total após validação."""
        metrics = get_metrics()
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'metric-001',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'high',
            'sla': {'timeout_ms': 120000, 'deadline': deadline, 'max_retries': 2},
            'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 60000,
            'jwt_token': 'header.payload.signature',
            'user_id': 'user-dev'
        }

        before = metrics.opa_validations_total.labels(
            policy_name='neuralhive/orchestrator/resource_limits',
            result='allowed'
        )._value.get()

        await validator.validate_execution_ticket(ticket)

        after = metrics.opa_validations_total.labels(
            policy_name='neuralhive/orchestrator/resource_limits',
            result='allowed'
        )._value.get()

        assert after == before + 1

    @pytest.mark.asyncio
    async def test_metrics_increment_on_violation(self, real_opa_client, real_opa_config):
        """Verifica opa_policy_rejections_total incrementa após violação."""
        metrics = get_metrics()
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'metric-002',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'high',
            'sla': {'timeout_ms': 7200000, 'deadline': deadline, 'max_retries': 5},
            'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 60000,
            'jwt_token': 'header.payload.signature',
            'user_id': 'user-dev'
        }

        before = metrics.opa_policy_rejections_total.labels(
            policy_name='resource_limits',
            rule='timeout_exceeds_maximum',
            severity='high'
        )._value.get()

        await validator.validate_execution_ticket(ticket)

        after = metrics.opa_policy_rejections_total.labels(
            policy_name='resource_limits',
            rule='timeout_exceeds_maximum',
            severity='high'
        )._value.get()

        assert after == before + 1

    @pytest.mark.asyncio
    async def test_validation_duration_records_latency(self, real_opa_client, real_opa_config):
        """Verifica histograma de duração de validação."""
        metrics = get_metrics()
        validator = PolicyValidator(real_opa_client, real_opa_config)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        ticket = {
            'ticket_id': 'metric-003',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'high',
            'sla': {'timeout_ms': 120000, 'deadline': deadline, 'max_retries': 2},
            'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 60000,
            'jwt_token': 'header.payload.signature',
            'user_id': 'user-dev'
        }

        before_sum = metrics.opa_validation_duration_seconds.labels(
            policy_name='neuralhive/orchestrator/resource_limits'
        )._sum.get()

        await validator.validate_execution_ticket(ticket)

        after_sum = metrics.opa_validation_duration_seconds.labels(
            policy_name='neuralhive/orchestrator/resource_limits'
        )._sum.get()

        assert after_sum > before_sum

    @pytest.mark.asyncio
    async def test_circuit_breaker_state_changes(self, real_opa_config, monkeypatch):
        """Verifica atualização do estado do circuit breaker."""
        metrics = get_metrics()
        real_opa_config.opa_fail_open = True
        client = OPAClient(real_opa_config)
        await client.initialize()
        validator = PolicyValidator(client, real_opa_config)

        monkeypatch.setattr(
            client,
            'batch_evaluate',
            AsyncMock(side_effect=OPAConnectionError("Connection refused"))
        )

        gauge = metrics.opa_circuit_breaker_state.labels(circuit_name='opa_client')
        before = gauge._value.get()

        ticket = {
            'ticket_id': 'metric-004',
            'tenant_id': 'tenant-1',
            'namespace': 'production',
            'risk_band': 'low',
            'sla': {'timeout_ms': 60000, 'deadline': int((datetime.now() + timedelta(hours=1)).timestamp() * 1000), 'max_retries': 1},
            'qos': {'delivery_mode': 'AT_LEAST_ONCE', 'consistency': 'EVENTUAL'},
            'priority': 'LOW',
            'required_capabilities': ['testing'],
            'estimated_duration_ms': 10000
        }

        await validator.validate_execution_ticket(ticket)
        metrics.record_opa_circuit_breaker_state('open', 5)

        after = gauge._value.get()

        assert after != before
        await client.close()

if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
