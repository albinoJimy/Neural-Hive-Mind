# Guia de Auditoria de Compliance - Authorization Audit Log

## Visao Geral

O Authorization Audit Log registra todas as decisoes de autorizacao tomadas pelo OPA (Open Policy Agent) no Orchestrator Dynamic, fornecendo rastreabilidade completa para compliance com GDPR, SOC2 e outras regulamentacoes.

## Dados Auditados

Cada decisao de autorizacao registra:

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `timestamp` | string | Data/hora da decisao (ISO 8601) |
| `user_id` | string | ID do usuario (se disponivel) |
| `tenant_id` | string | ID do tenant |
| `resource` | object | Recurso sendo acessado (type, id, task_type) |
| `action` | string | Acao sendo executada |
| `decision` | string | 'allow' ou 'deny' |
| `policy_path` | string | Politica OPA avaliada |
| `violations` | array | Lista de violacoes (se deny) |
| `context` | object | Contexto adicional (workflow_id, plan_id, correlation_id) |

### Exemplo de Entrada de Audit

```json
{
  "timestamp": "2026-01-24T10:30:45.123Z",
  "user_id": "user-456",
  "tenant_id": "tenant-123",
  "resource": {
    "type": "ticket",
    "id": "ticket-789",
    "task_type": "code_generation"
  },
  "action": "create",
  "decision": "allow",
  "policy_path": "neuralhive/orchestrator/security_constraints",
  "violations": [],
  "context": {
    "workflow_id": "wf-abc123",
    "plan_id": "plan-def456",
    "correlation_id": "corr-ghi789"
  }
}
```

## Retencao de Dados

- **Periodo de retencao**: 90 dias (configuravel via `AUDIT_RETENTION_DAYS`)
- **Armazenamento**: MongoDB collection `authorization_audit`
- **Backup**: Incluido no backup diario do MongoDB
- **Indices**: 8 indices para queries eficientes

## Consultas de Auditoria

### API REST

```bash
# Listar todas as decisoes de um tenant
curl "http://orchestrator-dynamic:8000/api/v1/audit/authorizations?tenant_id=tenant-123&limit=100"

# Listar apenas decisoes 'deny'
curl "http://orchestrator-dynamic:8000/api/v1/audit/authorizations?decision=deny&limit=50"

# Filtrar por periodo
curl "http://orchestrator-dynamic:8000/api/v1/audit/authorizations?start_time=2026-01-01T00:00:00Z&end_time=2026-01-31T23:59:59Z"

# Filtrar por usuario
curl "http://orchestrator-dynamic:8000/api/v1/audit/authorizations?user_id=user-456"

# Filtrar por politica
curl "http://orchestrator-dynamic:8000/api/v1/audit/authorizations?policy_path=neuralhive/orchestrator/security_constraints"

# Paginacao
curl "http://orchestrator-dynamic:8000/api/v1/audit/authorizations?limit=50&skip=100"
```

### Resposta da API

```json
{
  "total": 1234,
  "results": [
    {
      "timestamp": "2026-01-24T10:30:45.123Z",
      "user_id": "user-456",
      "tenant_id": "tenant-123",
      "decision": "allow",
      "policy_path": "neuralhive/orchestrator/security_constraints",
      "...": "..."
    }
  ],
  "query": {
    "tenant_id": "tenant-123",
    "limit": 100,
    "skip": 0
  }
}
```

### MongoDB Queries

```javascript
// Contar decisoes por tenant
db.authorization_audit.aggregate([
  { $group: { _id: "$tenant_id", count: { $sum: 1 } } }
])

// Listar violacoes de seguranca
db.authorization_audit.find({
  decision: "deny",
  "violations.severity": "critical"
}).sort({ timestamp: -1 })

// Auditoria de acesso de usuario especifico
db.authorization_audit.find({
  user_id: "user-123"
}).sort({ timestamp: -1 })

// Decisoes nas ultimas 24 horas
db.authorization_audit.find({
  timestamp: { $gte: new Date(Date.now() - 24*60*60*1000).toISOString() }
}).count()

// Top 10 tenants com mais denies
db.authorization_audit.aggregate([
  { $match: { decision: "deny" } },
  { $group: { _id: "$tenant_id", count: { $sum: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 10 }
])
```

## Dashboard Grafana

Acesse: `http://grafana:3000/d/authorization-audit`

### Paineis Disponiveis

| Painel | Descricao |
|--------|-----------|
| Authorization Decisions Over Time | Taxa de decisoes allow/deny ao longo do tempo |
| Deny Rate | Gauge mostrando taxa de deny atual |
| Total Decisions (24h) | Total de decisoes nas ultimas 24 horas |
| Decisions by Policy | Tabela com contagem por politica e decisao |
| Deny Rate by Tenant | Grafico de taxa de deny por tenant |
| Audit Query Performance | Latencia p95/p99 de queries de auditoria |
| Top 10 Denied Resources | Recursos mais frequentemente negados |
| Audit Log Volume Trend | Tendencia de volume de logs |

## Compliance

### GDPR (Art. 30 - Records of Processing Activities)

O audit log atende aos requisitos de:

| Requisito GDPR | Como Atendido |
|----------------|---------------|
| Registro de operacoes de processamento | Campo `action` e `timestamp` |
| Identificacao de controlador/processador | Campo `tenant_id` |
| Finalidade do processamento | Campo `action` e `context` |
| Categorias de dados | Campo `resource.type` |
| Registro de acessos | Campos `user_id` e `decision` |

