# Spec Tasks

> Migração J4 real funcional. Continuação do gate "J4/MIGRATE fiável" (Fase 4 provou a composição em
> runtime; a migração real ficou bloqueada por bugs de integração). Arquitetura: activities
> thin-wrappers sobre o serviço `data-migration` (fonte de verdade); job_id do serviço como chave única.
>
> **Princípios:** reusar a composição já provada (não re-arquitetar a jornada); thin-wrappers reais (sem
> simulação); anti-verde-falso (validação real fail-closed; rollback em divergência); TDD; diffs mínimos
> (py3.10); zero regressão nos testes congelados do gate. Cada fase é um gate. Detalhe em
> `sub-specs/technical-spec.md`.

## Tasks

### Fase 0 — Pré-condições: seed (#3), determinismo (#1 runtime), harness E2E

- [x] 1. Corrigir o seed do repo, validar #1 em runtime e preparar o harness E2E reprodutível
  - **DoD:** `scripts/init-legacy-db.sql` corrigido no repo (`#`→`--`; `pgoutput` removido/ajustado) e o
    oráculo de contagens (Fase 0 do gate) mantém 24 linhas; **#1 validado em runtime** — rebuild+deploy do
    orchestrator e confirmação de que o `DataMigrationWorkflow` corre sem `os.environ.get` (a composição
    chega à 1ª activity); harness E2E (DBs fixture legacy/moderno + injeção J4) reproduzível a partir dos
    manifests do scratchpad.
  - **Evidência:** `sub-specs/fase0-evidence.md`.
  - [x] 1.1 Testes: seed corrigido parseia num PostgreSQL real (4 tabelas, 24 linhas); oráculo inalterado
  - [x] 1.2 Corrigir `init-legacy-db.sql`; recriar fixture; rebuild+deploy orchestrator; provar #1 em runtime
  - [x] 1.3 Documentar baseline pós-#1 (até onde o fluxo chega antes de bater no #2)

### Fase 1 — Corrigir o serviço data-migration (bug #2: análise de schema)

- [ ] 2. Eliminar o `syntax error at or near "$1"` na criação de job
  - **DoR:** Fase 0 fechada.
  - **DoD:** `POST /api/v1/migrations` (db_urls válidas) cria o job **sem erro** de análise de schema; a
    introspeção usa interpolação validada de identificador (padrão `validate_sql_identifier`), não
    placeholder `$1` em contexto inválido. Corrigidos outros bugs do serviço expostos no start/batch.
  - **Evidência:** `sub-specs/fase1-evidence.md`.
  - [ ] 2.1 Testes (serviço, TDD): análise de schema de um legacy real devolve as 4 tabelas sem erro;
    caso de identificador inválido continua rejeitado (sem SQL injection)
  - [ ] 2.2 Corrigir a introspeção/mapeamento de schema no `data-migration`
  - [ ] 2.3 Gate: `POST /migrations` cria job + `GET /migrations/{id}` coerente (verde, mockando DB ou com fixture)

### Fase 2 — Activities thin-wrappers (job_id do serviço como chave única)

- [ ] 3. `analyze`/`batch` reais via serviço; criação e propagação do job_id; db_urls no contrato
  - **DoR:** Fase 1 fechada.
  - **DoD:** uma activity inicial cria o job (`POST /migrations`) e devolve o `job_id` REAL; o
    `DataMigrationWorkflow` usa-o em todas as fases; `run_batch_migration` aciona `POST
    /migrations/{id}/start` + poll (remove o `# Simular 100%`); `validate_data` opera sobre o mesmo
    job_id. `_extract_migration_config` + harness passam a carregar `legacy_db_url`/`modern_db_url`
    (fail-closed). Sem simulação local.
  - **Evidência:** `sub-specs/fase2-evidence.md`.
  - [ ] 3.1 Testes (httpx mockado): create_job devolve job_id; batch faz start+poll até terminal;
    fail-closed em erro; job_id propagado; db_urls obrigatórias
  - [ ] 3.2 Implementar as thin-wrappers + propagação do job_id + contrato db_urls
  - [ ] 3.3 Gate: bloco verde; zero regressão nos testes congelados do gate (journey/generate/migrate routing)

### Fase 3 — Gate E2E negativo (anti-verde-falso real em cluster)

- [ ] 4. Destino vazio / divergência → FAILED com rollback (observado em cluster)
  - **DoR:** Fase 2 fechada.
  - **DoD:** intenção J4 com batch que não escreve (ou divergência forçada) → `/validate` real reporta
    `overall_passed=False` → `DataMigrationWorkflow` faz rollback → resultado `FAILED`. **Observado em
    cluster** (logs/Temporal), não só em bloco. Nenhum verde-falso.
  - **Evidência:** `sub-specs/fase3-evidence.md`.
  - [ ] 4.1 Gate cluster negativo: divergência origem≠destino → FAILED + rollback observável
  - [ ] 4.2 Confirmar que o caminho não reivindica `completed` em nenhuma variante de falha

### Fase 4 — Gate E2E positivo (migração real)

- [ ] 5. Intenção J4 migra dados reais: rows_migrated == N + /validate OK
  - **DoR:** Fase 3 fechada.
  - **DoD:** intenção `J4_MIGRATE` (origem 24 linhas, destino vazio) → migração real → destino com 24
    linhas (`rows_migrated == 24`) + `/validate` OK → `completed`, **em cluster**. Zero regressão J2/J3.
    Restaurar os requests do orchestrator (dívida de infra do gate).
  - **Evidência:** `sub-specs/fase4-evidence.md` (contagens reais origem==destino, /validate OK, journey).
  - [ ] 5.1 Gate cluster positivo: `rows_migrated == 24` + `/validate` OK + `completed`
  - [ ] 5.2 Confirmar ausência de regressão em J2/J3 e restaurar requests do orchestrator
