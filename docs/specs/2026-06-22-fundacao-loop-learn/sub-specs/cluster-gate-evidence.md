# Gate de cluster — descoberta e correção (2026-06-22)

> Spec: 2026-06-22-fundacao-loop-learn · Branch `feat/convergencia-dbs` (pós-merge `7548690f`)
> Executado contra o cluster real (Contabo), DB `neural_hive_orchestration`.

## O que o gate de cluster revelou

A execução dos gates contra o cluster **invalidou uma premissa central da Fase 2** e
recalibrou o valor do trabalho. Factos medidos em `neural_hive_orchestration.execution_tickets`:

| Métrica | Valor real |
|---|---|
| total de tickets | 1299 |
| com `actual_duration_ms > 0` | **240** |
| `completed_at` / `started_at` tipo | **BSON `Date`** (não int millis) |
| `created_at` tipo | int millis |
| `result_simulated` (campo) | inexistente (0 docs) |
| `ml_min_training_samples` | 100 |

**A coleção vive em `neural_hive_orchestration`** (decisão da convergência-dbs de manter o
schema operacional), não em `neural_hive_dev`. O sink e o predictor usam ambos
`mongodb_client.db`, logo apontam para a MESMA DB do orchestrator — alinhados.

## Premissa errada da Fase 2 (corrigida)

A Fase 2 assumiu `completed_at` como int millis (extrapolando de `ticket_generation.py:256`
que grava `created_at` em millis) e mudou o filtro do predictor para millis. **Errado:**
`completed_at`/`started_at` são gravados como `Date`. Medição do impacto na janela de 30d:

| Filtro | Tickets encontrados |
|---|---|
| original `datetime` (correto) | **208** |
| Fase 2 `millis` (regressão) | 32 |

Com `ml_min_training_samples=100`: 208 ≥ 100 (treina) vs 32 < 100 (cego). **A Fase 2 teria
introduzido uma regressão que cegava o predictor.** O gate apanhou-a antes do deploy.

## Correção aplicada (contrato Date)

Decisão do utilizador: **alinhar com o real (Date)**, sem migração.

- `duration_predictor.py` — revertido `cutoff_ms`→`cutoff_date` (datetime) nos 2 sítios;
  **mantida** a exclusão `result_simulated:{$ne:true}`.
- `feedback_sink.py` — `_ms_to_datetime()` converte `completed_at`/`started_at` de millis
  (contrato portável) para BSON `Date` ao gravar, casando com os 240 tickets existentes e
  com o filtro do predictor. `actual_duration_ms` permanece int (não é timestamp).
- Testes atualizados para o contrato `Date` (sink grava datetime; predictor filtra datetime;
  guarda cruzada verifica datetime consistente). **21/21 verdes.**

## Validação contra dados reais

```
filtro CORRIGIDO (datetime + result_simulated!=true), 30d → 208 treináveis  (≥100 ✅)
```

## Reenquadramento honesto do valor

O diagnóstico de 2026-06-21 (loop cego, 3/1247) estava **desatualizado** — algo (provável
trabalho "ExecutionResultConsumer persistence" de 2026-06-21) já persiste duração +
`completed_at` Date, e o predictor original já tinha 208≥100 amostras. O valor real desta
spec **não** é destravar o predictor (já treinava), mas:

1. **Exclusão de verde-falso do treino** (`result_simulated`) — novo, protege a qualidade.
2. **Sink/adapter transversal** — garante que novos tickets têm duração persistida de forma
   consistente (Date), por qualquer capacidade (EXECUTE hoje; GENERATE/MIGRATE depois).
3. **Guardas anti-regressão** + **evitar a regressão de tipo** que a Fase 2 ia introduzir.

## Pendente

- **Deploy** do orchestrator com este código (sink converte Date; predictor mantém datetime)
  e **E2E A→C6** para confirmar que novos tickets do sink aparecem com `completed_at` Date e
  `result_simulated` preenchido. Sem deploy, o cluster corre a versão antiga.
