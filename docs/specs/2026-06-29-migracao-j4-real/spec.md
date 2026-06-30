# Spec Requirements Document

> Spec: Migração J4 real funcional (activities thin-wrappers sobre o serviço; full-stack)
> Created: 2026-06-29
> Status: Planning

## Overview

Tornar a **migração de dados J4 real e funcional** ponta-a-ponta: uma intenção `J4_MIGRATE` migra dados
PostgreSQL (legacy → moderno) **de facto**, com `rows_migrated == N` validado por contagem real. É a
continuação do gate **"J4/MIGRATE fiável"** (`docs/specs/2026-06-29-gate-j4-migrate-fiavel`), cuja Fase 4
provou que a composição da jornada funciona em runtime (routing J4 → `MigrateJourneyWorkflow` → child
`DataMigrationWorkflow`), mas que a migração **real** está bloqueada por bugs de integração em camadas
nunca exercitadas E2E.

**Arquitetura escolhida:** as activities de migração do orchestrator passam a ser **thin-wrappers HTTP
sobre o serviço `data-migration`** (a fonte de verdade da migração — tem `batch_migrator`, `data_validator`
reais). A 1ª activity cria o job via `POST /api/v1/migrations` (com db_urls), obtém o **job_id real do
serviço**, e propaga-o por todas as activities (analyze → batch → validate), resolvendo a desconexão
job_id orchestrator↔serviço. Espelha o padrão já aplicado a `validate_data` na Fase 2 do gate.

**Escopo full-stack:** corrige o que for preciso no **orchestrator** (wiring, job_id, db_urls) **e no
serviço `data-migration`** (bug da análise de schema e outros expostos pelo primeiro fluxo real).

## User Stories

### MJR-US1 · Intenção J4 migra dados reais

```gherkin
Funcionalidade: Migração de dados real legacy→moderno

  Cenário: Migrar 4 tabelas de um PostgreSQL legacy para um moderno vazio
    Dada uma intenção J4_MIGRATE com origem (24 linhas conhecidas) e destino vazio
    Quando a jornada composta executa a migração
    Então as linhas são migradas de facto para o destino (rows_migrated == 24)
    E a validação por contagem real confirma origem == destino
    E o resultado é completed (não simulado)
```

### MJR-US2 · Activities são thin-wrappers sobre o serviço (job_id resolvido)

```gherkin
Funcionalidade: Orchestrator orquestra, serviço migra (fonte de verdade)

  Cenário: O job é criado no serviço e propagado pelas activities
    Dada a 1ª activity da migração
    Quando ela cria o job via POST /api/v1/migrations (db_urls do migration_config)
    Então obtém o job_id REAL do serviço
    E analyze/batch/validate operam todas sobre esse job_id (sem simulação local)
    E não há desconexão entre o job_id do orchestrator e o do serviço
```

### MJR-US3 · Caminho negativo e positivo provados E2E

```gherkin
Funcionalidade: Anti-verde-falso real (não só em bloco)

  Cenário: Destino que não recebeu dados falha a validação
    Dada uma migração cujo batch não escreveu no destino (ou divergência forçada)
    Quando a validação real corre (COUNT origem vs destino)
    Então o resultado é FAILED (destino 0 ≠ origem 24), com rollback
    E NÃO se reivindica sucesso

  Cenário: Migração íntegra passa
    Dada uma migração que escreveu todas as linhas
    Quando a validação real corre
    Então origem == destino e o resultado é completed
```

### MJR-US4 · Bugs de integração resolvidos

```gherkin
Funcionalidade: Caminho real desbloqueado

  Cenário: O serviço cria o job sem rebentar na análise de schema
    Dado um POST /api/v1/migrations com db_urls válidas
    Quando o serviço analisa o schema legado
    Então não há "syntax error at or near $1" (introspeção corrigida)
    E o job é criado com sucesso
```

## Spec Scope

1. **Activities thin-wrappers sobre o serviço** — refatorar as activities de migração do orchestrator
   (`analyze`, `batch` e a já-feita `validate`) para chamadas HTTP reais ao `data-migration:8019`; uma
   activity inicial cria o job (`POST /migrations`) e o `job_id` real é propagado por todas. Sem
   simulação local (remove os `# Simular 100%` / hardcodes).
2. **Resolver job_id + db_urls** — o `migration_config` do plano J4 passa a carregar/derivar
   `legacy_db_url`/`modern_db_url`; a fronteira (consumer/`MigrateJourneyWorkflow`) propaga-as; o job_id
   do serviço torna-se a chave única da migração.
3. **Corrigir o serviço `data-migration`** — bug #2 da análise de schema (`syntax error at or near "$1"`,
   introspeção mal-parametrizada) e quaisquer outros bugs expostos pelo primeiro fluxo real.
4. **Corrigir `scripts/init-legacy-db.sql`** (#3) — comentários `#` inválidos → `--`; remover/ajustar
   `CREATE EXTENSION "pgoutput"` — para o seed correr num PostgreSQL real.
5. **Validar #1 (determinismo) em runtime** — confirmar em cluster que o `DataMigrationWorkflow`
   (corrigido no commit `375129e6`) corre sem o erro `os.environ.get`.
6. **Gates E2E** — caminho **negativo** (destino vazio/divergência → FAILED) **e positivo** (migração
   real, `rows_migrated == N`, `/validate` OK) provados em cluster.

## Out of Scope

- **GENERATE em J4** (a composição GENERATE→MIGRATE já está provada em bloco na spec do gate; aqui o foco
  é a **migração de dados pura**, sem geração de código — `generate_target` ausente).
- **Cutover canary** (`CutoverWorkflow` shadow→canary→100%) — fica para spec própria.
- **CDC contínuo** (Debezium) além do necessário para o batch + validação.
- **Fontes não-PostgreSQL** (MongoDB, ficheiros).
- **Over-commit do cluster** (#4, infra) — mitiga-se com requests reduzidos para o teste; a resolução
  estrutural é separada.

## Expected Deliverable

1. Uma intenção `J4_MIGRATE` migra dados reais de um PostgreSQL legacy (N linhas) para um moderno vazio,
   com `rows_migrated == N` e `/validate` OK, **em cluster**.
2. **Caminho negativo E2E real**: destino vazio/divergência → `FAILED` com rollback (anti-verde-falso já
   não só em bloco, mas observado em cluster).
3. Activities de migração são **thin-wrappers** sobre o serviço (sem simulação); o `job_id` do serviço é
   a chave única — desconexão resolvida.
4. Bugs **#1** (validado runtime), **#2** (análise de schema) e **#3** (seed) resolvidos.
