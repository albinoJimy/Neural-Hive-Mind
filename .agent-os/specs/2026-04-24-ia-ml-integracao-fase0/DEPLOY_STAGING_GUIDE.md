# Deploy Staging - FASE 0 IA/ML Integration

**Data:** 2026-04-27
**Status:** PRONTO PARA DEPLOY (v1.2)
**Feature Flags:** `USE_PROFESSIONAL_FEATURES=false` (rollback-safe)
**Componentes Implementados:** Feature Extraction, Drift Detection, Model Promotion, Auto-Retrain Integration

---

## Resumo da Implementação

### Componentes Modificados (TICKETS 100% COMPLETOS)

| Serviço | Modificação | Feature Flag | Ticket |
|---------|-------------|--------------|--------|
| `approval-service` | Feature Adapter integrado | `USE_PROFESSIONAL_FEATURES` | TICKET 3.3 ✅ |
| `orchestrator-dynamic` | Drift Detector integrado | `ML_DRIFT_CHECK_ENABLED` | TICKET 3.2 ✅ |
| `orchestrator-dynamic` | Drift-Retrain Connector | `ML_RETRAINING_TRIGGERS_ENABLED` | TICKET 3.2 ✅ |
| `ml_pipelines/deployment` | Model Promotion Pipeline | `MODEL_PROMOTION_ENABLED` | TICKET 3.4 ✅ |
| `ml_pipelines/training` | Reference Data Generator | N/A | TICKET 2.3 ✅ |

### Arquivos Atualizados

- `k8s/approval-service-deployment.yaml` - Feature flags adicionadas (v1.2)
- `k8s/orchestrator-dynamic-deployment.yaml` - Configurações drift detection + auto-retrain (v1.2)
- `ml_pipelines/deployment/model_promotion.py` - Pipeline de promoção de modelos
- `ml_pipelines/training/create_reference_data.py` - Gerador de baseline sintético
- `ml_models/approval_v7_reference.pkl` - Baseline de features para drift detection

### Testes Implementados

- **Model Promotion**: 17/17 testes passando
- **Drift-Retrain Integration**: 19/19 testes passando
- **Reference Data**: 16/16 testes passando
- **Total FASE 0**: 52+ testes automatizados

---

## Plano de Deploy Staging

### Script de Deploy Automatizado

Use o script `deploy-staging.sh` para deploy automatizado:

```bash
# Deploy completo (Fase 1 + Fase 2)
./.agent-os/specs/2026-04-24-ia-ml-integracao-fase0/deploy-staging.sh --full

# Apenas Fase 1 (feature flags OFF)
./.agent-os/specs/2026-04-24-ia-ml-integracao-fase0/deploy-staging.sh --phase-1

# Apenas Fase 2 (ativar feature flags)
./.agent-os/specs/2026-04-24-ia-ml-integracao-fase0/deploy-staging.sh --phase-2

# Rollback imediato
./.agent-os/specs/2026-04-24-ia-ml-integracao-fase0/deploy-staging.sh --rollback
```

### Fase 1: Deploy com Feature Flag OFF (Dia 1)

**Objetivo:** Validar que as mudanças não quebram o funcionamento existente.

```bash
# 1. Build das imagens com as novas mudanças
docker build -t neural-hive-mind/approval-service:v1.1.0-ml-phase0 -f services/approval-service/Dockerfile .
docker build -t neural-hive-mind/orchestrator-dynamic:v1.1.0-ml-phase0 -f services/orchestrator-dynamic/Dockerfile .

# 2. Push para registry
docker push neural-hive-mind/approval-service:v1.1.0-ml-phase0
docker push neural-hive-mind/orchestrator-dynamic:v1.1.0-ml-phase0

# 3. Deploy no staging (feature flag OFF por padrão)
kubectl apply -f k8s/approval-service-deployment.yaml
kubectl apply -f k8s/orchestrator-dynamic-deployment.yaml

# 4. Verificar deploy
kubectl rollout status deployment/approval-service -n approval
kubectl rollout status deployment/orchestrator-dynamic -n orchestrator-dynamic

# 5. Verificar logs
kubectl logs -f deployment/approval-service -n approval --tail=100
kubectl logs -f deployment/orchestrator-dynamic -n orchestrator-dynamic --tail=100
```

**Métricas a Monitorar (24h):**
- Taxa de aprovação (approve/reject ratio)
- Latência de predição (P95 < 100ms)
- Error rate (< 1%)
- CPU/memory usage

