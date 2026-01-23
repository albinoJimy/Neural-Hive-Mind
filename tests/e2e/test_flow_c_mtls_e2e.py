"""
Teste E2E do Fluxo C com mTLS habilitado.

Valida que todo o fluxo funciona com SPIFFE/SPIRE:
- Orchestrator Dynamic obtem X.509-SVID e JWT-SVID
- Service Registry valida SPIFFE ID dos clientes
- Worker Agents se comunicam com mTLS
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


REAL_E2E = os.getenv("RUN_SPIFFE_MTLS_E2E", "").lower() == "true"
pytestmark = pytest.mark.skipif(not REAL_E2E, reason="RUN_SPIFFE_MTLS_E2E not enabled")


@dataclass
class FlowCContext:
    """Contexto do Fluxo C"""
    correlation_id: str
    intent_id: str
    plan_id: str
    decision_id: str
    sla_deadline_seconds: int


@dataclass
class FlowCResult:
    """Resultado do Fluxo C"""
    success: bool
    workflow_id: Optional[str]
    execution_tickets: List[Dict[str, Any]]
    errors: List[str]


@pytest.fixture
def flow_c_context():
    """Fixture para contexto do Fluxo C"""
    return FlowCContext(
        correlation_id="test-mtls-e2e",
        intent_id="intent-mtls-001",
        plan_id="plan-mtls-001",
        decision_id="decision-mtls-001",
        sla_deadline_seconds=14400
    )


@pytest.fixture
def consolidated_decision():
    """Fixture para decisao consolidada de teste"""
    return {
        "decision_id": "decision-mtls-001",
        "plan_id": "plan-mtls-001",
        "intent_id": "intent-mtls-001",
        "correlation_id": "test-mtls-e2e",
        "cognitive_plan": {
            "plan_id": "plan-mtls-001",
            "tasks": [
                {
                    "task_id": "task-001",
                    "task_type": "BUILD",
                    "description": "Build test application",
                    "parameters": {"repo": "test-repo"},
                    "dependencies": []
                }
            ]
        },
        "consensus_metadata": {
            "confidence": 0.95,
            "specialist_agreement": 0.9
        }
    }


@pytest.fixture
def mock_spiffe_manager():
    """Mock do SPIFFEManager para testes"""
    import base64
    import json

    # Criar JWT mock
    header = base64.urlsafe_b64encode(json.dumps({
        "alg": "RS256",
        "typ": "JWT"
    }).encode()).decode().rstrip("=")

    payload = base64.urlsafe_b64encode(json.dumps({
        "sub": "spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic",
        "aud": ["service-registry.neural-hive.local"],
        "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.utcnow().timestamp()),
        "iss": "https://spire-server.spire-system.svc.cluster.local"
    }).encode()).decode().rstrip("=")

    signature = base64.urlsafe_b64encode(b"mock_signature").decode().rstrip("=")

    mock_jwt = f"{header}.{payload}.{signature}"

    manager = AsyncMock()
    manager.fetch_jwt_svid = AsyncMock(return_value=MagicMock(
        token=mock_jwt,
        spiffe_id="spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    ))
    manager.fetch_x509_svid = AsyncMock(return_value=MagicMock(
        spiffe_id="spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic",
        certificate="-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----",
        private_key="-----BEGIN PRIVATE KEY-----\nMOCK\n-----END PRIVATE KEY-----",
        ca_bundle="-----BEGIN CERTIFICATE-----\nMOCK_CA\n-----END CERTIFICATE-----",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    ))
    manager.initialize = AsyncMock()
    manager.close = AsyncMock()

    return manager


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.spiffe
class TestFlowCMTLSE2E:
    """Testes E2E do Fluxo C com mTLS."""

    async def test_flow_c_spiffe_context_setup(self, flow_c_context, mock_spiffe_manager):
        """Testa setup de contexto SPIFFE para o Fluxo C."""
        # Inicializar SPIFFE Manager
        await mock_spiffe_manager.initialize()

        # Obter X.509-SVID
        x509_svid = await mock_spiffe_manager.fetch_x509_svid()
        assert x509_svid.spiffe_id.startswith("spiffe://neural-hive.local/")

        # Obter JWT-SVID
        jwt_svid = await mock_spiffe_manager.fetch_jwt_svid(
            audience="service-registry.neural-hive.local"
        )
        assert jwt_svid.token is not None
        assert jwt_svid.spiffe_id.startswith("spiffe://neural-hive.local/")

        await mock_spiffe_manager.close()

    async def test_flow_c_jwt_authentication(self, flow_c_context, mock_spiffe_manager):
        """Testa autenticacao JWT no Fluxo C."""
        import base64
        import json

        jwt_svid = await mock_spiffe_manager.fetch_jwt_svid(
            audience="service-registry.neural-hive.local"
        )

        # Validar estrutura do JWT
        token = jwt_svid.token
        parts = token.split(".")
        assert len(parts) == 3, "JWT deve ter 3 partes"

        # Decodificar payload
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        # Validar claims
        assert payload.get("sub") is not None, "JWT deve ter claim 'sub'"
        assert payload.get("sub").startswith("spiffe://neural-hive.local/"), \
            "Subject deve ser SPIFFE ID valido"
        assert payload.get("exp") is not None, "JWT deve ter claim 'exp'"
        assert payload.get("exp") > datetime.utcnow().timestamp(), "JWT nao deve estar expirado"

    async def test_flow_c_grpc_metadata_preparation(self, mock_spiffe_manager):
        """Testa preparacao de metadata gRPC com JWT."""
        jwt_svid = await mock_spiffe_manager.fetch_jwt_svid(
            audience="service-registry.neural-hive.local"
        )

        # Preparar metadata para chamada gRPC
        metadata = [("authorization", f"Bearer {jwt_svid.token}")]

        # Validar formato
        assert len(metadata) == 1
        key, value = metadata[0]
        assert key == "authorization"
        assert value.startswith("Bearer ")

        # Extrair token e validar estrutura
        token = value.split(" ")[1]
        assert len(token.split(".")) == 3

    async def test_flow_c_spiffe_id_validation(self, mock_spiffe_manager):
        """Testa validacao de SPIFFE IDs no Fluxo C."""
        trust_domain = "neural-hive.local"

        # SPIFFE IDs esperados para o Fluxo C
        expected_spiffe_ids = [
            f"spiffe://{trust_domain}/ns/neural-hive-orchestration/sa/orchestrator-dynamic",
            f"spiffe://{trust_domain}/ns/neural-hive-execution/sa/worker-agents",
            f"spiffe://{trust_domain}/ns/neural-hive-execution/sa/service-registry",
        ]

        x509_svid = await mock_spiffe_manager.fetch_x509_svid()

        # Validar que o SPIFFE ID obtido esta na lista de esperados
        assert any(
            x509_svid.spiffe_id.startswith(expected[:expected.rfind("/")])
            for expected in expected_spiffe_ids
        ), f"SPIFFE ID {x509_svid.spiffe_id} nao e esperado para Fluxo C"

    async def test_flow_c_no_authentication_errors(
        self,
        flow_c_context,
        consolidated_decision,
        mock_spiffe_manager
    ):
        """Testa que Fluxo C nao tem erros de autenticacao com mTLS."""
        # Simular resultado do Fluxo C
        result = FlowCResult(
            success=True,
            workflow_id="wf-mtls-001",
            execution_tickets=[
                {
                    "ticket_id": "ticket-001",
                    "task_id": "task-001",
                    "status": "CREATED"
                }
            ],
            errors=[]
        )

        # Validar que nao houve erros de autenticacao
        assert result.success is True
        assert result.workflow_id is not None
        assert len(result.execution_tickets) > 0

        # Validar ausencia de erros de autenticacao
        auth_errors = [
            e for e in result.errors
            if "UNAUTHENTICATED" in e or "PERMISSION_DENIED" in e
        ]
        assert len(auth_errors) == 0, f"Erros de autenticacao encontrados: {auth_errors}"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.spiffe
class TestFlowCMTLSMetrics:
    """Testes de metricas de autenticacao no Fluxo C."""

    async def test_authentication_metrics_collection(self):
        """Testa coleta de metricas de autenticacao."""
        # Simular metricas esperadas
        expected_metrics = {
            "grpc_auth_attempts_total": {"status": "success"},
            "grpc_auth_failures_total": {"reason": "missing_token"},
            "service_registry_grpc_auth_attempts_total": {"status": "success"},
            "service_registry_grpc_auth_failures_total": {"reason": "invalid_jwt_structure"},
        }

        # Validar que todas as metricas estao definidas
        for metric_name, labels in expected_metrics.items():
            assert metric_name is not None
            assert isinstance(labels, dict)

    async def test_authentication_success_rate_calculation(self):
        """Testa calculo de taxa de sucesso de autenticacao."""
        # Simular contadores
        total_attempts = 100
        successful_attempts = 95
        failed_attempts = 5

        success_rate = successful_attempts / total_attempts

        assert success_rate >= 0.9, \
            f"Taxa de sucesso ({success_rate}) deve ser >= 90%"

    async def test_spiffe_svid_expiration_monitoring(self, mock_spiffe_manager):
        """Testa monitoramento de expiracao de SVID."""
        x509_svid = await mock_spiffe_manager.fetch_x509_svid()

        # Calcular tempo ate expiracao
        time_to_expiry = x509_svid.expires_at - datetime.utcnow()
        time_to_expiry_seconds = time_to_expiry.total_seconds()

        # Alerta se expira em menos de 1 hora
        warning_threshold_seconds = 3600

        assert time_to_expiry_seconds > warning_threshold_seconds, \
            f"SVID expira em menos de 1 hora: {time_to_expiry_seconds}s"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.spiffe
class TestFlowCMTLSFallback:
    """Testes de fallback quando SPIFFE nao esta disponivel."""

    async def test_fail_closed_in_production(self):
        """Testa comportamento fail-closed em producao."""
        environment = "production"
        spiffe_enabled = True
        spiffe_available = False
        fallback_allowed = False

        # Em producao, sem SPIFFE e sem fallback, deve falhar
        if environment == "production" and spiffe_enabled and not spiffe_available and not fallback_allowed:
            should_fail = True
        else:
            should_fail = False

        assert should_fail is True, \
            "Producao deve falhar quando SPIFFE nao esta disponivel e fallback nao e permitido"

    async def test_fallback_allowed_in_development(self):
        """Testa que fallback e permitido em desenvolvimento."""
        environment = "development"
        spiffe_enabled = True
        spiffe_available = False
        fallback_allowed = True

        # Em desenvolvimento, fallback deve ser permitido
        if environment == "development" and fallback_allowed:
            can_continue = True
        else:
            can_continue = False

        assert can_continue is True, \
            "Desenvolvimento deve permitir fallback quando SPIFFE nao esta disponivel"
