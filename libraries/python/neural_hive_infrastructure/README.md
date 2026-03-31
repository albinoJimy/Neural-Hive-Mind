# Neural Hive Infrastructure

Biblioteca de configurações base partilhadas por todos os serviços da plataforma Neural Hive-Mind.

## Instalação

```bash
pip install -e libraries/python/neural_hive_infrastructure/
```

## Uso

### Configurações Básicas

```python
from neural_hive_infrastructure import BaseInfrastructureSettings, get_settings

class MyServiceSettings(BaseInfrastructureSettings):
    # Configurações específicas do serviço
    my_custom_feature_enabled: bool = True
    my_api_timeout_seconds: int = 30

settings = get_settings(MyServiceSettings)
```

### Acesso às Configurações

```python
# Configurações da aplicação
print(settings.service_name)        # 'nhm-service'
print(settings.environment)         # 'development'
print(settings.log_level)           # 'INFO'

# Configurações de infraestrutura
print(settings.kafka_bootstrap_servers)
print(settings.mongodb_uri)
print(settings.redis_cluster_nodes)
print(settings.otel_endpoint)
```

### Métodos Helper

```python
# Configurações Kafka para aiokafka
kafka_config = settings.get_kafka_config()

# Configurações MongoDB
mongodb_config = settings.get_mongodb_config()

# Configurações Redis
redis_config = settings.get_redis_config()
```

## Classes Disponíveis

- `BaseInfrastructureSettings` - Classe base com todas as configurações comuns
- `KafkaSettings` - Configurações Kafka standalone
- `MongoDBSettings` - Configurações MongoDB standalone
- `RedisSettings` - Configurações Redis standalone
- `OpenTelemetrySettings` - Configurações OTEL standalone
- `GRPCSettings` - Configurações gRPC standalone
- `SPIFFESettings` - Configurações SPIFFE/SPIRE standalone
- `VaultSettings` - Configurações Vault standalone
- `ObservabilitySettings` - Métricas, tracing, logging

## Validações Automáticas

- HTTPS obrigatório em produção/staging para endpoints externos
- Senha Redis obrigatória em produção
- Níveis de log validados
- Formato de URIs validadas
- Fail-open Vault apenas em desenvolvimento