### Fase 2: Ativar Feature Flag (Dia 2)

**Objetivo:** Testar feature extraction profissional com A/B testing.

```bash
# Ativar USE_PROFESSIONAL_FEATURES (patch temporário)
kubectl patch configmap approval-service-config -n approval --type=json \
  -p='[{"op": "replace", "path": "/data/USE_PROFESSIONAL_FEATURES", "value": "true"}]'

# Restart pods para aplicar a mudança
kubectl rollout restart deployment/approval-service -n approval

# Verificar que os pods estão rodando com a nova config
kubectl describe deployment/approval-service -n approval
```

**Métricas Comparativas (24h):**
| Métrica | Legado | Profissional | Delta |
|---------|--------|--------------|-------|
| Approve Rate | baseline | novo | diff |
| Latência P95 | baseline | novo | diff |
| CPU Usage | baseline | novo | diff |

### Fase 3: Análise e Decisão (Dia 3)

**Critérios de Sucesso:**
1. ✅ Sem erros de predição
2. ✅ Latência ≤ 1.2x do legado (já validado: 0.82x)
3. ✅ Taxa de aprovação similar (±5%)
4. ✅ Sem regressões de negócio

**Se Sucesso:**
- Manter `USE_PROFESSIONAL_FEATURES=true`
- Planejar remoção do código legado (regex manuais)

**Se Falha:**
- Rollback imediato: `USE_PROFESSIONAL_FEATURES=false`
- Investigar logs e métricas
- Corrigir e retestar

---

## Monitoramento

### Dashboard Grafana (A Criar - EPIC 4)

Enquanto o dashboard não está criado, usar queries Prometheus:

```promql
# Taxa de aprovação
sum(rate(approval_decision_total{decision="approve"}[5m])) /
sum(rate(approval_decision_total[5m]))

# Latência P95
histogram_quantile(0.95, sum(rate(approval_prediction_latency_seconds_bucket[5m])) by (le))

# Drift detectado
ml_drift_detected_total{severity="critical"}
```

### Logs Estruturados

```bash
# Logs de predição
kubectl logs -f deployment/approval-service -n approval | grep "prediction"

# Logs de drift detection
kubectl logs -f deployment/orchestrator-dynamic -n orchestrator-dynamic | grep "drift"

# Logs de erro
kubectl logs -f deployment/approval-service -n approval --tail=100 | grep "ERROR"
```

---

## Rollback Plan

### Rollback Imediato (< 5 min)

```bash
# 1. Desativar feature flags
kubectl patch configmap approval-service-config -n approval --type=json \
  -p='[{"op": "replace", "path": "/data/USE_PROFESSIONAL_FEATURES", "value": "false"}]'

# 2. Restart pods
kubectl rollout restart deployment/approval-service -n approval
kubectl rollout restart deployment/orchestrator-dynamic -n orchestrator-dynamic

# 3. Verificar recovery
kubectl rollout status deployment/approval-service -n approval
kubectl rollout status deployment/orchestrator-dynamic -n orchestrator-dynamic
```

### Rollback de Versão

```bash
# Voltar para imagem anterior
kubectl set image deployment/approval-service approval-service=ghcr.io/albinojimy/neural-hive-mind/approval-service:1.0.0 -n approval
kubectl set image deployment/orchestrator-dynamic orchestrator-dynamic=ghcr.io/albinojimy/neural-hive-mind/orchestrator-dynamic:latest -n orchestrator-dynamic
```

---

## Checklist de Deploy

### Pré-Deploy
- [ ] Código mergeado para main (TICKET 3.4, 3.2, 2.3)
- [ ] Testes unitários passando (52+ testes)
- [ ] Testes de integração passando (19 testes E2E)
- [ ] Reference data criado (`ml_models/approval_v7_reference.pkl`)

### Deploy Fase 1 (Feature Flags OFF)
- [ ] Imagens buildadas e pushadas
- [ ] Feature flags configuradas (OFF por padrão)
  - `USE_PROFESSIONAL_FEATURES=false`
  - `ML_AUTO_RETRAIN_ENABLED=false`
- [ ] Deploy executado no staging
- [ ] Pods rodando sem crashes
- [ ] Logs sem erros
- [ ] Métricas baseline coletadas (24h)

