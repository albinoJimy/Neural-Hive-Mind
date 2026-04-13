# Runbooks Neural Hive Mind

Esta directory contém runbooks para responder a alertas e incidentes no sistema Neural Hive Mind.

## Estrutura

```
runbooks/
├── README.md (este arquivo)
├── queen-agent-down.md
├── consensus-engine-no-quorum.md
├── service-registry-down.md
└── approval-service-queue-backlog.md
```

## Runbooks Disponíveis

| Runbook | Alerta | Severidade | Camada |
|---------|--------|------------|--------|
| [Queen Agent Down](./queen-agent-down.md) | QueenAgentDown | Critical | Coordination |
| [Consensus Engine No Quorum](./consensus-engine-no-quorum.md) | ConsensusEngineNoQuorum | Critical | Cognitive |
| [Service Registry Down](./service-registry-down.md) | ServiceRegistryDown | Critical | Coordination |
| [Approval Service Queue Backlog](./approval-service-queue-backlog.md) | ApprovalServiceQueueBacklog | Warning | Decision |

## Comandos Rápidos

### Verificar Todos os Serviços

```bash
kubectl get pods -n neural-hive
kubectl get pods -n neural-hive | grep -E "0/1.*Error|0/1.*CrashLoop"
```

### Verificar Alertas Ativos

```bash
kubectl port-forward -n observability svc/neural-hive-prometheus-kub-prometheus 9090:9090
# Acessar http://localhost:9090/alerts
```

### Logs em Tempo Real

```bash
kubectl logs -n neural-hive -l app=queen-agent -f
kubectl logs -n neural-hive -l app=consensus-engine -f
```

## Links Úteis

- **Grafana:** http://grafana.observability.svc.cluster.local:3000
- **Prometheus:** http://prometheus.observability.svc.cluster.local:9090
- **AlertManager:** http://alertmanager.observability.svc.cluster.local:9093

---

**Última atualização:** 2026-04-13
**Versão:** 1.0
