# Spec Requirements Document

> Spec: journey-router
> Created: 2026-06-23
> Status: Planning

## Overview

Materializar o **eixo Y do modelo harmonizado** ([ADR-0011](../../adr/ADR-0011-harmonizacao-fluxos-capacidades-jornadas.md)): introduzir **Journey** como conceito de primeira classe e um **classificador de jornada inteligente** que analisa o contexto e os inputs da intenção para decidir qual jornada (J1-J4) compõe a execução. É o **passo 2 do princípio Fundação → Roteamento → Capacidades** — a Fundação (loop OBSERVE→LEARN) está feita (spec [fundacao-loop-learn](../2026-06-22-fundacao-loop-learn/spec.md)), com o gancho `journey_id` já presente no contrato `ExecutionFeedback` à espera de ser preenchido.

Hoje o roteamento de jornada é **difuso e raso**: o `workflow_classifier` (STE) classifica `ORCHESTRATION`/`GENERATION` por keywords, e o `decision_consumer` (orchestrator) re-deriva esse `workflow_type` para escolher o workflow (fluxo_g vs orchestration). Não há o conceito de Journey, nem `journey_id` atribuído, nem segmentação do loop de aprendizagem por jornada. A investigação do bug de tickets duplicados revelou ainda **dois caminhos a reagir ao mesmo plano** (consenso + resposta de aprovação) — sintoma do roteamento não-centralizado.

Esta spec entrega: o enum `Journey` partilhado, um `JourneyClassifier` **híbrido em 2 tiers** (sinais estruturados determinísticos + LLM semântico para os casos ambíguos, com `confidence`/`reasoning`/`UNKNOWN` no padrão anti-verde-falso do projeto), a propagação do `journey_id` início→fim, e métricas segmentadas por jornada.

```
intenção → STE: workflow_classifier + DAG + JourneyClassifier(híbrido)
        → cognitive_plan { journey, journey_id, journey_confidence, journey_reasoning }
        → decision_consumer roteia POR journey → workflow correto
        → ExecutionTicket/ExecutionFeedback herdam journey_id
        → loop LEARN + métricas segmentáveis por jornada
```

## User Stories

> Formato Gherkin (Given/When/Then). Cada cenário é diretamente verificável.

```gherkin
Feature: Classificador de jornada inteligente (híbrido, anti-verde-falso)
  Como arquiteto do pipeline cognitivo
  Quero que a jornada seja decidida analisando o contexto e os inputs da intenção
  Para que o roteamento seja semântico e explicável, não keywords frágeis

  Scenario: Sinal estruturado forte resolve sem LLM (Tier 1)
    Given uma intenção cujo cognitive_plan tem workflow_type = GENERATION
    When o JourneyClassifier classifica a jornada
    Then decide J3_BUILD por sinal estruturado
    And classification_method = "structured_signal"
    And não invoca o LLM

  Scenario: Caso ambíguo recorre ao LLM (Tier 2)
    Given uma intenção cujos sinais estruturados são ambíguos
    When o JourneyClassifier classifica a jornada
    Then invoca o LLM (neural_hive_llm) para analisar o contexto completo
    And devolve Journey + confidence + reasoning
    And classification_method = "llm"

  Scenario: Baixa confiança não inventa jornada (anti-verde-falso)
    Given uma classificação cuja confidence < threshold
    When o JourneyClassifier conclui
    Then a jornada é UNKNOWN
    And o plano fica requires_manual_validation = true
    And nunca força uma jornada cega
```

```gherkin
Feature: Journey como conceito de primeira classe, propagado início→fim
  Como engenheiro de ML
  Quero que o journey_id flua da decisão até ao ExecutionFeedback
  Para poder segmentar o loop LEARN e as métricas por jornada

  Scenario: journey_id propaga pela cadeia
    Given um plano classificado como J2_ORCHESTRATE com um journey_id
    When os tickets são executados e o feedback é persistido
    Then o ExecutionFeedback tem o mesmo journey_id (deixa de ser None)
    And as métricas-chave têm o label journey
```

```gherkin
Feature: Roteamento por jornada (centralizado)
  Como operador
  Quero que o orchestrator roteie pelo journey decidido a montante
  Para que a escolha do workflow seja única e testável

  Scenario: Roteamento determinado pela jornada
    Given um cognitive_plan com journey = J3_BUILD
    When o decision_consumer processa o plano
    Then encaminha para o fluxo_g_workflow (geração)
    And não re-deriva o workflow_type

  Scenario: Migração detetada por marcador de ingestão
    Given uma intenção com context.source = "doc-ingestion"
    When o JourneyClassifier classifica a jornada
    Then decide J4_MIGRATE por sinal estruturado
```

## Spec Scope

1. **Modelo `Journey` partilhado** — enum `Journey` (J1_PLAN_ONLY, J2_ORCHESTRATE, J3_BUILD, J4_MIGRATE, UNKNOWN) + `JourneyDecision` (journey, confidence, reasoning, classification_method) em `neural_hive_domain`.
2. **`JourneyClassifier` híbrido (STE)** — Tier 1 (sinais estruturados: source de ingestão→J4; execution_mode=plan_only→J1; workflow_type GENERATION→J3 / ORCHESTRATION→J2) + Tier 2 (LLM via `neural_hive_llm` para casos ambíguos) + anti-verde-falso (confidence/reasoning/UNKNOWN).
3. **Propagação no Cognitive Plan** — campos `journey`, `journey_id`, `journey_confidence`, `journey_reasoning`, `journey_classification_method` no `cognitive_plan`, gravados pelo STE.
4. **Roteamento por jornada** — `decision_consumer` roteia por `journey` (deixa de re-derivar workflow_type) e propaga `journey_id` aos tickets.
5. **Marcador de ingestão (J4)** — `doc-ingestion/gateway_client` marca `context.source="doc-ingestion"` na intenção (sinal estruturado fiável, não keywords).
6. **Métricas por jornada** — label `journey` nas métricas-chave (`neural_hive_observability`), fechando a segmentação do loop LEARN por jornada.

## Out of Scope

- **Extrair GENERATE como capacidade autónoma** — é o passo 3 (Capacidades) do ADR-0011; adiar até J3/BUILD ser fiável.
- **Consolidar PLAN** (STE + consensus) — a separação é correta; nunca.
- **Modelo ML dedicado de classificação de jornada** — usa-se LLM + sinais; o corpus está degenerado (mesmo bloqueio do NLU). Treino de modelo fica fora.
- **Validação E2E completa do Fluxo H (J4)** — o roteamento J4 fica funcional, mas o E2E end-to-end da migração depende da maturação do Fluxo H.
- **Camada 2 do fix de duplicação** (índice Mongo) — defesa residual independente, registada noutra spec/memória.

## Expected Deliverable

1. Uma intenção `GENERATION` é classificada `J3_BUILD` por sinal estruturado (sem LLM), e uma intenção ambígua recorre ao LLM e devolve Journey + confidence + reasoning; uma classificação de baixa confiança fica `UNKNOWN` + `requires_manual_validation` (verificável em testes + logs).
2. Após um E2E A→C6, o `cognitive_plan` tem `journey`/`journey_id` preenchidos e o `ExecutionFeedback` dos tickets herda o mesmo `journey_id` (deixa de ser `None`) — verificável em `neural_hive_orchestration.execution_tickets`.
3. Uma intenção com `context.source="doc-ingestion"` é classificada `J4_MIGRATE`; as métricas-chave passam a ter o label `journey` (verificável no Prometheus/coleção).
