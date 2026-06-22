# Spec Tasks

> Ordenação: Fase 0 (preparação) → Fase 1 (corpus) → Fase 2 (approval) → Fase 3 (restantes) → Fase 4 (corte) → Fase 5 (prevenção). Cada fase é um gate: só avança com E2E verde + contagens conferidas.
>
> **Regra de ouro:** migrar dados PRIMEIRO, repontar serviço DEPOIS, verificar, só então avançar. Detalhe técnico em `sub-specs/technical-spec.md`.
>
> **Alvo dev:** `neural_hive_dev`.

## Tasks

### Fase 0 — Preparação e baseline (risco zero, não toca runtime)

- [x] 1. Backup, inventário e baseline
  - **DoR:** acesso ao pod `mongodb-*` em `mongodb-cluster`; credenciais `root`; espaço para dumps fora do cluster.
  - **DoD:** dumps das 4 DBs Mongo + PostgreSQL `neural_hive_tickets` criados e **restaurados com sucesso** num namespace efémero (restore-test); inventário coleção→DB→alvo escrito; baseline E2E verde com contagens por DB registadas.
  - **Evidência:** `sub-specs/fase0-evidence.md` (restore-test Mongo+PG OK; degenerados marcados; baseline E2E 2026-06-22 verde).
  - [x] 1.1 `mongodump` de `neural_hive`, `neural_hive_dev`, `neural_hive_orchestration`, `neural_hive_workers` + `pg_dump` de **todas** as DBs PG não-sistema (cobre `sla_management`, fonte real de tickets; `neural_hive_tickets` vazia)
  - [x] 1.2 Restore-test num namespace efémero (Mongo `neural_hive_dev` + PostgreSQL `sla_management` 935 tickets — contagens idênticas à origem)
  - [x] 1.3 Inventário de fonte-de-verdade por coleção (tabela do technical-spec preenchida com contagens atuais)
  - [x] 1.4 Marcar registos degenerados de `cognitive_ledger` (CRUD E2E / labels circulares) para exclusão da migração (10246 docs: 3607 degenerados + 3852 suspeitos; **0 candidatos válidos**)

### Fase 1 — Consolidar o corpus de treino (sem repontar escritores)

- [x] 2. Migrar corpus válido `neural_hive → neural_hive_dev`
  - **DoR:** Fase 0 fechada (backup restaurável); script de migração idempotente revisto.
  - **DoD:** contagens copiadas == origem (menos degenerados) para `specialist_feedback`, `specialist_opinions` (de-dup), `plan_approvals`, `plan_features`, `explainability_ledger`; índices recriados; TTL GDPR de `plan_approvals` presente no alvo.
  - **Evidência:** `sub-specs/fase1-evidence.md` (APPLY verde, `missing=0` nas 5 coleções; 2ª run idempotente insere 0; TTL GDPR `plan_approvals` ativo; verificação independente no cluster).
  - [x] 2.1 Script de migração aditiva idempotente (`10-migrate-corpus.{sh,js}`, insert-if-absent por chave única natural; preserva `_id`; 2ª execução insere 0)
  - [x] 2.2 De-duplicação de `specialist_opinions` (chave lógica `plan_id`+`specialist_type`+`created_at`; 0 dups por `opinion_id` no alvo)
  - [x] 2.3 Recriar índices + índice TTL GDPR (`m002_gdpr_ttl_indexes.py`) em `neural_hive_dev` (`plan_approvals.created_at_ttl expireAfterSeconds=63072000`; quirk inerte de `specialist_feedback` sinalizado, não mascarado)
  - [x] 2.4 Validar contagens e integridade (amostragem de conteúdo 25/coleção, 0 mismatches; verificação independente no cluster)

- [x] 3. Repontar consumidores read-only para `neural_hive_dev`
  - **DoR:** Task 2 fechada (corpus presente no alvo).
  - **DoD:** cronjobs de treino leem `neural_hive_dev`; um retraining executado vê ≥ o nº de amostras do baseline (sinal reunificado); feature-store lê o alvo.
  - **Evidência:** `sub-specs/fase1-evidence.md` (secção Task 3): 4 repoints declarativos; data-readiness `neural_hive_dev ≥ neural_hive` em todas as métricas da query real do trainer (opinions 90d 1998≥1806; corpus válido 1582=1582).
  - [x] 3.1 Repontar `specialist-retraining-job`, `predictive-models-training-job`, `business-metrics-job` (env `MONGODB_DATABASE`) — specialist (primário) e business-metrics honram a env; predictive declarado mas inerte até Fase 5.1 (DB hardcoded em `train_predictive_models.py:54`)
  - [x] 3.2 Repontar feature-store (`environments/dev/helm-values/feature-store-values.yaml`; settings.py honra `MONGODB_DATABASE`; serviço não-deployed → repoint versionado)
  - [x] 3.3 Provar amostras ≥ baseline via query real do trainer (job containerizado não-executável aqui: imagens ECR/locais indisponíveis no cluster Contabo; data-readiness prova o gate sem verde-falso)

### Fase 2 — Repontar approval-service (o ponto que partiu antes)

