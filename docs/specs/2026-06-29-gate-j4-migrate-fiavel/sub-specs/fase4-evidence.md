# Fase 4 — Evidência (gate E2E em cluster, caminho negativo / anti-verde-falso)

> Task 5 do gate "J4/MIGRATE fiável". Âmbito escolhido: **caminho negativo / anti-verde-falso primeiro**
> (provar que uma migração J4 com batch ainda-simulado + validação real → FAILED, sem verde-falso).
> Data: 2026-06-29. Conduzido manualmente (integração em cluster, não pipeline de agentes).

## Resultado: PARCIAL — Fases 1-3 PROVADAS em runtime; migração real bloqueada por 4 bugs de integração

A Fase 4 cumpriu o propósito de um **gate de fiabilidade**: descobriu que o caminho de migração **real**
NÃO está pronto, com a lista precisa de bugs — e confirmou que o sistema é **anti-verde-falso** (falha
honestamente em cada ponto, nunca finge sucesso).

## 1. PROVADO em runtime no cluster (Fases 1 + 3)

Deploy: imagem `orchestrator-dynamic:bdce0f3` (revision `bdce0f34`, Fases 1-3) construída via
workflow_dispatch e deployada em `neural-hive` (2 réplicas Ready, após reduzir requests por over-commit).
DBs fixture deployados: `j4-postgres-legacy` (seedado, **24 linhas**: users=5, orders=5, products=5,
order_items=9) + `j4-postgres-modern` (4 tabelas vazias).

Injetada intenção `J4_MIGRATE` (plan direto, `context.source=doc-ingestion`, `migration_config` com
`tables`, **sem** `generate_target`) no topic `plans.consensus`. Logs reais (plan `gatej4neg-1782765536`):

```
Plan direto do STE detectado (sem decision_id) plan_id=gatej4neg-1782765536
Invocando capacidade MIGRATE  journey=J4_MIGRATE routing_basis=journey tables=['users','orders','products','order_items'] workflow_id=orch-gatej4neg-1782765536
MigrateJourneyWorkflow iniciado  journey=J4_MIGRATE plan_id=gatej4neg-1782765536
→ child DataMigrationWorkflow  id=orch-gatej4neg-1782765536-migrate (run 019f151b...)
```

Confirma, em cluster real:
- **Fase 1**: routing `J4_MIGRATE` → capacidade MIGRATE (`routing_basis=journey`), **não** a OrchestrationWorkflow genérica.
- **Fase 3**: o `MigrateJourneyWorkflow` arranca o child `DataMigrationWorkflow` com o ID `{wid}-migrate`;
  sem `generate_target` **saltou GENERATE** (condicionalidade correta).

## 2. Bugs de integração descobertos (em camadas nunca exercitadas E2E)

O caminho de migração real está bloqueado por 4 bugs reais — todos pré-existentes, expostos pela
primeira execução E2E:

1. **`DataMigrationWorkflow` viola determinismo Temporal** — `Cannot access os.environ.get from inside a
   workflow`. **Latente precisamente porque o workflow era órfão** (nunca executado); des-orfanizá-lo
   (Fases 1+3) expô-lo. **CORRIGIDO (2026-06-29):** as 8 activities eram importadas *inline dentro dos
   métodos* (fora do sandbox passthrough), ao contrário do `FluxoGWorkflow`/`OrchestrationWorkflow` que
   as importam no topo sob `with workflow.unsafe.imports_passed_through()`. Movidas para o bloco
   passthrough do topo (padrão idêntico aos outros workflows); imports inline removidos. Import OK,
   activities no escopo, 20 testes de workflow verdes (zero regressão), worker importa OK. **Pendente:
   validação em runtime** (rebuild+deploy+re-injetar) — alta confiança por seguir o padrão que funciona,
   mas não re-exercitado em cluster nesta sessão (junto de #2).
2. **`data-migration` service — análise de schema**: `POST /api/v1/migrations` falha com
   `syntax error at or near "$1"` (query de introspeção mal-parametrizada). Impede criar o job de migração.
3. **`scripts/init-legacy-db.sql`**: começa com comentários estilo shell (`#`, inválidos em SQL) +
   `CREATE EXTENSION "pgoutput"` (não instalável) → o initdb falha. **Corrigido localmente** para seedar
   o fixture (`#`→`--`, remover pgoutput); o ficheiro do repo continua com o bug (nunca correu num postgres real).
4. **Cluster over-commit de requests** (infra, [[infra_memory_overcommit_istiod]]): o pod do orchestrator
   novo (640Mi requests) não agenda; reduzi requests temporariamente (512→256Mi) para o teste — **a
   restaurar**. Não é bug de código.

## 3. Anti-verde-falso: CONFIRMADO (a um nível mais forte)

O princípio central da spec — o sistema **não dá verde-falso** numa migração que não migrou — está
confirmado: em cada um dos 4 pontos, o sistema **falhou honestamente** (erro explícito), nunca reportou
sucesso. O `DataMigrationWorkflow` rebenta no determinismo em vez de fingir `completed`.

**Ressalva honesta:** a prova **limpa** que o âmbito visava — job criado → batch simulado → `/validate`
real deteta `destino(0) ≠ origem(24)` → `FAILED` — **NÃO foi alcançada end-to-end**, porque a cadeia
rebenta ANTES de chegar ao `/validate` (no determinismo do `DataMigrationWorkflow`, bug #1). O gate
`/validate` fail-closed em si está provado em bloco (Fase 2, mutação); a sua execução real no cluster
fica para depois de #1 e #2 corrigidos.

## 4. Conclusão e dívida

- **Fases 1 e 3 estão provadas em runtime** (routing + composição child-workflow). A Fase 2 (gate
  `/validate` fail-closed) está provada em bloco; falta a sua execução em cluster (bloqueada por #1/#2).
- O gate revelou que **tornar a migração real funcional é uma empreitada separada** (corrigir #1 no
  orchestrator + #2/#3 no data-migration service), fora do escopo declarado desta spec (que é o
  orchestrator **compor** a jornada). Recomenda-se uma spec própria "migração J4 real" para os bugs #1-#3.
- Artefactos de teste no cluster (DBs fixture, requests reduzidos) a limpar/restaurar.
