import os
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

import pytest

from tests.e2e.fixtures.vault_spire_setup import (
    vault_client,
    spiffe_manager,
    orchestrator_vault_client,
    require_real_env,
    build_test_settings,
)
from src.clients.vault_integration import OrchestratorVaultClient

# Import condicional para evitar erros quando neural_hive_security não tem VaultClient
if TYPE_CHECKING:
    try:
        from neural_hive_security import VaultClient
    except ImportError:
        VaultClient = None  # type: ignore
else:
    # Em runtime, usar MagicMock se não disponível
    try:
        from neural_hive_security import VaultClient
    except (ImportError, TypeError):
        VaultClient = None  # type: ignore

REAL_E2E = os.getenv("RUN_VAULT_SPIFFE_E2E", "").lower() == "true"
pytestmark = pytest.mark.skipif(not REAL_E2E, reason="RUN_VAULT_SPIFFE_E2E not enabled")


@pytest.mark.asyncio
async def test_vault_kubernetes_authentication(vault_client: VaultClient):
    """Valida autenticação no Vault usando token de service account."""
    require_real_env()
    assert vault_client.token is not None
    assert vault_client.token_expiry is not None
    assert vault_client.token_expiry > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_fetch_postgres_dynamic_credentials(vault_client: VaultClient):
    """Busca credenciais dinâmicas do PostgreSQL (temporal-orchestrator)."""
    require_real_env()
    creds = await vault_client.get_database_credentials("temporal-orchestrator")
    assert creds["username"]
    assert creds["password"]
    assert creds.get("ttl", 0) > 0


@pytest.mark.asyncio
async def test_fetch_static_secrets(orchestrator_vault_client: OrchestratorVaultClient):
    """Busca segredos estáticos (MongoDB, Redis, Kafka) do Vault."""
    require_real_env()
    mongodb_uri = await orchestrator_vault_client.get_mongodb_uri()
    redis_password = await orchestrator_vault_client.get_redis_password()
    kafka_creds = await orchestrator_vault_client.get_kafka_credentials()

    assert mongodb_uri
    assert redis_password is not None
    assert kafka_creds.get("username") is not None or kafka_creds.get("password") is not None


@pytest.mark.asyncio
async def test_token_renewal_before_expiration(vault_client: VaultClient):
    """Renova token do Vault antes da expiração."""
    require_real_env()
    success = await vault_client.renew_token()
    assert success is True


@pytest.mark.asyncio
async def test_credential_rotation(orchestrator_vault_client: OrchestratorVaultClient):
    """Valida renovação de credenciais dinâmicas."""
    require_real_env()
    creds = await orchestrator_vault_client.get_postgres_credentials()
    assert creds["username"]

    # Força threshold de renovação simulando expiração iminente
    orchestrator_vault_client._postgres_credentials_expiry = datetime.now(timezone.utc) + timedelta(seconds=5)
    await orchestrator_vault_client._renew_postgres_credentials_if_needed()


@pytest.mark.asyncio
async def test_fail_open_behavior_when_vault_unavailable():
    """Fail-open: credenciais de fallback quando Vault indisponível."""
    require_real_env()
    settings = build_test_settings()
    settings.vault_address = "http://127.0.0.1:9999"  # endereço inválido
    settings.vault_fail_open = True
    client = OrchestratorVaultClient(settings)
    try:
        await client.initialize()
    except Exception:
        # falha esperada; garantir fallback
        client.vault_client = None

    creds = await client.get_postgres_credentials()
    assert creds["username"] == settings.postgres_user
    assert creds["password"] == settings.postgres_password


@pytest.mark.asyncio
async def test_fail_closed_behavior_when_vault_unavailable():
    """Fail-closed: erro propagado quando fail_open=False."""
    require_real_env()
    settings = build_test_settings()
    settings.vault_address = "http://127.0.0.1:9999"
    settings.vault_fail_open = False
    client = OrchestratorVaultClient(settings)

    with pytest.raises(Exception):
        await client.initialize()


# ============================================================================
# Gap 3: Testes X.509-SVID
# ============================================================================

