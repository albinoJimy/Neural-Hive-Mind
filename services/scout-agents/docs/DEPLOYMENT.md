# Guide de Deploy - Scout Agents

## Pré-requisitos

- Kubernetes 1.25+
- Helm 3.x
- Redis cluster (opcional)
- Kafka cluster (opcional)
- Prometheus + Grafana (para observabilidade)

## Deploy Local com Docker Compose

```bash
# Subir serviços
docker-compose up -d

# Verificar status
docker-compose ps

# Ver logs
docker-compose logs -f scout-agents
```

## Deploy em Kubernetes

### 1. Preparar Namespace

```bash
kubectl create namespace scout-agents
```

### 2. Instalar com Helm

```bash
helm repo add neural-hive-mind https://charts.neural-hive-mind.com
helm install scout-agents neural-hive-mind/scout-agents \
  --namespace scout-agents \
  --values values.yaml
```

### 3. Configuração Personalizada

Crie `custom-values.yaml`:

```yaml
replicaCount: 3

image:
  repository: ghcr.io/albinojimy/neural-hive-mind/scout-agents
  tag: "v1.0.0"

config:
  redis:
    url: "redis://redis.prod.svc.cluster.local:6379"
  kafka:
    bootstrapServers: "kafka.prod.svc.cluster.local:9092"

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 200m
    memory: 256Mi

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20
```

```bash
helm upgrade scout-agents neural-hive-mind/scout-agents \
  --namespace scout-agents \
  --values custom-values.yaml
```

## Verificação de Deploy

```bash
# Ver pods
kubectl get pods -n scout-agents

# Ver serviços
kubectl get svc -n scout-agents

# Ver logs
kubectl logs -f deployment/scout-agents -n scout-agents

# Testar health endpoint
kubectl port-forward svc/scout-agents 8000:8000 -n scout-agents
curl http://localhost:8000/health/ready
```

## CI/CD

### GitHub Actions

O deploy é automático via push para branch `main`:

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]
    paths:
      - 'services/scout-agents/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: |
          cd services/scout-agents
          pytest --cov=src

  build-and-deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build and push image
        run: |
          docker build -t ghcr.io/scout-agents:${{ github.sha }} .
          docker push ghcr.io/scout-agents:${{ github.sha }}
      - name: Deploy to Kubernetes
        run: |
          helm upgrade scout-agents ./helm/scout-agents \
            --set image.tag=${{ github.sha }}
```

## Rollback

```bash
# Ver histórico
helm history scout-agents -n scout-agents

# Rollback para versão anterior
helm rollback scout-agents -n scout-agents

# Rollback para revisão específica
helm rollback scout-agents 2 -n scout-agents
```

## Troubleshooting

### Pods não iniciam

```bash
kubectl describe pod <pod-name> -n scout-agents
kubectl logs <pod-name> -n scout-agents --previous
```

### Conexão Redis falha

```bash
# Verificar serviço Redis
kubectl get svc redis -n scout-agents

# Testar conexão
kubectl run -it --rm debug --image=redis:alpine --restart=Never \
  -- redis-cli -h redis scout-agents ping
```

### Alta latência

```bash
# Ver HPA
kubectl get hpa -n scout-agents

# Aumentar réplicas
kubectl scale deployment scout-agents --replicas=10 -n scout-agents
```

## Monitoramento

Configure alertas no Prometheus:

```yaml
# Alertas recomendados
groups:
  - name: scout-agents
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{job="scout-agents",status=~"5.."}[5m]) > 0.05
        annotations:
          summary: "Alta taxa de erros no Scout Agents"

      - alert: HighMemoryUsage
        expr: process_resident_memory_bytes{job="scout-agents"} > 1GB
        annotations:
          summary: "Alto consumo de memória"

      - alert: StuckExplorations
        expr: scout_active_explorations > 100
        annotations:
          summary: "Muitas explorações ativas"
```
