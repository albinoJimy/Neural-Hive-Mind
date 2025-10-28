# Guia de Operações - Camada de Memória Multicamadas

## Visão Geral

Este guia documenta as operações da camada de memória multicamadas do Neural Hive-Mind, composta por Redis, MongoDB, Neo4j e ClickHouse.

## Arquitetura

### Componentes

1. **Redis Cluster** - Memória de Curto Prazo
   - TTL: 5-15 minutos
   - Uso: Cache, deduplicação de eventos
   - Namespace: `redis-cluster`

2. **MongoDB** - Contexto Operacional
   - Retenção: 30 dias
   - Uso: Estados intermediários, contexto de sessão
   - Namespace: `mongodb-cluster`

3. **Neo4j** - Knowledge Graph Semântico
   - Retenção: Ontologias versionadas
   - Uso: Relações causais, grafos de conhecimento
   - Namespace: `neo4j-cluster`

4. **ClickHouse** - Analytics Histórico
   - Retenção: 18 meses (540 dias)
   - Uso: Séries temporais, telemetria, eventos
   - Namespace: `clickhouse-cluster`

## Operações Comuns

### MongoDB

#### Backup Manual

```bash
# Conectar ao pod primário
kubectl exec -it -n mongodb-cluster neural-hive-mongodb-0 -- bash

# Executar backup
mongodump --out=/backup/manual-$(date +%Y%m%d-%H%M%S) --gzip
```

#### Restore

```bash
# Copiar backup para o pod
kubectl cp backup.tar.gz mongodb-cluster/neural-hive-mongodb-0:/tmp/

# Conectar e restaurar
kubectl exec -it -n mongodb-cluster neural-hive-mongodb-0 -- bash
mongorestore --gzip /tmp/backup.tar.gz
```

#### Verificar Status do ReplicaSet

```bash
kubectl exec -n mongodb-cluster neural-hive-mongodb-0 -- mongosh --eval "rs.status()"
```

#### Adicionar Índices

```bash
kubectl exec -n mongodb-cluster neural-hive-mongodb-0 -- mongosh neural_hive --eval '
db.sessions.createIndex({ "session_id": 1 }, { unique: true });
db.sessions.createIndex({ "created_at": 1 }, { expireAfterSeconds: 2592000 });
'
```

#### Monitorar Performance

```bash
# Via Grafana
open https://grafana.neural-hive.io/d/mongodb-cluster

# Via CLI
kubectl exec -n mongodb-cluster neural-hive-mongodb-0 -- mongosh --eval "db.serverStatus()"
```

### Neo4j

#### Backup Manual

```bash
# Parar escrita temporariamente (se necessário)
kubectl exec -n neo4j-cluster neo4j-0 -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "CALL dbms.checkpoint()"

# Executar backup
kubectl exec -n neo4j-cluster neo4j-0 -- neo4j-admin database dump neo4j \
  --to-path=/backup/manual-$(date +%Y%m%d-%H%M%S)
```

#### Restore

```bash
# Parar database
kubectl exec -n neo4j-cluster neo4j-0 -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "STOP DATABASE neo4j"

# Restaurar
kubectl exec -n neo4j-cluster neo4j-0 -- neo4j-admin database load neo4j \
  --from-path=/backup/dump-file

# Reiniciar database
kubectl exec -n neo4j-cluster neo4j-0 -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "START DATABASE neo4j"
```

#### Verificar Status do Cluster

```bash
kubectl exec -n neo4j-cluster neo4j-0 -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "CALL dbms.cluster.overview() YIELD role, addresses RETURN role, addresses;"
```

#### Executar Queries

```bash
# Conectar via cypher-shell
kubectl exec -it -n neo4j-cluster neo4j-0 -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD"

# Exemplo: contar nós
MATCH (n) RETURN count(n);
```

#### Carregar Ontologias

```bash
# Copiar arquivo cypher
kubectl cp ontology.cypher neo4j-cluster/neo4j-0:/tmp/

# Executar
kubectl exec -n neo4j-cluster neo4j-0 -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  -f /tmp/ontology.cypher
```

#### Monitorar Queries Lentas

```bash
# Via query log
kubectl exec -n neo4j-cluster neo4j-0 -- tail -f /logs/query.log

# Via Grafana
open https://grafana.neural-hive.io/d/neo4j-cluster
```

### ClickHouse

#### Backup Manual

```bash
# Executar backup via clickhouse-backup (se instalado)
kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-backup create manual-$(date +%Y%m%d-%H%M%S)
```

#### Restore

```bash
# Listar backups
kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-backup list

# Restaurar
kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-backup restore <backup-name>
```

