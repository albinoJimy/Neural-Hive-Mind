import asyncio

import pytest

# Skip se dependências não estão disponíveis
pytest.importorskip("aiohttp")
kubernetes = pytest.importorskip("kubernetes")

import aiohttp

from tests.e2e.utils.k8s_helpers import get_pod_logs
from tests.e2e.utils.metrics import query_prometheus, get_metric_value


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_resource_limits_enforcement(
    orchestrator_client, sample_opa_policy_violation, k8s_client, port_forward_manager
):
    prom_url = port_forward_manager["prometheus"]
    baseline = await query_prometheus(prom_url, "sum(orchestration_opa_policy_rejections_total)")
    before_val = float(baseline["data"]["result"][0]["value"][1]) if baseline["data"]["result"] else 0.0

    response = await orchestrator_client.post("/api/v1/flow-c/execute", json=sample_opa_policy_violation)
    assert response.status_code in {400, 403}
    error = response.json()
    detail_str = str(error).lower()
    assert "policy" in detail_str
    assert "resource" in detail_str or "cpu" in detail_str

    logs = get_pod_logs(k8s_client, "neural-hive-orchestration", "app=orchestrator-dynamic", tail_lines=50)
    assert "OPA" in logs or "policy" in logs

    for _ in range(6):
        metrics = await query_prometheus(prom_url, "sum(orchestration_opa_policy_rejections_total)")
        current = float(metrics["data"]["result"][0]["value"][1]) if metrics["data"]["result"] else 0.0
        if current > before_val:
            break
        await asyncio.sleep(5)
    else:
        pytest.fail("Métrica orchestration_opa_policy_rejections_total não incrementou após violação de recursos")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_sla_enforcement(orchestrator_client, sample_execution_ticket, port_forward_manager):
    prom_url = port_forward_manager["prometheus"]
    baseline = await query_prometheus(prom_url, "sum(orchestration_opa_policy_rejections_total)")
    before_val = float(baseline["data"]["result"][0]["value"][1]) if baseline["data"]["result"] else 0.0

    ticket = {**sample_execution_ticket, "sla_deadline_ms": 0}
    response = await orchestrator_client.post("/api/v1/flow-c/execute", json=ticket)
    assert response.status_code in {400, 403}
    body = response.json()
    assert "sla" in str(body).lower()

    metrics = await query_prometheus(prom_url, "sum(orchestration_opa_policy_rejections_total)")
    after_val = float(metrics["data"]["result"][0]["value"][1]) if metrics["data"]["result"] else 0.0
    assert after_val >= before_val, "Métrica de rejeição OPA não encontrada para SLA"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_feature_flags(orchestrator_client, port_forward_manager):
    response = await orchestrator_client.get("/api/v1/flow-c/features")
    assert response.status_code in {200, 404}
    data = response.json() if response.status_code == 200 else {}
    flag_state = data.get("intelligent_scheduler_enabled", False) if isinstance(data, dict) else False
    prom_val = await get_metric_value(
        port_forward_manager["prometheus"],
        "orchestration_opa_feature_flags",
        labels={"flag_name": "intelligent_scheduler_enabled"},
    )
    if prom_val is not None:
        flag_metric = float(prom_val)
        if not flag_state:
            assert flag_metric == 0.0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_burst_capacity(orchestrator_client, sample_execution_ticket):
    tasks = [sample_execution_ticket for _ in range(5)]
    payload = {"tickets": tasks}
    response = await orchestrator_client.post("/api/v1/flow-c/bulk", json=payload)
    assert response.status_code in {200, 207, 429}
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    results = data.get("results", []) if isinstance(data, dict) else []
    accepted = sum(1 for r in results if str(r.get("status")).lower() in {"accepted", "ok", "created", "200"})
    rejected = sum(1 for r in results if str(r.get("status")).lower() in {"rejected", "denied", "429", "403"})
    if results:
        assert accepted + rejected >= len(tasks)
        if response.status_code == 429:
            assert rejected > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_circuit_breaker(orchestrator_client, k8s_client, port_forward_manager):
    prom_url = port_forward_manager["prometheus"]
    # Força indisponibilidade do OPA escalando para 0 e valida circuito aberto
    deployment = "opa"
    namespace = "neural-hive-orchestration"
    current_scale = k8s_client.read_namespaced_deployment_scale(name=deployment, namespace=namespace)
    replicas_before = current_scale.spec.replicas or 1
    try:
        k8s_client.patch_namespaced_deployment_scale(
            name=deployment, namespace=namespace, body={"spec": {"replicas": 0}}
        )
        await asyncio.sleep(5)
        response = await orchestrator_client.post("/api/v1/flow-c/execute", json={"ticket_id": "opa-cb-test"})
        assert response.status_code in {200, 202, 503}

        for _ in range(6):
            metrics = await query_prometheus(
                prom_url, 'orchestration_opa_circuit_breaker_state{circuit_name="opa_client"}'
            )
            results = metrics.get("data", {}).get("result", [])
            if results and float(results[0]["value"][1]) >= 1.0:
                break
            await asyncio.sleep(5)
        else:
            pytest.fail("Circuit breaker OPA não foi acionado (métrica permaneceu 0)")
    finally:
        k8s_client.patch_namespaced_deployment_scale(
            name=deployment, namespace=namespace, body={"spec": {"replicas": replicas_before}}
        )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_security_tenant_isolation(orchestrator_client, sample_execution_ticket, port_forward_manager):
    """Testa enforcement de isolamento de tenant."""
    prom_url = port_forward_manager["prometheus"]
    
    # Ticket com tenant não autorizado
    ticket = {
        **sample_execution_ticket,
        "tenant_id": "tenant-unauthorized",
        "user_id": "user@example.com",
        "jwt_token": "eyJhbGc.eyJzdWI.signature"
    }
    
    response = await orchestrator_client.post("/api/v1/flow-c/execute", json=ticket)
    assert response.status_code in {400, 403}
    
    error = response.json()
    assert "tenant" in str(error).lower() or "security" in str(error).lower()
    
    # Verificar métrica de violação
    for _ in range(6):
        metrics = await query_prometheus(
            prom_url,
            'orchestration_security_tenant_isolation_violations_total'
        )
        results = metrics.get("data", {}).get("result", [])
        if results and float(results[0]["value"][1]) > 0:
            break
        await asyncio.sleep(5)
    else:
        pytest.fail("Métrica de tenant isolation violation não incrementou")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_security_missing_authentication(orchestrator_client, sample_execution_ticket, port_forward_manager):
    """Testa enforcement de autenticação obrigatória."""
    prom_url = port_forward_manager["prometheus"]
    
    # Ticket sem JWT token
    ticket = {
        **sample_execution_ticket,
        "tenant_id": "tenant-123",
        "user_id": "user@example.com"
        # jwt_token ausente
    }
    
    response = await orchestrator_client.post("/api/v1/flow-c/execute", json=ticket)
    assert response.status_code in {400, 401, 403}
    
    error = response.json()
    assert "authentication" in str(error).lower() or "jwt" in str(error).lower()
    
    # Verificar métrica de falha de autenticação
    metrics = await query_prometheus(
        prom_url,
        'orchestration_security_authentication_failures_total'
    )
    results = metrics.get("data", {}).get("result", [])
    assert results, "Métrica de authentication failure não encontrada"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_security_insufficient_permissions(orchestrator_client, sample_execution_ticket, port_forward_manager):
    """Testa enforcement de autorização RBAC."""
    prom_url = port_forward_manager["prometheus"]
    
    # Ticket com capability que usuário não tem permissão
    ticket = {
        **sample_execution_ticket,
        "tenant_id": "tenant-123",
        "user_id": "viewer@example.com",  # Viewer não pode fazer deployment
        "jwt_token": "eyJhbGc.eyJzdWI.signature",
        "required_capabilities": ["deployment"]
    }
    
    response = await orchestrator_client.post("/api/v1/flow-c/execute", json=ticket)
    assert response.status_code in {400, 403}
    
    error = response.json()
    assert "permission" in str(error).lower() or "authorization" in str(error).lower()
    
    # Verificar métrica de authorization denial
    metrics = await query_prometheus(
        prom_url,
        'orchestration_security_authorization_denials_total{user_id="viewer@example.com"}'
    )
    results = metrics.get("data", {}).get("result", [])
    assert results, "Métrica de authorization denial não encontrada"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_security_pii_handling(orchestrator_client, sample_execution_ticket, port_forward_manager):
    """Testa enforcement de governança de dados (PII)."""
    prom_url = port_forward_manager["prometheus"]
    
    # Ticket com PII mas classificação incorreta
    ticket = {
        **sample_execution_ticket,
        "tenant_id": "tenant-123",
        "user_id": "user@example.com",
        "jwt_token": "eyJhbGc.eyJzdWI.signature",
        "contains_pii": True,
        "data_classification": "public"  # Deveria ser confidential
    }
    
    response = await orchestrator_client.post("/api/v1/flow-c/execute", json=ticket)
    assert response.status_code in {400, 403}
    
    error = response.json()
    assert "pii" in str(error).lower() or "data" in str(error).lower()
    
    # Verificar métrica de data governance violation
    metrics = await query_prometheus(
        prom_url,
        'orchestration_security_data_governance_violations_total'
    )
    results = metrics.get("data", {}).get("result", [])
    assert results, "Métrica de data governance violation não encontrada"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_security_rate_limiting(orchestrator_client, sample_execution_ticket, port_forward_manager):
    """Testa enforcement de rate limiting por tenant."""
    prom_url = port_forward_manager["prometheus"]
    
    # Simular múltiplas requisições para exceder rate limit
    ticket = {
        **sample_execution_ticket,
        "tenant_id": "tenant-rate-limited",
        "user_id": "user@example.com",
        "jwt_token": "eyJhbGc.eyJzdWI.signature"
    }
    
    # Enviar 150 requisições (limite é 100/min)
    responses = []
    for i in range(150):
        ticket_copy = {**ticket, "ticket_id": f"rate-test-{i}"}
        response = await orchestrator_client.post("/api/v1/flow-c/execute", json=ticket_copy)
        responses.append(response.status_code)
        await asyncio.sleep(0.01)  # 10ms entre requisições
    
    # Verificar que algumas foram rejeitadas por rate limit
    rejected = sum(1 for status in responses if status == 429)
    assert rejected > 0, "Nenhuma requisição foi rejeitada por rate limit"
    
    # Verificar métrica de rate limit exceeded
    metrics = await query_prometheus(
        prom_url,
        'orchestration_security_rate_limit_exceeded_total{tenant_id=\"tenant-rate-limited\"}'
    )
    results = metrics.get("data", {}).get("result", [])
    assert results, "Métrica de rate limit exceeded não encontrada"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_security_compliance_dashboard(port_forward_manager):
    """Testa que dashboard de compliance está acessível e funcional."""
    grafana_url = port_forward_manager.get("grafana")
    if not grafana_url:
        pytest.skip("Grafana não disponível")
    
    # Verificar que dashboard existe
    async with aiohttp.ClientSession() as session:
        # Buscar dashboard por tag
        async with session.get(
            f"{grafana_url}/api/search?tag=security",
            auth=aiohttp.BasicAuth("admin", "admin")
        ) as response:
            assert response.status == 200
            dashboards = await response.json()

            # Verificar que dashboard de security existe
            security_dashboard = next(
                (d for d in dashboards if "security" in d.get("title", "").lower()),
                None
            )
            assert security_dashboard is not None, "Dashboard de security não encontrado"
