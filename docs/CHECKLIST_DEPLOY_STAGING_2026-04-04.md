# Checklist Deploy Staging - Neural Hive Mind

**Data:** 2026-04-04
**Versao:** 1.0
**Target Environment:** Staging
**Completude:** 97.5%

---

## Legenda

- `[ ]` - Pendente
- `[~]` - Em progresso
- `[x]` - Completo
- `[!]` - Bloqueador / Requer atencao

---

## Parte 1: Pre-requisitos de Infraestrutura

### 1.1 Cluster Kubernetes

- [ ] **Cluster Kubernetes funcional**
  ```bash
  # Verificar conexao com cluster
  kubectl cluster-info
  kubectl get nodes
  ```

- [ ] **kubectl configurado**
  ```bash
  # Verificar contexto atual
  kubectl config current-context
  kubectl config view
  ```

- [ ] **Helm 3.x instalado**
  ```bash
  helm version
  ```

- [ ] **Quotas de recursos configuradas**
  ```bash
  # Verificar resource quotas
  kubectl get resourcequota -n neural-hive-staging
  ```

- [ ] **Storage Class disponivel**
  ```bash
  kubectl get storageclass
  ```

### 1.2 Namespace e Configuracoes Base

- [ ] **Criar namespace de staging**
  ```bash
  kubectl create namespace neural-hive-staging
  kubectl create namespace neural-hive-monitoring
  kubectl create namespace neural-hive-infra
  ```

- [ ] **Configurar labels e annotations**
  ```bash
  kubectl label namespace neural-hive-staging environment=staging
  kubectl label namespace neural-hive-staging project=neural-hive-mind
  ```

- [ ] **Network policies base aplicadas**
  ```bash
  kubectl apply -f k8s/network-policies/base/
  ```

---

## Parte 2: Secrets e Configuracoes Sensíveis

### 2.1 Secrets de Database

- [ ] **MongoDB Secret**
  ```bash
  kubectl create secret generic mongodb-secret \
    --from-literal=uri="mongodb://<user>:<password>@<host>:27017/neural_hive_staging?authSource=admin" \
    --from-literal=username=<user> \
    --from-literal=password=<password> \
    -n neural-hive-staging
  ```

- [ ] **PostgreSQL Secret** (se usado)
  ```bash
  kubectl create secret generic postgres-secret \
    --from-literal=host=<host> \
    --from-literal=port=5432 \
    --from-literal=database=neural_hive_staging \
    --from-literal=username=<user> \
    --from-literal=password=<password> \
    -n neural-hive-staging
  ```

### 2.2 Secrets de Mensageria

- [ ] **Kafka Secret**
  ```bash
  kubectl create secret generic kafka-secret \
    --from-literal=servers="<kafka-broker1>:9092,<kafka-broker2>:9092" \
    --from-literal=username=<user> \
    --from-literal=password=<password> \
    -n neural-hive-staging
  ```

### 2.3 Secrets de Cache e Estado

- [ ] **Redis Secret**
  ```bash
  kubectl create secret generic redis-secret \
    --from-literal=url="redis://<host>:6379" \
    --from-literal=password=<password> \
    -n neural-hive-staging
  ```

- [ ] **Neo4j Secret**
  ```bash
  kubectl create secret generic neo4j-secret \
    --from-literal=uri="bolt://<host>:7687" \
    --from-literal=username=neo4j \
    --from-literal=password=<password> \
    -n neural-hive-staging
  ```

### 2.4 Secrets de Servicos Externos

- [ ] **Temporal Secret**
  ```bash
  kubectl create secret generic temporal-secret \
    --from-literal=host=<temporal-host> \
    --from-literal=port=7233 \
    --namespace=neural-hive-staging
  ```

