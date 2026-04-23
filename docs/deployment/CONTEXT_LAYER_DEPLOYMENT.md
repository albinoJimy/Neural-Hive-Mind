# Context Layer - Deployment Guide

> **Version:** 1.0.0
> **Last Updated:** 2026-04-24
> **Status:** Production Ready

---

## Overview

`neural_hive_context` é uma biblioteca Python que fornece serviços de contexto para decisões de roteamento no Neural Hive Mind. Ela é usada por:

- **Semantic Translation Engine** - Enriquecimento de CognitivePlan
- **Orchestrator Dynamic** - Roteamento entre Fluxo C e Fluxo G
- **Gateway Intenções** - Detecção PII em tempo real

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    neural_hive_context                      │
│                        (Biblioteca)                          │
├─────────────────────────────────────────────────────────────┤
│  Models: RichContext, WorkflowType, PIIType, PIIResult      │
│  Services:                                                   │
│    - MultiSignalWorkflowClassifier                          │
│    - RegexPIIDetector (11 tipos BR)                         │
│    - AngolanPIIDetector (3 tipos AO)                        │
│    - ContextManagerService                                  │
│    - StubActiveLearningService                              │
│  Interfaces: IWorkflowClassifier, IPIIDetector, etc         │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ pip install
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼────┐      ┌───────▼──────┐     ┌─────▼─────┐
   │   STE   │      │ Orchestrator │     │  Gateway  │
   │ (parse) │      │   (routing)  │     │   (NLU)   │
   └─────────┘      └──────────────┘     └───────────┘
```

---

## Deployment Steps

### 1. Aplicar ConfigMap

```bash
kubectl apply -f k8s/context-layer-configmap.yaml
```

### 2. Atualizar Serviços Consumidores

Para cada serviço que usa `neural_hive_context`, adicionar as variáveis de ambiente do ConfigMap.

#### Semantic Translation Engine

Adicionar ao `deployment.yaml`:

```yaml
spec:
  template:
    spec:
      containers:
      - name: semantic-translation-engine
        envFrom:
        - configMapRef:
            name: context-layer-config
        # ... outras envs
        volumeMounts:
        - name: neural-hive-context
          mountPath: /app/libs/neural_hive_context
          readOnly: true
      volumes:
      - name: neural-hive-context
        emptyDir: {}
        initContainers:
        - name: install-neural-hive-context
          image: python:3.12-slim
          command:
            - pip
            - install
            - --target=/app/libs
            - git+https://github.com/albinojimy/Neural-Hive-Mind.git@main#subdirectory=libs/neural_hive_context
          volumeMounts:
          - name: neural-hive-context
            mountPath: /app/libs
```

#### Orchestrator Dynamic

Similar ao STE, adicionar `envFrom` e volume mount.

---

## 3. Configuração por Serviço

### Semantic Translation Engine

```yaml
# ste-deployment.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ste-context-layer-config
  namespace: neural-hive-mind
data:
  # Habilitar enrich_context
  STE_ENABLE_CONTEXT_ENRICHMENT: "true"
  STE_CONTEXT_CLASSIFIER_TYPE: "multi_signal"
  STE_CONTEXT_PII_DETECTION: "true"
```

### Orchestrator Dynamic

```yaml
# orchestrator-deployment.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orchestrator-context-layer-config
  namespace: neural-hive-mind
data:
  # Habilitar routing dinâmico
  ORCHESTRATOR_ENABLE_DYNAMIC_ROUTING: "true"
  ORCHESTRATOR_WORKFLOW_CLASSIFIER_TYPE: "multi_signal"
  ORCHESTRATOR_DEFAULT_WORKFLOW: "orchestration"
```

---

## 4. Verificação de Deploy

### Verificar ConfigMap

```bash
kubectl get configmap context-layer-config -n neural-hive-mind -o yaml
```

### Verificar Pods

```bash
kubectl get pods -n neural-hive-mind -l component=context-layer
```

### Logs do Context Layer

```bash
# Semantic Translation Engine
kubectl logs -n neural-hive-mind deployment/semantic-translation-engine \
  -c semantic-translation-engine | grep -i context

# Orchestrator Dynamic
kubectl logs -n neural-hive-mind deployment/orchestrator-dynamic \
  -c orchestrator-dynamic | grep -i workflow
