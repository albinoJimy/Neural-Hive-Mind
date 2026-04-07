"""
Testes unitários para PVCManager.

Testes para gerenciamento de PVCs em builds Kaniko com contextos grandes.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from src.services.kaniko.pvc_manager import (
    PVCManager,
    CONFIGMAP_MAX_BYTES,
    detect_large_context_and_create_pvc,
    cleanup_build_pvc,
    get_pvc_mount_spec,
)


@pytest.fixture
def mock_k8s_client():
    """Mock do cliente Kubernetes."""
    client = MagicMock()
    core_v1_api = MagicMock()
    client.CoreV1Api.return_value = core_v1_api
    return core_v1_api


@pytest.fixture
def pvc_manager(mock_k8s_client):
    """Instância do PVCManager com cliente mockado."""
    manager = PVCManager(namespace="test-namespace", storage_class="test-storage")
    manager._k8s_client = mock_k8s_client
    return manager


@pytest.fixture
def sample_dockerfile(tmp_path):
    """Cria um Dockerfile de exemplo."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12\nRUN pip install aiokafka")
    return str(dockerfile)


@pytest.fixture
def sample_build_context(tmp_path):
    """Cria um contexto de build de exemplo."""
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    (context_dir / "app.py").write_text("print('hello')")
    (context_dir / "requirements.txt").write_text("fastapi\nuvicorn")
    return str(context_dir)


@pytest.fixture
def sample_pvc():
    """Mock de PVC criado."""
    pvc = Mock()
    pvc.metadata = Mock()
    pvc.metadata.name = "kaniko-build-test123"
    pvc.metadata.namespace = "test-namespace"
    return pvc


class TestPVCManagerInitialization:
    """Testes para inicialização do PVCManager."""

    def test_initialization_with_defaults(self):
        """Testa inicialização com valores padrão."""
        manager = PVCManager()

        assert manager.namespace == "default"
        assert manager.storage_class == "standard"
        assert manager._k8s_client is None

    def test_initialization_with_custom_values(self):
        """Testa inicialização com valores customizados."""
        manager = PVCManager(namespace="custom-namespace", storage_class="ssd")

        assert manager.namespace == "custom-namespace"
        assert manager.storage_class == "ssd"

    def test_get_k8s_client_lazy_load(self, pvc_manager):
        """Testa lazy load do cliente Kubernetes."""
        # Cliente já setado via fixture
        assert pvc_manager._k8s_client is not None
        client = pvc_manager._get_k8s_client()
        assert client is not None


class TestDetectContextSize:
    """Testes para detecção de tamanho do contexto."""

    def test_detect_context_small(self, pvc_manager, sample_dockerfile, sample_build_context):
        """Testa detecção de contexto pequeno."""
        size = pvc_manager.detect_context_size(sample_dockerfile, sample_build_context)

        assert size > 0
        assert size < CONFIGMAP_MAX_BYTES
        assert size < 1024 * 1024  # Menos de 1MB

    def test_detect_context_size_with_dockerfile_only(
        self, pvc_manager, sample_dockerfile, tmp_path
    ):
        """Testa detecção com apenas Dockerfile."""
        empty_context = str(tmp_path / "empty")
        import os

        os.makedirs(empty_context, exist_ok=True)

        size = pvc_manager.detect_context_size(sample_dockerfile, empty_context)

        assert size > 0
        # Deve ser apenas o tamanho do Dockerfile

    def test_detect_context_size_nonexistent_dockerfile(self, pvc_manager, sample_build_context):
        """Testa detecção com Dockerfile inexistente."""
        size = pvc_manager.detect_context_size("/nonexistent/Dockerfile", sample_build_context)

        # Não deve falhar, apenas não contar o Dockerfile
        assert size >= 0


