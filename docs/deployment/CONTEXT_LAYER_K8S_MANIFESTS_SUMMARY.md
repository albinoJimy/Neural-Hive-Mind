# Context Layer - K8s Manifests Summary

> **Data:** 2026-04-23
> **Status:** ✅ Completo
> **Task:** #16 - K8s deployment manifests

---

## Arquivos Criados

### 1. ConfigMaps

| Arquivo | Descrição |
|---------|-----------|
| `k8s/context-layer-configmap.yaml` | ConfigMap compartilhado com todas as configurações do Context Layer |

### 2. Service Deployments

| Arquivo | Descrição | Context Layer Integration |
|---------|-----------|---------------------------|
| `k8s/semantic-translation-engine-deployment.yaml` | STE com enrich_context e workflow_type | ✅ initContainer + PYTHONPATH |
| `k8s/orchestrator-dynamic-deployment.yaml` | Orchestrator com routing dinâmico C↔G | ✅ initContainer + PYTHONPATH |
| `k8s/gateway-intencoes-context-layer-deployment.yaml` | Gateway com PII detection | ✅ initContainer + PYTHONPATH |
| `k8s/context-layer-example-deployment.yaml` | Exemplo de integração | ✅ Documentação |

### 3. Scripts

| Arquivo | Descrição |
|---------|-----------|
| `k8s/validate-context-layer.sh` | Valida manifests antes do deploy |
| `k8s/context-layer-deploy.sh` | Aplica manifests na ordem correta |

### 4. Documentação

| Arquivo | Descrição |
|---------|-----------|
| `k8s/README.md` | Atualizado com seção Context Layer |
| `docs/deployment/CONTEXT_LAYER_DEPLOYMENT.md` | Guia completo de deploy |
| `libs/neural_hive_context/README.md` | Documentação da biblioteca |

---

## Pattern de Integração

Todos os serviços consumidores seguem o mesmo padrão:

```yaml
spec:
  initContainers:
  - name: install-neural-hive-context
    image: python:3.12-slim
    command:
      - sh
      - -c
      - |
        pip install --no-cache-dir --target=/app/libs \
          git+https://github.com/albinojimy/Neural-Hive-Mind.git@main#subdirectory=libs/neural_hive_context
    volumeMounts:
    - name: python-libs
      mountPath: /app/libs
  containers:
  - name: <service>
    env:
    - name: PYTHONPATH
      value: "/app/libs:/usr/local/lib/python3.12/site-packages"
    envFrom:
    - configMapRef:
        name: context-layer-config
    volumeMounts:
    - name: python-libs
      mountPath: /app/libs
      readOnly: true
  volumes:
  - name: python-libs
    emptyDir: {}
```

---

## Serviços e Context Layer Features

| Serviço | Context Layer Features |
|---------|----------------------|
| **Semantic Translation Engine** | `enrich_context()`, `workflow_type`, PII detection |
| **Orchestrator Dynamic** | Routing dinâmico C↔G baseado em `workflow_type` |
| **Gateway Intenções** | PII detection em tempo real, masking em logs |

---

## Variáveis de Ambiente Context Layer

| Variável | Default | Descrição |
|----------|---------|-----------|
| `CONTEXT_LAYER_ENABLED` | true | Habilita Context Layer |
| `CONTEXT_CACHE_ENABLED` | true | Habilita cache LRU |
| `WORKFLOW_CLASSIFIER_TYPE` | multi_signal | Tipo de classificador |
| `WORKFLOW_CLASSIFIER_THRESHOLD` | 0.45 | Threshold para decisão |
| `PII_DETECTOR_ENABLED` | true | Habilita detecção PII |
| `PII_DETECTOR_ANGOLAN_ENABLED` | true | Habilita PII angolanos |

---

## Deploy Steps

```bash
# 1. Validar
./k8s/validate-context-layer.sh

# 2. Aplicar
./k8s/context-layer-deploy.sh

# 3. Verificar
kubectl get pods -n semantic-translation-engine
kubectl get pods -n orchestrator-dynamic
kubectl get pods -n gateway

# 4. Verificar instalação da biblioteca
kubectl exec -n semantic-translation-engine deployment/semantic-translation-engine -- \
  python -c "import neural_hive_context; print('OK')"
```

---

## Monitoring

Todos os serviços incluem:

- **ServiceMonitor** para métricas Prometheus
- **HPA** para autoscaling (2-10 replicas)
- **NetworkPolicy** para segurança
- **Probes** para health checks

---

## Troubleshooting

### initContainer Falha

```bash
kubectl logs -n semantic-translation-engine deployment/semantic-translation-engine \
  -c install-neural-hive-context
```

### Import Error

```bash
kubectl exec -n semantic-translation-engine deployment/semantic-translation-engine -- \
  python -c "from neural_hive_context.services import MultiSignalWorkflowClassifier; print('OK')"
```

### Ver PYTHONPATH

```bash
kubectl exec -n semantic-translation-engine deployment/semantic-translation-engine -- \
  env | grep PYTHONPATH
```

---

## Status Final

| Item | Status |
|------|--------|
| ConfigMaps | ✅ 4 criados |
| Deployments | ✅ 3 criados |
| HPAs | ✅ 3 criados |
| ServiceMonitors | ✅ 3 criados |
| NetworkPolicies | ✅ 3 criados |
| Scripts | ✅ 2 criados |
| Documentação | ✅ 3 atualizados/criados |

---

**Context Layer K8s Deployment - Completo**
