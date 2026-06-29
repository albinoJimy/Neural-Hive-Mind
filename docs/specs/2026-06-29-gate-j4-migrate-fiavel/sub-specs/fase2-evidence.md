# Fase 2 — Evidência: gate `/validate` fail-closed (Task 3)

> Spec: `docs/specs/2026-06-29-gate-j4-migrate-fiavel/` — eixo Jornadas, gate "J4/MIGRATE fiável" (ADR-0011).
> Objectivo: tornar o gate de validação da migração **real** e **fail-closed**, eliminando o verde-falso da
> activity `validate_data`. TDD estrito, diffs mínimos (py3.10), zero regressão.

## 1. Verde-falso descoberto (o que estava errado)

A activity `validate_data` em `services/orchestrator-dynamic/src/activities/data_migration.py` **hardcodava o
sucesso** — não validava nada:

```python
validation_report = {
    "overall_passed": True,                       # <-- hardcoded
    "table_results": [
        {
            "table": t["target_table"],
            "row_count_match": True,               # <-- hardcoded
            "legacy_rows": t.get("estimated_rows", 0),   # <-- ESTIMADO, não real
            "target_rows": t.get("estimated_rows", 0),   # <-- ESTIMADO == legacy por construção
            "sample_checks_passed": True,          # <-- hardcoded
        }
        for t in tables
    ],
    ...
}
return {"success": True, "validation_report": validation_report}
```

Tinha o comentário "_Na implementação real, comparar dados_". Consequência: o gate interno do
`DataMigrationWorkflow` (`src/workflows/data_migration_workflow.py:185-196`)

```python
validation_result = await self._validate_data(...)
if not validation_result["success"]:
    validation_report = validation_result.get("validation_report", {})
    if not validation_report.get("overall_passed", False):
        return await self._handle_rollback(workflow_id, "validation", ...)
```

**nunca disparava o rollback** — `success` era sempre `True` e `overall_passed` sempre `True`. A migração
era declarada válida sem comparar uma única linha. Combinado com o verde-falso do batch
(`run_batch_migration`, linha ~420: `rows_migrated = total_rows  # Simular 100%`), o pipeline reportava
"migração completa e validada" com o destino potencialmente vazio.

## 2. Correção (chamada real ao `/validate`, fail-closed)

A `validate_data` foi reescrita para chamar o serviço REAL que já existe:

- **Endpoint:** `POST {base_url}/api/v1/migrations/{job_id}/validate` (data-migration:8019).
- **Implementação real do serviço:** `services/data-migration/src/services/data_validator.py` →
  `validate_row_counts` faz `SELECT COUNT(*) FROM source` vs `SELECT COUNT(*) FROM target` com tolerância,
  mais integridade referencial e distribuição; `generate_validation_report` consolida em `overall_passed`.
- **Formato da resposta** (`ValidationResultResponse` em
  `services/data-migration/src/api/routers/migrations.py:126`): `{ overall_passed, total_validations,
  passed_validations, failed_validations, results: [{ table, type, passed, legacy_count, modern_count,
  discrepancy, details }] }`.

A activity mapeia `results[].legacy_count`/`modern_count` para `legacy_rows`/`target_rows` **reais** (não
estimados) e deriva `overall_passed` do serviço.

### Injeção de dependências (espelha o padrão do Fluxo G)

Acrescentado, ao nível do módulo, `_http_client: Optional[httpx.AsyncClient]` +
`_data_migration_base_url` + `set_data_migration_dependencies(http_client=..., base_url=...)`, idêntico a
`fluxo_g_integration.set_fluxo_g_dependencies`. O worker Temporal
(`src/workers/temporal_worker.py`) injeta o **mesmo** `httpx.AsyncClient` já criado para o Fluxo G.

### Regra FAIL-CLOSED (nunca assume sucesso por defeito)

`success=True` **só** quando o serviço devolve `overall_passed=True` explicitamente. Caso contrário →
`{"success": False, "validation_report": {"overall_passed": False, "reason": ...}, "error": ...}`:

