# Spec Tasks

> Spec: Consolidação de Namespaces do Orchestrator-Dynamic
> Created: 2026-06-01

## Tasks

- [x] 1. Determinar o contrato de comunicação canónico (gRPC vs HTTP)
  - [x] 1.1 Inspecionar `services/orchestrator-dynamic/src/` à procura do servidor (gRPC `add_insecure_port`/`add_secure_port`/`server.start` ou app HTTP/FastAPI em `:8003`)
  - [x] 1.2 Confirmar container ports do deployment canónico e o que o service expõe vs o que o código serve
  - [x] 1.3 Verificar o código cliente de queen-agent/optimizer-agents/self-healing (`src/clients/`) — que protocolo esperam e se respeitam as env `ORCHESTRATOR_*`
  - [x] 1.4 Decidir e documentar o contrato canónico (host FQDN, porta única, protocolo, TLS) — ADR em `sub-specs/contract-decision.md`
  - [x] 1.5 Verificar: contrato canónico documentado e validado contra código servidor+cliente

- [x] 2. Garantir que o orchestrator canónico expõe o contrato decidido (manifestos prontos — PR #112)
  - [x] 2.1 gRPC: porta 50053 exposta no Service + containerPort (via service.ports, values-k8s.yaml) respeitando labels Gatekeeper
  - [x] 2.2 (n/a — contrato é gRPC, não HTTP)
  - [x] 2.3 Aplicado via Helm values versionados (configmap.yaml: ENABLE_GRPC_SERVER/GRPC_SERVER_PORT) — rollout fica pós-merge
  - [x] 2.4 Verificar no cluster: `kubectl get svc/endpoints` expõe 50053 e responde (Service expõe 50053 — TCP OPEN, /health 200, 9 endpoints — verificado no cluster 2026-06-02)

- [x] 3. Alinhar os 3 clientes ao endpoint canónico (manifestos prontos — PR #112)
  - [x] 3.1 `optimizer-agents`: host→canónico, porta 50051→50053, ORCHESTRATOR_ENDPOINT coerente
  - [x] 3.2 `queen-agent`: host legacy→canónico (porta 50053 já correta)
  - [x] 3.3 `self-healing-engine`: namespace morto→canónico, porta 50052→50053, useTls true→false (+ NetworkPolicy)
  - [x] 3.4 Persistido nos Helm values versionados — rollout fica pós-merge
  - [x] 3.5 Verificar no cluster: logs dos 3 clientes sem `DEADLINE_EXCEEDED`/`connection refused`/DNS falhado (queen-agent 0 erros de conexão; optimizer/self-healing a 0 réplicas — values versionados corretos para quando escalarem — verificado 2026-06-02)

# NOTA: decisão revista — canónico é NEURAL-HIVE (não orchestrator-dynamic/). Ver ADR atualizado.
- [x] 4. Consolidar deployments (canónico = neural-hive; remover órfãos)
  - [x] 4.1 Confirmado zero tráfego nos órfãos (0 ConfigMaps referenciam orchestrator-dynamic.orchestrator-dynamic / neural-hive-staging)
  - [x] 4.2 Reparado o release neural-hive/orchestrator-dynamic (estava failed/pending por SPIRE+rate-limiter): rollback p/ limpar pending + helm upgrade --wait=false com overlay staging corrigido (spiffe.enabled=false, PR #114) → rev 142 deployed, 0 pods SPIRE
  - [x] 4.3 Removidos órfãos: deployment+service `orchestrator-dynamic/` (kubectl apply manual) e service `neural-hive-staging/orchestrator-dynamic`. (neural-hive-orchestration nunca existiu — só ref morta, corrigida no #113)
  - [x] 4.4 Verificado: só `neural-hive/orchestrator-dynamic` existe; zero pods Init/SPIRE

- [x] 5. Validação
  - [x] 5.2/5.3 queen-agent (2/2) aponta p/ canónico neural-hive:50053, 0 erros de conexão; canónico: gRPC 50053 insecure up, /health 200, release deployed
  - [x] 5.1/5.4 teste de integração de regressão criado (`tests/integration/test_orchestrator_namespace_consolidation.py` — 10 testes, config-contract determinístico) + `docs/feature-map.md` atualizado (optimizer/self-healing a 0 réplicas — charts #113 já apontam p/ canónico quando escalados)
