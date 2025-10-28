# Guia Operacional - Motor de Tradução Semântica

## 📋 Visão Geral

O Motor de Tradução Semântica (Semantic Translation Engine) implementa o **Fluxo B (Geração de Planos)** do Neural Hive-Mind, convertendo Intent Envelopes em Cognitive Plans executáveis.

### Arquitetura

- **Entrada**: Intent Envelopes consumidos de tópicos Kafka `intentions.*`
- **Processamento**: Parsing semântico, geração de DAG, avaliação de risco, explicabilidade
- **Saída**: Cognitive Plans publicados no tópico Kafka `plans.ready`
- **Persistência**: Ledger cognitivo imutável no MongoDB, cache Redis
- **Enriquecimento**: Knowledge Graph no Neo4j para contexto histórico e ontologias

### Componentes

1. **Semantic Parser**: Extrai objetivos, mapeia entidades para ontologia canônica
2. **DAG Generator**: Gera grafo acíclico de tarefas com ordem topológica
3. **Risk Scorer**: Calcula score de risco (prioridade + segurança + complexidade)
4. **Explainability Generator**: Cria tokens e narrativas de justificativa
5. **Cognitive Ledger**: Registro append-only com hash SHA-256 para integridade
6. **Orchestrator**: Coordena todas as etapas (B1-B6) do Fluxo B

---

## 🚀 Operações Comuns

### Deploy

```bash
# Configurar ambiente
export ENV=dev  # ou staging, prod
export NEO4J_PASSWORD=<senha-neo4j>
export MONGODB_PASSWORD=<senha-mongodb>

# Executar deploy
./scripts/deploy/deploy-semantic-translation-engine.sh

# Validar deployment
./scripts/validation/validate-semantic-translation-engine.sh
```

### Verificar Status

```bash
# Pods
kubectl get pods -n semantic-translation-engine

# Deployment
kubectl get deployment -n semantic-translation-engine

# Services
kubectl get svc -n semantic-translation-engine

# Health check
kubectl exec -n semantic-translation-engine <pod-name> -- \
  curl http://localhost:8000/health

# Readiness check
kubectl exec -n semantic-translation-engine <pod-name> -- \
  curl http://localhost:8000/ready
```

### Logs

```bash
# Logs em tempo real (todos os pods)
kubectl logs -f -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine

# Logs de um pod específico
kubectl logs -n semantic-translation-engine <pod-name>

# Logs estruturados com jq
kubectl logs -n semantic-translation-engine <pod-name> | jq .

# Filtrar por intent_id
kubectl logs -n semantic-translation-engine <pod-name> | \
  jq 'select(.intent_id == "<intent-id>")'

# Filtrar erros
kubectl logs -n semantic-translation-engine <pod-name> | \
  jq 'select(.level == "error")'
```

### Métricas

```bash
# Port-forward para endpoint de métricas
kubectl port-forward -n semantic-translation-engine \
  svc/semantic-translation-engine 8080:8080

# Consultar métricas
curl http://localhost:8080/metrics

# Métricas específicas
curl -s http://localhost:8080/metrics | grep neural_hive_geracao
curl -s http://localhost:8080/metrics | grep neural_hive_dag_complexity
curl -s http://localhost:8080/metrics | grep neural_hive_risk_score
```

**Dashboard Grafana**: http://grafana/d/semantic-translation-engine

### Traces Distribuídos

```bash
# Acessar Jaeger UI
# URL: http://jaeger/search?service=semantic-translation-engine

# Buscar por intent_id
# Tag: neural.hive.intent.id=<intent-id>

# Buscar por plan_id
# Tag: neural.hive.plan.id=<plan-id>

# Filtrar por duração alta
# Min Duration: 400ms (SLO threshold)
```

### Consumer Lag

```bash
# Verificar lag do consumer group
kafka-consumer-groups.sh \
  --bootstrap-server <kafka-bootstrap-servers> \
  --group semantic-translation-engine \
  --describe

# Resetar offsets (CUIDADO!)
kafka-consumer-groups.sh \
  --bootstrap-server <kafka-bootstrap-servers> \
  --group semantic-translation-engine \
  --reset-offsets --to-earliest \
  --topic intentions.business \
  --execute
```

---

