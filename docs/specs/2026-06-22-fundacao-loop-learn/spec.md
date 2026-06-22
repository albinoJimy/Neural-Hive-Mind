# Spec Requirements Document

> Spec: fundacao-loop-learn
> Created: 2026-06-22
> Status: Em execução — Fases 0-3 código completo e verde (21/21 testes); gate de cluster CORRIGIU a Fase 2 (completed_at é BSON Date, não millis — ver sub-specs/cluster-gate-evidence.md) e validou 208 treináveis ≥ 100; falta deploy + E2E A→C6

## Overview

Fechar o **loop de aprendizagem (D6/LEARN)** do NHM construindo-o como **Fundação transversal** (plano-Z do modelo harmonizado — ver [ADR-0011](../../adr/ADR-0011-harmonizacao-fluxos-capacidades-jornadas.md)), e não como um patch acoplado à capacidade EXECUTE. Hoje o sinal de execução real (`actual_duration_ms`) **já viaja** no evento `execution.results` mas é **descartado**: o `execution_result_consumer.py` só envia o signal Temporal e nunca persiste o resultado, pelo que `execution_tickets` fica quase sem o campo (3/1247 históricos) e o `duration_predictor` treina cego. Há ainda um **segundo bug latente de contrato de tipo**: `ticket_generation.py:256` grava timestamps como `int` (epoch millis) mas o predictor filtra `completed_at: {"$gte": <datetime>}` — `$gte` entre tipos BSON diferentes nunca casa, logo mesmo persistindo a duração o predictor continuaria a não a encontrar.

A entrega é tratada como **costura de fundação primeiro**, respeitando o princípio ordenador **Fundação → Roteamento → Capacidades. Nunca o inverso**:

```
loop acoplado a EXECUTE (verde-falso treina o modelo) → Fundação transversal (contrato + sink capability-agnostic) → ganchos prontos p/ Roteamento (journey_id) e Capacidades (capability)
```

Distinção orientadora: o loop OBSERVE→LEARN **não pertence a nenhuma capacidade**. É um plano transversal que J2/ORCHESTRATE, J3/BUILD e J4/MIGRATE alimentam através do **mesmo contrato canónico** (`ExecutionFeedback`) e do **mesmo coletor** (`FeedbackSink`). Hoje liga-se apenas o emissor EXECUTE (o único que já produz o sinal); a interface fica transversal por construção para que GENERATE/MIGRATE sejam adapters adicionais, sem reabrir a Fundação.

## User Stories

> Formato Gherkin (Given/When/Then). Cada cenário é diretamente verificável.

```gherkin
Feature: Loop de aprendizagem alimentado com duração real (Fundação)
  Como engenheiro de ML
  Quero que a duração real de cada execução seja persistida no corpus que o LEARN lê
  Para que o duration_predictor treine sobre dados reais e não fique cego

  Background:
    Given o evento execution.results já transporta actual_duration_ms calculado pelo worker
    And a coleção canónica execution_tickets é a fonte que o duration_predictor consome

  Scenario: O resultado de um ticket é persistido ao fechar
    Given um ticket de execução COMPLETED publicado em execution.results
    When o ExecutionResultConsumer processa o resultado
    Then o documento correspondente em execution_tickets tem actual_duration_ms > 0
    And tem status, started_at, completed_at e feedback_persisted_at preenchidos
    And o envio do signal Temporal continua a ocorrer independentemente da persistência

  Scenario: O predictor deixa de estar cego
    Given execuções reais persistidas durante a janela de treino
    When o duration_predictor verifica a disponibilidade de dados de treino
    Then encontra amostras suficientes (>= ml_min_training_samples)
    And não regista "insufficient_training_data"
```

```gherkin
Feature: Contrato de tipo consistente entre escrita e leitura
  Como arquiteto
  Quero que completed_at/started_at sejam BSON Date em toda a costura do loop
  Para que o filtro temporal do predictor case com o que é gravado
  # NOTA: o gate de cluster mostrou que completed_at/started_at são BSON Date
  # (não int millis) — ver sub-specs/cluster-gate-evidence.md. O contrato
  # ExecutionFeedback usa millis (portável); o sink converte para Date ao gravar.

  Scenario: O filtro temporal encontra os registos
    Given completed_at gravado como BSON Date (o sink converte millis -> Date)
    When o duration_predictor filtra completed_at >= cutoff dentro da janela de treino
    Then o cutoff é um datetime (casa com BSON Date)
    And a query devolve os tickets dentro da janela
```