#### Otimizar Tables

```bash
kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-client --query "OPTIMIZE TABLE telemetry.metrics FINAL;"

kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-client --query "OPTIMIZE TABLE events.event_log FINAL;"
```

#### Verificar Replicação

```bash
kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-client --query "SELECT * FROM system.replicas FORMAT Vertical;"
```

#### Monitorar Merges

```bash
kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-client --query "SELECT * FROM system.merges FORMAT Vertical;"
```

#### Queries de Manutenção

```bash
# Ver tabelas e tamanhos
kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-client --query "
    SELECT
      database,
      table,
      formatReadableSize(sum(bytes)) as size,
      sum(rows) as rows
    FROM system.parts
    WHERE active
    GROUP BY database, table
    ORDER BY sum(bytes) DESC;"

# Ver parts por tabela
kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-client --query "
    SELECT
      table,
      count() as parts_count
    FROM system.parts
    WHERE active AND database = 'telemetry'
    GROUP BY table;"
```

## Troubleshooting

### MongoDB

#### Problema: Replicação Lenta

**Sintomas:**
- Lag de replicação > 10s
- Alertas `MongoDBReplicationLag`

**Diagnóstico:**
```bash
kubectl exec -n mongodb-cluster neural-hive-mongodb-0 -- mongosh --eval "
  rs.printReplicationInfo();
  rs.printSecondaryReplicationInfo();
"
```

**Soluções:**
1. Verificar network latency entre pods
2. Verificar tamanho do oplog: `db.getReplicationInfo()`
3. Aumentar oplog se necessário
4. Verificar índices em queries lentas

#### Problema: Conexões Altas

**Sintomas:**
- Conexões ativas > 80% do limite
- Alertas `MongoDBHighConnections`

**Diagnóstico:**
```bash
kubectl exec -n mongodb-cluster neural-hive-mongodb-0 -- mongosh --eval "
  db.serverStatus().connections
"
```

**Soluções:**
1. Verificar connection pooling nas aplicações
2. Identificar queries lentas: `db.currentOp()`
3. Aumentar limite de conexões se necessário
4. Otimizar queries lentas

#### Problema: Disk Space Alto

**Sintomas:**
- Uso de disco > 85%
- Alertas `MongoDBDiskSpaceHigh`

**Soluções:**
1. Aumentar PVC: `kubectl edit pvc -n mongodb-cluster`
2. Habilitar compressão: `storage.wiredTiger.engineConfig.journalCompressor: zstd`
3. Executar compact: `db.runCommand({ compact: 'collection_name' })`
4. Revisar políticas de retenção

### Neo4j

#### Problema: Heap Usage Alto

**Sintomas:**
- Heap > 85%
- Alertas `Neo4jHighHeapUsage`
- GC frequentes

**Diagnóstico:**
```bash
kubectl exec -n neo4j-cluster neo4j-0 -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "CALL dbms.queryJmx('java.lang:type=Memory') YIELD attributes RETURN attributes;"
```

**Soluções:**
1. Ajustar heap size no values.yaml
2. Otimizar queries: adicionar LIMIT, usar índices
3. Verificar memory leaks em queries
4. Escalar verticalmente pods

#### Problema: Cluster Sem Leader

**Sintomas:**
- Alertas `Neo4jNoLeader`
- Cluster instável

**Diagnóstico:**
```bash
kubectl exec -n neo4j-cluster neo4j-0 -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "CALL dbms.cluster.overview();"
```

**Soluções:**
1. Verificar network connectivity entre cores
2. Verificar logs: `kubectl logs -n neo4j-cluster neo4j-0`
3. Verificar quorum: precisa maioria de cores online
4. Restart coordenado se necessário

#### Problema: Queries Lentas

**Sintomas:**
- Queries > 30s
- Alertas `Neo4jSlowQueries`

**Diagnóstico:**
```bash
# Ver queries ativas
kubectl exec -n neo4j-cluster neo4j-0 -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "CALL dbms.listQueries();"

# Ver query log
kubectl logs -n neo4j-cluster neo4j-0 | grep -A5 "slow query"
```

**Soluções:**
1. Adicionar índices: `CREATE INDEX FOR (n:Label) ON (n.property)`
2. Usar `PROFILE` para analisar plano de execução
3. Otimizar Cypher: evitar cartesian products
4. Aumentar query timeout se queries legítimas

### ClickHouse

#### Problema: Replicação Lenta

**Sintomas:**
- Lag > 60s
- Alertas `ClickHouseReplicationLag`

