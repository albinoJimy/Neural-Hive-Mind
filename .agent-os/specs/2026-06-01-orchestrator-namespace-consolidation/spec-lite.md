# Spec Summary (Lite)

Consolidar as referências ao `orchestrator-dynamic` — hoje fragmentadas por 3 namespaces (canónico saudável em `orchestrator-dynamic`, legacy quebrado em `neural-hive`, inexistente em `neural-hive-orchestration`) — num único endpoint canónico. Alinhar host/porta/protocolo/TLS dos 3 clientes (queen-agent, optimizer-agents, self-healing-engine), corrigir a referência morta do self-healing e desativar com segurança os deployments legacy, eliminando os pods presos no SPIRE e a duplicação.
