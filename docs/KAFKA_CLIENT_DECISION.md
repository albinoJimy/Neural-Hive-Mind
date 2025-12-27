# Decisão Arquitetural: Clientes Kafka no Neural Hive-Mind

## Contexto
O projeto tinha uso simultâneo de `confluent-kafka` e `aiokafka` em vários serviços, causando:
- Conflitos de dependências transitivas (ambos dependem de kafka-python)
- Aumento desnecessário do tamanho de imagens Docker (~50MB por serviço)
- Confusão sobre qual cliente usar em novos serviços

## Decisão

### Usar aiokafka para:
- Serviços que precisam de **async/await nativo** com FastAPI
- Consumo/produção simples de mensagens JSON
- **Serviços:** queen-agent, analyst-agents, guard-agents, self-healing-engine, code-forge

### Usar confluent-kafka para:
- Serviços que precisam de **Schema Registry** e serialização Avro
- Integração com Confluent Platform
- **Serviços:** consensus-engine, gateway-intencoes, orchestrator-dynamic, worker-agents, optimizer-agents, semantic-translation-engine, execution-ticket-service

## Versões Padronizadas
- `aiokafka==0.10.0` (suporta Kafka 3.x)
- `confluent-kafka==2.3.0` (versão estável com Schema Registry)

## Consequências
✅ Redução de ~50MB por imagem Docker
✅ Eliminação de conflitos de dependências
✅ Clareza arquitetural
⚠️ Serviços async não podem usar Schema Registry diretamente (usar fastavro se necessário)
