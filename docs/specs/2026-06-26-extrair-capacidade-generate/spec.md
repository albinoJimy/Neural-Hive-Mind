# Spec Requirements Document

> Spec: Extrair GENERATE como capacidade autónoma (fronteira de contrato, multi-linguagem-ready)
> Created: 2026-06-26
> Status: Planning

## Overview

Promover **GENERATE** de fluxo embutido no orchestrator a **capacidade autónoma** com um
contrato `Plan(GENERATION) → Software em execução` explícito, testável em bloco e invocável de
forma uniforme. É o **passo 3 do ADR-0011** (eixo Capacidades), desbloqueado agora que o gate
"J3/BUILD fiável" foi estabelecido (`docs/specs/2026-06-23-j3-build-generate`).

A extração é por **fronteira de contrato** (grau incremental): o `FluxoGWorkflow` (Temporal)
mantém-se como implementação por trás da fronteira — preserva-se a durabilidade/retry/saga e a
fiabilidade J3/BUILD acabada de blindar. O que muda é a **estrutura**: deixa de haver uma
dependência directa e "vazada" do routing para a classe do workflow, e passa a existir uma
capacidade com in/out explícito que J3 (e, no futuro, J4) compõem sem duplicar wiring.

**Princípio transversal desta spec — pronto para multi-linguagem:** embora só **Python FastAPI**
seja implementado e provado, o contrato, o campo `target{language, framework}` e a seleção de
template/builder são desenhados **stack-neutros**. Adicionar uma linguagem depois é registar uma
nova estratégia atrás da **mesma** fronteira — sem mudar o contrato nem o routing.

Contexto de código: hoje `decision_consumer.py` importa `FluxoGWorkflow` e conhece a sua classe
(`_select_workflow_class_by_journey`); o resultado do workflow já carrega `language`/`framework`
(`fluxo_g_workflow.py:501-506`), prova de que a informação de stack já flui — falta a fronteira.

## User Stories

### GEN-US1 · GENERATE é uma capacidade com contrato explícito

```gherkin
Funcionalidade: Capacidade GENERATE com contrato in/out

  Cenário: Invocar GENERATE com um plano de geração
    Dado um GenerateRequest { plan_id, journey, cognitive_plan, target{language, framework} }
    Quando a capacidade GENERATE é invocada
    Então devolve um GenerateResult { status, code_artifact_id, container_image_ref,
         deployment{namespace, service_url, health}, journey, failure_reason? }
    E o contrato é testável isoladamente, sem correr a jornada inteira
```

### GEN-US2 · Routing invoca a capacidade, não a sua implementação

```gherkin
Funcionalidade: Fronteira não-vazada

  Cenário: Plano J3_BUILD roteia para a capacidade GENERATE
    Dado um plano classificado como J3_BUILD
    Quando o decision_consumer o processa
    Então invoca a capacidade GENERATE (não importa nem conhece FluxoGWorkflow)
    E o fallback por workflow_type é preservado para jornadas sem geração
```

### GEN-US3 · Pronto para multi-linguagem (sem o implementar)

```gherkin
Funcionalidade: Extensibilidade de stack atrás da mesma fronteira

  Cenário: Stack FastAPI resolvida pela estratégia registada
    Dado target { language: "python", framework: "fastapi" }
    Quando a capacidade resolve a estratégia de geração
    Então usa o template/builder FastAPI registado

  Cenário: Registar uma nova stack não muda o contrato
    Dado uma estratégia de stack adicional registada no registry
    Quando a capacidade é invocada com essa target
    Então a estratégia nova é selecionada sem alterar GenerateRequest/GenerateResult nem o routing

  Cenário: Stack não suportada falha fechado (anti-verde-falso)
    Dado target de uma stack sem estratégia registada
    Quando a capacidade é invocada
    Então devolve status=FAILED com razão "stack não suportada"
    E NÃO cai silenciosamente para FastAPI
```

### GEN-US4 · Equivalência comportamental (zero regressão)

```gherkin
Funcionalidade: Paridade E2E após a extração

  Cenário: Intenção J3 continua a produzir software a correr
    Dado uma intenção de geração FastAPI classificada como J3_BUILD
    Quando o plano é aprovado e executado via a capacidade GENERATE
    Então é feito deploy de um Deployment real ready 1/1 com healthcheck 200
    E é persistido um code_artifact com journey=J3_BUILD
    E o comportamento é equivalente ao caminho FluxoG anterior
```

## Spec Scope

1. **Contrato da capacidade GENERATE** — módulo `src/capabilities/generate/` com
   `GenerateRequest`/`GenerateResult` explícitos e fail-closed; `target{language, framework}`
   stack-neutro.
2. **GenerateCapability** — encapsula o `FluxoGWorkflow` (Temporal): inicia, recolhe o resultado
   G1–G8 e mapeia para `GenerateResult`; preserva durabilidade/retry/saga.
3. **Des-vazar a fronteira no routing** — `decision_consumer` invoca a capacidade em vez de
   importar/conhecer `FluxoGWorkflow`; fallback por `workflow_type` preservado.
4. **Registry de stacks (multi-linguagem-ready)** — seleção de template/builder por
   `(language, framework)`; FastAPI é a única estratégia registada; stack desconhecida → FAILED;
   extensão = registar nova estratégia sem mudar contrato/routing.
5. **Gates de equivalência** — teste de contrato em bloco + paridade E2E J3 (Deployment 1/1 +
   `/health` 200 via a capacidade).

## Out of Scope

- **Implementar** outras linguagens/frameworks além de Python FastAPI (só se *prepara* a fronteira).
- Novo microserviço autónomo para GENERATE (grau de extração mais caro — adiado; a fronteira
  habilita-o se algum dia justificar).
- Mover a orquestração G1–G8 para o code-forge.
- GENERATE dentro de J4_MIGRATE (só se garante que a capacidade é composable; o wiring de J4
  fica para spec própria).
- Qualidade semântica do código gerado além de "compila + arranca + healthcheck 200".

## Expected Deliverable

1. Uma capacidade GENERATE com contrato `GenerateRequest → GenerateResult` explícito e testável
   isoladamente (teste de bloco verde).
2. O `decision_consumer` invoca a capacidade sem conhecer `FluxoGWorkflow`; fallback preservado.
3. Registry de stacks com FastAPI registado e prova de extensibilidade (estratégia "fake"
   registada em teste é selecionada sem tocar no contrato); stack desconhecida → FAILED.
4. Paridade E2E: intenção J3 produz Deployment real ready 1/1 + `/health` 200 via a capacidade,
   com `code_artifact` journey=J3_BUILD — equivalente ao caminho anterior.
