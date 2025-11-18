# Comandos Rápidos - Neural Specialists

Referência rápida de comandos para gerenciar os 4 Neural Specialists deployados.

---

## Status e Monitoramento

### Ver status de todos os specialists
```bash
for ns in specialist-technical specialist-behavior specialist-evolution specialist-architecture; do
    echo "=== $ns ==="
    kubectl get pods -n $ns
    echo ""
done
```

### Ver logs em tempo real
```bash
# Specialist específico
kubectl logs -n specialist-technical -l app=specialist-technical -f

# Todos os specialists (em janelas separadas)
kubectl logs -n specialist-technical -l app=specialist-technical -f
kubectl logs -n specialist-behavior -l app=specialist-behavior -f
kubectl logs -n specialist-evolution -l app=specialist-evolution -f
kubectl logs -n specialist-architecture -l app=specialist-architecture -f
```

### Health checks
```bash
# Technical
kubectl run test-technical --rm -i --restart=Never --image=curlimages/curl -- \
  curl -s http://specialist-technical.specialist-technical.svc.cluster.local:8000/health

# Behavior
kubectl run test-behavior --rm -i --restart=Never --image=curlimages/curl -- \
  curl -s http://specialist-behavior.specialist-behavior.svc.cluster.local:8000/health

# Evolution
kubectl run test-evolution --rm -i --restart=Never --image=curlimages/curl -- \
  curl -s http://specialist-evolution.specialist-evolution.svc.cluster.local:8000/health

# Architecture
kubectl run test-architecture --rm -i --restart=Never --image=curlimages/curl -- \
  curl -s http://specialist-architecture.specialist-architecture.svc.cluster.local:8000/health
```

### Status detalhado
```bash
# Technical
kubectl run test-technical-status --rm -i --restart=Never --image=curlimages/curl -- \
  curl -s http://specialist-technical.specialist-technical.svc.cluster.local:8000/status
```

### Métricas Prometheus
```bash
# Port-forward para acessar métricas
kubectl port-forward -n specialist-technical svc/specialist-technical 8080:8080

# Em outro terminal
curl http://localhost:8080/metrics
```

---

## Gerenciamento de Deployments

### Listar releases Helm
```bash
helm list -n specialist-technical
helm list -n specialist-behavior
helm list -n specialist-evolution
helm list -n specialist-architecture
```

### Upgrade de um specialist
```bash
# Exemplo: Technical
helm upgrade specialist-technical helm-charts/specialist-technical \
  --values helm-charts/specialist-technical/values-k8s.yaml \
  --namespace specialist-technical
```

### Rollback
```bash
# Ver histórico
helm history specialist-technical -n specialist-technical

# Rollback para versão anterior
helm rollback specialist-technical -n specialist-technical

# Rollback para revisão específica
helm rollback specialist-technical 1 -n specialist-technical
```

### Restart de pods
```bash
# Technical
kubectl rollout restart deployment specialist-technical -n specialist-technical

# Todos
for ns in specialist-technical specialist-behavior specialist-evolution specialist-architecture; do
    kubectl rollout restart deployment -n $ns
done
```

---

## Troubleshooting

### Descrever pod (ver eventos)
```bash
kubectl get pods -n specialist-technical
kubectl describe pod -n specialist-technical <pod-name>
```

### Exec into pod
```bash
# Entrar no pod
kubectl exec -it -n specialist-technical <pod-name> -- /bin/bash

# Executar comando único
kubectl exec -n specialist-technical <pod-name> -- python --version
```

### Verificar secrets
```bash
kubectl get secrets -n specialist-technical
kubectl describe secret specialist-technical-secrets -n specialist-technical

# Ver valores (base64 encoded)
kubectl get secret specialist-technical-secrets -n specialist-technical -o yaml
```

### Verificar ConfigMaps
```bash
kubectl get configmaps -n specialist-technical
kubectl describe configmap specialist-technical-config -n specialist-technical
```

### Eventos do namespace
```bash
kubectl get events -n specialist-technical --sort-by='.lastTimestamp'
```

### Testar conectividade com dependências
```bash
# MongoDB
kubectl run test-mongo --rm -i --restart=Never --image=mongo:7.0 -- \
  mongosh "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017" \
  --eval "db.adminCommand('ping')"

# Neo4j (HTTP)
kubectl run test-neo4j --rm -i --restart=Never --image=curlimages/curl -- \
  curl -s http://neo4j.neo4j-cluster.svc.cluster.local:7474

# Redis
kubectl run test-redis --rm -i --restart=Never --image=redis:7-alpine -- \
  redis-cli -h neural-hive-cache.redis-cluster.svc.cluster.local PING

# MLflow
kubectl run test-mlflow --rm -i --restart=Never --image=curlimages/curl -- \
  curl -s http://mlflow.mlflow.svc.cluster.local:5000/health
```

---

## Desenvolvimento

### Port-forward para desenvolvimento local
```bash
# Technical - HTTP
kubectl port-forward -n specialist-technical svc/specialist-technical 8000:8000

# Technical - gRPC
kubectl port-forward -n specialist-technical svc/specialist-technical 50051:50051

# Technical - HTTP + gRPC
kubectl port-forward -n specialist-technical svc/specialist-technical 8000:8000 50051:50051

# Behavior
kubectl port-forward -n specialist-behavior svc/specialist-behavior 8001:8000 50052:50051

# Evolution
kubectl port-forward -n specialist-evolution svc/specialist-evolution 8002:8000 50053:50051

# Architecture
kubectl port-forward -n specialist-architecture svc/specialist-architecture 8003:8000 50054:50051
```

