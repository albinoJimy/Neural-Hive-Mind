# Tasks - HA-001-PROBES

- [ ] 1. **Criar helper compartilhado em neural_hive_observability**
    - [ ] 1.1 Criar arquivo `health/startup.py` com helper
    - [ ] 1.2 Exportar helper em `__init__.py`
    - [ ] 1.3 Adicionar type hints e docstrings
    - [ ] 1.4 Testar helper localmente

- [ ] 2. **Adicionar /health/startup em serviços core (5 serviços)**
    - [ ] 2.1 consensus-engine - adicionar endpoint em src/main.py
    - [ ] 2.2 semantic-translation-engine - adicionar endpoint em src/main.py
    - [ ] 2.3 worker-agents - adicionar endpoint em src/main.py
    - [ ] 2.4 queen-agent - adicionar endpoint em src/main.py
    - [ ] 2.5 approval-service - adicionar endpoint em src/main.py

- [ ] 3. **Adicionar /health/startup em specialist services (5 serviços)**
    - [ ] 3.1 specialist-architecture - adicionar em http_server_fastapi.py
    - [ ] 3.2 specialist-business - adicionar em http_server_fastapi.py
    - [ ] 3.3 specialist-technical - adicionar em http_server_fastapi.py
    - [ ] 3.4 specialist-behavior - adicionar em http_server_fastapi.py
    - [ ] 3.5 specialist-evolution - adicionar em http_server_fastapi.py

- [ ] 4. **Adicionar /health/startup em serviços restantes (3 serviços)**
    - [ ] 4.1 scout-agents - adicionar endpoint
    - [ ] 4.2 self-healing-engine - adicionar endpoint
    - [ ] 4.3 analyst-agents - adicionar endpoint
    - [ ] 4.4 execution-ticket-service - adicionar endpoint

- [ ] 5. **Adicionar startupProbe nos helm charts**
    - [ ] 5.1 Adicionar startupProbe no template padrão
    - [ ] 5.2 Atualizar consensus-engine chart
    - [ ] 5.3 Atualizar semantic-translation-engine chart
    - [ ] 5.4 Atualizar worker-agents chart
    - [ ] 5.5 Atualizar outros charts conforme necessário

- [ ] 6. **Testes E2E**
    - [ ] 6.1 Criar teste para validar todos os /health/startup
    - [ ] 6.2 Validar resposta contém status, service, version, started_at
    - [ ] 6.3 Testar com serviços localmente
    - [ ] 6.4 Verificar todos os testes passam

- [ ] 7. **Documentação**
    - [ ] 7.1 Atualizar MEMORY.md com implementação
    - [ ] 7.2 Criar guia de health endpoints
    - [ ] 7.3 Atualizar roadmap se aplicável
