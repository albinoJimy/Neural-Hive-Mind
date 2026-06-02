# Technical Specification

This is the technical specification for the spec detailed in @.agent-os/specs/2026-06-01-orchestrator-namespace-consolidation/spec.md

## Estado atual (levantamento no cluster — 2026-06-01)

### Deployments/Services `orchestrator-dynamic`

| Namespace | Deployment | Service (portas) | Endpoints | Criado | Observação |
|---|---|---|---|---|---|
| `orchestrator-dynamic` | ✅ 3/3 ready (base 1.3.0) | `http:8003`, `metrics:8000` | 3 pods | 2026-04-27 | **Canónico/saudável**. NÃO expõe gRPC. |
| `neural-hive` | ⚠️ 1/2 (Helm-managed) | `50053`, `8000`, `9090` | 1 pod (antigo, 10d) | 2026-02-26 | **Legacy**. 2 pods presos em `Init` (socket SPIRE inexistente). |
| `neural-hive-orchestration` | ❌ não existe | sem portas | 0 | — | Referenciado pelo self-healing, mas **morto**. |

### Configuração atual dos clientes

| Cliente | ConfigMap | Host configurado | Porta | TLS |
|---|---|---|---|---|
| `optimizer-agents` | `optimizer-agents` | `orchestrator-dynamic.neural-hive.svc.cluster.local` | `50051` | — |
| `queen-agent` | `queen-agent-config` | `orchestrator-dynamic.neural-hive.svc.cluster.local` | `50053` | — |
| `self-healing-engine` | `self-healing-engine-config` | `orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local` | `50052` | `true` |

**Inconsistências detetadas:** 3 hosts diferentes (2 namespaces, 1 inexistente), 3 portas gRPC diferentes (50051/50052/50053), TLS apenas num cliente, e o canónico não expõe nenhuma destas portas (só HTTP 8003).

## Technical Requirements

- **Determinar o contrato de comunicação canónico** antes de qualquer alteração de cliente:
  - Inspecionar o código/manifesto do orchestrator canónico (`services/orchestrator-dynamic/`) para confirmar se serve gRPC (e em que porta de container) ou se migrou para HTTP/REST em `:8003`.
  - Verificar os container ports do pod canónico (atualmente só `http=8003`, `metrics=8000`) e o código do servidor (procurar `grpc`, `add_insecure_port`, `server.start`).
  - Decidir: (A) expor a porta gRPC no service canónico e nos container ports, ou (B) migrar os clientes para o protocolo HTTP em `:8003`.
- **Alinhar os 3 clientes** ao contrato decidido, atualizando os respetivos ConfigMaps:
  - Host → FQDN do serviço canónico (`orchestrator-dynamic.orchestrator-dynamic.svc.cluster.local`).
  - Porta → porta canónica única.
  - Protocolo/TLS → coerente entre todos (uniformizar a flag TLS).
- **Verificar o código cliente** (`neural_hive_*` / `src/clients/`) de cada agente para garantir que respeita as env vars (`ORCHESTRATOR_*`) e o protocolo escolhido; ajustar onde o protocolo esteja hardcoded.
- **Desativação segura dos legacy** (apenas após validação de conectividade ao canónico):
  - Confirmar via `kubectl get endpoints` e logs que nenhum cliente continua a contactar `neural-hive`/`neural-hive-orchestration`.
  - Escalar a 0 o deployment legacy `neural-hive/orchestrator-dynamic`; remover via Helm (identificar o release com `helm list -A`) para evitar reversão automática.
  - Remover quaisquer Services/ConfigMaps órfãos em `neural-hive-orchestration`.
- **Persistência**: as alterações de configuração devem ser feitas nos manifestos/Helm values versionados (não apenas `kubectl edit`), para sobreviverem a redeploys. Os ConfigMaps `*-config` correspondentes devem ser atualizados na fonte.
- **Restrições do cluster** (do levantamento): Gatekeeper exige labels `app` + `app.kubernetes.io/name` e `container-must-have-limits`; respeitar em qualquer recurso novo/alterado. Pull de imagens pode ser lento em alguns nodes.

## Critérios de validação

- Logs de cada cliente mostram conexão estabelecida ao orchestrator canónico (sem `DEADLINE_EXCEEDED`, `connection refused` ou DNS de namespace inexistente).
- `kubectl get deploy,svc,endpoints -A | grep orchestrator-dynamic` lista apenas o namespace canónico.
- `kubectl get pods -A | grep orchestrator-dynamic | grep -v Running` vazio (sem pods `Init`/`CrashLoop`).
- Readiness/health dos 3 clientes a 100%.

## External Dependencies (Conditional)

Nenhuma nova dependência externa. Trabalho limitado a manifestos K8s/Helm, ConfigMaps e, se necessário, ajuste do servidor/cliente gRPC-HTTP já existente no código.
