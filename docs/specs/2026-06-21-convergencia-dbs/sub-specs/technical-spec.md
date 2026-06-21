# Technical Specification

This is the technical specification para a spec detalhada em @docs/specs/2026-06-21-convergencia-dbs/spec.md

## Descoberta-chave (análise de causa-raiz)

O "drift" reportado pelo E2E (`plan_approvals a 0 em neural_hive_dev mas 1 em neural_hive`) **não é um bug de configuração** — é o resíduo de uma **migração de nomenclatura incompleta** sobreposta a decisões per-serviço de "cada serviço com a sua DB". Investigação (código + cluster + git) confirmou:

- **O default de código é `neural_hive`** em todos os `settings.py` (`mongodb_database: str = Field(default="neural_hive")`). Era a DB monolítica original.
- **`neural_hive_dev` foi criada para isolar dados frescos do corpus poluído** (`cognitive_ledger` legado tem ~10246 docs, muitos degenerados de E2E/labels circulares). Só os serviços geradores de planos (STE, consensus, 5 specialists) foram repontados, via `environments/dev/helm-values/`.
- **A migração nunca foi terminada**: approval-service, gateway, worker-agents, memory-layer-api, feature-store, optimizer, queen ficaram no default `neural_hive`.
- **Existem 4 (na verdade 5+) DBs**: `neural_hive_orchestration` (orchestrator) e `neural_hive_workers` (só DLQ) são drift adicional; `neural_hive_analytics` aparece num cronjob.

### Estado real medido no cluster (run E2E de 2026-06-21)

| DB | Tamanho | Conteúdo (evidência) | Quem aponta |
|---|---|---|---|
| `neural_hive` | 53.3 MB | `explainability_ledger` 18626, `cognitive_ledger` 10246, `specialist_opinions` 8291, `specialist_feedback` 2482, `consensus_decisions` 767, **`plan_approvals` 485**, `plan_features` 648 | default de código → approval, gateway, worker, memory-layer, feature-store, optimizer, queen |
| `neural_hive_dev` | 6.2 MB | run fresco: ledger 1, opinions 4, consensus 1 | dev-values: STE, consensus, 5 specialists |
| `neural_hive_orchestration` | 2.8 MB | estado de orquestração | orchestrator-dynamic (configmap) |
| `neural_hive_workers` | ~0 MB | só `execution_tickets_dlq` | worker-agents (tickets reais em PostgreSQL) |

### Porque o repoint ingénuo do approval-service partiu (lição de `6fddd01d`)

O fluxo de aprovação está **desacoplado via Kafka/HTTP, não via Mongo partilhado**:
- O orchestrator **não lê** `plan_approvals` em Mongo (recebe o sinal pelo tópico Kafka `cognitive-plans-approval-responses`, `flow_c_consumer.py`).
- O approval-service é o **dono único** (escritor + leitor) de `plan_approvals` e faz ML/active-learning sobre o corpus acumulado (`specialist_feedback` 2482, `plan_approvals` 485) que vive em `neural_hive`.

Repontá-lo sozinho para `neural_hive_dev` desligou-o desse corpus → coleções vazias → HTTP 404 → 0 tickets. **A correção não é nunca-mexer; é migrar os dados primeiro** (esta spec, Fase 1/2). O comentário em `services/approval-service/helm/approval-service/values-dev.yaml:25-34` documenta o porquê do revert e deixa de ser verdadeiro após a Fase 1.

## Princípio de desenho

1. **Migrar dados antes de repontar** — nenhum serviço é repontado antes de a sua coleção-fonte existir e estar validada no alvo.
2. **Copiar, não mover, até ao corte** — `neural_hive` permanece intacta (fallback vivo) até N dias de E2E verde; só então é arquivada read-only.
3. **Gate E2E entre fases** — cada fase só fecha com o A→C6 verde (8/8 tickets) e contagens por DB conferidas.
4. **Reversibilidade explícita** — cada repoint é 1 commit declarativo (dev-values) reversível; cada migração é aditiva (não destrutiva).
5. **Config explícita como anti-regressão** — eliminar o default de código implícito; `MONGODB_DATABASE` obrigatório.

## Alvo e mapa de migração de coleções

DB-alvo dev: **`neural_hive_dev`**.

