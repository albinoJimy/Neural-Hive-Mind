# Auditoria (qualidade + completude) e remediação dirigida (2026-06-22)

> Spec: 2026-06-22-fundacao-loop-learn · Branch `feat/convergencia-dbs`
> Pipeline: auditoria qualidade → auditoria completude → remediação dirigida → commit → push.

## Achados das auditorias

Duas auditorias independentes (subagentes) sobre o código e a spec do loop. Achados
acionáveis e a respetiva remediação:

| ID | Severidade | Achado | Remediação |
|---|---|---|---|
| **C1-compl** | CRÍTICO | `simulated` vive em `result["metadata"]` (campo `result` do payload), mas o adapter lia `result_data.get("metadata")` (topo) → **sempre False** → anti-verde-falso morto no caminho real. O teste mascarava (injetava metadata no topo). | Adapter lê `result_data["result"]["metadata"]["simulated"]`; teste `_result()` usa payload real; +`test_top_level_metadata_is_not_the_source`. |
| **C2-compl** | ALTO | `started_at`/`completed_at`/`trace_id`/`journey_id` **não existem** no payload do worker (só `timestamp` millis + `actual_duration_ms`). Sink gravava `None`/`now_ms`. | `completed_at` deriva do `timestamp` do worker; `started_at = completed_at - actual_duration_ms`; `trace_id` cai em `correlation_id`. |
| **A1-qual** | ALTO | `_send_workflow_signal` lança → `_emit_feedback` (a seguir) nunca corria → feedback perdido se o workflow não existir/expirar. | `_emit_feedback` movido para **antes** do signal (continua protegido; não bloqueia). |
| **C1-qual** | CRÍTICO | `completed_at or now_ms` trata `0` como falsy. | Substituído por `is None` + derivação do `timestamp`. |
| **C2-qual** | ALTO/MÉD | `_ms_to_datetime` gravava `1970`/rebentava para `0`, negativos ou overflow. | Guarda `ms <= 0 → None` + `try/except (OSError, OverflowError, ValueError)`. |
| **A2-qual** | MÉDIO | `update_one(upsert=False)` com `matched=0` silencioso (race: worker publica antes do ticket existir). | Log `feedback_sink_ticket_not_found` quando `matched_count == 0`. |
| **M1–M6, B1** | MÉD/BAIXO | Documentação ainda afirmava "epoch millis" (contradizia a correção Date); nomes de teste órfãos. | spec.md (Gherkin+deliverable), fase0/1/2-evidence, fase3 snippet mongosh, technical-spec, tasks.md atualizados; testes renomeados. |

## Testes (22/22 verdes)

```
test_feedback_sink.py ..........                     10
test_execution_result_consumer_feedback.py .......    7  (+2: result.metadata + guarda topo)
test_duration_predictor_feedback_query.py ..          2
test_loop_learn_contract_guard.py ...                 3
TOTAL                                                22 passed
```

Novos testes-guarda de C1: `test_maps_simulated_from_result_metadata` (lê do sítio certo)
e `test_top_level_metadata_is_not_the_source` (metadata no topo não conta).

## Impacto

Sem esta remediação, o **valor #1 da spec** (excluir verde-falso do treino) estava morto no
caminho real (`simulated` sempre False), e o sink gravava timestamps incompletos. Após a
remediação, o adapter lê o payload real do worker corretamente e o anti-verde-falso funciona.

## Continua pendente de cluster

Deploy do orchestrator + E2E A→C6 para confirmar, com tickets **novos**, que o sink grava
`completed_at` BSON Date e `result_simulated` corretamente preenchido a partir de
`result.metadata`. Sem deploy, o cluster corre a versão antiga.
