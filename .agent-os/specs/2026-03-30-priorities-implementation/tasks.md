# Spec Tasks

## Tasks

### P0 - CRÍTICO (1-2 semanas)

- [ ] 1. Epic A: Aumentar Cobertura de Testes (9.41% → 60%)
  - [ ] 1.1 Criar testes para semantic-translation-engine (50+ testes)
  - [ ] 1.2 Criar testes para consensus-engine (50+ testes)
  - [ ] 1.3 Criar testes para approval-service (30+ testes)
  - [ ] 1.4 Criar testes para gateway-intencoes (40+ testes)
  - [ ] 1.5 Criar testes para neural_hive_domain (criar dir tests/)
  - [ ] 1.6 Verificar cobertura de testes com pytest-cov

- [ ] 2. Epic B: Remover CORS Wildcards
  - [ ] 2.1 Corrigir architect-agent CORS (app.py:28)
  - [ ] 2.2 Corrigir MCP Servers CORS (5 serviços)
  - [ ] 2.3 Corrigir .env.example files (6 serviços)
  - [ ] 2.4 Adicionar validação de CORS em produção (cors.py)

- [ ] 3. Epic C: Feature Store Funcional
  - [ ] 3.1 Criar Feature Store Service (main.py com API REST)
  - [ ] 3.2 Criar Feature Computation Pipeline (26 features)
  - [ ] 3.3 Integração com Approval Service (feature_store_client.py)
  - [ ] 3.4 Criar testes do Feature Store (30+ testes)

- [ ] 4. Epic D: Integração Online Learning
  - [ ] 4.1 Criar Consumer Kafka de Feedback (feedback_consumer.py)
  - [ ] 4.2 Criar wrapper para IncrementalLearner (online_learning_service.py)
  - [ ] 4.3 Criar Scheduler de Retreino (retraining_scheduler.py)
  - [ ] 4.4 Criar testes de Online Learning (20+ testes)

### P1 - IMPORTANTE (3-4 semanas)

- [ ] 5. Epic E: Helm Charts para Serviços Core
  - [ ] 5.1 Criar Helm Chart para gateway-intencoes
  - [ ] 5.2 Criar Helm Chart para consensus-engine
  - [ ] 5.3 Criar Helm Chart para orchestrator-dynamic
  - [ ] 5.4 Criar Helm Chart para approval-service
  - [ ] 5.5 Criar Helm Chart para worker-agents
  - [ ] 5.6 Criar Helm Chart para queen-agent

- [ ] 6. Epic F: NotImplementedError & Dívida Técnica
  - [ ] 6.1 Resolver NotImplementedError em code-forge (2 ocorrências)
  - [ ] 6.2 Resolver NotImplementedError em risk_scoring (1 ocorrência)
  - [ ] 6.3 Completar TODOs em optimizer-agents (4 TODOs)
  - [ ] 6.4 Completar TODO em sla-management-system (1 TODO)
  - [ ] 6.5 Implementar stubs em self-healing-engine (5 pass)

- [ ] 7. Epic G: Activar Features Fase 3
  - [ ] 7.1 Activar Active Learning em produção (settings.py)
  - [ ] 7.2 Activar Evolution Hooks (specialist-evolution settings.py)
  - [ ] 7.3 Activar Chaos Engineering em staging (self-healing settings.py)

- [ ] 8. Epic H: OPA Gatekeeper Webhook
  - [ ] 8.1 Criar OPA Gatekeeper Configuration (config.yaml)
  - [ ] 8.2 Criar ValidatingWebhookConfiguration
  - [ ] 8.3 Criar testes de OPA Policies (17 policies)

### P2 - DESEJÁVEL (1-2 meses)

- [ ] 9. Epic I: READMEs para Serviços Sem Documentação
  - [ ] 9.1 Criar README para approval-service
  - [ ] 9.2 Criar README para queen-agent
  - [ ] 9.3 Criar README para guard-agents
  - [ ] 9.4 Criar README para specialist-business
  - [ ] 9.5 Criar README para specialist-technical
  - [ ] 9.6 Criar README para specialist-architecture
  - [ ] 9.7 Criar README para specialist-behavior
  - [ ] 9.8 Criar README para specialist-evolution
  - [ ] 9.9 Criar README para explainability-api
  - [ ] 9.10 Criar README para mcp-servers

- [ ] 10. Epic J: Consumers para Tópicos Kafka Órfãos
  - [ ] 10.1 Criar consumer para insights.analyzed (orchestrator-dynamic)
  - [ ] 10.2 Criar consumer para exploration-signals (scout-agents)
  - [ ] 10.3 Criar consumer para security-incidents (guard-agents)
  - [ ] 10.4 Criar consumer para strategic.decisions (orchestrator-dynamic)
  - [ ] 10.5 Criar consumer para optimization.applied (optimizer-agents)

- [ ] 11. Epic K: Modelos ML para Especialistas
  - [ ] 11.1 Criar script train_business_specialist.py
  - [ ] 11.2 Criar script train_technical_specialist.py
  - [ ] 11.3 Criar script train_architecture_specialist.py
  - [ ] 11.4 Criar script train_behavior_specialist.py
  - [ ] 11.5 Criar script train_evolution_specialist.py
  - [ ] 11.6 Integrar modelos nos serviços especialistas

- [ ] 12. Epic L: Multi-região Deploy
  - [ ] 12.1 Criar Terraform Multi-Region Configuration
  - [ ] 12.2 Criar Kubernetes Multi-Cluster configuration
  - [ ] 12.3 Criar Database Replication configuration

---

## Ordem de Execução

1. **P0 - Paralelo quando possível:**
   - Epic A (Testes) - independente
   - Epic B (CORS) - independente
   - Epic C (Feature Store) - C003 depende de C001-C002
   - Epic D (Online Learning) - D001 depende de A (approval-service testes)

2. **P1 - Sequencial onde indicado:**
   - Epic E (Helm) - independente
   - Epic F (Dívida) - F005 depende de G
   - Epic G (Activar Fase 3) - depende de D e F
   - Epic H (OPA) - H003 depende de H001-H002

3. **P2 - Paralelo quando possível:**
   - Epic I (READMEs) - independente
   - Epic J (Kafka) - independente
   - Epic K (Modelos ML) - K006 depende de K001-K005
   - Epic L (Multi-região) - L001 depende de L002, L002 depende de L003

---

## checkpoints de Revisão

- **Checkpoint 1** (após P0): Testes ≥60%, CORS=0 wildcards, Feature Store funcional, Online Learning integrado
- **Checkpoint 2** (após P1): Helm=12 charts, Dívida resolvida, Fase 3 activada, OPA configurado
- **Checkpoint 3** (após P2): READMEs completos, Kafka gaps fechados, modelos treinados, multi-região OK
