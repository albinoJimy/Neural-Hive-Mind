# Fase 1 — Evidência (Adapter EXECUTE)

> Spec: 2026-06-22-fundacao-loop-learn · Task 2 · Branch `feat/fundacao-loop-learn`
> Data: 2026-06-22 · Princípio: a capacidade liga-se à Fundação (não o inverso)

## Resumo

O `ExecutionResultConsumer` (capacidade EXECUTE) passou a ser um **adapter fino**:
traduz o `ExecutionResult` (formato do worker) para o contrato canónico
`ExecutionFeedback` e delega ao `FeedbackSink` (plano-Z). **Sem lógica de Mongo no
consumer.** A persistência é desacoplada do signal Temporal.

## Ciclo TDD

1. **RED** — `tests/unit/test_execution_result_consumer_feedback.py` (6 testes) →
   `TypeError: __init__() got an unexpected keyword argument 'feedback_sink'` (razão certa).
2. **GREEN** — adicionado `feedback_sink` ao construtor + `_emit_feedback()` + chamada em
   `_process_result` (após signal, antes do commit) + DI no `main.py` → `6 passed`.

```
tests/unit/test_execution_result_consumer_feedback.py ......   6 passed
+ test_feedback_sink.py (Fase 0) ..........                   10 passed
TOTAL                                                          16 passed
```

## Alterações

| Ficheiro | Mudança |
|---|---|
| `src/consumers/execution_result_consumer.py` | construtor `feedback_sink=None` (kwarg opcional — não quebra assinatura existente); `_emit_feedback()` adapter; chamada em `_process_result` |
| `src/main.py` | instancia `FeedbackSink(app_state.mongodb_client, metrics=...)` com guarda e injeta no consumer |
| `tests/unit/test_execution_result_consumer_feedback.py` | 6 testes novos (ficheiro novo — não toca o teste-contrato) |

## Garantias provadas por teste

| Garantia | Teste |
|---|---|
| Tradução EXECUTE→contrato | `test_translates_result_to_execution_feedback` (`capability="EXECUTE"`, campos mapeados) |
| Anti-verde-falso na origem | `test_maps_simulated_from_result_metadata` (lê `result.metadata.simulated`; ver audit-remediation-evidence.md) |
| Tipo millis com fallback | `test_completed_at_falls_back_to_now_millis` |
| DI opcional | `test_no_sink_is_noop` (sink ausente não rebenta) |
| Integração loop+signal | `test_process_result_emits_feedback_and_signals` |
| **Desacoplamento** | `test_feedback_failure_does_not_block_signal_or_commit` (sink rebenta → signal+commit continuam) |

## Incidente de tooling resolvido (honestidade)

`ruff --fix` aplicou `UP017` (`timezone.utc`→`UTC`) — incompatível com **Python 3.10.12**
do ambiente (`datetime.UTC` é 3.11+). Partiu o import do consumer e o shim
`UTC = timezone.utc` do `main.py` (transformado em `UTC = UTC`). Revertido manualmente
para `timezone.utc` em 4 pontos; confirmado `ast.parse` OK e testes verdes.
**Lição:** não correr `ruff --fix` sem `target-version = py310` nestes serviços.

## Não-regressão

- Os 4 warnings `TRY300`/`G201` do consumer são **pré-existentes** (confirmado no
  `git show HEAD:` original) — não introduzidos pela Fase 1.
- `test_execution_result_consumer.py` mantém **os mesmos 5 vermelhos pré-existentes**
  (`MagicMock can't be used in 'await'`): o `_emit_feedback` é noop quando
  `feedback_sink=None` (caso desses testes), logo não altera o seu resultado. Regra 7
  respeitada (teste-contrato não tocado).

## Gate E2E — PENDENTE de cluster

O gate E2E A→C6 (8/8 COMPLETED + `actual_duration_ms>0` + `completed_at` epoch millis no
plano de teste) **requer o cluster** e o script E2E não corre via harness (exit 144, ver
MEMORY). O comportamento crítico de desacoplamento está provado por teste de integração.
A executar no cluster antes de fechar a Task 2.

## Gate Fase 1 (código) — VERDE

- [x] consumer = adapter fino (sem Mongo); tradução para contrato canónico
- [x] persistência desacoplada do signal (provado: falha não bloqueia)
- [x] DI no `main.py` com guarda
- [x] 16/16 testes verdes; black limpo; sem `UTC` incompatível
- [ ] gate E2E A→C6 no cluster (pendente)
