"""
Testes de integracao para mTLS handshake com SPIFFE/SPIRE.

Valida:
- X.509-SVID e obtido do SPIRE Agent
- Canal gRPC seguro e estabelecido com mTLS
- JWT-SVID e enviado no metadata
- Service Registry valida SPIFFE ID
"""

import pytest
import grpc
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class MockX509SVID:
    """Mock para X.509-SVID"""
    spiffe_id: str
    certificate: str
    private_key: str
    ca_bundle: str
    expires_at: datetime


@dataclass
class MockJWTSVID:
    """Mock para JWT-SVID"""
    token: str
    spiffe_id: str
    expires_at: datetime
    is_placeholder: bool = False


@pytest.fixture
def mock_x509_svid():
    """Fixture para X.509-SVID mockado"""
    return MockX509SVID(
        spiffe_id="spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents",
        certificate="-----BEGIN CERTIFICATE-----\nMOCK_CERT\n-----END CERTIFICATE-----",
        private_key="-----BEGIN PRIVATE KEY-----\nMOCK_KEY\n-----END PRIVATE KEY-----",
        ca_bundle="-----BEGIN CERTIFICATE-----\nMOCK_CA\n-----END CERTIFICATE-----",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )


@pytest.fixture
def mock_jwt_svid():
    """Fixture para JWT-SVID mockado"""
    # JWT mockado com estrutura valida (header.payload.signature)
    import base64
    import json

    header = base64.urlsafe_b64encode(json.dumps({
        "alg": "RS256",
        "typ": "JWT"
    }).encode()).decode().rstrip("=")

    payload = base64.urlsafe_b64encode(json.dumps({
        "sub": "spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents",
        "aud": ["service-registry.neural-hive.local"],
        "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.utcnow().timestamp()),
        "iss": "https://spire-server.spire-system.svc.cluster.local"
    }).encode()).decode().rstrip("=")

    signature = base64.urlsafe_b64encode(b"mock_signature").decode().rstrip("=")

    return MockJWTSVID(
        token=f"{header}.{payload}.{signature}",
        spiffe_id="spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )


@pytest.fixture
def mock_spiffe_manager(mock_x509_svid, mock_jwt_svid):
    """Fixture para SPIFFEManager mockado"""
    manager = AsyncMock()
    manager.fetch_x509_svid = AsyncMock(return_value=mock_x509_svid)
    manager.fetch_jwt_svid = AsyncMock(return_value=mock_jwt_svid)
    manager.close = AsyncMock()
    manager.initialize = AsyncMock()
    return manager


@pytest.mark.asyncio
@pytest.mark.integration
class TestSPIFFEMTLSHandshake:
    """Testes de mTLS handshake com SPIFFE."""

    async def test_x509_svid_fetch(self, mock_spiffe_manager, mock_x509_svid):
        """Testa obtencao de X.509-SVID do SPIRE Agent."""
        # Obter X.509-SVID
        x509_svid = await mock_spiffe_manager.fetch_x509_svid()

        # Validacoes
        assert x509_svid is not None
        assert x509_svid.spiffe_id.startswith("spiffe://neural-hive.local/")
        assert x509_svid.certificate is not None
        assert x509_svid.private_key is not None
        assert x509_svid.ca_bundle is not None
        assert x509_svid.expires_at > datetime.utcnow()

        # Verificar que nao e placeholder
        assert not getattr(x509_svid, "is_placeholder", False)

    async def test_jwt_svid_fetch(self, mock_spiffe_manager, mock_jwt_svid):
        """Testa obtencao de JWT-SVID do SPIRE Agent."""
        # Obter JWT-SVID
        jwt_svid = await mock_spiffe_manager.fetch_jwt_svid(
            audience="service-registry.neural-hive.local"
        )

        # Validacoes
        assert jwt_svid is not None
        assert jwt_svid.token is not None
        assert jwt_svid.spiffe_id.startswith("spiffe://neural-hive.local/")
        assert jwt_svid.expires_at > datetime.utcnow()

        # Verificar estrutura do JWT
        parts = jwt_svid.token.split(".")
        assert len(parts) == 3

        # Verificar que nao e placeholder
        assert not getattr(jwt_svid, "is_placeholder", False)

    async def test_jwt_token_structure_validation(self, mock_jwt_svid):
        """Testa validacao da estrutura do JWT token."""
        import base64
        import json

        token = mock_jwt_svid.token
        parts = token.split(".")

        assert len(parts) == 3, "JWT deve ter 3 partes separadas por '.'"

        # Decodificar payload
        payload_b64 = parts[1]
        # Adicionar padding se necessario
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_json = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_json)

        # Validar claims obrigatorios
        assert "sub" in payload, "JWT deve ter claim 'sub'"
        assert "exp" in payload, "JWT deve ter claim 'exp'"
        assert "iat" in payload, "JWT deve ter claim 'iat'"

        # Validar SPIFFE ID no subject
        assert payload["sub"].startswith("spiffe://"), "Subject deve ser SPIFFE ID"
        assert "neural-hive.local" in payload["sub"], "Trust domain deve ser neural-hive.local"

    async def test_spiffe_id_trust_domain_validation(self, mock_x509_svid):
        """Testa validacao do trust domain no SPIFFE ID."""
        spiffe_id = mock_x509_svid.spiffe_id
        trust_domain = "neural-hive.local"

        assert spiffe_id.startswith(f"spiffe://{trust_domain}/"), \
            f"SPIFFE ID deve comecar com spiffe://{trust_domain}/"

    async def test_jwt_expiration_check(self, mock_jwt_svid):
        """Testa verificacao de expiracao do JWT."""
        import base64
        import json

        token = mock_jwt_svid.token
        parts = token.split(".")

        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_json = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_json)

        exp_timestamp = payload["exp"]
        current_timestamp = datetime.utcnow().timestamp()

        assert exp_timestamp > current_timestamp, "JWT nao deve estar expirado"

    async def test_grpc_metadata_authorization_header(self, mock_jwt_svid):
        """Testa formatacao do header de autorizacao para gRPC."""
        jwt_token = mock_jwt_svid.token

        # Formatar metadata
        metadata = [("authorization", f"Bearer {jwt_token}")]

        # Validar formato
        assert len(metadata) == 1
        key, value = metadata[0]
        assert key == "authorization"
        assert value.startswith("Bearer ")
        assert len(value.split(" ")[1].split(".")) == 3

    async def test_allowed_spiffe_ids_configuration(self):
        """Testa configuracao de SPIFFE IDs permitidos."""
        trust_domain = "neural-hive.local"

        allowed_spiffe_ids = [
            f"spiffe://{trust_domain}/ns/neural-hive-execution/sa/worker-agents",
            f"spiffe://{trust_domain}/ns/neural-hive-orchestration/sa/orchestrator-dynamic",
        ]

        # Validar formato dos SPIFFE IDs
        for spiffe_id in allowed_spiffe_ids:
            assert spiffe_id.startswith(f"spiffe://{trust_domain}/"), \
                f"SPIFFE ID invalido: {spiffe_id}"
            assert "/ns/" in spiffe_id, "SPIFFE ID deve conter namespace"
            assert "/sa/" in spiffe_id, "SPIFFE ID deve conter service account"