- [ ] **MLflow Secret**
  ```bash
  kubectl create secret generic mlflow-secret \
    --from-literal=tracking-uri="http://mlflow:5000" \
    --from-literal=s3-endpoint=<s3-endpoint> \
    --from-literal=s3-bucket=<mlflow-bucket> \
    -n neural-hive-staging
  ```

### 2.5 Secrets de Container Registry

- [ ] **GitHub Container Registry Secret**
  ```bash
  kubectl create secret docker-registry ghcr-secret \
    --docker-server=ghcr.io \
    --docker-username=<github-username> \
    --docker-password=<github-token> \
    -n neural-hive-staging
  ```

- [ ] **Secret de pull para todos os namespaces**
  ```bash
  kubectl create secret docker-registry ghcr-secret \
    --docker-server=ghcr.io \
    --docker-username=<github-username> \
    --docker-password=<github-token> \
    -n neural-hive-infra
  ```

### 2.6 Verificar Secrets Criados

- [ ] **Validar secrets**
  ```bash
  kubectl get secrets -n neural-hive-staging
  kubectl describe secret mongodb-secret -n neural-hive-staging
  ```

---

## Parte 3: Infraestrutura Core

### 3.1 Infraestrutura de Mensageria (Kafka)

- [ ] **Deploy Kafka Operator**
  ```bash
  helm install strimzi-operator strimzi/strimzi-kafka-operator \
    -n neural-hive-infra --create-namespace
  ```

- [ ] **Deploy Kafka Cluster**
  ```bash
  kubectl apply -f k8s/infrastructure/kafka/
  ```

- [ ] **Verificar Kafka pods**
  ```bash
  kubectl get pods -n neural-hive-infra -l strimzi.io/cluster=kafka
  kubectl get kafka -n neural-hive-infra
  ```

- [ ] **Criar topicos Kafka**
  ```bash
  kubectl apply -f k8s/infrastructure/kafka/topics/
  ```

- [ ] **Verificar topicos criados**
  ```bash
  kubectl get kafkatopic -n neural-hive-staging
  ```

### 3.2 Banco de Dados

- [ ] **Deploy MongoDB**
  ```bash
  helm install mongodb bitnami/mongodb \
    -n neural-hive-infra \
    --set auth.rootPassword=<password> \
    --set architecture=replicaset \
    --set replicaCount=3 \
    --set persistence.size=50Gi
  ```

- [ ] **Deploy PostgreSQL** (se necessario)
  ```bash
  helm install postgresql bitnami/postgresql \
    -n neural-hive-infra \
    --set auth.password=<password> \
    --set primary.persistence.size=50Gi
  ```

- [ ] **Deploy Redis**
  ```bash
  helm install redis bitnami/redis \
    -n neural-hive-infra \
    --set architecture=standalone \
    --set auth.enabled=true \
    --set auth.password=<password>
  ```

- [ ] **Deploy Neo4j**
  ```bash
  helm install neo4j bitnami/neo4j \
    -n neural-hive-infra \
    --set neo4j.password=<password> \
    --set volumePermissions.enabled=true
  ```

### 3.3 Orquestracao e ML

- [ ] **Deploy Temporal**
  ```bash
  helm install temporal temporal/temporal \
    -n neural-hive-infra \
    --set server.replicaCount=1 \
    --set cassandra.config.enabled=false \
    --set postgresql.enabled=true
  ```

- [ ] **Deploy MLflow**
  ```bash
  helm install mlflow mlflow/mlflow \
    -n neural-hive-infra \
    --set image.repository=ghcr.io/<owner>/mlflow \
    --set defaultArtifactRoot=s3://mlflow/
  ```

- [ ] **Verificar infra pods**
  ```bash
  kubectl get pods -n neural-hive-infra
  ```

---

## Parte 4: MCP Servers (8 Servicos)

### 4.1 Queen MCP Server

- [ ] **Build e push imagem**
  ```bash
  cd services/mcp-servers/queen-mcp-server
  docker build -t ghcr.io/<owner>/queen-mcp-server:v1.0.0-staging .
  docker push ghcr.io/<owner>/queen-mcp-server:v1.0.0-staging
  ```

