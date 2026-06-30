# Inventário de fonte-de-verdade por coleção (Fase 0)

> Spec: convergencia-dbs — Fase 0 (preparação risco-zero)
> Gerado por: `scripts/db-convergence/00-inventory.sh` (read-only)
> Data do levantamento (UTC): 2026-06-21T21:53:21Z
> Contexto kubectl: neural-hive-prod

Levantamento read-only das DBs MongoDB `neural*` e de TODAS as DBs
PostgreSQL não-sistema da instância de dados. Contagens via
`countDocuments` (Mongo) e `COUNT(*)` exato (PostgreSQL — não
`n_live_tup`, que é estimativa do planner e pode estar stale).

## MongoDB — coleção → DB → contagem → alvo de migração

Coluna **Alvo** = decisão de desenho (mapa de migração do
`technical-spec.md`), não uma medição. DB-alvo dev: `neural_hive_dev`.

| DB | Coleção | Documentos | Alvo de migração |
|---|---|---|---|
| `neural_hive` | `ab_test_results` | 0 | (avaliar) |
| `neural_hive` | `approvals` | 1 | (avaliar) |
| `neural_hive` | `authorization_audit` | 91 | (avaliar) |
| `neural_hive` | `cognitive_ledger` | 10246 | manter dev; nao migrar legado degenerado |
| `neural_hive` | `compliance_audit_log` | 3 | (avaliar) |
| `neural_hive` | `consensus_decisions` | 767 | manter dev |
| `neural_hive` | `consensus_explainability` | 0 | (avaliar) |
| `neural_hive` | `data_quality_metrics` | 3555 | (avaliar) |
| `neural_hive` | `exception_approvals` | 0 | (avaliar) |
| `neural_hive` | `execution_tickets` | 0 | orchestration: avaliar (tickets-Mongo != tickets-PG) |
| `neural_hive` | `experiments_ledger` | 0 | (avaliar) |
| `neural_hive` | `explainability_ledger` | 18626 | copiar -> dev |
| `neural_hive` | `explainability_ledger_v2` | 8373 | (avaliar) |
| `neural_hive` | `incident_postmortems` | 0 | (avaliar) |
| `neural_hive` | `incidents` | 0 | (avaliar) |
| `neural_hive` | `insights` | 217 | (avaliar) |
| `neural_hive` | `model_metadata` | 12 | (avaliar) |
| `neural_hive` | `operational_context` | 0 | (avaliar) |
| `neural_hive` | `optimization_ledger` | 0 | (avaliar) |
| `neural_hive` | `pheromone_signals` | 520 | (avaliar) |
| `neural_hive` | `plan_approvals` | 485 | copiar -> dev + recriar TTL GDPR (m002) |
| `neural_hive` | `plan_approvals_continuous_feedback` | 0 | (avaliar) |
| `neural_hive` | `plan_features` | 648 | copiar -> dev |
| `neural_hive` | `redis_fallback` | 540 | (avaliar) |
| `neural_hive` | `remediation_actions` | 0 | (avaliar) |
| `neural_hive` | `security_incidents` | 0 | (avaliar) |
| `neural_hive` | `specialist_feedback` | 2482 | copiar -> dev |
| `neural_hive` | `specialist_opinions` | 8291 | copiar legado valido -> dev (de-dup plan_id+specialist_type+created_at) |
| `neural_hive` | `strategic_decisions_ledger` | 0 | (avaliar) |
| `neural_hive` | `telemetry_buffer` | 0 | (avaliar) |
| `neural_hive` | `validation_audit` | 115 | (avaliar) |
| `neural_hive` | `workflow_results` | 79 | (avaliar) |
| `neural_hive` | `workflows` | 0 | (avaliar) |
| `neural_hive_dev` | `cognitive_ledger` | 97 | manter dev; nao migrar legado degenerado |
| `neural_hive_dev` | `compliance_audit_log` | 188 | (avaliar) |
| `neural_hive_dev` | `consensus_decisions` | 199 | manter dev |
| `neural_hive_dev` | `consensus_explainability` | 0 | (avaliar) |
| `neural_hive_dev` | `explainability_ledger` | 288 | copiar -> dev |
| `neural_hive_dev` | `explainability_ledger_v2` | 191 | (avaliar) |
| `neural_hive_dev` | `operational_context` | 0 | (avaliar) |
| `neural_hive_dev` | `pheromone_signals` | 968 | (avaliar) |
| `neural_hive_dev` | `plan_approvals` | 0 | copiar -> dev + recriar TTL GDPR (m002) |
| `neural_hive_dev` | `plan_approvals_continuous_feedback` | 0 | (avaliar) |
| `neural_hive_dev` | `plan_features` | 29 | copiar -> dev |
| `neural_hive_dev` | `redis_fallback` | 54 | (avaliar) |
| `neural_hive_dev` | `specialist_feedback` | 0 | copiar -> dev |
| `neural_hive_dev` | `specialist_opinions` | 188 | copiar legado valido -> dev (de-dup plan_id+specialist_type+created_at) |
| `neural_hive_orchestration` | `authorization_audit` | 3819 | (avaliar) |
| `neural_hive_orchestration` | `code_artifacts` | 1 | (avaliar) |
| `neural_hive_orchestration` | `cognitive_ledger` | 0 | manter dev; nao migrar legado degenerado |
| `neural_hive_orchestration` | `execution_tickets` | 1255 | orchestration: avaliar (tickets-Mongo != tickets-PG) |
| `neural_hive_orchestration` | `incidents` | 0 | (avaliar) |
| `neural_hive_orchestration` | `telemetry_buffer` | 0 | (avaliar) |
| `neural_hive_orchestration` | `ticket_audit_log` | 0 | (avaliar) |
| `neural_hive_orchestration` | `validation_audit` | 245 | (avaliar) |
| `neural_hive_orchestration` | `workflow_results` | 64 | (avaliar) |
| `neural_hive_orchestration` | `workflows` | 0 | (avaliar) |
| `neural_hive_workers` | `execution_tickets_dlq` | 0 | vazio -> descartavel |

