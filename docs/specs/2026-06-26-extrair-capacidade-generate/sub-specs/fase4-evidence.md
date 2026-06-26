# Fase 4 — Gate de equivalência E2E (zero regressão) · Evidência

> Spec: Extrair GENERATE como capacidade autónoma (multi-linguagem-ready)
> Task 5 — Paridade comportamental: intenção J3 produz software a correr **via a capacidade**
> Data: 2026-06-26 · Branch: `feat/convergencia-dbs` · Cluster: `neural-hive` · Serviço: `orchestrator-dynamic`

## Estado: GATE DE EQUIVALÊNCIA E2E PASSADO — software gerado real a correr via `GenerateCapability`

Uma intenção de geração FastAPI (journey `J3_BUILD`) entra pelo **resume pós-aprovação**
(`POST /api/v1/workflows/start`), é roteada pela **fronteira não-vazada** para a
`GenerateCapability` (não pelo arranque directo de `FluxoGWorkflow`), percorre G1–G8 e
produz **software real a correr** no cluster: generate → build → push GHCR → deploy →
**healthcheck 200**. Comportamento equivalente ao caminho FluxoG anterior (gate J3/BUILD fiável,
spec `2026-06-23-j3-build-generate`), agora **através da capacidade**.

## Pré-condição: código da capacidade deployado

- Imagem deployada do orchestrator: `ghcr.io/albinojimy/neural-hive-mind/orchestrator-dynamic:52a1e63`
  (= HEAD `52a1e635`, Fase 3). Os commits da capacidade (`1cc3c694` contrato/registry,
  `b7f398e9` GenerateCapability, `70a9e8ca` des-vazar routing) são ancestrais → **o caminho
  `GenerateCapability` está em produção**. Pods arrancados 13:27–13:35Z, `2/2 Running` (0 restarts).

## Prova em cluster — plano `21fb028b-b05b-488f-92f1-f9b1a13bb440` (via capacidade)

Cadeia completa, com timestamps dos logs do orchestrator (`routing_basis=capability_generate`
é a assinatura da fronteira não-vazada — o resume delega na capacidade, que arranca o FluxoG):

| Passo | Evidência (log/cluster) | Timestamp |
|-------|-------------------------|-----------|
| **Resume → capacidade** | `workflow_start_attempt … journey=J3_BUILD routing_basis=capability_generate workflow_id=orch-flow-c-0e71d73c-…` | 14:31:07 |
| **Capacidade arranca FluxoG** | `workflow_started … workflow_class=FluxoGWorkflow workflow_id=orch-flow-c-0e71d73c-…` (durabilidade/saga preservadas; id `flow-c-{correlation_id}` honrado) | 14:31:07 |
| **G6 geração** | `code_artifacts`: `plan_id=21fb028b… journey=J3_BUILD status=completed framework=fastapi generation_method=TEMPLATE` | 14:31:58 |
| **G7 build+push** | `build_package_completed status=completed quality_score=0.8` → imagem **publicada no GHCR** | 14:34:10 |
| **G8 deploy** | `deploy_software_completed status=deployed service_url=http://service-21fb028b-….default.svc.cluster.local:80` | 14:41:28 |

### Estado vivo verificado **directamente** (anti-verde-falso — não se aceita `status=deployed` como prova)

- **Deployment** `service-21fb028b-b05b-488f-92f1-f9b1a13bb440-1.0.0` (namespace `default`):
  **`READY 2/2`**, 2 pods `1/1 Running`, **0 restarts** (excede o mínimo `1/1` da DoD).
- **Imagem do pod** (G7 real, pull bem-sucedido — sem ImagePullBackOff):
  `ghcr.io/albinojimy/neural-hive-mind/service-21fb028b-b05b-488f-92f1-f9b1a13bb440:1.0.0`.
- **Healthcheck `/health` = HTTP 200** (curl real in-pod, porta 8080):
  `{"status":"healthy","service":"service-21fb028b-…"}`. `/health/live` e `/health/ready` → 200.