- [ ] **Deploy via Helm**
  ```bash
  helm install queen-mcp-server services/mcp-servers/queen-mcp-server/helm/ \
    -n neural-hive-staging \
    --set image.repository=ghcr.io/<owner>/queen-mcp-server \
    --set image.tag=v1.0.0-staging \
    --set image.pullSecrets[0].name=ghcr-secret \
    --set queen.opaUrl=http://opa.neural-hive-infra.svc.cluster.local:8181 \
    --set queen.mongodbUri=$(kubectl get secret mongodb-secret -n neural-hive-staging -o jsonpath='{.data.uri}' | base64 -d) \
    --set queen.neo4jUri=$(kubectl get secret neo4j-secret -n neural-hive-staging -o jsonpath='{.data.uri}' | base64 -d) \
    --set queen.redisUri=$(kubectl get secret redis-secret -n neural-hive-staging -o jsonpath='{.data.url}' | base64 -d)
  ```

- [ ] **Verificar deployment**
  ```bash
  kubectl get pods -n neural-hive-staging -l app=queen-mcp-server
  kubectl logs -f deployment/queen-mcp-server -n neural-hive-staging
  ```

- [ ] **Verificar health check**
  ```bash
  kubectl exec -it deployment/queen-mcp-server -n neural-hive-staging -- curl localhost:3012/health
  ```

- [ ] **Testar conexao com Queen Agent**
  ```bash
  kubectl exec -it deployment/queen-mcp-server -n neural-hive-staging -- \
    curl -X POST http://localhost:3012/mcp/tools/list -H "Content-Type: application/json"
  ```

### 4.2 Execution MCP Server

- [ ] **Build e push imagem**
  ```bash
  cd services/mcp-servers/execution-mcp-server
  docker build -t ghcr.io/<owner>/execution-mcp-server:v1.0.0-staging .
  docker push ghcr.io/<owner>/execution-mcp-server:v1.0.0-staging
  ```

- [ ] **Deploy via Helm**
  ```bash
  helm install execution-mcp-server services/mcp-servers/execution-mcp-server/helm/ \
    -n neural-hive-staging \
    --set image.repository=ghcr.io/<owner>/execution-mcp-server \
    --set image.tag=v1.0.0-staging \
    --set image.pullSecrets[0].name=ghcr-secret
  ```

- [ ] **Verificar deployment**
  ```bash
  kubectl get pods -n neural-hive-staging -l app=execution-mcp-server
  kubectl logs -f deployment/execution-mcp-server -n neural-hive-staging
  ```

### 4.3 Architect MCP Server

- [ ] **Build e push imagem**
  ```bash
  cd services/mcp-servers/architect-mcp-server
  docker build -t ghcr.io/<owner>/architect-mcp-server:v1.0.0-staging .
  docker push ghcr.io/<owner>/architect-mcp-server:v1.0.0-staging
  ```

- [ ] **Deploy via Helm**
  ```bash
  helm install architect-mcp-server services/mcp-servers/architect-mcp-server/helm/ \
    -n neural-hive-staging \
    --set image.repository=ghcr.io/<owner>/architect-mcp-server \
    --set image.tag=v1.0.0-staging \
    --set image.pullSecrets[0].name=ghcr-secret
  ```

- [ ] **Verificar deployment**
  ```bash
  kubectl get pods -n neural-hive-staging -l app=architect-mcp-server
  ```

### 4.4 Analyst MCP Server

- [ ] **Build e push imagem**
  ```bash
  cd services/mcp-servers/analyst-mcp-server
  docker build -t ghcr.io/<owner>/analyst-mcp-server:v1.0.0-staging .
  docker push ghcr.io/<owner>/analyst-mcp-server:v1.0.0-staging
  ```

