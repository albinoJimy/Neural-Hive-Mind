# Fase 3 — Prova de extensibilidade multi-linguagem (Evidência)

> Spec: Extrair GENERATE como capacidade autónoma (multi-linguagem-ready)
> Task 4 — Garantir que adicionar uma stack não toca contrato/routing
> Data: 2026-06-26 · Branch: `feat/convergencia-dbs` · Serviço: `orchestrator-dynamic`

## Estado: COMPLETA — extensibilidade provada na fronteira, 8 testes verdes (unit/bloco)

Task de **prova de propriedade** (não implementa outra stack — Out of Scope). Pipeline:
dev (TDD) → auditoria qualidade (SHIP, mutation testing) → auditoria completude
(INCOMPLETO→remediado) → remediação dirigida. Evidência **unit-level** (o gate E2E cluster é
a Fase 4/Task 5). **4.2 não exigiu ajuste de produção** — `capability.py`/`stacks.py` ficam
sem diff (a propagação completa da estratégia já fora feita na Fase 1).

## Entregáveis (ficheiro novo, aditivo)

- `tests/unit/capabilities/test_generate_extensibility.py` — **8 testes**. Único entregável de
  código da Task 4. `git diff src/capabilities/generate/` = **vazio** (produção intacta).

A stack **fake** usada é `elixir/phoenix` com valores DISTINTOS de FastAPI
(`template_ref="phoenix"`, `builder="buildpacks"`, `health_path="/healthz"`, `container_port=4000`),
registada **apenas no teste** — qualquer leak de valor FastAPI é apanhado por assert.

## DoD / Scope 4 / GEN-US3 — cobertura ponto-a-ponto (provado por teste)

| Item | Estado | Evidência (`test_generate_extensibility.py`) |
|------|--------|----------------------------------------------|
| Fake registada só em teste → selecionada via `target` | COBERTO | `test_fake_registada_selecionada_via_target` (`start_workflow` 1×, `args[0] is FluxoGWorkflow.run`) |
| MESMO caminho de contrato (workflow mockado) | COBERTO | `test_caminho_de_contrato_identico_fake` (`start` + `map_result`) |
| Propaga valores da estratégia FAKE (sem FastAPI hardcoded) | COBERTO | asserts `template_ref/builder/health_path/container_port == FAKE` + `!= "fastapi"/"/health"/8080` |
| SEM alterar `GenerateRequest`/`GenerateResult` | COBERTO | `type(result) is GenerateResult`; `type(request) is GenerateRequest`/`GenerateTarget` |
| SEM alterar routing | COBERTO (estrutural) | nenhum ficheiro de routing tocado (`git status`); routing é journey-based (congelado na Fase 2 por `test_workflow_start_journey_routing.py`) |
| Stack desconhecida/removida → FAILED sem iniciar | COBERTO | `test_registry_vazio_stack_fake_falha_sem_iniciar`, `test_registar_fake_nao_reintroduz_fastapi` (`UnsupportedStackError` + `start_workflow.assert_not_called()`) |
| `map_result` stack-agnóstico em SUCESSO **e** FALHA | COBERTO | `test_contrato_inalterado_map_result_stack_agnostico` (completed) + `test_map_result_stack_agnostico_falha_fake_sem_lenidade` (failed: `failure_reason` presente, `code_artifact_id`/`deployment` None) |
| Registar a fake NÃO contamina `default_stack_registry` | COBERTO (isolamento) | `test_registar_fake_nao_contamina_default_registry` (default fresco só conhece python/fastapi) |

GEN-US3 (spec): cenário 1 (FastAPI resolvida) ✓, cenário 2 (nova stack não muda contrato) ✓,
cenário 3 (não suportada falha fechado, não cai p/ FastAPI) ✓. Expected Deliverable 3 ✓.

## Anti-verde-falso — provado por mutation testing (auditoria de qualidade)

Mutações no código de **produção** → cada uma derruba ≥1 teste (provando que a prova "morde"):

- Desactivar o gate `if dep.get("verified") is not True` (`capability.py:166`) →
  `test_map_result_stack_agnostico_falha_fake_sem_lenidade` falha (devolveria `completed`).
- `StackRegistry.resolve` cair em fallback silencioso para FastAPI (`stacks.py:83`) → 3 testes
  falham (`DID NOT RAISE UnsupportedStackError`).
- Hardcodar valores FastAPI na propagação `setdefault` (`capability.py:105-108`) →
  `test_fake_registada_selecionada_via_target` falha (`'fastapi' != 'phoenix'`).

Após reverter as mutações, `git diff src/capabilities/generate/` vazio e 46/46 verdes.

## 4.2 — acoplamento FastAPI fora da entrada do registry: NENHUM (justificado)

Greps por `fastapi|8080|/health|template_ref|health_path|container_port` no caminho da fronteira:

- `capability.py:101-109` — propaga `strategy.*` via `setdefault`; **zero** literais FastAPI.
- `stacks.py:90-108` — `default_stack_registry()` regista python/fastapi: é **a entrada do
  registry** (local correto; o DoD permite acoplamento aqui).
- `decision_consumer.py:_extract_generate_target` — `language = params.get("language") or "python"`
  / `framework = ... or "fastapi"`: é o **default de derivação do target** (a entrada do registry),
  não sobrepõe uma stack fixada pelo plano. Um plano com `parameters.language=elixir` → target
  elixir/phoenix → registry → desconhecida → FAILED. Não é acoplamento fora da fronteira.
- `decision_consumer.py:361` `:8080` = URL do Kafka Schema Registry (não relacionado).
- Materialização real FastAPI (templates G6-G8/code-forge) → **Out of Scope**.

Conclusão: nenhum ajuste de produção necessário (4.2 satisfeito por justificação + asserts de
ausência de leak).

## Flake observado na auditoria — diagnosticado como artefacto do pipeline (não bug real)

A auditoria de completude observou `test_fake_registada_selecionada_via_target` falhar **uma vez**
(`'fastapi' == 'phoenix'` em `template_ref`), não reproduzível. **Causa-raiz:** as duas auditorias
correram em paralelo na mesma working tree e a auditoria de qualidade tinha (temporariamente)
hardcodado valores FastAPI em `capability.py:105-108` para mutation testing — a auditoria de
completude correu pytest nessa janela. **Não é bug de isolamento:** a `capability.start` faz cópia
shallow do `cognitive_plan` e dos `parameters` (`{**...}`), não muta o request original. Provado:
tree de produção limpa + **18+ runs combinados verdes** (10× `54 passed`, 8× `83 passed` com o
comando exacto do auditor, 5× o teste isolado).

## Verificação
- `python3 -m pytest tests/unit/capabilities/ -q` → **46 passed** (extensibility: 8).
- Run combinado (capabilities + consumers routing + journey routing) 8× → **83 passed** estável.
- `black -l 100 --check` → limpo · `ruff check --select F,E9` → sem findings.
- Regressão: failed pré-existente idêntico (`NameError: timedelta` em 4 ficheiros sem relação,
  bug de import py3.10), `+8 passed` — **zero regressão** (mudança puramente aditiva, sem diff de
  produção).
