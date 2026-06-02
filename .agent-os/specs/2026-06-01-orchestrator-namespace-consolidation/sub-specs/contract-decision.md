# ADR — Contrato de Comunicação Canónico do Orchestrator (Task 1)

> Spec: @.agent-os/specs/2026-06-01-orchestrator-namespace-consolidation/spec.md
> Decisão: Task 1 (determinação do contrato gRPC vs HTTP)
> Data: 2026-06-01
> Status: Decidido

## Decisão

O contrato canónico do `orchestrator-dynamic` é **gRPC**, serviço **`OrchestratorStrategic`**, na porta **`50053`**, **sem TLS** (insecure) no estado atual do cluster.

> ⚠️ **REVISÃO DE NAMESPACE (2026-06-01, pós-investigação Task 4):** o host canónico é **`orchestrator-dynamic.neural-hive.svc.cluster.local`** (NÃO `orchestrator-dynamic.orchestrator-dynamic`). A investigação de deploy revelou que o pipeline CI/CD (`deploy-after-build.yml`) deploya SEMPRE para o namespace `neural-hive` (namespace fixo "temporário"); o release Helm `orchestrator-dynamic` vive em `neural-hive` e o seu Service já expõe `50053`. O deployment em `orchestrator-dynamic/orchestrator-dynamic` (3/3) era um `kubectl apply` MANUAL órfão, fora do CI/CD, a remover. Decisão do utilizador: alinhar com o pipeline (neural-hive). O PR #112 (que apontava para `orchestrator-dynamic/`) foi corrigido pelo PR #113 (host → `neural-hive`).

## Evidência (código)

- **Servidor gRPC existe e é o contrato real:** `services/orchestrator-dynamic/src/main.py:910` arranca `start_grpc_server` quando `enable_grpc_server` (default `True`), na porta `grpc_server_port` (default **50053**, `settings.py:535` — "Porta do servidor gRPC para comandos estratégicos").
- **Serviço gRPC:** `src/grpc_server/server.py:56` regista `OrchestratorStrategicServicer` (`add_OrchestratorStrategicServicer_to_server`).
- **TLS:** o servidor tenta mTLS via SPIFFE/SPIRE (`add_secure_port`) com **fallback automático para insecure** (`server.py:74,82`). Como `spiffe_enabled` (default `False`) e `spiffe_enable_x509` (default `False`) estão desligados e **o SPIRE foi removido do cluster**, o servidor corre **insecure**.
- **HTTP/FastAPI também existe** (`main.py:1096`, uvicorn em `:8003`) mas serve health/REST/métricas — não é o canal de orquestração estratégica que os clientes usam.

## Problema confirmado: o Service canónico não expõe a porta gRPC

O pod canónico corre o gRPC em `50053` internamente, mas o **Service `orchestrator-dynamic/orchestrator-dynamic` expõe apenas `http:8003` e `metrics:8000`** — não há porta `50053`. Por isso os clientes não conseguem alcançar o gRPC canónico; só o Service legacy (`neural-hive`) expõe `50053`.

## Divergências dos clientes (código default vs ConfigMap no cluster)

| Cliente | Código default | ConfigMap no cluster | Correto (alvo) |
|---|---|---|---|
| optimizer-agents | `orchestrator-dynamic.orchestrator-dynamic...:50051` | `...neural-hive...:50051` | `...orchestrator-dynamic...:50053` |
| queen-agent | (env-driven) | `...neural-hive...:50053` | `...orchestrator-dynamic...:50053` |
| self-healing-engine | `...neural-hive...:50052`, `use_tls=True` | `...neural-hive-orchestration...:50052`, TLS=`true` | `...orchestrator-dynamic...:50053`, `use_tls=false` |

**Portas trocadas:** `50051` é do service-registry, `50052` é do execution-ticket-service — só `50053` é o orchestrator. Apenas o queen-agent tem a porta certa; optimizer e self-healing usam portas de outros serviços.

## Consequências para as tarefas seguintes

- **Task 2:** expor a porta `50053` (gRPC) no Service canónico e nos container ports do deployment `orchestrator-dynamic/orchestrator-dynamic` (Helm values). O servidor já a serve — falta apenas publicá-la.
- **Task 3:** corrigir nos 3 clientes host→canónico, porta→`50053`, e `use_tls=false` (uniformizar; o self-healing tem `true`, que falharia contra um servidor insecure).
- **Segurança (nota):** a comunicação fica insecure enquanto o SPIRE não for reintroduzido. Reativar mTLS (SPIFFE) é trabalho futuro fora do âmbito desta spec; se for requisito, abrir spec dedicada.

## Alternativa rejeitada

**Migrar clientes para HTTP `:8003`** — rejeitada: o canal estratégico é gRPC (`OrchestratorStrategic`) e os clientes já têm stubs gRPC gerados; migrar para HTTP exigiria reescrever clientes e servidor sem benefício. Expor a porta gRPC existente é mínimo e correto.
