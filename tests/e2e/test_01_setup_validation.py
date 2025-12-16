import asyncio

import httpx
import pytest

from tests.e2e.utils.k8s_helpers import get_pod_logs


@pytest.mark.e2e
def test_kubernetes_cluster_accessible(k8s_client):
    namespaces = [ns.metadata.name for ns in k8s_client.list_namespace().items]
    expected = {"fluxo-a", "semantic-translation", "consensus-orchestration", "neural-hive-orchestration", "neural-hive-execution"}
    assert expected.issubset(set(namespaces))


@pytest.mark.e2e
def test_kafka_cluster_healthy(kafka_admin_client):
    metadata = kafka_admin_client.list_topics(timeout=10)
    topics = metadata.topics
    required_topics = ["intentions", "plans.ready", "plans.consensus", "execution.tickets"]
    for topic in required_topics:
        assert topic in topics, f"Tópico {topic} não encontrado"
        assert len(topics[topic].partitions) == 3


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_schema_registry_accessible(k8s_service_endpoints):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"http://{k8s_service_endpoints['schema_registry']}/subjects")
        resp.raise_for_status()
        subjects = resp.json()
    assert any("ExecutionTicket" in s or "execution-ticket" in s for s in subjects)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mongodb_accessible(mongodb_client):
    dbs = await mongodb_client.list_database_names()
    assert dbs, "MongoDB não retornou databases"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_redis_accessible(redis_client):
    pong = await redis_client.ping()
    assert pong is True


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_temporal_server_accessible(temporal_client):
    namespaces = await temporal_client.workflow_service.get_system_info()
    assert namespaces, "Temporal não respondeu"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_server_accessible(port_forward_manager):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"http://{port_forward_manager['orchestrator']}/opa/health")
        resp.raise_for_status()
    assert resp.status_code == 200


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_all_services_healthy(k8s_client):
    namespaces = ["neural-hive-orchestration", "neural-hive-execution"]
    for ns in namespaces:
        pods = k8s_client.list_namespaced_pod(namespace=ns).items
        assert pods, f"Nenhum pod em {ns}"
        for pod in pods:
            conditions = pod.status.conditions or []
            ready = any(c.type == "Ready" and c.status == "True" for c in conditions)
            assert ready, f"Pod {pod.metadata.name} não está Ready em {ns}"
            logs = get_pod_logs(k8s_client, ns, f"app={pod.metadata.labels.get('app','')}", tail_lines=5)
            assert logs is not None
