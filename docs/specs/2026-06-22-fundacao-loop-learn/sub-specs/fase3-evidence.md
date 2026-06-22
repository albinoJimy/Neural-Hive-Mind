# Fase 3 — Evidência (Anti-regressão e prova de transversalidade)

> Spec: 2026-06-22-fundacao-loop-learn · Task 4 · Branch `feat/fundacao-loop-learn`
> Data: 2026-06-22

## Resumo

Fechadas as guardas anti-regressão do loop OBSERVE→LEARN, **todas como testes unit que
correm no CI**. Destaque: uma guarda nova de **contrato cruzado** sink↔predictor, provada
a detetar regressões reais.

## Guardas no CI (21/21 verdes)

| Guarda | Ficheiro | Protege contra |
|---|---|---|
| Contrato do sink (transversal, idempotente, desacoplado) | `test_feedback_sink.py` (10) | quebra da Fundação |
| **Transversalidade** (`capability="GENERATE"` sem alterar o sink) | `test_feedback_sink.py::test_transversal_accepts_generate_without_change` | acoplar o loop a uma capacidade |
| Adapter EXECUTE (tradução + desacoplamento) | `test_execution_result_consumer_feedback.py` (6) | consumer voltar a descartar a duração |
| Contrato de tipo + exclusão de simulados | `test_duration_predictor_feedback_query.py` (2) | regressão `datetime` / treinar verde-falso |
| **Contrato cruzado sink↔predictor** | `test_loop_learn_contract_guard.py` (3) | renomeação que cega o loop silenciosamente |

```
test_feedback_sink.py ..........                    10
test_execution_result_consumer_feedback.py ......    6
test_duration_predictor_feedback_query.py ..         2
test_loop_learn_contract_guard.py ...                3
TOTAL                                               21 passed
```

## Prova de que a guarda de contrato cruzado FUNCIONA

A guarda não passa por acaso — provou-se a detetar uma regressão real:

```
# renomear no predictor: result_simulated → result_simulated_RENAMED
sed -i 's/"result_simulated": {"$ne": True}/"result_simulated_RENAMED": .../' duration_predictor.py
pytest test_loop_learn_contract_guard.py::test_sink_writes_every_field_predictor_reads
→ FAILED   (guarda apanhou a divergência de contrato)
# restaurado → 3 passed
```

Isto cobre o cenário mais perigoso: uma futura alteração que renomeie um campo num só
lado quebraria o loop **sem erro visível** (o predictor voltaria a ficar cego). A guarda
falha o CI nesse caso.

## 4.1 — Assert E2E de loop-fechado (pendente de cluster)

O script `scripts/test-e2e-pipeline-completo.sh` está **git-ignored** (confirmado por
`git check-ignore`), logo não é versionável. A validação de loop-fechado com dados reais
corre no cluster com:

```javascript
// após um E2E A→C6, na DB neural_hive_dev:
db.execution_tickets.countDocuments({ actual_duration_ms: { $gt: 0 }, result_simulated: { $ne: true } })
// esperado: > baseline (hoje 3/1247) — prova de que o loop está a persistir duração real

// tipo correto (epoch millis, não Date):
typeof db.execution_tickets.findOne({ actual_duration_ms: { $gt: 0 } }).completed_at  // "number"
```

E confirmar nos logs do orchestrator que `_check_training_data_availability` deixa de
emitir `insufficient_training_data`.

## Estado final e ganchos prontos (Fundação → Roteamento → Capacidades)

A Fundação ficou costurada e transversal, com os encaixes dos passos seguintes prontos:

| Passo (ADR-0011) | Estado | Encaixe deixado pronto |
|---|---|---|
| **Fundação** (esta spec) | ✅ contrato + sink + adapter EXECUTE + leitor alinhado | — |
| **Roteamento** (passo 2) | ⬜ futuro | campo `journey_id` no contrato (hoje opcional) — o router só passa a preenchê-lo |
| **Capacidades** (passo 3) | ⬜ futuro | campo `capability` + padrão adapter — GENERATE/MIGRATE = novo adapter para o mesmo sink |

## Gate Fase 3 — VERDE (CI)

- [x] guarda de tipo (anti-`datetime`) no CI
- [x] guarda de transversalidade no CI (âncora do princípio)
- [x] guarda de contrato cruzado sink↔predictor (provada a detetar regressão)
- [x] 21/21 testes do loop verdes; ruff limpo
- [ ] assert E2E de loop-fechado com dados reais — documentado, pendente de cluster
