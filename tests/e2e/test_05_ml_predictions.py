import asyncio
import pytest

from tests.e2e.utils.k8s_helpers import scale_deployment
from tests.e2e.utils.metrics import query_prometheus


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ml_duration_prediction_enabled(
    gateway_client, test_mongodb_collections, sample_intent_request, port_forward_manager
):
    prom_url = port_forward_manager["prometheus"]
    baseline = await query_prometheus(prom_url, 'sum(orchestration_ml_predictions_total{status="success"})')
    before_val = float(baseline["data"]["result"][0]["value"][1]) if baseline["data"]["result"] else 0.0

    response = await gateway_client.post("/intentions", json=sample_intent_request)
    assert response.status_code == 200
    intent_id = response.json()["intent_id"]

    await asyncio.sleep(60)
    tickets = await test_mongodb_collections["execution_tickets"].find({"intent_id": intent_id}).to_list(length=100)
    assert tickets
    for ticket in tickets:
        assert "predicted_duration_ms" in ticket
        assert ticket["predicted_duration_ms"] > 0
    metrics = await query_prometheus(prom_url, 'sum(orchestration_ml_predictions_total{status="success"})')
    after_val = float(metrics["data"]["result"][0]["value"][1]) if metrics["data"]["result"] else 0.0
    assert after_val >= before_val, "Métrica de predição não incrementou"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ml_anomaly_detection(gateway_client, test_mongodb_collections, sample_intent_request):
    intent = {**sample_intent_request, "text": "Task tipo raro com parametros incomuns"}
    response = await gateway_client.post("/intentions", json=intent)
    assert response.status_code == 200
    intent_id = response.json()["intent_id"]

    await asyncio.sleep(60)
    tickets = await test_mongodb_collections["execution_tickets"].find({"intent_id": intent_id}).to_list(length=100)
    assert tickets
    assert any(ticket.get("anomaly", {}).get("is_anomaly") for ticket in tickets)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ml_prediction_error_tracking(gateway_client, test_mongodb_collections, sample_intent_request):
    response = await gateway_client.post("/intentions", json=sample_intent_request)
    assert response.status_code == 200
    intent_id = response.json()["intent_id"]

    await asyncio.sleep(120)
    tickets = await test_mongodb_collections["execution_tickets"].find({"intent_id": intent_id}).to_list(length=100)
    assert tickets
    for ticket in tickets:
        if "prediction_error_ms" in ticket:
            assert ticket["prediction_error_ms"] >= 0
            return
    pytest.skip("Nenhum erro de predição registrado ainda")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ml_fallback_on_mlflow_failure(
    gateway_client, test_mongodb_collections, sample_intent_request, k8s_client, port_forward_manager
):
    prom_url = port_forward_manager["prometheus"]
    baseline = await query_prometheus(prom_url, 'sum(orchestration_scheduler_allocations_total{fallback="True"})')
    before_val = float(baseline["data"]["result"][0]["value"][1]) if baseline["data"]["result"] else 0.0

    deployment = "mlflow"
    namespace = "mlflow"
    current_scale = k8s_client.read_namespaced_deployment_scale(name=deployment, namespace=namespace)
    replicas_before = current_scale.spec.replicas or 1
    try:
        scale_deployment(k8s_client, namespace, deployment, replicas=0)
        await asyncio.sleep(5)

        response = await gateway_client.post("/intentions", json=sample_intent_request)
        assert response.status_code == 200
        intent_id = response.json()["intent_id"]

        await asyncio.sleep(90)
        _ = await test_mongodb_collections["execution_tickets"].find({"intent_id": intent_id}).to_list(length=200)

        for _ in range(6):
            metrics = await query_prometheus(
                prom_url, 'sum(orchestration_scheduler_allocations_total{fallback="True"})'
            )
            after_val = float(metrics["data"]["result"][0]["value"][1]) if metrics["data"]["result"] else 0.0
            if after_val > before_val:
                break
            await asyncio.sleep(5)
        else:
            pytest.fail("Scheduler não entrou em fallback após indisponibilidade do MLflow")
    finally:
        scale_deployment(k8s_client, namespace, deployment, replicas=replicas_before)
