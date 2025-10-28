# Semantic Translation Engine

Motor de Tradução Semântica - Neural Hive-Mind Fase 1

## Visão Geral

O Semantic Translation Engine é o componente responsável por consumir Intent Envelopes do Kafka e transformá-los em Cognitive Plans estruturados e executáveis. Ele implementa o **Fluxo B (Geração de Planos)** da arquitetura Neural Hive-Mind.

## Arquitetura

### Fluxo de Dados

```
Intent Envelope (Kafka)
    ↓
Semantic Parser (enriquecimento de contexto)
    ↓
Neo4j (consulta ao grafo de conhecimento)
    ↓
DAG Generator (geração de passos executáveis)
    ↓
Risk Scorer (avaliação de riscos)
    ↓
Explainability Generator (geração de explicações)
    ↓
Cognitive Plan (estruturado)
    ↓
MongoDB (persistência no ledger cognitivo)
    ↓
Kafka (publicação em plans.ready)
```

### Dependências Externas

- **Kafka**: Mensageria para consumo de intenções e publicação de planos
  - Topics de entrada: `intentions.business`, `intentions.technical`, `intentions.infrastructure`, `intentions.security`
  - Topic de saída: `plans.ready`
- **Neo4j**: Grafo de conhecimento para consulta de padrões e workflows
- **MongoDB**: Persistência do ledger cognitivo e contexto operacional
- **Redis**: Cache de contexto e queries frequentes
- **OpenTelemetry Collector**: Observabilidade e traces distribuídos

## Estrutura do Projeto

```
services/semantic-translation-engine/
├── src/
│   ├── main.py                      # Ponto de entrada FastAPI
│   ├── config/                      # Configurações
│   │   └── settings.py
│   ├── models/                      # Modelos Pydantic
│   │   ├── intent.py
│   │   └── plan.py
│   ├── consumers/                   # Kafka consumers
│   │   └── intent_consumer.py
│   ├── producers/                   # Kafka producers
│   │   └── plan_producer.py
│   ├── clients/                     # Clientes de infraestrutura
│   │   ├── neo4j_client.py
│   │   ├── mongodb_client.py
│   │   └── redis_client.py
│   ├── services/                    # Lógica de negócio
│   │   ├── semantic_parser.py
│   │   ├── dag_generator.py
│   │   ├── risk_scorer.py
│   │   ├── explainability_generator.py
│   │   └── orchestrator.py
│   └── observability/               # Métricas e tracing
│       └── metrics.py
├── Dockerfile                       # Multi-stage build
├── requirements.txt                 # Dependências Python
└── README.md                        # Este arquivo
```

## Desenvolvimento Local

### Pré-requisitos

- Python 3.11+
- Docker (para build de imagem)
- Acesso às dependências externas:
  - Kafka (Strimzi)
  - Neo4j
  - MongoDB
  - Redis

### Instalação

```bash
# Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

### Configuração

Variáveis de ambiente necessárias (ver `src/config/settings.py`):

```bash
# Kafka
export KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
export KAFKA_CONSUMER_GROUP_ID="semantic-translation-engine"
export KAFKA_TOPICS="intentions.business,intentions.technical,intentions.infrastructure,intentions.security"
export KAFKA_PLANS_TOPIC="plans.ready"

# Neo4j
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="neo4j"
export NEO4J_DATABASE="neo4j"

# MongoDB
export MONGODB_URI="mongodb://localhost:27017"
export MONGODB_DATABASE="neural_hive"

# Redis
export REDIS_CLUSTER_NODES="localhost:6379"
export REDIS_SSL_ENABLED="false"

# OpenTelemetry
export OTEL_ENDPOINT="http://localhost:4317"

# Aplicação
export ENVIRONMENT="local"
export LOG_LEVEL="DEBUG"
```

### Executar Localmente

```bash
# Modo development com hot-reload
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Modo production
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2
```

## Build e Deploy

### Build da Imagem Docker

```bash
# Configurar Docker para usar daemon do Minikube (ambiente local)
eval $(minikube docker-env)

# Build da imagem a partir da raiz do repositório
cd /home/jimy/Base/Neural-Hive-Mind  # ajustar para o caminho da raiz do seu repositório
docker build -f services/semantic-translation-engine/Dockerfile -t neural-hive-mind/semantic-translation-engine:local .

# Verificar imagem
docker images | grep semantic-translation-engine
```

### Deploy no Kubernetes (Minikube)

```bash
# Usar script de deploy local
./scripts/deploy/deploy-semantic-translation-engine-local.sh

# Ou deploy manual via Helm
helm upgrade --install semantic-translation-engine \
  ./helm-charts/semantic-translation-engine \
  --namespace semantic-translation-engine \
  --values ./helm-charts/semantic-translation-engine/values-local.yaml \
  --set image.tag=local \
  --set image.pullPolicy=IfNotPresent \
  --wait --timeout 10m