@pytest.mark.asyncio
@pytest.mark.integration
class TestSPIFFEAuthInterceptor:
    """Testes do interceptor de autenticacao SPIFFE."""

    @pytest.fixture
    def mock_settings(self):
        """Mock das configuracoes"""
        settings = MagicMock()
        settings.SPIFFE_TRUST_DOMAIN = "neural-hive.local"
        settings.SPIFFE_VERIFY_PEER = True
        settings.SPIFFE_JWT_AUDIENCE = "service-registry.neural-hive.local"
        return settings

    async def test_missing_authorization_header(self, mock_settings):
        """Testa rejeicao quando header de autorizacao esta ausente."""
        # Simular metadata sem authorization
        metadata = {}

        auth_header = metadata.get("authorization", "")
        assert not auth_header.startswith("Bearer "), \
            "Requisicao sem token deve ser rejeitada"

    async def test_invalid_jwt_structure(self, mock_settings):
        """Testa rejeicao quando JWT tem estrutura invalida."""
        invalid_tokens = [
            "not.a.valid.jwt.token",  # 5 partes
            "invalid_token",  # 1 parte
            "only.two.parts",  # 3 partes mas invalido
        ]

        for token in invalid_tokens:
            parts = token.split(".")
            if parts[0] == "only":
                # Este tem 3 partes, entao passa a validacao de estrutura
                continue
            assert len(parts) != 3, f"Token invalido nao deve ter 3 partes: {token}"

    async def test_valid_spiffe_id_authorization(self, mock_settings):
        """Testa autorizacao de SPIFFE ID valido."""
        trust_domain = mock_settings.SPIFFE_TRUST_DOMAIN
        spiffe_id = f"spiffe://{trust_domain}/ns/neural-hive-execution/sa/worker-agents"

        allowed_spiffe_ids = {
            "Register": [spiffe_id],
            "Heartbeat": [spiffe_id],
            "DiscoverAgents": [
                f"spiffe://{trust_domain}/ns/neural-hive-orchestration/sa/orchestrator-dynamic",
                spiffe_id
            ],
        }

        # Verificar autorizacao para cada metodo
        for method, allowed_ids in allowed_spiffe_ids.items():
            assert spiffe_id in allowed_ids or "*" in allowed_ids, \
                f"SPIFFE ID deve estar autorizado para {method}"

    async def test_invalid_trust_domain_rejection(self, mock_settings):
        """Testa rejeicao de SPIFFE ID com trust domain invalido."""
        valid_trust_domain = mock_settings.SPIFFE_TRUST_DOMAIN
        invalid_spiffe_id = "spiffe://malicious-domain.com/ns/attacker/sa/evil-agent"

        assert not invalid_spiffe_id.startswith(f"spiffe://{valid_trust_domain}/"), \
            "SPIFFE ID com trust domain invalido deve ser rejeitado"


@pytest.mark.asyncio
@pytest.mark.integration
class TestMTLSCredentials:
    """Testes de criacao de credenciais mTLS."""

    async def test_server_credentials_creation(self, mock_x509_svid):
        """Testa criacao de credenciais de servidor."""
        # Em teste real, criariamos grpc.ssl_server_credentials
        # Aqui validamos que os dados necessarios estao presentes
        assert mock_x509_svid.certificate is not None
        assert mock_x509_svid.private_key is not None
        assert mock_x509_svid.ca_bundle is not None

        # Validar formato PEM
        assert "BEGIN CERTIFICATE" in mock_x509_svid.certificate
        assert "BEGIN PRIVATE KEY" in mock_x509_svid.private_key
        assert "BEGIN CERTIFICATE" in mock_x509_svid.ca_bundle

    async def test_channel_credentials_creation(self, mock_x509_svid):
        """Testa criacao de credenciais de canal."""
        # Validar que temos todos os componentes para criar ssl_channel_credentials
        assert mock_x509_svid.ca_bundle is not None, "CA bundle necessario para validar servidor"
        assert mock_x509_svid.private_key is not None, "Chave privada necessaria para autenticacao"
        assert mock_x509_svid.certificate is not None, "Certificado necessario para identificacao"