@pytest.mark.asyncio
async def test_fetch_x509_svid(spiffe_manager):
    """Valida obtenção de X.509-SVID via SPIFFE Workload API."""
    require_real_env()

    if not spiffe_manager:
        pytest.skip("SPIFFE manager não disponível")

    # Verificar se X.509 está habilitado
    try:
        x509_svid = await spiffe_manager.fetch_x509_svid()

        assert x509_svid is not None
        assert x509_svid.certificate
        assert x509_svid.private_key
        assert x509_svid.spiffe_id
        assert x509_svid.spiffe_id.startswith("spiffe://")

        # Validar formato do certificado PEM
        assert "-----BEGIN CERTIFICATE-----" in x509_svid.certificate
        assert "-----END CERTIFICATE-----" in x509_svid.certificate

        # Validar formato da chave privada PEM
        assert "-----BEGIN PRIVATE KEY-----" in x509_svid.private_key
        assert "-----END PRIVATE KEY-----" in x509_svid.private_key

        # Validar CA bundle
        assert x509_svid.ca_bundle
        assert "-----BEGIN CERTIFICATE-----" in x509_svid.ca_bundle

        # Validar data de expiração
        assert x509_svid.expires_at > datetime.now(timezone.utc)

    except Exception as e:
        if "X.509-SVID support is disabled" in str(e):
            pytest.skip("X.509-SVID support desabilitado na configuração")
        raise


@pytest.mark.asyncio
async def test_x509_svid_refresh(spiffe_manager):
    """Valida renovação de X.509-SVID antes da expiração."""
    require_real_env()

    if not spiffe_manager:
        pytest.skip("SPIFFE manager não disponível")

    try:
        # Buscar X.509-SVID inicial
        first_svid = await spiffe_manager.fetch_x509_svid()
        first_expiry = first_svid.expires_at

        # Buscar novamente (simular renovação)
        second_svid = await spiffe_manager.fetch_x509_svid()
        second_expiry = second_svid.expires_at

        # Validar que ambos têm SPIFFE IDs válidos
        assert first_svid.spiffe_id.startswith("spiffe://")
        assert second_svid.spiffe_id.startswith("spiffe://")

        # Em produção, as expirações devem ser diferentes após refresh
        # Em testes com placeholder, podem ser iguais
        if not first_svid.is_placeholder:
            assert first_expiry <= second_expiry or (
                second_expiry - datetime.now(timezone.utc)
            ).total_seconds() > 3600  # Pelo menos 1 hora restante

    except Exception as e:
        if "X.509-SVID support is disabled" in str(e):
            pytest.skip("X.509-SVID support desabilitado na configuração")
        raise


@pytest.mark.asyncio
async def test_x509_svid_parsing(spiffe_manager):
    """Valida parsing e estrutura do certificado X.509-SVID."""
    require_real_env()

    if not spiffe_manager:
        pytest.skip("SPIFFE manager não disponível")

    try:
        x509_svid = await spiffe_manager.fetch_x509_svid()

        # Validar estrutura do certificado PEM
        cert_lines = x509_svid.certificate.strip().split('\n')

        # Remover cabeçalho e rodapé PEM
        cert_body = [line for line in cert_lines
                     if not line.startswith('-----')]
        assert len(cert_body) > 0, "Certificado vazio"

        # Validar que é base64 válido (sem espaços ou newlines)
        import base64
        cert_data = ''.join(cert_body)
        try:
            decoded = base64.b64decode(cert_data, validate=True)
            assert len(decoded) > 0, "Certificado decodificado vazio"
        except Exception:
            pytest.fail("Certificado não contém base64 válido")

        # Validar SPIFFE ID no formato correto
        assert x509_svid.spiffe_id.startswith("spiffe://"), \
            f"SPIFFE ID inválido: {x509_svid.spiffe_id}"

        parts = x509_svid.spiffe_id.split('/')
        assert len(parts) >= 3, "SPIFFE ID deve ter pelo menos trust domain e workload"

        trust_domain = parts[2]
        assert trust_domain == "neural-hive.local" or trust_domain.endswith(".local"), \
            f"Trust domain inválido: {trust_domain}"

    except Exception as e:
        if "X.509-SVID support is disabled" in str(e):
            pytest.skip("X.509-SVID support desabilitado na configuração")
        raise


# ============================================================================
# Gap 4: Testes PKI (Vault PKI secrets engine)
# ============================================================================

