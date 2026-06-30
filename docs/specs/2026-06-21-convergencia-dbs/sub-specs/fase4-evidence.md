# Evidência de execução — Fase 4 (Task 7: janela de corte)

> Spec: convergencia-dbs — Fase 4 (eliminar escrita dupla). Contexto: `neural-hive-prod`.

## DoD — checklist com evidência

| Item | Estado | Evidência |
|---|---|---|
| `neural_hive` sem escritas novas (contagem estável) | ✅ | corpus congelado no baseline da Task 2 após 2 workloads E2E reais |
| E2E verde pós-corte | ✅ | Tasks 4 e 5 (planos `ed799f2b`, `cde2180d`) fecharam em `neural_hive_dev` |
| 7.1 Freeze dos escritores do corpus | ✅ (implícito) | escritores já repontados (Fases 1–3); sem escrita dupla a eliminar |
| 7.2 Migração-delta idempotente | ✅ | delta = **0 candidatos** nas 5 coleções (re-run de `10-migrate-corpus`) |
| 7.3 Observar contagem estável | ✅ | `neural_hive` corpus inalterado; `neural_hive_dev` cresceu (escritores lá) |

## Descoberta-chave: nunca houve "escrita dupla"

A spec desenhou a Fase 4 como freeze + delta para eliminar escrita dupla durante uma
transição com dual-write. **A nossa arquitetura nunca fez dual-write:** cada serviço
escreve numa **única** DB, e os repoints (Fases 2–3) moveram essa escrita
**atomicamente** (1 commit declarativo + rollout por serviço). Logo não há período de
dual-write a reconciliar — o corte fica conseguido pelos próprios repoints.

## Prova 1 — `neural_hive` corpus congelado no baseline (sob workload real)

Entre a migração da Task 2 e agora correram **duas** E2E completas (Tasks 4 e 5). As 5
coleções-corpus de `neural_hive` permanecem **exatamente no baseline da Task 2**:

| Coleção | baseline Task 2 | agora | Δ |
|---|---|---|---|
| `plan_approvals` | 486 | 486 | **0** |
| `specialist_feedback` | 2482 | 2482 | **0** |
| `specialist_opinions` | 8291 | 8291 | **0** |
| `plan_features` | 648 | 648 | **0** |
| `explainability_ledger` | 18626 | 18626 | **0** |

Zero escritas novas em `neural_hive` apesar de workload E2E real — prova mais forte que
uma observação ociosa por tempo.

## Prova 2 — `neural_hive_dev` é a DB viva (cresceu com os planos novos)

As mesmas coleções em `neural_hive_dev` cresceram com os 2 planos frescos das Tasks 4–5:

| Coleção | pós-Task 2 | agora | Δ |
|---|---|---|---|
| `plan_approvals` | 486 | 488 | +2 |
| `specialist_feedback` | 2482 | 2490 | +8 |
| `specialist_opinions` | 8483 | 8491 | +8 |
| `plan_features` | 677 | 679 | +2 |
| `explainability_ledger` | 18919 | 18929 | +10 |

O sinal vai todo para `neural_hive_dev`; nenhum para `neural_hive`.

## Prova 3 — migração-delta idempotente: delta vazio

Re-execução de `scripts/db-convergence/10-migrate-corpus.sh` (dry-run) reporta
`candidates=0` nas 5 coleções (`MIGRATION_VERDICT=OK`) — não há docs novos em
`neural_hive` para copiar. O script idempotente é o tratador-de-delta: como nada foi
escrito em `neural_hive` desde a Fase 1, o delta é nulo. (Re-correr com `APPLY=true`
seria um no-op: 0 inserções.)

## Sobre marcar `neural_hive` read-only (7.1, alternativa)

**Não aplicado nesta fase.** Marcar a DB inteira read-only é o passo de **arquivo da
Fase 5** ("arquivar `neural_hive` read-only após janela de verde"), feito após N dias de
E2E verde. Fazê-lo agora seria prematuro e arriscado: `neural_hive` ainda contém
coleções **não-corpus** (ex.: `authorization_audit`, `data_quality_metrics`) que podem
ser usadas por serviços fora do âmbito desta spec. O corte do corpus está conseguido
(escritores repontados, delta nulo); o arquivo formal é da Fase 5.

## Resultado da Fase 4

A janela de corte está efetivamente fechada: `neural_hive` corpus congelado (0 escritas
sob workload real), `neural_hive_dev` é a DB viva, delta nulo, E2E verde. Não foi
necessário freeze nem read-only porque os repoints atómicos das Fases 2–3 eliminaram a
escrita no corpus de `neural_hive` sem período de dual-write. `neural_hive` permanece
intacta como fallback vivo até ao arquivo da Fase 5.
