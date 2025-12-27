# Versões Canônicas de Dependências - Neural Hive-Mind

Este documento consolida os pinos finais usados pelos serviços e bibliotecas internas. Em caso de divergência, `versions.txt` é a fonte de verdade.

## Pinos Canônicos (principais)

| Categoria | Dependência | Versão |
|-----------|-------------|--------|
| Web | fastapi | 0.104.1 |
| Web | uvicorn[standard] | 0.24.0 |
| Validação | pydantic | 2.5.3 |
| Config | pydantic-settings | 2.1.0 |
| Kafka | confluent-kafka | 2.3.0 |
| Avro | avro-python3 | 1.10.2 |
| Avro | fastavro | 1.9.4 |
| gRPC | grpcio / grpcio-tools / grpcio-health-checking / grpcio-reflection | 1.75.1 |
| Protobuf | protobuf | 5.27.0 |
| Observabilidade | opentelemetry-* (api, sdk, exporters) | 1.21.0 |
| Observabilidade | opentelemetry-instrumentation-* | 0.42b0 |
| Observabilidade | neural_hive_observability | 1.1.0 |
| Logging | structlog | 23.2.0 |
| Prometheus | prometheus-client | 0.19.0 |
| HTTP | httpx | 0.25.2 |
| Redis | redis[hiredis] | 5.0.1 |
| MongoDB | pymongo | 4.6.1 |
| MongoDB | motor | 3.3.2 |
| Numérico | numpy | 1.26.2 |
| Numérico | pandas | 2.1.3 |
| Numérico | scipy | 1.11.4 |
| ML | scikit-learn | 1.5.2 |
| ML | mlflow | 2.9.0 |
| Deep Learning | torch | 2.1.2 |
| Deep Learning | torchaudio | 2.1.2 |
| NLP | sentence-transformers | 2.3.1 |
| NLP | spacy | 3.7.2 |
| Vetorização | faiss-cpu | 1.7.4 |

## OpenTelemetry Collector
- Versão: **0.89.0**
- Chart Helm: **0.66.0**
- Endpoint: `http://opentelemetry-collector.observability.svc.cluster.local:4317`

## Status de Normalização
- ✅ Serviços: 19/19 atualizados para os pinos acima
- ✅ Bibliotecas internas: neural_hive_observability, neural_hive_specialists, neural_hive_integration alinhadas
- ✅ Base images: python-specialist-base e python-mlops-base atualizadas para versões fixas
- ✅ Arquivo central `versions.txt` atualizado para 1.0.7 (2025-12-20)

## Referência
- Fonte de verdade: `versions.txt`
- Observabilidade: ver seção OpenTelemetry em `versions.txt`
- Kafka/Avro: seguir versões acima para evitar conflitos de serialização
