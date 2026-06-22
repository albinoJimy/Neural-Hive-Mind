# Evidência de execução — Fase 0 (Task 1: backup, inventário e baseline)

> Spec: convergencia-dbs — Fase 0 (preparação risco-zero)
> Artefacto de evidência **one-time** (ao contrário de `inventory.md`, que é
> regenerado idempotentemente por `00-inventory.sh`). Regista as provas reais
> que fecham o DoD da Task 1; não é regenerado automaticamente.
> Contexto kubectl: `neural-hive-prod`.

A **regra de ouro** da spec é "Concluído = o trabalho real aconteceu e é provável
por evidência". Esta página é essa prova: cada item do DoD com a sua evidência
medida no cluster, não `success=True`.

## DoD da Task 1 — checklist com evidência

| Item DoD | Estado | Evidência |
|---|---|---|
| Dumps das 4 DBs Mongo + PostgreSQL criados | ✅ | Backup `20260621T215728Z` (manifesto abaixo) |
| Backup **restaurado com sucesso** em namespace efémero (restore-test) | ✅ | Restore-test Mongo+PG OK (contagens idênticas, abaixo) |
| Inventário coleção→DB→alvo escrito | ✅ | `sub-specs/inventory.md` (gerado por `00-inventory.sh`) |
| Baseline E2E verde com contagens por DB registadas | ✅ | E2E 2026-06-22 08:40 UTC verde (abaixo) + per-DB no inventário |
| Registos degenerados de `cognitive_ledger` marcados para exclusão | ✅ | `03-identify-degenerate.js` (contagens abaixo) |

## 1.1 — Backup das 4 DBs Mongo + PostgreSQL

Dois backups completos foram criados (ambos gitignored — binários grandes, não
commitados):

- `./.db-backups/20260621T215728Z/` — backup inicial (pré-baseline).
- `./.db-backups/20260622T085101Z/` — backup fresco pós-baseline (canónico para a
  Fase 1), usado no restore-test final pós-remediação.

Manifesto do backup inicial:

```
timestamp_utc=20260621T215728Z
kube_context=neural-hive-prod
mongo=mongodb-cluster/mongodb-756ddddf9c-z52dc
pg=neural-hive-data/postgres-sla-8578895d74-zjn74
mongo:neural_hive=mongo-neural_hive.archive.gz (19M)
mongo:neural_hive_dev=mongo-neural_hive_dev.archive.gz (1.3M)
mongo:neural_hive_orchestration=mongo-neural_hive_orchestration.archive.gz (244K)
mongo:neural_hive_workers=mongo-neural_hive_workers.archive.gz (4.0K)
pg:code_forge=pg-code_forge.dump (8.0K)
pg:neural_hive_tickets=pg-neural_hive_tickets.dump (8.0K)
pg:sla_management=pg-sla_management.dump (160K)
```

As 4 DBs Mongo `neural*` e **todas** as DBs PostgreSQL não-sistema estão
cobertas. Os tickets canónicos reais residem em `sla_management.execution_tickets`
(`neural_hive_tickets` está genuinamente vazia — ver `inventory.md`).

## 1.2 — Restore-test (gate da Fase 0): Mongo **e** PostgreSQL

Executado por `02-restore-test.sh` (namespace efémero isolado, comparação contra
a origem read-only, cleanup garantido). Saída (2026-06-22 08:31 UTC):

```
SUCESSO (Mongo): contagens das coleccoes NAO-VAZIAS IDENTICAS entre origem e restauro.
  origem/restaurado: cognitive_ledger=97, compliance_audit_log=188, consensus_decisions=199,
  explainability_ledger=288, explainability_ledger_v2=191, pheromone_signals=968,
  plan_features=29, redis_fallback=54, specialist_opinions=188
SUCESSO (PostgreSQL): contagem de execution_tickets IDENTICA entre origem e restauro (935).
RESTORE-TEST: OK (mongo:neural_hive_dev, pg:sla_management)
```

- **Mongo:** `neural_hive_dev` restaurada num MongoDB efémero; todas as coleções
  não-vazias com contagem idêntica à origem.
- **PostgreSQL:** `sla_management` (DB com dados reais) restaurada num PostgreSQL
  15 efémero via `pg_restore`; `execution_tickets` idêntico à origem.
- Namespace efémero apagado pelo trap de cleanup (confirmado: 0 namespaces
  `dbconv-*` residuais).

**Re-prova pós-remediação (2026-06-22 08:54 UTC):** após corrigir dois achados da
auditoria de qualidade no `02-restore-test.sh` (ver abaixo), o restore-test foi
re-executado contra o backup fresco `20260622T085101Z` e passou limpo:
`SUCESSO (Mongo) ... SUCESSO (PostgreSQL): execution_tickets IDENTICA (943)` →
`RESTORE-TEST: OK (mongo:neural_hive_dev, pg:sla_management)`, exit 0. (943 = 935
baseline + 8 tickets da própria baseline E2E; a extração da contagem com o fix
`tr -dc '0-9'` devolve o número correto.)