- [ ] **Deploy via Helm**
  ```bash
  helm install analyst-mcp-server services/mcp-servers/analyst-mcp-server/helm/ \
    -n neural-hive-staging \
    --set image.repository=ghcr.io/<owner>/analyst-mcp-server \
    --set image.tag=v1.0.0-staging \
    --set image.pullSecrets[0].name=ghcr-secret
  ```

- [ ] **Verificar deployment**
  ```bash
  kubectl get pods -n neural-hive-staging -l app=analyst-mcp-server
  ```

### 4.5 Guard MCP Server

- [ ] **Build e push imagem**
  ```bash
  cd services/mcp-servers/guard-mcp-server
  docker build -t ghcr.io/<owner>/guard-mcp-server:v1.0.0-staging .
  docker push ghcr.io/<owner>/guard-mcp-server:v1.0.0-staging
  ```

- [ ] **Deploy via Helm**
  ```bash
  helm install guard-mcp-server services/mcp-servers/guard-mcp-server/helm/ \
    -n neural-hive-staging \
    --set image.repository=ghcr.io/<owner>/guard-mcp-server \
    --set image.tag=v1.0.0-staging \
    --set image.pullSecrets[0].name=ghcr-secret
  ```

- [ ] **Verificar deployment**
  ```bash
  kubectl get pods -n neural-hive-staging -l app=guard-mcp-server
  ```

### 4.6 Code Forge MCP Server

- [ ] **Build e push imagem**
  ```bash
  cd services/mcp-servers/code-forge-mcp-server
  docker build -t ghcr.io/<owner>/code-forge-mcp-server:v1.0.0-staging .
  docker push ghcr.io/<owner>/code-forge-mcp-server:v1.0.0-staging
  ```

- [ ] **Deploy via Helm**
  ```bash
  helm install code-forge-mcp-server services/mcp-servers/code-forge-mcp-server/helm/ \
    -n neural-hive-staging \
    --set image.repository=ghcr.io/<owner>/code-forge-mcp-server \
    --set image.tag=v1.0.0-staging \
    --set image.pullSecrets[0].name=ghcr-secret
  ```

- [ ] **Verificar deployment**
  ```bash
  kubectl get pods -n neural-hive-staging -l app=code-forge-mcp-server
  ```

### 4.7 Worker MCP Server

- [ ] **Build e push imagem**
  ```bash
  cd services/mcp-servers/worker-mcp-server
  docker build -t ghcr.io/<owner>/worker-mcp-server:v1.0.0-staging .
  docker push ghcr.io/<owner>/worker-mcp-server:v1.0.0-staging
  ```

- [ ] **Deploy via Helm**
  ```bash
  helm install worker-mcp-server services/mcp-servers/worker-mcp-server/helm/ \
    -n neural-hive-staging \
    --set image.repository=ghcr.io/<owner>/worker-mcp-server \
    --set image.tag=v1.0.0-staging \
    --set image.pullSecrets[0].name=ghcr-secret
  ```

- [ ] **Verificar deployment**
  ```bash
  kubectl get pods -n neural-hive-staging -l app=worker-mcp-server
  ```

### 4.8 Healer MCP Server

- [ ] **Build e push imagem**
  ```bash
  cd services/mcp-servers/healer-mcp-server
  docker build -t ghcr.io/<owner>/healer-mcp-server:v1.0.0-staging .
  docker push ghcr.io/<owner>/healer-mcp-server:v1.0.0-staging
  ```

- [ ] **Deploy via Helm**
  ```bash
  helm install healer-mcp-server services/mcp-servers/healer-mcp-server/helm/ \
    -n neural-hive-staging \
    --set image.repository=ghcr.io/<owner>/healer-mcp-server \
    --set image.tag=v1.0.0-staging \
    --set image.pullSecrets[0].name=ghcr-secret
  ```

- [ ] **Verificar deployment**
  ```bash
  kubectl get pods -n neural-hive-staging -l app=healer-mcp-server
  ```

