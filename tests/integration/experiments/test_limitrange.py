"""
Testes de Integração para LimitRange de Experimentos (EXPERIMENT-001-04)

Este módulo testa a aplicação de limites de recursos padrão para pods
de experimentos.

Testes:
- EXPERIMENT-001-10: Testar resource limits
- Teste de defaults application
- Teste de min/max constraints

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
class TestExperimentsLimitRange:
    """
    Testes para o LimitRange de experimentos.

    EXPERIMENT-001-04: Implementar LimitRange para pods
    """

    def test_limitrange_manifest_file_exists(self, experiments_manifests_dir):
        """
        Testa que o ficheiro de manifesto limitrange.yaml existe.

        Given: O diretório de manifests existe
        When: Ler o diretório
        Then: O ficheiro limitrange.yaml está presente
        """
        limit_file = experiments_manifests_dir / "limitrange.yaml"
        assert limit_file.exists(), "limitrange.yaml deve existir"

    def test_limitrange_manifest_valid_yaml(self, experiments_manifests_dir):
        """
        Testa que o manifesto de LimitRange é YAML válido.

        Given: O ficheiro limitrange.yaml existe
        When: Parse o YAML
        Then: Os documentos são válidos
        """
        limit_file = experiments_manifests_dir / "limitrange.yaml"
        with open(limit_file) as f:
            documents = list(yaml.safe_load_all(f))

        # Filtrar documentos None
        docs = [d for d in documents if d is not None]

        # Deve ter pelo menos um LimitRange
        limit_ranges = [d for d in docs if d.get("kind") == "LimitRange"]
        assert len(limit_ranges) >= 1, "Deve ter pelo menos 1 LimitRange"

    def test_limitrange_has_container_defaults(self, experiments_manifests_dir):
        """
        Testa que o LimitRange tem defaults para containers.

        Given: O manifesto de LimitRange
        When: Verificar defaults de container
        Then: default, defaultRequest, max, min estão definidos
        """
        limit_file = experiments_manifests_dir / "limitrange.yaml"
        with open(limit_file) as f:
            docs = list(yaml.safe_load_all(f))

        limit_range = next(
            (d for d in docs if d and d.get("kind") == "LimitRange" and "limits" in d.get("metadata", {}).get("name", "")),
            None,
        )

        assert limit_range is not None

        container_limits = next(
            (limit for limit in limit_range["spec"]["limits"] if limit["type"] == "Container"),
            None,
        )

        assert container_limits is not None
        assert "default" in container_limits
        assert "defaultRequest" in container_limits
        assert "max" in container_limits
        assert "min" in container_limits

    def test_limitrange_cpu_defaults_match_spec(self, experiments_manifests_dir):
        """
        Testa que os defaults de CPU correspondem à spec.

        Given: O manifesto de LimitRange
        When: Verificar defaults de CPU
        Then: defaultRequest cpu = 100m
        """
        limit_file = experiments_manifests_dir / "limitrange.yaml"
        with open(limit_file) as f:
            docs = list(yaml.safe_load_all(f))

        limit_range = next(
            (d for d in docs if d and d.get("kind") == "LimitRange"),
            None,
        )

        container_limits = next(
            (limit for limit in limit_range["spec"]["limits"] if limit["type"] == "Container"),
            None,
        )

        assert container_limits is not None
        assert container_limits["defaultRequest"]["cpu"] == "100m"

    def test_limitrange_memory_defaults_match_spec(self, experiments_manifests_dir):
        """
        Testa que os defaults de memória correspondem à spec.

        Given: O manifesto de LimitRange
        When: Verificar defaults de memória
        Then: defaultRequest memory = 128Mi
        """
        limit_file = experiments_manifests_dir / "limitrange.yaml"
        with open(limit_file) as f:
            docs = list(yaml.safe_load_all(f))

        limit_range = next(
            (d for d in docs if d and d.get("kind") == "LimitRange"),
            None,
        )

        container_limits = next(
            (limit for limit in limit_range["spec"]["limits"] if limit["type"] == "Container"),
            None,
        )

        assert container_limits is not None
        assert container_limits["defaultRequest"]["memory"] == "128Mi"

    def test_limitrange_max_limits_match_spec(self, experiments_manifests_dir):
        """
        Testa que os limites máximos correspondem à spec.

        Given: O manifesto de LimitRange
        When: Verificar limites máximos
        Then: max cpu = 2, max memory = 4Gi
        """
        limit_file = experiments_manifests_dir / "limitrange.yaml"
        with open(limit_file) as f:
            docs = list(yaml.safe_load_all(f))

        limit_range = next(
            (d for d in docs if d and d.get("kind") == "LimitRange"),
            None,
        )

        container_limits = next(
            (limit for limit in limit_range["spec"]["limits"] if limit["type"] == "Container"),
            None,
        )

        assert container_limits is not None
        assert container_limits["max"]["cpu"] == "2"
        assert container_limits["max"]["memory"] == "4Gi"

    def test_limitrange_can_be_created(
        self, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que o LimitRange pode ser criado no namespace.

        EXPERIMENT-001-10: Testar resource limits

        Given: Um namespace de experimentos
        When: Criar LimitRange
        Then: O LimitRange é criado com sucesso
        """
        namespace_name = test_experiments_namespace

        limit_range = client.V1LimitRange(
            metadata=client.V1ObjectMeta(
                name="test-limits",
                namespace=namespace_name,
            ),
            spec=client.V1LimitRangeSpec(
                limits=[
                    client.V1LimitRangeItem(
                        type="Container",
                        default={"cpu": "500m", "memory": "512Mi"},
                        default_request={"cpu": "100m", "memory": "128Mi"},
                        max={"cpu": "2", "memory": "4Gi"},
                        min={"cpu": "10m", "memory": "32Mi"},
                    )
                ]
            ),
        )

        created = k8s_core_client.create_namespaced_limit_range(
            namespace=namespace_name,
            body=limit_range,
        )

        assert created is not None
        assert created.metadata.name == "test-limits"

        # Cleanup
        k8s_core_client.delete_namespaced_limit_range(
            name="test-limits", namespace=namespace_name
        )

    def test_limitrange_applies_defaults_to_pod(
        self, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que os defaults são aplicados a pods sem recursos.

        Given: Um LimitRange com defaults configurado
        When: Criar pod sem especificar recursos
        Then: Os defaults são aplicados automaticamente
        """
        namespace_name = test_experiments_namespace

        # Criar LimitRange
        limit_range = client.V1LimitRange(
            metadata=client.V1ObjectMeta(name="test-defaults"),
            spec=client.V1LimitRangeSpec(
                limits=[
                    client.V1LimitRangeItem(
                        type="Container",
                        default={"cpu": "200m", "memory": "256Mi"},
                        default_request={"cpu": "50m", "memory": "64Mi"},
                    )
                ]
            ),
        )
        k8s_core_client.create_namespaced_limit_range(
            namespace=namespace_name, body=limit_range
        )

        # Criar pod sem recursos especificados
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name="no-resources-pod"),
            spec=client.V1PodSpec(
                containers=[
                    client.V1Container(
                        name="nginx",
                        image="nginx:alpine",
                        # Sem recursos especificados
                    )
                ]
            ),
        )
        k8s_core_client.create_namespaced_pod(
            namespace=namespace_name, body=pod
        )

        # Aguardar pod ser criado e defaults aplicados
        time.sleep(2)

        # Verificar que os defaults foram aplicados
        updated_pod = k8s_core_client.read_namespaced_pod(
            name="no-resources-pod", namespace=namespace_name
        )

        container = updated_pod.spec.containers[0]
        assert container.resources is not None
        assert container.resources.limits is not None
        assert container.resources.requests is not None
        assert container.resources.limits.cpu == "200m"
        assert container.resources.limits.memory == "256Mi"

        # Cleanup
        k8s_core_client.delete_namespaced_pod(
            name="no-resources-pod", namespace=namespace_name
        )
        k8s_core_client.delete_namespaced_limit_range(
            name="test-defaults", namespace=namespace_name
        )

    def test_limitrange_enforces_max_limits(
        self, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que os limites máximos são aplicados.

        Given: Um LimitRange com max configurado
        When: Tentar criar pod que excede o max
        Then: A criação é rejeitada
        """
        namespace_name = test_experiments_namespace

        # Criar LimitRange com max baixo
        limit_range = client.V1LimitRange(
            metadata=client.V1ObjectMeta(name="test-max"),
            spec=client.V1LimitRangeSpec(
                limits=[
                    client.V1LimitRangeItem(
                        type="Container",
                        max={"cpu": "500m", "memory": "512Mi"},
                    )
                ]
            ),
        )
        k8s_core_client.create_namespaced_limit_range(
            namespace=namespace_name, body=limit_range
        )

        # Tentar criar pod que excede o max
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name="excess-pod"),
            spec=client.V1PodSpec(
                containers=[
                    client.V1Container(
                        name="nginx",
                        image="nginx:alpine",
                        resources=client.V1ResourceRequirements(
                            limits={"cpu": "1", "memory": "1Gi"}  # Excede max
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
        assert "max limit" in str(exc_info.value.body).lower() or "exceeds" in str(exc_info.value.body).lower()

        # Cleanup
        k8s_core_client.delete_namespaced_limit_range(
            name="test-max", namespace=namespace_name
        )

    def test_limitrange_enforces_min_limits(
        self, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que os limites mínimos são aplicados.

        Given: Um LimitRange com min configurado
        When: Tentar criar pod abaixo do min
        Then: A criação é rejeitada ou valores são ajustados
        """
        namespace_name = test_experiments_namespace

        # Criar LimitRange com min
        limit_range = client.V1LimitRange(
            metadata=client.V1ObjectMeta(name="test-min"),
            spec=client.V1LimitRangeSpec(
                limits=[
                    client.V1LimitRangeItem(
                        type="Container",
                        min={"cpu": "100m", "memory": "128Mi"},
                    )
                ]
            ),
        )
        k8s_core_client.create_namespaced_limit_range(
            namespace=namespace_name, body=limit_range
        )

        # Tentar criar pod abaixo do min - Kubernetes deve rejeitar ou ajustar
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name="below-min-pod"),
            spec=client.V1PodSpec(
                containers=[
                    client.V1Container(
                        name="nginx",
                        image="nginx:alpine",
                        resources=client.V1ResourceRequirements(
                            requests={"cpu": "10m", "memory": "32Mi"}  # Abaixo do min
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
        k8s_core_client.delete_namespaced_limit_range(
            name="test-min", namespace=namespace_name
        )

    def test_limitrange_pod_limits(self, k8s_core_client, test_experiments_namespace):
        """
        Testa que os limites de pod são aplicados.

        Given: Um LimitRange com limites de pod
        When: Verificar limites
        Then: Os limites de pod são respeitados
        """
        namespace_name = test_experiments_namespace

        limit_range = client.V1LimitRange(
            metadata=client.V1ObjectMeta(name="test-pod-limits"),
            spec=client.V1LimitRangeSpec(
                limits=[
                    client.V1LimitRangeItem(
                        type="Pod",
                        max={"cpu": "4", "memory": "8Gi"},
                    )
                ]
            ),
        )
        k8s_core_client.create_namespaced_limit_range(
            namespace=namespace_name, body=limit_range
        )

        # Verificar que LimitRange foi criada
        created = k8s_core_client.read_namespaced_limit_range(
            name="test-pod-limits", namespace=namespace_name
        )
        assert created is not None

        # Cleanup
        k8s_core_client.delete_namespaced_limit_range(
            name="test-pod-limits", namespace=namespace_name
        )


@pytest.mark.integration
@pytest.mark.k8s
class TestExperimentsLimitRangeNegative:
    """
    Testes negativos para o LimitRange de experimentos.
    """

    def test_limitrange_invalid_min_exceeds_max_fails(
        self, k8s_core_client, test_experiments_namespace
    ):
        """
        Testa que min maior que max falha.

        Given: Um LimitRange com min > max
        When: Tentar criar
        Then: Erro é retornado
        """
        namespace_name = test_experiments_namespace

        limit_range = client.V1LimitRange(
            metadata=client.V1ObjectMeta(name="invalid-limits"),
            spec=client.V1LimitRangeSpec(
                limits=[
                    client.V1LimitRangeItem(
                        type="Container",
                        min={"cpu": "1"},  # Min maior que max
                        max={"cpu": "100m"},
                    )
                ]
            ),
        )

        with pytest.raises(ApiException) as exc_info:
            k8s_core_client.create_namespaced_limit_range(
                namespace=namespace_name, body=limit_range
            )

        assert exc_info.value.status == 422
