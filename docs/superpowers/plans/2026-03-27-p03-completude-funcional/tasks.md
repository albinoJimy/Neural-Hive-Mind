# Spec Tasks — P03 Completude Funcional

## Tasks

### Worker Agents (40h)

- [ ] 1. BUILD Executor
  - [ ] 1.1 Escrever testes para Code Forge integration
  - [ ] 1.2 Implementar trigger_pipeline() real
  - [ ] 1.3 Implementar wait_for_completion() real
  - [ ] 1.4 Remover fallback simulated
  - [ ] 1.5 Testes E2E com pipeline real

- [ ] 2. DEPLOY Executor
  - [ ] 2.1 Escrever testes para ArgoCD integration
  - [ ] 2.2 Implementar sync_wave() real
  - [ ] 2.3 Implementar wait_for_health() real
  - [ ] 2.4 Remover fallback simulated
  - [ ] 2.5 Testes E2E com deploy real

- [ ] 3. TEST Executor
  - [ ] 3.1 Escrever testes para GitHub Actions integration
  - [ ] 3.2 Implementar trigger_workflow() real
  - [ ] 3.3 Implementar wait_for_results() real
  - [ ] 3.4 Remover fallback simulated
  - [ ] 3.5 Testes E2E com CI real

- [ ] 4. VALIDATE Executor
  - [ ] 4.1 Escrever testes para OPA Gatekeeper
  - [ ] 4.2 Implementar validate_policy() real
  - [ ] 4.3 Remover fallback simulated
  - [ ] 4.4 Testes E2E com policies reais

- [ ] 5. EXECUTE Executor
  - [ ] 5.1 Escrever testes para Docker/K8s client
  - [ ] 5.2 Implementar run_container() real
  - [ ] 5.3 Implementar wait_for_exit() real
  - [ ] 5.4 Remover fallback simulated
  - [ ] 5.5 Testes E2E com execução real

- [ ] 6. QUERY Executor
  - [ ] 6.1 Escrever testes para DB clients
  - [ ] 6.2 Implementar execute_query() MongoDB real
  - [ ] 6.3 Implementar execute_query() Redis real
  - [ ] 6.4 Remover fallback simulated
  - [ ] 6.5 Testes E2E com queries reais

- [ ] 7. TRANSFORM Executor
  - [ ] 7.1 Escrever testes para transform pipeline
  - [ ] 7.2 Implementar apply_pandas() real
  - [ ] 7.3 Implementar apply_spark() real
  - [ ] 7.4 Remover fallback simulated
  - [ ] 7.5 Testes E2E com transformações reais

- [ ] 8. COMPENSATE Executor
  - [ ] 8.1 Escrever testes para rollback logic
  - [ ] 8.2 Implementar execute_rollback() real
  - [ ] 8.3 Implementar verify_rollback() real
  - [ ] 8.4 Remover fallback simulated
  - [ ] 8.5 Testes E2E com rollback real

### Scout Agents (20h)

- [ ] 9. Kafka Consumer Real
  - [ ] 9.1 Escrever testes para Kafka consumer
  - [ ] 9.2 Implementar consumo de tópicos reais
  - [ ] 9.3 Implementar signal detection
  - [ ] 9.4 Publicar sinais para Kafka

- [ ] 10. Service Registry Client
  - [ ] 10.1 Escrever testes para gRPC client
  - [ ] 10.2 Implementar register() real
  - [ ] 10.3 Implementar heartbeat() real
  - [ ] 10.4 Testes E2E com registry real

- [ ] 11. Pheromone Client
  - [ ] 11.1 Escrever testes para pheromone client
  - [ ] 11.2 Implementar publish_pheromone() real
  - [ ] 11.3 Implementar subscribe_pheromone() real
  - [ ] 11.4 Testes E2E com pheromones reais

- [ ] 12. ML Signal Detection
  - [ ] 12.1 Escrever testes para ML models
  - [ ] 12.2 Substituir heurísticas por modelo ML
  - [ ] 12.3 Treinar modelo com dados históricos
  - [ ] 12.4 Validar performance

### Code Forge MCP (15h)

- [ ] 13. MCP Tool Catalog Integration
  - [ ] 13.1 Ler INTEGRATION_MCP.md
  - [ ] 13.2 Escrever testes para MCP client
  - [ ] 13.3 Modificar template_selector.py
  - [ ] 13.4 Modificar code_composer.py
  - [ ] 13.5 Modificar validator.py
  - [ ] 13.6 Testes E2E com MCP real

### Proto Compilation (5h)

- [ ] 14. Protos Pendentes
  - [ ] 14.1 Compilar protos analyst-agents
  - [ ] 14.2 Compilar protos optimizer-agents
  - [ ] 14.3 Verificar imports funcionam
  - [ ] 14.4 Testar gRPC communication

### Verificação Final

- [ ] 15. Integração Geral
  - [ ] 15.1 Rodar testes E2E completos
  - [ ] 15.2 Verificar zero fallbacks simulados
  - [ ] 15.3 Documentar integrações
  - [ ] 15.4 Commit e push
