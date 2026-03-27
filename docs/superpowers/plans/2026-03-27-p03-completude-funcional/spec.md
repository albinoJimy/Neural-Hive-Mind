# Spec Requirements Document

> Spec: P03 — Completude Funcional
> Created: 2026-03-27
> Status: Planning
> Priority: ALTA

---

## Overview

Transformar stubs e simulações em funcionalidades reais. Worker Agents, Scout Agents e Code Forge têm integrações documentadas mas não aplicadas, resultando em execução simulada em vez de real.

---

## User Stories

### Como utilizador do sistema
Eu quero que Worker Agents executem tarefas reais de build/deploy
Para que o Fluxo C (Orquestração) funcione em produção

**Workflow:**
1. Orchestrator envia execution ticket
2. Worker Agent recebe e executa tarefa real
3. Resultado real é retornado (não simulado)

### como analista de dados
Eu quero que Scout Agents consumam eventos reais de canais digitais
Para que sinais de negócio sejam detetados em tempo real

**Workflow:**
1. Canais digitais emitem eventos
2. Scout Agent consome eventos Kafka
3. Sinais são publicados para análise

### Como desenvolvedor
Eu quero que Code Forge use MCP Tool Catalog dinamicamente
Para que seleção de ferramentas seja baseada em contexto

**Workflow:**
1. Code Forge recebe cognitive plan
2. MCP Tool Catalog é consultado
3. Ferramentas ótimas são selecionadas

---

## Spec Scope

### B.1 Worker Agents (40h)
- BUILD executor com Code Forge real
- DEPLOY executor com ArgoCD/Flux
- TEST executor com GitHub Actions
- VALIDATE executor com OPA Gatekeeper
- EXECUTE executor com Docker/K8s
- QUERY executor com DB clients reais
- TRANSFORM executor com Pandas/Spark
- COMPENSATE executor com rollback real

### B.2 Scout Agents (20h)
- Kafka consumer real para eventos
- Service Registry gRPC client
- Pheromone client para publicação
- Modelos ML para signal detection

### B.3 Code Forge MCP (15h)
- Integration de MCP Tool Catalog
- Template selector dinâmico
- Code composer com MCP tools
- Validator com MCP validation

### B.4 Proto Compilation (5h)
- Protos do analyst-agents
- Protos do optimizer-agents

---

## Out of Scope

- Novos tipos de executores (fora de escopo)
- Refactoring de arquitetura (futuro)
- Performance optimization (fase seguinte)

---

## Expected Deliverable

1. Worker Agents executam tarefas reais (sem fallback simulado)
2. Scout Agents consomem eventos Kafka reais
3. Code Forge usa MCP Tool Catalog dinamicamente
4. Protos compilados para analyst/optimizer agents
5. Testes E2E validando integrações
