# Fase 5 — G8: deploy real + E2E (Evidência)

> Spec: Endurecer J3/BUILD (capacidade GENERATE) — pré-condição ADR-0011
> Task 6 — Deploy real do software gerado + prova E2E
> Data: 2026-06-25 · Branch: `feat/convergencia-dbs` · Cluster: `neural-hive`

## Estado: GATE "J3/BUILD fiável" ESTABELECIDO — software gerado real a correr

Uma **intenção de geração** (FastAPI, TEMPLATE, sem LLM) percorre o FluxoG ponta-a-ponta e
produz **software real a correr** no cluster: **generate → build → push → deploy → healthcheck**.

## Prova em cluster (E2E final)

- **Plano**: `52a083d8-1ac3-49d2-b92e-2129bba4371f` · journey `J3_BUILD` · workflow `orch-flow-c-j3-e2e-1782407725` (FluxoGWorkflow, routing_basis=journey)
- **G6** geração: `code_artifact_id` persistido em `code_artifacts` (framework=fastapi, generation_method=TEMPLATE, sem LLM)
- **G7** build: `build_package_completed` status=completed quality_score=0.8 → **imagem publicada no GHCR** `ghcr.io/albinojimy/neural-hive-mind/service-52a083d8-…:1.0.0` (Kaniko `--destination`, push real)
- **G8** deploy: `deploy_software_completed` status=**deployed** → `service-52a083d8-….svc.cluster.local:80`
- **Deployment `1/1` READY**, pod `Running` (0 restarts)
- **Healthcheck**: `/health`, `/health/live`, `/health/ready` → **HTTP 200** (in-pod, porta 8080)
- **Labels Gatekeeper** presentes no pod: `app` + `app.kubernetes.io/name`
- **code_artifact** com `journey=J3_BUILD` (propagação adicionada)

## Defeitos REAIS corrigidos para fechar G7→G8 (todos provados por E2E)

### deploy-service (G8)
1. **`ImportError: AsyncLoggingMiddleware`** — `main.py` usava API antiga de `neural_hive_observability`; substituído por `init_observability` (commit 2cd2841).
2. **Labels Gatekeeper** ausentes no Deployment/pod/Service gerados (`must-have-app-label-all` negaria os pods) → add `app.kubernetes.io/name` (42ff887).
3. **`imagePullSecrets` + réplica do `ghcr-secret`** no namespace alvo — sem isso o pod não puxa a imagem privada (ImagePullBackOff) (9172ea9).
4. **Healthcheck verde-falso** — `_verify_health_checks` filtrava por `app={deployment_name}` (não existe) → `0==0`=HEALTHY; corrige selector para `app=service_name` + exige `total_pods>0` (0e3e827).
5. **`--timeout={timeout}s` literal** (sem f-string) → `kubectl rollout status` falhava com `invalid duration "{timeout}s"` (32cb97a).

### code-forge (G6/G7)
6. **Template FastAPI** expõe `/health/live` + `/health/ready` e escuta em **8080** (contrato do deploy-service: containerPort/probes fixos em 8080) (01989ff, 1b64fba).
7. **Label do pod Kaniko >63 chars** (`build`=image_tag completo) → admission 422; clamp para sufixo único ≤63 (90cf6ed).
8. **SBOM/assinatura abortavam o pipeline** (Syft recebe `mongodb://…` como imagem) → best-effort (6eb6c61).
9. **`Object of type datetime is not JSON serializable`** (Redis `_serialize_value` + colunas JSON do SQLAlchemy) → `default=str` + `json_serializer`; `save_pipeline`/`publish_result` best-effort (e744870, 6eb6c61).
10. **`container_image` nunca exposto** no estado/GET — guardado só em `context.metadata` → G8 abortava com "container_image não encontrado"; propaga `container_image_ref` (digest-pinned quando disponível) (e744870).
11. **Dockerfile gerado crashava** (`pip --user` em `/root/.local` mas corre como `appuser` → `Permission denied`) → instala no home do appuser com `--chown` (289b0dd).
12. **`KANIKO_CLEANUP_PODS=false`** (env imperativo) — o cleanup apagava o pod Kaniko durante o push (digest-read "container not found"; imagem `NotFound`). **PENDENTE persistir em helm** (ver abaixo).

### orchestrator (G7→G8)
13. **`push_to_registry` default `False`** em `build_package` (G7) → Kaniko corria com `--no-push` → a imagem nunca chegava ao GHCR → `ImagePullBackOff/NotFound`. Para J3_BUILD a publicação é obrigatória → default **True** (60b4f4d).
14. **Timeout do POST de deploy**: cliente HTTP injetado tem 60s, mas o deploy-service responde 202 só após o rollout (síncrono) → timeout 1200s por-request (32510f6).
15. **`journey` propagada** para o `code_artifact` (rastreabilidade) (60b4f4d).

## Fora de âmbito (honesto)
- **ExecutionFeedback / loop LEARN para FluxoG**: `record_feedback_for_ml` (G13) constrói o training_example mas a **persistência real está diferida** (caminho-real-first-class §5.4, Task 12). Não é entregável desta spec.
- **Namespace efémero TTL+ResourceQuota**: o deploy-service cria o namespace + Service + Deployment reais; TTL/ResourceQuota não implementados neste caminho (o gate central — software a correr + healthcheck — está provado).
- **`digest=null`** no resultado do Kaniko (leitura de `/kaniko/digest` corre após o container terminar) — cosmético; o deploy usa a tag publicada.

## Patches imperativos a persistir em helm (dívida)
- `code-forge`: `KANIKO_CLEANUP_PODS=false` (env) — necessário para o push do Kaniko concluir.
- Confirmar `push_to_registry` default True no deploy do orchestrator (60b4f4d) torna o plano J3 fiável **por omissão** (sem override).
