# Plano de Execução: Testes E2E Neural Hive-Mind

## Objetivo
Executar testes end-to-end completos seguindo o plano em `docs/PLANO_TESTE_MANUAL_FLUXOS_A_C.md`

## Fluxos a Testar

### Fluxo A - Gateway de Intenções → Kafka
- A1: Health Check do Gateway
- A2: Enviar Intenção (Payload 1 - TECHNICAL)
- A3: Validar Logs do Gateway
- A4: Validar Mensagem no Kafka (intentions.technical)
- A5: Validar Cache no Redis
- A6: Validar Métricas Prometheus
- A7: Validar Trace Jaeger

### Fluxo B - Semantic Translation Engine → Plano Cognitivo
- B1: Validar Consumo pelo STE
- B2: Validar Logs de Geração de Plano
- B3: Validar Mensagem no Kafka (plans.ready)
- B4: Validar Persistência no MongoDB
- B5: Validar Consulta Neo4j
- B6: Validar Métricas STE Prometheus
- B7: Validar Trace STE Jaeger

### Fluxo B - Specialists (5 Especialistas)
- C1: Validar Chamadas gRPC aos Specialists
- C2: Validar Specialist Business
- C3: Validar Specialist Technical
- C4: Validar Specialist Behavior
- C5: Validar Specialist Evolution
- C6: Validar Specialist Architecture
- C7: Validar Persistência de Opiniões no MongoDB
- C8: Validar Métricas Specialists Prometheus

### Fluxo C - Consensus Engine
- D1: Validar Consumo de Plano pelo Consensus
- D2: Validar Agregação Bayesiana
- D3: Validar Decisão Final
- D4: Validar Publicação no Kafka (plans.consensus)
- D5: Validar Persistência da Decisão MongoDB
- D6: Validar Publicação de Feromônios Redis
- D7: Validar Métricas Consensus Prometheus
- D8: Validar Trace Consensus Jaeger

### Fluxo C - Orchestrator Dynamic
- E1: Validar Consumo de Decisão pelo Orchestrator
- E2: Validar Geração de Execution Tickets
- E3: Validar Publicação no Kafka (execution.tickets)
- E4: Validar Persistência Tickets MongoDB
- E5: Validar Ordem de Execução
- E6: Validar Métricas Orchestrator Prometheus
- E7: Validar Trace Orchestrator Jaeger

## Execução

### Pré-requisitos
- Verificar kubectl, curl, jq conectados
- Port forwards configurados
- Payloads de teste preparados

### Ordem de Execução
1. Preparação do Ambiente
2. Fluxo A (Gateway)
3. Fluxo B (STE)
4. Fluxo B (Specialists)
5. Fluxo C (Consensus)
6. Fluxo C (Orchestrator)
7. Validação E2E Consolidada

### Documentação por Teste
- **INPUT**: Dados enviados, configuração
- **OUTPUT**: Resposta obtida
- **ANÁLISE PROFUNDA**: Validação contra esperado
- **EXPLICABILIDADE**: O que significa o resultado

## Relatório Final
- Checklist de validação de cada fluxo
- Métricas coletadas
- IDs de trace
- Status: PASSOU/FALHOU
