# Spec Requirements Document

> Spec: Gate "J4/MIGRATE fiável" — jornada de migração de legado composta e provada E2E
> Created: 2026-06-29
> Status: Planning

## Overview

Estabelecer o gate **"J4/MIGRATE fiável"**: provar ponta-a-ponta que uma intenção de migração de
legado (jornada `J4_MIGRATE`) produz um **sistema migrado real e validado**, compondo as capacidades
`INGEST → PLAN → GENERATE → EXECUTE → MIGRATE` em vez de cair na `OrchestrationWorkflow` genérica. É a
**pré-condição** para depois extrair MIGRATE como capacidade autónoma e compor formalmente a jornada
J4 — exatamente como o gate "J3/BUILD fiável" (`docs/specs/2026-06-23-j3-build-generate`) precedeu a
extração da capacidade GENERATE.

**Diagnóstico que motiva a spec** (análise `memory/proj_j4_migrate_gap_analise_2026-06-29.md`): hoje
`decision_consumer.py:252` roteia `J4_MIGRATE → OrchestrationWorkflow` (a **mesma** classe de J2), que
é agnóstica à journey e **não invoca** INGEST, GENERATE nem MIGRATE. Os blocos existem e são produção
isoladamente (`doc-ingestion:8018`, `data-migration:8019`, com `DataMigrationWorkflow`/`CutoverWorkflow`
**registados no worker mas órfãos** — nenhum `start_workflow` os inicia). Uma sonda de runtime
(2026-06-29) confirmou: injetar `journey=J4_MIGRATE` faz correr a orquestração genérica e falhar na
validação comum, **sem tocar em qualquer capacidade de migração**. A jornada J4 do ADR-0011 existe
como *label*, não como fluxo executável.

**Princípio transversal — anti-verde-falso (FAIL-CLOSED):** o gate só passa com evidência real de
software migrado a correr. Migração com perda de dados, validação pós-migração reprovada, ou qualquer
fase composta em falha → `FAILED` (sem simulação, sem verde falso), herdando a doutrina de
`caminho-real-first-class` e do gate J3/BUILD.

## User Stories

### J4M-US1 · Intenção de migração de legado produz sistema migrado real

```gherkin
Funcionalidade: Jornada J4 ponta-a-ponta com software migrado a correr

  Cenário: Migração de um schema/dados PostgreSQL de legado
    Dada uma intenção de migração classificada como J4_MIGRATE (sinal context.source=doc-ingestion)
    Quando o plano é aprovado e executado pela jornada composta
    Então é ingerido o artefacto de legado, planeada a migração, gerado o serviço moderno,
         feito deploy, e migrados schema+dados do PostgreSQL legacy para o moderno
    E a validação pós-migração confirma integridade (contagem de linhas + checks)
    E o comportamento é observável (não simulado)
```

### J4M-US2 · A jornada compõe capacidades, não a orquestração genérica

```gherkin
Funcionalidade: Fronteira de jornada (não cair na OrchestrationWorkflow de J2)

  Cenário: Plano J4_BUILD roteia para o fluxo composto de migração
    Dado um plano classificado como J4_MIGRATE
    Quando o decision_consumer o processa
    Então a jornada encadeia INGEST → PLAN → GENERATE → EXECUTE → MIGRATE
    E o DataMigrationWorkflow deixa de ser órfão (é iniciado pela jornada)
    E a GenerateCapability é reusada (não duplicada) na fase de geração
    E J2_ORCHESTRATE permanece inalterada (zero regressão)
```

### J4M-US3 · Validação pós-migração é gate fail-closed (anti-verde-falso)

```gherkin
Funcionalidade: Gate de validação fail-closed

  Cenário: Migração com perda de dados falha fechado
    Dada uma migração cuja validação pós-migração deteta divergência (linhas em falta / integridade)
    Quando a jornada avalia o resultado de MIGRATE
    Então o resultado é FAILED com razão explícita
    E NÃO se reivindica sucesso (sem verde falso)

  Cenário: Endpoint /validate indisponível também falha fechado
    Dado que o data-migration /validate não responde ou devolve erro
    Quando a jornada avalia a migração
    Então o resultado é FAILED (fail-closed, sem assumir sucesso)
```