```gherkin
Feature: Proteção do treino contra verde-falso
  Como engenheiro de ML
  Quero que execuções simuladas/degradadas sejam persistidas mas excluídas do treino
  Para que o modelo não aprenda durações falsas

  Scenario: Execução simulada é observável mas não treina
    Given um resultado com metadata.simulated = true
    When o FeedbackSink persiste o feedback
    Then o documento tem result_simulated = true
    And o duration_predictor exclui esse documento do conjunto de treino (result_simulated != true)
```

```gherkin
Feature: Fundação transversal (capability-agnostic)
  Como arquiteto
  Quero que o loop seja um plano-Z transversal, não uma propriedade de EXECUTE
  Para que GENERATE e MIGRATE encaixem como adapters sem reabrir a Fundação

  Scenario: O sink aceita qualquer capacidade sem alteração
    Given um FeedbackSink já em uso pelo adapter EXECUTE
    When um teste invoca FeedbackSink.record com capability = "GENERATE"
    Then o registo é persistido com capability = "GENERATE"
    And nenhuma alteração ao FeedbackSink é necessária

  Scenario: O contrato carrega os ganchos de Roteamento e Capacidade desde já
    Given o contrato ExecutionFeedback usado pelo emissor EXECUTE
    Then inclui o campo capability preenchido com "EXECUTE"
    And inclui o campo journey_id (preenchível pelo Roteamento no passo seguinte, hoje opcional)
```

## Spec Scope

1. **Contrato canónico `ExecutionFeedback`** — modelo/schema capability-agnostic (campos: `capability`, `journey_id`, `ticket_id`, `plan_id`, `trace_id`, `status`, `actual_duration_ms`, `started_at`, `completed_at`, `simulated`, `feedback_persisted_at`), formalizado como Avro em `schemas/execution-feedback/`.
2. **`FeedbackSink` transversal (plano-Z)** — ponto único de persistência idempotente (`update_one` por `ticket_id`), desacoplado, que marca `result_simulated`; vive fora de qualquer capacidade.
3. **Adapter EXECUTE** — o `execution_result_consumer` traduz `ExecutionResult` → `ExecutionFeedback` e delega ao sink, sem conter lógica de Mongo; persistência desacoplada do signal (falha não bloqueia o workflow).
4. **Alinhamento do leitor LEARN** — corrigir o `duration_predictor` para filtrar em epoch millis (2 sítios) e excluir `result_simulated`.
5. **Anti-regressão e validação** — asserção E2E de loop fechado (contagem de duração real sobe) + teste de transversalidade (sink aceita `capability="GENERATE"` sem alteração) + guarda contra reintrodução do tipo datetime no filtro.
6. **Ganchos prontos (não ativados)** — `capability`/`journey_id` presentes no contrato para que Roteamento (journey router) e Capacidades (adapters GENERATE/MIGRATE) encaixem depois sem reabrir a Fundação.

## Out of Scope

- **Ligar emissores GENERATE (G6-G13) e MIGRATE (H) ao sink** — pertence ao passo "Capacidades" (após o journey router); aqui só se garante que o sink os aceita.
- **Journey router explícito** — é o passo "Roteamento" (passo 2 do ADR-0011); aqui só se cria o gancho `journey_id`.
- **Migração para coleção dedicada `execution_feedback`** — hoje reutiliza-se `execution_tickets` (o predictor já lê); a coleção dedicada é evolução futura sem tocar emissores.
- **Backfill dos tickets históricos sem duração** — o evento já passou; o modelo treina a partir de dados novos (regravação opcional via `result_consolidation` fica como nota, não escopo).
- **Sincronização Mongo→ClickHouse** — o predictor tenta ClickHouse com fallback Mongo; o Mongo é a fonte da verdade deste passo.

## Expected Deliverable

1. Após um E2E A→C6, `db.execution_tickets.countDocuments({actual_duration_ms: {$gt: 0}, result_simulated: {$ne: true}})` mantém-se ≥ baseline (gate de cluster: 208 treináveis ≥ `ml_min=100`), e os tickets do sink têm `completed_at` como **BSON `Date`** (o sink converte millis→Date) — consistente com os tickets existentes.
2. `duration_predictor.check_training_data_availability()` deixa de registar `insufficient_training_data` quando há execuções reais na janela; um ticket com `metadata.simulated=true` aparece na coleção mas **não** entra na query de treino.
3. Um teste unitário invoca `FeedbackSink.record(capability="GENERATE")` com sucesso **sem alterar o sink** — prova de que a Fundação é transversal e que Roteamento/Capacidades encaixam sem cirurgia (consistência com o princípio Fundação → Roteamento → Capacidades).
