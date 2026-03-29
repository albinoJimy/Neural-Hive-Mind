# Spec Requirements Document

> Spec: GAP-02 Execution Results Consumer
> Created: 2026-03-29
> Status: Planning
> Epic: Completar feedback loop de execução

## Overview

Implementar consumer do tópico `execution.results` no Orchestrator Dynamic para fechar o feedback loop de execução dos Worker Agents. Atualmente, os Worker Agents publicam resultados mas nenhum serviço consome, deixando workflows Temporal aguardando timeout.

**Problema:** Worker Agents produzem em `execution.results`, mas NENHUM serviço consome
**Impacto:** Workflows não completam, consolidação de resultados falha, telemetria incompleta
**Solução:** Implementar consumer no Orchestrator Dynamic que envia signals para workflows Temporal
**Benefício:** Feedback loop completo, workflows completam corretamente, telemetria funcional

## User Stories

### Como Orchestrator Dynamic

Como Orchestrator Dynamic, quero receber notificações quando Worker Agents completam tickets, para que eu possa continuar o workflow Temporal sem aguardar timeout.

**Workflow Atual (QUEBRADO):**
1. Workflow Temporal inicia
2. Ticket é publicado para Worker Agents
3. Worker executa e publica em `execution.results`
4. ❌ Ninguém consome → workflow aguarda timeout

**Workflow Corrigido:**
1. Workflow Temporal inicia
2. Ticket é publicado para Worker Agents
3. Worker executa e publica em `execution.results`
4. ✅ Consumer processa e envia signal para workflow
5. Workflow continua imediatamente

### Como Engenheiro de Observabilidade

Como engenheiro de observabilidade, quero capturar todos os resultados de execução, para que dashboards e alertas reflitam o estado real do sistema.

## Spec Scope

### In Scope

1. **Schema Execution Result**
   - Atualizar `schemas/execution-result/execution-result.avsc`
   - Adicionar campos: `plan_id`, `workflow_id`, `correlation_id`
   - Manter backward compatibility

2. **Consumer Kafka**
   - Criar `services/orchestrator-dynamic/src/consumers/execution_result_consumer.py`
   - Consumir tópico `execution.results`
   - Enviar signal `ticket_completed` para workflow Temporal
   - Cache workflow_id em Redis para lookup

3. **Cache de Workflow ID**
   - Modificar `services/orchestrator-dynamic/src/activities/ticket_generation.py`
   - Salvar mapeamento `ticket_id → workflow_id` no Redis
   - TTL de 24h

4. **Producer Worker Agents**
   - Modificar `services/worker-agents/src/clients/kafka_result_producer.py`
   - Incluir novos campos: `plan_id`, `workflow_id`, `correlation_id`

5. **Integração no Main**
   - Modificar `services/orchestrator-dynamic/src/main.py`
   - Inicializar consumer no lifespan
   - Gerenciar shutdown gracioso

### Out of Scope

- Modificação do signal `ticket_completed` no workflow Temporal (já existe)
- Criação de novos tópicos Kafka
- Mudança no comportamento dos Worker Agents (apenas metadata adicional)

## Expected Deliverable

1. **Código Criado/Modificado**
   - Schema atualizado com novos campos
   - Consumer Kafka funcional
   - Cache de workflow_id implementado
   - Producer atualizado com metadata
   - Integração no main do orchestrator

2. **Testes**
   - Unit tests do consumer (mock Temporal)
   - Integration test do feedback loop completo
   - Teste E2E com Kafka local

3. **Documentação**
   - Atualizar diagrama de arquitetura
   - Documentar novo signal flow
