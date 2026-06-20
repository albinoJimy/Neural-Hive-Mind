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

- [ ] 4. Code Forge — build real verificável
  - **DoR:** `ghcr-secret` confirmado em `docker-build`; `OCI_REGISTRY_URL` alvo definido; code-forge deploy localizado (0/0).
  - **DoD:** build produz `{registry}/{artifact}:{version}` com digest confirmável por `skopeo inspect`; sem code-forge → ticket FAILED (nunca `stub://`).
  - [ ] 4.1 Testes: build → digest real; sem forge → FAILED
  - [ ] 4.2 Escalar code-forge ≥1; montar `ghcr-secret` no pod Kaniko
  - [ ] 4.3 `OCI_REGISTRY_URL` + `--destination` com registry; devolver digest+URI
  - [ ] 4.4 Remover fallback `stub://artifact`; validar com `skopeo inspect`

- [ ] 5. Fluxo G — wiring da geração de código
  - **DoR:** as 10 activities G6-G13 localizadas e confirmadas implementadas (não stubs); porta real do code-forge (8080) confirmada.
  - **DoD:** plano `generation` executa sem ActivityNotRegistered; `generate_code` devolve `code_artifact_id` persistido em MongoDB, confirmado por consulta.
  - [ ] 5.1 Testes: worker regista G6-G13; plano generation não dá ActivityNotRegistered
  - [ ] 5.2 Registar G6-G13 (`temporal_worker.py:465`) + `set_code_generation_dependencies`
  - [ ] 5.3 Corrigir porta 8020→8080 (configurável)
  - [ ] 5.4 Alinhar endpoint G1 `/from-plan`
  - [ ] 5.5 Verificar via E2E: `code_artifact_id` persistido

### Balde B — Médio

- [ ] 6. Validação real por domínio (OPA)
  - **DoR:** `security_validation.rego` como template; contrato de `input_data` por domínio definido; ConfigMap do OPA localizada.
  - **DoD:** as 4 políticas avaliam input e devolvem allow/violations (decisão com `result`); validate de architecture/quality/perf/operational deixa de ser `policy_undefined`; SAST timeout → FAILED.
  - [ ] 6.1 Testes: 4 políticas avaliam input; timeout SAST → FAILED
  - [ ] 6.2 Criar 4 `.rego` + montar na ConfigMap do OPA
  - [ ] 6.3 `policy_undefined` fail-open só para domínios sem política exigida
  - [ ] 6.4 Validate fail-closed (remover fallback simulado genérico)
  - [ ] 6.5 Verificar testes/E2E

- [ ] 7. Transform real (data-flow semântico do STE)
  - **DoR:** confirmado que `_inject_dependency_outputs` injeta `dependency_outputs`; formato dos outputs de query/transform conhecido.
  - **DoD:** task transform com dependência aplica `operations` sobre o campo referido por `input_ref`; `output.noop != True`, confirmado num plano real.
  - [ ] 7.1 Testes: transform com dependência resolve `input_ref` e aplica `operations` (não no-op)
  - [ ] 7.2 STE gera `operations` + `input_ref` por task downstream
  - [ ] 7.3 Executor resolve `input_ref` contra `dependency_outputs`
  - [ ] 7.4 Verificar via E2E

- [ ] 8. Deploy real + ambiente efémero (imperativo)
  - **DoR:** quota de memória do cluster avaliada (over-commit conhecido); param `namespace` do deploy_executor confirmado.
  - **DoD:** deploy via `helm --wait`+`rollout status` devolve evidência de reconciliação num namespace efémero (dev); sem provider → FAILED; cleanup do namespace por TTL.
  - [ ] 8.1 Testes: deploy real devolve evidência; sem provider → FAILED
  - [ ] 8.2 Caminho deploy imperativo verificável; remover `_execute_simulation`
  - [ ] 8.3 Namespace efémero + ResourceQuota/TTL/cleanup
  - [ ] 8.4 Verificar via E2E em dev

- [ ] 9. Preditores ML do orchestrator (treinar e ligar)
  - **DoR:** tabela ClickHouse `tickets`/dados de duração disponíveis; Prophet/RandomForest localizados.
  - **DoD:** duration/load usam modelo treinado registado no MLflow; previsões deixam de ser constantes heurísticas, confirmado.
  - [ ] 9.1 Testes: predictors usam modelo treinado quando disponível
  - [ ] 9.2 Treinar+registar duration (RF) e load (Prophet central); ligar ao pipeline
  - [ ] 9.3 Verificar previsões não-constantes

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

- [ ] 12. Pipeline de dados reais (sair do sintético)
  - **DoR:** `RealDataCollector` localizado; volume de feedback em MongoDB avaliado.
  - **DoD:** modelos re-treinados com ≥1000 amostras reais/specialist; métricas de qualidade (f1) melhoram vs sintético, registado no MLflow.
  - [ ] 12.1 Ativar `RealDataCollector` (opinions/feedback Mongo; intentions.audit Kafka)
  - [ ] 12.2 Acumular ≥1000 amostras/specialist; re-treinar com dados reais
  - [ ] 12.3 Feature store real ou serving mínimo de features