### SOC2 (CC6.3 - Logical Access Controls)

O audit log fornece:

| Requisito SOC2 | Como Atendido |
|----------------|---------------|
| Rastreamento de decisoes de acesso | Todos os campos de audit |
| Identificacao de tentativas de acesso negadas | Campo `decision="deny"` |
| Contexto de decisoes de autorizacao | Campos `violations` e `context` |
| Retencao de logs | 90 dias com backup |

### Exportacao para Compliance

```bash
# Exportar audit log para JSON (ultimo mes)
mongoexport --db neural_hive --collection authorization_audit \
  --query '{"timestamp": {"$gte": "2026-01-01T00:00:00Z"}}' \
  --out audit_log_jan_2026.json

# Exportar para CSV
mongoexport --db neural_hive --collection authorization_audit \
  --type=csv --fields=timestamp,tenant_id,user_id,decision,policy_path \
  --out audit_log.csv

# Exportar apenas denies para investigacao
mongoexport --db neural_hive --collection authorization_audit \
  --query '{"decision": "deny"}' \
  --out denied_requests.json
```

## Metricas Prometheus

| Metrica | Tipo | Descricao |
|---------|------|-----------|
| `neural_hive_authorization_audit_logged_total` | Counter | Total de decisoes auditadas |
| `neural_hive_authorization_audit_errors_total` | Counter | Total de erros ao auditar |
| `neural_hive_authorization_audit_query_duration_seconds` | Histogram | Duracao de queries |

### Queries PromQL Uteis

```promql
# Taxa de decisoes por segundo
sum(rate(neural_hive_authorization_audit_logged_total[5m])) by (decision)

# Taxa de deny (porcentagem)
sum(rate(neural_hive_authorization_audit_logged_total{decision="deny"}[5m]))
/ sum(rate(neural_hive_authorization_audit_logged_total[5m])) * 100

# Latencia p99 de queries
histogram_quantile(0.99, rate(neural_hive_authorization_audit_query_duration_seconds_bucket[5m]))

# Erros de audit nas ultimas 24h
sum(increase(neural_hive_authorization_audit_errors_total[24h]))
```

## Alertas

Alertas configurados em `monitoring/alerts/authorization-audit-alerts.yaml`:

| Alerta | Condicao | Severidade |
|--------|----------|------------|
| HighDenyRate | Taxa de deny > 10% em 5min | warning |
| UnauthorizedAccessAttempts | > 5 denies do mesmo user_id em 1min | critical |
| PolicyViolationSpike | Aumento subito de violacoes | warning |
| AuditLogFailures | Erros de persistencia > 10 em 5min | critical |

## Troubleshooting

### Audit log nao esta sendo gerado

1. Verificar se MongoDB esta disponivel:
   ```bash
   kubectl logs -n neural-hive orchestrator-dynamic-xxx | grep mongodb_client_ready
   ```

2. Verificar se OPA Client tem referencia ao MongoDB:
   ```bash
   kubectl logs -n neural-hive orchestrator-dynamic-xxx | grep "OPA Policy Engine inicializado"
   # Deve mostrar: audit_logging_enabled=True
   ```

3. Verificar metricas:
   ```promql
   rate(neural_hive_authorization_audit_logged_total[5m])
   ```

### Performance de queries lenta

1. Verificar indices:
   ```javascript
   db.authorization_audit.getIndexes()
   ```

2. Adicionar indice composto se necessario:
   ```javascript
   db.authorization_audit.createIndex({ tenant_id: 1, timestamp: -1, decision: 1 })
   ```

3. Verificar tamanho da collection:
   ```javascript
   db.authorization_audit.stats()
   ```

### Dados faltando no audit log

1. Verificar se OPA esta retornando resultados:
   ```bash
   kubectl logs -n neural-hive orchestrator-dynamic-xxx | grep "opa_policy_evaluation"
   ```

2. Verificar erros de persistencia:
   ```promql
   sum(rate(neural_hive_authorization_audit_errors_total[5m])) by (error_type)
   ```

## Seguranca

- **Acesso ao audit log**: Restrito a roles `admin` e `auditor`
- **Imutabilidade**: Registros nao podem ser modificados apos criacao
- **Criptografia**: Dados em repouso criptografados (MongoDB encryption at rest)
- **Transmissao**: TLS 1.3 para queries via API
- **Fail-open**: Erros de audit nao bloqueiam operacoes criticas

## Arquitetura

```
                                    +-------------------+
                                    |   API Clients     |
                                    +--------+----------+
                                             |
                                             v
+----------------+     +------------+     +------------------+
|  OPA Server    |<--->| OPA Client |---->| MongoDB          |
+----------------+     +-----+------+     | (authorization   |
                             |            |  _audit)         |
                             v            +--------+---------+
                      +------+------+              |
                      |   Metrics   |              v
                      | (Prometheus)|     +--------+---------+
                      +-------------+     |   Grafana        |
                                          |   Dashboard      |
                                          +------------------+
```

## Referencias

- [OPA Best Practices](https://www.openpolicyagent.org/docs/latest/)
- [GDPR Art. 30](https://gdpr-info.eu/art-30-gdpr/)
- [SOC2 Trust Services Criteria](https://www.aicpa.org/interestareas/frc/assuranceadvisoryservices/trustdataintegritytaskforce)
- [MongoDB Security Checklist](https://docs.mongodb.com/manual/administration/security-checklist/)