### 4.9 Validacao MCP Servers

- [ ] **Verificar todos os MCP servers**
  ```bash
  kubectl get pods -n neural-hive-staging -l app.kubernetes.io/part-of=mcp-servers
  ```

- [ ] **Testar descoberta de servicos**
  ```bash
  kubectl exec -it deployment/queen-mcp-server -n neural-hive-staging -- \
    curl -X GET http://localhost:3012/mcp/services/list
  ```

---

## Parte 5: ML Inference API

### 5.1 ML Inference Service

- [ ] **Build e push imagem**
  ```bash
  cd services/ml-inference-api
  docker build -t ghcr.io/<owner>/ml-inference-api:v1.0.0-staging .
  docker push ghcr.io/<owner>/ml-inference-api:v1.0.0-staging
  ```

- [ ] **Deploy via Helm**
  ```bash
  helm install ml-inference-api services/ml-inference-api/helm/ml-inference-api/ \
    -n neural-hive-staging \
    --set image.repository=ghcr.io/<owner>/ml-inference-api \
    --set image.tag=v1.0.0-staging \
    --set image.pullSecrets[0].name=ghcr-secret \
    --set replicaCount=2 \
    --set autoscaling.enabled=true \
    --set autoscaling.minReplicas=2 \
    --set autoscaling.maxReplicas=10
  ```

- [ ] **Carregar modelo ML**
  ```bash
  # Copiar modelo treinado para MLflow
  kubectl exec -it deployment/ml-inference-api -n neural-hive-staging -- \
    python -c "import mlflow; mlflow.pyfunc.log_model('nhm_approval_model', model_path='/app/ml_models')"
  ```

- [ ] **Verificar deployment**
  ```bash
  kubectl get pods -n neural-hive-staging -l app=ml-inference-api
  kubectl logs -f deployment/ml-inference-api -n neural-hive-staging
  ```

- [ ] **Verificar HPA**
  ```bash
  kubectl get hpa -n neural-hive-staging
  ```

- [ ] **Testar predicao**
  ```bash
  kubectl exec -it deployment/ml-inference-api -n neural-hive-staging -- \
    curl -X POST http://localhost:8008/api/v1/predict \
    -H "Content-Type: application/json" \
    -d '{"features": {"confidence": 0.8, "risk": 0.2}}'
  ```

---

## Parte 6: Execution Ticket Service

### 6.1 Execution Ticket Service

- [ ] **Build e push imagem**
  ```bash
  cd services/execution-ticket-service
  docker build -t ghcr.io/<owner>/execution-ticket-service:v1.0.0-staging .
  docker push ghcr.io/<owner>/execution-ticket-service:v1.0.0-staging
  ```

- [ ] **Deploy via Helm** (criar Helm chart se necessario)
  ```bash
  # Se nao existe Helm chart, deploy via kubectl
  kubectl apply -f services/execution-ticket-service/k8s/deployment.yaml
  kubectl apply -f services/execution-ticket-service/k8s/service.yaml
  ```

- [ ] **Verificar deployment**
  ```bash
  kubectl get pods -n neural-hive-staging -l app=execution-ticket-service
  kubectl logs -f deployment/execution-ticket-service -n neural-hive-staging
  ```

- [ ] **Verificar gRPC endpoints**
  ```bash
  kubectl exec -it deployment/execution-ticket-service -n neural-hive-staging -- \
    grpcurl -plaintext localhost:50051 list
  ```

---

## Parte 7: Monitoring e Observabilidade

### 7.1 Prometheus

- [ ] **Deploy Prometheus**
  ```bash
  helm install prometheus prometheus-community/kube-prometheus-stack \
    -n neural-hive-monitoring --create-namespace \
    --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false
  ```

- [ ] **Configurar ServiceMonitors**
  ```bash
  kubectl apply -f k8s/monitoring/servicemonitors/
  ```

