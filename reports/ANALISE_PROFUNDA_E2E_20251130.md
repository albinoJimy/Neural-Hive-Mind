# Análise Profunda - Issues E2E
**Data:** 2025-11-30
**Ambiente:** Kubernetes (Neural-Hive-Mind)

---

## Resumo Executivo

| Issue | Severidade | Root Cause | Fix Required |
|-------|------------|------------|--------------|
| #1 Timeout Business Specialist | **MÉDIA** | Processamento leva 49-66s (timeout: 15s) | Config ou otimização |
| #2 Falha conexão Temporal | **CRÍTICA** | Endpoint REST `/api/v1/workflows/start` não existe | Implementar endpoint |
| #3 correlation_id null | **MÉDIA** | Mismatch camelCase vs snake_case no JSON | Fix deserialização |
| #4 OpenTelemetry desabilitado | **BAIXA** | Comentado no código | Descomentar config |

---

## Issue #1: Timeout do Specialist-Business (MÉDIA)

### Evidências
```log
2025-11-30 08:48:46 [info] Plan evaluation completed successfully
  processing_time_ms=66104 (66 segundos!)
  confidence_score=0.6613
  recommendation=approve
  specialist_type=business
```

### Root Cause
- O specialist-business leva **49-66 segundos** para avaliar um plano
- O timeout configurado no Consensus Engine é **15 segundos** (`GRPC_TIMEOUT_MS=15000`)
- Resultado: Timeout gRPC → retries → latência alta no fluxo B

### Análise Técnica
1. **Conectividade TCP**: OK (testada com socket)
2. **Health checks**: OK (`status=SERVING`, `model_loaded=True`)
3. **Endpoints**: OK (2 pods ativos no service)
4. **Problema real**: Tempo de inferência do modelo ML muito alto

### Correções Propostas
**Opção A (Rápida):** Aumentar timeout gRPC
```yaml
# helm-charts/consensus-engine/values.yaml
env:
  GRPC_TIMEOUT_MS: "120000"  # 2 minutos
  SPECIALIST_GRPC_TIMEOUT_MS: "120000"
```

**Opção B (Melhor):** Otimizar modelo do specialist
- Verificar se modelo está em GPU
- Implementar cache de features
- Reduzir complexidade do modelo

---

## Issue #2: Falha Conexão Temporal (CRÍTICA)

### Evidências
```log
2025-11-30 08:47:24 [info] starting_workflow correlation_id=6149c720-ecec-4506-8774-52d995c9c577
2025-11-30 08:47:26 [info] starting_workflow (retry 2)
2025-11-30 08:47:28 [info] starting_workflow (retry 3)
2025-11-30 08:47:28 [error] flow_c_failed error='RetryError[ConnectError]'
```

### Root Cause
O **OrchestratorClient** faz chamadas HTTP para:
```
POST http://orchestrator-dynamic.neural-hive-orchestration:8000/api/v1/workflows/start
```

Mas este **endpoint NÃO EXISTE** no `main.py` do orchestrator-dynamic!

### Análise do Código

**OrchestratorClient** (`libraries/neural_hive_integration/.../orchestrator_client.py:87-88`):
```python
response = await self.client.post(
    f"{self.base_url}/api/v1/workflows/start",  # <- ENDPOINT INEXISTENTE
    json=request.model_dump(),
)
```

**Endpoints existentes no main.py**:
- `/health` ✓
- `/ready` ✓
- `/api/v1/tickets/{ticket_id}` (501 Not Implemented)
- `/api/v1/flow-c/status` ✓
- `/api/v1/ml/*` ✓
- `/api/v1/workflows/{workflow_id}` (501 Not Implemented)
- **`/api/v1/workflows/start`** ← **NÃO EXISTE!**

### Problemas Adicionais
1. **URL base incorreta**: Client usa `neural-hive-orchestration`, mas namespace é `consensus-orchestration`
2. **Temporal Worker**: Pode não estar registrado corretamente

### Correção Proposta

Implementar endpoint em `services/orchestrator-dynamic/src/main.py`:

