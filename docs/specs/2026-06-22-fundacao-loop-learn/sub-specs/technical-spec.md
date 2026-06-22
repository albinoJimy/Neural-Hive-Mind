# Technical Specification

This is the technical specification para a spec detalhada em @docs/specs/2026-06-22-fundacao-loop-learn/spec.md

## Descoberta-chave (análise de causa-raiz)

O loop LEARN está partido por **dois bugs distintos** na fronteira EXECUTE→OBSERVE, ambos confirmados no código:

1. **O sinal é produzido mas descartado.** O worker calcula a duração (`services/worker-agents/src/engine/execution_engine.py:530`, `actual_duration_ms`) e publica-a no `ExecutionResult` (`services/worker-agents/src/models/execution_result.py:15`). O `ExecutionResultConsumer._process_result` (`services/orchestrator-dynamic/src/consumers/execution_result_consumer.py:120-194`) extrai apenas `ticket_id/plan_id/status`, envia o signal Temporal e **nunca toca no Mongo**. Resultado: `execution_tickets` quase sem `actual_duration_ms` (3/1247 históricos).

2. **Contrato de tipo incompatível.** `ticket_generation.py:256` grava `created_at: int(datetime.now().timestamp() * 1000)` (epoch millis) e `completed_at: None`. O `duration_predictor` (`services/orchestrator-dynamic/src/ml/duration_predictor.py:203` e `:571`) filtra `completed_at: {"$gte": <datetime>}`. No MongoDB, `$gte` entre `int` e `Date` (tipos BSON distintos) **não casa** — logo, mesmo persistindo a duração, o predictor continuaria a não a encontrar.

### Porque o desenho NÃO pode ser um patch no consumer (lição da harmonização)

Meter a persistência dentro do `execution_result_consumer` resolveria o sintoma mas **violaria o modelo harmonizado** (ADR-0011): o loop LEARN é **plano-Z transversal**, não uma propriedade da capacidade EXECUTE. Acoplá-lo a C significaria que o feedback de GENERATE (G6-G13) e de MIGRATE (H) nunca passaria pelo mesmo canal, e que o formato da Fundação seria ditado pelo `ExecutionResult` de EXECUTE (o "inverso" proibido: uma capacidade a definir a fundação). A correção é construir a **Fundação transversal primeiro** e ligar EXECUTE como **adapter**.

## Princípio de desenho

1. **Fundação primeiro, transversal** — o contrato `ExecutionFeedback` e o `FeedbackSink` são capability-agnostic; não vivem dentro de nenhuma capacidade.
2. **A Fundação manda no formato** — as capacidades traduzem o seu resultado para o contrato canónico; o contrato nunca é "o que EXECUTE manda".
3. **Ganchos de Roteamento/Capacidades prontos** — `capability` e `journey_id` existem no contrato desde já (baratos), para que o passo 2 (router) e o passo 3 (adapters G/H) encaixem sem reabrir a Fundação.
4. **Desacoplamento persist↔signal** — a persistência tem `try/except` próprio e nunca propaga; o workflow não pode ficar refém de telemetria.
5. **Tipo único: epoch millis** — consistente com o schema `ExecutionTicket` e com `ticket_generation`; corrige-se o leitor (predictor), não se introduz `datetime` na escrita.
6. **Verde-falso observável mas não treinável** — `result_simulated` é persistido (observabilidade) e excluído do treino (qualidade de dados).

## Contrato canónico `ExecutionFeedback`

Formalizado como Avro em `schemas/execution-feedback/execution-feedback.avsc` e como modelo Pydantic partilhado.

| Campo | Tipo | Origem | Papel |
|---|---|---|---|
| `feedback_id` | str | `{ticket_id}:{millis}` | idempotência/auditoria |
| `capability` | str | emissor | `EXECUTE`\|`GENERATE`\|`MIGRATE` — gancho de Capacidade |
| `journey_id` | str\|null | router (passo 2) | gancho de Roteamento (hoje opcional) |
| `ticket_id` | str | evento | chave de update |
| `plan_id` | str | evento | correlação de plano |
| `trace_id` | str\|null | evento | correlação OBSERVE |
| `status` | str | evento | filtrar COMPLETED |
| `actual_duration_ms` | int\|null | evento | **label** do regressor |
| `started_at` | int\|null | evento | epoch millis |
| `completed_at` | int\|null | evento / now | epoch millis (filtro de janela) |
| `simulated` | bool | `metadata.simulated` | exclui verde-falso do treino |
| `feedback_persisted_at` | int | now | auditoria do loop |

## Superfície de alteração

