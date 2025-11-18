# 🚀 Guia Rápido - Completar Fase 1

## Status Atual ✅

- ✅ 5 Specialists operacionais (business, behavior, evolution, architecture, technical)
- ✅ Gateway Intenções funcionando
- ✅ Infraestrutura completa (MongoDB, Redis, Neo4j, Kafka)
- ❌ 3 Componentes faltantes (semantic-translation-engine, consensus-engine, memory-layer-api)

## Passos para Completar

### 1️⃣ Build das Imagens Docker

```bash
# Build automático dos 3 componentes faltantes
./build-fase1-componentes.sh

# Ou manualmente:
docker build -t neural-hive-mind/semantic-translation-engine:1.0.0 \
  -f services/semantic-translation-engine/Dockerfile .

docker build -t neural-hive-mind/consensus-engine:1.0.0 \
  -f services/consensus-engine/Dockerfile .

docker build -t neural-hive-mind/memory-layer-api:1.0.0 \
  -f services/memory-layer-api/Dockerfile .
```

**Tempo estimado**: 5-15 minutos

### 2️⃣ Deploy no Kubernetes

```bash
# Deploy automático usando Helm
./deploy-fase1-componentes-faltantes.sh
```

**Tempo estimado**: 2-5 minutos

### 3️⃣ Validação

```bash
# Verificar pods
kubectl get pods -n semantic-translation-engine
kubectl get pods -n consensus-engine
kubectl get pods -n memory-layer-api

# Verificar logs
kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine
kubectl logs -n memory-layer-api -l app.kubernetes.io/name=memory-layer-api

# Testar health endpoints
kubectl port-forward -n semantic-translation-engine svc/semantic-translation-engine 8000:8000 &
curl http://localhost:8000/health
```

### 4️⃣ Teste End-to-End

```bash
# Executar teste completo da Fase 1
./tests/phase1-end-to-end-test.sh --continue-on-error
```

**Tempo estimado**: 2-5 minutos

## Testes Já Disponíveis

### Testes dos Specialists ✅
```bash
# Teste básico
./test-specialists-v2.sh

# Teste de conectividade gRPC
./test-grpc-specialists.sh

# Teste de conectividade interna
cat test-connectivity-internal.py | kubectl exec -i -n specialist-business deployment/specialist-business -- python3
```

## Troubleshooting

### Problema: Build falhando

```bash
# Ver logs detalhados
cat /tmp/build-semantic-translation-engine.log
cat /tmp/build-consensus-engine.log
cat /tmp/build-memory-layer-api.log

# Verificar dependências Python
ls libraries/python/neural_hive_specialists/
```

### Problema: Pod em CrashLoopBackOff

```bash
# Ver logs do pod
kubectl logs -n <namespace> <pod-name>

# Descrever pod para ver eventos
kubectl describe pod -n <namespace> <pod-name>

# Verificar conectividade com dependências
kubectl exec -n <namespace> <pod-name> -- ping mongodb.mongodb-cluster.svc.cluster.local
```

### Problema: ImagePullBackOff

```bash
# Se usando Minikube, reconstruir com daemon correto
eval $(minikube docker-env)
./build-fase1-componentes.sh

# Verificar imagePullPolicy nos values
grep pullPolicy helm-charts/*/values-local.yaml
```

## Arquitetura da Fase 1

```
┌─────────────────────────────────────────────────────────────┐
│                      Gateway Intenções                       │
│                       (port 8000)                            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│           Semantic Translation Engine (STE)                  │
│  Recebe: Intenções de usuário                               │
│  Produz: Planos cognitivos                                  │
│  Kafka Topics: intentions.* → plans.ready                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    5 Specialists                             │
│  • Business      • Behavior      • Evolution                 │
│  • Architecture  • Technical                                 │
│  Avaliam planos e geram opiniões especializadas             │
│  gRPC: port 50051 | HTTP: port 8000                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Consensus Engine                            │
│  Recebe: Opiniões dos specialists                           │
│  Produz: Decisões consolidadas                              │
│  Kafka Topics: specialists.opinions.* → decisions.*         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Memory Layer API                            │
│  Persiste: Contexto e histórico                             │
│  Neo4j: Knowledge Graph                                      │
│  MongoDB: Ledger & Documents                                 │
└─────────────────────────────────────────────────────────────┘
```

## Dependências de Cada Componente

### Semantic Translation Engine
- **Kafka**: neural-hive-kafka-kafka-bootstrap.kafka:9092
- **Neo4j**: neo4j.neo4j-cluster:7687
- **MongoDB**: mongodb.mongodb-cluster:27017
- **Redis**: neural-hive-cache.redis-cluster:6379

### Consensus Engine
- **Kafka**: neural-hive-kafka-kafka-bootstrap.kafka:9092
- **MongoDB**: mongodb.mongodb-cluster:27017
- **Redis**: neural-hive-cache.redis-cluster:6379

### Memory Layer API
- **Neo4j**: neo4j.neo4j-cluster:7687
- **MongoDB**: mongodb.mongodb-cluster:27017
- **Redis**: neural-hive-cache.redis-cluster:6379

## Checklist Final

- [ ] Build das 3 imagens Docker concluído
- [ ] Deploy dos 3 componentes no Kubernetes
- [ ] Pods dos 3 componentes em estado Running
- [ ] Health endpoints respondendo (200 OK)
- [ ] Teste end-to-end passando
- [ ] Logs sem erros críticos

## Próximos Passos (Fase 2)

Após completar a Fase 1:
1. Deploy do Orchestrator Dynamic
2. Deploy dos Agent Workers (Analyst, Optimizer, Queen)
3. Deploy do Execution Ticket Service
4. Integração completa end-to-end

---

**Documentação Completa**: [COMANDOS_UTEIS.md](COMANDOS_UTEIS.md)
**Resultados dos Testes**: [RESULTADO_TESTE_FASE1.md](RESULTADO_TESTE_FASE1.md)
**Plano Detalhado**: [PLANO_DEPLOY_FASE1_COMPLETO.md](PLANO_DEPLOY_FASE1_COMPLETO.md)