```

## Endpoints

### Health Checks

- **GET `/health`**: Liveness probe
  ```json
  {
    "status": "healthy",
    "service": "semantic-translation-engine",
    "version": "1.0.0"
  }
  ```

- **GET `/ready`**: Readiness probe (verifica todas as dependências)
  ```json
  {
    "ready": true,
    "checks": {
      "kafka_consumer": true,
      "kafka_producer": true,
      "neo4j": true,
      "mongodb": true,
      "redis": true
    }
  }
  ```

### Métricas

- **GET `/metrics`**: Endpoint Prometheus com métricas customizadas

## Métricas Disponíveis

### Contadores
- `neural_hive_plans_generated_total{domain, status}`: Total de planos gerados
- `neural_hive_kafka_messages_consumed_total{topic}`: Total de mensagens consumidas
- `neural_hive_kafka_messages_produced_total{topic}`: Total de mensagens produzidas
- `neural_hive_errors_total{error_type, component}`: Total de erros

### Histogramas
- `neural_hive_plan_generation_duration_seconds{domain}`: Latência de geração de planos
- `neural_hive_neo4j_query_duration_seconds{query_type}`: Latência de queries Neo4j
- `neural_hive_mongodb_operation_duration_seconds{operation}`: Latência de operações MongoDB

### Gauges
- `neural_hive_redis_cache_hit_rate`: Taxa de acerto do cache Redis

## Testes

### Executar Testes Automatizados

```bash
# Script de teste end-to-end
./tests/test-semantic-translation-engine-local.sh
```

### Teste Manual

```bash
# Publicar Intent Envelope de teste no Kafka
kubectl run kafka-producer-test --restart='Never' \
  --image docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
  --namespace neural-hive-kafka \
  --command -- sh -c "echo '{
    \"id\": \"test-intent-123\",
    \"actor\": {\"type\": \"human\", \"id\": \"user-1\", \"name\": \"Test User\"},
    \"intent\": {
      \"text\": \"Criar API REST para gerenciar produtos\",
      \"domain\": \"business\",
      \"classification\": \"api-creation\",
      \"entities\": [],
      \"keywords\": [\"API\", \"REST\", \"produtos\"]
    },
    \"confidence\": 0.95,
    \"context\": {
      \"session_id\": \"test-session\",
      \"user_id\": \"user-1\",
      \"tenant_id\": \"tenant-1\",
      \"channel\": \"test\"
    },
    \"constraints\": {
      \"priority\": \"high\",
      \"security_level\": \"internal\"
    },
    \"timestamp\": $(date +%s)000
  }' | kafka-console-producer.sh \
    --bootstrap-server neural-hive-kafka-bootstrap:9092 \
    --topic intentions.business"

# Verificar logs
kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine -f

# Consumir plano gerado
kubectl run kafka-consumer-test --restart='Never' \
  --image docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
  --namespace neural-hive-kafka \
  --command -- sh -c "kafka-console-consumer.sh \
    --bootstrap-server neural-hive-kafka-bootstrap:9092 \
    --topic plans.ready \
    --from-beginning \
    --max-messages 1"
```

## Troubleshooting

### Pod não inicia

```bash
# Verificar eventos
kubectl describe pod -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine

# Verificar logs
kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine

# Verificar imagem
kubectl get pod -n semantic-translation-engine -o jsonpath='{.items[0].spec.containers[0].image}'
```

### Consumer não conecta ao Kafka

```bash
# Testar conectividade
kubectl run kafka-test --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine \
  -- nc -zv neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local 9092

# Verificar configuração
kubectl get configmap -n semantic-translation-engine semantic-translation-engine -o yaml | grep KAFKA
```

### Neo4j timeout

```bash
# Verificar conectividade
kubectl run neo4j-test --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine \
  -- nc -zv neo4j.neo4j.svc.cluster.local 7687

# Aumentar timeout (valores configuráveis no ConfigMap)
# NEO4J_QUERY_TIMEOUT_MS=30000
```

### MongoDB não conecta

```bash
# Verificar conectividade
kubectl run mongo-test --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine \
  -- nc -zv mongodb.mongodb-cluster.svc.cluster.local 27017

# Verificar logs MongoDB
kubectl logs -n mongodb-cluster -l app=mongodb
```

## Comandos Úteis

```bash
# Ver logs em tempo real
kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine -f

# Port-forward para health checks
kubectl port-forward -n semantic-translation-engine svc/semantic-translation-engine 8000:8000

# Port-forward para métricas
kubectl port-forward -n semantic-translation-engine svc/semantic-translation-engine 8080:8080

# Reiniciar deployment
kubectl rollout restart deployment/semantic-translation-engine -n semantic-translation-engine

# Escalar replicas
kubectl scale deployment/semantic-translation-engine -n semantic-translation-engine --replicas=2

# Deletar deployment
helm uninstall semantic-translation-engine -n semantic-translation-engine

# Rebuild e redeploy (executar da raiz do repositório)
eval $(minikube docker-env)
docker build -f services/semantic-translation-engine/Dockerfile -t neural-hive-mind/semantic-translation-engine:local .
kubectl rollout restart deployment/semantic-translation-engine -n semantic-translation-engine
```

## Observabilidade

### Logs Estruturados

Todos os logs seguem formato JSON estruturado com campos:
- `timestamp`: Timestamp ISO 8601
- `level`: DEBUG/INFO/WARNING/ERROR/CRITICAL
- `message`: Mensagem descritiva
- `correlation_id`: ID de correlação do trace
- `intent_id`: ID da intenção processada
- `plan_id`: ID do plano gerado

### Traces Distribuídos

O serviço está instrumentado com OpenTelemetry e envia traces para o collector configurado:
- Spans customizados para cada etapa do processamento
- Propagação de contexto via headers Kafka
- Atributos: `intent_id`, `plan_id`, `domain`, `correlation_id`

### Dashboards

Métricas Prometheus podem ser visualizadas em:
- Grafana (via port-forward para `grafana-service:3000`)
- Visualização de traces em Jaeger (porta 16686)

## Licença

Proprietary - Neural Hive-Mind Team

## Documentação Adicional

- [Guia de Deploy e Testes](../../docs/SEMANTIC_TRANSLATION_ENGINE_DEPLOYMENT.md)
- [Arquitetura Geral](../../ARCHITECTURE.md)
- [Deployment Local](../../DEPLOYMENT_LOCAL.md)
