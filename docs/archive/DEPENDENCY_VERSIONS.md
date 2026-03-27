# Versões Canônicas de Dependências - Neural Hive-Mind

Este documento consolida os pinos finais usados pelos serviços e bibliotecas internas.
**Fonte de verdade:** `versions.txt`

## Atualização: 2025-12-18

### IMPORTANTE: Compatibilidade gRPC/Protobuf
- `grpcio-tools 1.68.1` requer `protobuf>=5.29.2`
- Todas as versões foram atualizadas para garantir compatibilidade

## Pinos Canônicos (principais)

| Categoria | Dependência | Versão |
|-----------|-------------|--------|
| Web | fastapi | 0.115.6 |
| Web | uvicorn[standard] | 0.34.0 |
| Validação | pydantic | 2.10.4 |
| Config | pydantic-settings | 2.7.1 |
| gRPC | grpcio / grpcio-tools / grpcio-health-checking / grpcio-reflection | 1.68.1 |
| Protobuf | protobuf | 5.29.2 |
| Kafka | confluent-kafka | 2.6.1 |
| Kafka | aiokafka | 0.12.0 |
| Avro | fastavro | 1.9.7 |
| Observabilidade | opentelemetry-* (api, sdk, exporters) | 1.39.1 |
| Observabilidade | opentelemetry-instrumentation-* | 0.60b1 |
| Observabilidade | neural_hive_observability | 1.2.0 |
| Logging | structlog | 24.4.0 |
| Prometheus | prometheus-client | 0.21.1 |
| HTTP | httpx | 0.28.1 |
| HTTP | aiohttp | 3.11.11 |
| Redis | redis[hiredis] | 5.2.1 |
| MongoDB | pymongo | 4.10.1 |
| MongoDB | motor | 3.6.0 |
| Numérico | numpy | 1.26.4 |
| Numérico | pandas | 2.2.3 |
| Numérico | scipy | 1.14.1 |
| ML | scikit-learn | 1.6.0 |
| ML | mlflow | 2.19.0 |
| Deep Learning | torch | 2.5.1 |
| NLP | sentence-transformers | 3.3.1 |

## Status de Normalização
- ✅ Serviços: Todos atualizados para os pinos acima
- ✅ Bibliotecas internas: neural_hive_observability, neural_hive_specialists, neural_hive_integration alinhadas
- ✅ Base images: python-specialist-base e python-mlops-base atualizadas

## Script de Normalização

Para normalizar todas as dependências, execute:

```bash
./scripts/normalize-dependencies.sh
```

## Referência
- Fonte de verdade: `versions.txt`
- Script de normalização: `scripts/normalize-dependencies.sh`
