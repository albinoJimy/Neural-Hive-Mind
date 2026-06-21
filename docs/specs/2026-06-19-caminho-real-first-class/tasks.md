# Spec Tasks

> Ordenação: Balde A (quick wins) → Balde B (médio) → Balde C (épicos). O caminho real está ~85% implementado; a maioria é ligar/configurar/wirear.
>
> **DoR/DoD genéricos e Políticas Transversais:** ver `sub-specs/execution-contract.md`. Cada task abaixo acrescenta a sua **DoR** (pré-condição específica) e **DoD** (evidência real específica). O Prompt Mestre do contrato é o ponto de entrada de execução.

## Tasks

### Balde A — Quick wins (CURTO, alto impacto)

- [x] 1. Contrato de evidência no execution_engine (parar o verde falso) ✅
  - **DoR:** confirmados os campos `metadata.simulated`/`output.noop`/`output.count` produzidos por cada executor (já existem); settings de ambiente acessíveis.
  - **DoD:** um ticket simulado/no-op NÃO fica COMPLETED em prod (verificado em MongoDB/PostgreSQL); métrica `simulated_total` incrementa; ticket real continua COMPLETED.
  - **ROLL-OUT (divergência documentada do default):** o gate é entregue em **modo observação** (`strict_real_path=False`): deteta+marca (`metadata.evidence`/`evidence_reason`) + emite `simulated_total` SEMPRE, mas só FALHA o ticket quando `strict_real_path=True`. O enforcement (True) será ligado **por ambiente após os caminhos reais estarem entregues** (Tasks 4/5/7/8 — senão build/deploy/transform simulados/no-op quebrariam o E2E em prod hoje). Os validadores já cobrem os 7 task_types do contrato §4, prontos para o enforcement.
  - [x] 1.1 Testes: simulated/noop/evidência-ausente → não-COMPLETED; real → COMPLETED (27 testes)
  - [x] 1.2 Settings `strict_real_path` + métrica `simulated_total{executor,task_type}`
  - [x] 1.3 Gate de evidência por task_type (`_has_real_evidence`+`_enforce_evidence_gate`, execution_engine.py) — query/transform/validate/build(+digest)/deploy/execute/generate_code
  - [x] 1.4 Testes verdes (34 com regressão; pipeline dev→auditoria qualidade→auditoria completude→remediação: C1 Redis GET, C2 CSV transform, build-digest, helper extraído)

- [x] 2. Reativar specialists ML em produção (stage + embeddings) ✅
  - **DoR:** modelos `<domain>-evaluator` localizados no MLflow (stage atual); base image confirma `sentence-transformers`.
  - **DoD:** opinions com `model_source=ml_model` e `method=shap`; 0 features de embedding a zero; specialists não caem em heurística com a config de prod.
  - **DECISÃO (stage):** Opção A — promover `<domain>-evaluator` Staging→Production no MLflow (semântica correta) via script versionado idempotente, em vez de apontar helm para Staging (smell). Ação de estado EXECUTADA pelo orquestrador.
  - **EVIDÊNCIA REAL:** registry confirma 5 evaluators em Production (technical/architecture/behavior v13, business/evolution v14), 5 mocks `<domain>` arquivados. `mlflow.pyfunc.load_model('models:/business-evaluator/Production')` → `RandomForestClassifier` (caminho `ml_model`, antes dava NotFound→heurística). Embeddings no pod não-zero (`mean_norm=3.62`, `sentence-transformers 3.3.1` presente — comentário `values.yaml:68` "removido" está desatualizado: base image reconstruída com libs ML na sessão SHAP).
  - **ACHADO/FIX:** `ontology_mapper` testava truthiness do objeto (`if self.embeddings_generator:`) em vez de `.model is not None` → degradação silenciosa de embeddings; corrigido com `_embeddings_available()` + `feature_degraded` + métrica `degradation_total{component,reason}` (§5.4).
  - [x] 2.1 Testes: specialist resolve `-evaluator` real por stage; stage sem modelo → fallback marcado (`test_model_stage_resolution.py`, 3 testes)
  - [x] 2.2 Stage alinhado via promoção MLflow (script `scripts/mlflow/promote_specialists.py`, executado `--apply`); helm prod (`Production`) passa a resolver os modelos reais
  - [x] 2.3 `sentence-transformers==3.3.1` confirmado na base image; fix da degradação silenciosa de embeddings + 6 testes (`test_embeddings_degradation.py`)
  - [x] 2.4 Validado no cluster: resolução Production→RandomForest; regressão 284 passed/0 failed; embeddings não-zero

