# TICKET 1.6 - Deploy e Monitoramento em Staging

**Status:** ⏳ PRONTO PARA EXECUÇÃO
**Data:** 2026-04-27
**Responsável:** Claude Code

---

## Checklist de Deploy

### Fase 1: Preparação

- [ ] Verificar que todos os testes passam: `pytest services/orchestrator-dynamic/tests/`
- [ ] Verificar que approval-service tem `USE_PROFESSIONAL_FEATURES=false` (default)
- [ ] Verificar que orchestrator-dynamic tem flags ML configuradas

### Fase 2: Deploy com Feature Flags OFF

```bash
# Deploy approval-service
kubectl apply -f k8s/approval-service-deployment.yaml

# Deploy orchestrator-dynamic
kubectl apply -f k8s/orchestrator-dynamic-deployment.yaml

# Verificar status
kubectl rollout status deployment/approval-service -n approval
kubectl rollout status deployment/orchestrator-dynamic -n neural-hive-orchestration

# Verificar pods
kubectl get pods -n approval
kubectl get pods -n neural-hive-orchestration
```

### Fase 3: Coletar Baseline (24h)

**Métricas para coletar:**
- Taxa de aprovação (approve/reject ratio)
- Latência P95 de predição
- Error rate (< 1%)
- CPU/memory usage
- Drift score baseline

**Grafana Dashboards:**
- ML Model Health: `http://grafana.neural-hive.local/d/ml_model_health`
- Data Drift: `http://grafana.neural-hive.local/d/ml_data_drift`

### Fase 4: Ativar Feature Flags

```bash
# Ativar feature extraction profissional
kubectl patch configmap approval-service-config -n approval --type=json \
  -p='[{"op": "replace", "path": "/data/USE_PROFESSIONAL_FEATURES", "value": "true"}]'

# Ativar auto-retrain (opcional, requer validação prévia)
kubectl patch configmap orchestrator-dynamic-config -n neural-hive-orchestration --type=json \
  -p='[{"op": "replace", "path": "/data/ML_AUTO_RETRAIN_ENABLED", "value": "true"}]'

# Restart pods para aplicar mudanças
kubectl rollout restart deployment/approval-service -n approval
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration

# Verificar logs
kubectl logs -n approval -l app=approval-service --tail=100 | grep -i "professional.*features"
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=100 | grep -i "auto.*retrain"
```

### Fase 5: Monitorar (24-48h)

**Verificar:**
- [ ] Taxa de aprovação estável (variação < 5%)
- [ ] Latência P95 < 1.2x do baseline
- [ ] Error rate < 1%
- [ ] Drift score não aumentou
- [ ] Sem crashes ou restarts

**Comandos de monitoramento:**
```bash
# Taxa de aprovação
kubectl exec -n approval -c approval-service -- curl -s localhost:8004/metrics | grep approval_service_approvals_total

# Latência
kubectl exec -n approval -c approval-service -- curl -s localhost:8004/metrics | grep approval_service_prediction_duration_seconds

# Drift
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=100 | grep drift
```

### Fase 6: Comparação e Decisão

| Métrica | Baseline | Profissional | Diff | Status |
|---------|----------|--------------|------|--------|
| Taxa Aprovação | __% | __% | __% | ✅/❌ |
| Latência P95 | __ms | __ms | __% | ✅/❌ |
| Error Rate | __% | __% | __% | ✅/❌ |
| Drift Score | __ | __ | __ | ✅/❌ |

**Decisão:**
- Se ✅ > 3: manter `USE_PROFESSIONAL_FEATURES=true`
- Se ❌ > 2: rollback e investigar

### Fase 7: Rollback (se necessário)

```bash
# Desativar feature flags
kubectl patch configmap approval-service-config -n approval --type=json \
  -p='[{"op": "replace", "path": "/data/USE_PROFESSIONAL_FEATURES", "value": "false"}]'

# Restart
kubectl rollout restart deployment/approval-service -n approval
```

---

## Dashboards Grafana

| Dashboard | URL | Propósito |
|-----------|-----|-----------|
| ML Model Health | `/d/ml_model_health` | Accuracy, latência, predições |
| Data Drift | `/d/ml_data_drift` | PSI, MAE ratio, K-S test |
| Training Pipeline | `/d/ml_training_pipeline` | Retrains, promoções, duration |

---

## Alertas Prometheus

| Alerta | Severidade | Condição |
|--------|------------|----------|
| MLDriftCritical | critical | drift_status == 2 por 10min |
| MLDriftWarning | warning | drift_status == 1 por 30min |
| MLModelLowF1Score | warning | F1 < 0.72 por 30min |
| AutoRetrainFailed | warning | failure_count > 0 em 1h |

---

## Logs Úteis

```bash
# Approval service
kubectl logs -n approval -l app=approval-service --tail=500 -f

# Orchestrator com drift
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=500 -f | grep -i drift

# Auto-retrain
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=500 -f | grep -i retrain
```

---

## Troubleshooting

### Problema: Alta latência após ativar features profissionais

**Verificar:**
```bash
# Comparar latência antes/depois
curl -s http://approval-service:8004/metrics | grep prediction_duration_seconds
```

**Solução:** Se > 1.2x, investigar NLPFeatureExtractor

### Problema: Taxa de aprovação caiu drasticamente

**Verificar:**
```bash
# Comparar features
kubectl logs -n approval -l app=approval-service --tail=100 | grep "nlp_features"
```

**Solução:** Rollback e validar FeatureAdapter

### Problema: Drift detectado constantemente

**Verificar:**
```bash
# Drift score
curl -s http://orchestrator-dynamic:8003/metrics | grep drift_score
```

**Solução:** Verificar se reference data está atualizado

---

## Critérios de Sucesso

- [ ] Deploy executado sem erros
- [ ] Baseline coletado (24h)
- [ ] Feature flags ativadas
- [ ] Métricas comparadas
- [ ] Variação < 5% em todas as métricas
- [ ] Sem incidentes em 48h

---

## Pós-Deploy

Se sucesso:
1. Manter `USE_PROFESSIONAL_FEATURES=true`
2. Ativar `ML_AUTO_RETRAIN_ENABLED=true` (opcional)
3. Remover código legado (regex manuais) em PR futuro
4. Documentar lessons learned

Se falha:
1. Rollback imediato
2. Investigar causa raiz
3. Corrigir e repetir teste

---

**TICKET 1.6 - PRONTO PARA EXECUÇÃO** ⏳
