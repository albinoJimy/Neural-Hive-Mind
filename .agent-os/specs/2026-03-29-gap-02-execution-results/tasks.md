# Tasks - GAP-02: Execution Results Consumer

## Tasks

- [ ] 1. Atualizar Schema Execution Result
  - [ ] 1.1 Ler schema atual `schemas/execution-result/execution-result.avsc`
  - [ ] 1.2 Adicionar campo `plan_id` (string)
  - [ ] 1.3 Adicionar campo `workflow_id` (null, string)
  - [ ] 1.4 Adicionar campo `correlation_id` (null, string)
  - [ ] 1.5 Atualizar schema version de 1 para 2
  - [ ] 1.6 Validar schema com avro-tools
  - [ ] 1.7 Commit: "feat(schema): atualizar execution-result com plan_id e workflow_id"

- [ ] 2. Criar Consumer Kafka Execution Result
  - [ ] 2.1 Criar arquivo `services/orchestrator-dynamic/src/consumers/execution_result_consumer.py`
  - [ ] 2.2 Implementar classe `ExecutionResultConsumer`
  - [ ] 2.3 Implementar método `async initialize()` para AIOKafkaConsumer
  - [ ] 2.4 Implementar método `async start()` para loop de consumo
  - [ ] 2.5 Implementar método `async _process_result(message)` para processar mensagens
  - [ ] 2.6 Implementar método `async _get_workflow_for_ticket()` para cache lookup
  - [ ] 2.7 Implementar método `async _send_workflow_signal()` para signal Temporal
  - [ ] 2.8 Implementar método `def _deserialize()` para deserialização
  - [ ] 2.9 Implementar método `async stop()` para shutdown gracioso
  - [ ] 2.10 Adicionar tratamento de erros e logging
  - [ ] 2.11 Commit: "feat(orchestrator): adicionar consumer execution.results"

- [ ] 3. Implementar Cache de Workflow ID
  - [ ] 3.1 Ler `services/orchestrator-dynamic/src/activities/ticket_generation.py`
  - [ ] 3.2 Implementar função `cache_workflow_mapping()`
  - [ ] 3.3 Adicionar chamada após `publish_ticket()` em `generate_execution_ticket()`
  - [ ] 3.4 Validar cache key pattern: `workflow:by:ticket:{ticket_id}`
  - [ ] 3.5 Validar TTL de 24h (86400 segundos)
  - [ ] 3.6 Commit: "feat(orchestrator): cachear mapeamento ticket→workflow no Redis"

- [ ] 4. Atualizar Producer Worker Agents
  - [ ] 4.1 Ler `services/worker-agents/src/clients/kafka_result_producer.py`
  - [ ] 4.2 Adicionar parâmetros `plan_id`, `workflow_id`, `correlation_id` em `publish_result()`
  - [ ] 4.3 Incluir novos campos no payload
  - [ ] 4.4 Atualizar schema_version para 2
  - [ ] 4.5 Commit: "feat(worker): adicionar metadata de workflow em execution.results"

- [ ] 5. Adicionar Configurações
  - [ ] 5.1 Ler `services/orchestrator-dynamic/src/config/settings.py`
  - [ ] 5.2 Adicionar `execution_result_consumer_enabled`
  - [ ] 5.3 Adicionar `execution_result_consumer_group`
  - [ ] 5.4 Adicionar `execution_result_workers`
  - [ ] 5.5 Commit: "feat(orchestrator): adicionar configs para execution result consumer"

- [ ] 6. Integrar Consumer no Main
  - [ ] 6.1 Ler `services/orchestrator-dynamic/src/main.py`
  - [ ] 6.2 Adicionar campos `execution_result_consumer` e `execution_result_task` em AppState
  - [ ] 6.3 Adicionar import de `ExecutionResultConsumer`
  - [ ] 6.4 Adicionar inicialização no lifespan (startup)
  - [ ] 6.5 Adicionar task `asyncio.create_task()` para start()
  - [ ] 6.6 Adicionar shutdown no lifespan (shutdown)
  - [ ] 6.7 Commit: "feat(orchestrator): integrar execution result consumer no lifespan"

- [ ] 7. Escrever Testes
  - [ ] 7.1 Criar `tests/unit/test_execution_result_consumer.py`
  - [ ] 7.2 Testar `process_result()` com mock Temporal
  - [ ] 7.3 Testar `_get_workflow_for_ticket()` com mock Redis
  - [ ] 7.4 Testar `_send_workflow_signal()` com mock Temporal
  - [ ] 7.5 Criar `tests/integration/test_execution_result_flow.py`
  - [ ] 7.6 Testar feedback loop completo (Kafka → Consumer → Temporal)
  - [ ] 7.7 Commit: "test(orchestrator): adicionar testes do execution result consumer"

- [ ] 8. Validação E2E
  - [ ] 8.1 Subir ambiente local com docker-compose
  - [ ] 8.2 Iniciar workflow de teste
  - [ ] 8.3 Publicar execution.result via Kafka
  - [ ] 8.4 Verificar signal recebido no workflow Temporal
  - [ ] 8.5 Verificar cache Redis preenchido
  - [ ] 8.6 Verificar métricas Prometheus
  - [ ] 8.7 Commit: "test(e2e): validar feedback loop execution.results"

- [ ] 9. Atualizar Documentação
  - [ ] 9.1 Atualizar diagrama de arquitetura com novo consumer
  - [ ] 9.2 Documentar signal flow `ticket_completed`
  - [ ] 9.3 Atualizar README do orchestrator-dynamic
  - [ ] 9.4 Commit: "docs(orchestrator): documentar execution result consumer"

- [ ] 10. Deploy
  - [ ] 10.1 Criar branch `feat/GAP-02-execution-results-consumer`
  - [ ] 10.2 Fazer push de todos os commits
  - [ ] 10.3 Criar PR com descrição detalhada
  - [ ] 10.4 Aguardar CI/CD passar
  - [ ] 10.5 Merge para main
  - [ ] 10.6 Monitorar deploy em produção
  - [ ] 10.7 Validar logs e métricas
