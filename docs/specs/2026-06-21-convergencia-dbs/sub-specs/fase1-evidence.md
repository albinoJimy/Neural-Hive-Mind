# Evidência de execução — Fase 1 (Task 2: migrar corpus válido `neural_hive → neural_hive_dev`)

> Spec: convergencia-dbs — Fase 1 (consolidar o corpus de treino, sem repontar escritores)
> Artefacto de evidência **one-time** (regista as provas reais que fecham o DoD
> da Task 2). Contexto kubectl: `neural-hive-prod`.

A **regra de ouro** da spec é "Concluído = o trabalho real aconteceu e é provável
por evidência". Esta página é essa prova: cada item do DoD com a sua evidência
medida no cluster (não `success=True`), incluindo uma **verificação independente**
do estado do MongoDB após a migração.

Migração executada por `scripts/db-convergence/10-migrate-corpus.{sh,js}` (cópia
**aditiva, idempotente e não-destrutiva**; `neural_hive` fica intacta como
fallback vivo). Backup canónico da Fase 0: `20260622T085101Z`.

## DoD da Task 2 — checklist com evidência

| Item DoD | Estado | Evidência |
|---|---|---|
| Script de migração aditiva idempotente (2.1) | ✅ | 2ª execução APPLY insere 0 (abaixo); 0 duplicados por chave natural |
| De-duplicação de `specialist_opinions` (2.2) | ✅ | chave lógica `plan_id+specialist_type+created_at`; 0 dups por `opinion_id` |
| Recriar índices + TTL GDPR m002 (2.3) | ✅ | índices recriados (0 erros); `plan_approvals.created_at_ttl expireAfterSeconds=63072000` |
| Validar contagens e integridade (2.4) | ✅ | contagens == origem; amostragem de conteúdo (25/coleção, 0 mismatches) + verificação independente |
| Contagens copiadas == origem (DoD macro) | ✅ | `missing_after=0` nas 5 coleções (verificação independente abaixo) |

## 2.1–2.4 — Resultado da migração (modo APPLY, veredicto OK)

Saída do `10-migrate-corpus.js` (campos-chave por coleção; `MIGRATION_VERDICT=OK`,
`index_errors=0`, `write_errors_total=0`):

| Coleção | chave única | src | dst antes | copiados | dst depois | `missing` | `content_mismatches` | `copy_complete` |
|---|---|---|---|---|---|---|---|---|
| `specialist_feedback` | `feedback_id` | 2482 | 0 | 2482 | 2482 | 0 | 0 | ✅ |
| `specialist_opinions` | `opinion_id` (+de-dup lógica) | 8291 | 192 | 8291 | 8483 | 0 | 0 | ✅ |
| `plan_approvals` | `plan_id` | 486 | 0 | 486 | 486 | 0 | 0 | ✅ |
| `plan_features` | `plan_id` | 648 | 30 | 647 | 677 | 0 | 0 | ✅ |
| `explainability_ledger` | `_id` | 18626 | 293 | 18626 | 18919 | 0 | 0 | ✅ |

- **Não-destrutivo provado:** `plan_features` saltou **1** doc (`skipped_existing_key=1`)
  cujo `plan_id` já existia no alvo (doc fresco do pipeline) — a migração **não o
  clobrou**. Idem `specialist_opinions` (192 frescos preservados) e
  `explainability_ledger` (293 frescos preservados).
- **Integridade de conteúdo (2.4):** amostra de 25 docs/coleção comparada
  payload-a-payload (forma canónica EJSON) origem↔alvo — `content_mismatches=0` e
  `sample_not_copied=0` em todas.

## Idempotência — 2ª execução APPLY insere 0

A migração foi corrida **duas vezes** com `APPLY=true`. A 2ª execução (com o
corpus já presente) reportou, em todas as 5 coleções: `candidates=0`,
`inserted=0`, `skipped_existing_key` == `src_count`, `write_errors=0`,
`dup_key_skipped=0`. Re-executar é um no-op seguro — idempotência provada.

## Verificação INDEPENDENTE no cluster (não confia no output do script)

`mongosh` read-only direto sobre `neural_hive_dev` (2026-06-22):

```
=== contagens neural_hive_dev ===
  specialist_feedback: dev=2482  (src=2482)
  specialist_opinions: dev=8483  (src=8291)   # 192 frescos + 8291 legado
  plan_approvals: dev=486  (src=486)
  plan_features: dev=677  (src=648)            # 30 frescos + 647 (1 saltado)
  explainability_ledger: dev=18919  (src=18626) # 293 frescos + 18626 legado

=== TTL GDPR em neural_hive_dev ===
  plan_approvals.created_at_ttl = expireAfterSeconds=63072000 key={"created_at":1}
  specialist_feedback.created_at_ttl = expireAfterSeconds=63072000 key={"created_at":1}

=== unicidade preservada (0 = sem duplicados de chave natural) ===
  specialist_feedback dups por feedback_id = 0
  specialist_opinions dups por opinion_id = 0
  plan_approvals dups por plan_id = 0
  plan_features dups por plan_id = 0

=== amostra integridade ===
  plan_approval (plan_id=343b9ef4-...) presente no dev=true  payload_igual=true
```

Toda a origem está presente no alvo; zero duplicados de chave natural; TTL GDPR de
`plan_approvals` ativo (2 anos); payload idêntico na amostra independente.

## Achado honesto — TTL GDPR de `specialist_feedback` é INERTE (quirk do m002)

O `m002_gdpr_ttl_indexes.py` cria o TTL de `specialist_feedback` no campo
`created_at`, mas esses documentos usam `submitted_at` (não têm `created_at`). Um
índice TTL sobre um campo ausente **nunca expira** documentos. O script:

1. **Replica o m002 fielmente** (campo `created_at`) — é o contrato nomeado no DoD,
   e divergir criaria conflito quando o `approval-service` correr o m002 no alvo.
2. **Sinaliza o quirk honestamente** (`ttl_warnings`) em vez de o mascarar:
   `specialist_feedback: TTL em 'created_at' INERTE — 0/2482 docs tem o campo como Date`.

O TTL GDPR **exigido pelo DoD** (`plan_approvals`) está correto e ativo. A
correção do campo do TTL de `specialist_feedback` no m002 é um **ticket próprio do
approval-service** (fora do âmbito cirúrgico da Task 2).

## Reversibilidade

A migração é aditiva: `neural_hive` permanece intacta (fallback vivo até ao corte
da Fase 4). Reverter = remover do alvo os docs copiados (por chave natural) ou
restaurar `neural_hive_dev` do backup `20260622T085101Z`. Nenhum dado de origem foi
movido ou alterado.

## Gate da Fase 1 (parcial)

- ✅ **Contagens copiadas == origem (menos degenerados)** — `cognitive_ledger` legado
  excluído por desenho (0 candidatos válidos, Fase 0); as 5 coleções do corpus
  copiadas a 100% (`missing=0`).
- ⏭️ **Retraining vê ≥ baseline de amostras** — pertence à **Task 3** (repontar os
  cronjobs read-only para `neural_hive_dev` e executar um retraining). Não faz parte
  da Task 2 (migração); fica como o próximo passo da Fase 1.
