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

## BUILD KANIKO PROVADO (não eram recursos — era PUSH/credenciais)

> Correcção: a hipótese inicial de "pressão de recursos" estava **errada**. Os pods Kaniko eram
> criados no namespace **`docker-build`** (não `neural-hive`) — por isso não apareciam em
> `kubectl -n neural-hive get pods`. **Agendam e correm sem problema de recursos.**

**O build Kaniko REAL teve SUCESSO** (com `push_to_registry=False` → `--no-push`):
- Pod `kaniko-b13953d1` (namespace `docker-build`): **phase = Succeeded**.
- Logs do Kaniko mostram o **build completo da imagem FastAPI** a partir do código gerado:
  ```
  RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
  Taking snapshot of full filesystem...
  USER appuser
  HEALTHCHECK --interval=30s ... CMD python -c "...urlopen('http://localhost:8000/health')"
  EXPOSE 8000
  CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
  Skipping push to container registry due to --no-push flag
  ```
- O contexto extraído contém o código gerado real (`Dockerfile`, `main.py`, `requirements.txt`).

Logo: **G7 constrói uma imagem de container REAL via Kaniko** (com `/health`, `EXPOSE 8000`, uvicorn)
a partir do código FastAPI gerado. DoD 5.2 ("build real via Kaniko") **satisfeito**.

## Único bloqueio do publish (5.3): credenciais GHCR (não recursos, não código)
Com `push_to_registry=True`, o Kaniko falha **apenas no push**:
```
error checking push permissions ... checking push permission for
"ghcr.io/albinojimy/neural-hive-mind/...": ... DENIED: requested access to the resource is denied
```
O secret `ghcr-secret` (dockerconfigjson, **139 dias**, user `albinoJimy`, token de 40 chars) está
**expirado ou sem scope `write:packages`**. É um problema de **credenciais/segredos** (como o LLM),
fora do âmbito de código — não se devem fabricar/injectar segredos. Os pods Kaniko com push aparecem
em `kubectl -n docker-build get pods` como `Error` (falha no push, não no build).

## Veredicto
- **G7 build real via Kaniko: PROVADO** — imagem FastAPI construída com sucesso (`Succeeded`).
- **Gate 5.3 (imagem publicada no GHCR + skopeo): NÃO atingido** — bloqueado **só** pelas credenciais
  de push do GHCR (`ghcr-secret` denied). Sem verde falso: a imagem não foi publicada.

## Próximo passo recomendado
Actualizar o secret `ghcr-secret` (namespace `docker-build`) com um PAT GitHub válido com scope
`write:packages` para `albinojimy`. Depois re-correr com `push_to_registry=True` → a imagem é
publicada no GHCR e o gate 5.3 fecha (skopeo inspect do digest). O build já está provado; falta
apenas a credencial de push.