### Deploy Fase 2 (Feature Flags ON)
- [ ] Ativar `USE_PROFESSIONAL_FEATURES=true`
- [ ] Verificar predições profissionais funcionando
- [ ] Ativar drift detection checks
- [ ] Verificar logs de drift detection
- [ ] Métricas comparativas coletadas (24h)

### Deploy Fase 3 (Auto-Retrain - OPCIONAL)
- [ ] Ativar `ML_AUTO_RETRAIN_ENABLED=true`
- [ ] Monitorar triggers de retrain
- [ ] Verificar rollback automático
- [ ] Análise completa
- [ ] Decisão documentada

---

## Comandos Úteis

```bash
# Ver pods
kubectl get pods -n approval
kubectl get pods -n orchestrator-dynamic

# Ver configmaps
kubectl get configmap approval-service-config -n approval -o yaml
kubectl get configmap orchestrator-config -n orchestrator-dynamic -o yaml

# Ver eventos
kubectl get events -n approval --sort-by='.lastTimestamp'
kubectl get events -n orchestrator-dynamic --sort-by='.lastTimestamp'

# Executar pod para debug
kubectl exec -it deployment/approval-service -n approval -- /bin/bash

# Port forward para teste local
kubectl port-forward svc/approval-service 8080:8080 -n approval
```

---

## Validação por Componente

### Model Promotion Pipeline (TICKET 3.4)

**Objetivo:** Validar que modelos são promovidos de staging → production com segurança.

```bash
# 1. Verificar se o modelo de referência existe
kubectl exec -it deployment/approval-service -n approval -- ls -la /app/ml_models/

# 2. Verificar logs de promoção de modelo
kubectl logs -f deployment/approval-service -n approval | grep -i "promotion"

# 3. Testar validação de modelo
kubectl exec -it deployment/approval-service -n approval -- python -c "
from ml_pipelines.deployment.model_promotion import ModelPromotion
promo = ModelPromotion()
result = promo.validate_model('v7')
print(f'Validation result: {result}')
"

# 4. Verificar backup de modelos
kubectl exec -it deployment/approval-service -n approval -- ls -la /app/ml_models/backups/
```

**Métricas a Validar:**
- Acurácia mínima: 0.85
- F1 Score mínimo: 0.80
- Drift score máximo: 0.3

### Drift Detection (TICKET 3.2)

**Objetivo:** Validar detecção de drift em features e predições.

```bash
# 1. Verificar baseline de referência carregado
kubectl logs -f deployment/orchestrator-dynamic -n orchestrator-dynamic | grep -i "reference.*baseline"

# 2. Verificar checks de drift sendo executados
kubectl logs -f deployment/orchestrator-dynamic -n orchestrator-dynamic | grep -i "drift.*check"

# 3. Forçar um check de drift manualmente
kubectl exec -it deployment/orchestrator-dynamic -n orchestrator-dynamic -- python -c "
from src.monitoring.drift_detector import DriftDetector
detector = DriftDetector()
report = detector.run_drift_check()
print(f'Drift status: {report[\"overall_status\"]}')
"
```

**Métricas a Validar:**
- PSI threshold: 0.25 (feature drift)
- MAE ratio: 1.5 (prediction drift)
- KS p-value: 0.05 (target drift)

### Auto-Retrain Integration (TICKET 3.2)

**Objetivo:** Validar que drift crítico trigger retrain automático.

```bash
# 1. Verificar se connector está disponível
kubectl logs -f deployment/orchestrator-dynamic -n orchestrator-dynamic | grep -i "retrain.*connector"

# 2. Simular drift crítico (TEST ONLY)
kubectl exec -it deployment/orchestrator-dynamic -n orchestrator-dynamic -- python -c "
# Simular drift crítico para testar trigger
from src.consumers.decision_consumer import DecisionConsumer
# ... código de teste ...
"

# 3. Verificar triggers de retrain
kubectl logs -f deployment/orchestrator-dynamic -n orchestrator-dynamic | grep -i "trigger.*retrain"
```

**Métricas a Validar:**
- Trigger executado quando drift > 0.3
- Notificação enviada
- Modelo em backup antes de promover novo

---

## Próximos Passos (Pós-Deploy)

Após validação bem-sucedida em staging:

1. **Deploy em Produção** (mesmo processo, com janela de manutenção)
2. **Monitoramento 7 dias** com feature flag ON
3. **Remover código legado** (30 regex manuais)
4. **Documentar aprendizados**
5. **Iniciar EPIC 3** (Auto-Retrain Integration)

---

**Fim do Guia de Deploy Staging**
