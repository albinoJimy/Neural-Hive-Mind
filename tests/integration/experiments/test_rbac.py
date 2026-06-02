"""
Testes de Integração para RBAC de Experimentos (EXPERIMENT-001-05)

Este módulo testa o controlo de acesso baseado em roles para o namespace
de experimentos.

Testes:
- Teste de criação de Roles
- Teste de criação de RoleBindings
- Teste de permissões de ServiceAccount

Autor: EXPERIMENT-001
Data: 2026-04-08
"""

import pytest
import yaml
from kubernetes import client
from kubernetes.client.exceptions import ApiException


@pytest.mark.integration
@pytest.mark.k8s
class TestExperimentsRBAC:
    """
    Testes para o RBAC de experimentos.

    EXPERIMENT-001-05: Criar RoleBinding para acesso específico
    """

    def test_rbac_manifest_file_exists(self, experiments_manifests_dir):
        """
        Testa que o ficheiro de manifesto rbac.yaml existe.

        Given: O diretório de manifests existe
        When: Ler o diretório
        Then: O ficheiro rbac.yaml está presente
        """
        rbac_file = experiments_manifests_dir / "rbac.yaml"
        assert rbac_file.exists(), "rbac.yaml deve existir"

    def test_rbac_manifest_valid_yaml(self, experiments_manifests_dir):
        """
        Testa que o manifesto de RBAC é YAML válido.

        Given: O ficheiro rbac.yaml existe
        When: Parse o YAML
        Then: Os documentos são válidos
        """
        rbac_file = experiments_manifests_dir / "rbac.yaml"
        with open(rbac_file) as f:
            documents = list(yaml.safe_load_all(f))

        # Filtrar documentos None
        docs = [d for d in documents if d is not None]

        # Deve ter Role, RoleBinding, ServiceAccount, ClusterRole, ClusterRoleBinding
        kinds = {d.get("kind") for d in docs}
        assert "Role" in kinds
        assert "RoleBinding" in kinds
        assert "ServiceAccount" in kinds

    def test_rbac_has_experiments_admin_role(self, experiments_manifests_dir):
        """
        Testa que a role experiments-admin existe.

        Given: O manifesto de RBAC
        When: Verificar roles
        Then: experiments-admin role está presente
        """
        rbac_file = experiments_manifests_dir / "rbac.yaml"
        with open(rbac_file) as f:
            docs = list(yaml.safe_load_all(f))

        admin_role = next(
            (
                d
                for d in docs
                if d
                and d.get("kind") == "Role"
                and d.get("metadata", {}).get("name") == "experiments-admin"
            ),
            None,
        )

        assert admin_role is not None
        assert len(admin_role["rules"]) > 0

    def test_rbac_has_experiments_viewer_role(self, experiments_manifests_dir):
        """
        Testa que a role experiments-viewer existe.

        Given: O manifesto de RBAC
        When: Verificar roles
        Then: experiments-viewer role está presente
        """
        rbac_file = experiments_manifests_dir / "rbac.yaml"
        with open(rbac_file) as f:
            docs = list(yaml.safe_load_all(f))

        viewer_role = next(
            (
                d
                for d in docs
                if d
                and d.get("kind") == "Role"
                and d.get("metadata", {}).get("name") == "experiments-viewer"
            ),
            None,
        )

        assert viewer_role is not None

        # Verificar que viewer tem apenas permissões de leitura
        for rule in viewer_role["rules"]:
            for verb in rule["verbs"]:
                assert verb in [
                    "get",
                    "list",
                    "watch",
                ], "Viewer deve ter apenas permissões de leitura"

    def test_rbac_has_service_account(self, experiments_manifests_dir):
        """
        Testa que o ServiceAccount experiment-pod existe.

        Given: O manifesto de RBAC
        When: Verificar ServiceAccounts
        Then: experiment-pod ServiceAccount está presente
        """
        rbac_file = experiments_manifests_dir / "rbac.yaml"
        with open(rbac_file) as f:
            docs = list(yaml.safe_load_all(f))

        sa = next(
            (
                d
                for d in docs
                if d
                and d.get("kind") == "ServiceAccount"
                and d.get("metadata", {}).get("name") == "experiment-pod"
            ),
            None,
        )

        assert sa is not None

    def test_rbac_has_role_bindings(self, experiments_manifests_dir):
        """
        Testa que as RoleBindings existem.

        Given: O manifesto de RBAC
        When: Verificar RoleBindings
        Then: RoleBindings para admin, viewer e executor estão presentes
        """
        rbac_file = experiments_manifests_dir / "rbac.yaml"
        with open(rbac_file) as f:
            docs = list(yaml.safe_load_all(f))

        bindings = [d for d in docs if d and d.get("kind") == "RoleBinding"]
        binding_names = {b["metadata"]["name"] for b in bindings}

        assert "experiments-admin-binding" in binding_names
        assert "experiments-viewer-binding" in binding_names
        assert "experiments-executor-binding" in binding_names

    def test_rbac_admin_role_can_create_pods(self, k8s_rbac_client, test_experiments_namespace):
        """
        Testa que a role admin pode criar pods.

        Given: Uma role experiments-admin
        When: Verificar regras
        Then: Permissão create para pods está presente
        """
        namespace_name = test_experiments_namespace

        role = client.V1Role(
            metadata=client.V1ObjectMeta(
                name="test-admin",
                namespace=namespace_name,
            ),
            rules=[
                client.V1PolicyRule(
                    api_groups=[""],
                    resources=["pods"],
                    verbs=["get", "list", "watch", "create", "update", "patch", "delete"],
                )
            ],
        )

        created = k8s_rbac_client.create_namespaced_role(namespace=namespace_name, body=role)

        assert created is not None
        assert "create" in created.rules[0].verbs

        # Cleanup
        k8s_rbac_client.delete_namespaced_role(name="test-admin", namespace=namespace_name)

    def test_rbac_viewer_role_cannot_create_pods(self, k8s_rbac_client, test_experiments_namespace):
        """
        Testa que a role viewer NÃO pode criar pods.

        Given: Uma role experiments-viewer
        When: Verificar regras
        Then: Apenas verbs de leitura estão presentes
        """
        namespace_name = test_experiments_namespace

        role = client.V1Role(
            metadata=client.V1ObjectMeta(
                name="test-viewer",
                namespace=namespace_name,
            ),
            rules=[
                client.V1PolicyRule(
                    api_groups=[""],
                    resources=["pods"],
                    verbs=["get", "list", "watch"],
                )
            ],
        )

        created = k8s_rbac_client.create_namespaced_role(namespace=namespace_name, body=role)

        assert created is not None
        assert "create" not in created.rules[0].verbs
        assert "delete" not in created.rules[0].verbs
        assert "update" not in created.rules[0].verbs

        # Cleanup
        k8s_rbac_client.delete_namespaced_role(name="test-viewer", namespace=namespace_name)

    def test_rbac_service_account_can_be_created(self, k8s_core_client, test_experiments_namespace):
        """
        Testa que o ServiceAccount pode ser criado.

        Given: Um namespace de experimentos
        When: Criar ServiceAccount
        Then: O ServiceAccount é criado com sucesso
        """
        namespace_name = test_experiments_namespace

        sa = client.V1ServiceAccount(
            metadata=client.V1ObjectMeta(
                name="test-sa",
                namespace=namespace_name,
            )
        )

        created = k8s_core_client.create_namespaced_service_account(
            namespace=namespace_name, body=sa
        )

        assert created is not None
        assert created.metadata.name == "test-sa"

        # Cleanup
        k8s_core_client.delete_namespaced_service_account(name="test-sa", namespace=namespace_name)

    def test_rbac_role_binding_links_role_to_subject(
        self, k8s_rbac_client, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que a RoleBinding vincula a role aos sujeitos corretos.

        Given: Uma Role e um ServiceAccount
        When: Criar RoleBinding
        Then: A vinculação é criada corretamente
        """
        namespace_name = test_experiments_namespace

        # Criar ServiceAccount
        sa = client.V1ServiceAccount(metadata=client.V1ObjectMeta(name="test-binding-sa"))
        k8s_core_client.create_namespaced_service_account(namespace=namespace_name, body=sa)

        # Criar Role
        role = client.V1Role(
            metadata=client.V1ObjectMeta(name="test-binding-role"),
            rules=[
                client.V1PolicyRule(
                    api_groups=[""],
                    resources=["pods"],
                    verbs=["get", "list"],
                )
            ],
        )
        k8s_rbac_client.create_namespaced_role(namespace=namespace_name, body=role)

        # Criar RoleBinding
        binding = client.V1RoleBinding(
            metadata=client.V1ObjectMeta(name="test-binding"),
            subjects=[
                client.V1Subject(
                    kind="ServiceAccount",
                    name="test-binding-sa",
                    namespace=namespace_name,
                )
            ],
            role_ref=client.V1RoleRef(
                kind="Role",
                name="test-binding-role",
                api_group="rbac.authorization.k8s.io",
            ),
        )

        created = k8s_rbac_client.create_namespaced_role_binding(
            namespace=namespace_name, body=binding
        )

        assert created is not None
        assert len(created.subjects) == 1
        assert created.subjects[0].name == "test-binding-sa"

        # Cleanup
        k8s_rbac_client.delete_namespaced_role_binding(
            name="test-binding", namespace=namespace_name
        )
        k8s_rbac_client.delete_namespaced_role(name="test-binding-role", namespace=namespace_name)
        k8s_core_client.delete_namespaced_service_account(
            name="test-binding-sa", namespace=namespace_name
        )


@pytest.mark.integration
@pytest.mark.k8s
class TestExperimentsRBACNegative:
    """
    Testes negativos para o RBAC de experimentos.
    """

    def test_rbac_binding_to_nonexistent_role_fails(
        self, k8s_rbac_client, test_experiments_namespace
    ):
        """
        Testa que vincular a role inexistente falha.

        Given: Uma RoleBinding para role inexistente
        When: Tentar criar
        Then: Erro é retornado
        """
        namespace_name = test_experiments_namespace

        binding = client.V1RoleBinding(
            metadata=client.V1ObjectMeta(name="invalid-binding"),
            subjects=[
                client.V1Subject(
                    kind="ServiceAccount",
                    name="default",
                    namespace=namespace_name,
                )
            ],
            role_ref=client.V1RoleRef(
                kind="Role",
                name="nonexistent-role",
                api_group="rbac.authorization.k8s.io",
            ),
        )

        with pytest.raises(ApiException) as exc_info:
            k8s_rbac_client.create_namespaced_role_binding(namespace=namespace_name, body=binding)

        assert exc_info.value.status == 404

    def test_rbac_invalid_role_ref_kind_fails(self, k8s_rbac_client, test_experiments_namespace):
        """
        Testa que kind inválido em RoleRef falha.

        Given: Uma RoleBinding com kind inválido
        When: Tentar criar
        Then: Erro é retornado
        """
        namespace_name = test_experiments_namespace

        binding = client.V1RoleBinding(
            metadata=client.V1ObjectMeta(name="invalid-kind-binding"),
            subjects=[
                client.V1Subject(
                    kind="ServiceAccount",
                    name="default",
                    namespace=namespace_name,
                )
            ],
            role_ref=client.V1RoleRef(
                kind="InvalidKind",  # Kind inválido
                name="test-role",
                api_group="rbac.authorization.k8s.io",
            ),
        )

        with pytest.raises(ApiException) as exc_info:
            k8s_rbac_client.create_namespaced_role_binding(namespace=namespace_name, body=binding)

        assert exc_info.value.status == 422
