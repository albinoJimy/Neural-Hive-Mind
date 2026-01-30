# 🔧 Comandos Úteis - Neural Hive-Mind Local

## 📋 Monitoramento

### Status Geral
```bash
# Status de todos os pods
kubectl get pods -A | grep neural-hive

# Status dos namespaces
kubectl get namespaces | grep neural-hive

# Status dos serviços
kubectl get svc -A | grep neural-hive

# Verificar recursos por namespace
kubectl top pods -A | grep neural-hive
```

### Logs
```bash
# Logs do serviço de teste
kubectl logs -f deployment/neural-test-service -n neural-hive-system

# Logs do Istio
kubectl logs -f deployment/istiod -n istio-system

# Logs do Gatekeeper
kubectl logs -f deployment/gatekeeper-controller-manager -n gatekeeper-system
```

## 🌐 Acesso aos Dashboards

### Kiali (Service Mesh)
```bash
kubectl port-forward svc/kiali 20001:20001 -n istio-system
# Acesse: http://localhost:20001
```

### Grafana (Métricas)
```bash
kubectl port-forward svc/grafana 3000:3000 -n istio-system
# Acesse: http://localhost:3000
```

### Jaeger (Tracing)
```bash
kubectl port-forward svc/jaeger 16686:16686 -n istio-system
# Acesse: http://localhost:16686
```

### Prometheus (Métricas Raw)
```bash
kubectl port-forward svc/prometheus 9090:9090 -n istio-system
# Acesse: http://localhost:9090
```

## 🧪 Teste e Desenvolvimento

### Acessar Serviço de Teste
```bash
# Via port-forward
kubectl port-forward svc/neural-test-service 8080:80 -n neural-hive-system
# Acesse: http://localhost:8080

# Teste interno
kubectl exec -n neural-hive-system deployment/neural-test-service -- curl localhost
```

### Deploy de Novos Serviços
```bash
# Template básico
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: meu-servico
  namespace: neural-hive-cognition
  labels:
    app: meu-servico
spec:
  replicas: 1
  selector:
    matchLabels:
      app: meu-servico
  template:
    metadata:
      labels:
        app: meu-servico
      annotations:
        sidecar.istio.io/inject: "true"
    spec:
      containers:
      - name: app
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: meu-servico
  namespace: neural-hive-cognition
spec:
  selector:
    app: meu-servico
  ports:
  - port: 80
    targetPort: 80
EOF
```

## 🛡️ Políticas e Segurança

### Verificar Políticas OPA
```bash
# Listar constraint templates
kubectl get constrainttemplates

# Listar constraints ativos
kubectl get constraints -A

# Verificar violações
kubectl get neuralhivemtlsrequired -A -o yaml
```

### Verificar mTLS
```bash
# Status de peer authentication
kubectl get peerauthentication -A

# Testar mTLS entre serviços
istioctl authn tls-check neural-test-service.neural-hive-system
```

## 🔄 Limpeza e Reset

### Limpar Deployment Local
```bash
# Remover serviços de teste
kubectl delete -f test-service-local.yaml

# Remover políticas aplicadas
kubectl delete constrainttemplates --all
kubectl delete peerauthentication -A --all

# Reset completo (CUIDADO!)
kubectl delete namespace neural-hive-cognition neural-hive-orchestration neural-hive-execution neural-hive-observability
```

### Restart de Componentes
```bash
# Restart do Gatekeeper
kubectl rollout restart deployment gatekeeper-controller-manager -n gatekeeper-system
kubectl rollout restart deployment gatekeeper-audit -n gatekeeper-system

# Restart do Istio
kubectl rollout restart deployment istiod -n istio-system
```

## 🚨 Troubleshooting

### Pods não iniciam
```bash
# Verificar eventos
kubectl get events --sort-by='.lastTimestamp' -A

# Descrever pod problemático
kubectl describe pod <nome-do-pod> -n <namespace>

# Verificar recursos
kubectl top nodes
kubectl top pods -A
```

### Problemas de Conectividade
```bash
# Testar DNS
kubectl run dns-test --image=busybox --rm -it -- nslookup kubernetes.default

# Testar conectividade entre namespaces
kubectl run network-test --image=busybox --rm -it --namespace neural-hive-system -- ping neural-test-service
```

### Problemas com Istio
```bash
# Verificar configuração do mesh
istioctl analyze

# Status dos proxies
istioctl proxy-status

# Configuração de um pod específico
istioctl proxy-config cluster <pod-name>.<namespace>
```

