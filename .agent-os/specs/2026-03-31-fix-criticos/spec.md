# Spec Requirements Document

> Spec: Fix Críticos - Sprint 1
> Created: 2026-03-31
> Status: Planning

## Overview

Corrigir 45 issues críticos identificados na análise completa dos 26 serviços do Neural-Hive-Mind, focando inicialmente nos 16 issues P0 que bloqueiam a produção. O sprint é dividido em 4 epics principais: Test Críticos, Pydantic V2 Migration, datetime Migration, e FastMCP API Fix.

## User Stories

### Epic 1: Fix Test Críticos

Como desenvolvedor, quero corrigir os testes falhando em worker-agents, semantic-translation-engine e specialist-behavior, para que o CI/CD possa executar sem bloqueios.

**Workflow detalhado:**
1. Identificar causa raiz de cada falha de teste
2. Aplicar correção técnica apropriada
3. Executar testes para verificar sucesso
4. Documentar mudanças e commitar

### Epic 2: Pydantic V2 Migration

Como desenvolvedor, quero migrar todos os decorators @validator para @field_validator, para eliminar warnings de deprecção e garantir compatibilidade com Pydantic V2.

**Workflow detalhado:**
1. Mapear todos os arquivos com @validator
2. Converter decorators um por um
3. Testar cada serviço após migração
4. Commitar e validar em produção

### Epic 3: datetime.utcnow() Migration

Como desenvolvedor, quero migrar datetime.utcnow() para datetime.now(timezone.utc), para garantir compatibilidade com Python 3.12+.

**Workflow detalhado:**
1. Executar script de migração automatizada
2. Validar mudanças em cada serviço
3. Testar timestamps em banco de dados
4. Deploy gradual com monitoramento

### Epic 4: FastMCP API Fix

Como desenvolvedor, quero corrigir a incompatibilidade da API FastMCP nos MCP servers, para que possam iniciar corretamente.

**Workflow detalhado:**
1. Identificar todos os usos do argumento 'description'
2. Substituir por 'instructions'
3. Testar cada MCP server
4. Validar integração com clientes

## Spec Scope

1. **Epic 1: Fix Test Críticos** - Corrigir 12 testes worker-agents, 18 testes NLP, refatorar 61 testes specialist-behavior
2. **Epic 2: Pydantic V2 Migration** - Migrar 34 @validator em 6 serviços
3. **Epic 3: datetime.utcnow() Migration** - Migrar 1,547 ocorrências em 21 serviços
4. **Epic 4: FastMCP API Fix** - Corrigir 4 MCP servers

## Out of Scope

- Novas funcionalidades
- Refatoração não crítica
- Performance optimization
- Documentação de usuário

## Expected Deliverable

1. Todos os testes críticos passando (0 falhas)
2. Zero warnings de deprecção Pydantic/datetime
3. Todos os MCP servers funcionando
4. CI/CD executando sem bloqueios
5. Relatório de changes aplicadas