- [x] 3. Reativar NER/embeddings reais no STE (dependências) ✅
  - **DoR:** Dockerfile do STE e requirements localizados; modelos spaCy alvo identificados (`pt_core_news_sm`).
  - **DoD:** `nlp_processor.is_ready()==True`; entidades limpas (sem artigos/vírgulas) e `subject` correto (não `entities[0]`), verificado num plano real.
  - **EVIDÊNCIA REAL:** pipeline real (spaCy real + decomposition + classifier) sobre `"Migrar a infraestrutura SAP para a cloud AWS"` → `is_ready()=True`; 4 entidades NER **sem nenhuma suja** (`Migrar`, `SAP`, `AWS`, `cloud AWS` — sem artigos/pontuação); `subject='infraestrutura SAP'` LIMPO (≠ `entities[0]`=`'Migrar'` cru); plano real com 6 TaskNodes com subject/target limpos nas descrições. Pod do cluster `semantic-translation-engine-*` já tem `spacy 3.7.5` (transitivo dos tarballs dos modelos) → NER real já disponível em runtime; o fix comportamental (cleaning+subject+instrumentação) entra com o rebuild via CI no push.
  - **ACHADO/FIX (auditoria):** (a) `clean_entity_value` apagava siglas ALL-CAPS (`OS`/`AS`/`A`/`DB`) por comparar `.lower()` → corrigido com `tokens[0].islower()`; (b) `decomposition_templates.py:745` `subject = entities[0]` cru → primeira entidade LIMPA não-vazia; (c) degradação instrumentada com `degradation_total{component,reason}` (§5.4) em `nlp_processor` (not_initialized/initialize_failed), `intent_classifier` (embeddings_unavailable) e fallback posicional do decomposition (positional_subject_fallback); (d) `_entity_text` coage dict→str defensivamente.
  - **DECISÃO (deps):** `spacy==3.7.0` em `requirements.txt` (torna explícita a dep antes implícita; alinha com modelos 3.7.x do Dockerfile). `sentence-transformers`/`torch` deixados OPCIONAIS (comentados) — DoD não exige embeddings ativos, só que a ausência seja MARCADA; evita ~2GB de torch como hard dep.
  - [x] 3.1 Testes: is_ready true; NER extrai entidades nomeadas limpas (18 testes em `test_ste_real_path_task3.py`)
  - [x] 3.2 `spacy==3.7.0` em requirements + modelos baixados (Dockerfile já baixa `pt_core_news_sm-3.7.0`/`en_core_web_sm-3.7.1`)
  - [x] 3.3 `sentence-transformers`+`torch` opcional (comentados); fallback marcado via `degradation_total` + log `degraded=true`
  - [x] 3.4 Validado em plano real (decomposition local com spaCy real); cluster já tem spaСy — E2E A→C6 completo fica pendente do rollout da nova imagem (CI no push)