### J4M-US4 · GENERATE reusado na composição (sem duplicar wiring)

```gherkin
Funcionalidade: Reuso da capacidade GENERATE em J4

  Cenário: Modernização gera serviço novo via a capacidade já provada
    Dada uma intenção de migração que exige código moderno
    Quando a jornada chega à fase GENERATE
    Então invoca a GenerateCapability existente (contrato GenerateRequest → GenerateResult)
    E o software gerado é deployado antes da fase de migração de dados
    E nenhuma lógica de geração é reimplementada na jornada J4
```

## Spec Scope

1. **Fluxo composto da jornada J4** — substituir o roteamento genérico `J4_MIGRATE →
   OrchestrationWorkflow` por uma orquestração que encadeia `INGEST → PLAN → GENERATE → EXECUTE →
   MIGRATE`, decidida pela semântica da journey (não por classe de workflow vazada).
2. **Integração MIGRATE (des-orfanizar)** — iniciar o `DataMigrationWorkflow` existente a partir da
   jornada J4 e recolher o seu resultado; preservar durabilidade/saga do Temporal.
3. **Reuso de GENERATE** — invocar a `GenerateCapability` (já provada em J3) na fase de geração da
   jornada, sem duplicar wiring; deploy do serviço moderno antes de migrar dados.
4. **Gate de validação anti-verde-falso** — usar o `/validate` do `data-migration` como gate
   fail-closed (linhas migradas + integridade); falha/validação-indisponível → `FAILED`.
5. **Gate E2E em cluster** — uma intenção de migração J4 produz, via o fluxo composto, um PostgreSQL
   moderno migrado a partir de um legacy de fixture, com validação confirmada e o serviço gerado a
   correr — análogo ao gate 3.3 de GENERATE.

## Out of Scope

- **Extrair MIGRATE como capacidade autónoma** (fronteira de contrato `MigrateRequest →
  MigrateResult`) — este gate apenas *prova a fiabilidade*; a extração é spec seguinte (tal como
  j3-build precedeu a extração de GENERATE).
- **Cutover canary gradual** (`CutoverWorkflow` shadow→canary 5/25/50/100%) — o gate usa `/validate`;
  o cutover progressivo fica para spec própria.
- **Fontes de migração não-PostgreSQL** (MongoDB, ficheiros, etc.) — o cenário canónico é
  PostgreSQL legacy → moderno.
- **Qualidade semântica do código gerado** além de "compila + arranca + healthcheck" (herdado de
  GENERATE).
- **Parsing LLM de documentos de legado reais no doc-ingestion** além do necessário para alimentar o
  plano de teste (o foco do gate é a fiabilidade da migração + composição, não a qualidade do NLU de
  ingestão).

## Expected Deliverable

1. Uma intenção de migração J4 produz, via **fluxo composto** (não `OrchestrationWorkflow` genérica),
   um PostgreSQL moderno migrado a partir de um legacy de fixture, com `/validate` a confirmar
   integridade (contagem de linhas + checks) e o serviço moderno gerado a correr.
2. A jornada **reusa** `GenerateCapability` e **inicia** o `DataMigrationWorkflow` (deixa de ser
   órfão); `J2_ORCHESTRATE` permanece inalterada (zero regressão, teste congelado verde).
3. Validação reprovada / perda de dados / `/validate` indisponível → `FAILED` (anti-verde-falso
   provado por testes e por mutação).
4. Gate E2E em cluster documentado em `sub-specs/` (plano real, DB migrado, validação 200, journey
   no artefacto) — evidência "software migrado a correr", análoga ao gate 3.3 de GENERATE.
