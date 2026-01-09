# Políticas de Retenção Memory Layer

## Visão Geral

Políticas de retenção de dados para cada camada de armazenamento do Memory Layer.

## Políticas por Camada

### Redis (Hot)

| Tipo de Dado | TTL Padrão | TTL Máximo | Descrição |
|--------------|------------|------------|-----------|
| context      | 5 min      | 15 min     | Contexto ativo de operações |
| session      | 15 min     | 15 min     | Dados de sessão |
| cache        | 5 min      | 15 min     | Cache genérico |

### MongoDB (Warm)

| Collection             | Retenção | Descrição |
|------------------------|----------|-----------|
| operational_context    | 30 dias  | Contexto operacional |
| cognitive_ledger       | 365 dias | Ledger cognitivo |
| data_lineage           | 730 dias | Linhagem de dados |
| data_quality_metrics   | 90 dias  | Métricas de qualidade |

### ClickHouse (Cold)

| Tabela                      | Retenção   | Descrição |
|-----------------------------|------------|-----------|
| operational_context_history | 18 meses   | Histórico de contexto |
| cognitive_plans_history     | 18 meses   | Histórico de planos |
| telemetry_events            | 12 meses   | Eventos de telemetria |
| audit_events                | 60 meses   | Eventos de auditoria |

### Neo4j (Semântico)

| Tipo           | Política                | Descrição |
|----------------|-------------------------|-----------|
| Ontology       | 10 versões por ontologia| Versionamento |
| Old versions   | Archive após 10 versões | Arquivamento |
| Relationships  | Permanente              | Relacionamentos |

## Enforcement

### Automático

O enforcement é executado automaticamente via CronJob:

- **Schedule:** Diariamente às 3h UTC
- **CronJob:** `memory-cleanup-retention`
- **Namespace:** `neural-hive`

### Manual

```bash
# Dry-run (apenas mostra o que seria deletado)
kubectl exec -it memory-layer-api-pod -- \
  python /app/src/jobs/enforce_retention.py --dry-run

# Execução real
kubectl create job --from=cronjob/memory-cleanup-retention manual-cleanup-$(date +%s)

# Via script Python
kubectl exec -it memory-layer-api-pod -- \
  python -c "
from src.services.retention_policy_manager import RetentionPolicyManager
import asyncio
manager = RetentionPolicyManager(settings)
asyncio.run(manager.enforce_all_policies(dry_run=False))
"
```

## Customização

### ConfigMap de Políticas

As políticas podem ser customizadas via ConfigMap:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: memory-layer-policies
  namespace: memory-layer-api
data:
  retention-policies.yaml: |
    mongodb:
      operational_context:
        retention_days: 30
      cognitive_ledger:
        retention_days: 365
      data_lineage:
        retention_days: 730

    clickhouse:
      operational_context_history:
        retention_months: 18
      audit_events:
        retention_months: 60

    neo4j:
      ontology_max_versions: 10
      archive_old_versions: true

    redis:
      default_ttl_seconds: 300
      max_ttl_seconds: 900
```

### Variáveis de Ambiente

```bash
# MongoDB
MONGODB_RETENTION_DAYS=30

# ClickHouse
CLICKHOUSE_RETENTION_MONTHS=18

# Redis
REDIS_DEFAULT_TTL=300
REDIS_MAX_TTL=900

# Dry-run mode
DRY_RUN=false
```

## Métricas

| Métrica | Tipo | Descrição |
|---------|------|-----------|
| `memory_retention_documents_deleted_total` | Counter | Documentos deletados |
| `memory_retention_job_duration_seconds` | Histogram | Duração do job |
| `memory_retention_errors_total` | Counter | Erros durante cleanup |

## Logs

```bash
# Ver logs do job de retenção
kubectl logs -l app.kubernetes.io/name=memory-cleanup-job -n neural-hive --tail=100

# Filtrar por collection
kubectl logs -l app.kubernetes.io/name=memory-cleanup-job -n neural-hive | grep "operational_context"
```

## Considerações de Compliance

### GDPR
- Dados pessoais devem ser removidos conforme solicitação
- Retenção máxima de dados pessoais: 30 dias após inatividade

### Auditoria
- `audit_events` mantidos por 5 anos (60 meses)
- Logs de acesso mantidos em separado

### Backup antes de Cleanup
- Sempre verifique backups antes de cleanup manual
- ClickHouse mantém dados em storage de longo prazo

## Troubleshooting

### Dados não sendo deletados

1. Verificar se CronJob está rodando:
```bash
kubectl get cronjob memory-cleanup-retention -n neural-hive
```

2. Verificar logs do job:
```bash
kubectl logs job/memory-cleanup-retention-xxx -n neural-hive
```

3. Verificar dry-run mode:
```bash
kubectl get configmap memory-layer-policies -o yaml | grep DRY_RUN
```

### Job falhando

1. Verificar conexão com datastores:
```bash
kubectl exec -it memory-layer-api-pod -- python -c "
from src.clients.mongodb_client import MongoDBClient
print('MongoDB OK')
"
```

2. Verificar permissões de delete