### Ficheiros a criar
- `schemas/execution-feedback/execution-feedback.avsc` — contrato Avro.
- `services/orchestrator-dynamic/src/observability/feedback_sink.py` — `FeedbackSink` (plano-Z); `record(ExecutionFeedback)` idempotente.
- modelo Pydantic `ExecutionFeedback` (em `src/models/` partilhado do orchestrator).

### Ficheiros a alterar
- `services/orchestrator-dynamic/src/consumers/execution_result_consumer.py` — construtor recebe `feedback_sink`; novo `_emit_feedback()` (adapter EXECUTE: traduz e delega); chamada após o signal, antes do `commit`.
- `services/orchestrator-dynamic/src/ml/duration_predictor.py` — `cutoff` em epoch millis (linhas ~203 e ~571); adicionar `result_simulated: {"$ne": True}` à query.
- `services/orchestrator-dynamic/src/main.py` — instanciar `FeedbackSink(app_state.mongodb_client)` e injetá-lo no consumer (DI já disponível em `main.py:498,544`).

### Coleção
- Reutiliza `execution_tickets` (o predictor já lê). Campos novos: `capability`, `journey_id`, `result_simulated`, `feedback_persisted_at`. Sem store novo nesta fase.

## Esboço de código (referência)

```python
# observability/feedback_sink.py  (PLANO-Z, transversal)
class FeedbackSink:
    COLLECTION = "execution_tickets"
    def __init__(self, mongodb_client, metrics=None):
        self.db = mongodb_client.db
        self.metrics = metrics
    async def record(self, fb) -> None:
        if not fb.ticket_id:
            return
        try:
            await self.db[self.COLLECTION].update_one(
                {"ticket_id": fb.ticket_id},
                {"$set": {
                    "capability": fb.capability, "journey_id": fb.journey_id,
                    "status": fb.status, "actual_duration_ms": fb.actual_duration_ms,
                    "started_at": fb.started_at, "completed_at": fb.completed_at,  # millis
                    "result_simulated": fb.simulated,
                    "feedback_persisted_at": fb.feedback_persisted_at,
                }},
                upsert=False,
            )
        except Exception as e:
            logger.warning("feedback_sink_persist_failed", ticket_id=fb.ticket_id, error=str(e))
```

```python
# duration_predictor.py  (LEARN — alinhar leitor)
cutoff_ms = int((datetime.now(timezone.utc)
                 - timedelta(days=self.config.ml_training_window_days)).timestamp() * 1000)
query = {
    "completed_at": {"$gte": cutoff_ms},
    "actual_duration_ms": {"$exists": True, "$ne": None, "$gt": 0},
    "result_simulated": {"$ne": True},
}
```

## Validação por fase (gates)

- **Gate Fase 0 (Contrato/Sink):** testes unitários do `FeedbackSink` passam, incluindo `record(capability="GENERATE")` sem alteração (transversalidade) e idempotência (2ª chamada não duplica).
- **Gate Fase 1 (Adapter EXECUTE):** após E2E A→C6, `execution_tickets` do plano de teste tem `actual_duration_ms>0` e `completed_at` em millis; o signal Temporal continua a fechar 8/8 tickets (persist não bloqueia).
- **Gate Fase 2 (Leitor LEARN):** `check_training_data_availability()` não regista `insufficient_training_data`; um ticket `simulated=true` é excluído da query de treino.
- **Gate Fase 3 (Anti-regressão):** asserção E2E "contagem de duração real sobe vs baseline"; guarda que falha se o filtro do predictor voltar a usar `datetime`.

## Mapa de risco

| Fase | Risco | Mitigação | Reversível? |
|---|---|---|---|
| 0 Contrato/Sink | Nenhum (não toca runtime) | testes unitários | — |
| 1 Adapter EXECUTE | Baixo (persist falha bloqueia signal?) | try/except isolado; persist após signal | Sim (1 commit) |
| 2 Leitor LEARN | Baixo (query muda) | gate de disponibilidade + exclusão simulados | Sim |
| 3 Anti-regressão | Nenhum | assert estruturado no E2E/CI | — |

## Notas de evolução (fora de escopo, mas habilitadas)

- **Roteamento (passo 2):** o journey router passa a preencher `journey_id`; sink/predictor intactos.
- **Capacidades (passo 3):** GENERATE/MIGRATE ligam-se como novos adapters ao **mesmo** `FeedbackSink`; Fundação não reabre.
- **Store dedicado:** mudar `FeedbackSink.COLLECTION` para `execution_feedback` (+ ajustar o reader) sem tocar emissores.