- **Healthcheck via Service DNS do k8s (cross-pod, porta 80)** — prova de networking real, não
  loopback: `GET http://service-21fb028b-….default.svc.cluster.local:80/health` → **HTTP 200**.
- **Service** `service-21fb028b-…` ClusterIP `10.107.96.32:80` activo.

> Segundo plano confirmado pelo mesmo caminho (redundância): `f8813649-9706-…` — `routing_basis=
> capability_generate` (13:47) → `workflow_started FluxoGWorkflow` → code_artifact journey=J3_BUILD
> → `build_package_completed` (13:50) → `deploy_software_completed` (13:50). (Deployment desse plano
> já não está vivo; serviu de primeira passagem.)

### Notas de honestidade (reconciliação de auditoria)

- **Namespace `default` (não efémero/dedicado):** o deploy materializa-se em `default` —
  **equivalente ao caminho FluxoG anterior** (plano 52a083d8 também deployou em `default`). O
  namespace efémero dedicado com TTL/ResourceQuota é **Out-of-Scope herdado** da spec j3-build
  (fase5-evidence §"Fora de âmbito"); o gate central — software a correr + healthcheck 200 — está
  provado. A redação da DoD foi reconciliada para refletir isto.
- **Entrada E2E = resume pós-aprovação:** a passagem exercitada em cluster foi o resume
  (`POST /api/v1/workflows/start`, GEN-US2 + GEN-US4). O ramo do **`decision_consumer` (Kafka)**
  para geração partilha a **mesma** `GenerateCapability` e a **mesma** autoridade
  `_requires_generate_capability` (DRY, CR-001 da Fase 2) — está provado por unit, mas a sua
  execução-em-cluster permanece **diferida (gate 3.3, não marcado [x])** por instabilidade histórica
  do control-plane. Não se infere prova de cluster para o ramo do consumer.

## 5.1 — Gate cluster E2E via `GenerateCapability` · PASSADO

Intenção J3 → software FastAPI real a correr **via a capacidade** (Deployment `2/2`, `/health` 200
in-pod e via Service DNS, `code_artifact` journey=J3_BUILD). A assinatura `routing_basis=
capability_generate` + `workflow_class=FluxoGWorkflow` prova que a fronteira foi exercida (resume
delega na capacidade; a capacidade arranca o FluxoG durável) — equivalência ao caminho anterior.

## 5.2 — Ausência de regressão em J2/J4 (Orchestration inalterado) · CONFIRMADO

- **Código:** o bloco de routing J2/J4 → `OrchestrationWorkflow` no `decision_consumer` e no resume
  (`main.py`) está **intocado** pela extração (só o ramo de geração foi des-vazado). Ver
  `sub-specs/fase2-evidence.md`.
- **Unit (teste congelado, regra 7):** `tests/unit/test_workflow_start_journey_routing.py` afirma
  `OrchestrationWorkflow` para J2/J4 e `FluxoGWorkflow.run` para J3 — **continua verde**; regressão
  da suíte unit+consumers **idêntica ao baseline** (96 failed pré-existentes, +18 testes novos).
- **Cluster:** sem tráfego J2/J4 na janela de teste (só correram intenções J3); não se sobre-afirma
  prova de cluster inexistente — a paridade J2/J4 assenta no teste congelado + bloco intocado.

> **Precisão de evidência (auditoria Task 5, CR-002):** o teste congelado
> `test_workflow_start_journey_routing.py` prova apenas que `FluxoGWorkflow.run` é passado ao
> `start_workflow` para J3 (continua a passar mesmo num revert que arrancasse o FluxoG *directamente*,
> sem a capacidade) — serve de garantia de **não-regressão de routing**, não de prova de que a
> **fronteira da capacidade foi exercida**. A prova de que o caminho passa pela `GenerateCapability`
> é: (a) `tests/unit/test_workflow_start_generate_capability.py` (workflow_id no formato
> `flow-c-{correlation_id}`, só gerado pelo caminho via capacidade) e (b) o log de cluster
> `routing_basis=capability_generate` emitido **antes** de `capability.start()`, seguido de
> `workflow_started workflow_class=FluxoGWorkflow` emitido **depois** do `start` (par de timestamps
> 14:31:07).

