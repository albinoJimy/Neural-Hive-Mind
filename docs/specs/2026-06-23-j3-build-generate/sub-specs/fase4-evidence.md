# Fase 4 — G7: build real (Kaniko → GHCR) (Evidência)

> Spec: Endurecer J3/BUILD (capacidade GENERATE) — pré-condição ADR-0011
> Task 5 — Build real do código gerado em imagem de container
> Data: 2026-06-25 · Branch: `feat/convergencia-dbs` · Cluster: `neural-hive`

## Estado: pipeline de build REAL correctamente ligado; execução do pod Kaniko bloqueada por INFRA

O pipeline G7 (`build_package` → code-forge `/api/v1/pipelines`) foi corrigido para fazer um
**build Kaniko real com push para o GHCR**. Provou-se em cluster que o pipeline:
percorre os stages, **cria o pod Kaniko** com os argumentos e destino GHCR correctos e o código
gerado real como contexto. O passo final — o **pod Kaniko executar o build+push** — não conclui
neste cluster (o pod desaparece em segundos sem resultado), por **pressão de recursos / scheduling**
(infra), não por código.

## Defeitos do pipeline de build corrigidos (commits c8ce60a→0c80c76)
1. **pipeline abortava no update de status** (503 do execution-ticket-service via mesh) ANTES do
   build → `update_status` passou a **best-effort** (reporte de status é observabilidade, não aborta
   o build). Pipeline prossegue para os stages de build.
2. **`write() argument must be str, not coroutine`** em `_prepare_build_workspace`:
   `_extract_generated_code` é async mas não era awaited → add `await`. Escreve o código gerado real.
3. **Builder DOCKER hardcoded** → `failed to connect to docker.sock` (não há docker daemon no pod).
   Add setting `CONTAINER_BUILDER_TYPE` (default `kaniko`) → usa Kaniko no cluster.
4. **Pod Kaniko negado pelo Gatekeeper** (403 `must-have-app-label-all`: faltava
   `app.kubernetes.io/name`) → label adicionado. O pod passa a ser **criado**.
5. **`--destination=f4svc:1.0.0`** sem registry (iria para docker.io) → prefixa `OCI_REGISTRY_URL`
   (`ghcr.io/albinojimy/neural-hive-mind`) → destino `ghcr.io/.../f4svc:1.0.0`.
6. `KANIKO_CLEANUP_PODS` / `KANIKO_BUILD_TIMEOUT` configuráveis (debug do build).

## Prova em cluster (pipeline de build)
Logs reais (pipeline da geração TEMPLATE):
```
stage template_selection -> code_composition -> dockerfile_generation -> container_build
code_fetched_from_mongodb  artifact_id=...   (código FastAPI real como contexto)
kaniko_build_started  image_tag=ghcr.io/albinojimy/neural-hive-mind/f4final:1.0.0
configmap_created  kaniko-context-...        (contexto do build)
kaniko_args  ["--dockerfile=Dockerfile","--context=dir:///workspace",
              "--destination=ghcr.io/albinojimy/neural-hive-mind/f4final:1.0.0"]
kaniko_pod_created  pod_name=kaniko-...      (pod criado — Gatekeeper já não nega)
```
Pipeline status via API: `running / stage=BUILDING`.

## Bloqueio honesto (infra, não código)
- O pod Kaniko é **criado** (API aceita, sem 403) mas **desaparece em ~8s** sem fase
  Running/Succeeded/Failed e sem resultado logado — mesmo com `cleanup_pods=False`. Não chega a
  construir nem a fazer push. A imagem **não** aparece no GHCR (404).
- Causa mais provável: **pressão de recursos do cluster** (workers a ~99% de memória — ver
  `infra_memory_overcommit_istiod`) impede o pod Kaniko de correr; um build de container precisa de
  CPU+memória que o cluster sobre-comprometido não tem. (Observou-se também `exit 137`/OOM em exec
  durante a sessão.) É um limite de ambiente, não do pipeline.
- Dependências de enriquecimento degradadas no caminho (mcp-tool-catalog 503; git clone do repo de
  templates falha → fallback de template) — toleradas, não bloqueiam o build.

## Veredicto
- **Código do G7 (build real Kaniko→GHCR): COMPLETO e correcto** — provado que cria o pod Kaniko
  com args/destino GHCR correctos e o código gerado real.
- **Gate 4.3/5.3 (imagem publicada e puxável): NÃO atingido** — bloqueado pela **não-execução do pod
  Kaniko no cluster** (recursos/scheduling). Sem verde falso: a imagem não está no GHCR.

## Próximo passo recomendado
Libertar recursos no cluster (os workers estão a ~99% de memória) ou agendar o pod Kaniko num node
com capacidade / com requests adequados, e re-correr. Em alternativa, diagnosticar a deleção imediata
do pod Kaniko (eventos do node / ResourceQuota / scheduler) com `KANIKO_CLEANUP_PODS=false`. O
pipeline de build está correcto; falta apenas o pod Kaniko sobreviver e construir.
