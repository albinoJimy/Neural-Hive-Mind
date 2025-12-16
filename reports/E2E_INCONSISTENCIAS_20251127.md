# Relatório de Inconsistências - Teste E2E Manual

**Data**: 2025-11-27
**Executor**: Claude Code
**Ambiente**: Local Kubernetes (kind)

---

## Resumo Executivo

| Severidade | Quantidade | Status |
|------------|------------|--------|
| 🔴 CRÍTICO | 1 | Bloqueante para Fluxo C |
| 🟠 ALTO | 2 | Corrigidos durante teste |
| 🟡 MÉDIO | 2 | Workaround disponível |
| 🟢 BAIXO | 3 | Aceitável para dev |

---

## 🔴 ISSUE #1 - CRÍTICO: correlation_id não propagado no Fluxo C

### Descrição
O `correlation_id` não é propagado do plano cognitivo para a decisão consolidada, causando falha de validação no Orchestrator Dynamic.

### Componentes Afetados
- `services/consensus-engine/src/services/consensus_orchestrator.py`
- `services/orchestrator-dynamic/src/integration/flow_c_consumer.py`

### Erro
```
1 validation error for FlowCContext
correlation_id
  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]
```

### Evidência
```json
// MongoDB - consensus_decisions
{
  "decision_id": "8874bdd9-85f5-45b2-86b4-32b3b32f54e2",
  "correlation_id": null,  // <-- PROBLEMA
  "trace_id": null,
  "span_id": null
}
```

### Impacto
- **Bloqueante**: Execution tickets NÃO são gerados
- Fluxo C incompleto - decisões não viram ações executáveis

### Causa Raiz
O Consensus Engine não extrai o `correlation_id` do plano original ao criar a decisão consolidada.

### Fix Recomendado
```python
# Em consensus_orchestrator.py - ao criar ConsolidatedDecision
decision = ConsolidatedDecision(
    decision_id=str(uuid.uuid4()),
    plan_id=plan['plan_id'],
    intent_id=plan['intent_id'],
    correlation_id=plan.get('correlation_id', ''),  # ADICIONAR
    trace_id=trace_context.get('trace_id', ''),
    span_id=trace_context.get('span_id', ''),
    # ... resto
)
```

### Prioridade
**P0** - Deve ser corrigido antes de qualquer teste de produção

---

## 🟠 ISSUE #2 - ALTO: Timeout gRPC insuficiente para Specialists

### Descrição
O timeout padrão de 5 segundos é insuficiente para os specialists que levam 6-8 segundos para processar.

### Componentes Afetados
- `services/consensus-engine/src/config/settings.py`
- `helm-charts/consensus-engine/values-local.yaml`
- `helm-charts/consensus-engine/templates/configmap.yaml`

### Erro
```
Timeout ao invocar especialista plan_id=... specialist_type=business timeout_ms=5000
RetryError[<Future at ... state=finished raised TimeoutError>]
Pareceres insuficientes: 0/5
```

### Impacto
- Consensus Engine não recebia nenhum parecer
- Fluxo falhava completamente

### Causa Raiz
1. ConfigMap define `SPECIALIST_GRPC_TIMEOUT_MS`
2. Código Settings espera `GRPC_TIMEOUT_MS` (Pydantic field: `grpc_timeout_ms`)
3. Variável de ambiente não era mapeada corretamente

### Fix Aplicado
```bash
# ConfigMap patch
kubectl patch configmap consensus-engine-config -n consensus-orchestration \
  --type merge -p '{"data":{"GRPC_TIMEOUT_MS":"15000"}}'
```

```yaml
# helm-charts/consensus-engine/values-local.yaml
specialists:
  grpcTimeoutMs: 15000  # Era 5000
```

### Fix Permanente Necessário
Atualizar `templates/configmap.yaml` para usar a variável correta:
```yaml
GRPC_TIMEOUT_MS: "{{ .Values.config.specialists.grpcTimeoutMs }}"
```

### Status
✅ Corrigido temporariamente via ConfigMap patch

---

## 🟠 ISSUE #3 - ALTO: Endpoints de Specialists incorretos

### Descrição
Os endpoints dos specialists no `values-local.yaml` apontavam para namespaces inexistentes.

### Componentes Afetados
- `helm-charts/consensus-engine/values-local.yaml`

### Configuração Incorreta
```yaml
specialists:
  businessEndpoint: specialist-business.specialist-business.svc.cluster.local:50051
  # Namespace 'specialist-business' não existe
```

### Configuração Correta
```yaml
specialists:
  businessEndpoint: specialist-business.semantic-translation.svc.cluster.local:50051
  # Specialists estão no namespace 'semantic-translation'
```

### Impacto
- gRPC channels falhavam ao conectar
- Timeout imediato (DNS resolution failure)

### Fix Aplicado
```yaml
# helm-charts/consensus-engine/values-local.yaml - CORRIGIDO
specialists:
  businessEndpoint: specialist-business.semantic-translation.svc.cluster.local:50051
  technicalEndpoint: specialist-technical.semantic-translation.svc.cluster.local:50051
  behaviorEndpoint: specialist-behavior.semantic-translation.svc.cluster.local:50051
  evolutionEndpoint: specialist-evolution.semantic-translation.svc.cluster.local:50051
  architectureEndpoint: specialist-architecture.semantic-translation.svc.cluster.local:50051
```

### Status
✅ Corrigido no values-local.yaml

---

