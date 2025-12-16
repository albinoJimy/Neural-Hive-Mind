# Guia de Validacao da Fase 2 - Neural Hive Mind

Este documento descreve como validar os 13 servicos da Fase 2 do Neural Hive Mind.

## Pre-requisitos

### Ferramentas Necessarias

- `kubectl` configurado com acesso ao cluster
- Python 3.11+ com bibliotecas: `motor`, `asyncpg`, `redis`, `neo4j`, `grpcio`
- `jq` para processamento JSON
- Acesso aos namespaces: `neural-hive`, `kafka`

### Instalacao de Dependencias Python

```bash
pip install motor asyncpg redis neo4j grpcio grpcio-health-checking
```

## Execucao de Validacoes

### Validacao Completa

```bash
# Executa todas as 8 fases de validacao
./scripts/validation/validate-phase2-services.sh

# Modo rapido (apenas pods e HTTP)
./scripts/validation/validate-phase2-services.sh --quick

# Saida em JSON
./scripts/validation/validate-phase2-services.sh --json
```

### Validacao de Bancos de Dados

```bash
# Testa conectividade MongoDB, PostgreSQL, Redis, Neo4j
python scripts/validation/test_database_connectivity.py

# Modo silencioso
python scripts/validation/test_database_connectivity.py --quiet

# Saida JSON
python scripts/validation/test_database_connectivity.py --json
```

### Validacao de Comunicacao gRPC

```bash
# Testa comunicacao entre servicos gRPC
python scripts/validation/test_grpc_communication.py

# Testar servico especifico
python scripts/validation/test_grpc_communication.py --service queen-agent
```

### Validacao de Kafka Consumers

```bash
# Valida consumer groups e lag
./scripts/validation/test_kafka_consumers.sh

# Servico especifico
./scripts/validation/test_kafka_consumers.sh --service orchestrator-dynamic
```

### Dashboard de Status

```bash
# Dashboard em tempo real (atualiza a cada 5s)
./scripts/validation/phase2-status-dashboard.sh

# Alterar intervalo de atualizacao
./scripts/validation/phase2-status-dashboard.sh --refresh 10

# Executar apenas uma vez
./scripts/validation/phase2-status-dashboard.sh --once
```

## Interpretacao de Resultados

### Codigos de Status

| Codigo | Significado | Acao |
|--------|-------------|------|
| `[PASS]` | Validacao bem-sucedida | Nenhuma |
| `[FAIL]` | Validacao falhou | Investigar imediatamente |
| `[WARN]` | Aviso - pode indicar problema | Monitorar |

### Codigos de Saida

- `0`: Todas validacoes passaram
- `1`: Uma ou mais validacoes falharam

## Troubleshooting

### Problema: Pod nao esta Ready

```bash
# Verificar eventos do pod
kubectl describe pod <pod-name> -n neural-hive

# Verificar logs
kubectl logs <pod-name> -n neural-hive --tail=100

# Verificar probes
kubectl get pod <pod-name> -n neural-hive -o yaml | grep -A5 "livenessProbe"
```

### Problema: Endpoint /ready retorna 503

```bash
# Verificar logs do servico
kubectl logs -l app=<service> -n neural-hive --tail=200

# Verificar conectividade de bancos de dados
kubectl exec -n neural-hive <pod> -- curl -s http://localhost:8000/health
```

### Problema: gRPC retorna UNAVAILABLE

```bash
# Verificar se porta esta aberta
kubectl exec -n neural-hive <pod> -- ss -tlnp | grep 50051

# Verificar logs do servidor gRPC
kubectl logs -l app=<service> -n neural-hive | grep -i grpc
```

### Problema: Kafka consumer lag alto

```bash
# Verificar lag detalhado
kubectl exec -n kafka <kafka-pod> -- kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group <consumer-group> \
  --describe

# Verificar logs do consumer
kubectl logs -l app=<service> -n neural-hive | grep -i kafka
```

## Integracao com CI/CD

### GitHub Actions

```yaml
- name: Validar Servicos Fase 2
  run: |
    ./scripts/validation/validate-phase2-services.sh --json > validation-report.json
    if [ $? -ne 0 ]; then
      echo "Validacao falhou"
      exit 1
    fi
```

### Makefile

```makefile
validate-phase2:
	./scripts/validation/validate-phase2-services.sh

validate-phase2-quick:
	./scripts/validation/validate-phase2-services.sh --quick

validate-databases:
	python scripts/validation/test_database_connectivity.py

validate-grpc:
	python scripts/validation/test_grpc_communication.py

validate-kafka:
	./scripts/validation/test_kafka_consumers.sh
```

## Matriz de Validacao por Servico

| Servico | HTTP | gRPC | MongoDB | PostgreSQL | Redis | Neo4j | Kafka |
|---------|------|------|---------|------------|-------|-------|-------|
| orchestrator-dynamic | X | - | X | - | X | - | X |
| queen-agent | X | X | X | - | X | X | X |
| worker-agents | X | - | - | - | - | - | X |
| code-forge | X | - | X | X | X | - | X |
| service-registry | X | X | - | - | X | - | - |
| execution-ticket-service | X | - | X | X | - | - | - |
| scout-agents | X | - | - | - | - | - | - |
| analyst-agents | X | - | X | X | X | X | - |
| optimizer-agents | X | X | X | - | X | - | - |
| guard-agents | X | - | X | - | - | - | X |
| sla-management-system | X | - | - | X | X | - | - |
| mcp-tool-catalog | X | - | X | - | - | - | - |
| self-healing-engine | X | - | - | - | - | - | - |

## Relatorios

Os relatorios de validacao sao salvos em:

```
reports/phase2-validation-report-<timestamp>.json
```

Estrutura do relatorio:

```json
{
  "report_metadata": {
    "timestamp": "2024-01-15T10:30:00Z",
    "report_id": "20240115_103000",
    "overall_status": "PASSED"
  },
  "summary": {
    "total_checks": 50,
    "passed_checks": 48,
    "failed_checks": 0,
    "warnings": 2,
    "pass_rate": 96.00
  },
  "phases": {
    "phase1_pods": true,
    "phase2_http": true,
    "phase3_metrics": true,
    "phase4_databases": true,
    "phase5_grpc": true,
    "phase6_kafka": true,
    "phase7_logs": true
  }
}
```
