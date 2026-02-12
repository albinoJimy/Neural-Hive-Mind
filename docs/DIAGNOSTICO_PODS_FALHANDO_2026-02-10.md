# Diagnóstico de Pods Falhando - Neural Hive-Mind
**Data:** 2026-02-10
**Namespace:** neural-hive

---

## Resumo Executivo

Investigação completa dos pods com status CrashLoopBackOff, ImagePullBackOff e Pending no namespace neural-hive. Identificadas 5 categorias de problemas.

---

## 1. Exaustão de Recursos do Cluster (CRÍTICO - Bloqueante)

### Pods Afetados (Status: Pending)
| Pod | Problema |
|-----|----------|
| self-healing-engine-6bbbf896c7 | Insufficient CPU/memory |
| guard-agents-7c86ff74d6 | Insufficient CPU/memory |
| code-forge-78fb9c6549 | Insufficient CPU/memory |
| consensus-engine-6fbd8d768f | Insufficient CPU/memory |
| consensus-engine-7d9f9f9fcb-wsb7w | Insufficient CPU/memory |
| analyst-agents-77fc8f6b7d | Insufficient CPU/memory |
| gateway-intencoes-5c697cb754 | Insufficient CPU/memory |

**Mensagem de erro:**
```
0/5 nodes are available: 1 Insufficient memory, 1 node(s) had untolerated taint
{node-role.kubernetes.io/control-plane: }, 4 Insufficient cpu.
```

**Ação necessária:** Escalar pods não essenciais ou adicionar nós ao cluster.

---

## 2. ImagePullBackOff - Tags de Imagem Incorretas

### Pods Afetados
| Pod | Tag da Imagem | Tag Esperada |
|-----|---------------|--------------|
| execution-ticket-service-58df94cc58 | SHA completo (40 chars) | SHA curto (7 chars) |
| explainability-api-6c6bbdfbb8 | SHA completo (40 chars) | SHA curto (7 chars) |
| mcp-tool-catalog (3 pods) | SHA completo (40 chars) | SHA curto (7 chars) |
| memory-layer-api (3 pods) | SHA completo (40 chars) | SHA curto (7 chars) |
| optimizer-agents | SHA completo (40 chars) | SHA curto (7 chars) |

**Causa raiz:** O workflow de build cria tags com SHA curto (7 caracteres), mas os deployments usam SHA completo (40 caracteres).

---

## 3. Problemas de Conexão com Serviços

### code-forge
- **Configuração atual:** `postgresql.postgresql.svc.cluster.local`
- **Problema:** DNS não existe (NXDOMAIN)
- **Correção necessária:** `postgres-sla.neural-hive-data.svc.cluster.local`
- **ConfigMap:** `code-forge-config` → `POSTGRES_HOST`

### orchestrator-dynamic
- **Configuração atual no código:** `redis-cluster.redis-cluster.svc.cluster.local:6379`
- **Problema:** DNS não existe
- **ConfigMap correto:** `neural-hive-cache.redis-cluster.svc.cluster.local:6379`
- **Observação:** ConfigMap já está correto, possível default no código

### guard-agents, worker-agents
- **Problema:** Service Registry connection refused
- **Causa:** Service Registry instável (2 de 3 pods em CrashLoopBackOff)

---

## 4. Instabilidade do Service Registry

| Pod | Status |
|-----|--------|
| service-registry-ffd5cb788-2vcfq | CrashLoopBackOff |
| service-registry-ffd5cb788-grz4r | CrashLoopBackOff |
| service-registry-ffd5cb788-ssdvm | Running (com restarts) |

**Impacto:** Todos os serviços que dependem de registro no Service Registry falham ao iniciar.

---

## 5. Métricas Prometheus Duplicadas

### orchestrator-dynamic
**Erro:**
```
Duplicated timeseries in CollectorRegistry: {
  'orchestration_workflows_started_created',
  'orchestration_workflows_started_total',
  'orchestration_workflows_started'
}
```

**Impacto:** Drift Detector e gRPC Server falham na inicialização.

---

## Pods em CrashLoopBackOff (Análise)

| Pod | Causa Principal |
|-----|-----------------|
| code-forge-7cd4b86654 | PostgreSQL DNS não encontrado |
| explainability-api-cf5f6d57 | Inicia mas recebe SIGTERM (~3s) |
| guard-agents-68c4594644 | Service Registry connection refused |
| orchestrator-dynamic-54b7654896 | Redis DNS não encontrado + métricas duplicadas |
| self-healing-engine-5b6bc7df79 | Inicia mas recebe SIGTERM |
| worker-agents-69d5dcdfb9 | Service Registry connection refused |
| service-registry (2 pods) | Investigação necessária |
| sla-management-system-b5949bc6f | Investigação necessária |
| memory-layer-api-7988f84695 | Investigação necessária |

---

## Plano de Ação

1. **Escalar pods não essenciais** para liberar recursos
2. **Atualizar ConfigMaps** com hosts corretos de banco/Redis
3. **Rebuild de imagens** com tags corretas
4. **Investigar Service Registry** CrashLoopBackOff
5. **Corrigir métricas duplicadas** no orchestrator-dynamic

---

## Comandos Úteis

```bash
# Ver pods em problema
kubectl get pods -n neural-hive | grep -E "(Pending|CrashLoopBackOff|ImagePullBackOff|Error)"

# Ver recursos disponíveis
kubectl top nodes

# Ver events de um pod específico
kubectl describe pod <pod-name> -n neural-hive

# Ver logs
kubectl logs <pod-name> -n neural-hive --tail=50
```
