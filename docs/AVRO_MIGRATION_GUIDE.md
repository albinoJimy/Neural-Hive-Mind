# Avro Migration Guide

## Overview
- Objetivo: padronizar serialização Kafka em Avro com Schema Registry, garantindo validação de schema, compatibilidade e melhor performance.
- Serviços afetados: `orchestrator-dynamic`, `execution-ticket-service`, `worker-agents`.
- Padrão adotado: `confluent-kafka` síncrono com wrappers assíncronos (`run_in_executor`) + `SchemaRegistryClient`.
- Schema Avro: `schemas/execution-ticket/execution-ticket.avsc`.

## Breaking Changes
- `aiokafka` removido; todos os producers/consumers agora usam `confluent-kafka`.
- Serialização muda de JSON para Avro (com fallback para JSON quando Schema Registry indisponível).
- Operações Kafka são síncronas; chamadas assíncronas usam executors para não bloquear o loop.
- Dependência explícita de Schema Registry em tempo de execução.

## Configuration
- Variável obrigatória: `KAFKA_SCHEMA_REGISTRY_URL` (ex.: `http://schema-registry.neural-hive-kafka.svc.cluster.local:8081`).
- Exemplos:
  - Local: `KAFKA_BOOTSTRAP_SERVERS=localhost:9092`, `KAFKA_SCHEMA_REGISTRY_URL=http://localhost:8081`.
  - Produção: usar valores do Helm (`config.kafka.schemaRegistryUrl`) que já propagam para ConfigMaps.
- Fallback: quando o Schema Registry não responde na inicialização, os serviços usam JSON para manter compatibilidade (sem validação de schema).

## Testing
- Subir Kafka + Schema Registry com `docker-compose-test.yml`.
- Executar testes de integração:
  - `services/orchestrator-dynamic/tests/test_kafka_avro_serialization.py`
  - `services/execution-ticket-service/tests/test_ticket_consumer_avro.py`
  - `services/worker-agents/tests/test_kafka_ticket_consumer_avro.py`
- Defina `RUN_KAFKA_INTEGRATION_TESTS=1` para habilitar os testes; topics são criados sob demanda.
- Verifique validação de schema e roundtrip Avro; use `kafkacat` ou `kafka-console-consumer` para inspecionar bytes se necessário.

## Deployment
- Atualize Helm Values com `schemaRegistryUrl` (já aplicado para os três charts).
- Confirme conectividade para `schema-registry.neural-hive-kafka.svc.cluster.local:8081` antes do rollout.
- Rollback: se o Schema Registry falhar, o fallback JSON mantém compatibilidade, mas sem validação; restaure o serviço anterior ou o Registry.

## References
- Schema: `schemas/execution-ticket/execution-ticket.avsc`.
- Implementações: `services/gateway-intencoes/src/kafka/producer.py`, `services/consensus-engine/src/producers/decision_producer.py`.
- Libs: `confluent-kafka`, `fastavro`.