## 🗄️ Persistência

### MongoDB - Ledger Cognitivo

```bash
# Conectar ao MongoDB
mongosh mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive

# Consultar ledger por plan_id
db.cognitive_ledger.find({plan_id: "<plan-id>"}).pretty()

# Consultar ledger por intent_id
db.cognitive_ledger.find({intent_id: "<intent-id>"}).pretty()

# Verificar integridade do ledger
db.cognitive_ledger.find({}, {plan_id: 1, hash: 1, _id: 0}).limit(10)

# Contar planos por domínio
db.cognitive_ledger.aggregate([
  {$unwind: "$plan_data"},
  {$group: {_id: "$plan_data.original_domain", count: {$sum: 1}}}
])
```

### Neo4j - Knowledge Graph

```bash
# Conectar ao Neo4j
cypher-shell -a bolt://neo4j-bolt.neo4j-cluster.svc.cluster.local:7687 \
  -u neo4j -p <password>

# Consultar intenções similares
MATCH (i:Intent {domain: "business"})
WHERE i.text CONTAINS "criar"
RETURN i.id, i.text, i.timestamp
LIMIT 10;

# Consultar ontologias
MATCH (o:Ontology)
RETURN o.type, o.canonical_type, o.properties
LIMIT 10;

# Consultar relações causais
MATCH (i:Intent {id: "<intent-id>"})-[r:CAUSES|DEPENDS_ON]->(related)
RETURN type(r), related.id, related.type;
```

### Redis - Cache

```bash
# Conectar ao Redis
redis-cli -h neural-hive-cache.redis-cluster.svc.cluster.local

# Verificar keys de cache
KEYS neo4j:*
KEYS context:enriched:*
KEYS ontology:*

# Consultar cache de query
GET neo4j:query:<hash>

# Invalidar cache
DEL neo4j:query:<hash>
FLUSHDB  # CUIDADO: limpa todo o cache
```

---

## 🔧 Troubleshooting

### Consumer não está consumindo

**Sintomas**: Pods saudáveis mas sem processar mensagens

**Diagnóstico**:
```bash
# Verificar logs
kubectl logs -n semantic-translation-engine <pod-name> | grep "Intent consumer"

# Verificar conectividade Kafka
kubectl exec -n semantic-translation-engine <pod-name> -- \
  nc -zv neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local 9092

# Verificar consumer group
kafka-consumer-groups.sh --bootstrap-server <kafka> \
  --group semantic-translation-engine --describe
```

**Resolução**:
1. Verificar NetworkPolicy permite conexão com Kafka
2. Verificar secrets de autenticação Kafka
3. Resetar offsets se necessário
4. Reiniciar pods: `kubectl rollout restart deployment -n semantic-translation-engine`

---

### Latência alta (> 400ms SLO)

**Sintomas**: P95 de `neural_hive_geracao_duration_seconds` > 0.4s

**Diagnóstico**:
```bash
# Verificar distribuição de latência
curl -s http://localhost:8080/metrics | \
  grep neural_hive_geracao_duration_seconds

# Verificar latência Neo4j
curl -s http://localhost:8080/metrics | \
  grep neural_hive_kg_query_duration

# Verificar cache hit rate
curl -s http://localhost:8080/metrics | \
  grep cache_hits_total
```

**Resolução**:
1. **Neo4j lento** (> 50ms):
   - Otimizar índices: `CREATE INDEX ON :Intent(domain, text)`
   - Aumentar timeout: editar `neo4j_query_timeout` em ConfigMap
   - Verificar recursos do Neo4j: CPU/memória
2. **Cache hit rate baixo** (< 60%):
   - Aumentar TTL do Redis
   - Verificar conectividade Redis
3. **DAG complexo** (> 20 tarefas):
   - Revisar heurísticas de decomposição
   - Ajustar templates de tarefas

---

### Planos não sendo publicados

**Sintomas**: Planos gerados mas não aparecem em `plans.ready`

**Diagnóstico**:
```bash
# Verificar logs de producer
kubectl logs -n semantic-translation-engine <pod-name> | \
  grep "Plan producer\|B6:"

# Verificar tópico existe
kafka-topics.sh --bootstrap-server <kafka> \
  --list | grep plans.ready

# Verificar mensagens no tópico
kafka-console-consumer.sh --bootstrap-server <kafka> \
  --topic plans.ready --from-beginning --max-messages 10
```

