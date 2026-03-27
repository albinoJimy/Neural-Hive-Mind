# Plano de Deploy Completo - Fase 1

## Status Atual

### ✅ Componentes Deployados e Funcionais
1. **Specialists (5/5)**
   - specialist-business
   - specialist-behavior
   - specialist-evolution
   - specialist-architecture
   - specialist-technical

2. **Gateway**
   - gateway-intencoes

3. **Infraestrutura**
   - MongoDB (mongodb-cluster)
   - Redis (redis-cluster)
   - Neo4j (neo4j-cluster)
   - Kafka (kafka namespace)

### ❌ Componentes Faltantes
1. **semantic-translation-engine** - Motor de Tradução Semântica
2. **consensus-engine** - Motor de Consenso
3. **memory-layer-api** - API de Camada de Memória

## Pré-requisitos Verificados

- ✅ Cluster Kubernetes operacional
- ✅ MongoDB rodando: `mongodb.mongodb-cluster.svc.cluster.local:27017`
- ✅ Redis rodando: `neural-hive-cache.redis-cluster.svc.cluster.local:6379`
- ✅ Neo4j rodando: `neo4j.neo4j-cluster.svc.cluster.local:7687`
- ✅ Kafka rodando: `neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092`
- ✅ Helm charts disponíveis para todos componentes
- ✅ Dockerfiles disponíveis para todos componentes

## Passos para Completar a Fase 1

### Opção 1: Build Local e Deploy Manual

#### 1. Construir Imagens Docker

```bash
# Semantic Translation Engine
docker build -t neural-hive-mind/semantic-translation-engine:1.0.0 \
  -f services/semantic-translation-engine/Dockerfile .

# Consensus Engine
docker build -t neural-hive-mind/consensus-engine:1.0.0 \
  -f services/consensus-engine/Dockerfile .

# Memory Layer API
docker build -t neural-hive-mind/memory-layer-api:1.0.0 \
  -f services/memory-layer-api/Dockerfile .
```

#### 2. Carregar Imagens no Cluster

Se usando Minikube:
```bash
eval $(minikube docker-env)
# Re-executar os builds acima
```

Se usando cluster remoto, fazer push para registry:
```bash
# Tag e push para registry
docker tag neural-hive-mind/semantic-translation-engine:1.0.0 <registry>/semantic-translation-engine:1.0.0
docker push <registry>/semantic-translation-engine:1.0.0
# Repetir para os outros componentes
```

#### 3. Deploy via Helm

```bash
# Deploy usando script criado
./deploy-fase1-componentes-faltantes.sh
```

### Opção 2: Usar Script de Build Existente

```bash
# Verificar se há script de build para todos componentes
ls scripts/build/ | grep -E "(semantic|consensus|memory)"

# Se existir, executar build script e depois deploy
```

## Configurações Importantes

### Semantic Translation Engine
- **Porta**: 8000 (HTTP/REST)
- **Namespace**: semantic-translation-engine
- **Dependências**:
  - Kafka (input: intentions.*, output: plans.ready)
  - Neo4j (knowledge graph)
  - MongoDB (context & ledger)
  - Redis (cache)

### Consensus Engine  
- **Porta**: 8000 (HTTP/REST)
- **Namespace**: consensus-engine
- **Dependências**:
  - Kafka (input: specialists.opinions.*, output: decisions.*)
  - MongoDB (decision logs)
  - Redis (cache)

### Memory Layer API
- **Porta**: 8000 (HTTP/REST)
- **Namespace**: memory-layer-api
- **Dependências**:
  - Neo4j (graph database)
  - MongoDB (document store)
  - Redis (cache)

## Validação Pós-Deploy

### 1. Verificar Pods
```bash
kubectl get pods -n semantic-translation-engine
kubectl get pods -n consensus-engine
kubectl get pods -n memory-layer-api
```

### 2. Verificar Logs
```bash
kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine
kubectl logs -n memory-layer-api -l app.kubernetes.io/name=memory-layer-api
```

### 3. Testar Health Endpoints
```bash
# Via port-forward
kubectl port-forward -n semantic-translation-engine svc/semantic-translation-engine 8000:8000 &
curl http://localhost:8000/health

kubectl port-forward -n consensus-engine svc/consensus-engine 8001:8000 &
curl http://localhost:8001/health

kubectl port-forward -n memory-layer-api svc/memory-layer-api 8002:8000 &
curl http://localhost:8002/health
```

### 4. Executar Teste End-to-End
```bash
./tests/phase1-end-to-end-test.sh --continue-on-error
```

## Problemas Esperados e Soluções

### Problema: Imagens não encontradas
**Solução**: Construir imagens localmente ou ajustar imagePullPolicy

### Problema: Pod em CrashLoopBackOff
**Solução**: 
1. Verificar logs: `kubectl logs -n <namespace> <pod>`
2. Verificar conectividade com dependências
3. Validar secrets e configmaps

### Problema: Health check falhando
**Solução**:
1. Verificar se o serviço está ouvindo na porta correta
2. Verificar logs de inicialização
3. Validar configurações de ambiente

## Próximos Passos Após Deploy

1. ✅ Validar conectividade entre todos componentes
2. ✅ Executar teste end-to-end completo
3. ✅ Verificar métricas e observabilidade
4. ✅ Documentar arquitetura final deployada
5. ➡️ Iniciar Fase 2 (Orchestrator, Agents, etc.)

---

**Script Criado**: `deploy-fase1-componentes-faltantes.sh`  
**Documentação**: `COMANDOS_UTEIS.md`