@pytest.mark.asyncio
async def test_vault_pki_issue_certificate(vault_client):
    """Valida emissão de certificados via Vault PKI engine."""
    require_real_env()

    if not vault_client or not hasattr(vault_client, 'issue_certificate'):
        pytest.skip("Vault PKI não disponível")

    try:
        # Emitir certificado para um workload
        cert_result = await vault_client.issue_certificate(
            common_name="orchestrator-test.neural-hive.local",
            ttl="24h"
        )

        assert cert_result is not None
        assert "certificate" in cert_result
        assert "private_key" in cert_result
        assert "ca_chain" in cert_result

        # Validar formato do certificado PEM
        assert "-----BEGIN CERTIFICATE-----" in cert_result["certificate"]
        assert "-----END CERTIFICATE-----" in cert_result["certificate"]

        # Validar formato da chave privada
        assert "-----BEGIN" in cert_result["private_key"]
        assert "-----END" in cert_result["private_key"]

        # Validar CA chain
        assert cert_result["ca_chain"]
        assert "-----BEGIN CERTIFICATE-----" in cert_result["ca_chain"]

    except AttributeError:
        pytest.skip("Método issue_certificate não disponível (Vault client versão antiga)")
    except Exception as e:
        if "404" in str(e) or "invalid path" in str(e).lower():
            pytest.skip("Vault PKI secrets engine não configurado")
        if "403" in str(e) or "permission" in str(e).lower():
            pytest.skip("Sem permissão para PKI operations")
        raise


@pytest.mark.asyncio
async def test_vault_pki_ca_chain(vault_client):
    """Valida CA chain retornada pelo Vault PKI."""
    require_real_env()

    if not vault_client or not hasattr(vault_client, 'issue_certificate'):
        pytest.skip("Vault PKI não disponível")

    try:
        # Emitir certificado para obter CA chain
        cert_result = await vault_client.issue_certificate(
            common_name="worker-agent.neural-hive.local",
            ttl="720h"  # 30 dias
        )

        ca_chain = cert_result.get("ca_chain", "")

        # Validar que CA chain contém pelo menos um certificado
        assert ca_chain, "CA chain vazia"

        # Contar certificados na chain
        cert_count = ca_chain.count("-----BEGIN CERTIFICATE-----")
        assert cert_count >= 1, f"CA chain deve ter pelo menos 1 certificado, tem {cert_count}"

        # Validar formato PEM
        assert "-----BEGIN CERTIFICATE-----" in ca_chain
        assert "-----END CERTIFICATE-----" in ca_chain

        # Validar que CA é um certificado raiz ou intermediário
        # (CA certs geralmente têm CA:TRUE na extensão basic constraints)
        # Aqui validamos apenas formato básico
        assert len(ca_chain) > 100, "CA chain muito curta"

    except AttributeError:
        pytest.skip("Método issue_certificate não disponível (Vault client versão antiga)")
    except Exception as e:
        if "404" in str(e) or "invalid path" in str(e).lower():
            pytest.skip("Vault PKI secrets engine não configurado")
        if "403" in str(e) or "permission" in str(e).lower():
            pytest.skip("Sem permissão para PKI operations")
        raise


@pytest.mark.asyncio
async def test_vault_pki_multiple_roles(vault_client):
    """Valida emissão de certificados para múltiplas roles/workloads."""
    require_real_env()

    if not vault_client or not hasattr(vault_client, 'issue_certificate'):
        pytest.skip("Vault PKI não disponível")

    try:
        # Emitir certificados para diferentes workloads
        workloads = [
            "orchestrator.neural-hive.local",
            "worker-agent.neural-hive.local",
            "analyst-agent.neural-hive.local",
        ]

        certificates = {}

        for workload in workloads:
            try:
                cert_result = await vault_client.issue_certificate(
                    common_name=workload,
                    ttl="24h"
                )
                certificates[workload] = cert_result
            except Exception as e:
                if "404" in str(e) or "invalid path" in str(e).lower():
                    pytest.skip("Vault PKI secrets engine não configurado")
                if "403" in str(e) or "permission" in str(e).lower():
                    pytest.skip("Sem permissão para PKI operations")
                raise

        # Validar que obtivemos certificados para todos os workloads
        assert len(certificates) >= 1, "Pelo menos um certificado deve ser emitido"

        # Validar que cada certificado tem o CN correto
        for workload, cert_data in certificates.items():
            assert workload in cert_data["certificate"], \
                f"Common name {workload} não encontrado no certificado"

    except AttributeError:
        pytest.skip("Método issue_certificate não disponível (Vault client versão antiga)")
    except Exception as e:
        if "404" in str(e) or "invalid path" in str(e).lower():
            pytest.skip("Vault PKI secrets engine não configurado")
        if "403" in str(e) or "permission" in str(e).lower():
            pytest.skip("Sem permissão para PKI operations")
        raise