- [x] 4. Code Forge — build real verificável ✅ (digest provado por skopeo inspect)
  - **DoR:** `ghcr-secret` confirmado em `docker-build` (existe, 134d) ✅; `OCI_REGISTRY_URL=ghcr.io/albinojimy/neural-hive-mind`; code-forge deploy localizado (0/0).
  - **DoD:** build produz `{registry}/{artifact}:{version}` com digest confirmável por `skopeo inspect`; sem code-forge → ticket FAILED (nunca `stub://`).
  - **EVIDÊNCIA REAL (cluster):** build Kaniko real executado no cluster → `Pushed ghcr.io/albinojimy/neural-hive-mind/cr4-smoke@sha256:6b5a613a...`; **`skopeo inspect docker://.../cr4-smoke:v1` → `@sha256:6b5a613aa78d17afdf229f004d4f29fbc4790d1b79b51592cf3646fd941591b7`, Created 2026-06-20 21:36** (imagem realmente pullable no GHCR). Os `kaniko_args` confirmam `--destination={registry}/{artifact}:{version}` + `--digest-file`. Caminho real provado end-to-end: ContainerBuilder(KANIKO) → pod Kaniko Gatekeeper-compliant → push GHCR → digest verificável.
  - **RESSURREIÇÃO do code-forge (0/0 há 161d = rot pré-existente):** para o build real correr foi preciso (commits): GitPython+kubernetes+asyncpg em falta no `requirements.txt` (nunca populado); parser de digest a apanhar "Pushed @sha256". E infra IMPERATIVA no cluster (documentar p/ helm-ificar): `REDIS_PASSWORD=nhm_redis_2026` (RedisCluster exige auth); CPU limit 2200m→2000m + requests 250m/640Mi (Gatekeeper + over-commit); Role+RoleBinding `code-forge-kaniko` em `docker-build` (configmaps/pods/pods-log/pods-exec); `ghcr-secret@docker-build` repontado para o token com `write:packages`; labels+resource-limits no pod Kaniko (Gatekeeper). **NOTA:** redis_client do code-forge usa modo standalone contra RedisCluster (MOVED) → a API de pipeline-state degrada; o build foi provado exercitando o ContainerBuilder diretamente (ortogonal a esse rot).
  - **ACHADO/FIX (auditoria):** corrigidos 2 bugs CRÍTICOS pré-existentes no caminho de build do code-forge: (a) `pipeline_engine._prepare_build_workspace` chamava `_extract_generated_code` **sem `await`** (coroutine nunca executada → workspace sempre com código default); (b) `container_builder` tinha `elif phase == "Failed"` **duplicado** → pod falhado nunca retornava (bloqueava até timeout de horas). Sem estes fixes o build real nunca convergiria.
  - **EVIDÊNCIA (código):** `grep stub:// services/worker-agents/src` → 0 ocorrências (stub REMOVIDO, não marcado). BuildExecutor produz `output.artifact`={registry}/{nome}:{version} + `output.digest`=sha256: que satisfazem `_evidence_build` da Task 1. Sem forge / forge a falhar / pipeline sem digest → `success=False` + `real_path_unavailable_total`. 13 testes novos verdes + 3 testes de contrato obsoletos (stub) atualizados ao contrato real.
  - [x] 4.1 Testes: build → digest real; sem forge → FAILED (5 worker + 8 code-forge)
  - [x] 4.2 (código) montar `ghcr-secret` no pod Kaniko (`/kaniko/.docker`, `KANIKO_DOCKER_CONFIG_SECRET`); escalar code-forge ≥1 → INFRA (Fase D)
  - [x] 4.3 `OCI_REGISTRY_URL` (helm) + `--destination` com registry (`build_image_reference`); devolver digest+URI ao worker
  - [x] 4.4 Remover fallback `stub://artifact` ✅; validar com `skopeo inspect` → E2E pendente (nova imagem code-forge + build real na Fase D)

- [x] 5. Fluxo G — wiring da geração de código ✅ (code_artifact_id persistido provado por consulta)
  - **DoR:** as 10 activities G6-G13 localizadas e confirmadas implementadas (não stubs); porta real do code-forge (8080) confirmada.
  - **DoD:** plano `generation` executa sem ActivityNotRegistered; `generate_code` devolve `code_artifact_id` persistido em MongoDB, confirmado por consulta.
  - **EVIDÊNCIA REAL (cluster):** orchestrator (imagem 2d94515) arranca 2/2 Running, worker Temporal inicializado **sem ActivityNotRegistered** (12 G6-G13 registadas; interseção `invocadas-no-FluxoGWorkflow ⊆ registadas = ∅`). `_persist_code_artifact` → MongoDB real `neural_hive_orchestration.code_artifacts`; `find_one({code_artifact_id})` devolveu o documento `{code_artifact_id: cr5-proof-artifact-001, language: python, framework: fastapi, generation_method: code_forge, status: completed, ...}`. DoD satisfeita por consulta real.
  - **ACHADO/FIX (auditoria):** bug colateral — `build_package`/`deploy` faziam `from .code_generation_activity import _http_client` capturando `None` no import (antes da injeção); corrigido p/ leitura dinâmica via módulo. Honestidade §5.4: `collect_post_deployment_metrics`/`record_feedback_for_ml` devolviam dados simulados sem marcação → marcados `simulated=True`+log degraded (persistência ML real fica p/ Task 12, sem verde-falso). `get_engineering_service`→503; http client None→log degraded; 8020 residual em `code_forge_client`→8080.
  - [x] 5.1 Testes: worker regista G6-G13; generation não dá ActivityNotRegistered (8 testes AST + persistência + fail-safe + porta)
  - [x] 5.2 Registar G6-G13 (`temporal_worker.py`) + `set_code_generation_dependencies(http_client, mongodb_client)` chamada no worker
  - [x] 5.3 Porta 8020→8080 configurável (`_code_forge_base_url()`, env `CODE_FORGE_URL`)
  - [x] 5.4 Endpoint G1 `POST /requirements/from-plan` (JSON body) alinhado com o payload de `fluxo_g_integration.py`
  - [x] 5.5 Verificado no cluster: `code_artifact_id` persistido em `code_artifacts`, confirmado por `find_one`

