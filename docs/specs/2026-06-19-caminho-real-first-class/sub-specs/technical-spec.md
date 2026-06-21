# Technical Specification

This is the technical specification para a spec detalhada em @docs/specs/2026-06-19-caminho-real-first-class/spec.md

## Descoberta-chave (análise de viabilidade)

Investigação profunda (código + cluster + MLflow) revelou que **o caminho real está ~85% implementado**. O sistema não é "ML/execução falsos por falta de capacidade" — é **caminho real construído mas desligado** por wiring/config/dependências/dados. Isto reorienta a spec de "implementar de raiz" para "ligar + configurar + completar wiring", com 3 épicos genuínos isolados.

Confirmações relevantes:
- **Data-flow entre tasks JÁ está wired ponta-a-ponta** (`worker-agents/src/engine/execution_engine.py:356-422`, `_inject_dependency_outputs`): o worker injeta o `metadata.result` das dependências em `input_data` em runtime. A premissa anterior "input_data=null partido" estava desatualizada.
- **Os campos de honestidade já existem mas são ignorados**: `metadata.simulated` e `output.noop` são produzidos pelos executores mas o engine decide COMPLETED apenas por `success=True` (`execution_engine.py:~523`).

## Princípio de desenho

1. **Contrato de evidência por `task_type`** — o `execution_engine` só emite COMPLETED se houver evidência verificável do tipo correto; `metadata.simulated=True`/`output.noop=True`/evidência ausente → não-COMPLETED.
2. **Sem simulação em runtime** (dev e prod) — remover/gate os caminhos `_execute_simulation`/`stub://`; runtime sempre real ou falha explícita. (Mocks continuam legítimos em testes.)
3. **Honestidade como anti-regressão** — `degradation_total{component,reason}`, `real_path_unavailable_total` e `STRICT_REAL_PATH` impedem o regresso silencioso à simulação.

## Contrato de evidência (por task_type)

| task_type | Evidência verificável de COMPLETED |
|---|---|
| query | `output.count` + documentos/results reais; fonte registada (collection/cypher) |
| transform | output derivado não-noop (operações aplicadas; `output.noop != True`) |
| validate | decisão OPA com `result` presente (não `policy_undefined`) ou scan com findings; não `simulated` |
| build | artefacto pullable: `{registry}/{artifact}:{version}` + **digest** verificável (`skopeo inspect`/`crane digest`) |
| deploy | recurso reconciliado: ArgoCD App `Synced/Healthy` **ou** (modo imperativo) `helm --wait` + `kubectl rollout status` OK |
| execute | processo real com exit code real e stdout/stderr capturados (não `[SIMULAÇÃO]`) |
| generate_code (Fluxo G) | artefacto de código persistido (`code_artifact_id`/MongoDB) e, se exigido, commit/PR referenciável |

## Technical Requirements — por balde de esforço

### Balde A — Quick wins (CURTO, alto impacto)

- **Honestidade do engine** (`worker-agents/src/engine/execution_engine.py:~523`): gate que recusa COMPLETED quando `metadata.simulated=True`/`output.noop=True`/evidência ausente; emitir `simulated_total{executor,task_type}`. Os campos já existem.
- **Specialists ML em produção** (`specialist-*/src/config.py:21` + `helm-charts/specialist-*/values.yaml:~104`): alinhar `modelStage` — promover `<domain>-evaluator` Staging→Production **ou** apontar helm para Staging. Hoje prod pede `Production` (inexistente) → heurística.
- **Embeddings dos specialists** (`libraries/python/neural_hive_specialists/requirements.txt:~82`): instalar `sentence-transformers==3.3.1` (já está na base image dos specialists, mas confirmar) para eliminar os 3 features a zero (`embeddings_generator.py:102-107`).
- **STE NER/embeddings** (`semantic-translation-engine/requirements-base.txt`): adicionar `spacy==3.7.0` (o Dockerfile já baixa modelos `pt_core_news_sm`/`en_core_web_sm` mas falta o pacote base) e `sentence-transformers`+`torch` (opcional, fallback gracioso). Resolve `nlp_processor.is_ready()==False`.
- **Code Forge build real** (`services/code-forge/`): (a) escalar deploy ≥1 réplica (hoje 0/0); (b) montar `ghcr-secret` no pod Kaniko (`container_builder.py:995-1026`); (c) setar `OCI_REGISTRY_URL=ghcr.io/albinojimy/neural-hive-mind` e compor `--destination` com registry (`pipeline_engine.py:~394`); (d) devolver digest+URI no resultado.
- **Fluxo G wiring** (`orchestrator-dynamic/src/workers/temporal_worker.py:465`): registar as 10 activities G6-G13 em `activities=[...]`; chamar `set_code_generation_dependencies`; corrigir porta do code-forge 8020→8080 (`code_generation_activity.py:101,177`; `build_package_activity.py:84,164`).