```

---

## 5. Testes de Integração

### Teste 1: Workflow Classification

```python
from neural_hive_context.services import MultiSignalWorkflowClassifier
from neural_hive_context.models import RichContext

classifier = MultiSignalWorkflowClassifier()
context = RichContext(...)

result = await classifier.classify(context)
print(f"Workflow: {result.workflow_type}")  # ORCHESTRATION ou GENERATION
```

### Teste 2: PII Detection

```python
from neural_hive_context.services import RegexPIIDetector

detector = RegexPIIDetector()
result = detector.detect("Meu email é joao@exemplo.com")

assert result.has_pii is True
assert result.entities[0].type == PIIType.EMAIL
```

### Teste 3: Angolan PII

```python
from neural_hive_context.services import AngolanPIIDetector

detector = AngolanPIIDetector()
result = detector.detect("NIF: 005123456")

assert result.has_pii is True
assert any(e.type == PIIType.NIF for e in result.entities)
```

---

## 6. Monitoring

### Métricas Prometheus

```yaml
# Adicionar ao ServiceMonitor do serviço
endpoints:
- port: metrics
  path: /metrics
  interval: 30s
  relabelings:
  - source_labels: [__meta_kubernetes_pod_label_neuralhive_layer]
    action: keep
    regex: context
```

### Métricas Importantes

| Métrica | Descrição | SLO |
|---------|-----------|-----|
| `context_layer_classification_duration_seconds` | Latência de classificação | <0.05s p95 |
| `context_layer_pii_detection_duration_seconds` | Latência de detecção PII | <0.03s p95 |
| `context_layer_cache_hit_rate` | Taxa de cache hit | >80% |
| `context_layer_workflow_distribution{type}` | Distribuição ORCHESTRATION vs GENERATION | - |

---

## 7. Troubleshooting

### Problema: Import Error

```
ModuleNotFoundError: No module named 'neural_hive_context'
```

**Solução:** Verificar se o volume está montado e se o initContainer rodou com sucesso.

```bash
kubectl describe pod <pod-name> -n neural-hive-mind
```

### Problema: Routing Sempre para Orchestration

```
Workflow sempre ORCHESTRATION mesmo para intenções de geração
```

**Solução:** Verificar se `workflow_type` está presente no CognitivePlan:

```bash
kubectl logs -n neural-hive-mind deployment/semantic-translation-engine | grep workflow_type
```

### Problema: PII Não Detectado

```
PII não sendo detectado em intents
```

**Solução:** Verificar se `PII_DETECTOR_ENABLED=true` no ConfigMap.

---

## 8. Rollback

```bash
# Rollback para versão anterior
kubectl rollout undo deployment/semantic-translation-engine -n neural-hive-mind

# Verificar status
kubectl rollout status deployment/semantic-translation-engine -n neural-hive-mind
```

---

## 9. Escalabilidade

### HPA (Horizontal Pod Autoscaler)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: semantic-translation-engine-hpa
  namespace: neural-hive-mind
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: semantic-translation-engine
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
```

---

## 10. Segurança

### Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: context-layer-network-policy
  namespace: neural-hive-mind
spec:
  podSelector:
    matchLabels:
      neuralhive/layer: context
  policyTypes:
  - Ingress
  - Egress
  egress:
  # Permitir acesso ao MongoDB
  - to:
    - namespaceSelector:
        matchLabels:
          name: mongodb-cluster
    ports:
    - protocol: TCP
      port: 27017
  # Permitir acesso ao Kafka
  - to:
    - namespaceSelector:
        matchLabels:
          name: kafka
    ports:
    - protocol: TCP
      port: 9092
```

---

## Appendix A: Variáveis de Ambiente

| Variável | Default | Descrição |
|----------|---------|-----------|
| `CONTEXT_LAYER_ENABLED` | true | Habilita Context Layer |
| `CONTEXT_CACHE_ENABLED` | true | Habilita cache LRU |
| `CONTEXT_CACHE_TTL_SECONDS` | 300 | TTL do cache em segundos |
| `WORKFLOW_CLASSIFIER_TYPE` | multi_signal | Tipo de classificador |
| `PII_DETECTOR_ENABLED` | true | Habilita detecção PII |
| `PII_DETECTOR_TYPES_ENABLED` | all | Tipos de PII habilitados |
| `ACTIVE_LEARNING_ENABLED` | true | Habilita Active Learning |

---

**Deployment Guide v1.0.0 - Context Layer**
