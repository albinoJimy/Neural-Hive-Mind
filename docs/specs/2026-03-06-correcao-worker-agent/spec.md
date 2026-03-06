# Spec Requirements Document

> Spec: Correção Worker Agent - ExecutionEngine e Contratos
> Created: 2026-03-06
> Status: Planning

## Overview

Corrigir dois bugs críticos identificados durante teste E2E do Worker Agent que causam falhas silenciosas na execução de tickets: (1) ExecutionEngine sempre marca tickets como COMPLETED independente do resultado da execução, e (2) mismatch de contrato entre Semantic Translation Engine e Executors quanto aos parâmetros esperados.

## User Stories

### Correção de Falhas Silenciosas

Como **operador do Neural Hive-Mind**, eu quero que tickets com falhas de execução sejam marcados como FAILED, para que eu possa identificar e corrigir problemas reais na infraestrutura.

**Workflow atual:**
1. Intent é processado → STE gera Cognitive Plan
2. Orchestrator cria tickets na Execution Ticket Service
3. Worker Agent executa tickets
4. **PROBLEMA:** Tickets com erro são marcados COMPLETED
5. **RESULTADO:** Falhas ficam invisíveis para o operador

### Harmonização de Contratos

Como **desenvolvedor**, eu quero que a STE gere parâmetros que os Executors possam processar, para que as tasks sejam executadas corretamente.

**Workflow atual:**
1. STE gera tasks com `{subject, target, entities}`
2. Executors esperam `{collection, input_data, policy_path}`
3. **PROBLEMA:** ValueError nos executores
4. **RESULTADO:** Tasks falham mas são marcadas COMPLETED (bug #1)

## Spec Scope

1. **Corrigir ExecutionEngine** - Adicionar verificação de `result['success']` antes de marcar COMPLETED
2. **Harmonizar contratos de parâmetros** - STE gerar parâmetros específicos que os Executors exigem
3. **Adicionar validação de parâmetros** - Executors validam parâmetros obrigatórios no início da execução

## Out of Scope

- Refatoração completa da arquitetura STE/Executor
- Implementação de novos tipos de executores
- Mudanças no fluxo de approval
- Alterações no Schema Registry

## Expected Deliverable

1. Tickets com falhas de execução marcados como FAILED
2. Tickets executados com sucesso quando parâmetros corretos são fornecidos
3. Logs claros indicando motivo da falha quando parâmetros faltam
