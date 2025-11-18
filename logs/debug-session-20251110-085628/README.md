# Sessão de Captura de Logs gRPC - TypeError Analysis

**Session ID**: debug-session-20251110-085628
**Data/Hora Início**: 2025-11-10 08:56:28
**Duração Configurada**: 600s (10 minutos)
**Namespace Specialists**: neural-hive
**Namespace Consensus**: neural-hive


---

## Arquivos de Log Capturados

| Componente | Arquivo | Padrões Filtrados |
|------------|---------|-------------------|
| consensus-engine | consensus-engine-<pod-name>-debug.log (um arquivo por pod) | EvaluatePlan, TypeError, evaluated_at, gRPC channel, Invocando especialistas |
| specialist-business | specialist-business-debug.log | EvaluatePlan, evaluated_at, processing_time_ms, Received EvaluatePlan, completed successfully |
| specialist-technical | specialist-technical-debug.log | EvaluatePlan, evaluated_at, processing_time_ms, Received EvaluatePlan, completed successfully |
| specialist-behavior | specialist-behavior-debug.log | EvaluatePlan, evaluated_at, processing_time_ms, Received EvaluatePlan, completed successfully |
| specialist-evolution | specialist-evolution-debug.log | EvaluatePlan, evaluated_at, processing_time_ms, Received EvaluatePlan, completed successfully |
| specialist-architecture | specialist-architecture-debug.log | EvaluatePlan, evaluated_at, processing_time_ms, Received EvaluatePlan, completed successfully |

---

## Comandos kubectl Utilizados

### Consensus Engine
```bash
# Captura de cada pod individualmente
for pod in $(kubectl get pods -n neural-hive -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[*].metadata.name}'); do
  kubectl logs -f $pod -n neural-hive --tail=100 | \
    grep -E 'EvaluatePlan|TypeError|evaluated_at|gRPC channel|Invocando especialistas'
done
```

### Specialists
```bash
for specialist in business technical behavior evolution architecture; do
  kubectl logs -f deployment/specialist-$specialist -n neural-hive --tail=100 | \
    grep -E 'EvaluatePlan|evaluated_at|processing_time_ms|Received EvaluatePlan|completed successfully'
done
```

---

## Status da Captura

- **Status**: Em andamento
- **Início**: 2025-11-10 08:56:28
- **Término Previsto**: 2025-11-10 09:06:28

---

## Próximos Passos

1. Aguardar término da captura (600s)
2. Analisar logs capturados neste diretório
3. Preencher análise em `ANALISE_DEBUG_GRPC_TYPEERROR.md`
4. Correlacionar logs por plan_id/trace_id
5. Identificar causa raiz do TypeError

---

## Observações

- Todos os pods devem estar com LOG_LEVEL=DEBUG
- Filtros regex aplicados para reduzir ruído
- Logs capturados em tempo real via `kubectl logs -f`
- Sessão pode ser interrompida com Ctrl+C (será tratado gracefully)