### Balde B — Médio

- **Políticas OPA por domínio** (`policies/rego/orchestrator/`): criar `architecture/compliance`, `quality/standards`, `performance/limits`, `operational/procedures` seguindo o template de `security_validation.rego`; montar na ConfigMap do OPA. Tornar a degradação `policy_undefined` (`opa_client.py:197-210`) **fail-open só para domínios sem política exigida** (configurável).
- **Transform real (data-flow semântico)** (`semantic-translation-engine/src/services/decomposition_templates.py` + `cognitive_plan.py:59-76`): o STE deve gerar `operations` reais e uma referência de campo (`input_ref: "${dep.output.documents}"`) por task downstream; o executor resolve a referência. O transporte runtime já existe.
- **Validate fail-closed** (`validate_executor.py:330-375,215-229`): remover/gate o fallback simulado genérico; timeout SAST → `success=False`.
- **Deploy real imperativo** (`deploy_executor.py`): caminho `helm upgrade --wait` + `kubectl rollout status` como evidência (alternativa MÉDIA ao GitOps), com namespace efémero em dev.
- **Endpoint G1** (`fluxo_g_integration.py:72` vs `requirements-engineering/src/api/routers/requirements.py:40`): alinhar contrato `/from-plan`.
- **Ambiente efémero dev** (`deploy_executor.py:69` já aceita `namespace`): provisionar namespace efémero por ticket + `ResourceQuota`/TTL/cleanup.
- **Preditores ML** (`orchestrator-dynamic/src/ml/duration_predictor.py`, `neural_hive_ml/predictive_models/load_predictor.py`): treinar e registar (RandomForest/Prophet já implementados); ligar ao pipeline.

### Balde C — Épicos genuínos (GRANDE)

- **Classificador NLU de domínio ML** (`nlu-service/src/services/nlu_pipeline.py:865-958`): único componente sem ML. Requer dataset rotulado (texto→domínio), treino (sklearn TF-IDF / spaCy TextCategorizer / BERTimbau-PT), integração mantendo keyword como fallback marcado. Adicionar domínio `UNKNOWN`.
- **GitOps completo** (deploy ArgoCD/Flux): instalar no cluster, AppProject/repo, Secret de token, ligar `argocd_enabled=True`. Os clients (`argocd_client.py`/`flux_client.py`) já são reais.
- **Pipeline de dados reais** (`ml_pipelines/training/real_data_collector.py` — implementado, inativo): ligar coleta de `specialist_opinions`/`specialist_feedback`, acumular ≥1000 amostras/specialist, re-treinar (sair dos 399 sintéticos). Feature store é stub.

## External Dependencies (Conditional)

- **spacy==3.7.0** (STE) — NER real; o Dockerfile já baixa os modelos mas falta o pacote base. **Justificação:** sem ele, NER do STE devolve `[]` (heurística).
- **sentence-transformers==3.3.1** + **torch** (STE; confirmar nos specialists) — embeddings reais. **Justificação:** sem eles, reforço semântico do STE "permanentemente morto" e 3 features dos specialists a zero.
- **kubernetes-asyncio** (worker-agents) — necessário para `flux_client` (Balde C/GitOps).
- **evidently>=0.4.0** (specialists, opcional) — drift detection real (hoje no-op silencioso).
