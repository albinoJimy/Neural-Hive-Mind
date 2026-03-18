# Spec Requirements Document

> Spec: GAPS-06 MCP Servers Integration
> Created: 2026-03-18
> Status: Planning
> Epic: Neural-Hive-Mind GAPS-06

## Overview

Completar a integração do Model Context Protocol (MCP) no Neural-Hive-Mind, permitindo que agentes especializados (Scout, Optimizer, Guard, etc.) interajam com ferramentas externas através de uma camada padronizada. Esta integração habilita orquestração dinâmica de tools via Queen Agent e fornece SDK para agentes especializados.

## User Stories

### 1. Scout Agent com MCP Tools

Como Scout Agent, quero acessar ferramentas MCP para análise de código (SonarQube, Trivy), para que eu possa fornecer insights de qualidade e segurança nas minhas explorações.

**Workflow:**
1. Scout Agent solicita análise ao Queen Agent
2. Queen Agent consulta MCP Tool Catalog
3. MCP Tool Catalog roteia para SonarQube/Trivy MCP Servers
4. Resultados são agregados e retornados ao Scout Agent
5. Scout Agent enriquece recomendações com dados de qualidade/segurança

### 2. Queen Agent Orquestra Tools MCP

Como Queen Agent, quero orquestrar múltiplas chamadas a ferramentas MCP em paralelo, para que eu possa otimizar a execução de tarefas complexas.

**Workflow:**
1. Tarefa complexa chega ao Queen Agent
2. Queen Agent identifica ferramentas necessárias via MCP Tool Catalog
3. Múltiplas chamadas são disparadas em paralelo
4. Resultados são agregados e validados
5. Resposta consolidada é retornada ao solicitante

### 3. Agente Especializado Usa SDK

Como desenvolvedor de agentes especializados, quero um SDK consistente para interagir com MCP, para que eu possa integrar ferramentas externas sem duplicar código.

**Workflow:**
1. Agente especializado importa `neural_hive_mcp_sdk`
2. Configura client MCP com credenciais
3. Chama `execute_tool()` com nome e parâmetros
4. Recebe resposta tipada e tratada
5. Processa resultado sem se preocupar com protocolo MCP

## Spec Scope

1. **Scout MCP Server** - Expõe ferramentas de descoberta de código (list_files, search_code, analyze_structure)
2. **Optimizer MCP Server** - Expõe ferramentas de otimização (suggest_refactors, analyze_performance, optimize_queries)
3. **Queen Agent ↔ MCP Integration** - Orquestração de tools via Queen Agent com paralelismo e agregação
4. **MCP Client SDK** - Biblioteca `neural_hive_mcp_sdk` para uso por agentes especializados
5. **Testes E2E** - Suíte de testes de integração end-to-end para MCP

## Out of Scope

- Implementação de novos adapters (REST, CLI, Container já existem)
- UI/Web dashboard para MCP Tool Catalog
- Integração com ferramentas externas não listadas
- Modificação do protocolo MCP core

## Expected Deliverable

1. Scout MCP Server funcional com 3+ ferramentas de descoberta de código
2. Optimizer MCP Server funcional com 3+ ferramentas de otimização
3. Queen Agent orquestrando calls MCP com paralelismo
4. SDK `neural_hive_mcp_sdk` instalável via pip
5. 100+ testes passando (unit + integration + E2E)
