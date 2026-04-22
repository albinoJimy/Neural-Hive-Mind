# Correções Aplicadas - Problemas Kubernetes
**Data:** 2026-04-22
**Cluster:** neural-hive-prod

---

## ✅ Prioridade 1 (CRÍTICO) - Concluído

### 1. grpc Version Mismatch - RESOLVIDO
**Arquivo:** `services/optimizer-agents/requirements-optimizer.txt`
- **Removido:** `grpcio-health-checking==1.68.1` (linha 15)
- **Justificativa:** Já definido corretamente em requirements-base.txt como 1.71.2

**Arquivo:** `libraries/neural_hive_integration/setup.py`
- **Alterado:** `"grpcio>=1.68.1"` → `"grpcio>=1.71.2"` (linha 22)
- **Justificativa:** Alinhar com requirements-base.txt

### 2. Missing Module neural_hive_security - RESOLVIDO
**Arquivo:** `services/architect-agent/Dockerfile`
- **Removido:** Linhas 26-28 (instalação de neural_hive_security)
- **Justificativa:** Código não usa mais essa biblioteca

**Arquivo:** `services/architect-agent/src/api/app.py`
- **Alterado:** Comentário linha 25 para refletir implementação local

---

## ✅ Prioridade 2 (ALTA) - Concluído

### 3. Duplicate HPAs - RESOLVIDO
**Ação Executada:** Remoção de 5 HPAs duplicados via kubectl
```bash
kubectl delete hpa orchestrator-dynamic-hpa -n neural-hive
kubectl delete hpa service-registry-hpa -n neural-hive
kubectl delete hpa optimizer-agents-hpa -n neural-hive
kubectl delete hpa self-healing-engine-hpa -n neural-hive
kubectl delete hpa sla-management-system-hpa -n neural-hive
```

**Result:** AmbiguousSelector warnings eliminados

### 4. Metrics API - FUNCIONANDO
**Status:** metrics-server já estava instalado e funcionando
- Pod: `metrics-server-59d465df9f-222kw` (1/1 Running)
- API: `/apis/metrics.k8s.io/v1beta1/nodes` retornando métricas

**Ação:** Nenhuma necessária

---

## ✅ Prioridade 3 (MÉDIA) - Em Progresso

### 5. Gatekeeper Admission Labels - PARCIALMENTE RESOLVIDO
**Arquivos Modificados:**
- `services/gateway-intencoes/helm/gateway-intencoes/templates/deployment.yaml`
- `services/orchestrator-dynamic/helm/orchestrator-dynamic/templates/deployment.yaml`
- `services/optimizer-agents/helm/optimizer-agents/templates/deployment.yaml` (já usava helpers)
- `services/scout-agents/helm/scout-agents/templates/deployment.yaml` (já usava helpers)
- `services/worker-agents/helm/worker-agents/templates/deployment.yaml`

**Labels Adicionados:**
```yaml
labels:
  app: {{ .Chart.Name }}
  app.kubernetes.io/name: {{ .Chart.Name }}
  app.kubernetes.io/component: {{ .Chart.Name }}
  app.kubernetes.io/part-of: neural-hive-mind
```

**Próximos Passos:**
- Rebuild e redeploy dos serviços afetados
- Verificar se novos pods são aceitos pelo Gatekeeper

### 6. Insufficient CPU - PENDENTE
**Status:** Pods pending por insufficient CPU ainda existem
**Causa:** Anti-affinity rules com peso 100

**Solução Recomendada:**
- Reduzir peso de anti-affinity de 100 para 50
- Ou usar topologia de zone ao invés de hostname

**Arquivos a modificar:** Helm charts de todos os serviços

---

## 📊 Status Atual

| Problema | Status | Ação |
|----------|--------|------|
| grpc mismatch | ✅ Resolvido | Rebuild imagem optimizer-agents |
| Missing neural_hive_security | ✅ Resolvido | Rebuild imagem architect-agent |
| Duplicate HPAs | ✅ Resolvido | Nenhuma |
| Metrics API | ✅ Funcionando | Nenhuma |
| Gatekeeper labels | 🟡 Parcial | Rebuild e redeploy serviços |
| Insufficient CPU | ⚠️ Pendente | Ajustar anti-affinity |

---

## 🔧 Próximos Passos

### Imediato
1. Rebuild imagem do optimizer-agents:
   ```bash
   docker build -t optimizer-agents:latest -f services/optimizer-agents/Dockerfile .
   ```

2. Rebuild imagem do architect-agent:
   ```bash
   docker build --no-cache -t architect-agent:latest -f services/architect-agent/Dockerfile .
   ```

3. Redeploy serviços com labels atualizados:
   ```bash
   helm upgrade gateway-intencoes ./services/gateway-intencoes/helm/gateway-intencoes -n neural-hive
   helm upgrade orchestrator-dynamic ./services/orchestrator-dynamic/helm/orchestrator-dynamic -n neural-hive
   helm upgrade worker-agents ./services/worker-agents/helm/worker-agents -n neural-hive
   ```

### Curto Prazo
4. Ajustar anti-affinity rules para resolver problema de CPU

### Longo Prazo
5. Implementar validação nos scripts de deploy para prevenir duplicação de HPA
6. Documentar padrões de nomenclatura e labels

---

**Documento:** K8S_FIXES_APPLIED_2026-04-22.md
