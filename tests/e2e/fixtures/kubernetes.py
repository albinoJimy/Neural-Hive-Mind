import contextlib
import os
import signal
import subprocess
import time
import uuid
from typing import Dict, Optional

import pytest
from kubernetes import client, config
from kubernetes.client import CoreV1Api
from kubernetes.client.exceptions import ApiException


def _load_kube_config() -> None:
    with contextlib.suppress(Exception):
        config.load_kube_config()
        return
    with contextlib.suppress(Exception):
        config.load_incluster_config()


@pytest.fixture(scope="session")
def k8s_client() -> CoreV1Api:
    _load_kube_config()
    api = client.CoreV1Api()
    api.list_namespace()  # validates connectivity
    return api


@pytest.fixture(scope="function")
def test_namespace(k8s_client: CoreV1Api) -> str:
    namespace_name = f"e2e-test-{uuid.uuid4().hex[:8]}"
    namespace = client.V1Namespace(
        metadata=client.V1ObjectMeta(
            name=namespace_name,
            labels={"test": "e2e", "timestamp": str(time.time())},
        )
    )
    k8s_client.create_namespace(body=namespace)
    try:
        yield namespace_name
    finally:
        with contextlib.suppress(ApiException):
            k8s_client.delete_namespace(name=namespace_name, grace_period_seconds=0)


def _start_port_forward(namespace: str, service: str, local_port: int, remote_port: int) -> subprocess.Popen:
    cmd = [
        "kubectl",
        "port-forward",
        f"-n{namespace}",
        f"svc/{service}",
        f"{local_port}:{remote_port}",
    ]
    env = os.environ.copy()
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, preexec_fn=os.setsid)


@pytest.fixture(scope="session")
def port_forward_manager() -> Dict[str, str]:
    forwards = {
        "gateway": ("neural-hive-orchestration", "gateway", 8000, 8000),
        "orchestrator": ("neural-hive-orchestration", "orchestrator-dynamic", 8001, 8001),
        "prometheus": ("monitoring", "prometheus-server", 9090, 9090),
        "jaeger": ("observability", "jaeger-query", 16686, 16686),
    }
    processes: Dict[str, subprocess.Popen] = {}
    endpoints: Dict[str, str] = {}
    for name, (namespace, service, local_port, remote_port) in forwards.items():
        proc = _start_port_forward(namespace, service, local_port, remote_port)
        processes[name] = proc
        endpoints[name] = f"localhost:{local_port}"
    # allow port-forwards to establish
    time.sleep(3)
    try:
        yield endpoints
    finally:
        for proc in processes.values():
            with contextlib.suppress(Exception):
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)


@pytest.fixture(scope="session")
def k8s_service_endpoints(k8s_client: CoreV1Api) -> Dict[str, str]:
    services = {
        "kafka": ("neural-hive-kafka", "kafka", 9092),
        "schema_registry": ("neural-hive-kafka", "schema-registry", 8081),
        "mongodb": ("mongodb-cluster", "mongodb", 27017),
        "redis": ("redis-cluster", "redis", 6379),
        "service_registry": ("neural-hive-orchestration", "service-registry", 50051),
        "temporal": ("neural-hive-orchestration", "temporal-frontend", 7233),
        "temporal_db": ("temporal", "temporal-postgresql", 5432),
    }
    endpoints: Dict[str, str] = {}
    for name, (namespace, service, port) in services.items():
        svc = k8s_client.read_namespaced_service(name=service, namespace=namespace)
        host = f"{svc.metadata.name}.{svc.metadata.namespace}.svc.cluster.local"
        endpoints[name] = f"{host}:{port}"
    return endpoints
