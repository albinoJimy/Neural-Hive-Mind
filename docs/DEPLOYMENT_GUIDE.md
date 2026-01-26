# Guia de Deployment - Phase 2

Este documento complementa o [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) principal com informacoes especificas para validacao de comunicacao gRPC na Phase 2.

## Validacao de Comunicacao gRPC

Apos deploy do orchestrator-dynamic e execution-ticket-service, e necessario validar a conectividade gRPC entre os servicos.

### Script de Validacao

```bash
# Executar validacao completa de conectividade gRPC
./scripts/validation/validate-grpc-ticket-service.sh
```

O script valida:
1. Pods rodando no namespace
2. Logs de inicializacao do servidor gRPC
3. Conectividade de rede na porta 50052
4. Servicos gRPC disponiveis (via grpcurl se disponivel)
5. Readiness probe gRPC
6. Metricas gRPC no endpoint Prometheus
7. Kubernetes Service e endpoints

### Sinais de Sucesso

Apos deploy bem-sucedido, verificar:

| Sinal | Onde Verificar | Comando |
|-------|----------------|---------|
| gRPC server inicializado | Logs do execution-ticket-service | `kubectl logs -l app=execution-ticket-service \| grep grpc_server_started` |
| Health service registrado | Logs do execution-ticket-service | `kubectl logs -l app=execution-ticket-service \| grep grpc_health_check_registered` |
| Pod Ready | Status do pod | `kubectl get pods -l app=execution-ticket-service` |
| Metricas gRPC presentes | Endpoint Prometheus | `curl localhost:9090/metrics \| grep grpc_server_handled_total` |

### Troubleshooting

#### Erro: Connection Timeout

**Sintoma**: Orchestrator nao consegue conectar ao execution-ticket-service

**Diagnostico**:
```bash
# Verificar se pod esta rodando
kubectl get pods -n neural-hive-orchestration -l app=execution-ticket-service

# Verificar eventos do pod
kubectl describe pod -l app=execution-ticket-service -n neural-hive-orchestration
```

**Solucoes**:
- Verificar se o pod iniciou corretamente
- Verificar logs de erro durante inicializacao
- Aumentar `startupProbe.failureThreshold` se o pod demora para inicializar

#### Erro: ConnectError

**Sintoma**: Conexao recusada na porta 50052

**Diagnostico**:
```bash
# Verificar se porta 50052 esta no Service
kubectl get svc execution-ticket-service -n neural-hive-orchestration -o yaml | grep -A5 ports:

# Verificar NetworkPolicies
kubectl get networkpolicies -n neural-hive-orchestration

# Testar DNS
kubectl exec deployment/orchestrator-dynamic -- nslookup execution-ticket-service
```

**Solucoes**:
- Verificar se Service expoe porta 50052
- Verificar se NetworkPolicies permitem trafego na porta gRPC
- Verificar se DNS do servico resolve corretamente

#### Erro: Unavailable (Service Not Serving)

**Sintoma**: gRPC health check retorna NOT_SERVING

**Diagnostico**:
```bash
# Verificar status de dependencias
kubectl logs -l app=execution-ticket-service | grep -E "(postgres|mongodb).*error"

# Verificar readiness probe
kubectl describe pod -l app=execution-ticket-service | grep -A10 Readiness
```

**Solucoes**:
- Verificar conexao com PostgreSQL
- Verificar conexao com MongoDB
- Verificar se dependencias estao saudaveis

### Verificacao Manual

```bash
# 1. Verificar porta gRPC acessivel do orchestrator
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  nc -zv execution-ticket-service 50052

# 2. Listar servicos gRPC (requer grpcurl no pod)
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  grpcurl -plaintext execution-ticket-service:50052 list

# 3. Verificar health check gRPC
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  grpcurl -plaintext execution-ticket-service:50052 grpc.health.v1.Health/Check

# 4. Verificar metricas
kubectl exec -n neural-hive-orchestration -l app=execution-ticket-service -- \
  curl -s localhost:9090/metrics | grep grpc_server
```

## Referencias

- [Arquitetura gRPC Orchestrator-Ticket](architecture/orchestrator-ticket-service-grpc.md)
- [Phase 2 Architecture Diagram](PHASE2_ARCHITECTURE_DIAGRAM.md)
- [Flow C Integration](PHASE2_FLOW_C_INTEGRATION.md)
