# Spec Tasks

> Gate "J4/MIGRATE fiável" (ADR-0011, eixo Jornadas) — provar E2E a jornada de migração de legado
> composta (`INGEST → PLAN → GENERATE → EXECUTE → MIGRATE`) antes de extrair MIGRATE como capacidade.
>
> **Princípios:** compor capacidades/serviços existentes (não novos serviços); reusar
> `GenerateCapability` e des-orfanizar `DataMigrationWorkflow`; anti-verde-falso (validação reprovada /
> perda de dados / `/validate` indisponível → FAILED); TDD estrito; diffs mínimos (py3.10); zero
> regressão em J2. Cada fase é um gate: só avança com testes verdes. Detalhe em
> `sub-specs/technical-spec.md`.

## Tasks

### Fase 0 — Diagnóstico + harness de prova reprodutível

- [x] 1. Estabelecer o baseline do gap e o fixture de migração
  - **DoD:** baseline documentado (J4 cai na `OrchestrationWorkflow` genérica; `DataMigrationWorkflow`
    órfão — confirmado pela sonda 2026-06-29); fixture de migração reprodutível: PostgreSQL **legacy**
    com N linhas conhecidas em ≥1 tabela + PostgreSQL **moderno** vazio, em namespace efémero
    (TTL/ResourceQuota, reuso do padrão do gate J3); harness de injeção de intenção J4 (plan direto no
    topic `plans.consensus`, produtor in-pod), idêntico ao gate 3.3. **FEITO** — pipeline
    dev(TDD)→auditoria(qualidade SHIP + completude SHIP)→remediação. **31 testes verdes** (18 novos +
    13 congelados, zero regressão). Descobertas do scouting: o fixture **legacy já existia**
    (`postgres-legacy` + `scripts/init-legacy-db.sql`, 4 tabelas) e o baseline routing **já estava
    testado** (`test_decision_consumer_journey_routing.py:74`) — não duplicado. Adicionado o que faltava:
    DB **destino** (`postgres-modern` no compose + `scripts/init-modern-db.sql`, DDL sem INSERTs),
    **oráculo de contagens** determinístico (`{users:5, orders:5, products:5, order_items:9}` + parser
    anti-drift) e **harness** J4 (função pura + produção Kafka separada/opcional, round-trip pelo
    deserializer real). NOTA honesta: a Fase 0 só **define e testa em bloco** — a execução real do
    fixture (docker-compose, migração, `rows_migrated==N`, `/validate`) é Fase 4.
  - **Evidência:** `sub-specs/fase0-evidence.md`.
  - [x] 1.1 Testes: harness constrói/injeta J4 e o baseline (J4→OrchestrationWorkflow real) é observado;
    oráculo expõe N linhas conhecidas (contagem determinística da origem) — 18 testes
  - [x] 1.2 Implementar fixture (DB **destino** `postgres-modern` + `init-modern-db.sql`; legacy já
    existia) + harness de injeção (`tests/integration/j4_migrate_fixture.py`)
  - [x] 1.3 Documentar baseline (`sub-specs/fase0-evidence.md`): J4 cai na orquestração genérica e não
    toca migração; `DataMigrationWorkflow` órfão

### Fase 1 — Compor o fluxo J4 (des-vazar routing + des-orfanizar MIGRATE)

