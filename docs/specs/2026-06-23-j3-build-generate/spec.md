# Spec Requirements Document

> Spec: Endurecer J3/BUILD (capacidade GENERATE) — pré-condição ADR-0011
> Created: 2026-06-23
> Status: Planning

## Overview

Tornar a jornada **J3_BUILD** (`CAPTURE → PLAN → GENERATE → EXECUTE(deploy)`) fiável ponta-a-ponta, de forma que uma intenção de geração produza **software real, em execução** no cluster (gera → build → deploy → healthcheck). Isto estabelece o gate normativo do ADR-0011 — *"extrair GENERATE como capacidade autónoma só quando J3/BUILD for fiável"* — e desbloqueia o passo seguinte do eixo Capacidades.

Contexto: a validação E2E do journey-router (2026-06-23) provou que o **roteamento** J3_BUILD funciona (journey classificado e propagado, tickets COMPLETED), mas a **capacidade GENERATE não é fiável**: o `FluxoGWorkflow` não foi acionado (o plano correu como orchestration genérica), o code-forge rejeita tickets por contrato divergente, e nenhum `code_artifact` foi produzido. Ver `proj_j3_build_reliability_2026-06-23`.

## User Stories

### J3-US1 · Uma intenção de geração gera software real

```gherkin
Funcionalidade: Geração de software a partir de uma intenção (J3_BUILD)

  Cenário: Intenção de criação de microserviço produz software em execução
    Dado uma intenção "Criar e desenvolver um microserviço REST em Python (FastAPI)"
    E que o journey router a classifica como J3_BUILD
    Quando o plano é aprovado e executado
    Então o orchestrator inicia o FluxoGWorkflow (não orchestration genérica)
    E o code-forge gera código-fonte FastAPI real (não stub)
    E é construída uma imagem de container real publicada no GHCR
    E é feito deploy de um Deployment real num namespace efémero
    E o healthcheck do serviço responde 200
    E é persistido um code_artifact com journey=J3_BUILD
```

### J3-US2 · Falhas reais não passam por verde falso

```gherkin
Funcionalidade: Anti-verde-falso no pipeline de geração

  Cenário: Build que falha marca a etapa como FAILED
    Dado um plano J3_BUILD em geração
    Quando o build (G7) falha ou produz imagem não-puxável
    Então a etapa é marcada FAILED com a razão
    E o pipeline não reporta COMPLETED simulado

  Cenário: Deploy que não fica saudável marca FAILED
    Dado um plano J3_BUILD cujo código foi gerado e empacotado
    Quando o Deployment (G8) não atinge ready 1/1 ou o healthcheck != 200
    Então a etapa é marcada FAILED com a razão
    E nenhum software é reportado como entregue
```

### J3-US3 · Contrato de ticket único entre consumidores

```gherkin
Funcionalidade: Contrato ExecutionTicket unificado

  Cenário: Worker e code-forge aceitam o mesmo ticket
    Dado um ExecutionTicket emitido pelo produtor (STE/orchestrator)
    Quando é consumido pelo worker-agents e pelo code-forge
    Então ambos o desserializam sem erro
    E task_type e priority seguem o contrato canónico (enum)
    E tickets legados (task_type minúsculas / priority int) são normalizados, não rejeitados
```

### J3-US4 · Roteamento J3→FluxoG fiável (incl. pós-aprovação)

```gherkin
Funcionalidade: Roteamento determinístico por journey

  Cenário: Plano J3 que exige aprovação humana ainda roteia para FluxoG
    Dado um plano J3_BUILD com final_decision=review_required
    Quando o plano é aprovado
    Então o resume pós-aprovação inicia o FluxoGWorkflow
    E não cai em orchestration genérica nem executa tarefas query/transform parasitas
```

## Spec Scope

1. **Roteamento J3→FluxoGWorkflow** — fiável no caminho direto **e no resume pós-aprovação** (defeito central detetado).
2. **Contrato `ExecutionTicket` canónico** — unificar `task_type` (enum maiúsculas) e `priority` (enum string) entre produtor, worker-agents e code-forge, com desserializador tolerante a legado.
3. **Pipeline G real e fail-closed** — G1 (requisitos) → G6 (código FastAPI via code-forge) → G7 (build real Kaniko→GHCR) → G8 (deploy real + healthcheck), cada etapa marca FAILED em falha real.
4. **Stack canónica Python FastAPI REST** — provada profundamente (gera → build → deploy → healthcheck).
5. **Diagnóstico inicial (Fase 0)** — run J3 real instrumentado para fixar os break-points exatos antes de corrigir.

## Out of Scope

- Múltiplas linguagens/stacks (só Python FastAPI nesta spec).
- Extrair GENERATE como serviço/capacidade autónoma (é o passo seguinte do ADR-0011, habilitado por esta spec).
- Refactor não relacionado do code-forge.
- Qualidade semântica do código gerado além de "compila + arranca + healthcheck 200".
- Decomposição genérica do STE para outros fins (só se a Fase 0 mostrar que bloqueia J3).

## Expected Deliverable

1. Uma intenção de geração percorre J3_BUILD ponta-a-ponta e produz um **Deployment real `ready 1/1` com healthcheck 200** num namespace efémero, com `code_artifact` + `ExecutionFeedback` marcados `journey=J3_BUILD`.
2. Falhas reais em qualquer G-step resultam em **FAILED** (sem verde falso).
3. Worker-agents e code-forge desserializam o **mesmo** `ExecutionTicket` sem erro.
4. Gate "J3/BUILD fiável" do ADR-0011 estabelecido e documentado — pronto para extrair GENERATE.