class TestShouldUsePVC:
    """Testes para decisão de uso de PVC."""

    def test_should_use_pvc_small_context(self, pvc_manager):
        """Testa contexto pequeno não precisa de PVC."""
        result = pvc_manager.should_use_pvc(100 * 1024)  # 100KB

        assert result is False

    def test_should_use_pvc_at_limit(self, pvc_manager):
        """Testa contexto no limite exato."""
        result = pvc_manager.should_use_pvc(CONFIGMAP_MAX_BYTES)

        assert result is False  # Limite é >

    def test_should_use_pvc_over_limit(self, pvc_manager):
        """Testa contexto acima do limite precisa de PVC."""
        result = pvc_manager.should_use_pvc(CONFIGMAP_MAX_BYTES + 1)

        assert result is True

    def test_should_use_pvc_large_context(self, pvc_manager):
        """Testa contexto grande precisa de PVC."""
        result = pvc_manager.should_use_pvc(5 * 1024 * 1024)  # 5MB

        assert result is True


class TestCalculatePVCSize:
    """Testes para cálculo de tamanho do PVC."""

    def test_calculate_size_small_context(self, pvc_manager):
        """Testa cálculo para contexto pequeno."""
        size_gb = pvc_manager.calculate_pvc_size_gb(500 * 1024)  # 500KB

        # Mínimo 1GB
        assert size_gb == 1

    def test_calculate_size_medium_context(self, pvc_manager):
        """Testa cálculo para contexto médio."""
        size_gb = pvc_manager.calculate_pvc_size_gb(10 * 1024 * 1024)  # 10MB

        # 10MB * 1.5 / 1024^3 = ~0.000014 GB, arredonda para 1
        assert size_gb == 1

    def test_calculate_size_large_context(self, pvc_manager):
        """Testa cálculo para contexto grande."""
        size_gb = pvc_manager.calculate_pvc_size_gb(500 * 1024 * 1024)  # 500MB

        # 500MB * 1.5 = 750MB, arredonda para 1GB
        assert size_gb == 1

    def test_calculate_size_very_large_context(self, pvc_manager):
        """Testa cálculo para contexto muito grande."""
        size_gb = pvc_manager.calculate_pvc_size_gb(2 * 1024 * 1024 * 1024)  # 2GB

        # 2GB * 1.5 = 3GB, int(3) + 1 = 4 (arredondamento para cima)
        assert size_gb == 4

    def test_calculate_size_with_custom_margin(self, pvc_manager):
        """Testa cálculo com margem customizada."""
        size_gb = pvc_manager.calculate_pvc_size_gb(
            1024 * 1024 * 1024, margin_multiplier=2.0  # 1GB  # 2x de margem
        )

        # 1GB * 2 = 2GB, int(2) + 1 = 3 (arredondamento para cima)
        assert size_gb == 3


class TestGetPVCName:
    """Testes para geração de nome do PVC."""

    def test_get_pvc_name_with_build_id(self, pvc_manager):
        """Testa geração de nome com build_id."""
        name = pvc_manager.get_pvc_name("my-build-123")

        assert name == "kaniko-build-my-build-123"

    def test_get_pvc_name_without_build_id(self, pvc_manager):
        """Testa geração de nome sem build_id (gera UUID)."""
        name1 = pvc_manager.get_pvc_name()
        name2 = pvc_manager.get_pvc_name()

        # Nomes devem ser diferentes (UUIDs diferentes)
        assert name1 != name2
        assert name1.startswith("kaniko-build-")
        assert len(name1) == len("kaniko-build-") + 8  # 8 caracteres hex