```python
from pydantic import BaseModel
from typing import Dict, Any

class WorkflowStartRequest(BaseModel):
    cognitive_plan: Dict[str, Any]
    correlation_id: str
    priority: int = 5
    sla_deadline_seconds: int = 14400

@app.post('/api/v1/workflows/start')
async def start_workflow(request: WorkflowStartRequest):
    """Start Temporal workflow para execução do plano cognitivo."""
    if not app_state.temporal_client:
        raise HTTPException(status_code=503, detail="Temporal não disponível")

    workflow_id = f"flow-c-{request.correlation_id}"

    try:
        # Usar Temporal client diretamente
        handle = await app_state.temporal_client.start_workflow(
            "OrchestrationWorkflow",
            {
                'cognitive_plan': request.cognitive_plan,
                'correlation_id': request.correlation_id,
                'priority': request.priority
            },
            id=workflow_id,
            task_queue=get_settings().temporal_task_queue
        )

        return {
            'workflow_id': workflow_id,
            'status': 'started',
            'correlation_id': request.correlation_id
        }
    except Exception as e:
        logger.error('workflow_start_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Issue #3: correlation_id Não Propagado (MÉDIA)

### Evidências
```json
// MongoDB cognitive_ledger
{
  "plan_id": "0bb472a4-a1de-4993-ba84-a659c35c590e",
  "plan_data": {
    "correlation_id": null,  // <- DEVERIA TER VALOR!
    "trace_id": null,
    "span_id": null
  }
}
```

### Root Cause

**Mismatch de nomenclatura entre camelCase e snake_case:**

1. **Gateway** serializa com camelCase (`to_avro_dict()`):
```python
avro_data = {
    "correlationId": self.correlation_id,  # <- camelCase
}
```

2. **STE** busca com snake_case:
```python
correlation_id = intent_envelope.get('correlation_id')  # <- snake_case
```

3. **Headers Kafka** usam kebab-case:
```python
headers = {
    'correlation-id': (intent_envelope.correlation_id or '').encode('utf-8'),
}
```

### Fluxo do correlation_id

| Componente | Envio | Recebimento | Status |
|------------|-------|-------------|--------|
| Gateway → Kafka | Headers: `correlation-id` ✓ | - | OK |
| Gateway → Kafka | Payload: `correlationId` ✓ | - | OK |
| Kafka → STE | - | Headers: `correlation-id` ✓ | OK |
| Kafka → STE | - | Payload: busca `correlation_id` ❌ | **PROBLEMA** |

### Correção Proposta

**Opção A:** Corrigir STE para buscar `correlationId` (camelCase)
```python
# services/semantic-translation-engine/src/services/orchestrator.py
correlation_id = (
    trace_context.get('correlation_id') or
    intent_envelope.get('correlationId') or  # <- Adicionar camelCase
    intent_envelope.get('correlation_id')
)
```

**Opção B:** Padronizar Gateway para usar snake_case
```python
# services/gateway-intencoes/src/models/intent_envelope.py
def to_avro_dict(self):
    return {
        "correlation_id": self.correlation_id,  # <- snake_case
    }
```

**Recomendação:** Opção A (menor impacto, retrocompatível)

---

## Issue #4: OpenTelemetry Desabilitado (BAIXA)

### Evidências
```python
# services/gateway-intencoes/src/main.py:213-226
# Initialize tracing with OTLP exporter
# init_tracing(observability_config)  <- COMENTADO!

# Initialize full observability stack
# init_observability(...)  <- COMENTADO!

logger.info("Observabilidade desabilitada para dev local")
```

### Root Cause
- Código de inicialização do OpenTelemetry está **comentado**
- Jaeger mostra apenas `jaeger-all-in-one` como serviço

### Correção Proposta

1. Descomentar e habilitar via variável de ambiente:
```python
# services/gateway-intencoes/src/main.py
if settings.otel_enabled:
    init_tracing(observability_config)
```

2. Configurar nos values:
```yaml
# helm-charts/gateway-intencoes/values.yaml
env:
  OTEL_ENABLED: "true"
  OTEL_ENDPOINT: "http://neural-hive-jaeger-collector:4318"
```

---

## Priorização de Correções

| Prioridade | Issue | Impacto | Esforço |
|------------|-------|---------|---------|
| **P0** | #2 Temporal endpoint | Fluxo C não funciona | Médio |
| **P1** | #1 Timeout specialist | Latência alta no Fluxo B | Baixo |
| **P2** | #3 correlation_id | Perda de rastreabilidade | Baixo |
| **P3** | #4 OpenTelemetry | Sem traces distribuídos | Baixo |

---

## Próximos Passos

1. [ ] Implementar endpoint `/api/v1/workflows/start` no orchestrator
2. [ ] Aumentar timeout gRPC para specialists (120s)
3. [ ] Corrigir deserialização do correlation_id no STE
4. [ ] Habilitar OpenTelemetry (opcional para produção)
5. [ ] Revalidar fluxo E2E completo

---

**Análise realizada por:** Claude Code
**Duração da análise:** ~30 minutos