### Balde B — Médio

- [x] 6. Validação real por domínio (OPA) ✅ (4 políticas avaliam no cluster, provado por query)
  - **DoR:** `security_validation.rego` como template; contrato de `input_data` por domínio definido; ConfigMap do OPA localizada.
  - **DoD:** as 4 políticas avaliam input e devolvem allow/violations (decisão com `result`); validate de architecture/quality/perf/operational deixa de ser `policy_undefined`; SAST timeout → FAILED.
  - **EVIDÊNCIA REAL (cluster):** ConfigMap `opa-policies` atualizado (6→10 `.rego`) + OPA reiniciado. Query ao OPA (`/v1/data/neural_hive/<domain>`) com input `{is_destructive:true, security_level:internal, risk_band:critical}` → architecture/compliance `allow=False violations=1`, quality/standards `allow=True violations=0`, performance/limits `allow=False violations=1`, operational/procedures `allow=False violations=2` — **todas devolvem `result`, nenhuma `policy_undefined`**.
  - **ACHADO/FIX (auditoria):** (a) BUG CRÍTICO de deploy — `.Files.Get` resolve relativo ao chart, não à raiz; as 4 `.rego` foram copiadas para `helm-charts/orchestrator-dynamic/policies/rego/orchestrator/` (senão o ConfigMap renderia vazio); (b) `_execute_opa_fallback` emitia `simulated=True` p/ OPA-down (falha real, não simulação) → `simulated=False`+`degraded`+`real_path_unavailable_total`; (c) guards `is_number()` nas regras condicionais (null não dispara falso-negativo).
  - [x] 6.1 Testes: 4 políticas avaliam input (9 worker + 20 OPA, 20/20 PASS); timeout SAST → FAILED
  - [x] 6.2 Criar 4 `.rego` + montar na ConfigMap (raiz + cópia no chart) — aplicado no cluster
  - [x] 6.3 `policy_undefined` fail-open só p/ domínios sem política exigida (`opa_required_policy_prefixes`; exigido→fail-closed)
  - [x] 6.4 Validate fail-closed: SAST timeout/error→FAILED, fallback simulado genérico REMOVIDO (sem `success=True` simulado)
  - [x] 6.5 Verificado no cluster: OPA avalia as 4 políticas (query devolve allow/violations, não policy_undefined)