| Coleção | DB atual (fonte-de-verdade) | Ação |
|---|---|---|
| `cognitive_ledger` | `neural_hive_dev` (fresco) + `neural_hive` (legado poluído) | manter dev; **não** migrar legado degenerado |
| `specialist_opinions` | ambas (8291 legado / 4 fresco) | copiar legado válido → dev, de-dup por `plan_id`+`specialist` |
| `specialist_feedback` | `neural_hive` (2482) | copiar → dev |
| `plan_approvals` | `neural_hive` (485) | copiar → dev + recriar índice TTL GDPR (`m002`) |
| `plan_features` | `neural_hive` (648) | copiar → dev |
| `consensus_decisions` | `neural_hive_dev` (fresco) | manter |
| `execution_tickets_dlq` | `neural_hive_workers` | vazio → trivial / descartável |
| estado orchestration | `neural_hive_orchestration` | avaliar: migrar ou manter schema lógico documentado |

## Técnica de migração (sem escrita dupla)

- **Migração aditiva idempotente**: script versionado que copia por `plan_id`/chave natural com `upsert`, re-executável sem duplicar.
- **De-duplicação**: `specialist_opinions` existe em ambas — chave natural (`plan_id`+`specialist_type`+`created_at`) para evitar duplicados.
- **Índices**: recriar todos os índices da coleção no alvo, incluindo o TTL GDPR de `plan_approvals` (2 anos, `m002_gdpr_ttl_indexes.py`).
- **Janela de corte**: para o delta final, escalar a 0 os escritores do corpus (freeze curto) → copiar delta desde o timestamp da Fase 1 → repontar → re-escalar. Alternativa: `neural_hive` frozen read-only e passe-delta único.

## Superfície de alteração declarativa

dev-values a **criar** (hoje ausentes → herdam default de código):
- `environments/dev/helm-values/approval-service-values.yaml` (`config.mongodb.database: neural_hive_dev`)
- `environments/dev/helm-values/gateway-intencoes-values.yaml`
- `environments/dev/helm-values/worker-agents-values.yaml`
- (Fase posterior / fora de âmbito imediato) feature-store, optimizer, queen

Cronjobs a repontar (env `MONGODB_DATABASE`):
- `k8s/cronjobs/specialist-retraining-job.yaml`
- `k8s/cronjobs/predictive-models-training-job.yaml`
- `k8s/cronjobs/business-metrics-job.yaml`

Anti-regressão:
- Tornar `MONGODB_DATABASE` obrigatório nos `settings.py` (sem default, ou default que falha-fast em ambiente não-test).
- Guarda no script E2E (`scripts/test-e2e-pipeline-completo.sh`): transformar o aviso atual de drift num assert estruturado que distingue "drift esperado durante transição" de "falha real".

## Validação por fase (gates)

- **Gate Fase 0**: restore-test do backup num namespace efémero bem-sucedido.
- **Gate Fase 1**: contagens copiadas == origem (menos degenerados); retraining vê ≥ baseline de amostras.
- **Gate Fase 2**: E2E A→C6 verde, `plan_approvals` do novo plano em `neural_hive_dev`, 0 ocorrências de 404, 8/8 tickets COMPLETED.
- **Gate Fase 3**: E2E verde após cada repoint.
- **Gate Fase 4**: contagem `neural_hive` estabiliza (0 escritas novas) durante janela de observação.
- **Gate Fase 5**: nenhum deployment sem `MONGODB_DATABASE` explícito; guarda anti-regressão ativa no CI.

## Mapa de risco

| Fase | Risco | Mitigação | Reversível? |
|---|---|---|---|
| 0 Baseline/backup | Nenhum | restore-test | — |
| 1 Copiar corpus + cronjobs RO | Baixo | cópia aditiva; cronjobs não escrevem pipeline | Sim (env) |
| 2 approval-service | **Médio** (foi o que partiu) | dados-primeiro elimina o 404 | Sim (1 commit) |
| 3 gateway/worker | Baixo | gate E2E por repoint | Sim |
| 4 Janela de corte | Médio (downtime curto) | freeze + delta idempotente | Sim (re-escalar) |
| 5 Limpeza | Baixo | arquivar, não apagar | Arquivo restaurável |