class TestCreatePVCForBuild:
    """Testes para criação de PVC."""

    def test_create_pvc_success(self, pvc_manager, mock_k8s_client, sample_pvc):
        """Testa criação bem-sucedida de PVC."""
        # Configurar mock para retornar PVC com nome correto
        mock_k8s_client.create_namespaced_persistent_volume_claim.return_value = sample_pvc

        result = pvc_manager.create_pvc_for_build(build_id="test", size_gb=5)

        # O get_pvc_name gera "kaniko-build-test" para build_id="test"
        assert result is not None
        # O sample_pvc mock retorna "kaniko-build-test123" mas o nome gerado é "kaniko-build-test"
        assert pvc_manager.get_pvc_name("test") == "kaniko-build-test"
        mock_k8s_client.create_namespaced_persistent_volume_claim.assert_called_once()

        # Verificar argumentos da chamada
        call_args = mock_k8s_client.create_namespaced_persistent_volume_claim.call_args
        assert call_args[1]["namespace"] == "test-namespace"

        body = call_args[1]["body"]
        assert body["metadata"]["name"] == "kaniko-build-test"
        assert body["spec"]["resources"]["requests"]["storage"] == "5Gi"
        assert body["spec"]["storageClassName"] == "test-storage"
        assert "app" in body["metadata"]["labels"]
        assert body["metadata"]["labels"]["app"] == "kaniko"

    def test_create_pvc_with_custom_access_mode(self, pvc_manager, mock_k8s_client, sample_pvc):
        """Testa criação com modo de acesso customizado."""
        mock_k8s_client.create_namespaced_persistent_volume_claim.return_value = sample_pvc

        result = pvc_manager.create_pvc_for_build(
            build_id="test-build", size_gb=2, access_mode="ReadWriteMany"
        )

        assert result is not None
        call_args = mock_k8s_client.create_namespaced_persistent_volume_claim.call_args
        assert call_args[1]["body"]["spec"]["accessModes"] == ["ReadWriteMany"]

    def test_create_pvc_without_storage_class(self, mock_k8s_client, sample_pvc):
        """Testa criação sem storage_class específico (usa default 'standard')."""
        mock_k8s_client.create_namespaced_persistent_volume_claim.return_value = sample_pvc

        manager = PVCManager(namespace="test-ns", storage_class=None)
        manager._k8s_client = mock_k8s_client

        result = manager.create_pvc_for_build("test-build", 1)

        call_args = mock_k8s_client.create_namespaced_persistent_volume_claim.call_args
        # storageClassName default é "standard" quando não especificado
        assert call_args[1]["body"]["spec"]["storageClassName"] == "standard"

    def test_create_pvc_with_labels(self, pvc_manager, mock_k8s_client, sample_pvc):
        """Testa que PVC é criado com labels corretos."""
        mock_k8s_client.create_namespaced_persistent_volume_claim.return_value = sample_pvc

        pvc_manager.create_pvc_for_build("my-build", 3)

        call_args = mock_k8s_client.create_namespaced_persistent_volume_claim.call_args
        body = call_args[1]["body"]
        labels = body["metadata"]["labels"]

        assert labels["app"] == "kaniko"
        assert labels["build-id"] == "my-build"
        assert labels["temporary"] == "true"

    def test_create_pvc_with_annotations(self, pvc_manager, mock_k8s_client, sample_pvc):
        """Testa que PVC é criado com annotations corretas."""
        mock_k8s_client.create_namespaced_persistent_volume_claim.return_value = sample_pvc

        pvc_manager.create_pvc_for_build("my-build", 2)

        call_args = mock_k8s_client.create_namespaced_persistent_volume_claim.call_args
        annotations = call_args[1]["body"]["metadata"]["annotations"]

        assert "cleanup-after" in annotations
        assert annotations["cleanup-after"] == "build-complete"


class TestGetPVCMountPath:
    """Testes para obter caminho de mount."""

    def test_get_pvc_mount_path(self, pvc_manager):
        """Testa retorno do caminho de mount padrão."""
        path = pvc_manager.get_pvc_mount_path("any-pvc-name")

        assert path == "/workspace-pvc"