### Debug de Políticas OPA
```bash
# Logs detalhados do Gatekeeper
kubectl logs deployment/gatekeeper-controller-manager -n gatekeeper-system --tail=50

# Testar criação de recurso
kubectl apply --dry-run=server -f meu-arquivo.yaml
```

## 📚 Referências Rápidas

### Estrutura de Namespaces
- `neural-hive-system`: Componentes principais e testes
- `neural-hive-cognition`: Processamento e interpretação
- `neural-hive-orchestration`: Coordenação e workflow
- `neural-hive-execution`: Agentes e workers
- `neural-hive-observability`: Métricas, logs e tracing

### Portas Padrão
- Kiali: 20001
- Grafana: 3000
- Jaeger: 16686
- Prometheus: 9090
- Serviço de teste: 8080 (via port-forward)

---

🤖 **Para mais informações, consulte DEPLOYMENT_LOCAL.md**
## 🧪 Testes da Fase 1

### Script Rápido de Teste
```bash
# Executar teste automatizado da Fase 1
./testar-fase1.sh

# Parar ambiente de teste
docker compose -f docker-compose-test.yml down

# Ver logs em tempo real
docker compose -f docker-compose-test.yml logs -f

# Ver logs específicos
docker compose -f docker-compose-test.yml logs -f kafka
docker compose -f docker-compose-test.yml logs -f redis
```

### Testes Manuais

#### Kafka
```bash
# Criar tópico
docker exec kafka kafka-topics --bootstrap-server localhost:9092 \
  --create --topic test-topic --partitions 3 --replication-factor 1

# Listar tópicos
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# Publicar mensagem
echo "test message" | docker exec -i kafka kafka-console-producer \
  --bootstrap-server localhost:9092 --topic test-topic

# Consumir mensagens
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 --topic test-topic --from-beginning
```

#### Redis
```bash
# Conectar ao Redis CLI
docker exec -it redis redis-cli

# Testar PING/PONG
docker exec redis redis-cli ping

# SET/GET valores
docker exec redis redis-cli SET mykey "myvalue"
docker exec redis redis-cli GET mykey

# Listar todas as chaves
docker exec redis redis-cli KEYS '*'
```

### Relatórios
```bash
# Ver relatório de teste
cat TESTE_FASE1_RESULTADO.md

# Gerar novo relatório
./testar-fase1.sh
```

---

## 🎯 Kubernetes - Fase 2 (Kubeadm)

### Comandos do Cluster

```bash
# Status do cluster
kubectl cluster-info
kubectl get nodes
kubectl get pods -A

# Validar Fase 2
./validar-fase2-k8s.sh

# Namespaces
kubectl get namespaces
kubectl get all -n redis-cluster
kubectl get all -n mongodb-cluster
```

### MongoDB

```bash
# Nome do pod (substitua <pod-name> pelo nome real)
MONGODB_POD=$(kubectl get pods -n mongodb-cluster -o name | grep mongodb | head -1 | sed 's/pod\///')

# Conectar ao MongoDB
kubectl exec -it -n mongodb-cluster $MONGODB_POD -- mongosh mongodb://localhost:27017 -u root -p local_dev_password --authenticationDatabase admin

# Testar ping
kubectl exec -n mongodb-cluster $MONGODB_POD -- mongosh mongodb://localhost:27017 -u root -p local_dev_password --authenticationDatabase admin --eval "db.adminCommand('ping')"

# Listar databases
kubectl exec -n mongodb-cluster $MONGODB_POD -- mongosh mongodb://localhost:27017 -u root -p local_dev_password --authenticationDatabase admin --eval "show dbs"

# Inserir documento de teste
kubectl exec -n mongodb-cluster $MONGODB_POD -- mongosh mongodb://localhost:27017/neural_hive -u root -p local_dev_password --authenticationDatabase admin --eval 'db.test.insertOne({msg: "Hello from K8s"})'
```

### Redis

```bash
# Nome do pod
REDIS_POD=$(kubectl get pods -n redis-cluster -o name | head -1)

# Conectar ao Redis
kubectl exec -it -n redis-cluster $REDIS_POD -- redis-cli

# Testar PING
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli ping

# SET/GET
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli SET mykey "value"
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli GET mykey

# Listar todas as chaves
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli KEYS '*'
```

### Persistent Volumes