### Testar endpoints localmente (após port-forward)
```bash
# Health check
curl http://localhost:8000/health

# Status detalhado
curl http://localhost:8000/status

# Métricas
curl http://localhost:8080/metrics

# Feedback API (se habilitado)
curl http://localhost:8000/api/v1/feedback/stats
```

### Rebuild e redeploy
```bash
# 1. Build nova imagem
docker build -t neural-hive/specialist-technical:v5 \
  -f services/specialist-technical/Dockerfile .

# 2. Export para containerd
docker save neural-hive/specialist-technical:v5 -o /tmp/specialist-technical-v5.tar
ctr -n k8s.io images import /tmp/specialist-technical-v5.tar
rm /tmp/specialist-technical-v5.tar

# 3. Update values.yaml
# Editar helm-charts/specialist-technical/values-k8s.yaml
# Mudar image.tag para v5

# 4. Upgrade Helm release
helm upgrade specialist-technical helm-charts/specialist-technical \
  --values helm-charts/specialist-technical/values-k8s.yaml \
  --namespace specialist-technical
```

---

## Limpeza

### Desinstalar um specialist
```bash
helm uninstall specialist-technical -n specialist-technical
kubectl delete namespace specialist-technical
```

### Desinstalar todos os specialists
```bash
for spec in technical behavior evolution architecture; do
    helm uninstall specialist-$spec -n specialist-$spec
    kubectl delete namespace specialist-$spec
done
```

### Limpar imagens Docker
```bash
# Docker local
docker rmi neural-hive/specialist-technical:v4-final
docker rmi neural-hive/specialist-behavior:v4-final
docker rmi neural-hive/specialist-evolution:v4-final
docker rmi neural-hive/specialist-architecture:v4-final

# Containerd
ctr -n k8s.io images rm docker.io/neural-hive/specialist-technical:v4-final
ctr -n k8s.io images rm docker.io/neural-hive/specialist-behavior:v4-final
ctr -n k8s.io images rm docker.io/neural-hive/specialist-evolution:v4-final
ctr -n k8s.io images rm docker.io/neural-hive/specialist-architecture:v4-final
```

---

## Scripts de Automação

### Deploy todos os specialists
```bash
#!/bin/bash
SPECS=("technical" "behavior" "evolution" "architecture")

for spec in "${SPECS[@]}"; do
    echo "=== Deploying specialist-$spec ==="
    helm install specialist-$spec helm-charts/specialist-$spec \
        --values helm-charts/specialist-$spec/values-k8s.yaml \
        --namespace specialist-$spec \
        --create-namespace \
        --wait --timeout=3m

    if [ $? -eq 0 ]; then
        echo "✓ specialist-$spec deployado com sucesso!"
    else
        echo "✗ Erro no deploy de specialist-$spec"
        exit 1
    fi
done

echo ""
echo "=== Validação ==="
for spec in "${SPECS[@]}"; do
    echo "specialist-$spec:"
    kubectl get pods -n specialist-$spec
done
```

### Health check de todos
```bash
#!/bin/bash
SPECS=("technical" "behavior" "evolution" "architecture")

echo "========================================="
echo "  HEALTH CHECKS - 4 SPECIALISTS"
echo "========================================="
echo ""

for spec in "${SPECS[@]}"; do
    echo "=== specialist-$spec ==="
    kubectl run test-$spec-health --rm -i --restart=Never --image=curlimages/curl -- \
        curl -s http://specialist-$spec.specialist-$spec.svc.cluster.local:8000/health
    echo ""
done

echo "========================================="
```

### Coletar logs de todos
```bash
#!/bin/bash
SPECS=("technical" "behavior" "evolution" "architecture")
OUTPUT_DIR="/tmp/specialists-logs"

mkdir -p $OUTPUT_DIR

for spec in "${SPECS[@]}"; do
    echo "Coletando logs de specialist-$spec..."
    kubectl logs -n specialist-$spec -l app=specialist-$spec \
        > $OUTPUT_DIR/specialist-$spec.log
done

echo "Logs salvos em $OUTPUT_DIR/"
ls -lh $OUTPUT_DIR/
```

---

## Configurações Comuns

### Alterar log level
```bash
# Editar values-k8s.yaml
# config.logLevel: DEBUG | INFO | WARNING | ERROR

# Aplicar mudança
helm upgrade specialist-technical helm-charts/specialist-technical \
  --values helm-charts/specialist-technical/values-k8s.yaml \
  --namespace specialist-technical
```

### Alterar recursos (CPU/Memory)
```bash
# Editar values-k8s.yaml
# resources:
#   requests:
#     cpu: 500m
#     memory: 1Gi
#   limits:
#     cpu: 2000m
#     memory: 4Gi

# Aplicar mudança
helm upgrade specialist-technical helm-charts/specialist-technical \
  --values helm-charts/specialist-technical/values-k8s.yaml \
  --namespace specialist-technical
```

### Habilitar autoscaling
```bash
# Editar values-k8s.yaml
# autoscaling:
#   enabled: true
#   minReplicas: 2
#   maxReplicas: 10
#   targetCPUUtilizationPercentage: 70

# Aplicar mudança
helm upgrade specialist-technical helm-charts/specialist-technical \
  --values helm-charts/specialist-technical/values-k8s.yaml \
  --namespace specialist-technical

# Verificar HPA
kubectl get hpa -n specialist-technical
```

---

## Referências

- [DEPLOYMENT_SPECIALISTS_FASE3.md](DEPLOYMENT_SPECIALISTS_FASE3.md) - Documentação completa do deployment
- [COMANDOS_UTEIS.md](COMANDOS_UTEIS.md) - Comandos gerais do sistema
- [README.md](README.md) - Documentação geral do projeto