## 🟡 ISSUE #4 - MÉDIO: Modelo ML com atributo incompatível

### Descrição
Os modelos ML treinados usam atributos não disponíveis na versão atual do sklearn.

### Componentes Afetados
- Todos os Specialists (business, technical, behavior, evolution, architecture)
- Modelos no MLflow

### Erro
```
AttributeError: 'DecisionTreeClassifier' object has no attribute 'monotonic_cst'
AttributeError: 'RandomForestClassifier' object has no attribute 'monotonic_cst'
```

### Impacto
- Inferência ML falha
- Sistema usa fallback heurístico (funciona, mas menos preciso)

### Causa Raiz
- Modelos treinados com sklearn >= 1.4 (que tem `monotonic_cst`)
- Ambiente de inferência usa sklearn < 1.4

### Workaround Atual
Fallback heurístico funciona corretamente - specialists retornam opiniões baseadas em regras.

### Fix Recomendado
1. Atualizar sklearn nos containers dos specialists para >= 1.4
2. OU retreinar modelos sem usar `monotonic_cst`

### Status
⚠️ Workaround ativo - não bloqueante

---

## 🟡 ISSUE #5 - MÉDIO: Consumer loop finaliza após erro

### Descrição
O Kafka consumer do Consensus Engine finaliza completamente após encontrar um erro de processamento.

### Componentes Afetados
- `services/consensus-engine/src/integration/plan_consumer.py`

### Evidência
```
2025-11-27 13:41:27 [error] Erro no loop de consumo error="Pareceres insuficientes: 0/5..."
2025-11-27 13:41:27 [info] Consumer loop finalizado
```

### Impacto
- Após um erro, novas mensagens não são processadas
- Requer restart manual do pod

### Causa Raiz
```python
async def consume_loop(self):
    try:
        async for msg in self.consumer:
            await self.process_message(msg)
    except Exception as e:
        logger.error("Erro no loop de consumo", error=str(e))
    finally:
        logger.info("Consumer loop finalizado")  # <-- Sai do loop
```

### Fix Recomendado
```python
async def consume_loop(self):
    while True:
        try:
            async for msg in self.consumer:
                try:
                    await self.process_message(msg)
                except Exception as e:
                    logger.error("Erro processando mensagem", error=str(e))
                    # Continua processando próximas mensagens
        except Exception as e:
            logger.error("Erro no consumer, reconectando...", error=str(e))
            await asyncio.sleep(5)
```

### Status
⚠️ Pendente correção

---

## 🟢 ISSUE #6 - BAIXO: Schema Registry não configurado

### Descrição
Schema Registry não está configurado, sistema usa JSON fallback.

### Warning
```
Schema Registry não configurado - usando JSON fallback
```

### Impacto
- Serialização Avro não disponível
- Sem validação de schema
- Performance levemente inferior

### Status
✅ Aceitável para ambiente local/dev

---

## 🟢 ISSUE #7 - BAIXO: Neo4j sem dados históricos

### Descrição
Neo4j não possui dados de intents históricos para consulta de similaridade.

### Warning
```
warn: property key does not exist. The property `domain` does not exist in database `neo4j`
warn: label does not exist. The label `Intent` does not exist in database `neo4j`
```

### Impacto
- Similar intents sempre retorna 0 resultados
- Context enrichment menos eficaz

### Status
✅ Esperado em ambiente novo

---

## 🟢 ISSUE #8 - BAIXO: OpenTelemetry desabilitado

### Descrição
OpenTelemetry está desabilitado em todos os serviços.

### Configuração
```yaml
openTelemetry:
  enabled: false
```

### Impacto
- Traces não aparecem no Jaeger
- Observabilidade distribuída limitada

### Status
✅ Configuração intencional para ambiente local

---

## Métricas do Teste

| Métrica | Valor |
|---------|-------|
| **Data/Hora** | 2025-11-27 13:27-13:43 UTC |
| **correlation_id** | test-e2e-20251127-142742 |
| **intent_id** | 8be4735c-491c-4b90-a749-1c9b338d5b6a |
| **plan_id** | 7f700715-dd84-4ca8-a76b-4d247c762cf0 |
| **decision_id** | 8874bdd9-85f5-45b2-86b4-32b3b32f54e2 |

### Latências

| Componente | Latência |
|------------|----------|
| Gateway | 587ms |
| STE | 896ms |
| Specialists (cada) | ~6100ms |
| Consensus total | ~7s |
| E2E (Gateway → Decision) | ~16s |

### Resultados

| Item | Resultado |
|------|-----------|
| Fluxo A (Gateway → Kafka) | ✅ OK |
| Fluxo B (STE → Specialists) | ✅ OK |
| Fluxo C (Consensus → Orchestrator) | ⚠️ Parcial |
| Specialists responderam | 5/5 ✅ |
| Decisão gerada | review_required ✅ |
| Execution tickets | 0 ❌ |

---

## Ações Recomendadas

### Imediatas (P0)
1. [ ] Corrigir propagação de `correlation_id` no Consensus Engine

### Curto Prazo (P1)
2. [ ] Atualizar template Helm para usar `GRPC_TIMEOUT_MS`
3. [ ] Implementar retry no consumer loop do Consensus Engine

### Médio Prazo (P2)
4. [ ] Atualizar sklearn ou retreinar modelos ML
5. [ ] Popular Neo4j com dados históricos de teste
6. [ ] Configurar OpenTelemetry para ambiente de staging

---

*Relatório gerado automaticamente durante teste E2E manual*
