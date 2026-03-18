# Optimizer Agents Helm Chart

Optimizer Agents - Serviço de análise e otimização de workflows para o Neural-Hive-Mind.

## Funcionalidades

- **Análise Multi-database**: MongoDB, PostgreSQL, Neo4j, Redis, ClickHouse
- **Análise de Código**: Python (complexidade ciclomática)
- **Auto-apply Mechanism**: Aplicação automática de otimizações seguras
- **REST API**: 8 endpoints para consulta e aprovação de recomendações

## Instalação

```bash
# Adicionar repositório Helm (se aplicável)
helm repo add neural-hive-mind https://charts.neural-hive-mind.com

# Instalar com valores padrão
helm install optimizer-agents ./helm/optimizer-agents

# Instalar com valores customizados
helm install optimizer-agents ./helm/optimizer-agents -f values-production.yaml
```

## Configuração

### Valores Principais

| Parâmetro | Descrição | Default |
|-----------|-----------|---------|
| `replicaCount` | Número de réplicas | `1` |
| `image.repository` | Imagem Docker | `ghcr.io/albinojimy/neural-hive-mind/optimizer-agents` |
| `image.tag` | Tag da imagem | `0.1.0` |
| `resources.limits.cpu` | Limite de CPU | `500m` |
| `resources.limits.memory` | Limite de memória | `512Mi` |

### Configurações do Aplicativo

| Parâmetro | Descrição | Default |
|-----------|-----------|---------|
| `config.logLevel` | Nível de log | `INFO` |
| `config.kafka.bootstrapServers` | Kafka brokers | `kafka.neural-hive-mind.svc:9092` |
| `config.kafka.topic` | Tópico para consumir | `ticket.completed` |
| `config.mongodb.url` | URL do MongoDB | `mongodb://mongodb:27017` |
| `config.mongodb.databaseName` | Nome do database | `neural_hive` |
| `config.optimization.enableAutoApply` | Auto-aplicar otimizações | `false` |

## Requirements

- Kubernetes 1.19+
- Helm 3.0+
- Kafka (neural-hive-mind stack)
- MongoDB (neural-hive-mind stack)

## Upgrade

```bash
helm upgrade optimizer-agents ./helm/optimizer-agents
```

## Uninstall

```bash
helm uninstall optimizer-agents
```

## Troubleshooting

### Ver status do deployment
```bash
kubectl get deployment optimizer-agents -n neural-hive-mind
```

### Ver logs
```bash
kubectl logs -f deployment/optimizer-agents -n neural-hive-mind
```

### Ver eventos Kafka
```bash
kubectl exec -it deployment/optimizer-agents -n neural-hive-mind -- \
  kafka-console-consumer --bootstrap-server kafka:9092 --topic ticket.completed --from-beginning
```