- [x] 4. Repoint declarativo do approval-service
  - **DoR:** Fase 1 fechada — `plan_approvals`/`specialist_feedback` confirmados em `neural_hive_dev`.
  - **DoD:** E2E A→C6 verde; `plan_approvals` do novo plano em `neural_hive_dev`; 0 ocorrências de HTTP 404 na aprovação; 8/8 tickets COMPLETED.
  - **Evidência:** `sub-specs/fase2-evidence.md` (plano fresco `ed799f2b`: GET aprovação=200 sem 404, approve=200, 8/8 task_ids COMPLETED, plan_approval em neural_hive_dev e ausente de neural_hive).
  - [x] 4.1 Criar `environments/dev/helm-values/approval-service-values.yaml` (`env.MONGODB_DATABASE: neural_hive_dev` — chave real do chart)
  - [x] 4.2 Atualizar o comentário-aviso em `values-dev.yaml` (substituído pelo estado pós-Fase 1 + `MONGODB_DATABASE: neural_hive_dev`)
  - [x] 4.3 Deploy (`kubectl set env` — instância dev gerida manualmente, sem helm release; persistente e reversível)
  - [x] 4.4 Gate E2E A→C6 verde (0 404, 8/8 COMPLETED) + rollback documentado (reverter env + dev-values)

### Fase 3 — Repontar restantes escritores

- [x] 5. gateway-intencoes + worker-agents → `neural_hive_dev`
  - **DoR:** Fase 2 verde.
  - **DoD:** E2E verde após cada repoint; coleções dos serviços no alvo.
  - **Evidência:** `sub-specs/fase3-evidence.md` (Task 5). gateway NÃO usa Mongo (sem repoint); worker repontado + E2E A→C6 verde (plano `cde2180d`, 4/4 task_ids COMPLETED, plan_approval em neural_hive_dev).
  - [x] 5.1 Criar dev-values: `worker-agents-values.yaml` criado; `gateway-intencoes` NÃO persiste em Mongo (settings.py sem campos Mongo, zero cliente Mongo) → não precisa de repoint
  - [x] 5.2 Deploy (`kubectl set env`) + gate E2E verde (GET aprovação=200, 4/4 tickets COMPLETED com o worker em neural_hive_dev)

- [x] 6. Avaliar/consolidar `neural_hive_orchestration` e `neural_hive_workers`
  - **DoR:** Task 5 fechada.
  - **DoD:** decisão documentada: migrar para `neural_hive_dev` ou manter como schema lógico intencional; `neural_hive_workers` (só DLQ) tratado.
  - **Evidência:** `sub-specs/fase3-evidence.md` (Task 6): decisão fundamentada.
  - [x] 6.1 Mapear leitores/escritores de `neural_hive_orchestration` (orchestrator-dynamic + execution-ticket-service, ambos com MONGODB_DATABASE explícito; estado operacional a crescer)
  - [x] 6.2 DECISÃO: **manter** `neural_hive_orchestration` como schema lógico intencional (estado operacional da orquestração, não corpus de treino; fronteira deliberada; tickets canónicos em PostgreSQL)
  - [x] 6.3 `execution_tickets_dlq` vazio + worker repontado (Task 5) → nada a migrar; arquivar `neural_hive_workers` em Fase 5

### Fase 4 — Janela de corte (eliminar escrita dupla)

- [x] 7. Migração-delta final + freeze curto
  - **DoR:** todos os escritores repontados (Fases 2–3); janela de manutenção acordada.
  - **DoD:** `neural_hive` sem escritas novas durante janela de observação (contagem estável); E2E verde pós-corte.
  - **Evidência:** `sub-specs/fase4-evidence.md`. Corpus `neural_hive` congelado no baseline Task2 (Δ=0 nas 5 coleções) após 2 E2E reais; `neural_hive_dev` cresceu; delta=0 candidatos.
  - [x] 7.1 Freeze implícito: escritores do corpus já repontados (Fases 1–3) → sem escrita dupla a eliminar (read-only fica para o arquivo da Fase 5)
  - [x] 7.2 Migração-delta idempotente (`10-migrate-corpus` re-run): delta = 0 candidatos nas 5 coleções (nada escrito em `neural_hive` desde a Fase 1)
  - [x] 7.3 Contagem `neural_hive` estável (Δ=0 sob workload E2E real); `neural_hive_dev` cresceu (+2 planos); E2E verde

### Fase 5 — Prevenção de regressão e limpeza

- [ ] 8. Config explícita + guarda anti-regressão + arquivo
  - **DoR:** Fase 4 fechada; N dias de E2E verde acordados antes de arquivar.
  - **DoD:** nenhum deployment sem `MONGODB_DATABASE` explícito; guarda anti-regressão ativa no E2E/CI; `neural_hive` arquivada read-only (não apagada).
  - [ ] 8.1 Tornar `MONGODB_DATABASE` explícito/obrigatório nos `settings.py` (fail-fast se ausente em ambiente não-test)
  - [ ] 8.2 Transformar o aviso de drift do `test-e2e-pipeline-completo.sh` em assert estruturado (drift esperado vs falha real)
  - [ ] 8.3 Arquivar/renomear `neural_hive` read-only após janela de verde
  - [ ] 8.4 Atualizar inventário canónico (memória/`CONTABO_TICKET.md`) com o estado final
