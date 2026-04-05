# Spec: CI/CD Pipelines

> **Data:** 2026-04-04
> **Status:** Planning
> **Prioridade:** 🔴 CRÍTICA

## Resumo Executivo

Implementar pipelines de CI/CD completos e padronizados para todos os 40 serviços do Neural Hive Mind, garantindo qualidade de código, segurança, testes automatizados e deploy confiável.

## Contexto da Análise

**Status Atual:** ⚠️ Parcial - 35+ workflows existentes mas desorganizados

**Setup Identificado:**
- GitHub Actions como ferramenta CI/CD
- GHCR (ghcr.io/albinojimy/neural-hive-mind) como registry
- 40 serviços com Dockerfile
- 48 Helm charts disponíveis
- ruff, black, mypy configurados
- pytest com coverage

## User Stories

### US-CI-001: Pipeline de Build Automatizado
Como engenheiro de DevOps, quero pipelines de build que detectem mudanças e buildem apenas serviços modificados.

**Workflow:**
1. Push para branch
2. Detecta arquivos modificados
3. Build em paralelo (max 6)
4. Push imagens para GHCR
5. Gera tags: latest, SHA, branch, versão semântica

### US-CI-002: Pipeline de Testes Automatizados
Como desenvolvedor, quero testes automáticos em todos os níveis (unit, integration, e2e).

**Requisitos:**
- Testes unitários em Python 3.11 e 3.12
- Testes de integração com dependencies (mongo, redis, kafka)
- Coverage report agregado
- Quality gate enforceable (coverage > 80%)

### US-CI-003: Pipeline de Segurança
Como engenheiro de segurança, quero scans de vulnerabilidade automatizados.

**Requisitos:**
- Trivy filesystem scan
- Trivy image scan
- Upload SARIF para GitHub Security
- Falha em CRITICAL vulnerabilities

### US-CI-004: Pipeline de Deploy Automatizado
Como engenheiro de DevOps, quero deploy automatizado para staging/production.

**Workflow:**
- Trigger após build bem-sucedido
- Determina ambiente por branch (main→prod, develop→staging)
- Atualiza deployment via Helm upgrade
- Verifica health check
- Rollback automático em falha

## Escopo

### IN SCOPE
1. Template de CI reutilizável
2. Workflows para cada categoria (core, agents, MCP, specialized)
3. Ambientes: dev, staging, production
4. Integrações: GHCR, Codecov, GitHub Security, Kubernetes

### OUT OF SCOPE
- Serviços sem Dockerfile
- Criação de testes
- Configuração de clusters Kubernetes
- Monitoramento pós-deploy

## Tickets

### Fase 1: Fundação (1 semana)
- [ ] 1.1 Criar Template de CI Reutilizável
- [ ] 1.2 Criar Template de Testes Reutilizável
- [ ] 1.3 Criar Pipeline de Linting Unificado

### Fase 2: Implementação (2 semanas)
- [ ] 2.1 Pipelines para Serviços Core (9 serviços)
- [ ] 2.2 Pipelines para Serviços de Agentes (9 serviços)
- [ ] 2.3 Pipelines para Serviços MCP (13 servidores)
- [ ] 2.4 Pipelines para Serviços Especializados (5 serviços)

### Fase 3: Deploy (1 semana)
- [ ] 3.1 Pipeline de Deploy para Staging
- [ ] 3.2 Pipeline de Deploy para Production
- [ ] 3.3 Pipeline de Rollback

### Fase 4: Melhorias (1 semana)
- [ ] 4.1 Cache e Otimização
- [ ] 4.2 Notificações e Dashboards
- [ ] 4.3 Documentação

## Estratégia de Ambientes

| Ambiente | Branch | Namespace | Auto-deploy |
|----------|--------|-----------|-------------|
| Development | feature/* | neural-hive-dev | Não |
| Staging | develop | neural-hive-staging | Sim |
| Production | main | neural-hive-prod | Não (manual) |

## Estimativa Total

**16 tickets | 5 semanas**

## Critérios de Aceite

- [ ] Todos 40 serviços têm CI/CD implementado
- [ ] Build incremental < 10 minutos
- [ ] Coverage global > 80%
- [ ] Zero vulnerabilidades CRITICAL
- [ ] Deploy staging < 5 minutos
- [ ] Deploy production < 15 minutos
- [ ] Rollback < 5 minutos

## Documentação Adicional

- **Tasks Detalhadas:** `tasks.md` (22 tickets decompostos)
- **Especificação Técnica:** `sub-specs/technical-spec.md` (arquitetura de workflows)
- **Resumo Executivo:** `spec-lite.md` (visão rápida)

---

*Spec criada por Claude Code - 2026-04-04*
