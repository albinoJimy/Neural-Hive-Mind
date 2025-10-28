# Operações dos Especialistas Neurais

## Visão Geral
Guia operacional para gerenciar os 5 especialistas neurais da camada cognitiva do Neural Hive-Mind.

## Arquitetura
- **Business Specialist**: análise de workflows, KPIs, custos
- **Technical Specialist**: qualidade de código, performance, segurança
- **Behavior Specialist**: jornadas de usuário, análise de sentimento
- **Evolution Specialist**: oportunidades de melhoria, hipóteses
- **Architecture Specialist**: dependências, escalabilidade, padrões

## Operações Comuns

### Deploy
```bash
export ENV=dev
export MLFLOW_TRACKING_URI=http://mlflow:5000
export MONGODB_URI=mongodb://mongodb:27017
export NEO4J_PASSWORD=secret
./scripts/deploy/deploy-specialists.sh
```

### Validação
```bash
./scripts/validation/validate-specialists.sh
```

### Logs
```bash
# Logs de um especialista específico
kubectl logs -f -n specialist-business -l app.kubernetes.io/name=specialist-business

# Logs estruturados (JSON)
kubectl logs -n specialist-business <pod-name> | jq .

# Filtrar por plan_id
kubectl logs -n specialist-business <pod-name> | jq 'select(.plan_id == "<id>")'
```

### Métricas
```bash
# Port-forward para métricas
kubectl port-forward -n specialist-business svc/specialist-business 8080:8080
curl http://localhost:8080/metrics

# Dashboard Grafana
open http://grafana/d/specialists-cognitive-layer
```

### Traces
```bash
# Jaeger UI
open http://jaeger/search?service=specialist-business

# Buscar por plan_id
# Tag: neural.hive.plan.id=<id>
```

### MLflow
```bash
# Acessar MLflow UI
kubectl port-forward -n mlflow svc/mlflow 5000:5000
open http://localhost:5000

# Listar modelos registrados
mlflow models list --registered-model-name business-evaluator

# Promover modelo para Production
mlflow models transition-stage \
  --name business-evaluator \
  --version 2 \
  --stage Production
```

### Ledger
```bash
# Consultar pareceres no MongoDB
mongosh mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive

db.specialist_opinions.find({plan_id: "<id>"}).pretty()

# Verificar integridade
db.specialist_opinions.aggregate([
  {$project: {opinion_id: 1, hash: 1}},
  {$limit: 10}
])
```

## Troubleshooting

### Especialista não está avaliando
- Verificar conectividade com MLflow
- Verificar modelo carregado
- Verificar logs para erros de deserialização
- Verificar network policy

### Latência alta (> 5s SLO)
- Verificar latência de inferência do modelo
- Verificar latência de queries ao Neo4j
- Verificar recursos (CPU, memória)
- Verificar cache Redis

### Confidence score baixo (< 0.8)
- Verificar qualidade dos dados de entrada
- Verificar drift do modelo
- Considerar re-treinamento
- Verificar heurísticas

### Divergência alta entre especialistas
- Analisar fatores de raciocínio
- Verificar se é esperado (domínios diferentes)
- Considerar recalibração de pesos (próxima fase)
- Escalar para revisão humana

### Modelo não carregado
- Verificar conectividade com MLflow
- Verificar se modelo existe no registry
- Verificar stage do modelo (Production/Staging)
- Verificar logs de inicialização

### Pareceres não sendo persistidos
- Verificar conectividade com MongoDB
- Verificar permissões de escrita
- Verificar logs do ledger client
- Verificar espaço em disco

## Runbooks
- [Runbook geral](runbook.md)
- [Troubleshooting guide](troubleshooting-guide.md)

## Dashboards
- [Specialists Cognitive Layer](http://grafana/d/specialists-cognitive-layer)
- [Fluxo B - Geração de Planos](http://grafana/d/fluxo-b-geracao-planos)

## Alertas
- Ver `monitoring/alerts/specialists-alerts.yaml`

## Referências
- [Documento 03 - Especialistas Neurais](../../documento-03-componentes-e-processos-neural-hive-mind.md)
- [Observabilidade - Camada Cognitiva](../observability/services/agentes/camada-cognitiva.md)
- [Catálogo de Agentes](../observability/services/agentes.md)
