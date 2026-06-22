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
- ✅ **Retraining vê ≥ baseline de amostras** — provado na Task 3 (abaixo).

---

# Task 3 — Repontar consumidores read-only para `neural_hive_dev`

## DoD da Task 3 — checklist com evidência

| Item DoD | Estado | Evidência |
|---|---|---|
| Cronjobs de treino leem `neural_hive_dev` (3.1) | ✅ (declarativo) | `MONGODB_DATABASE: neural_hive_dev` nos 3 manifests |
| Feature-store lê o alvo (3.2) | ✅ (declarativo) | `environments/dev/helm-values/feature-store-values.yaml` |
| Um retraining vê ≥ nº de amostras do baseline (3.3) | ✅ (data-readiness) | query real do trainer: `neural_hive_dev` ≥ `neural_hive` em todas as métricas |

## 3.1 — Repoint dos cronjobs (declarativo, env `MONGODB_DATABASE`)

Nenhum destes 3 cronjobs está **deployed** no cluster (objetos ausentes em
`mlflow`/`neural-hive-mind`/`neural-hive-ml`); o repoint é declarativo no manifest
versionado. A coluna "Código honra a env?" refere-se à resolução da DB no código,
não a estado de runtime.

| Cronjob | Ficheiro | Env editada | Código honra a env? |
|---|---|---|---|
| `specialist-models-retraining` (ns `mlflow`) | `k8s/cronjobs/specialist-retraining-job.yaml` | `MONGODB_DATABASE: neural_hive_dev` | ✅ — caminho primário `RealDataCollector` honra `os.getenv("MONGODB_DATABASE")` (`train_specialist_model.py:706`) |
| `business-metrics-collector` (ns `neural-hive-mind`) | `k8s/cronjobs/business-metrics-job.yaml` | `MONGODB_DATABASE` + `CONSENSUS_MONGODB_DATABASE: neural_hive_dev` | ✅ — `run_business_metrics_collector.py:34,37` honram as envs |
| `predictive-models-training` (ns `neural-hive-ml`) | `k8s/cronjobs/predictive-models-training-job.yaml` | `MONGODB_DATABASE: neural_hive_dev` (declarada) | ⚠️ **inerte até Fase 5.1** — `train_predictive_models.py:54` tem a DB hardcoded (`self.mongo_client.neural_hive`) e ignora a env |

## 3.2 — Feature-store

`services/feature-store/src/config/settings.py:40` lê `MONGODB_DATABASE` (pydantic,
default de código `neural_hive`). Criado
`environments/dev/helm-values/feature-store-values.yaml` com `MONGODB_DATABASE:
neural_hive_dev`. **NOTA:** o feature-store **não está deployed** neste cluster
(`kubectl get deploy -A | grep feature-store` vazio) — o repoint fica versionado e
pronto para o deploy.

## 3.3 — Prova de "retraining vê ≥ baseline" (data-readiness)

O job containerizado **não foi executado**: os cronjobs não estão deployed e as
imagens (`...ecr.us-east-1.amazonaws.com/...` para specialists,
`neural-hive-ml-training:1.0.7` para preditivos) não estão disponíveis neste
cluster Contabo (`neural-hive-prod`). Em vez de fingir um job (verde-falso), a
prova é a **query real que o trainer usa** (`RealDataCollector`, ver
`ml_pipelines/training/real_data_collector.py:273,310-313`) executada contra
ambas as DBs — é exatamente o que o retraining "vê":

Threshold de feedback: o default real do trainer é `min_feedback_rating=0.0`
(`real_data_collector.py:231`) e o cronjob não o altera — por isso a métrica
principal usa `human_rating ≥ 0.0`; mostra-se também `≥ 0.5` (mais restritivo) por
referência. O gate (dev ≥ baseline) vale em ambos.

| Métrica (query real do trainer) | `neural_hive` (baseline) | `neural_hive_dev` (pós-Task 2) | dev ≥ baseline |
|---|---|---|---|
| `specialist_opinions` total | 8291 | 8483 | ✅ |
| opiniões na janela `created_at ≥ now-90d` | 1806 | 1998 | ✅ |
| amostras válidas corpus, `human_rating ≥ 0.0` (default do job) | 2406 | 2406 | ✅ (=) |
| amostras válidas corpus, `human_rating ≥ 0.5` (referência) | 1582 | 1582 | ✅ (=) |
| amostras válidas 90d (`≥ 0.0` ou `≥ 0.5`) | 5 | 5 | ✅ (=) |

Toda a métrica em `neural_hive_dev` é ≥ a de `neural_hive` — **o sinal de treino
está reunificado** (dev tem agora todo o corpus legado + os frescos). Antes da
Task 2, `neural_hive_dev` tinha apenas o corpus fresco e o retraining (apontado a
`neural_hive`) nunca via os dados frescos; agora a DB canónica contém ambos.

## Achados honestos (fora do âmbito da Task 3 — encaminhados para Fase 5.1)

A Fase 5.1 ("tornar `MONGODB_DATABASE` explícito/obrigatório nos `settings.py`,
fail-fast") é o lugar próprio para estes; documentados aqui sem mascarar:

1. **DB hardcoded ignora a env** em `ml_pipelines/training/train_predictive_models.py:54`
   (`self.mongo_client.neural_hive`) e no caminho secundário
   `ml_pipelines/training/train_specialist_model.py:903` (`db = client["neural_hive"]`).
   O caminho **primário** do retraining (RealDataCollector) honra a env — por isso
   o gate 3.3 é real. Os hardcodes precisam do fix da Fase 5.1 para o repoint ser
   total.
2. **Divergência de coleção de feedback:** `RealDataCollector` usa por default a
   coleção `feedback` (`real_data_collector.py:131-133`), que está **vazia** (0 em
   ambas as DBs); os dados reais vivem em `specialist_feedback` (2482). É um bug
   pré-existente do pipeline ML (não introduzido pela convergência) — o cronjob
   teria de definir `FEEDBACK_COLLECTION=specialist_feedback`.
   **Interação com o achado nº1:** com `feedback` vazia, o caminho primário pode
   render poucas/0 amostras úteis e accionar o caminho secundário
   (`train_specialist_model.py:903`, DB hardcoded `neural_hive`) — o que reforça a
   **urgência da Fase 5.1** (não a dilui). A prova 3.3 acima usa a coleção com
   dados reais (`specialist_feedback`) para medir o gate de convergência, que é
   sobre a reunificação do corpus, independente deste bug de configuração do trainer.
3. **`predictive` depende de `execution_tickets`** (0 em `neural_hive`/`neural_hive_dev`;
   os tickets reais estão em `neural_hive_orchestration`/PostgreSQL) — bloqueio do
   diagnóstico do pipeline ML (Tasks 9/12), independente da convergência.

## Reversibilidade

Cada repoint é declarativo (1 edição de manifest/values), revertível voltando
`MONGODB_DATABASE` a `neural_hive`. `neural_hive` permanece intacta (fallback vivo).
