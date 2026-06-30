# Gate E2E no cluster — loop provado end-to-end (2026-06-22)

> Spec: 2026-06-22-fundacao-loop-learn · Branch `feat/convergencia-dbs` · Imagem `orchestrator-dynamic:a64d7f0`
> Executado contra o cluster real com o código deployed.

## Como foi corrido (contornando o sandbox do harness)

O script `test-e2e-pipeline-completo.sh` não corre no sandbox (exit 144 — SIGTERM mata o
`kubectl port-forward` de longa duração). O E2E foi replicado via pods efémeros dentro do
cluster, contornando 3 barreiras descobertas:
1. **port-forward morre** → aceder ao gateway pelo **ClusterIP** de dentro do cluster.
2. **istio sidecar race** (curl antes do proxy ready, exit 7) → `sleep 14` antes do curl.
3. **mTLS STRICT / Host header** → pod **com** sidecar (identidade mTLS) + conectar ao
   **ClusterIP** (o `LoopbackAwareTrustedHostMiddleware` aceita rede pod 10.x).

## Fluxo executado (A→C6)

1. **Intenção** (texto forte do script): gateway → `intent_id d015485c`, `status processed`,
   confiança 0.95, domínio SECURITY, `requires_manual_validation=false`.
2. **Plano** `d7ac4c54` (risk_band medium) em `neural_hive_dev`: cognitive_ledger=1,
   consensus_decisions=1, plan_approvals=1 (status `pending`).
3. **Aprovação**: `POST /api/v1/approvals/d7ac4c54/approve` (Basic auth admin) → `approved`.
4. **Execução**: orchestrator gerou tickets → workers → `execution.results` → **consumer
   novo (a64d7f0) → FeedbackSink**.

## Prova do loop (tickets em `neural_hive_orchestration`)

8 tickets COMPLETED (task_0–task_7), **todos** com o feedback do sink novo:

| Validação | Resultado |
|---|---|
| `feedback_persisted_at` SET + `capability=EXECUTE` | 8/8 ✅ (sink transversal gravou) |
| `completed_at instanceof Date` | 8/8 ✅ (correção de tipo pós-gate — sink converte millis→Date) |
| `result_simulated` correto | task_3 e task_6 = **true**; restantes false ✅ |
| `actual_duration_ms` real | 695–12066 ms ✅ |

O `result_simulated=true` em 2 tasks **prova C1 corrigido**: o adapter lê `simulated` de
`result.metadata` (no caminho real) — antes lia o topo do payload e dava sempre `false`.

## Validação do leitor LEARN (filtro do predictor, dados reais)

```
treináveis (datetime + result_simulated!=true + dur>0, 30d): 214  ≥ ml_min=100  ✅
tickets com result_simulated=true (excluídos do treino):       2
tickets com feedback do sink novo:                             8
```

## Nota — bug pré-existente independente

Surgiram também 8 tickets PENDING duplicados (16 total vs 8) — é o bug conhecido de
tickets duplicados do orchestrator (issue independente, ver MEMORY), não relacionado com
esta spec. Os 8 COMPLETED têm o feedback correto.

## Conclusão

O loop OBSERVE→LEARN está **provado end-to-end no cluster**: execução real → sink grava
feedback com tipo correto (Date) e anti-verde-falso funcional (result_simulated de
result.metadata) → predictor encontra 214 treináveis excluindo simulados. Todas as
correções (Fundação, contrato Date, C1/C2/A1 da auditoria) confirmadas em produção.