- [ ] **Verificar Prometheus**
  ```bash
  kubectl get pods -n neural-hive-monitoring -l app.kubernetes.io/name=prometheus
  kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n neural-hive-monitoring
  ```

### 7.2 Grafana

- [ ] **Importar dashboards**
  ```bash
  kubectl apply -f k8s/monitoring/grafana/dashboards/
  ```

- [ ] **Verificar Grafana**
  ```bash
  kubectl port-forward svc/prometheus-grafana 3000:3000 -n neural-hive-monitoring
  # Login: admin / prom-operator
  ```

- [ ] **Configurar datasource Prometheus**
  ```bash
  # Via UI Grafana: http://prometheus-kube-prometheus-prometheus:9090
  ```

### 7.3 Loki (Logging)

- [ ] **Deploy Loki**
  ```bash
  helm install loki grafana/loki-stack \
    -n neural-hive-monitoring \
    --set loki.persistence.enabled=true \
    --set loki.persistence.size=50Gi
  ```

- [ ] **Configurar Promtail**
  ```bash
  # Promtail instalado junto com loki-stack
  ```

---

## Parte 8: Ingress e Exposicao

### 8.1 NGINX Ingress

- [ ] **Install NGINX Ingress**
  ```bash
  helm install ingress-nginx ingress-nginx/ingress-nginx \
    -n ingress-nginx --create-namespace
  ```

- [ ] **Aplicar ingress rules**
  ```bash
  kubectl apply -f k8s/ingress/
  ```

- [ ] **Configurar SSL/TLS**
  ```bash
  kubectl apply -f k8s/ingress/tls/
  ```

- [ ] **Verificar ingress**
  ```bash
  kubectl get ingress -n neural-hive-staging
  kubectl describe ingress <ingress-name> -n neural-hive-staging
  ```

---

## Parte 9: Comandos de Verificacao Pos-Deploy

### 9.1 Verificacao Geral

- [ ] **Todos os pods running**
  ```bash
  kubectl get pods -n neural-hive-staging
  ```

- [ ] **Todos os deployments ready**
  ```bash
  kubectl get deployments -n neural-hive-staging
  ```

- [ ] **Servicos expostos**
  ```bash
  kubectl get svc -n neural-hive-staging
  ```

- [ ] **HPA funcionando**
  ```bash
  kubectl get hpa -n neural-hive-staging
  ```

### 9.2 Health Checks

- [ ] **Gateway de Intencoes**
  ```bash
  kubectl exec -it deployment/gateway-intencoes -n neural-hive-staging -- \
    curl http://localhost:8000/health
  ```

- [ ] **Semantic Translation Engine**
  ```bash
  kubectl exec -it deployment/semantic-translation-engine -n neural-hive-staging -- \
    curl http://localhost:8001/health
  ```

- [ ] **Consensus Engine**
  ```bash
  kubectl exec -it deployment/consensus-engine -n neural-hive-staging -- \
    curl http://localhost:8002/health
  ```

- [ ] **Orchestrator Dynamic**
  ```bash
  kubectl exec -it deployment/orchestrator-dynamic -n neural-hive-staging -- \
    curl http://localhost:8003/health
  ```

- [ ] **Approval Service**
  ```bash
  kubectl exec -it deployment/approval-service -n neural-hive-staging -- \
    curl http://localhost:8004/health
  ```

- [ ] **Queen Agent**
  ```bash
  kubectl exec -it deployment/queen-agent -n neural-hive-staging -- \
    curl http://localhost:8006/health
  ```

### 9.3 Testes de Conectividade

- [ ] **Testar conexao Kafka**
  ```bash
  kubectl exec -it deployment/gateway-intencoes -n neural-hive-staging -- \
    python -c "import socket; print(socket.gethostbyname('kafka.neural-hive-infra.svc.cluster.local'))"
  ```