## Anti-verde-falso (DoD: falha real em qualquer G-step → FAILED)

- `/health` 200 verificado por **curl directo ao endpoint** (in-pod + Service DNS), não por
  `status=deployed` reportado. O verde-falso histórico do healthcheck do deploy-service (selector
  inexistente → `0==0`=HEALTHY) foi corrigido na spec j3-build (fase5) e aqui contornado por
  observação independente do FastAPI gerado.
- Stack explícita não suportada → `UnsupportedStackError` → resume HTTP 422 / consumer commit+return
  (sem fallback silencioso para FastAPI). Provado por teste unit (Fase 2/3); não se injectou falha
  destrutiva no cluster.

## Re-verificação independente + auditoria (pipeline qualidade + completude)

Pipeline de auditoria adversarial executado sobre a Task 5 (não só `success=True` — evidência real):

- **Re-verificação de cluster (2026-06-26, ~15:5x):** o Deployment `service-21fb028b-…-1.0.0`
  **continua vivo** (`2/2`, 0 restarts) — não foi snapshot efémero. `/health` reconfirmado por curl
  real **HTTP 200** in-pod (8080) **e** cross-pod via Service DNS (80). `code_artifact` no MongoDB
  `neural_hive_orchestration.code_artifacts` reconfirmado: `plan_id=21fb028b, journey=J3_BUILD,
  status=completed, framework=fastapi, generation_method=TEMPLATE, language=python`. Imagem do
  orchestrator deployada = `52a1e63` (commits da capacidade ancestrais).
- **Auditoria de qualidade: SHIP** (0 críticos, 2 warnings, 3 info). Confirma fronteira não-vazada
  real (`routing_basis=capability_generate` antes de `capability.start()`; FluxoGWorkflow só é dead
  code legado no `_select_workflow_class_by_journey`, não no caminho produtivo) e ausência de
  verde-falso.
- **Auditoria de completude: COMPLETO** (8/8 itens da DoD PASS; gate 3.3 honestamente `[ ]`).

**Remediação dirigida aplicada** (não altera o veredicto SHIP — endurece honestidade/contrato):
- **CR-001:** docstring de `capability.py` reconciliada — `map_result` é o contrato de saída mas
  **sem chamador de produção** hoje (resultado consumido via signals/ExecutionResultConsumer); o
  anti-verde-falso E2E vem da observação directa do `/health`, não de `map_result`.
- **CR-002:** este documento clarifica que o teste congelado prova só `FluxoGWorkflow.run` (não a
  fronteira); a prova da fronteira é `test_workflow_start_generate_capability.py` + log
  `routing_basis=capability_generate` (ver §5.2).
- **CR-003:** `_requires_generate_capability` ganhou guard explícito `_is_plan_only` (contrato
  auto-consistente: J1+generation já não devolve `True`) + teste novo
  `tests/consumers/test_decision_consumer_plan_only_guard.py` (RED→GREEN). Suíte da capacidade:
  **88 verdes** (85 + 3 novos); regressão alargada idêntica ao baseline (96 failed pré-existentes).

## Conclusão

Task 5 (Fase 4) **PASSADA**: a extração de GENERATE para capacidade autónoma por fronteira de
contrato preserva a equivalência E2E — uma intenção J3_BUILD produz software FastAPI real a correr
(Deployment `2/2`, `/health` 200, imagem GHCR, `code_artifact` journey=J3_BUILD) **via
`GenerateCapability`**, sem regressão no caminho Orchestration (J2/J4). Spec
`2026-06-26-extrair-capacidade-generate` completa (Fases 0–4).
