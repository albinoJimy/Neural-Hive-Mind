"""
Testes de Integração para ResourceQuota de Experimentos (EXPERIMENT-001-02)

Este módulo testa a aplicação de quotas de recursos para limitar o consumo
de recursos por experimentos.

Testes:
- EXPERIMENT-001-08: Testar aplicação de quotas
- Teste de limit enforcement
- Teste de quota breach detection

Autor: EXPERIMENT-001
Data: 2026-04-08
"""

import time

import pytest
import yaml
from kubernetes import client
from kubernetes.client.exceptions import ApiException


@pytest.mark.integration
@pytest.mark.k8s
class TestExperimentsResourceQuota:
    """
    Testes para o ResourceQuota de experimentos.

    EXPERIMENT-001-02: Definir ResourceQuota para experiments
    """

    def test_resourcequota_manifest_file_exists(self, experiments_manifests_dir):
        """
        Testa que o ficheiro de manifesto resourcequota.yaml existe.

        Given: O diretório de manifests existe
        When: Ler o diretório
        Then: O ficheiro resourcequota.yaml está presente
        """
        quota_file = experiments_manifests_dir / "resourcequota.yaml"
        assert quota_file.exists(), "resourcequota.yaml deve existir"

    def test_resourcequota_manifest_valid_yaml(self, experiments_manifests_dir):
        """
        Testa que o manifesto de quota é YAML válido.

        Given: O ficheiro resourcequota.yaml existe
        When: Parse o YAML
        Then: O documento é válido com os valores esperados
        """
        quota_file = experiments_manifests_dir / "resourcequota.yaml"
        with open(quota_file) as f:
            documents = list(yaml.safe_load_all(f))

        # Encontrar o ResourceQuota
        quota_doc = None
        for doc in documents:
            if doc and doc.get("kind") == "ResourceQuota":
                quota_doc = doc
                break

        assert quota_doc is not None, "Deve conter um ResourceQuota"
        assert quota_doc["metadata"]["name"] == "experiments-quota"
        assert quota_doc["metadata"]["namespace"] == "nhm-experiments"

    def test_resourcequota_has_cpu_limits(self, experiments_manifests_dir):
        """
        Testa que a quota tem limites de CPU configurados.

        Given: O manifesto de quota
        When: Verificar limites de CPU
        Then: requests.cpu e limits.cpu estão definidos
        """
        quota_file = experiments_manifests_dir / "resourcequota.yaml"
        with open(quota_file) as f:
            docs = list(yaml.safe_load_all(f))

        quota = next((d for d in docs if d and d.get("kind") == "ResourceQuota"), None)
        assert quota is not None

        hard = quota["spec"]["hard"]
        assert "requests.cpu" in hard
        assert "limits.cpu" in hard
        assert hard["requests.cpu"] == "8"
        assert hard["limits.cpu"] == "12"

    def test_resourcequota_has_memory_limits(self, experiments_manifests_dir):
        """
        Testa que a quota tem limites de memória configurados.

        Given: O manifesto de quota
        When: Verificar limites de memória
        Then: requests.memory e limits.memory estão definidos
        """
        quota_file = experiments_manifests_dir / "resourcequota.yaml"
        with open(quota_file) as f:
            docs = list(yaml.safe_load_all(f))

        quota = next((d for d in docs if d and d.get("kind") == "ResourceQuota"), None)
        assert quota is not None

        hard = quota["spec"]["hard"]
        assert "requests.memory" in hard
        assert "limits.memory" in hard
        assert hard["requests.memory"] == "16Gi"
        assert hard["limits.memory"] == "24Gi"

    def test_resourcequota_has_pod_limits(self, experiments_manifests_dir):
        """
        Testa que a quota tem limite de pods configurado.

        Given: O manifesto de quota
        When: Verificar limite de pods
        Then: pods está definido como 20
        """
        quota_file = experiments_manifests_dir / "resourcequota.yaml"
        with open(quota_file) as f:
            docs = list(yaml.safe_load_all(f))

        quota = next((d for d in docs if d and d.get("kind") == "ResourceQuota"), None)
        assert quota is not None

        hard = quota["spec"]["hard"]
        assert "pods" in hard
        assert hard["pods"] == "20"

    def test_resourcequota_has_pvc_limits(self, experiments_manifests_dir):
        """
        Testa que a quota tem limite de PVCs configurado.

        Given: O manifesto de quota
        When: Verificar limite de PVCs
        Then: persistentvolumeclaims está definido como 5
        """
        quota_file = experiments_manifests_dir / "resourcequota.yaml"
        with open(quota_file) as f:
            docs = list(yaml.safe_load_all(f))

        quota = next((d for d in docs if d and d.get("kind") == "ResourceQuota"), None)
        assert quota is not None

        hard = quota["spec"]["hard"]
        assert "persistentvolumeclaims" in hard
        assert hard["persistentvolumeclaims"] == "5"

    def test_resourcequota_can_be_created(
        self, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que a ResourceQuota pode ser criada no namespace.

        EXPERIMENT-001-08: Testar aplicação de quotas

        Given: Um namespace de experimentos
        When: Criar ResourceQuota
        Then: A quota é criada com sucesso
        """
        namespace_name = test_experiments_namespace

        quota = client.V1ResourceQuota(
            metadata=client.V1ObjectMeta(
                name="test-quota",
                namespace=namespace_name,
            ),
            spec=client.V1ResourceQuotaSpec(
                hard={
                    "requests.cpu": "4",
                    "requests.memory": "8Gi",
                    "limits.cpu": "8",
                    "limits.memory": "16Gi",
                    "pods": "10",
                    "persistentvolumeclaims": "3",
                },
                scopes=["NotTerminating"],
            ),
        )

        created = k8s_core_client.create_namespaced_resource_quota(
            namespace=namespace_name,
            body=quota,
        )

        assert created is not None
        assert created.metadata.name == "test-quota"

        # Cleanup
        k8s_core_client.delete_namespaced_resource_quota(
            name="test-quota", namespace=namespace_name
        )

    def test_resourcequota_enforces_pod_count(
        self, k8s_core_client, test_experiments_namespace, wait_for_resource
    ):
        """
        Testa que a quota de pods é aplicada.

        Given: Uma quota com limite de 2 pods
        When: Tentar criar o terceiro pod
        Then: O criação é rejeitada
        """
        namespace_name = test_experiments_namespace

        # Criar quota com limite baixo
        quota = client.V1ResourceQuota(
            metadata=client.V1ObjectMeta(
                name="pod-limit-quota",
                namespace=namespace_name,
            ),
            spec=client.V1ResourceQuotaSpec(
                hard={"pods": "2"},
            ),
        )
        k8s_core_client.create_namespaced_resource_quota(
            namespace=namespace_name, body=quota
        )

        # Criar 2 pods com sucesso
        for i in range(2):
            pod = client.V1Pod(
                metadata=client.V1ObjectMeta(
                    name=f"test-pod-{i}",
                ),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name="nginx",
                            image="nginx:alpine",
                        )
                    ]
                ),
            )
            k8s_core_client.create_namespaced_pod(namespace=namespace_name, body=pod)

        # Aguardar pods serem contabilizados na quota
        time.sleep(2)

        # Tentar criar o terceiro pod - deve falhar
        pod3 = client.V1Pod(
            metadata=client.V1ObjectMeta(name="test-pod-3"),
            spec=client.V1PodSpec(
                containers=[
                    client.V1Container(
                        name="nginx",
                        image="nginx:alpine",
                    )
                ]
            ),
        )

        with pytest.raises(ApiException) as exc_info:
            k8s_core_client.create_namespaced_pod(
                namespace=namespace_name, body=pod3
            )

        assert exc_info.value.status == 403
        assert "exceeded quota" in str(exc_info.value.body).lower()

        # Cleanup
        for i in range(2):
            with pytest.raises(ApiException):
                k8s_core_client.delete_namespaced_pod(
                    name=f"test-pod-{i}", namespace=namespace_name
                )
        k8s_core_client.delete_namespaced_resource_quota(
            name="pod-limit-quota", namespace=namespace_name
        )

    def test_resourcequota_tracks_usage(
        self, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que a quota rastreia o uso de recursos.

        Given: Uma quota criada
        When: Criar pods com recursos especificados
        Then: A quota mostra o uso atualizado
        """
        namespace_name = test_experiments_namespace

        quota = client.V1ResourceQuota(
            metadata=client.V1ObjectMeta(
                name="usage-tracking-quota",
                namespace=namespace_name,
            ),
            spec=client.V1ResourceQuotaSpec(
                hard={
                    "requests.cpu": "2",
                    "requests.memory": "4Gi",
                    "pods": "10",
                },
            ),
        )
        k8s_core_client.create_namespaced_resource_quota(
            namespace=namespace_name, body=quota
        )

        # Criar pod com recursos específicos
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name="usage-pod"),
            spec=client.V1PodSpec(
                containers=[
                    client.V1Container(
                        name="nginx",
                        image="nginx:alpine",
                        resources=client.V1ResourceRequirements(
                            requests={"cpu": "100m", "memory": "128Mi"},
                            limits={"cpu": "200m", "memory": "256Mi"},
                        ),
                    )
                ]
            ),
        )
        k8s_core_client.create_namespaced_pod(namespace=namespace_name, body=pod)

        # Aguardar atualização da quota
        time.sleep(2)

        # Verificar uso da quota
        quota_status = k8s_core_client.read_namespaced_resource_quota(
            name="usage-tracking-quota", namespace=namespace_name
        )

        assert quota_status.status.used is not None
        assert "pods" in quota_status.status.used
        assert int(quota_status.status.used["pods"]) >= 1

        # Cleanup
        k8s_core_client.delete_namespaced_pod(
            name="usage-pod", namespace=namespace_name
        )
        k8s_core_client.delete_namespaced_resource_quota(
            name="usage-tracking-quota", namespace=namespace_name
        )

    def test_resourcequota_scopes(
        self, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que os scopes da quota são aplicados corretamente.

        Given: Uma quota com scope NotTerminating
        When: Criar pod com activeDeadlineSeconds
        Then: O pod não conta para a quota
        """
        namespace_name = test_experiments_namespace

        quota = client.V1ResourceQuota(
            metadata=client.V1ObjectMeta(
                name="scope-quota",
                namespace=namespace_name,
            ),
            spec=client.V1ResourceQuotaSpec(
                hard={"pods": "1"},
                scopes=["NotTerminating"],
            ),
        )
        k8s_core_client.create_namespaced_resource_quota(
            namespace=namespace_name, body=quota
        )

        # Pod terminável (com activeDeadlineSeconds) não conta para quota
        terminating_pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name="terminating-pod"),
            spec=client.V1PodSpec(
                active_deadline_seconds_seconds=600,
                containers=[
                    client.V1Container(
                        name="nginx",
                        image="nginx:alpine",
                    )
                ],
            ),
        )

        # Este pod deve ser criado mesmo sem quota disponível
        k8s_core_client.create_namespaced_pod(
            namespace=namespace_name, body=terminating_pod
        )

        # Cleanup
        k8s_core_client.delete_namespaced_pod(
            name="terminating-pod", namespace=namespace_name
        )
        k8s_core_client.delete_namespaced_resource_quota(
            name="scope-quota", namespace=namespace_name
        )


@pytest.mark.integration
@pytest.mark.k8s
class TestExperimentsResourceQuotaNegative:
    """
    Testes negativos para o ResourceQuota de experimentos.
    """

    def test_resourcequota_cpu_exceed_fails(
        self, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que exceder quota de CPU falha.

        Given: Uma quota com limite de CPU
        When: Tentar criar pod que excede o limite
        Then: Erro é retornado
        """
        namespace_name = test_experiments_namespace

        quota = client.V1ResourceQuota(
            metadata=client.V1ObjectMeta(
                name="cpu-quota",
                namespace=namespace_name,
            ),
            spec=client.V1ResourceQuotaSpec(
                hard={"limits.cpu": "1"},
            ),
        )
        k8s_core_client.create_namespaced_resource_quota(
            namespace=namespace_name, body=quota
        )

        # Tentar criar pod que excede quota
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name="excess-cpu-pod"),
            spec=client.V1PodSpec(
                containers=[
                    client.V1Container(
                        name="nginx",
                        image="nginx:alpine",
                        resources=client.V1ResourceRequirements(
                            limits={"cpu": "2"}  # Excede quota de 1
                        ),
                    )
                ]
            ),
        )

        with pytest.raises(ApiException) as exc_info:
            k8s_core_client.create_namespaced_pod(
                namespace=namespace_name, body=pod
            )

        assert exc_info.value.status == 403

        # Cleanup
        k8s_core_client.delete_namespaced_resource_quota(
            name="cpu-quota", namespace=namespace_name
        )
