# Spec Requirements Document

> Spec: caminho-real-first-class
> Created: 2026-06-19
> Status: Planning

## Overview

Garantir que cada `COMPLETED` no pipeline cognitivo corresponde a **trabalho real verificável por evidência**, eliminando simulação e heurística-de-lacuna como caminhos aceitáveis em **qualquer ambiente** (incluindo dev). Onde o caminho real não existe (classificador NLU ML, geração de código, preditores ML), esta spec entrega-o de raiz como épicos faseados. O objetivo final é *verde-verdadeiro*: o sistema **faz** o trabalho, não o simula nem o sinaliza apenas.

Distinção orientadora:

```
verde-falso (mente) → vermelho-honesto (diz a verdade) → verde-verdadeiro (FAZ o trabalho)
```

A honestidade (marcar/medir/falhar) é o piso desta spec, não o teto: serve para que nenhuma regressão para simulação passe despercebida enquanto construímos os caminhos reais.

## User Stories

### Operador confia que COMPLETED é trabalho feito

Como **operador**, quero que um ticket `COMPLETED` só seja emitido quando existe **evidência verificável** do trabalho (artefacto no registry, recurso K8s reconciliado, relatório de política avaliado, ficheiros de código commitados), para que o estado do pipeline seja a realidade e não uma simulação.

Hoje executores de deploy/build/validate/execute/test devolvem `success=True` simulado e o `execution_engine` marca `COMPLETED` sem validar evidência.

### Engenheiro corre trabalho real em dev

Como **engenheiro**, quero que dev execute trabalho real (deploy real para namespace efémero, build real para registry de dev, validação OPA real) em vez de simulação, para que o que testo em dev seja fiel ao que corre em produção.

Hoje os defaults desligam GitOps/CI/integrações e o sistema cai em simulação silenciosa, tornando dev não-representativo.

### Arquiteto entrega os caminhos reais em falta

Como **arquiteto**, quero que os caminhos cognitivos que hoje são heurística (classificação NLU, extração de subject/entities, consenso ML, geração de código) sejam implementados de raiz como caminho real primário, para que a qualidade do plano e da execução deixe de depender de keyword-matching e stubs.

## Spec Scope

1. **Contrato de evidência de conclusão** - Cada `task_type` define o artefacto verificável que prova trabalho real; o `execution_engine` só emite `COMPLETED` se a evidência existir e for validável.
2. **Remoção de simulação** - Eliminar os caminhos `_execute_simulation`/`stub://`/`noop` como resultado de produção e dev; substituí-los por execução real ou falha explícita (sem `ALLOW_SIMULATION`).
3. **Caminhos reais de distância curta** - Entregar trabalho real verificável em: query (confirmar real), transform (data-flow real entre tasks), validate (políticas OPA reais por domínio), subject/entities (NER sintático).
4. **Caminhos reais de distância média** - Ativar e robustecer build real (Code Forge), deploy real via GitOps (ArgoCD/Flux) com ambiente efémero em dev, e registar/wirear o Fluxo G de geração.
5. **Caminhos reais de distância longa (épicos)** - Implementar de raiz: classificador NLU ML, consenso ML honesto (modelo não-descartado, maioria-não-ML como falha), preditores ML do orchestrator, geração de código real (LLM/Code Forge) no Fluxo G, reforço semântico do STE (embeddings/NER).
6. **Honestidade como piso (anti-regressão)** - Métricas `degradation_total`/`real_path_unavailable_total` e modo estrito (`STRICT_REAL_PATH`) que falha quando o caminho real está indisponível — para impedir o regresso silencioso à simulação durante e após a implementação.

## Out of Scope

- Construção da infraestrutura física de cluster (provisionamento de nós); assume-se o cluster K8s existente, mas a spec inclui a configuração de ambientes efémeros sobre ele.
- Dashboards/visualização das novas métricas (a spec emite as métricas; a UI é trabalho a jusante).
- Substituição do motor Temporal ou do broker Kafka.
- Mocks em **testes** (legítimos): a spec exige trabalho real no **runtime** do pipeline, não nos testes unitários.

## Expected Deliverable

1. Um plano cuja execução não produza evidência real **falha** (não fica `COMPLETED`), em qualquer ambiente; não existe caminho de simulação que emita `COMPLETED`.
2. Para cada `task_type`, a evidência de trabalho real é consultável: build → digest de artefacto pullable; deploy → recurso ArgoCD/Flux reconciliado; validate → decisão OPA com regras avaliadas; transform → output derivado do input real; generate_code → ficheiros commitados.
3. Em dev, um plano de criação de software executa o Fluxo G real (gera código, faz build e deploy reais para namespace efémero) ou falha explicitamente — nunca simula.
4. A classificação de domínio (NLU) e a extração de subject/entities resultam de modelo/NER reais, com confidence honesta; os specialists usam o modelo ML carregado e o consenso escala para revisão quando a maioria dos votos não é ML.
