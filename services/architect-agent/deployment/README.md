# Kubernetes Deployment - Architect Agent

> Manifestos Kubernetes para deploy do architect-agent (Fluxo G Fase 1)

---

## Pré-requisitos

1. **Kubernetes cluster** v1.28+
2. **Namespace** `neural-hive-staging` criado
3. **Secrets** configuradas:
   - `architect-agent-secrets`: OPENAI_API_KEY, ANTHROPIC_API_KEY
4. **Dependências** externas:
   - MongoDB (pod/service)
   - Redis (pod/service)
   - Neo4j (pod/service)

---

## Estrutura

```
deployment/
├── k8s-deployment.yaml    # Deployment, ServiceAccount, ConfigMap, HPA
├── k8s-service.yaml        # Service, Headless Service, Ingress, PDB
└── README.md              # Este ficheiro
```

---

## Deploy

### 1. Criar namespace

```bash
kubectl create namespace neural-hive-staging
```

### 2. Criar secrets

```bash
kubectl create secret generic architect-agent-secrets \
  --from-literal=openai-api-key=sk-xxx \
  --from-literal=anthropic-api-key=sk-ant-xxx \
  -n neural-hive-staging
```

### 3. Aplicar manifests

```bash
# Aplicar deployment
kubectl apply -f deployment/k8s-deployment.yaml

# Aplicar service
kubectl apply -f deployment/k8s-service.yaml

# Ou tudo de uma vez
kubectl apply -f deployment/
```

### 4. Verificar deploy

```bash
# Ver pods
kubectl get pods -n neural-hive-staging -l app=architect-agent

# Ver deployment
kubectl get deployment architect-agent -n neural-hive-staging

# Ver service
kubectl get service architect-agent -n neural-hive-staging

# Ver logs
kubectl logs -f deployment/architect-agent -n neural-hive-staging
```

---

## Configuração

### Replicas

- **Min:** 2 (HA)
- **Max:** 10 (HPA)
- **Default:** 2

### Resources

| Container | Requests | Limits |
|-----------|----------|--------|
| architect-agent | 250m CPU, 256Mi RAM | 500m CPU, 512Mi RAM |

### Autoscaling

**HPA (Horizontal Pod Autoscaler):**
- Scale up: CPU > 70% ou Memory > 80%
- Scale down: CPU < 35% e Memory < 40%
- Stable window: 5 minutos

### Probes

| Tipo | Path | Início | Período | Timeout |
|------|------|--------|---------|---------|
| Liveness | `/health/live` | 10s | 30s | 5s |
| Readiness | `/health/ready` | 5s | 10s | 3s |

---

## Serviços

### architect-agent (ClusterIP)

Porta principal para tráfico HTTP interno.

- **Port:** 8008
- **Type:** ClusterIP
- **Selector:** `app=architect-agent`

### architect-agent-headless (ClusterIP)

Para statefulsets ou need DNS direto.

- **Port:** 8008
- **Type:** ClusterIP (headless)
- **Selector:** `app=architect-agent`

### Ingress

**Host:** `architect.staging.neural-hive.com`

Rota externa via ingress nginx.

---

## Upgrade

### Rolling Update

```bash
# Atualizar imagem
kubectl set image deployment/architect-agent \
  architect-agent=ghcr.io/albinojimy/neural-hive-mind/architect-agent:v0.2.1 \
  -n neural-hive-staging

# Ou aplicar novo deployment.yaml
kubectl apply -f deployment/k8s-deployment.yaml
```

### Rollback

```bash
kubectl rollout undo deployment/architect-agent -n neural-hive-staging

# Ver histórico
kubectl rollout history deployment/architect-agent -n neural-hive-staging
```

---

## Troubleshooting

### Pods não iniciam

```bash
# Ver pod events
kubectl describe pod -n neural-hive-staging -l app=architect-agent

# Ver logs
kubectl logs -n neural-hive-staging -l app=architect-agent --previous
```

### Service não responde

```bash
# Ver endpoints
kubectl get endpoints architect-agent -n neural-hive-staging

# Testar internamente
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n neural-hive-staging \
  -- curl -X POST http://architect-agent:8008/api/v1/architecture \
  -H "Content-Type: application/json" \
  -d '{"intent": "Test", "context": {}}'
```

### HPA não escala

```bash
# Ver métricas
kubectl get hpa architect-agent -n neural-hive-staging

# Ver resource usage
kubectl top pod -n neural-hive-staging -l app=architect-agent
```

---

## Alternativa: Helm

Para deploy via Helm (já existe chart em `helm/architect-agent/`):

```bash
helm install architect-agent helm/architect-agent/ \
  --namespace neural-hive-staging \
  --values helm/architect-agent/values-staging.yaml
```

---

## Monitorização

### Métricas Prometheus

Service expõe métricas na porta 9098:

```bash
kubectl port-forward -n neural-hive-staging svc/architect-agent 9098:9098
curl http://localhost:9098/metrics
```

### Logs Estruturados

```bash
# Ver logs em tempo real
kubectl logs -f -n neural-hive-staging -l app=architect-agent

# Logs dos últimos 10 minutos
kubectl logs -n neural-hive-staging -l app=architect-agent --since=10m
```

---

**Versão:** v0.2.0
**Última atualização:** 2026-04-17