- [ ] **Testar conexao MongoDB**
  ```bash
  kubectl exec -it deployment/consensus-engine -n neural-hive-staging -- \
    python -c "from pymongo import MongoClient; print(MongoClient('<mongo-uri>').server_info())"
  ```

- [ ] **Testar conexao Redis**
  ```bash
  kubectl exec -it deployment/gateway-intencoes -n neural-hive-staging -- \
    python -c "import redis; r=redis.from_url('<redis-url>'); print(r.ping())"
  ```

### 9.4 Teste E2E

- [ ] **Enviar intent completo**
  ```bash
  kubectl port-forward svc/gateway-intencoes 8000:8000 -n neural-hive-staging
  curl -X POST http://localhost:8000/api/v1/intent \
    -H "Content-Type: application/json" \
    -H "X-API-Key: <test-api-key>" \
    -d '{
      "text": "Analisar dados de vendas do ultimo trimestre",
      "user_id": "test-user-001",
      "session_id": "test-session-001"
    }'
  ```

- [ ] **Verificar resposta**
  ```bash
  # Guardar o request_id e verificar status
  curl -X GET http://localhost:8000/api/v1/intent/<request_id>/status \
    -H "X-API-Key: <test-api-key>"
  ```

---

## Parte 10: Comandos de Rollback

### 10.1 Rollback de Servico Individual

- [ ] **Ver historico de revisions**
  ```bash
  kubectl rollout history deployment/gateway-intencoes -n neural-hive-staging
  ```

- [ ] **Rollback para versao anterior**
  ```bash
  kubectl rollout undo deployment/gateway-intencoes -n neural-hive-staging
  ```

- [ ] **Rollback para revision especifica**
  ```bash
  kubectl rollout undo deployment/gateway-intencoes --to-revision=3 -n neural-hive-staging
  ```

- [ ] **Verificar status**
  ```bash
  kubectl rollout status deployment/gateway-intencoes -n neural-hive-staging
  ```

### 10.2 Rollback via Helm

- [ ] **Listar releases**
  ```bash
  helm list -n neural-hive-staging
  ```

- [ ] **Ver historico de releases**
  ```bash
  helm history queen-mcp-server -n neural-hive-staging
  ```

- [ ] **Rollback Helm**
  ```bash
  helm rollback queen-mcp-server -n neural-hive-staging
  ```

- [ ] **Rollback para revisao especifica**
  ```bash
  helm rollback queen-mcp-server 2 -n neural-hive-staging
  ```

### 10.3 Rollback Completo (Emergencia)

- [ ] **Script de rollback completo**
  ```bash
  #!/bin/bash
  SERVICES=(
    "queen-mcp-server"
    "execution-mcp-server"
    "architect-mcp-server"
    "analyst-mcp-server"
    "guard-mcp-server"
    "code-forge-mcp-server"
    "worker-mcp-server"
    "healer-mcp-server"
    "ml-inference-api"
    "execution-ticket-service"
  )

  for svc in "${SERVICES[@]}"; do
    echo "Rolling back $svc..."
    helm rollback $svc -n neural-hive-staging || echo "Failed to rollback $svc"
  done

  kubectl wait --for=condition=available deployment --all -n neural-hive-staging --timeout=600s
  ```

- [ ] **Rollback de emergencia (escalar para zero)**
  ```bash
  kubectl scale deployment --all -n neural-hive-staging --replicas=0
  # Aguardar investigacao
  kubectl scale deployment --all -n neural-hive-staging --replicas=1
  ```

### 10.4 Rollback de Imagem

- [ ] **Forcar rollback de imagem**
  ```bash
  kubectl set image deployment/queen-mcp-server \
    queen-mcp-server=ghcr.io/<owner>/queen-mcp-server:v0.9.0-staging \
    -n neural-hive-staging
  ```

---

## Parte 11: Testes de Aceitacao

### 11.1 Testes de Saude

