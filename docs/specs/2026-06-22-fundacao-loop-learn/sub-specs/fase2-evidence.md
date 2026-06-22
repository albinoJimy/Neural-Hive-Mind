# Fase 2 — Evidência (Leitor LEARN)

> ⚠️ **CORRIGIDO pós-gate de cluster.** Este ficheiro descreve a abordagem original
> (filtro em epoch millis), que o gate de cluster provou ser uma **regressão**:
> `completed_at` é BSON `Date`, não int millis. A correção (predictor em `datetime`,
> sink converte millis→Date) está em [`cluster-gate-evidence.md`](./cluster-gate-evidence.md).
> Nomes de teste reais: `test_uses_datetime_and_excludes_simulated`,
> `test_train_uses_datetime_and_excludes_simulated`.

> Spec: 2026-06-22-fundacao-loop-learn · Task 3 · Branch `feat/fundacao-loop-learn`
> Data: 2026-06-22

## Resumo

Corrigido o **segundo bug** do loop (contrato de tipo) e adicionada a **exclusão de
verde-falso** no `duration_predictor` — os dois pontos onde o LEARN lê o corpus.

## Os dois bugs fechados

1. **Tipo incompatível.** `completed_at` é persistido em epoch millis (int), mas o
   predictor filtrava `{"$gte": <datetime>}`. `$gte` entre `int` e `Date` (tipos BSON
   distintos) nunca casa → predictor cego mesmo com dados presentes. Corrigido para
   `cutoff_ms` (epoch millis) nos 2 sítios.
2. **Verde-falso treina o modelo.** Adicionado `result_simulated: {"$ne": True}` às
   queries de contagem e de treino → execuções simuladas ficam observáveis mas não
   envenenam o modelo.

## Ciclo TDD

1. **RED** — `tests/unit/test_duration_predictor_feedback_query.py` (2 testes) →
   `assert isinstance(flt["completed_at"]["$gte"], int)` falha com
   `datetime.datetime(...)` (razão certa: filtro ainda em datetime).
2. **GREEN** — `cutoff_ms` + `result_simulated` nos 2 sítios → `2 passed`.

```
tests/unit/test_duration_predictor_feedback_query.py ..    2 passed
+ Fase 1 (6) + Fase 0 (10)                                18 passed total
```

## Alterações (diff mínimo: 20 inserções, 5 deleções)

| Sítio | Método | Mudança |
|---|---|---|
| `_check_training_data_availability` | `count_documents` | `cutoff_ms` + `result_simulated: {"$ne": True}` |
| `train_model` | `find` (fallback Mongo) | `cutoff_ms` + `result_simulated: {"$ne": True}` |

## Garantias provadas por teste (contrato de query)

| Garantia | Teste |
|---|---|
| Filtro em epoch millis (bug 1) | `test_uses_epoch_millis_and_excludes_simulated` (`isinstance($gte, int)`) |
| Exclusão de simulados (bug 2) | ambos (`result_simulated == {"$ne": True}`) |
| Idem no caminho de treino | `test_train_uses_epoch_millis_and_excludes_simulated` (early-return sem dados) |

## Incidente de tooling (repetido, resolvido)

`black src/ml/duration_predictor.py` voltou a reformatar ~90 linhas de código alheio
(diff 87/28). Revertido ao HEAD e reaplicadas só as 3 mudanças manualmente (diff 20/5).
Nota pré-existente: o original já tinha `UTC = timezone.utc` duplicado (linhas 17/19) —
**não tocado** (não é desta spec).

## Não-regressão

`test_ml_prediction_integration.py` tem **6 falhas pré-existentes**
(`Mock object has no attribute 'enable_ml_enhanced_scheduling'` — config mock
desatualizado). **Provado** via `git stash push src/ml/duration_predictor.py`: na base
falham os mesmos 6. A mudança da Fase 2 (filtro de query) não as afeta.

## Gate Fase 2 (código) — VERDE

- [x] filtro em epoch millis nos 2 sítios (fecha o bug de tipo)
- [x] `result_simulated` excluído do treino (anti-verde-falso)
- [x] 18/18 testes verdes; diff mínimo; sem `cutoff_date` órfão
- [ ] prova com dados reais (`count` sobe; `insufficient_training_data` desaparece) — pendente de cluster, junto com o gate E2E da Fase 1