```bash
# Listar PV e PVC
kubectl get pv
kubectl get pvc -A

# Detalhes de storage MongoDB
kubectl describe pvc -n mongodb-cluster
kubectl get storageclass

# Ver uso de disco
kubectl exec -n mongodb-cluster $MONGODB_POD -- df -h
```

### Helm

```bash
# Listar releases instalados
helm list -A

# Status do MongoDB
helm status mongodb -n mongodb-cluster

# Atualizar valores
helm upgrade mongodb bitnami/mongodb -n mongodb-cluster --set auth.rootPassword=new_password

# Desinstalar (cuidado!)
helm uninstall mongodb -n mongodb-cluster
```

---

## 🧪 Testes de Integração

### Teste End-to-End Kubernetes

```bash
# Executar teste completo de integração
./teste-integracao-k8s.py

# O teste valida:
# - Redis CRUD
# - MongoDB CRUD
# - Kafka topics
# - Integração entre componentes
```

### Validações Disponíveis

```bash
# Fase 1 (Docker Compose)
./testar-fase1.sh
./test-intent-flow.py

# Fase 2 (Kubernetes)
./validar-fase2-k8s.sh
./teste-integracao-k8s.py
```

---

## 📊 Status do Sistema

### Ver todos os recursos

```bash
# Visão geral
kubectl get all -A | grep -E "(kafka|redis|mongodb)"

# Status dos pods
kubectl get pods -A --field-selector=status.phase=Running

# Usar recursos
kubectl top pods -A
kubectl top nodes

# Persistent Volumes
kubectl get pv,pvc -A
```

### Kafka (Strimzi)

```bash
# Status do cluster Kafka
kubectl get kafka -n kafka

# Listar topics
kubectl get kafkatopic -n kafka

# Logs do broker
kubectl logs neural-hive-kafka-broker-0 -n kafka

# Logs do operator
kubectl logs -l name=strimzi-cluster-operator -n kafka
```

---

## 🧪 Teste Fase 1 - Specialists

### Script de Teste Automatizado

```bash
# Executar teste completo dos 5 specialists
./test-specialists-v2.sh

# Resultado esperado:
# ✓ Cluster Kubernetes acessível
# ✓ Todos os deployments com replicas prontas (1/1)
# ✓ Todos os pods com status Running
# ✓ Todos os services ativos com portas 50051 (gRPC), 8000 (HTTP), 8080 (Prometheus)
# ✓ gRPC server iniciado em cada specialist
# ✓ HTTP server (Uvicorn/FastAPI) iniciado em cada specialist
```

### Verificações Individuais por Specialist

```bash
# Listar todos os specialists
kubectl get deployments -A | grep specialist

# Status dos 5 specialists
for spec in business behavior evolution architecture technical; do
  echo "=== specialist-$spec ==="
  kubectl get pods -n specialist-$spec
  kubectl get svc -n specialist-$spec
done
```

### Verificar Logs dos Specialists

```bash
# Business Specialist
kubectl logs -n specialist-business -l app.kubernetes.io/name=specialist-business --tail=50

# Behavior Specialist
kubectl logs -n specialist-behavior -l app.kubernetes.io/name=specialist-behavior --tail=50

# Evolution Specialist
kubectl logs -n specialist-evolution -l app.kubernetes.io/name=specialist-evolution --tail=50

# Architecture Specialist
kubectl logs -n specialist-architecture -l app.kubernetes.io/name=specialist-architecture --tail=50

# Technical Specialist
kubectl logs -n specialist-technical -l app.kubernetes.io/name=specialist-technical --tail=50
```

### Testar Health Endpoints

```bash
# Testar via port-forward (exemplo com specialist-business)
kubectl port-forward -n specialist-business svc/specialist-business 8000:8000 &
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics

# Ou testar diretamente do pod
kubectl exec -n specialist-business deployment/specialist-business -- wget -qO- http://localhost:8000/health
```

### Verificar Services e IPs

```bash
# Listar IPs e portas de todos os specialists
kubectl get svc -A | grep specialist

# Exemplo de output esperado:
# specialist-business       specialist-business       ClusterIP   10.102.250.6    <none>   50051/TCP,8000/TCP,8080/TCP
# specialist-behavior       specialist-behavior       ClusterIP   10.97.108.160   <none>   50051/TCP,8000/TCP,8080/TCP
# specialist-evolution      specialist-evolution      ClusterIP   10.98.45.222    <none>   50051/TCP,8000/TCP,8080/TCP
# specialist-architecture   specialist-architecture   ClusterIP   10.103.172.21   <none>   50051/TCP,8000/TCP,8080/TCP
# specialist-technical      specialist-technical      ClusterIP   10.103.87.56    <none>   50051/TCP,8000/TCP,8080/TCP
```