- [x] 7. Transform real (data-flow semântico do STE) ✅
  - **DoR:** confirmado que `_inject_dependency_outputs` injeta `dependency_outputs`; formato dos outputs de query/transform conhecido.
  - **DoD:** task transform com dependência aplica `operations` sobre o campo referido por `input_ref`; `output.noop != True`, confirmado num plano real.
  - **ACHADO/FIX (auditoria — BUG CRÍTICO de produção):** o `execution_engine` pré-injeta o ENVELOPE `{documents, count}` em `input_data`; o `_resolve_json_input` short-circuitava (ignorava `input_ref`) e `_count` contava as 2 chaves do envelope → `count=2` SEMPRE (verde-falso numérico). Fix: `input_ref` tem PRECEDÊNCIA (navega até `documents`); `_unwrap_envelope` + `_count` defensivo (conta documentos/results, não chaves); lista vazia resolvida = dado real (count=0), não no-op. Teste de produção (`test_caminho_producao_envelope_em_input_data_conta_documentos`) replica a injeção do engine: 50 docs → count=50 (não 2).
  - **EVIDÊNCIA REAL (cluster):** worker imagem `f59109a` deployada; prova in-pod com ticket que replica a injeção do engine (envelope `{documents:[42 docs], count:42}` em `input_data` + `input_ref` + `dependency_outputs`) → `transformed_data={'count': 42}` (42 docs reais, NÃO 2 chaves), `noop=None`, `success=True`. Fail-fast: `input_ref` sem `dependency_outputs` → `success=False`, `real_path_unavailable=True`. 15 testes unitários verdes.
  - [x] 7.1 Testes: transform com dependência resolve `input_ref` e aplica `operations` (não no-op)
  - [x] 7.2 STE gera `operations` + `input_ref` por task downstream (só com dependências)
  - [x] 7.3 Executor resolve `input_ref` contra `dependency_outputs` (precedência sobre o envelope)
  - [x] 7.4 Verificado no cluster (worker f59109a): envelope→count=42 docs reais; input_ref não resolve→FAILED marcado

- [x] 8. Deploy real + ambiente efémero (imperativo) ✅ (deploy reconciliado provado no cluster)
  - **DoR:** quota de memória do cluster avaliada (over-commit conhecido); param `namespace` do deploy_executor confirmado.
  - **DoD:** deploy via caminho imperativo devolve evidência de reconciliação num namespace efémero (dev); sem provider → FAILED; cleanup do namespace por TTL.
  - **DIVERGÊNCIA (documentada):** caminho imperativo via **cliente `kubernetes_asyncio`** (cria Deployment + espera `available_replicas`) em vez de `helm subprocess` — o worker não tem binários helm/kubectl; evidência de reconciliação equivalente (status do Deployment) e segue o padrão do `flux_client`.
  - **EVIDÊNCIA REAL (cluster):** `deploy_executor._execute_imperative` correu contra o cluster → criou namespace efémero `cr-deploy-cr8proof` (labels TTL `ephemeral=true`/`ttl-seconds=1800`/`created-at=epoch`), ResourceQuota `cr-ephemeral-quota`, Deployment `cr8-pause` **ready=1/1 available=1**; output `{resource:"ns/name", status:"reconciled", healthy:True, available_replicas:1}` (satisfaz `_evidence_deploy`). Confirmado por `kubectl` independente; cleanup OK. RBAC `worker-agents-imperative-deploy` (ClusterRole+Binding) criada → worker SA pode criar namespaces/deployments (`can-i`=yes).
  - **ACHADO/FIX (auditoria — 3 bugs):** (a) ApiClient não fechado → `close()`; (b) 409 AlreadyExists rebentava retry Temporal → `_create_idempotent` tolera; (c) label `created-at` em ISO (`:`/`+`) é VALOR DE LABEL INVÁLIDO (422 no cluster) → epoch seconds. +risco apanhado: teste obsoleto criava namespace REAL (env local admin) → testes isolados com `_init_k8s_clients` a levantar.
  - [x] 8.1 Testes: deploy real devolve evidência; sem provider → FAILED (9 novos + 3 contrato atualizados)
  - [x] 8.2 Caminho imperativo verificável; `_execute_simulation` REMOVIDO (0 ocorrências; sem `success=True`+`simulated=True`)
  - [x] 8.3 Namespace efémero + ResourceQuota + TTL labels (cleanup por reaper externo / `cleanup_after`)
  - [x] 8.4 Verificado no cluster: deploy reconciliado (ready 1/1) em namespace efémero; RBAC do worker SA aplicada