| Condição | Resultado |
|---|---|
| HTTP client não configurado | `success=False` (fail-closed) |
| Erro de rede / exceção httpx | `success=False` |
| Timeout httpx | `success=False` |
| Status não-2xx (4xx/5xx) | `success=False` |
| JSON sem o campo `overall_passed` | `success=False` |
| `overall_passed=False` (counts divergem / integridade falha) | `success=False` |
| `overall_passed=True` | `success=True` |

O helper `_validation_failed(reason)` garante **sempre** `success=False` **e**
`validation_report.overall_passed=False` em simultâneo — exactamente os dois predicados que o gate do
workflow exige para acionar o rollback. Doutrina espelhada do gate J3 GENERATE
(`src/capabilities/generate/capability.py`, `map_result` exige `verified is True`) e de
`caminho-real-first-class` (marcar+medir+falhar, sem fallback que assuma sucesso).

## 3. Como o gate do workflow passa a disparar rollback

Com a activity real, quando a validação reprova (ou o `/validate` está indisponível), `validate_data`
devolve `success=False` + `overall_passed=False`. O bloco `data_migration_workflow.py:185-196` — **não
tocado** (já estava fail-closed à espera de uma activity honesta) — entra no `_handle_rollback(...,
"validation", ...)`. O verde-falso do batch (destino vazio ≠ origem) é apanhado por esta validação real:
`legacy_count != modern_count` → `overall_passed=False` → FAILED + rollback.

## 4. Prova anti-verde-falso (mutação — subtask 3.3)

Testes novos: `services/orchestrator-dynamic/tests/activities/test_validate_data.py` (8 testes). Comando:
`python3 -m pytest tests/activities/test_validate_data.py -q` → **8 passed**.

Duas mutações aplicadas (e revertidas), cada uma derruba ≥1 teste:

- **Mutação A** — repor `overall_passed = True` hardcoded (em vez de derivar da resposta):
  `tests/activities/test_validate_data.py::test_validate_counts_diverge_fails` **FALHA**
  (`1 failed, 7 passed`).
- **Mutação B** — `except`/helper que devolve `success=True` em vez de fail-closed
  (`_validation_failed` a retornar `success=True`): **6 testes FALHAM** (`6 failed, 2 passed`) —
  `http_error`, `timeout`, `5xx`, `4xx`, `json_missing_field`, `no_http_client`.

Restaurado o código → **8 passed**. Logo o verde dos testes está acoplado ao comportamento real e
não é falso.

## 5. Honestidade de escopo

- **Fase 2 testa em bloco** com o `httpx.AsyncClient` **mockado** (stub programável): prova o contrato
  fail-closed da fronteira (mapeamento de resposta + todos os caminhos de falha). A **execução real em
  cluster** (DB legacy com N linhas → migração → `/validate` 200 com counts reais a baterem; e o caminho
  negativo com divergência forçada → FAILED observável) é a **Fase 4** (gate E2E).
- **Não tocado nesta fase:** `run_batch_migration` (batch simulado, linha ~420 — **dívida da Fase 4**; a
  validação real apanha-o porque destino vazio ≠ origem); o gate interno do workflow
  (`data_migration_workflow.py:185-196`, já fail-closed); o routing por journey (Fase 1, congelado).
- **Zero regressão:** `python3 -m pytest tests/consumers/test_decision_consumer_migrate_routing.py -q`
  → **19 passed**.

## 6. Ficheiros

- `services/orchestrator-dynamic/src/activities/data_migration.py` — injeção de deps +
  `validate_data` reescrita (fail-closed) + helper `_validation_failed`.
- `services/orchestrator-dynamic/src/workers/temporal_worker.py` — injeção do http client
  (`set_data_migration_dependencies`).
- `services/orchestrator-dynamic/tests/activities/test_validate_data.py` — **novo**, 8 testes.
