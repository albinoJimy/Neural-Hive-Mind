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

- [ ] 2. Migrar corpus válido `neural_hive → neural_hive_dev`
  - **DoR:** Fase 0 fechada (backup restaurável); script de migração idempotente revisto.
  - **DoD:** contagens copiadas == origem (menos degenerados) para `specialist_feedback`, `specialist_opinions` (de-dup), `plan_approvals`, `plan_features`, `explainability_ledger`; índices recriados; TTL GDPR de `plan_approvals` presente no alvo.
  - [ ] 2.1 Script de migração aditiva idempotente (upsert por chave natural; re-executável sem duplicar)
  - [ ] 2.2 De-duplicação de `specialist_opinions` (chave `plan_id`+`specialist_type`+`created_at`)
  - [ ] 2.3 Recriar índices + índice TTL GDPR (`m002_gdpr_ttl_indexes.py`) em `neural_hive_dev`
  - [ ] 2.4 Validar contagens e integridade (amostragem de docs migrados vs origem)

- [ ] 3. Repontar consumidores read-only para `neural_hive_dev`
  - **DoR:** Task 2 fechada (corpus presente no alvo).
  - **DoD:** cronjobs de treino leem `neural_hive_dev`; um retraining executado vê ≥ o nº de amostras do baseline (sinal reunificado); feature-store lê o alvo.
  - [ ] 3.1 Repontar `specialist-retraining-job`, `predictive-models-training-job`, `business-metrics-job` (env `MONGODB_DATABASE`)
  - [ ] 3.2 Repontar feature-store (criar dev-values ou env)
  - [ ] 3.3 Executar retraining e confirmar nº de amostras ≥ baseline

### Fase 2 — Repontar approval-service (o ponto que partiu antes)

- [ ] 4. Repoint declarativo do approval-service
  - **DoR:** Fase 1 fechada — `plan_approvals`/`specialist_feedback` confirmados em `neural_hive_dev`.
  - **DoD:** E2E A→C6 verde; `plan_approvals` do novo plano em `neural_hive_dev`; 0 ocorrências de HTTP 404 na aprovação; 8/8 tickets COMPLETED.
  - [ ] 4.1 Criar `environments/dev/helm-values/approval-service-values.yaml` com `config.mongodb.database: neural_hive_dev`
  - [ ] 4.2 Atualizar/remover o comentário-aviso em `values-dev.yaml:25-34` (deixa de ser verdadeiro após Fase 1)
  - [ ] 4.3 Deploy declarativo (helm, não patch efémero)
  - [ ] 4.4 Gate E2E completo + rollback documentado (reverter dev-values + redeploy)

### Fase 3 — Repontar restantes escritores

- [ ] 5. gateway-intencoes + worker-agents → `neural_hive_dev`
  - **DoR:** Fase 2 verde.
  - **DoD:** E2E verde após cada repoint; coleções dos serviços no alvo.
  - [ ] 5.1 Criar dev-values em falta para `gateway-intencoes` e `worker-agents`
  - [ ] 5.2 Deploy + gate E2E por serviço

- [ ] 6. Avaliar/consolidar `neural_hive_orchestration` e `neural_hive_workers`
  - **DoR:** Task 5 fechada.
  - **DoD:** decisão documentada: migrar para `neural_hive_dev` ou manter como schema lógico intencional; `neural_hive_workers` (só DLQ) tratado.
  - [ ] 6.1 Mapear leitores/escritores de `neural_hive_orchestration`
  - [ ] 6.2 Migrar ou documentar decisão de manter separado
  - [ ] 6.3 Tratar `execution_tickets_dlq` (vazio → descartar ou migrar)

### Fase 4 — Janela de corte (eliminar escrita dupla)

- [ ] 7. Migração-delta final + freeze curto
  - **DoR:** todos os escritores repontados (Fases 2–3); janela de manutenção acordada.
  - **DoD:** `neural_hive` sem escritas novas durante janela de observação (contagem estável); E2E verde pós-corte.
  - [ ] 7.1 Escalar a 0 os escritores do corpus (freeze) — ou marcar `neural_hive` read-only
  - [ ] 7.2 Migração-delta idempotente (docs novos desde Fase 1)
  - [ ] 7.3 Re-escalar; gate E2E; observar contagem de `neural_hive` estável

### Fase 5 — Prevenção de regressão e limpeza

- [ ] 8. Config explícita + guarda anti-regressão + arquivo
  - **DoR:** Fase 4 fechada; N dias de E2E verde acordados antes de arquivar.
  - **DoD:** nenhum deployment sem `MONGODB_DATABASE` explícito; guarda anti-regressão ativa no E2E/CI; `neural_hive` arquivada read-only (não apagada).
  - [ ] 8.1 Tornar `MONGODB_DATABASE` explícito/obrigatório nos `settings.py` (fail-fast se ausente em ambiente não-test)
  - [ ] 8.2 Transformar o aviso de drift do `test-e2e-pipeline-completo.sh` em assert estruturado (drift esperado vs falha real)
  - [ ] 8.3 Arquivar/renomear `neural_hive` read-only após janela de verde
  - [ ] 8.4 Atualizar inventário canónico (memória/`CONTABO_TICKET.md`) com o estado final
