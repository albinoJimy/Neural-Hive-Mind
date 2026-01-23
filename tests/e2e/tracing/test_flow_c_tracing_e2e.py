"""
Teste E2E de distributed tracing para Fluxo C.

Valida propagação de trace_id através de:
Gateway → STE → Consensus → Orchestrator → Workers

Requer:
- Cluster Kubernetes com todos os serviços
- OpenTelemetry Collector configurado
- Jaeger UI acessível
"""

import pytest
import asyncio
import httpx
from datetime import datetime
from typing import Optional


# Configuração - URLs podem ser sobrescritas via variáveis de ambiente
GATEWAY_URL = "http://gateway-intencoes.neural-hive.svc.cluster.local"
JAEGER_QUERY_URL = "http://jaeger-query.observability.svc.cluster.local:16686"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_flow_c_trace_propagation():
    """
    Testa propagação de trace através do Fluxo C completo.

    Passos:
    1. Enviar intenção via Gateway
    2. Aguardar processamento (STE → Consensus → Orchestrator)
    3. Consultar Jaeger para validar trace completo
    4. Validar spans esperados: C1-C6
    """

    # 1. Enviar intenção de teste
    intent_payload = {
        "text": "Deploy microservice user-api to production",
        "domain": "technical",
        "priority": "high",
        "metadata": {
            "test_type": "e2e_tracing",
            "timestamp": datetime.utcnow().isoformat()
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{GATEWAY_URL}/intentions",
            json=intent_payload,
            timeout=30.0
        )

        assert response.status_code == 200
        result = response.json()
        intent_id = result["intent_id"]
        correlation_id = result.get("correlation_id")

        print(f"✅ Intent enviado: {intent_id}")
        print(f"   Correlation ID: {correlation_id}")

    # 2. Aguardar processamento (Fluxo C leva ~10-30s)
    await asyncio.sleep(35)

    # 3. Consultar Jaeger para trace
    trace_id = await _find_trace_by_intent_id(intent_id)

    assert trace_id is not None, f"Trace não encontrado para intent_id={intent_id}"
    print(f"✅ Trace encontrado: {trace_id}")

    # 4. Validar spans do Fluxo C
    spans = await _get_trace_spans(trace_id)

    expected_services = [
        "gateway-intencoes",
        "semantic-translation-engine",
        "consensus-engine",
        "orchestrator-dynamic"
    ]

    found_services = {span["process"]["serviceName"] for span in spans}

    for service in expected_services:
        assert service in found_services, f"Service {service} não encontrado no trace"
        print(f"✅ Service encontrado: {service}")

    # Validar spans específicos do Fluxo C
    expected_operations = [
        "flow_c.execute",           # FlowCOrchestrator
        "C1.validate_decision",     # Validação
        "C2.generate_tickets",      # Geração de tickets
        "C3.discover_workers",      # Descoberta de workers
        "C4.assign_tickets",        # Atribuição
        "C5.monitor_execution",     # Monitoramento
        "C6.publish_telemetry"      # Telemetria
    ]

    found_operations = {span["operationName"] for span in spans}

    for operation in expected_operations:
        # Verificar se operação existe (pode ter prefixo do serviço)
        matching = [op for op in found_operations if operation in op]
        assert len(matching) > 0, f"Operation {operation} não encontrada no trace"
        print(f"✅ Operation encontrada: {operation}")

    # Validar atributos customizados
    flow_c_spans = [s for s in spans if "flow_c" in s["operationName"].lower()]
    assert len(flow_c_spans) > 0, "Nenhum span do Flow C encontrado"

    for span in flow_c_spans:
        tags = {tag["key"]: tag["value"] for tag in span.get("tags", [])}

        # Validar atributos obrigatórios
        assert "neural.hive.intent.id" in tags or "intent.id" in tags
        assert "neural.hive.component" in tags or "component" in tags

        print(f"✅ Span validado: {span['operationName']}")

    print(f"\n🎉 Teste E2E de tracing concluído com sucesso!")
    print(f"   Trace ID: {trace_id}")
    print(f"   Intent ID: {intent_id}")
    print(f"   Services: {len(found_services)}")
    print(f"   Spans: {len(spans)}")


async def _find_trace_by_intent_id(intent_id: str) -> Optional[str]:
    """Busca trace no Jaeger por intent_id."""
    async with httpx.AsyncClient() as client:
        # Buscar traces dos últimos 5 minutos
        lookback = "5m"

        # Query por tag neural.hive.intent.id
        params = {
            "service": "gateway-intencoes",
            "lookback": lookback,
            "tags": f'{{"neural.hive.intent.id":"{intent_id}"}}'
        }

        response = await client.get(
            f"{JAEGER_QUERY_URL}/api/traces",
            params=params,
            timeout=10.0
        )

        if response.status_code != 200:
            return None

        data = response.json()
        traces = data.get("data", [])

        if not traces:
            return None

        # Retornar primeiro trace encontrado
        return traces[0]["traceID"]


async def _get_trace_spans(trace_id: str) -> list:
    """Obtém todos os spans de um trace."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{JAEGER_QUERY_URL}/api/traces/{trace_id}",
            timeout=10.0
        )

        if response.status_code != 200:
            return []

        data = response.json()
        traces = data.get("data", [])

        if not traces:
            return []

        # Retornar spans do primeiro trace
        return traces[0].get("spans", [])


@pytest.mark.e2e
@pytest.mark.skip(reason="Requer Jaeger UI para validação manual")
def test_flow_c_tracing_manual_validation():
    """
    Teste manual para validação visual no Jaeger UI.

    Passos:
    1. Executar teste anterior para gerar trace
    2. Abrir Jaeger UI: http://jaeger-query.observability.svc.cluster.local:16686
    3. Buscar por service: gateway-intencoes
    4. Filtrar por tag: neural.hive.intent.id
    5. Validar visualmente:
       - Todos os serviços aparecem no trace
       - Spans C1-C6 estão presentes
       - Latências são razoáveis
       - Não há erros
    """
    pass