**Diagnóstico:**
```bash
kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-client --query "
    SELECT
      database, table,
      absolute_delay,
      queue_size
    FROM system.replicas
    WHERE absolute_delay > 0;"
```

**Soluções:**
1. Verificar ZooKeeper health
2. Verificar network latency
3. Otimizar tables: `OPTIMIZE TABLE ... FINAL`
4. Verificar logs: `kubectl logs -n clickhouse-cluster`

#### Problema: Muitos Parts

**Sintomas:**
- Parts > 300
- Alertas `ClickHouseTooManyParts`
- Queries lentas

**Diagnóstico:**
```bash
kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-client --query "
    SELECT table, count() as parts
    FROM system.parts
    WHERE active
    GROUP BY table
    HAVING parts > 100;"
```

**Soluções:**
1. Executar merge manual: `OPTIMIZE TABLE ... FINAL`
2. Ajustar configuração de merge: `merge_max_block_size`
3. Revisar estratégia de particionamento
4. Considerar batch inserts maiores

#### Problema: Queries Lentas

**Sintomas:**
- Queries > 60s
- Alertas `ClickHouseSlowQueries`

**Diagnóstico:**
```bash
kubectl exec -n clickhouse-cluster chi-clickhouse-cluster-0-0-0 -- \
  clickhouse-client --query "
    SELECT
      query_duration_ms,
      query,
      user
    FROM system.query_log
    WHERE type = 'QueryFinish'
    ORDER BY query_duration_ms DESC
    LIMIT 10;"
```

**Soluções:**
1. Verificar índices e partições
2. Otimizar query: usar PREWHERE, filtrar por data
3. Aumentar recursos (CPU, memory)
4. Considerar materialized views

## Runbooks

### Emergency Procedures

#### Cluster Completo Down

1. Verificar saúde do cluster Kubernetes
2. Verificar eventos: `kubectl get events -n <namespace>`
3. Verificar logs dos pods
4. Verificar PVCs e storage
5. Escalar para oncall se necessário

#### Data Corruption

1. Parar aplicações que escrevem
2. Identificar escopo da corrupção
3. Restaurar de backup
4. Validar dados restaurados
5. Reiniciar aplicações

#### Performance Degradation

1. Identificar componente afetado (dashboards)
2. Verificar recursos (CPU, memory, disk)
3. Verificar queries lentas
4. Aplicar otimizações conforme troubleshooting
5. Escalar recursos se necessário

## Monitoramento

### Dashboards Grafana

- MongoDB: https://grafana.neural-hive.io/d/mongodb-cluster
- Neo4j: https://grafana.neural-hive.io/d/neo4j-cluster
- ClickHouse: https://grafana.neural-hive.io/d/clickhouse-cluster
- Overview: https://grafana.neural-hive.io/d/memory-layer-overview

### Métricas Principais

**MongoDB:**
- `mongodb_up`: disponibilidade
- `mongodb_connections`: conexões ativas
- `mongodb_op_counters_total`: operações/seg
- `mongodb_replset_member_replication_lag`: lag replicação

**Neo4j:**
- `neo4j_database_system_check_point_events_total`: checkpoints
- `neo4j_vm_heap_used_bytes`: uso heap
- `neo4j_database_transaction_active`: transações ativas
- `neo4j_bolt_connections_opened_total`: conexões Bolt

**ClickHouse:**
- `clickhouse_query_total`: total queries
- `clickhouse_query_duration_seconds`: duração queries
- `clickhouse_table_parts`: parts por tabela
- `clickhouse_replicas_max_absolute_delay`: lag replicação

### Alertas

Ver: `monitoring/alerts/memory-layer-alerts.yaml`

## Manutenção

### Tarefas Diárias

- Verificar dashboards de saúde
- Revisar alertas ativos
- Verificar backups automáticos

### Tarefas Semanais

- Revisar queries lentas
- Otimizar índices se necessário
- Verificar crescimento de storage
- Testar procedimentos de restore

### Tarefas Mensais

- Revisar capacidade e planejamento
- Atualizar runbooks
- Revisar políticas de retenção
- Executar DR drill

## Referências

- [Documento 03: Componentes e Processos](../../documento-03-componentes-e-processos-neural-hive-mind.md)
- [Documento 08: Detalhamento Técnico](../../documento-08-detalhamento-tecnico-camadas-neural-hive-mind.md)
- Dashboards: https://grafana.neural-hive.io
- Alertas: `monitoring/alerts/memory-layer-alerts.yaml`

## Contatos de Escalação

- On-call primário: Neural Hive SRE
- Escalação secundária: Platform Team
- Emergências: #neural-hive-incidents (Slack)