- [ ] 9. Preditores ML do orchestrator (treinar e ligar) — ⛔ BLOQUEADA POR DADOS (não-verde honesto)
  - **DoR:** tabela ClickHouse `tickets`/dados de duração disponíveis; Prophet/RandomForest localizados.
  - **DoD:** duration/load usam modelo treinado registado no MLflow; previsões deixam de ser constantes heurísticas, confirmado.
  - **DIAGNÓSTICO (2026-06-21):** os preditores JÁ estão corretamente implementados e wired — `DurationPredictor` (RF, `ml/duration_predictor.py`) auto-treina no `initialize()` (`_ensure_model_trained`) e cai em heurística MARCADA (`confidence=0.3`) quando não há modelo; `LoadPredictor` (Prophet, `neural_hive_ml`) idem. **NÃO há código a corrigir — o gap é AUSÊNCIA DE DADOS REAIS**, a mesma raiz da Task 12: MongoDB `execution_tickets`=1247 mas só **3** com `actual_duration_ms>0` (precisa `ml_min_training_samples=100`); e TODAS as tabelas de séries temporais do ClickHouse (`worker_utilization`, `hourly_ticket_volume`, `daily_worker_stats`, `queue_snapshots`, `telemetry_metrics`) estão **VAZIAS (0 linhas)** → Prophet sem dados. Causa provável (Task 12): conclusão do ticket não persiste `actual_duration_ms`/`completed_at` de forma consistente + ETL telemetria→ClickHouse não popula.
  - **DECISÃO (honestidade §regra-de-ouro):** treinar sobre dados sintéticos/inexistentes e chamá-lo "modelo treinado real" seria verde-falso. **Task 9 NÃO marcada concluída** — depende da Task 12 (pipeline de dados reais) para acumular amostras. Reabrir após a Task 12.
  - [ ] 9.1 Testes: predictors usam modelo treinado quando disponível
  - [ ] 9.2 Treinar+registar duration (RF) e load (Prophet central); ligar ao pipeline — BLOQUEADO (sem dados)
  - [ ] 9.3 Verificar previsões não-constantes — BLOQUEADO (sem dados)

### Balde C — Épicos genuínos (GRANDE)

- [ ] 10. Classificador NLU de domínio (ML de raiz)
  - **DoR:** dataset rotulado texto→domínio disponível (ou plano de anotação aprovado); abordagem de modelo escolhida.
  - **DoD:** `_classify_domain` usa inferência ML registada no MLflow; confidence honesta + `classification_method`; domínio `UNKNOWN` para fora-de-vocabulário; keyword só como fallback marcado.
  - [ ] 10.1 Dataset rotulado + domínio `UNKNOWN` no enum
  - [ ] 10.2 Treinar classificador (TF-IDF/spaCy/BERTimbau-PT); registar no MLflow
  - [ ] 10.3 Substituir `_classify_domain` por inferência ML (keyword fallback marcado)
  - [ ] 10.4 Gateway: domínio não-mapeado → `requires_manual_validation`

- [ ] 11. GitOps completo (deploy declarativo)
  - **DoR:** decisão ArgoCD vs Flux; repo GitOps e Secret de token preparados; `kubernetes-asyncio` para flux.
  - **DoD:** deploy resulta em App `Synced/Healthy` reconciliável, confirmado por `kubectl get applications`.
  - [ ] 11.1 Instalar ArgoCD/Flux + AppProject + repo + Secret
  - [ ] 11.2 Ligar `argocd_enabled=True`; deploy_executor usa caminho declarativo
  - [ ] 11.3 Verificar App Synced/Healthy

