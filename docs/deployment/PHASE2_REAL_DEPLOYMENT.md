# Phase 2 Real Services Deployment

## Visao Geral

Este documento descreve o deployment dos 13 servicos reais da Fase 2, substituindo os stubs nginx anteriores.

## Servicos Deployados

| # | Servico | Namespace | Chart Path | Porta HTTP | Porta gRPC |
|---|---------|-----------|------------|------------|------------|
| 1 | service-registry | neural-hive-registry | helm-charts/service-registry | - | 50051 |
| 2 | execution-ticket-service | neural-hive-orchestration | helm-charts/execution-ticket-service | 8000 | 50052 |
| 3 | orchestrator-dynamic | neural-hive-orchestration | helm-charts/orchestrator-dynamic | 8000 | - |
| 4 | queen-agent | neural-hive-queen | services/queen-agent/helm-chart | 8000 | 50053 |
| 5 | worker-agents | neural-hive-workers | helm-charts/worker-agents | 8080 | - |
| 6 | code-forge | neural-hive-code-forge | helm-charts/code-forge | 8080 | 50051 |
| 7 | scout-agents | neural-hive-scouts | helm-charts/scout-agents | 8000 | - |
| 8 | analyst-agents | neural-hive-analysts | services/analyst-agents/helm-chart | 8000 | 50051 |
| 9 | optimizer-agents | neural-hive-optimizers | services/optimizer-agents/helm-chart | 8000 | 50051 |
| 10 | guard-agents | neural-hive-guards | helm-charts/guard-agents | 8080 | 50051 |
| 11 | sla-management-system | neural-hive-sla | helm-charts/sla-management-system | 8000 | - |
| 12 | mcp-tool-catalog | neural-hive-mcp | helm-charts/mcp-tool-catalog | 8080 | - |
| 13 | self-healing-engine | neural-hive-healing | helm-charts/self-healing-engine | 8080 | 50051 |

## Pre-requisitos

1. **Imagens Docker**: Todas as 13 imagens devem estar no registry `37.60.241.150:30500` com tag `1.0.0`
2. **Secrets Kubernetes**: Secrets criados pela fase anterior (`create-phase2-secrets.sh`)
3. **Infraestrutura**: PostgreSQL, MongoDB, Redis, Kafka, Temporal operacionais
4. **Ferramentas**: kubectl, helm instalados e configurados

## Processo de Deployment

### 1. Executar Deploy

```bash
./scripts/deploy/deploy-phase2-real-services.sh
```

O script ira:
- Verificar prerequisites
- Criar namespaces necessarios
- Remover stubs nginx antigos
- Deployar servicos em ordem de dependencia
- Validar que todos os pods ficaram ready

### 2. Validar Deployment

```bash
./scripts/validation/validate-phase2-deployment.sh
```

### 3. Verificar Logs

```bash
# Ver logs de um servico especifico
kubectl logs -n neural-hive-orchestration -l app.kubernetes.io/name=orchestrator-dynamic -f

# Ver todos os pods
kubectl get pods --all-namespaces | grep neural-hive
```

## Ordem de Deployment

Os servicos sao deployados na seguinte ordem para respeitar dependencias:

1. **Base Services**: service-registry, execution-ticket-service
2. **Orchestration Layer**: orchestrator-dynamic, queen-agent
3. **Execution Layer**: worker-agents, code-forge
4. **Agent Layer**: scout-agents, analyst-agents, optimizer-agents, guard-agents
5. **Support Services**: sla-management-system, mcp-tool-catalog, self-healing-engine

## Troubleshooting

### Pods nao ficam Ready

```bash
# Ver eventos do pod
kubectl describe pod <pod-name> -n <namespace>

# Ver logs
kubectl logs <pod-name> -n <namespace>

# Verificar secrets
kubectl get secrets -n <namespace>
```

### ImagePullBackOff

Verificar se a imagem existe no registry:

```bash
curl -X GET http://37.60.241.150:30500/v2/<service-name>/tags/list
```

### CrashLoopBackOff

Verificar logs e configuracao de secrets/environment variables.

## Rollback

Para fazer rollback de um servico:

```bash
helm rollback <service-name> -n <namespace>
```

## Proximos Passos

Apos deployment bem-sucedido:
1. Executar validacao de integracao (Fase seguinte)
2. Testar comunicacao gRPC entre servicos
3. Validar conectividade com bancos de dados
4. Executar teste end-to-end do Fluxo C
