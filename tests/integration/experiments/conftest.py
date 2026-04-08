"""
Testes de Integração para Safe Experimentation Environment (EXPERIMENT-001)

Este módulo fornece fixtures e configurações para testar os manifests Kubernetes
do ambiente de experimentos isolados.

Autor: EXPERIMENT-001
Data: 2026-04-08
"""

import contextlib
import time
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
import yaml
from kubernetes import client, config
from kubernetes.client import (
    AppsV1Api,
    BatchV1Api,
    CoreV1Api,
    NetworkingV1Api,
    RbacAuthorizationV1Api,
)
from kubernetes.client.exceptions import ApiException


def _load_kube_config() -> None:
    """Carrega configuração do Kubernetes (local ou in-cluster)."""
    with contextlib.suppress(Exception):
        config.load_kube_config()
        return
    with contextlib.suppress(Exception):
        config.load_incluster_config()


def _load_manifest(manifest_path: Path) -> dict | None:
    """Carrega um manifesto YAML do ficheiro."""
    with open(manifest_path) as f:
        documents = list(yaml.safe_load_all(f))
        return documents if documents else None


@pytest.fixture(scope="session")
def k8s_core_client() -> CoreV1Api:
    """Cliente CoreV1Api para recursos core do Kubernetes."""
    _load_kube_config()
    api = CoreV1Api()
    return api


@pytest.fixture(scope="session")
def k8s_apps_client() -> AppsV1Api:
    """Cliente AppsV1Api para recursos de applications."""
    _load_kube_config()
    api = AppsV1Api()
    return api


@pytest.fixture(scope="session")
def k8s_networking_client() -> NetworkingV1Api:
    """Cliente NetworkingV1Api para recursos de rede."""
    _load_kube_config()
    api = NetworkingV1Api()
    return api


@pytest.fixture(scope="session")
def k8s_rbac_client() -> RbacAuthorizationV1Api:
    """Cliente RbacAuthorizationV1Api para recursos de RBAC."""
    _load_kube_config()
    api = RbacAuthorizationV1Api()
    return api


@pytest.fixture(scope="session")
def k8s_batch_client() -> BatchV1Api:
    """Cliente BatchV1Api para recursos de jobs."""
    _load_kube_config()
    api = BatchV1Api()
    return api


@pytest.fixture(scope="session")
def experiments_manifests_dir() -> Path:
    """Retorna o diretório dos manifests de experimentos."""
    return Path("/home/jimy/NHM/Neural-Hive-Mind/infrastructure/kubernetes/experiments")


@pytest.fixture(scope="session")
def experiments_namespace_name() -> str:
    """Nome do namespace de experimentos."""
    return "nhm-experiments"


@pytest.fixture(scope="function")
def test_experiments_namespace(
    k8s_core_client: CoreV1Api,
    experiments_namespace_name: str,
) -> Generator[str, None, None]:
    """
    Cria um namespace de teste para experimentos.

    Este fixture cria um namespace temporário para testes e garante
    a limpeza após o teste.
    """
    # Usar um nome único para evitar conflitos
    namespace_name = f"{experiments_namespace_name}-test-{uuid.uuid4().hex[:8]}"

    namespace = client.V1Namespace(
        metadata=client.V1ObjectMeta(
            name=namespace_name,
            labels={
                "environment": "experiments",
                "test": "integration",
                "managed-by": "nhm",
                "component": "safe-experimentation",
            },
            annotations={
                "description": "Namespace de teste para experimentos",
                "temporary": "true",
            },
        )
    )

    k8s_core_client.create_namespace(body=namespace)

    # Aguardar namespace estar pronto
    max_retries = 10
    for _ in range(max_retries):
        try:
            k8s_core_client.read_namespace(name=namespace_name)
            break
        except ApiException:
            time.sleep(0.5)
    else:
        pytest.fail("Namespace não ficou pronto em tempo útil")

    try:
        yield namespace_name
    finally:
        with contextlib.suppress(ApiException):
            k8s_core_client.delete_namespace(
                name=namespace_name,
                body=client.V1DeleteOptions(grace_period_seconds=5),
            )


@pytest.fixture(scope="session")
def experiments_base_labels() -> dict[str, str]:
    """Labels base para recursos de experimentos."""
    return {
        "app.kubernetes.io/part-of": "neural-hive-mind",
        "app.kubernetes.io/component": "safe-experimentation",
    }


@pytest.fixture
def wait_for_resource():
    """Helper para aguardar criação de recursos."""

    def _wait(
        get_func,
        name: str,
        namespace: str,
        timeout: int = 30,
        interval: float = 0.5,
    ) -> bool:
        """Aguarda until recurso existe ou timeout."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                get_func(name=name, namespace=namespace)
                return True
            except ApiException as e:
                if e.status == 404:
                    time.sleep(interval)
                else:
                    raise
        return False

    return _wait


@pytest.fixture
def create_test_pod():
    """Helper para criar um pod de teste."""

    def _create(
        core_client: CoreV1Api,
        namespace: str,
        name: str,
        image: str = "nginx:alpine",
        labels: dict[str, str] | None = None,
    ) -> client.V1Pod:
        """Cria um pod simples para testes."""
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=name,
                labels=labels or {"test": "integration"},
            ),
            spec=client.V1PodSpec(
                containers=[
                    client.V1Container(
                        name="nginx",
                        image=image,
                        ports=[client.V1ContainerPort(container_port=80)],
                    )
                ],
                restart_policy="Never",
            ),
        )
        return core_client.create_namespaced_pod(namespace=namespace, body=pod)

    return _create


@pytest.fixture
def create_test_deployment():
    """Helper para criar um deployment de teste."""

    def _create(
        apps_client: AppsV1Api,
        namespace: str,
        name: str,
        image: str = "nginx:alpine",
        labels: dict[str, str] | None = None,
    ) -> client.V1Deployment:
        """Cria um deployment simples para testes."""
        deployment = client.V1Deployment(
            metadata=client.V1ObjectMeta(
                name=name,
                labels=labels or {"test": "integration"},
            ),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(
                    match_labels=labels or {"test": "integration"},
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels=labels or {"test": "integration"},
                    ),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="nginx",
                                image=image,
                            )
                        ]
                    ),
                ),
            ),
        )
        return apps_client.create_namespaced_deployment(namespace=namespace, body=deployment)

    return _create