**Achados da auditoria de qualidade remediados:**
- CRÍTICO: `tr -d '\r[:space:]'` não funciona como classe POSIX em `tr`
  (tratava `[:space:]` como conjunto literal de chars) → trocado por `tr -dc '0-9'`
  (mantém só dígitos; robusto a `\r`/`\n`/espaços e a falso-negativo).
- ALTO: guarda assimétrica — `PG_DST` não era validado como número antes da
  comparação → adicionada guarda simétrica que falha honestamente se o
  `pg_restore` não produzir a tabela.

**Acoplamento temporal (limitação documentada):** o restore-test compara contra a
origem **viva**. A baseline E2E das 08:40 escreveu em `neural_hive_dev`, pelo que
um restore-test do backup de ontem passou a divergir da origem atual (drift
temporal, não corrupção). Por isso o backup fresco `20260622T085101Z` foi tirado e
testado de imediato. O cabeçalho do script regista a regra: correr o `02` logo
após o `01`, sem pipeline a escrever entremeio.

> Nota: a sessão anterior deixou um namespace efémero órfão
> (`dbconv-restoretest-20260621t220414z`, pod a correr 10h) por interrupção antes
> do cleanup. Foi removido; os restore-tests acima são execuções limpas de ponta
> a ponta com veredicto combinado Mongo+PG.

## 1.3 — Inventário de fonte-de-verdade

Ver `sub-specs/inventory.md` (regenerado por `00-inventory.sh`). Totais por DB
Mongo: `neural_hive` 55051, `neural_hive_dev` 2202, `neural_hive_orchestration`
5384, `neural_hive_workers` 0. PostgreSQL: `sla_management.execution_tickets`
935 (fonte real de tickets); `neural_hive_tickets` 0.

## 1.4 — Registos degenerados de `cognitive_ledger@neural_hive`

Executado `03-identify-degenerate.js` (read-only, **zero deleção**) sobre 10246
docs. Contagens medidas (2026-06-22):

```json
{
  "total": 10246,
  "C1_crud_objective": 3656,
  "C2_single_task": 9903,
  "C3_no_trace": 9637,
  "C4_circular_labels": 3852,
  "DEGENERATE_smoke_crud": 3607,   // C1 ∧ C2 ∧ C3 — exclusão certa
  "SUSPECT_circular_only": 3852,   // C4 — rever antes de migrar
  "VALID_migration_candidate": 0   // objetivo NÃO-CRUD ∧ com trace
}
```

**Achado (reforça o desenho):** `VALID_migration_candidate == 0` — **nenhum** dos
10246 docs do `cognitive_ledger` legado qualifica como candidato válido de
migração. Confirma e endurece a decisão do `technical-spec.md` ("manter dev; não
migrar legado degenerado"): não há nada a salvar do `cognitive_ledger` legado.
A exclusão real é aplicada como filtro na Fase 1, não aqui.

## Baseline E2E — verde com contagens por DB registadas

Run fresco 2026-06-22 08:40 UTC (`scripts/test-e2e-pipeline-completo.sh`,
exit 0). Pipeline A→E completo: gateway → plano STE → consenso (`review_required`)
→ aprovação manual (`approved`) → 8 tickets criados.

| Coleção | Documentos | Status |
|---|---|---|
| cognitive_ledger | 1 | OK |
| specialist_opinions | 4 | OK |
| consensus_decisions | 1 | OK |
| execution_tickets | 8 | OK |
| plan_approvals | 1 | OK |

- Plan ID: `86c37e69-d690-4b95-8011-86d0de8b7567`; Decision ID:
  `51816935-2ac4-44fd-8b55-5bac26ca8a3a`.
- Relatório completo: `docs/test-raw-data/2026-06-22/E2E_PIPELINE_COMPLETO_2026-06-22.md`.

**Drift de baseline confirmado (é o ponto de partida que a spec converge):**

```
AVISO: plan_approvals a 0 em neural_hive_dev mas 1 em neural_hive - drift de DB
```

Este aviso é **esperado** na Fase 0: o `approval-service` ainda escreve
`plan_approvals` em `neural_hive` (default de código). A Fase 2 reaponta-o, e a
Fase 5.2 converte este aviso num assert estruturado (drift esperado vs falha
real). A baseline é, portanto, "pipeline verde a exibir o drift conhecido" — o
estado correto antes de qualquer escrita de migração.

**Reconciliação de contagem (drift vivo):** o `inventory.md` e o `technical-spec.md`
registaram `plan_approvals@neural_hive` = **485** no levantamento de 2026-06-21.
Após a baseline E2E de 2026-06-22, o cluster mede **486** — o +1 é exatamente o
approval que a própria baseline escreveu em `neural_hive` (não em `neural_hive_dev`),
prova direta de que o drift está vivo e é o alvo da Fase 2. O `inventory.md`
mantém-se como o snapshot pré-baseline (alinhado com a tabela do technical-spec);
será regenerado por `00-inventory.sh` no início da Fase 1.
