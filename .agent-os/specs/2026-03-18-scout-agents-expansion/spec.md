# Spec Requirements Document

> Spec: Scout Agents Expansion (50% → 100%)
> Created: 2026-03-18
> Status: Planning

## Overview

Completar a implementação do Scout Agent Service, parte da Fase 2 do roadmap Neural-Hive-Mind, expandindo de 50% para 100% de cobertura funcional incluindo análise AST multi-linguagem, detecção de padrões avançada, documentação completa, Helm chart para deploy Kubernetes, dashboard Grafana e testes abrangentes.

## User Stories

### Como desenvolvedor do Neural-Hive-Mind

Como desenvolvedor do sistema NHM, eu quero que o Scout Agent Service esteja 100% completo e operacional, para que o Orchestrator Dynamic possa utilizá-lo para descobrir caminhos de solução ótimos antes de delegar tarefas aos Worker Agents.

**Workflow:**
1. Orchestrator recebe uma intenção que requer análise de código
2. Orchestrator invoca Scout Agent via API REST
3. Scout Agent explora o codebase usando AST parsing
4. Scout Agent detecta padrões de design e dependências
5. Scout Agent retorna descobertas estruturadas
6. Orchestrator usa descobertas para criar plano de execução

### Como operador de infraestrutura

Como operador responsável pelo deploy em Kubernetes, eu quero um Helm chart completo para o Scout Agent, para que possa fazer deploy com `helm install` e configurar recursos via valores YAML.

**Workflow:**
1. Operator executa `helm install scout-agents ./helm/scout-agents`
2. Pod é iniciado com limites de CPU/memória configuráveis
3. Service e ServiceMesh são criados automaticamente
4. Health checks garantem disponibilidade
5. Logs e métricas são exportados para observabilidade

### Como engenheiro de observabilidade

Como engenheiro responsável pela monitoring stack, eu quero um dashboard Grafana para Scout Agent, para que possa visualizar métricas de exploração, performance e health em tempo real.

**Workflow:**
1. Dashboard mostra taxa de explorações por segundo
2. Gráficos exibem latência P50/P95/P99
3. Contadores identificam patterns detectados
4. Alerts notificam anomalias
5. Debugging é facilitado com visualizações

## Spec Scope

1. **Expansão de AST Parsing Multi-Linguagem** - Suporte completo para TypeScript, JavaScript, YAML, JSON, Java, C#, Go, C/C++, e Rust (além de Python)
2. **Expansão de Pattern Discovery** - Detecção de 20+ padrões de design (Strategy, Observer, Adapter, Bridge, Composite, etc.)
3. **Signal Detection & Curiosity** - Sistema de pontuação de curiosidade para exploração autônoma
4. **Multi-Scout Coordination** - Múltiplos scouts explorando em paralelo com agregação de resultados
5. **Test Coverage** - Expansão de 41 para ~150 testes unitários e integração
6. **Documentation** - Documentação API completa, guias de uso e architecture decision records (ADRs)
7. **Helm Chart** - Chart Kubernetes com valores configuráveis, RBAC, ServiceMesh e HPA
8. **Grafana Dashboard** - Dashboard com painéis para métricas, latência, throughput e health
9. **Integration Tests** - Testes E2E com Docker Compose validando fluxos completos
10. **Performance Optimization** - Cache AST parsing, paralelização e rate limiting

## Out of Scope

- Refactoring arquitetural do Scout Agent Service (manter estrutura atual)
- Integração com LLMs para análise semântica (feature futura de Analyst Agents)
- Deploy em produção (apenas preparar artefatos)
- Migração de banco de dados (não aplicável - Scout é stateless)

## Expected Deliverable

1. Scout Agent Service com 100% dos endpoints implementados e documentados
2. 100+ testes passando (unitários + integração)
3. Helm chart instalável via `helm install`
4. Dashboard Grafana importável com painéis funcionais
5. Documentação API completa (OpenAPI/Swagger)
6. Coverage de código ≥80%
7. Performance: exploração de codebase médio (1000 arquivos) em <30s
