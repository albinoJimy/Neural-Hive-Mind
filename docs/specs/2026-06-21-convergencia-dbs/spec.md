# Spec Requirements Document

> Spec: convergencia-dbs
> Created: 2026-06-21
> Status: Planning

## Overview

Convergir as **quatro bases de dados MongoDB** que hoje fragmentam os dados de um único plano cognitivo (`neural_hive`, `neural_hive_dev`, `neural_hive_orchestration`, `neural_hive_workers`) numa **DB canónica única por ambiente** (`neural_hive_dev` em dev), eliminando o "drift" estrutural que separa `plan_approvals` do resto do plano e que **fragmenta o sinal de treino ML** (opinions frescas escritas em `neural_hive_dev` não chegam ao corpus que os cronjobs de retraining leem em `neural_hive`).

A convergência é tratada como **migração de dados, não como troca de variável de ambiente**: a tentativa ingénua anterior (commit `f786fb16`, repontar o approval-service sozinho para `neural_hive_dev`) partiu o pipeline (lookup de aprovação HTTP 404 → 0 tickets → C3–C6 partido) e foi revertida deliberadamente (`6fddd01d`). Esta spec entrega a convergência de forma **faseada, reversível e com gate E2E entre fases**, com a regra de ouro: **migrar dados primeiro, repontar serviço depois, verificar, só então avançar.**

Distinção orientadora:

```
fragmentação silenciosa (4 DBs, sinal partido) → convergência verificada (1 DB, gate E2E) → prevenção (config explícita + guarda anti-regressão)
```

## User Stories

### Operador vê os dados de um plano numa só DB

Como **operador**, quero que todas as coleções de um plano cognitivo (`cognitive_ledger`, `specialist_opinions`, `consensus_decisions`, `plan_approvals`, `plan_features`) vivam na **mesma base de dados**, para que diagnosticar um run não exija saber que cada coleção está numa DB diferente.

Hoje `plan_approvals` vive em `neural_hive` e o resto em `neural_hive_dev`; o orchestrator usa `neural_hive_orchestration` e os workers `neural_hive_workers` (DLQ).

### Engenheiro de ML treina sobre o corpus completo

Como **engenheiro de ML**, quero que os cronjobs de retraining (`specialist-retraining`, `predictive-models-training`) leiam **o mesmo corpus** onde as opinions/feedbacks frescos são escritos, para que o treino reflita os dados mais recentes e não um corpus congelado.

Hoje o retraining lê `neural_hive` (8291 opinions históricas) mas o pipeline escreve opinions frescas em `neural_hive_dev` — o sinal recente nunca chega ao treino.

### Arquiteto elimina o default implícito que gera drift

Como **arquiteto**, quero que `MONGODB_DATABASE` seja **configuração explícita e versionada** em todos os serviços (em vez de cair no default de código `neural_hive`), para que nenhum serviço novo caia silenciosamente na DB errada e o drift não regresse.

Hoje 4+ serviços (approval-service, gateway, worker-agents, feature-store, optimizer, queen) não têm dev-values e herdam o default de código `neural_hive`.

## Spec Scope

1. **Baseline e backup** — Snapshot verificável (com restore-test) das 4 DBs Mongo + PostgreSQL antes de qualquer escrita; inventário de fonte-de-verdade por coleção.
2. **Consolidação do corpus de treino** — Migrar (copiar) o subconjunto **válido** do corpus de `neural_hive → neural_hive_dev` (excluindo registos degenerados), recriar índices/TTL GDPR e repontar os consumidores read-only (cronjobs ML, feature-store).
3. **Repoint do approval-service (o ponto que partiu)** — Com os dados já presentes no alvo, criar dev-values declarativos e repontar o approval-service para `neural_hive_dev`, com gate E2E completo (sem 404).
4. **Repoint dos restantes escritores** — gateway, worker-agents e avaliação/consolidação de `neural_hive_orchestration` e `neural_hive_workers`.
5. **Janela de corte** — Migração-delta final + freeze curto (ou frozen read-only) para eliminar escrita dupla durante a transição.
6. **Prevenção de regressão** — Tornar `MONGODB_DATABASE` explícito/obrigatório (fail-fast), guarda anti-regressão no E2E/CI (assert estruturado de "coleção em DB inesperada"), arquivar `neural_hive` read-only.

## Out of Scope

- **ClickHouse** (`clickhouse_database: neural_hive` em optimizer/memory-layer) e a DB `neural_hive_analytics` — sofrem do mesmo padrão de fragmentação mas merecem um plano gémeo separado (não Mongo).
- **PostgreSQL `neural_hive_tickets`** — é a fonte canónica de tickets por desenho; não converge para Mongo. Só entra no backup (Fase 0).
- Convergência em ambientes que não dev (não existe cluster prod separado nesta fase).

## Expected Deliverable

1. Um plano cognitivo de teste tem **todas** as suas coleções em `neural_hive_dev` (verificável por contagem por DB), e o E2E A→C6 fecha 8/8 tickets COMPLETED sem 404 de aprovação.
2. Um retraining executado vê ≥ o nº de amostras do baseline (sinal de treino reunificado, verificável nos logs do job).
3. `neural_hive` fica arquivada read-only (sem escritas novas) e nenhum serviço cai no default de código (verificável por `MONGODB_DATABASE` explícito em todos os deployments).