- [ ] **Health check de todos os servicos**
  ```bash
  #!/bin/bash
  SERVICES=("gateway-intencoes" "semantic-translation-engine" "consensus-engine" 
            "orchestrator-dynamic" "queen-agent" "approval-service" "ml-inference-api")
  PORTS=(8000 8001 8002 8003 8006 8004 8008)

  for i in "${!SERVICES[@]}"; do
    svc="${SERVICES[$i]}"
    port="${PORTS[$i]}"
    echo "Checking $svc on port $port..."
    kubectl exec -it deployment/$svc -n neural-hive-staging -- \
      curl -f http://localhost:$port/health || echo "FAILED: $svc"
  done
  ```

### 11.2 Testes de Performance

- [ ] **Load test no gateway**
  ```bash
  # Instalar k6 ou usar hey
  kubectl run -i --tty load-test --image=ricoli/hey --rm --restart=Never -- \
    -n 100 -c 10 -m POST \
    -H "Content-Type: application/json" \
    -H "X-API-Key: <test-api-key>" \
    -d '{"text":"test intent","user_id":"load-test"}' \
    http://gateway-intencoes.neural-hive-staging.svc.cluster.local:8000/api/v1/intent
  ```

### 11.3 Testes de Integração

- [ ] **Executar testes E2E**
  ```bash
  pytest tests/e2e/ -v -m e2e --base-url=http://<staging-url>
  ```

- [ ] **Verificar metricas no Prometheus**
  ```bash
  kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n neural-hive-monitoring
  # Acessar http://localhost:9090 e verificar queries:
  # - up{job="neural-hive"}
  # - rate(http_requests_total[5m])
  # - pipeline_latency_seconds
  ```

---

## Parte 12: Checklist Final

### 12.1 Pre-Go-Live

- [ ] Todos os pods em estado Running
- [ ] Todos os deployments com replicas ready
- [ ] Zero pods em CrashLoopBackOff
- [ ] Zero pods com status Error
- [ ] Logs sem erros criticos
- [ ] Health checks retornando 200
- [ ] Metricas visiveis no Grafana
- [ ] Alertas configurados
- [ ] Ingress funcionando
- [ ] SSL/TLS valido
- [ ] Testes E2E passando
- [ ] Documentacao atualizada

### 12.2 Documentacao

- [ ] Atualizar runbooks
- [ ] Atualizar diagramas de arquitetura
- [ ] Documentar procedimentos de rollback
- [ ] Documentar procedimentos de escalamento
- [ ] Criar pagina de status (status page)
- [ ] Configurar notificacoes (Slack/Email)

---

## Apêndice A: Comandos de Diagnostico

```bash
# Ver pods com problemas
kubectl get pods -n neural-hive-staging --field-selector=status.phase!=Running

# Ver eventos recentes
kubectl get events -n neural-hive-staging --sort-by=.metadata.creationTimestamp | tail -20

# Ver resource usage
kubectl top pods -n neural-hive-staging
kubectl top nodes

# Descrever pod com erro
kubectl describe pod <pod-name> -n neural-hive-staging

# Logs de pod com crash (container anterior)
kubectl logs <pod-name> -n neural-hive-staging --previous

# Ver PVCs
kubectl get pvc -n neural-hive-staging

# Ver configmaps
kubectl get configmaps -n neural-hive-staging

# Ver secrets
kubectl get secrets -n neural-hive-staging
```

---

## Apêndice B: Links Úteis

- **Dashboard Grafana:** http://grafana.<staging-domain>
- **Prometheus:** http://prometheus.<staging-domain>
- **Kubernetes Dashboard:** https://k8s.<staging-domain>
- **API Gateway:** https://api.<staging-domain>
- **MLflow:** http://mlflow.<staging-domain>

---

**Documento v1.0 - 2026-04-04**
**Proximo passo:** Executar deploy em ordem sequencial conforme checklist.