- [x] 2. Routing de J4 para o fluxo composto e arranque do `DataMigrationWorkflow`
  - **DoR:** Fase 0 fechada. ✓
  - **DoD:** para `J4_MIGRATE`, o handler deixa de cair na `OrchestrationWorkflow` genérica e aciona o
    fluxo composto que **inicia** o `DataMigrationWorkflow` (deixa de ser órfão), passando o migration
    spec derivado do plano (legacy/modern db urls, tabelas). Autoridade única de routing por journey
    (espelha `_requires_generate_capability`). Preservados: J1 não executa; **J2 → OrchestrationWorkflow
    inalterada (teste congelado verde)**; fallback por `workflow_type`. **FEITO** — pipeline
    dev(TDD)→auditoria(qualidade SHIP + completude SHIP)→remediação (Q1: docstring corrigido p/ não
    afirmar paridade com o resume, que fica para fase posterior). Padrão GENERATE espelhado:
    `_journey_requires_migration` + `_requires_migration` + `_extract_migration_config` (fail-closed) +
    bloco que arranca `DataMigrationWorkflow.run`. **71 testes verdes** (19 novos) + zero regressão
    GENERATE (48). `_select_workflow_class_by_journey` intocado (teste congelado verde). Nuance de
    desenho documentada: J4 **com** `migration_config` → MIGRATE; **inválido** → FAILED; **sem a chave**
    → compat (preserva o teste da Fase 2 do GENERATE). Ver `sub-specs/fase1-evidence.md`.
  - **Evidência:** `sub-specs/fase1-evidence.md`.
  - [x] 2.1 Testes: J4 → arranca `DataMigrationWorkflow` com o spec certo; J2 → `OrchestrationWorkflow`
    (congelado); journey ausente/UNKNOWN → fallback `workflow_type`; + anti-verde-falso (config inválido)
  - [x] 2.2 Implementar o routing por journey + wiring do `DataMigrationWorkflow` (start durável)
  - [x] 2.3 Gate: teste de bloco verde (in→out sem correr cluster) — 71 verdes

### Fase 2 — Gate de validação anti-verde-falso (FAIL-CLOSED)

- [ ] 3. `/validate` como gate fail-closed do resultado da migração
  - **DoR:** Fase 1 fechada.
  - **DoD:** após MIGRATE, a jornada exige `POST /migrations/{id}/validate` com resultado positivo
    explícito (contagem origem == destino + checks). Fail-closed: validação reprovada / divergência de
    contagem / `/validate` indisponível ou erro → resultado `FAILED` com `failure_reason`. Sem fallback
    que assuma sucesso. Espelha `map_result` de GENERATE (exige verificação real).
  - **Evidência:** `sub-specs/fase2-evidence.md`.
  - [ ] 3.1 Testes: validação OK → `completed`; contagem divergente → `FAILED`; `/validate` erro/timeout
    → `FAILED` (fail-closed); rollback acionado em falha
  - [ ] 3.2 Implementar o gate de validação + mapeamento de resultado fail-closed
  - [ ] 3.3 Gate: anti-verde-falso provado por mutação (desligar o gate `/validate` derruba ≥1 teste)

### Fase 3 — Reuso de GENERATE na composição (condicional)

- [ ] 4. Invocar `GenerateCapability` na fase de geração (sem duplicar wiring)
  - **DoR:** Fase 2 fechada.
  - **DoD:** a fase GENERATE invoca `GenerateCapability.start(GenerateRequest(...))` (reuso, não
    reimplementação de G1–G8); o serviço moderno gerado é deployado **antes** da migração de dados;
    GENERATE é **condicional** (planos de migração sem código novo saltam a fase — a journey marca-o).
  - **Evidência:** `sub-specs/fase3-evidence.md`.
  - [ ] 4.1 Testes: fase GENERATE invoca `GenerateCapability.start`; plano sem código novo → salta
    GENERATE; ordem GENERATE → deploy → MIGRATE respeitada
  - [ ] 4.2 Implementar a invocação + a condicionalidade (sem acoplar a jornada à stack)
  - [ ] 4.3 Gate: bloco verde

### Fase 4 — Gate E2E em cluster (software migrado a correr)

- [ ] 5. Paridade E2E: intenção J4 produz sistema migrado real e validado via o fluxo composto
  - **DoR:** Fase 3 fechada.
  - **DoD:** intenção de migração `J4_MIGRATE` → fluxo composto → serviço moderno gerado a correr
    (`/health` 200, quando GENERATE aplicável) + PostgreSQL migrado (`rows_migrated == N`) + `/validate`
    OK no cluster. Falha real em qualquer fase (geração/deploy/migração/validação) → `FAILED` sem verde
    falso. Zero regressão em J2 (teste congelado verde + bloco Orchestration intocado).
  - **Evidência:** `sub-specs/fase4-evidence.md` (plano real, DB migrado, validação 200, journey no
    artefacto).
  - [ ] 5.1 Gate cluster E2E: migração real validada (`rows_migrated == N`, `/validate` OK) + serviço a
    correr
  - [ ] 5.2 Confirmar ausência de regressão em J2 (caminho Orchestration inalterado)
  - [ ] 5.3 Anti-verde-falso E2E: forçar divergência de dados → resultado `FAILED` observável (sem
    verde falso)
