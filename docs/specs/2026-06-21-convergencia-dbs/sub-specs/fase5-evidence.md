# Evidência de execução — Fase 5 (Task 8: prevenção de regressão e limpeza)

> Spec: convergencia-dbs — Fase 5. Contexto: `neural-hive-prod`.

## DoD — checklist com evidência

| Item | Estado | Evidência |
|---|---|---|
| 8.1 `MONGODB_DATABASE` explícito/fail-fast nos settings + fix hardcodes | ✅ (escopo seguro) | validator fail-fast no approval-service + 2 hardcodes corrigidos + 13 testes |
| 8.2 Aviso de drift → assert estruturado no E2E | ✅ | `test-e2e-pipeline-completo.sh`: regressão de convergência → gate falha (exit 3) |
| 8.3 Arquivar `neural_hive` read-only | ⏳ **diferido** | gated pela DoR ("N dias de E2E verde"); corte foi hoje — ver decisão abaixo |
| 8.4 Atualizar inventário canónico | ✅ | estado final abaixo + memória; `CONTABO_TICKET.md` é ficheiro não-relacionado (não tocado) |

## 8.1 — `MONGODB_DATABASE` explícito (fail-fast) + fix dos hardcodes

### Fix dos hardcodes (bugs que tornavam o repoint da Task 3 inerte)

- `ml_pipelines/training/train_predictive_models.py:54`: `self.mongo_client.neural_hive`
  → `self.mongo_client[os.getenv("MONGODB_DATABASE", "neural_hive")]`.
- `ml_pipelines/training/train_specialist_model.py:903`: `client["neural_hive"]`
  → `client[os.getenv("MONGODB_DATABASE", "neural_hive")]`.

Agora estes caminhos honram a env `MONGODB_DATABASE` (antes ignoravam-na, anulando o
repoint declarativo dos cronjobs feito na Task 3).

### Fail-fast no `approval-service` (o serviço que regrediu)

`services/approval-service/src/config/settings.py`: novo `model_validator`
`require_explicit_mongodb_database` + função pura testável
`require_mongodb_database_explicit(environment, explicit, under_pytest)`. Em ambiente
de deployment real (não test/local) sem `MONGODB_DATABASE` explícito → `ValueError`
no arranque. **Pytest-safe** (salta sob pytest → não quebra testes/CI). 13 testes
novos passam (`tests/unit/test_mongodb_database_required.py`): falha em
production/staging/development sem env; OK com env explícito; OK em test/local; OK sob
pytest. `ruff`/`black -l 100` limpos nos ficheiros alterados.

### Escopo deliberado (anti-big-bang)

O fail-fast foi aplicado ao **approval-service** (o serviço central da spec, "o ponto
que partiu", com `MONGODB_DATABASE=neural_hive_dev` verificado no deployment). O mesmo
padrão é **seguro** para `consensus-engine` e `semantic-translation-engine` (pods
verificados com `MONGODB_DATABASE=neural_hive_dev`) e deve ser estendido a eles. NÃO foi
aplicado aos serviços **fora do âmbito da convergência** (`optimizer-agents`,
`memory-layer-api`, `hypothesis-library`, `experiment-impact-analyzer`,
`learning-doc-generator`) porque os seus deployments podem não ter a env — um fail-fast
big-bang partiria-os no próximo rebuild. Roll-out incremental recomendado, com
verificação do env por deployment antes de cada ativação.

## 8.2 — Assert estruturado anti-drift no E2E

`scripts/test-e2e-pipeline-completo.sh`: o aviso de drift (`log_error "AVISO ... drift
de DB"`) passou a **assert estruturado** que distingue:
- **Regressão de convergência** (coleção em `CONVERGED_COLLECTIONS` com dados na DB
  legada `neural_hive` e 0 na canónica) → acumula num marcador e o **gate falha**
  (`exit 3`) no fim, com lista das coleções em regressão.
- **Drift esperado** (coleção ainda não convergida) → mantém o aviso (não falha).

`CONVERGED_COLLECTIONS` (default) = `plan_approvals specialist_feedback
specialist_opinions plan_features explainability_ledger cognitive_ledger
consensus_decisions`. Sintaxe validada (`bash -n`); lógica de pertença testada
(convergidas→falha, não-convergidas→aviso). No estado atual (pós-Fases 1-4) não há
drift, por isso o gate passa; passará a falhar se uma regressão reintroduzir escrita
do corpus em `neural_hive`.

**Ressalva honesta (versionamento):** `scripts/test-e2e-*.sh` é ignorado por política
deliberada do repo (`.gitignore:75`), logo esta alteração vive na **working tree** —
exatamente onde o E2E é executado (teste manual contra o cluster; não é um job de CI,
que não tem acesso ao cluster). O guard está, portanto, ativo onde o E2E corre. Não
forcei `git add -f` nem alterei o `.gitignore` (seria override unilateral de política).
Para versionar o guard em git, o maintainer deve decidir des-ignorar o ficheiro.

## 8.3 — Arquivar `neural_hive` read-only — DIFERIDO (gated)

A própria DoR da Task 8 exige "N dias de E2E verde acordados antes de arquivar". O
corte (Fase 4) foi concluído **hoje** (2026-06-22). Arquivar agora queimaria a janela de
observação e seria irreversível-na-prática. **Decisão honesta: NÃO arquivar nesta
sessão.** Pré-condições para executar 8.3 depois:
- N dias (a acordar) de E2E verde com o corpus 100% em `neural_hive_dev`.
- Confirmar 0 escritas novas em `neural_hive` corpus durante a janela (Fase 4 já mostra
  Δ=0; manter a observação).
- Então: `neural_hive` → read-only/rename (não apagar; backup `20260622T085101Z` é o
  fallback). Idem `neural_hive_workers` (DLQ vazio desde a Task 5).

## 8.4 — Estado final do inventário

A convergência converge o **corpus cognitivo** para `neural_hive_dev` (DB canónica dev).

| DB | Papel final | Estado |
|---|---|---|
| `neural_hive_dev` | **Canónica** — corpus cognitivo + sinal de treino | viva, a crescer |
| `neural_hive` | Legada — corpus congelado (Δ=0 sob workload) | fallback vivo → arquivar (Fase 5/8.3, gated) |
| `neural_hive_orchestration` | Schema lógico intencional da camada de orquestração | mantida (decisão Task 6) |
| `neural_hive_workers` | DLQ (vazio; worker repontado na Task 5) | → arquivar (Fase 5/8.3, gated) |

Escritores do corpus → `neural_hive_dev`: STE, consensus, 5 specialists (pré-existente),
approval-service (Fase 2), worker-agents (Fase 3). gateway não usa Mongo. Cronjobs ML +
feature-store repontados (Fase 1/Task 3; predictive efetivo após o fix de hardcode 8.1).
O `inventory.md` (gerado por `00-inventory.sh`) pode ser regenerado para o snapshot
numérico final. `CONTABO_TICKET.md` referido na tarefa é um ficheiro não-relacionado
(ticket de rede) — não atualizado.

## Resultado da Fase 5

Anti-regressão ativa: config explícita (fail-fast no approval-service + fix dos
hardcodes que anulavam repoints) e guarda no E2E (assert estruturado que falha em
regressão de drift). Arquivo das DBs legadas (`neural_hive`, `neural_hive_workers`)
fica gated pela janela de observação acordada. O roll-out do fail-fast aos restantes
serviços do corpus é incremental e verificado.