class TestCleanupPVC:
    """Testes para limpeza de PVC."""

    def test_cleanup_pvc_success(self, pvc_manager, mock_k8s_client):
        """Testa limpeza bem-sucedida de PVC."""
        mock_k8s_client.delete_namespaced_persistent_volume_claim.return_value = None

        result = pvc_manager.cleanup_pvc("kaniko-build-test")

        assert result is True
        mock_k8s_client.delete_namespaced_persistent_volume_claim.assert_called_once()

        call_args = mock_k8s_client.delete_namespaced_persistent_volume_claim.call_args
        assert call_args[1]["namespace"] == "test-namespace"
        assert call_args[1]["name"] == "kaniko-build-test"

    def test_cleanup_pvc_not_found_ignore(self, pvc_manager, mock_k8s_client):
        """Testa limpeza quando PVC não existe (ignorar erro)."""
        from kubernetes.client.exceptions import ApiException

        error = ApiException(status=404, reason="Not Found")
        mock_k8s_client.delete_namespaced_persistent_volume_claim.side_effect = error

        result = pvc_manager.cleanup_pvc("nonexistent-pvc", ignore_if_not_found=True)

        # Deve retornar True porque ignoramos 404
        assert result is True

    def test_cleanup_pvc_not_found_raise(self, pvc_manager, mock_k8s_client):
        """Testa limpeza quando PVC não existe (não ignorar erro)."""
        from kubernetes.client.exceptions import ApiException

        error = ApiException(status=404, reason="Not Found")
        mock_k8s_client.delete_namespaced_persistent_volume_claim.side_effect = error

        result = pvc_manager.cleanup_pvc("nonexistent-pvc", ignore_if_not_found=False)

        # Deve retornar False porque houve erro
        assert result is False

    def test_cleanup_pvc_other_error(self, pvc_manager, mock_k8s_client):
        """Testa limpeza com outro tipo de erro."""
        from kubernetes.client.exceptions import ApiException

        error = ApiException(status=403, reason="Forbidden")
        mock_k8s_client.delete_namespaced_persistent_volume_claim.side_effect = error

        result = pvc_manager.cleanup_pvc("forbidden-pvc")

        # Deve retornar False porque houve erro não ignorado
        assert result is False


class TestListPVCsForBuild:
    """Testes para listagem de PVCs."""

    def test_list_pvcs_all(self, pvc_manager, mock_k8s_client):
        """Testa listar todos os PVCs de build."""
        mock_pvc1 = Mock()
        mock_pvc1.metadata = Mock()
        mock_pvc1.metadata.name = "kaniko-build-1"
        mock_pvc1.metadata.labels = {"app": "kaniko", "temporary": "true"}

        mock_pvc2 = Mock()
        mock_pvc2.metadata = Mock()
        mock_pvc2.metadata.name = "kaniko-build-2"
        mock_pvc2.metadata.labels = {"app": "kaniko", "temporary": "true"}

        mock_list = Mock()
        mock_list.items = [mock_pvc1, mock_pvc2]
        mock_k8s_client.list_namespaced_persistent_volume_claim.return_value = mock_list

        result = pvc_manager.list_pvcs_for_build()

        assert len(result) == 2
        assert result[0].metadata.name == "kaniko-build-1"
        assert result[1].metadata.name == "kaniko-build-2"

        # Verificar label selector
        call_args = mock_k8s_client.list_namespaced_persistent_volume_claim.call_args
        assert "label_selector" in call_args[1]
        assert "app=kaniko" in call_args[1]["label_selector"]
        assert "temporary=true" in call_args[1]["label_selector"]

    def test_list_pvcs_by_build_id(self, pvc_manager, mock_k8s_client):
        """Testa listar PVCs filtrando por build_id."""
        mock_pvc = Mock()
        mock_pvc.metadata = Mock()
        mock_pvc.metadata.name = "kaniko-build-mybuild"
        mock_pvc.metadata.labels = {"app": "kaniko", "temporary": "true", "build-id": "mybuild"}

        mock_list = Mock()
        mock_list.items = [mock_pvc]
        mock_k8s_client.list_namespaced_persistent_volume_claim.return_value = mock_list

        result = pvc_manager.list_pvcs_for_build(build_id="mybuild")

        assert len(result) == 1
        assert result[0].metadata.labels["build-id"] == "mybuild"

        call_args = mock_k8s_client.list_namespaced_persistent_volume_claim.call_args
        assert "build-id=mybuild" in call_args[1]["label_selector"]

    def test_list_pvcs_empty(self, pvc_manager, mock_k8s_client):
        """Testa listar quando não há PVCs."""
        mock_list = Mock()
        mock_list.items = []
        mock_k8s_client.list_namespaced_persistent_volume_claim.return_value = mock_list

        result = pvc_manager.list_pvcs_for_build()

        assert len(result) == 0


