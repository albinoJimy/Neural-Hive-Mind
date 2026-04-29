# Deploy Staging FASE 0 IA/ML Integration - Status Final

> **Data:** 2026-04-28
> **Status:** ✅ CONCLUÍDO (Parcial)
> **Serviços principais:** approval-service, orchestrator-dynamic

---

## Resumo Executivo

Deploy staging executado com sucesso para os serviços principais. Flags ML do FASE 0 foram ativadas nos deployments existentes no namespace `neural-hive`.

---

## Serviços Deployados

### approval-service
- **Replicas:** 2/2 READY ✅
- **Imagem:** ghcr.io/albinojimy/neural-hive-mind/approval-service:05ca2b2
- **Namespace:** neural-hive

**Flags ML Ativadas:**
```yaml
ML_AUTO_RETRAIN_ENABLED: true
MODEL_PROMOTION_ENABLED: true
ENABLE_ML_DRIFT_DETECTION: true
ENABLE_ML_PREDICTION: true
```

### orchestrator-dynamic
- **Replicas:** 3/3 READY ✅
- **Imagem:** ghcr.io/albinojimy/neural-hive-mind/orchestrator-dynamic:5c110b3
- **Namespace:** neural-hive

**Flags ML Ativadas (ConfigMap):**
```yaml
ML_AUTO_RETRAIN_ENABLED: true
MODEL_PROMOTION_ENABLED: true
FEEDBACK_REPLAY_ENABLED: true
ML_DRIFT_DETECTION_ENABLED: true
ML_DRIFT_BASELINE_ENABLED: true
ML_PREDICTIONS_ENABLED: true
ENABLE_ML_ENHANCED_SCHEDULING: true
```

---

## Correções Aplicadas

### 1. Gatekeeper Labels Fix
Deployments sem label `app` no pod template foram corrigidos:
- ✅ approval-service
- ✅ specialist-behavior
- ✅ specialist-evolution
- ✅ guard-agents
- ✅ scout-agents
- ✅ semantic-translation-engine
- ✅ opa
- ✅ memory-layer-api-sync-consumer

### 2. NetworkPolicy e Conectividade
- ✅ MongoDB acessível de neural-hive
- ✅ Kafka topics validados
- ✅ approval-service consumer/producer funcionando

---

## Cluster Status

**CPU Limitada** - vários pods Pending por falta de recursos:
- consensus-engine: 0/2 (specialists health check issue + CPU)
- guard-agents: 0/2 (CPU insufficient)
- scout-agents: 0/2 (CPU insufficient)
- semantic-translation-engine: 0/2 (CPU insufficient)
- specialist-behavior: 0/2 (CPU insufficient)
- specialist-evolution: 0/2 (CPU insufficient)

**Nodes:**
- vmi2092350: 76% CPU
- vmi2911680: 24% CPU
- vmi2911681: 18% CPU
- vmi3002938: 21% CPU
- vmi3075398: 39% CPU

---

## Próximos Passos

### Opcionais (Recomendado)
1. **Aumentar capacidade do cluster** - adicionar nodes ou CPU
2. **Escalar deployments não-críticos** - reduzir replicas para 0 quando não necessário
3. **Resolver consensus-engine readiness** - specialists health check está retornando false

### Monitoramento
- Verificar métricas ML nos próximos dias
- Confirmar que drift detection está funcionando
- Validar model promotion quando houver novos modelos

---

## Comandos Úteis

```bash
# Ver status dos serviços principais
kubectl get pods -n neural-hive -l app=approval-service
kubectl get pods -n neural-hive -l app.kubernetes.io/name=orchestrator-dynamic

# Ver logs de ML
kubectl logs -n neural-hive approval-service-<pod> | grep -i "ml\|model\|drift"
kubectl logs -n neural-hive orchestrator-dynamic-<pod> | grep -i "ml\|model\|drift"

# Verificar flags ML
kubectl get deployment approval-service -n neural-hive -o yaml | grep -E "ML_|MODEL_"
kubectl get configmap orchestrator-dynamic-config -n neural-hive -o yaml | grep -E "ML_|MODEL_|FEEDBACK"
```

---

## Conclusão

Deploy staging parcial concluído. Serviços principais (approval-service, orchestrator-dynamic) estão rodando com flags ML ativas. Cluster com CPU limitada impede full deploy.
