"""
Testes TDD para Policy Bundle Management (INFRA-002-07).

Siga o ciclo RED-GREEN-REFACTOR:
1. Escreva teste (RED - falha esperada)
2. Implemente código mínimo (GREEN - teste passa)
3. Refatore (REFACTOR - melhorias)
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest
import httpx

from neural_hive_opa import (
    PolicyBundle,
    PolicyBundleInfo,
    PolicyBundleManager,
    PolicyStatus,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_bundle_dir(tmp_path):
    """Diretório temporário para bundles."""
    bundle_dir = tmp_path / "opa_bundles"
    bundle_dir.mkdir(exist_ok=True)
    return bundle_dir


@pytest.fixture
def sample_policies():
    """Políticas de exemplo."""
    return {
        "authz": """
        package neuralhive.authz

        default allow = false

        allow {
            input.user.role == "admin"
        }
        """,
        "rbac": """
        package neuralhive.rbac

        default allow = false

        allow[input.user.permissions[_] == required_permission] {
            required_permission := input.resource.permission
        }
        """,
    }


# =============================================================================
# Testes: PolicyBundle
# =============================================================================

class TestPolicyBundle:
    """Testes para PolicyBundle."""

    def test_create_bundle(self):
        """
        DADO: Nome e versão
        QUANDO: Crio PolicyBundle
        ENTÃO: Bundle deve ser criado com valores corretos
        """
        bundle = PolicyBundle(
            name="test-bundle",
            version="1.0.0",
            policies={"policy1": "content"},
        )

        assert bundle.name == "test-bundle"
        assert bundle.version == "1.0.0"
        assert bundle.policies == {"policy1": "content"}
        assert bundle.status == PolicyStatus.PENDING

    def test_hash(self):
        """
        DADO: Bundle com políticas
        QUANDO: Calculo hash
        ENTÃO: Hash deve ser consistente
        """
        bundle = PolicyBundle(
            name="test",
            version="1.0",
            policies={"policy": "same content"},
        )

        hash1 = bundle.hash()
        hash2 = bundle.hash()

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex

    def test_hash_different_content(self):
        """
        DADO: Dois bundles com conteúdo diferente
        QUANDO: Calculo hash de cada um
        ENTÃO: Hashes devem ser diferentes
        """
        bundle1 = PolicyBundle(
            name="test",
            version="1.0",
            policies={"policy": "content A"},
        )
        bundle2 = PolicyBundle(
            name="test",
            version="1.0",
            policies={"policy": "content B"},
        )

        assert bundle1.hash() != bundle2.hash()


# =============================================================================
# Testes: PolicyBundleInfo
# =============================================================================

class TestPolicyBundleInfo:
    """Testes para PolicyBundleInfo."""

    def test_from_bundle(self):
        """
        DADO: PolicyBundle
        QUANDO: Crio PolicyBundleInfo
        ENTÃO: Campos devem corresponder
        """
        bundle = PolicyBundle(
            name="test",
            version="1.0",
            policies={"policy1": "content1", "policy2": "content2"},
            created_at=datetime(2026, 1, 1, 12, 0, 0),
        )

        info = PolicyBundleInfo(
            name=bundle.name,
            version=bundle.version,
            policy_count=len(bundle.policies),
            hash=bundle.hash(),
            created_at=bundle.created_at.isoformat(),
            status=bundle.status,
        )

        assert info.name == "test"
        assert info.version == "1.0"
        assert info.policy_count == 2
        assert len(info.hash) == 64


# =============================================================================
# Testes: PolicyBundleManager
# =============================================================================

class TestPolicyBundleManager:
    """Testes para PolicyBundleManager."""

    def test_init(self, temp_bundle_dir):
        """
        DADO: Diretório de bundles
        QUANDO: Crio PolicyBundleManager
        ENTÃO: Deve usar diretório fornecido
        """
        manager = PolicyBundleManager(
            opa_url="http://opa:8181",
            bundle_path=str(temp_bundle_dir),
        )

        assert manager.opa_url == "http://opa:8181"
        assert manager.bundle_path == temp_bundle_dir

    def test_init_defaults(self, tmp_path):
        """
        DADO: Nenhum argumento
        QUANDO: Crio PolicyBundleManager
        ENTÃO: Deve usar defaults
        """
        manager = PolicyBundleManager()

        assert manager.opa_url == "http://localhost:8181"
        assert manager.bundle_path.exists()

    @pytest.mark.asyncio
    async def test_create_bundle(self, sample_policies):
        """
        DADO: Políticas de exemplo
        QUANDO: Crio bundle com create_bundle
        ENTÃO: Bundle deve ser criado e ativado
        """
        manager = PolicyBundleManager()

        info = await manager.create_bundle(
            name="test-bundle",
            version="1.0",
            policies=sample_policies,
            activate=False,  # Não ativar para evitar chamada OPA
        )

        assert info.name == "test-bundle"
        assert info.version == "1.0"
        assert info.policy_count == 2

    @pytest.mark.asyncio
    async def test_list_bundles_empty(self):
        """
        DADO: Gerenciador sem bundles
        QUANDO: Listo bundles
        ENTÃO: Deve retornar lista vazia
        """
        manager = PolicyBundleManager()

        bundles = await manager.list_bundles()

        assert bundles == []

    @pytest.mark.asyncio
    async def test_list_bundles_after_create(self, sample_policies):
        """
        DADO: Gerenciador com bundles criados
        QUANDO: Listo bundles
        ENTÃO: Deve retornar lista com bundles
        """
        manager = PolicyBundleManager()

        await manager.create_bundle(
            name="bundle1",
            version="1.0",
            policies=sample_policies,
            activate=False,
        )
        await manager.create_bundle(
            name="bundle2",
            version="1.0",
            policies=sample_policies,
            activate=False,
        )

        bundles = await manager.list_bundles()

        assert len(bundles) == 2
        bundle_names = [b.name for b in bundles]
        assert "bundle1" in bundle_names
        assert "bundle2" in bundle_names

    @pytest.mark.asyncio
    async def test_get_bundle(self, sample_policies):
        """
        DADO: Bundle criado
        QUANDO: Busco bundle por nome
        ENTÃO: Deve retornar informações do bundle
        """
        manager = PolicyBundleManager()

        await manager.create_bundle(
            name="test-bundle",
            version="2.0",
            policies=sample_policies,
            activate=False,
        )

        info = await manager.get_bundle("test-bundle", "2.0")

        assert info is not None
        assert info.name == "test-bundle"
        assert info.version == "2.0"

    @pytest.mark.asyncio
    async def test_get_bundle_not_found(self):
        """
        DADO: Gerenciador vazio
        QUANDO: Busco bundle inexistente
        ENTÃO: Deve retornar None
        """
        manager = PolicyBundleManager()

        info = await manager.get_bundle("nonexistent", "1.0")

        assert info is None

    @pytest.mark.asyncio
    async def test_get_bundle_latest_version(self, sample_policies):
        """
        DADO: Múltiplas versões de um bundle
        QUANDO: Busco com version="latest"
        ENTÃO: Deve retornar versão mais recente
        """
        manager = PolicyBundleManager()

        await manager.create_bundle("test", "1.0", sample_policies, activate=False)
        await manager.create_bundle("test", "2.0", sample_policies, activate=False)
        await manager.create_bundle("test", "3.0", sample_policies, activate=False)

        info = await manager.get_bundle("test", "latest")

        assert info is not None
        assert info.version == "3.0"

    @pytest.mark.asyncio
    async def test_activate_bundle(self, sample_policies):
        """
        DADO: Bundle criado
        QUANDO: Ativo bundle
        ENTÃO: Deve fazer upload para OPA
        """
        manager = PolicyBundleManager()

        # Mock HTTP client
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=MagicMock(status_code=200, raise_for_status=MagicMock()))
        manager._client = mock_client

        await manager.create_bundle("test", "1.0", sample_policies, activate=False)

        await manager.activate_bundle("test", "1.0")

        # Verificar que put foi chamado para cada política
        assert mock_client.put.call_count == 2  # authz + rbac

    @pytest.mark.asyncio
    async def test_cleanup_old_bundles(self, sample_policies, temp_bundle_dir):
        """
        DADO: Múltiplas versões de bundle
        QUANDO: Limpo versões antigas (keep=2)
        ENTÃO: Deve remover versões antigas mantendo as 2 mais recentes
        """
        manager = PolicyBundleManager(bundle_path=str(temp_bundle_dir))

        # Criar bundles em versões diferentes
        for version in ["1.0", "2.0", "3.0", "4.0"]:
            await manager.create_bundle("test", version, sample_policies, activate=False)

        # Limpar mantendo 2 versões
        removed = await manager.cleanup_old_bundles("test", keep_versions=2)

        # Deve ter removido 1.0 e 2.0
        assert len(removed) == 2
        assert "1.0" in removed
        assert "2.0" in removed

        # Versões 3.0 e 4.0 devem permanecer
        info_30 = await manager.get_bundle("test", "3.0")
        info_40 = await manager.get_bundle("test", "4.0")
        assert info_30 is not None
        assert info_40 is not None

    @pytest.mark.asyncio
    async def test_validate_policy_success(self):
        """
        DADO: Política OPA válida
        QUANDO: Valido política
        ENTÃO: Deve retornar valid=True
        """
        manager = PolicyBundleManager()

        # Mock cliente OPA
        mock_client = AsyncMock()
        mock_response = MagicMock(status_code=200)
        mock_client.post = AsyncMock(return_value=mock_response)
        manager._client = mock_client

        result = await manager.validate_policy("package test { default allow = true }")

        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_policy_error(self):
        """
        DADO: Política OPA inválida
        QUANDO: Valido política
        ENTÃO: Deve retornar valid=False com erros
        """
        manager = PolicyBundleManager()

        # Mock cliente OPA
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json = MagicMock(return_value={"errors": ["syntax error"]})
        mock_client.post = AsyncMock(return_value=mock_response)
        manager._client = mock_client

        result = await manager.validate_policy("invalid policy {")

        assert result["valid"] is False
        assert len(result["errors"]) > 0


# =============================================================================
# Testes: Error Handling
# =============================================================================

class TestErrorHandling:
    """Testes para tratamento de erros."""

    @pytest.mark.asyncio
    async def test_download_bundle_failure(self):
        """
        DADO: Mock que retorna erro HTTP
        QUANDO: Tento download bundle
        ENTÃO: Deve levantar exceção HTTP
        """
        manager = PolicyBundleManager()

        # Mock cliente HTTP que falha
        mock_client = AsyncMock()

        # Criar request e response mocks
        mock_request = MagicMock()
        mock_request.url = "http://invalid-url/bundle.tar.gz"

        mock_response = MagicMock()
        mock_response.status_code = 404

        exc = httpx.HTTPStatusError(
            "Not Found",
            request=mock_request,
            response=mock_response,
        )
        mock_client.get = AsyncMock(side_effect=exc)
        manager._client = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await manager.download_bundle(
                bundle_url="http://invalid-url/bundle.tar.gz",
                name="test",
                version="1.0",
            )

    @pytest.mark.asyncio
    async def test_activate_bundle_not_loaded(self):
        """
        DADO: Bundle não carregado
        QUANDO: Tento ativar
        ENTÃO: Deve levantar ValueError
        """
        manager = PolicyBundleManager()

        with pytest.raises(ValueError, match="Bundle not loaded"):
            await manager.activate_bundle("nonexistent", "1.0")


# =============================================================================
# Testes: PolicyStatus Enum
# =============================================================================

class TestPolicyStatus:
    """Testes para PolicyStatus enum."""

    def test_status_values(self):
        """
        DADO: Enum PolicyStatus
        QUANDO: Verifico valores
        ENTÃO: Deve ter valores corretos
        """
        assert PolicyStatus.ACTIVE == "active"
        assert PolicyStatus.INACTIVE == "inactive"
        assert PolicyStatus.PENDING == "pending"
        assert PolicyStatus.ERROR == "error"
