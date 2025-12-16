# Checklist de Deployment da Infraestrutura - Neural Hive-Mind

## Pré-requisitos
- [ ] Cluster Kubeadm configurado (1 master + 2 workers)
- [ ] Todos os nós com status Ready
- [ ] kubectl configurado e conectado ao cluster
- [ ] Helm 3.x instalado
- [ ] Bootstrap aplicado com sucesso (fase anterior)
- [ ] Recursos disponíveis verificados (CPU: 8+ cores, RAM: 16+ GB, Storage: 200+ GB)

## Preparação do Ambiente
- [ ] StorageClass criado (`local-path` ou `hostpath`)
- [ ] StorageClass definido como default
- [ ] Namespaces de infraestrutura criados
- [ ] Repositórios Helm adicionados:
  - [ ] Strimzi: `helm repo add strimzi https://strimzi.io/charts/`
  - [ ] Redis Operator: `helm repo add ot-helm https://ot-redis-operator.github.io/helm-charts/`
  - [ ] MongoDB: `helm repo add mongodb https://mongodb.github.io/helm-charts`
  - [ ] Neo4j: `helm repo add neo4j https://helm.neo4j.com/neo4j`
  - [ ] ClickHouse: `helm repo add altinity https://docs.altinity.com/clickhouse-operator/`
- [ ] Repositórios atualizados: `helm repo update`
- [ ] Valores customizados preparados (script executado)

## Kafka (Strimzi)
- [ ] Namespace `kafka` criado
- [ ] Strimzi operator instalado
- [ ] Operator pod Running
- [ ] Kafka cluster manifest aplicado
- [ ] Kafka cluster status Ready
- [ ] Kafka pods Running (controller + broker)
- [ ] Tópicos criados via Helm chart
- [ ] Validação: 12+ tópicos listados
- [ ] Teste de produção/consumo realizado
- [ ] Logs verificados (sem erros críticos)

## Redis Cluster
- [ ] Namespace `redis-cluster` criado
- [ ] Namespace `redis-operator` criado
- [ ] Redis operator instalado
- [ ] Operator pod Running
- [ ] Redis cluster instalado via Helm
- [ ] RedisCluster CRD status verificado
- [ ] 3+ pods Redis Running
- [ ] PVCs provisionados e Bound
- [ ] Serviço ClusterIP criado
- [ ] Teste de conexão: `redis-cli ping` retorna PONG
- [ ] Cluster info verificado
- [ ] Senha obtida do Secret
- [ ] ServiceMonitor criado (se Prometheus disponível)

## MongoDB
- [ ] Namespace `mongodb-cluster` criado
- [ ] Namespace `mongodb-operator` criado
- [ ] MongoDB operator instalado
- [ ] Operator pod Running
- [ ] MongoDB cluster instalado via Helm
- [ ] MongoDBCommunity CRD status verificado
- [ ] 3 pods MongoDB Running (ReplicaSet)
- [ ] PVCs provisionados e Bound
- [ ] Serviço ClusterIP criado
- [ ] Teste de conexão: `mongosh` conecta com sucesso
- [ ] ReplicaSet status verificado: `rs.status()`
- [ ] Credenciais obtidas do Secret
- [ ] Database `neural_hive` criada
- [ ] ServiceMonitor criado

## Neo4j
- [ ] Namespace `neo4j-cluster` criado
- [ ] Neo4j instalado via Helm
- [ ] Pods Neo4j Running (core + replicas)
- [ ] PVCs provisionados e Bound
- [ ] Serviços criados (bolt: 7687, http: 7474, https: 7473)
- [ ] Teste de conexão Bolt realizado
- [ ] Neo4j Browser acessível via port-forward
- [ ] Plugins instalados (APOC, Neosemantics)
- [ ] Credenciais obtidas do Secret
- [ ] Cluster topology verificado (se cluster mode)
- [ ] ServiceMonitor criado

## ClickHouse
- [ ] Namespace `clickhouse-cluster` criado
- [ ] Namespace `clickhouse-operator` criado
- [ ] ClickHouse operator instalado
- [ ] Operator pod Running
- [ ] ClickHouse cluster instalado via Helm
- [ ] ClickHouseInstallation CRD status verificado
- [ ] Pods ClickHouse Running (shards + replicas)
- [ ] Pods ZooKeeper Running
- [ ] PVCs provisionados e Bound
- [ ] Serviços criados (http: 8123, native: 9000)
- [ ] Teste de query: `SELECT version()` executado
- [ ] Cluster verificado: `SELECT * FROM system.clusters`
- [ ] Credenciais obtidas do Secret
- [ ] ServiceMonitor criado

## Validação Completa
- [ ] Script de validação executado: `03-validate-infrastructure.sh`
- [ ] Todos os pods Running (0 CrashLoopBackOff)
- [ ] Todos os PVCs Bound (0 Pending)
- [ ] Todos os serviços ClusterIP criados
- [ ] Testes de conectividade inter-namespace realizados
- [ ] Logs verificados (sem erros críticos)
- [ ] Métricas endpoints acessíveis
- [ ] Relatório de validação gerado
- [ ] Status: ALL CHECKS PASSED

## Documentação
- [ ] Endpoints documentados
- [ ] Credenciais armazenadas de forma segura
- [ ] Recursos consumidos documentados
- [ ] Problemas encontrados e soluções documentados

## Próximos Passos
- [ ] Pronto para Fase 3: Deploy da Stack de Observabilidade

---

**Data de conclusão:** _____________  
**Responsável:** _____________  
**Tempo total:** _____________  
**Observações:** ________________________________________________
