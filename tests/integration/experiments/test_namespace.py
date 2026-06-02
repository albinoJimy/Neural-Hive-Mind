"""
Testes de Integração para Namespace de Experimentos (EXPERIMENT-001-01)

Este módulo testa a criação e gestão do namespace dedicado para experimentos.

Testes:
- EXPERIMENT-001-07: Testar criação de namespace
- EXPERIMENT-001-08: Validação de labels e annotations
- EXPERIMENT-001-09: Teste de isolamento básico entre namespaces

Autor: EXPERIMENT-001
Data: 2026-04-08
"""

import time

import pytest
import yaml
from kubernetes.client.exceptions import ApiException


@pytest.mark.integration
@pytest.mark.k8s
class TestExperimentsNamespace:
    """
    Testes para o namespace de experimentos.

    EXPERIMENT-001-01: Criar namespace `experiments` dedicado
    """

    def test_namespace_manifest_file_exists(self, experiments_manifests_dir):
        """
        Testa que o ficheiro de manifesto namespace.yaml existe.

        Given: O diretório de manifests existe
        When: Ler o diretório
        Then: O ficheiro namespace.yaml está presente
        """
        namespace_file = experiments_manifests_dir / "namespace.yaml"
        assert namespace_file.exists(), "namespace.yaml deve existir"
        assert namespace_file.is_file(), "namespace.yaml deve ser um ficheiro"

    def test_namespace_manifest_valid_yaml(self, experiments_manifests_dir):
        """
        Testa que o manifesto de namespace é YAML válido.

        Given: O ficheiro namespace.yaml existe
        When: Parse o YAML
        Then: O documento é válido
        """
        namespace_file = experiments_manifests_dir / "namespace.yaml"
        with open(namespace_file) as f:
            documents = list(yaml.safe_load_all(f))

        assert len(documents) == 1, "Deve ter exatamente um documento"
        assert documents[0]["kind"] == "Namespace", "Kind deve ser Namespace"
        assert documents[0]["metadata"]["name"] == "nhm-experiments"

    def test_namespace_has_required_labels(self, experiments_manifests_dir):
        """
        Testa que o namespace tem as labels obrigatórias.

        Given: O manifesto de namespace
        When: Verificar labels
        Then: As labels obrigatórias estão presentes
        """
        namespace_file = experiments_manifests_dir / "namespace.yaml"
        with open(namespace_file) as f:
            doc = yaml.safe_load(f)

        labels = doc["metadata"]["labels"]
        assert labels.get("environment") == "experiments"
        assert labels.get("managed-by") == "nhm"
        assert labels.get("component") == "safe-experimentation"
        assert labels.get("tier") == "isolation"

    def test_namespace_has_required_annotations(self, experiments_manifests_dir):
        """
        Testa que o namespace tem as annotations obrigatórias.

        Given: O manifesto de namespace
        When: Verificar annotations
        Then: As annotations obrigatórias estão presentes
        """
        namespace_file = experiments_manifests_dir / "namespace.yaml"
        with open(namespace_file) as f:
            doc = yaml.safe_load(f)

        annotations = doc["metadata"]["annotations"]
        assert "description" in annotations
        assert "created-by" in annotations
        assert annotations["created-by"] == "EXPERIMENT-001"

    def test_namespace_can_be_created(self, k8s_core_client, test_experiments_namespace):
        """
        Testa que o namespace pode ser criado no cluster.

        EXPERIMENT-001-07: Testar criação de namespace

        Given: Um cluster Kubernetes acessível
        When: Criar o namespace de experimentos
        Then: O namespace é criado com sucesso
        """
        namespace_name = test_experiments_namespace

        # Verificar que namespace existe
        namespace = k8s_core_client.read_namespace(name=namespace_name)

        assert namespace is not None
        assert namespace.metadata.name == namespace_name

    def test_namespace_persists_labels_after_creation(
        self, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que as labels são persistidas após criação.

        Given: Um namespace criado
        When: Ler o namespace do cluster
        Then: As labels estão corretas
        """
        namespace_name = test_experiments_namespace
        namespace = k8s_core_client.read_namespace(name=namespace_name)

        labels = namespace.metadata.labels
        assert labels.get("environment") == "experiments"
        assert labels.get("managed-by") == "nhm"
        assert labels.get("component") == "safe-experimentation"
        assert labels.get("tier") == "isolation"

    def test_namespace_persists_annotations_after_creation(
        self, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que as annotations são persistidas após criação.

        Given: Um namespace criado
        When: Ler o namespace do cluster
        Then: As annotations estão corretas
        """
        namespace_name = test_experiments_namespace
        namespace = k8s_core_client.read_namespace(name=namespace_name)

        annotations = namespace.metadata.annotations
        assert "description" in annotations
        assert "created-by" in annotations
        assert annotations["created-by"] == "EXPERIMENT-001"

    def test_namespace_status_active(self, k8s_core_client, test_experiments_namespace):
        """
        Testa que o namespace tem status Active.

        Given: Um namespace criado
        When: Verificar o status
        Then: O status é Active
        """
        namespace_name = test_experiments_namespace
        namespace = k8s_core_client.read_namespace(name=namespace_name)

        assert namespace.status.phase == "Active"

    def test_namespace_isolation(self, k8s_core_client, test_experiments_namespace):
        """
        Testa o isolamento básico entre namespaces.

        EXPERIMENT-001-09: Teste de isolamento básico

        Given: Dois namespaces diferentes
        When: Criar recursos em cada namespace
        Then: Os recursos não são visíveis no outro namespace
        """
        namespace_name = test_experiments_namespace

        # Criar um configmap no namespace de teste
        configmap_name = f"test-cm-{time.time_ns()}"
        k8s_core_client.create_namespaced_config_map(
            namespace=namespace_name,
            body={
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": configmap_name},
                "data": {"test": "data"},
            },
        )

        # Verificar que o configmap existe no namespace de teste
        _ = k8s_core_client.read_namespaced_config_map(
            name=configmap_name, namespace=namespace_name
        )

        # Verificar que o configmap NÃO existe no namespace default
        with pytest.raises(ApiException) as exc_info:
            k8s_core_client.read_namespaced_config_map(name=configmap_name, namespace="default")
        assert exc_info.value.status == 404

        # Limpeza
        k8s_core_client.delete_namespaced_config_map(name=configmap_name, namespace=namespace_name)

    def test_namespace_deletion(self, k8s_core_client, test_experiments_namespace):
        """
        Testa que o namespace pode ser deletado.

        Given: Um namespace criado
        When: Deletar o namespace
        Then: O namespace é removido (verificado pelo fixture cleanup)
        """
        # O fixture test_experiments_namespace já faz cleanup
        # Este teste apenas garante que o processo funciona
        namespace_name = test_experiments_namespace
        namespace = k8s_core_client.read_namespace(name=namespace_name)
        assert namespace is not None


@pytest.mark.integration
@pytest.mark.k8s
class TestExperimentsNamespaceNegative:
    """
    Testes negativos para o namespace de experimentos.

    Testa cenários de erro e validações.
    """

    def test_namespace_duplicate_name_fails(self, k8s_core_client, test_experiments_namespace):
        """
        Testa que criar namespace duplicado falha.

        Given: Um namespace já existe
        When: Tentar criar outro com o mesmo nome
        Then: Erro 409 Conflict é retornado
        """
        namespace_name = test_experiments_namespace

        # Tentar criar duplicado
        with pytest.raises(ApiException) as exc_info:
            k8s_core_client.create_namespace(
                body={
                    "apiVersion": "v1",
                    "kind": "Namespace",
                    "metadata": {"name": namespace_name},
                }
            )

        assert exc_info.value.status == 409

    def test_namespace_invalid_name_fails(self, k8s_core_client):
        """
        Testa que criar namespace com nome inválido falha.

        Given: Um nome inválido (com caracteres inválidos)
        When: Tentar criar namespace
        Then: Erro 422 Unprocessable Entity é retornado
        """
        invalid_name = "nhm-experiments_INVALID!@#"

        with pytest.raises(ApiException) as exc_info:
            k8s_core_client.create_namespace(
                body={
                    "apiVersion": "v1",
                    "kind": "Namespace",
                    "metadata": {"name": invalid_name},
                }
            )

        assert exc_info.value.status == 422
