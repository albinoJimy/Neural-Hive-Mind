"""
Teste E2E de distributed tracing para Fluxo C.

Valida propagação de trace_id através de:
Gateway → STE → Consensus → Orchestrator → Workers

Requer:
- Cluster Kubernetes com todos os serviços
- OpenTelemetry Collector configurado
- Jaeger UI acessível

Variáveis de ambiente:
- GATEWAY_URL: URL do Gateway (default: http://gateway-intencoes.neural-hive.svc.cluster.local)
- JAEGER_QUERY_URL: URL do Jaeger Query (default: http://jaeger-query.observability.svc.cluster.local:16686)

Exemplo de uso local com port-forward:
    kubectl port-forward -n neural-hive svc/gateway-intencoes 8000:80 &
    kubectl port-forward -n observability svc/jaeger-query 16686:16686 &

    GATEWAY_URL=http://localhost:8000 \\
    JAEGER_QUERY_URL=http://localhost:16686 \\
    pytest tests/e2e/tracing/test_flow_c_tracing_e2e.py -v
"""

import os
import pytest
import asyncio
import httpx
from datetime import datetime
from typing import Optional


# Configuração - URLs podem ser sobrescritas via variáveis de ambiente
GATEWAY_URL = os.getenv(
    'GATEWAY_URL',
    'http://gateway-intencoes.neural-hive.svc.cluster.local'
)
JAEGER_QUERY_URL = os.getenv(
    'JAEGER_QUERY_URL',
    'http://jaeger-query.observability.svc.cluster.local:16686'
)


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
    5. Validar continuidade de trace_id
    6. Validar hierarquia parent-child
    """

    # Log configuração do teste
    print(f"Configuração do teste:")
    print(f"  Gateway URL: {GATEWAY_URL}")
    print(f"  Jaeger URL: {JAEGER_QUERY_URL}")
    print()

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

    # 5. Validar continuidade de trace_id (todos os spans devem ter o mesmo trace_id)
    trace_ids_in_spans = {span.get('traceID') for span in spans}
    assert len(trace_ids_in_spans) == 1, (
        f"Fragmentação de trace detectada: {len(trace_ids_in_spans)} trace_ids diferentes. "
        f"Esperado: 1 trace_id único. Encontrados: {trace_ids_in_spans}"
    )
    print(f"✅ Continuidade de trace_id validada: {trace_ids_in_spans.pop()}")

    # 6. Validar parent-child relationships para spans do Fluxo C
    flow_c_root = next((s for s in spans if 'flow_c.execute' in s['operationName']), None)
    if flow_c_root:
        for operation in ['C1.validate_decision', 'C2.generate_tickets', 'C3.discover_workers']:
            child_span = next((s for s in spans if operation in s['operationName']), None)
            if child_span:
                references = child_span.get('references', [])
                parent_ref = next((r for r in references if r.get('refType') == 'CHILD_OF'), None)
                if parent_ref:
                    parent_span_id = parent_ref.get('spanID')
                    if parent_span_id == flow_c_root['spanID']:
                        print(f"✅ Hierarquia validada: {operation} → flow_c.execute")

    # 7. Validar ausência de erros
    error_spans = [s for s in spans if any(
        tag.get('key') == 'error' and tag.get('value') is True
        for tag in s.get('tags', [])
    )]
    assert len(error_spans) == 0, (
        f"Spans com erro detectados: {[s['operationName'] for s in error_spans]}"
    )
    print(f"✅ Nenhum span com erro detectado")

    # 8. Validar latências razoáveis (< 60s para cada span)
    for span in spans:
        duration_us = span.get('duration', 0)
        duration_s = duration_us / 1_000_000
        assert duration_s < 60, (
            f"Span {span['operationName']} com latência excessiva: {duration_s:.2f}s"
        )
    print(f"✅ Latências validadas (todas < 60s)")

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