**Resolução**:
1. Criar tópico se não existir:
   ```bash
   kafka-topics.sh --bootstrap-server <kafka> \
     --create --topic plans.ready --partitions 3 --replication-factor 2
   ```
2. Verificar schema Avro compatível
3. Verificar NetworkPolicy permite conexão com Kafka
4. Verificar transações Kafka não abortadas

---

### Erros de integridade no ledger

**Sintomas**: Hash SHA-256 não corresponde aos dados

**Diagnóstico**:
```bash
# Verificar integridade manual
mongosh --eval '
  db = db.getSiblingDB("neural_hive");
  db.cognitive_ledger.find().forEach(function(entry) {
    var calculated = crypto.createHash("sha256")
      .update(JSON.stringify(entry.plan_data))
      .digest("hex");
    if (calculated !== entry.hash) {
      print("INTEGRITY FAIL: " + entry.plan_id);
    }
  });
'
```

**Resolução**:
1. **Corrupção detectada**: Investigar logs de MongoDB, possível falha de disco
2. **Serialização inconsistente**: Verificar versão do código de geração de hash
3. **Backup e restore**: Restaurar de backup se corrupção confirmada

---

### Neo4j timeout

**Sintomas**: Queries ao Knowledge Graph > 50ms (SLO)

**Diagnóstico**:
```bash
# Verificar queries lentas no Neo4j
cypher-shell -a bolt://neo4j-bolt:7687 -u neo4j -p <password>
CALL dbms.listQueries() YIELD query, elapsedTimeMillis
WHERE elapsedTimeMillis > 50
RETURN query, elapsedTimeMillis;

# Verificar cache hit rate
curl -s http://localhost:8080/metrics | grep cache_hits
```

**Resolução**:
1. **Criar índices**:
   ```cypher
   CREATE INDEX intent_domain ON :Intent(domain);
   CREATE INDEX intent_text ON :Intent(text);
   CREATE FULLTEXT INDEX intent_search FOR (i:Intent) ON EACH [i.text];
   ```
2. **Aumentar cache TTL** (Redis): de 600s para 1800s
3. **Aumentar timeout configurável**: editar ConfigMap `neo4j_query_timeout`
4. **Escalar Neo4j**: adicionar replicas read-only

---

## 📊 Métricas e SLOs

### Service Level Objectives (SLOs)

| Métrica | SLO | Alerta Warning | Alerta Critical |
|---------|-----|----------------|-----------------|
| Latência B1→B6 (P95) | < 400ms | > 400ms | > 1000ms |
| Taxa de sucesso | > 97% | < 97% | < 90% |
| Neo4j query latency | < 50ms | > 50ms | > 100ms |
| Consumer lag | < 1000 msgs | > 1000 | > 5000 |
| Cache hit rate | > 60% | < 60% | < 40% |

### Métricas Principais

```promql
# Latência de geração (P95)
histogram_quantile(0.95,
  rate(neural_hive_geracao_duration_seconds_bucket[5m])
)

# Taxa de sucesso
sum(rate(neural_hive_plans_generated_total{status="success"}[5m])) /
sum(rate(neural_hive_plans_generated_total[5m]))

# Distribuição de risco
sum by (risk_band) (neural_hive_risk_score)

# Latência Neo4j
histogram_quantile(0.95,
  rate(neural_hive_kg_query_duration_seconds_bucket[5m])
)

# Cache hit rate
sum(rate(cache_hits_total[5m])) /
(sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m])))
```

---

## 🔗 Referências

- [Documento 06 - Fluxo B](../../documento-06-fluxos-processos-neural-hive-mind.md)
- [Observabilidade - Geração de Planos](../observability/services/geracao-planos.md)
- [Schema Cognitive Plan](../../schemas/cognitive-plan/cognitive-plan.avsc)
- [Runbook Geral](runbook.md)
- [Troubleshooting Guide](troubleshooting-guide.md)

---

## 📞 Suporte

- **Logs**: Loki + Grafana
- **Métricas**: Prometheus + Grafana
- **Traces**: Jaeger
- **Alertas**: Prometheus AlertManager
