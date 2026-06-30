# Fase 1 — Evidência (bug #2: análise de schema do serviço data-migration)

> Task 2 da spec "Migração J4 real funcional". Pipeline: dev → auditoria qualidade
> (SHIP) → auditoria completude (COMPLETO) → gate runtime em cluster → commit.
> Data: 2026-06-30. Commit do fix: `a1081f2a`. Imagem provada: `data-migration:a1081f2`.
> DoR ("Fase 0 fechada") satisfeita.

## Resultado: FASE 1 FECHADA — bug #2 corrigido e provado em runtime (POST 201 + total_rows=24)

## 1. Bug #2 — causa-raiz e correção

`services/data-migration/src/db/postgresql.py`, método `get_table_count` (~linha 300):
```python
# ANTES (rebenta):
query = "SELECT COUNT(*) FROM $1.$2"
result = await self.execute_query(query, (schema, table_name), fetch="val")
# DEPOIS:
query = f"SELECT COUNT(*) FROM {schema}.{table_name}"
result = await self.execute_query(query, fetch="val")
```
`$1`/`$2` em posição de **identificador** (schema/tabela) é inválido em PostgreSQL —
placeholders ligam apenas **valores** → `syntax error at or near "$1"`. `get_table_count`
é invocado por `schema_mapper.analyze_legacy_schema` durante `POST /api/v1/migrations`
→ era o bug #2 reportado na Fase 4 do gate.

**Correção segura (espelha `fetch_batch`):** os identificadores `schema`/`table_name`
JÁ são validados por `validate_sql_identifier` (linhas ~285-286) ANTES da interpolação
— a defesa anti-injection mantém-se. Auditoria de qualidade confirmou: a validação
precede a interpolação; `SQL_IDENTIFIER_PATTERN` barra `;`/aspas/espaços.

**Único `$1`-como-identificador do serviço:** varredura de `postgresql.py`,
`data_validator.py`, `batch_migrator.py` — todos os restantes `$1`/`$2` ligam VALORES
(`WHERE x=$1`, `LIMIT $1 OFFSET $2`, `$1::regclass`), válidos. Cadeia
`analyze_legacy_schema` (`get_tables`/`get_table_schema`/`get_primary_keys`/
`get_foreign_keys`/`get_indexes`/`get_table_count`) auditada por completo.

## 2. Testes TDD (anti-verde-falso)

`services/data-migration/tests/integration/test_get_table_count_real_postgres.py`
(novo; docker-gated, cleanup em `finally`; marker `real_integration` em `pyproject.toml`):
- `test_get_table_count_real_returns_seed_counts` — postgres:17-alpine real + seed
  `scripts/init-legacy-db.sql`: contagens `5/5/5/9` (=24). **Reproduz o bug com o
  código `$1.$2` (`PostgresSyntaxError`)**, passa com a fix.
- `test_analyze_legacy_schema_end_to_end_real` — caminho de `POST /migrations`
  (`SchemaMapper.analyze_legacy_schema` → `get_table_count`) com row_counts corretos.
- `test_get_table_count_rejects_injection_identifier` (sempre) — `table_name`/`schema`
  maliciosos → `ValueError` (interpolação NÃO abriu SQL injection).

Resultado: **3 novos PASSED**; suite relacionada (`test_postgresql`/`test_data_validator`/
`test_schema_mapper`/`test_batch_migrator`) **89 passed**, zero regressão. ruff/black
limpos. Falhas crónicas pré-existentes (não tocadas pelo commit): `test_settings.py`
(env-prefix pydantic), `test_e2e.py` (testcontainers API) — ambientais.

## 3. Gate runtime em cluster (subtask 2.3)

Rebuild `data-migration` (`04a757c`→`a1081f2`) via `build-and-push-ghcr.yml` +
`kubectl set image`. `POST /api/v1/migrations` (via python stdlib no pod — imagem sem
curl) contra os fixtures J4:

```
POST /api/v1/migrations  →  HTTP 201
  job_id=d5b9a861-1dab-4095-ad4e-be19bfd00bc1  status=pending
GET  /api/v1/migrations/{job_id}  →  status=pending  total_rows=24  rows_migrated=0
```

- **Bug #2 corrigido em runtime:** o POST **já não dá `syntax error at "$1"`** — a
  análise de schema completa end-to-end. `total_rows=24` prova que o `get_table_count`
  corrigido correu contra o legacy real e contou `5+5+5+9` (anti-verde-falso real, não
  `success=True`).

## 4. Outros bugs expostos pelo primeiro fluxo real (DoD "start/batch")

1. **MongoDB não configurado (config de deploy):** o serviço usava o default
   `mongodb://localhost:27017` (a `insert_schema_mapping` falhava com `Connection
   refused`). Causa: o chart `data-migration-1.0.0` deployado não injeta `MONGODB_URL`.
   **Mitigado para o gate** com `kubectl set env MONGODB_URL=mongodb://root:***@
   mongodb.mongodb-cluster.svc.cluster.local:27017 MONGODB_DATABASE=neural_hive_dev`
   (mesma instância dos outros serviços). **NÃO commitado** (contém credencial; regra
   sem-segredos). **Dívida:** wiring durável via secret/values no chart. Não é o bug #2
   nem código do serviço.
2. **`batch_migrator` escreve com métodos inexistentes (Fase 2/4):** `batch_migrator.py`
   usa `target_client.insert_batch`/`insert_many`/`execute`, mas `PostgreSQLClient` só
   tem `execute_query` → no `POST /migrations/{id}/start` real, escrita falha →
   `rows_migrated=0`. **Não rebenta como o `$1`** e é território da migração real
   (Fase 4 / gate positivo). Sinalizado pela auditoria de completude; **fora do scope
   da Fase 1** (que é desbloquear a criação do job).

## 5. Estado das subtasks

- [x] 2.1 — testes (TDD): análise de schema de legacy real devolve as 4 tabelas sem
  erro; identificador inválido continua rejeitado (sem SQL injection).
- [x] 2.2 — corrigida a introspeção (`get_table_count`); confirmado único ponto.
- [x] 2.3 — gate: `POST /migrations` 201 + `GET` coerente (`total_rows=24`), em cluster.

## 6. Dívida que transita

- MongoDB wiring durável no chart `data-migration` (hoje patch de env em runtime).
- `batch_migrator` write methods (Fase 2/4): a resolver quando o batch real correr.
- Infra orchestrator (#4): requests `256Mi`/HPA pinado da Fase 0 — restaurar na Fase 4.
