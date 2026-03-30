# Spec Requirements Document

> Spec: Implementação de Recomendações Prioritárias NHM
> Created: 2026-03-30
> Status: Planning

---

## Overview

Implementar 12 recomendações prioritárias identificadas na análise profunda do Neural-Hive-Mind para elevar a completude real de ~70% para ~90%, divididas em três níveis de prioridade: P0 (Crítico, 1-2 semanas), P1 (Importante, 3-4 semanas) e P2 (Desejável, 1-2 meses).

---

## User Stories

### Story 1: Aumentar Cobertura de Testes

Como **engenheiro de software**, eu quero **aumentar a cobertura de testes de 9.41% para 60%**, para **garantir qualidade e confiança no código**.

**Fluxo de trabalho:**
1. Executar testes existentes para identificar componentes sem cobertura
2. Criar testes unitários para componentes críticos (semantic-translation-engine, consensus-engine, approval-service, gateway-intencoes)
3. Criar testes de integração para Kafka, gRPC, Redis
4. Criar fixtures reutilizáveis para acelerar desenvolvimento de testes
5. Executar pytest com coverage para validar meta de 60%

**Problema resolvido:** Cobertura de testes extremamente baixa (9.41%) representa risco operacional crítico para um sistema de IA distribuído desta complexidade.

### Story 2: Remover CORS Wildcards

Como **engenheiro de segurança**, eu quero **remover configurações CORS wildcard de todos os serviços**, para **evitar ataques CSRF e acesso não autorizado cross-origin**.

**Fluxo de trabalho:**
1. Identificar serviços com `allow_origins=["*"]` (12 serviços)
2. Aplicar padrão `CORSConfig.get_origins_for_environment()` da biblioteca neural_hive_security
3. Configurar `IS_PUBLIC_API` para diferenciar serviços públicos de internos
4. Atualizar .env.example files para remover wildcards
5. Adicionar validação de CORS no startup que avisa em produção

**Problema resolvido:** Wildcards CORS em 12 serviços representam vulnerabilidade de segurança crítica para ataques CSRF.

### Story 3: Feature Store Funcional

Como **cientista de dados**, eu quero **um Feature Store funcional para computar e armazenar features**, para **alimentar modelos ML com dados consistentes**.

**Fluxo de trabalho:**
1. Criar serviço Feature Store com API REST (get/save/delete features)
2. Implementar pipeline de computação de features (26 tipos)
3. Configurar cache Redis com TTL e persistência MongoDB
4. Integrar Feature Store com Approval Service
5. Criar testes E2E para validar funcionalidade

**Problema resolvido:** Feature Store atual é apenas placeholder (237 LOC de definições), sem computação ou armazenamento real, bloqueando evolução de modelos ML.

### Story 4: Integração Online Learning

Como **engenheiro de ML**, eu quero **integrar Online Learning ao approval-service**, para **modelos aprenderem continuamente com feedback**.

**Fluxo de trabalho:**
1. Criar consumer Kafka para tópico `specialist_feedback`
2. Implementar wrapper para `IncrementalLearner` de ml_pipelines
3. Configurar scheduler de retreino (diário/semanal)
4. Implementar shadow validation antes de deploy
5. Criar testes de integração

**Problema resolvido:** Código de Online Learning existe mas está isolado, sem integração aos serviços, impedindo aprendizado contínuo em produção.

---

## Spec Scope

1. **Aumentar Cobertura de Testes (9.41% → 60%)**
   - Criar 200+ testes novos para 5 serviços críticos
   - Criar fixtures reutilizáveis
   - Testes de integração Kafka/gRPC/Redis

2. **Remover CORS Wildcards**
   - Corrigir 12 serviços com `allow_origins=["*"]`
   - Aplicar padrão `CORSConfig.get_origins_for_environment()`
   - Adicionar validação de CORS em produção

3. **Feature Store Funcional**
   - Criar serviço Feature Store com API REST
   - Implementar pipeline de computação de 26 features
   - Cache Redis + persistência MongoDB

4. **Integração Online Learning**
   - Consumer Kafka de feedback
   - Wrapper para IncrementalLearner
   - Scheduler de retreino automático

5. **Helm Charts para Serviços Core**
   - Criar 6 Helm charts (gateway, consensus, orchestrator, approval, worker, queen)
   - Configurar HPA, PodDisruptionBudget, resources

6. **Resolver NotImplementedError & Dívida Técnica**
   - Implementar 2 NotImplementedError em code-forge
   - Implementar 1 NotImplementedError em risk_scoring
   - Completar 4 TODOs em optimizer-agents
   - Completar 1 TODO em sla-management-system
   - Implementar 5 stubs em self-healing-engine

7. **Activar Features Fase 3**
   - Activar Active Learning em produção
   - Activar Evolution Hooks
   - Activar Chaos Engineering em staging

8. **OPA Gatekeeper Webhook**
   - Configurar webhook de admission
   - Activar 17 policies OPA
   - Criar testes de policies

9. **READMEs para Serviços Sem Documentação**
   - Criar 10 READMEs para serviços sem documentação

10. **Consumers para Tópicos Kafka Órfãos**
    - Criar 5 consumers para tópicos sem listener

11. **Modelos ML para Especialistas**
    - Criar 5 scripts de treino para especialistas
    - Integrar modelos nos serviços especialistas

12. **Multi-região Deploy**
    - Configurar Terraform para 2+ regiões
    - Configurar Kubernetes multi-cluster
    - Configurar replicação de bancos

---

## Out of Scope

- Refatoração de código existente (apenas correções críticas)
- Novas funcionalidades além das recomendadas
- Performance tuning (além do necessário para funcionamento)
- UI/Frontend changes
- Migração de banco de dados

---

## Expected Deliverable

1. **Cobertura de testes em 60%+** (pytest-cov report)
2. **Zero CORS wildcards** (grep retorna vazio)
3. **Feature Store funcional** (testes E2E passando)
4. **Online Learning integrado** (feedback loop funcionando)
5. **6 Helm charts criados** (find Chart.yaml retorna 12+)
6. **Zero NotImplementedError** (grep retorna vazio)
7. **READMEs para todos os serviços** (find README.md em todos)
8. **Consumers para tópicos Kafka órfãos** (20 gaps fechados)
9. **Modelos ML treinados para especialistas** (MLflow models)
10. **Completude global ~90%** (validação qualitativa)

---

## Referências

- Plano completo: `/home/jimy/.claude/plans/imperative-toasting-flute.md`
- Análise profunda: docs/ANALISE_COMPLETA_GERACAO_CODIGO_NHM.md
- Padrões de testes: services/orchestrator-dynamic/tests/conftest.py
- Padrões CORS: libraries/python/neural_hive_security/neural_hive_security/cors.py
- Feature Store base: libraries/python/neural_hive_specialists/feature_store.py
