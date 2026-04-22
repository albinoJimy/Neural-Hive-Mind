# Análise de Causas Raiz - Problemas Kubernetes
**Data:** 2026-04-22
**Cluster:** neural-hive-prod
**Contexto:** Validação completa do ambiente Kubernetes

---

## Índice
1. [grpc Version Mismatch](#1-grpc-version-mismatch)
2. [Insufficient CPU](#2-insufficient-cpu)
3. [Missing Module neural_hive_security](#3-missing-module-neural_hive_security)
4. [Duplicate HPAs](#4-duplicate-hpas)
5. [Metrics API Not Responding](#5-metrics-api-not-responding)
6. [Gatekeeper Admission Labels](#6-gatekeeper-admission-labels)

---

## 1. grpc Version Mismatch

### Status
🔴 **CRÍTICO** - optimizer-agents em CrashLoopBackOff

### Causa Raiz
O `requirements-optimizer.txt` está sobrescrevendo `grpcio-health-checking==1.68.1` enquanto `requirements-base.txt` define `grpcio==1.71.2`.

**Conflito de versões:**
| Arquivo | Linha | Versão | Problema |
|---------|-------|--------|----------|
| requirements-base.txt | 54 | grpcio==1.71.2 | ✅ Correto |
| requirements-base.txt | 55 | grpcio-health-checking==1.71.2 | ✅ Correto |
| requirements-optimizer.txt | 15 | grpcio-health-checking==1.68.1 | ❌ Sobrescreve incorretamente |
| neural_hive_integration/setup.py | 22 | grpcio>=1.68.1 | ⚠️ Versão antiga |

### Solução Definitiva

**Arquivo:** `/services/optimizer-agents/requirements-optimizer.txt`
- **Remover linha 15:** `grpcio-health-checking==1.68.1`
- **Justificativa:** Já está definido corretamente em requirements-base.txt

**Arquivo:** `/libraries/neural_hive_integration/setup.py`
- **Alterar linha 22:** `"grpcio>=1.71.2"` (era 1.68.1)
- **Justificativa:** Alinhar com requirements-base.txt

**Comando de correção:**
```bash
# 1. Remover linha do requirements-optimizer.txt
sed -i '/^grpcio-health-checking/d' services/optimizer-agents/requirements-optimizer.txt

# 2. Atualizar setup.py
sed -i 's/"grpcio>=1.68.1"/"grpcio>=1.71.2"/' libraries/neural_hive_integration/setup.py
```

---

## 2. Insufficient CPU

### Status
🟡 **ALERTA** - 4 pods de gateway-intencoes em Pending

### Causa Raiz
**NÃO é falta de capacidade** - o cluster tem 14.676m CPU disponível (60% livre).

O problema é a **combinação de:**
1. Regra de pod anti-affinity com peso 100 se comportando como required
2. Possíveis pods zombie consumindo recursos
3. Fragmentação de recursos nos nós

**Análise dos nós:**
| Node | CPU Usado | CPU Disp | Status |
|------|-----------|----------|--------|
| vmi2092350 (control) | 3646m (45%) | 6154m | ✅ |
| vmi2911680 | 2073m (34%) | 4027m | ⚠️ Memória 82% |
| vmi2911681 | 949m (15%) | 5251m | ✅ |
| vmi3002938 | 1037m (17%) | 5063m | ✅ |
| vmi3075398 | 2207m (36%) | 3993m | ✅ |

**Total Disponível:** ~24.588m CPU
**Total Usado:** ~9.912m CPU (40%)
**Total Realmente Disponível:** ~14.676m CPU

### Solução Definitiva

**Opção 1: Reduzir peso do anti-affinity (RECOMENDADO)**

Alterar o peso de 100 para 50 nos Helm charts:

```yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 50  # Era 100
        podAffinityTerm:
          labelSelector:
            matchExpressions:
              - key: app
                operator: In
                values:
                  - {{ .Chart.Name }}
          topologyKey: kubernetes.io/hostname
```

**Opção 2: Limpar pods zombie**

```bash
# Remover pods evicted/failed
kubectl get pods --all-namespaces | grep Evicted | awk '{print $1, $2}' | xargs -n2 kubectl delete pod -n
```

**Arquivos a modificar:** Todos os Helm charts dos serviços core

---

## 3. Missing Module neural_hive_security

### Status
🔴 **CRÍTICO** - 11/15 pods em neural-hive-mind em CrashLoopBackOff

### Causa Raiz
O código do `architect-agent` foi refatorado e **NÃO USA MAIS** a biblioteca `neural_hive_security`, mas o **Dockerfile ainda tenta instalá-la** (linhas 26-28).

**Análise:**
- Código atual (`src/config/settings.py`, `src/api/app.py`): NÃO faz importação
- Dockerfile (linhas 26-28): Tenta instalar neural_hive_security
- Resultado: Instalação falha ou biblioteca não disponível

### Solução Definitiva

**Arquivo:** `/services/architect-agent/Dockerfile`
- **Remover linhas 26-28:**
```dockerfile
# Build neural_hive_security library
COPY libraries/python/neural_hive_security/ /tmp/neural_hive_security/
RUN pip install --no-cache-dir --user /tmp/neural_hive_security/ && rm -rf /tmp/neural_hive_security
```

**Arquivo:** `/services/architect-agent/src/api/app.py`
- **Atualizar comentário linha 25:**
```python
# CORS - usa configuração segura por ambiente (implementação local)
```

**Comando de correção:**
```bash
# 1. Editar Dockerfile - remover linhas 26-28
# 2. Forçar rebuild da imagem
docker build --no-cache -t architect-agent:latest -f services/architect-agent/Dockerfile .
```

---

## 4. Duplicate HPAs

### Status
🟡 **ALERTA** - AmbiguousSelector warnings para 5 serviços

### Causa Raiz
Múltiplos HPAs configurados para os mesmos deployments:

| Serviço | HPA 1 | HPA 2 | Conflito |
|---------|-------|-------|----------|
| orchestrator-dynamic | orchestrator-dynamic | orchestrator-dynamic-hpa | ✗ |
| service-registry | service-registry | service-registry-hpa | ✗ |
| optimizer-agents | optimizer-agents | optimizer-agents-hpa | ✗ |
| self-healing-engine | self-healing-engine | self-healing-engine-hpa | ✗ |
| sla-management-system | sla-management-system | sla-management-system-hpa | ✗ |

**Padrão identificado:** O HPA duplicado tem sufixo `-hpa`

### Solução Definitiva

**Ação Imediata:**
```bash
# Remover HPAs duplicados (com sufixo -hpa)
kubectl delete hpa orchestrator-dynamic-hpa -n neural-hive
kubectl delete hpa service-registry-hpa -n neural-hive
kubectl delete hpa optimizer-agents-hpa -n neural-hive
kubectl delete hpa self-healing-engine-hpa -n neural-hive
kubectl delete hpa sla-management-system-hpa -n neural-hive
```

**Prevenção Futura:**
1. Encontrar a fonte dos HPAs duplicados (Helm, Kustomize, CI/CD)
2. Padronizar nomenclatura (sem sufixo `-hpa`)
3. Implementar validação nos scripts de deploy

---

## 5. Metrics API Not Responding

### Status
🟡 **ALERTA** - HPAs com <unknown> targets

### Causa Raiz
**O metrics-server não está instalado** no cluster.

**Evidências:**
- Mensagem: `no metrics returned from resource metrics API`
- Múltiplos HPAs com `<unknown>/70%`
- Ausência de diretório `services/metrics-server/`

### Solução Definitiva

**Instalação via Helm (RECOMENDADO):**
```bash
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/

helm upgrade --install metrics-server metrics-server/metrics-server \
  --namespace kube-system \
  --set args[0]=--kubelet-insecure-tls \
  --set args[1]=--kubelet-preferred-address-types=InternalIP \
  --set args[2]=--v=2
```

**Verificação:**
```bash
# 1. Verificar se o metrics-server está rodando
kubectl get pods -n kube-system -l k8s-app=metrics-server

# 2. Testar métricas
kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes

# 3. Aguardar 2-3 minutos e verificar HPAs
kubectl get hpa -A
```

---

## 6. Gatekeeper Admission Labels

### Status
🟡 **ALERTA** - Pods negados por missing labels

### Causa Raiz
Os manifests Kubernetes usam **APENAS o label `app`**, mas a constraint `must-have-app-label` exige **MÚLTIPLOS LABELS**.

**Labels obrigatórios:**
| Label | Status | Onde |
|-------|--------|------|
| `app` | ✅ Presente | Todos os manifests |
| `app.kubernetes.io/name` | ✗ Faltando | Templates Helm |
| `app.kubernetes.io/component` | ✗ Faltando (provável) | Templates Helm |
| `app.kubernetes.io/part-of` | ✗ Faltando (provável) | Templates Helm |

### Solução Definitiva

**Adicionar labels recomendados pelo Kubernetes em todos os templates Helm:**

```yaml
metadata:
  labels:
    app: {{ .Chart.Name }}
    app.kubernetes.io/name: {{ .Chart.Name }}
    app.kubernetes.io/component: {{ .Chart.Name }}
    app.kubernetes.io/part-of: neural-hive-mind
    app.kubernetes.io/managed-by: Helm
```

**Arquivos a modificar:**
- `/services/*/helm/*/templates/deployment.yaml` (todos os serviços)

**Alternativa:** Ajustar a constraint do Gatekeeper para exigir apenas `app`.

---

## Priorização de Correções

### Prioridade 1 (CRÍTICO - Resolver Imediatamente)
1. ✅ grpc version mismatch - optimizer-agents
2. ✅ Missing neural_hive_security - architect-agent

### Prioridade 2 (ALTA - Resolver em 24h)
3. ⚠️ Duplicate HPAs - remover duplicados
4. ⚠️ Metrics API - instalar metrics-server

### Prioridade 3 (MÉDIA - Resolver em 48h)
5. 📋 Insufficient CPU - ajustar anti-affinity
6. 📋 Gatekeeper labels - adicionar labels ou ajustar constraint

---

## Plano de Execução

```bash
# Passo 1: grpc version mismatch
cd /home/jimy/NHM/Neural-Hive-Mind
sed -i '/^grpcio-health-checking/d' services/optimizer-agents/requirements-optimizer.txt
sed -i 's/"grpcio>=1.68.1"/"grpcio>=1.71.2"/' libraries/neural_hive_integration/setup.py

# Passo 2: Missing neural_hive_security
# Editar services/architect-agent/Dockerfile manualmente

# Passo 3: Duplicate HPAs
kubectl delete hpa orchestrator-dynamic-hpa -n neural-hive
kubectl delete hpa service-registry-hpa -n neural-hive
kubectl delete hpa optimizer-agents-hpa -n neural-hive
kubectl delete hpa self-healing-engine-hpa -n neural-hive
kubectl delete hpa sla-management-system-hpa -n neural-hive

# Passo 4: Metrics API
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
helm upgrade --install metrics-server metrics-server/metrics-server \
  --namespace kube-system \
  --set args[0]=--kubelet-insecure-tls

# Passo 5-6: Requer modificação de Helm charts (fase seguinte)
```

---

**Documento gerado:** 2026-04-22
**Próxima revisão:** Após implementação das correções