### Totais por DB Mongo

| DB | Total de documentos |
|---|---|
| `neural_hive` | 55051 |
| `neural_hive_dev` | 2202 |
| `neural_hive_orchestration` | 5384 |
| `neural_hive_workers` | 0 |

## PostgreSQL — todas as DBs não-sistema (só backup, não convergem para Mongo)

| DB | Tabela | Linhas (COUNT exato) |
|---|---|---|
| `code_forge` | `artifact_metadata` | 0 |
| `code_forge` | `pipeline_results` | 0 |
| `neural_hive_tickets` | `execution_tickets` | 0 |
| `sla_management` | `alerts` | 0 |
| `sla_management` | `error_budgets` | 0 |
| `sla_management` | `execution_tickets` | 935 |
| `sla_management` | `freeze_events` | 0 |
| `sla_management` | `freeze_policies` | 0 |
| `sla_management` | `slo_definitions` | 0 |

Total de linhas: 935

## Notas

- Este artefacto é regenerado idempotentemente por `00-inventory.sh`; cada execução substitui o conteúdo com o estado atual.
- **Fonte-de-verdade dos tickets em PostgreSQL:** `sla_management.execution_tickets` (dados reais). A DB `neural_hive_tickets.execution_tickets` está **genuinamente vazia (0)** — confirmado por `COUNT(*)` exato, não estimativa stale. O `execution-ticket-service` aponta para `POSTGRES_DATABASE=sla_management`.
- **Discrepância a resolver (Fases 3/6):** tickets-PG (`sla_management.execution_tickets`) vs tickets-Mongo (`neural_hive_orchestration.execution_tickets`) são conjuntos distintos. O mapeamento de fonte-de-verdade única de tickets fica para as fases de consolidação; o backup da Fase 0 captura **ambos** os lados (todas as DBs PG + todas as DBs Mongo).
- Nenhuma DB PostgreSQL converge para Mongo nesta spec — entram apenas no backup (ver `01-backup.sh`).
- Registos degenerados de `cognitive_ledger` em `neural_hive` são identificados (sem apagar) por `03-identify-degenerate.js`.