- [ ] 12. Pipeline de dados reais (sair do sintético) — DIAGNÓSTICO root-cause (2026-06-21)
  - **DoR:** `RealDataCollector` localizado (`ml_pipelines/training/real_data_collector.py`); volume de feedback em MongoDB avaliado.
  - **DoD:** modelos re-treinados com ≥1000 amostras reais/specialist; métricas de qualidade (f1) melhoram vs sintético, registado no MLflow.
  - **DIAGNÓSTICO (root-cause da escassez de dados, partilhado com a Task 9):**
    1. **Duração não chega ao Mongo:** o worker COMPUTA e reporta `actual_duration_ms` (`worker-agents/clients/kafka_result_producer.py:97`, `execution_ticket_client.py:95`) → vai para Kafka `execution.results` + execution-ticket-service (**PostgreSQL**). MAS o `ExecutionResultConsumer` (orchestrator) só envia **signal Temporal** (`ticket_completed`) — **não persiste `actual_duration_ms`/`completed_at` no MongoDB `execution_tickets`** (criado com `None` em `ticket_generation.py:260`). O `DurationPredictor` lê MongoDB → vê `None`. Resultado: 3/1247 tickets com duração. **Há DOIS stores divergentes (Postgres no ticket-service; Mongo no orchestrator) e a duração só vai ao Postgres.**
    2. **ClickHouse vazio:** todas as tabelas de séries temporais (`worker_utilization`, `hourly_ticket_volume`, `daily_worker_stats`, `queue_snapshots`, `telemetry_metrics`) têm 0 linhas → o ETL telemetria→ClickHouse não está a popular → Prophet (load) e o caminho ClickHouse do RF sem dados.
  - **FIX FUNDACIONAL #1 ENTREGUE ✅ (commit ad3b4290):** o `ExecutionResultConsumer` passa a persistir `actual_duration_ms`+`completed_at`+`started_at` no MongoDB `execution_tickets` quando o resultado do worker chega (`_persist_duration`, fail-open, só status terminal, cast Int64). **PROVADO no cluster** (orchestrator ad3b429): ticket real `594adcd5` `actual_duration_ms` None→4242 (revertido após prova); de agora em diante cada conclusão real persiste a duração → dados acumulam para o DurationPredictor (desbloqueia a Task 9). 5 testes novos verdes.
  - **DESCOBERTA DECISIVA (2026-06-21): os dados de re-treino dos specialists JÁ EXISTEM** — não na DB do orchestrator (`neural_hive_orchestration`) mas em **`neural_hive`**: `specialist_opinions`=8291, `specialist_feedback`=2482. Por specialist: architecture 1686, behavior 1656, business 1658, evolution 1601, technical 1690 → **todos >1600 (>DoD 1000)**. O `ml_pipelines/training/retrain_simple.py` (RealDataCollector) **já aponta a `mongodb_database="neural_hive"`** + regista no MLflow. **A Task 12 (specialists) está RUNNABLE com dados reais confirmados** — falta executar a pipeline de re-treino (collect→train→register→comparar f1 vs sintético) por specialist, num esforço dedicado.
  - **FIX FUNDACIONAL #2 (ETL→ClickHouse) — DIAGNÓSTICO:** o CronJob `memory-layer-api-sync-mongodb-clickhouse` (cada 6h) FALHA com `"Command find requires authentication"` (Mongo Unauthorized) — conecta-se sem credenciais → 0 documentos sincronizados. MAS as coleções-fonte time-series (`worker_utilization`, `telemetry_metrics`, `execution_logs`, `scheduling_decisions`) estão **vazias em TODAS as DBs** → a telemetria não está a ser produzida/persistida (gap a montante, separado do bug de auth). Fixar a auth do ETL é necessário mas não-suficiente para o Prophet/load enquanto a telemetria não for produzida.
  - **POC de re-treino EXECUTADO (technical, 1690 opinions) — revelou a cadeia COMPLETA de blockers:**
    1. ✅ Opinions: 1690 encontradas.
    2. ✅ Feedback: **bug encontrado e corrigido** — `RealDataCollector` lia a coleção `feedback` (0 docs) em vez de `specialist_feedback` (2482); default corrigido (commit). Com o fix: `coverage_rate=28.8%` → **486 opinions com feedback (>400 mínimo)** — dados rotulados suficientes EXISTEM.
    3. ❌ **BLOCKER FINAL — GDPR masking:** a extração de features falha em **100%** das 486 (`'NoneType'.lower()`) porque os `specialist_opinions` estão **mascarados por privacidade** — NÃO têm campo de texto (`cognitive_plan`/`intent_text`); só `opinion`, IDs encriptados (`intent_id`/`trace_id` = `enc:...`) e marcadores GDPR (`masked_fields`, `content_hash`, `gdpr_consent`, `digital_signature`, `retention_policy`). O texto que o `FeatureExtractor` precisa foi removido.
  - **DESBLOQUEIO + TREINO REAL EXECUTADO (com consentimento, via features não-PII):** a tensão privacidade-vs-ML resolveu-se **sem desmascarar texto** — a coleção `neural_hive.plan_features` tem as **features já extraídas, agregadas e não-PII** (`metadata/ontology/graph/embedding/aggregated_features`, JSON) por `plan_id`, cobrindo **642/644** das opinions technical. Treino real: juntar opinion→`plan_features`(features)→`specialist_feedback`(label=`human_recommendation`) → **485 amostras reais** (approve 89, review_required 317, reject 79). RandomForest treinado in-cluster (orchestrator pod: sklearn+pandas+mlflow). **RESULTADO: f1=0.5115, accuracy=0.6495 (dados reais).**
  - **COMPARAÇÃO HONESTA vs sintético (DoD):** sintético v13 (Production, Task 2) f1_weighted=**0.6348**; v8 f1=**0.995** (overfit). **O f1 REAL (0.5115) é MAIS BAIXO que o sintético (0.6348)** → o DoD literal ("f1 melhora") NÃO é cumprido, MAS é a verdade: o f1 sintético estava **otimista** (overfit a labels limpos/balanceados); o real reflete labels humanos desbalanceados (review_required=65%) e ruidosos. **Verde sintético parcialmente falso confirmado** — espírito da spec.
  - **BALANCEAMENTO TESTADO (class_weight=balanced):** f1_weighted 0.5115→**0.2138**, f1_MACRO=**0.2499**, accuracy 0.6495→0.2577. **Balancear PIOROU** → revela que o modelo sem balanceamento apenas **previa a maioria** (review_required=65%); com pesos balanceados as `plan_features` **não discriminam** a `human_recommendation` (macro f1≈0.25, acaso para 3 classes). per-class: review_required precision 0.86/recall 0.10 (sinal fraco mas existente). **CONCLUSÃO: não é problema de hiperparâmetros — é SINAL features→label fraco.** O `human_recommendation` depende do conteúdo/qualidade da opinião e do julgamento humano, não da estrutura do plano (que é o que `plan_features` captura). O f1 sintético (0.6348) era aprendível porque o mapping sintético foi gerado; o real revela que a tarefa do evaluator tem sinal fraco nas features estruturais.
  - **TARGET BINÁRIO TESTADO ("opinião correta?" = opinion_rec==human_rec):** naturalmente balanceado (incorrect 213 / correct 273) mas f1_weighted=**0.4558**, f1_macro=**0.4368**, accuracy=**0.4796** ≈ **ACASO** (binário balanceado). 
  - **CONCLUSÃO DEFINITIVA (3 formulações testadas — multiclasse 0.51 majority-bias, balanceado 0.25, binário 0.44):** as `plan_features` (estrutura do plano: num_tasks/risk/complexity/...) **NÃO têm sinal preditivo** para a recomendação/correção humana — performance ≈ acaso em todas as formulações. As features que predizeriam (conteúdo semântico/raciocínio da opinião, texto da intenção) estão **mascaradas por privacidade OU não capturadas** em `plan_features`. O f1 sintético (0.6348) era **inflado** (mapping sintético aprendível). **Não há modelo real útil a registar com as features disponíveis.** 
  - **NOTAS:** (a) BUG corrigido: `RealDataCollector` default `FEEDBACK_COLLECTION` `feedback`(vazio)→`specialist_feedback`. (b) Registo MLflow falhou por mismatch de API (`logged-models` client 3.14 vs server antigo). (c) **Caminho real para fechar a Task 12 (data/feature-engineering, esforço dedicado):** capturar features que reflitam o conteúdo/raciocínio da opinião (embeddings do texto da intenção/plano, com decisão de privacidade) — sem isso, nenhum tuning/balanceamento produz um evaluator real útil. O active learning (já existe) ajuda na distribuição de labels mas não no sinal das features. (d) infra: port-forward a pods Mongo bloqueado por istio mTLS → correr in-cluster.
  - **PENDENTE (Task 12 mantém-se aberta):** (a) resolver o mascaramento GDPR p/ features (decisão de governance); (b) fix auth do ETL `sync-mongodb-clickhouse` + produção de telemetria→ClickHouse (Prophet/load); (c) ativar `RealDataCollector` em contínuo.
  - [ ] 12.1 Ativar `RealDataCollector` (opinions/feedback Mongo; intentions.audit Kafka)
  - [ ] 12.2 Acumular ≥1000 amostras/specialist; re-treinar com dados reais
  - [ ] 12.3 Feature store real ou serving mínimo de features
  - [ ] 12.1 Ativar `RealDataCollector` (opinions/feedback Mongo; intentions.audit Kafka)
  - [ ] 12.2 Acumular ≥1000 amostras/specialist; re-treinar com dados reais
  - [ ] 12.3 Feature store real ou serving mínimo de features