class TestCleanupAllBuildPVCs:
    """Testes para limpeza em lote de PVCs."""

    def test_cleanup_all_old_pvcs(self, pvc_manager, mock_k8s_client):
        """Testa limpeza de PVCs antigos."""
        # Criar PVCs com timestamps
        old_pvc = Mock()
        old_pvc.metadata = Mock()
        old_pvc.metadata.name = "old-pvc"
        old_pvc.metadata.creation_timestamp = datetime.now(timezone.utc) - timedelta(hours=25)
        old_pvc.metadata.labels = {"app": "kaniko", "temporary": "true"}

        new_pvc = Mock()
        new_pvc.metadata = Mock()
        new_pvc.metadata.name = "new-pvc"
        new_pvc.metadata.creation_timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
        new_pvc.metadata.labels = {"app": "kaniko", "temporary": "true"}

        mock_list = Mock()
        mock_list.items = [old_pvc, new_pvc]
        mock_k8s_client.list_namespaced_persistent_volume_claim.return_value = mock_list
        mock_k8s_client.delete_namespaced_persistent_volume_claim.return_value = None

        deleted = pvc_manager.cleanup_all_build_pvcs(older_than_hours=24)

        # Apenas o PVC antigo deve ser deletado
        assert deleted == 1
        mock_k8s_client.delete_namespaced_persistent_volume_claim.assert_called_once()

    def test_cleanup_all_no_old_pvcs(self, pvc_manager, mock_k8s_client):
        """Testa limpeza quando não há PVCs antigos."""
        new_pvc = Mock()
        new_pvc.metadata = Mock()
        new_pvc.metadata.name = "new-pvc"
        new_pvc.metadata.creation_timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
        new_pvc.metadata.labels = {"app": "kaniko", "temporary": "true"}

        mock_list = Mock()
        mock_list.items = [new_pvc]
        mock_k8s_client.list_namespaced_persistent_volume_claim.return_value = mock_list

        deleted = pvc_manager.cleanup_all_build_pvcs(older_than_hours=24)

        # Nenhum PVC deve ser deletado
        assert deleted == 0
        mock_k8s_client.delete_namespaced_persistent_volume_claim.assert_not_called()

    def test_cleanup_all_partial_failure(self, pvc_manager, mock_k8s_client):
        """Testa limpeza com falha parcial."""
        from kubernetes.client.exceptions import ApiException

        old_pvc1 = Mock()
        old_pvc1.metadata = Mock()
        old_pvc1.metadata.name = "old-pvc-1"
        old_pvc1.metadata.creation_timestamp = datetime.now(timezone.utc) - timedelta(hours=25)
        old_pvc1.metadata.labels = {"app": "kaniko", "temporary": "true"}

        old_pvc2 = Mock()
        old_pvc2.metadata = Mock()
        old_pvc2.metadata.name = "old-pvc-2"
        old_pvc2.metadata.creation_timestamp = datetime.now(timezone.utc) - timedelta(hours=25)
        old_pvc2.metadata.labels = {"app": "kaniko", "temporary": "true"}

        mock_list = Mock()
        mock_list.items = [old_pvc1, old_pvc2]
        mock_k8s_client.list_namespaced_persistent_volume_claim.return_value = mock_list

        # Primeiro deleta com sucesso, segundo falha
        def delete_side_effect(*args, **kwargs):
            name = kwargs.get("name") or (args[1] if len(args) > 1 else None)
            if name == "old-pvc-2":
                raise ApiException(status=403, reason="Forbidden")

        mock_k8s_client.delete_namespaced_persistent_volume_claim.side_effect = delete_side_effect

        deleted = pvc_manager.cleanup_all_build_pvcs(older_than_hours=24)

        # Apenas um deve ser deletado com sucesso
        assert deleted == 1


