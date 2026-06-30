# Fase 0 — Contrato + registry de stacks (Evidência)

> Spec: Extrair GENERATE como capacidade autónoma (multi-linguagem-ready)
> Task 1 — Definir o contrato da capacidade e o registry de stacks extensível
> Data: 2026-06-26 · Branch: `feat/convergencia-dbs` · Serviço: `orchestrator-dynamic`

## Estado: COMPLETA — contrato fail-closed + registry stack-neutro, 25 testes verdes

Task aditiva (não há fallback/stub pré-existente a substituir). Pipeline: dev (TDD) →
auditoria qualidade → auditoria completude → remediação dirigida. A evidência da Fase 0 é
**unit-level** (sem gate de cluster — gates de cluster só na Fase 2.3/4).

## Entregáveis (ficheiros novos)

- `src/capabilities/__init__.py`, `src/capabilities/generate/__init__.py` (re-exporta os símbolos públicos).
- `src/capabilities/generate/contract.py` — `GenerateTarget`, `GenerateRequest`, `DeploymentInfo`,
  `GenerateResult` (Pydantic v2).
- `src/capabilities/generate/stacks.py` — `UnsupportedStackError`, `GenerationStrategy`,
  `StackRegistry`, `default_stack_registry()`.
- `tests/unit/capabilities/test_generate_contract.py` (16) + `test_generate_stacks.py` (9).

## Anti-verde-falso (núcleo da spec) — provado por teste

- `GenerateResult(status="failed")` sem `failure_reason` → `ValidationError`.
- `GenerateResult(status="completed")` sem `code_artifact_id` (incl. **só espaços**) → `ValidationError`.
- `GenerateResult(status="completed")` com `failure_reason` (estado contraditório) → `ValidationError`.
- `StackRegistry.resolve()` de stack desconhecida → `UnsupportedStackError` e **NÃO** devolve
  FastAPI (teste explícito de ausência de fallback silencioso).

## Multi-linguagem-ready — provado por teste

- FastAPI registado por omissão com os valores do gate J3/BUILD: `template_ref="fastapi"`,
  `builder="kaniko"`, `health_path="/health"`, `container_port=8080`.
- `GenerateTarget{language, framework}` stack-neutro (sem enum); `register`/`resolve`
  case-insensitive com a **mesma** normalização (simetria provada).
- Registar uma estratégia "fake" (`rust/actix`) é resolvido sem tocar no contrato e com FastAPI
  intacto → ponto de extensão real, documentado na docstring de `stacks.py`.

## DoD "sem lógica de orquestração" — confirmado

Grep por `temporal|workflow|start_workflow|FluxoG|.run(` em `src/capabilities/generate/` e testes →
**zero ocorrências**. Task 1 é só contrato + registry.

## Remediação dirigida (achados das auditorias)

- **M1 (anti-verde-falso):** `code_artifact_id` só com espaços passava como `completed` → fechado
  (`.strip()` no invariante) + teste.
- **B1:** `language`/`framework` normalizados (`strip`) + teste.
- **B2:** `completed` com `failure_reason` (contraditório) → rejeitado + teste.
- **B3:** `GenerationStrategy.container_port` exige `> 0` (`Field(gt=0)`) + teste.
- **B4:** teste de simetria `register`(maiúsculas)/`resolve`(minúsculas).

## Verificação
- `python3 -m pytest tests/unit/capabilities/ -q` → **25 passed**.
- `black -l 100 --check` → 7 ficheiros limpos · `ruff check --select F,E9` → sem erros.
- Smoke import dos símbolos públicos via `src.capabilities.generate` → OK.