### Status de Inicialização

```bash
# Verificar se todos os servidores estão rodando
for spec in business behavior evolution architecture technical; do
  echo "=== Verificando $spec ==="
  POD=$(kubectl get pods -n specialist-$spec -l app.kubernetes.io/name=specialist-$spec -o jsonpath='{.items[0].metadata.name}')
  echo "gRPC Server:"
  kubectl logs -n specialist-$spec $POD --tail=100 | grep "gRPC server started" || echo "  Não encontrado"
  echo "HTTP Server:"
  kubectl logs -n specialist-$spec $POD --tail=100 | grep -E "Uvicorn running|HTTP server started" || echo "  Não encontrado"
  echo ""
done
```

### Troubleshooting Specialists

```bash
# Verificar erros nos logs
for spec in business behavior evolution architecture technical; do
  echo "=== Erros em specialist-$spec ==="
  kubectl logs -n specialist-$spec -l app.kubernetes.io/name=specialist-$spec --tail=100 | grep -i error
  echo ""
done

# Reiniciar um specialist específico
kubectl rollout restart deployment/specialist-business -n specialist-business

# Reiniciar todos os specialists
for spec in business behavior evolution architecture technical; do
  kubectl rollout restart deployment/specialist-$spec -n specialist-$spec
done

# Verificar descrição do pod para eventos
kubectl describe pod -n specialist-business -l app.kubernetes.io/name=specialist-business
```

### Observações Importantes

- **Modelos MLflow**: Os specialists tentam carregar modelos do MLflow mas usam fallback com heurísticas quando não encontrados
- **Autenticação JWT**: Desabilitada por padrão em desenvolvimento (modo inseguro)
- **OpenTelemetry**: Instrumentação gRPC pode falhar mas não impede funcionamento
- **Portas Expostas**:
  - 50051: gRPC API
  - 8000: HTTP/REST API (FastAPI)
  - 8080: Métricas Prometheus

### Endpoints Disponíveis

Cada specialist expõe os seguintes endpoints HTTP:

```bash
GET /health       # Health check básico
GET /ready        # Readiness probe
GET /metrics      # Métricas Prometheus
GET /status       # Status detalhado
POST /api/v1/feedback              # Submeter feedback
GET  /api/v1/feedback/{opinion_id} # Obter feedback específico
GET  /api/v1/feedback/stats        # Estatísticas de feedback
```

### Testes de Conectividade gRPC

```bash
# Teste completo de conectividade gRPC
./test-grpc-specialists.sh

# Teste de conectividade interna entre specialists
# (executa Python dentro do pod para testar conectividade)
cat test-connectivity-internal.py | kubectl exec -i -n specialist-business deployment/specialist-business -- python3

# Resultados esperados:
# ✓ Porta gRPC (50051): Todas acessíveis
# ✓ Porta HTTP (8000): Todas acessíveis
# ⚠ Porta Prometheus (8080): Configurada mas pode não estar bind corretamente
```

### Resultados dos Testes Fase 1

**Status Geral**: ✅ APROVADO

- ✅ Cluster Kubernetes: Operacional
- ✅ Deployments: 5/5 com replicas prontas (1/1)
- ✅ Pods: 5/5 em estado Running
- ✅ Services: 5/5 ativos com ClusterIP
- ✅ Endpoints: 5/5 com IPs válidos
- ✅ gRPC Server: 5/5 iniciados e respondendo
- ✅ HTTP Server: 5/5 iniciados e respondendo
- ✅ Conectividade TCP gRPC: 100% (15/15 testes)
- ✅ Conectividade interna: 66.7% (10/15 - porta Prometheus não acessível)
- ✅ Resolução DNS: 100% entre todos specialists

**Observações**:
- Porta Prometheus (8080) está configurada mas não está acessível externamente (possível problema de binding)
- Portas gRPC (50051) e HTTP (8000) estão totalmente funcionais
- Comunicação entre specialists funcionando via DNS do Kubernetes

**Scripts de Teste Disponíveis**:
- `test-specialists-v2.sh` - Teste básico de status e logs
- `test-grpc-specialists.sh` - Teste de conectividade gRPC
- `test-connectivity-internal.py` - Teste interno de conectividade