class TestConvenienceFunctions:
    """Testes para funções de conveniência."""

    @patch("src.services.kaniko.pvc_manager.PVCManager")
    def test_detect_large_context_and_create_pvc_small(self, mock_manager_class):
        """Testa detecção de contexto pequeno (sem PVC)."""
        mock_manager = Mock()
        mock_manager.detect_context_size.return_value = 100 * 1024
        mock_manager.should_use_pvc.return_value = False
        mock_manager_class.return_value = mock_manager

        needs_pvc, pvc_name, pvc_size_gb = detect_large_context_and_create_pvc(
            "/path/to/Dockerfile", "/path/to/context", "build-123"
        )

        assert needs_pvc is False
        assert pvc_name is None
        assert pvc_size_gb is None
        mock_manager.create_pvc_for_build.assert_not_called()

    @patch("src.services.kaniko.pvc_manager.PVCManager")
    def test_detect_large_context_and_create_pvc_large_success(self, mock_manager_class):
        """Testa detecção de contexto grande com criação bem-sucedida."""
        mock_pvc = Mock()
        mock_pvc.metadata = Mock()
        mock_pvc.metadata.name = "kaniko-build-build-123"

        mock_manager = Mock()
        mock_manager.detect_context_size.return_value = 5 * 1024 * 1024  # 5MB
        mock_manager.should_use_pvc.return_value = True
        mock_manager.calculate_pvc_size_gb.return_value = 2
        mock_manager.create_pvc_for_build.return_value = mock_pvc
        mock_manager_class.return_value = mock_manager

        needs_pvc, pvc_name, pvc_size_gb = detect_large_context_and_create_pvc(
            "/path/to/Dockerfile", "/path/to/context", "build-123"
        )

        assert needs_pvc is True
        assert pvc_name == "kaniko-build-build-123"
        assert pvc_size_gb == 2
        mock_manager.create_pvc_for_build.assert_called_once_with("build-123", 2)

    @patch("src.services.kaniko.pvc_manager.PVCManager")
    def test_detect_large_context_and_create_pvc_failure(self, mock_manager_class):
        """Testa detecção de contexto grande com falha na criação."""
        mock_manager = Mock()
        mock_manager.detect_context_size.return_value = 5 * 1024 * 1024
        mock_manager.should_use_pvc.return_value = True
        mock_manager.calculate_pvc_size_gb.return_value = 2
        mock_manager.create_pvc_for_build.side_effect = Exception("Kubernetes error")
        mock_manager_class.return_value = mock_manager

        needs_pvc, pvc_name, pvc_size_gb = detect_large_context_and_create_pvc(
            "/path/to/Dockerfile", "/path/to/context", "build-123"
        )

        # Em caso de erro, retorna False
        assert needs_pvc is False
        assert pvc_name is None
        assert pvc_size_gb is None

    @patch("src.services.kaniko.pvc_manager.PVCManager")
    def test_cleanup_build_pvc(self, mock_manager_class):
        """Testa função de conveniência para cleanup."""
        mock_manager = Mock()
        mock_manager.cleanup_pvc.return_value = True
        mock_manager_class.return_value = mock_manager

        result = cleanup_build_pvc("kaniko-build-test", "test-ns")

        assert result is True
        # Verifica que PVCManager foi instanciado com namespace correto
        mock_manager_class.assert_called_once_with(namespace="test-ns")
        # Verifica que cleanup_pvc foi chamado com o nome (ignora_not_found tem default True)
        mock_manager.cleanup_pvc.assert_called_once_with("kaniko-build-test")

    @patch("src.services.kaniko.pvc_manager.PVCManager")
    def test_get_pvc_mount_spec(self, mock_manager_class):
        """Testa função de conveniência para mount spec."""
        mock_manager = Mock()
        mock_manager.get_pvc_mount_path.return_value = "/custom-mount"
        mock_manager_class.return_value = mock_manager

        result = get_pvc_mount_spec("my-pvc")

        assert result == {"name": "my-pvc", "mountPath": "/custom-mount"}
        mock_manager.get_pvc_mount_path.assert_called_once_with("my-pvc")


class TestConstants:
    """Testes para constantes."""

    def test_configmap_max_bytes(self):
        """Testa que CONFIGMAP_MAX_BYTES está definido corretamente."""
        # Deve ser aproximadamente 800KB
        assert CONFIGMAP_MAX_BYTES == 800 * 1024
        assert CONFIGMAP_MAX_BYTES < 1024 * 1024  # Menos de 1MB
        assert CONFIGMAP_MAX_BYTES > 700 * 1024  # Mais de 700KB
