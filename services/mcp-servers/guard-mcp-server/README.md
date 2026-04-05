# Guard MCP Server

Servidor MCP (Model Context Protocol) que fornece ferramentas de validacao de segurança, deteccao de ameaças e remediação para o Neural Hive Mind.

## Descrição

O Guard MCP Server expõe ferramentas de segurança através do protocolo Anthropic MCP, permitindo que agentes de IA validem ExecutionTickets, escaneiem vulnerabilidades, detectem ameaças em tempo real e executem ações de remediação.

O servidor integra-se com:
- **Guard Agents** (porta 8008) - Validações de segurança e detecção de ameaças
- **Trivy** (porta 8080) - Scanner de vulnerabilidades
- **OPA** (porta 8181) - Open Policy Agent para políticas de autorização

## Funcionalidades

| Ferramenta | Descrição |
|------------|-----------|
| `validate_security` | Validar políticas de segurança OPA, RBAC e secrets para ExecutionTickets |
| `scan_vulnerabilities` | Escanear vulnerabilidades em imagens Docker, código e dependências via Trivy |
| `detect_threats` | Detectar ameaças em tempo real em eventos de segurança |
| `check_compliance` | Verificar compliance regulatório (GDPR, SOC2, ISO27001) |
| `remediate_issue` | Executar ações de remediação automática ou manual |

## Instalação

### Pré-requisitos

- Python 3.12+
- Docker (para containerização)
- Kubernetes/Helm (para deploy em cluster)
- Acesso ao Guard Agents, Trivy e OPA

### Instalação Local

```bash
# Clonar o repositório
cd /home/jimy/NHM/Neural-Hive-Mind/services/mcp-servers/guard-mcp-server

# Criar virtualenv
python -m venv .venv
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

### Execução Local

```bash
# Via Python
python -m guard_mcp_server

# Via Uvicorn (com hot reload)
uvicorn guard_mcp_server.app:app --host 0.0.0.0 --port 3014 --reload
```

### Execução via Docker

```bash
# Build da imagem
docker build -t guard-mcp-server:latest .

# Executar container
docker run -p 3014:3014 \
  -e GUARD_MCP_GUARD_AGENT_HOST=guard-agents \
  -e GUARD_MCP_GUARD_AGENT_PORT=8008 \
  guard-mcp-server:latest
```

### Deploy via Helm

```bash
# Instalar chart
helm install guard-mcp-server ./helm/guard-mcp-server \
  --namespace neural-hive-mind \
  --create-namespace

# Upgrade
helm upgrade guard-mcp-server ./helm/guard-mcp-server \
  --namespace neural-hive-mind

# Uninstall
helm uninstall guard-mcp-server --namespace neural-hive-mind
```

## Configuração

### Variáveis de Ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `GUARD_MCP_PORT` | Porta do servidor HTTP | `3015` |
| `GUARD_MCP_LOG_LEVEL` | Nível de log | `INFO` |
| `GUARD_MCP_GUARD_AGENT_HOST` | Host do Guard Agent | `guard-agents` |
| `GUARD_MCP_GUARD_AGENT_PORT` | Porta do Guard Agent | `8008` |
| `GUARD_MCP_TRIVY_HOST` | Host do Trivy | `trivy` |
| `GUARD_MCP_TRIVY_PORT` | Porta do Trivy | `8080` |
| `GUARD_MCP_OPA_HOST` | Host do OPA | `opa` |
| `GUARD_MCP_OPA_PORT` | Porta do OPA | `8181` |
| `GUARD_MCP_VALIDATION_TIMEOUT` | Timeout de validação (segundos) | `300` |

### Configuração Helm

```yaml
# helm/guard-mcp-server/values.yaml

image:
  repository: 37.60.241.150:30500/guard-mcp-server
  tag: "1.0.0"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  ports:
    http: 3014

resources:
  requests:
    cpu: 50m
    memory: 128Mi
  limits:
    cpu: 200m
    memory: 256Mi

autoscaling:
  enabled: false
  minReplicas: 1
  maxReplicas: 3
```

## Integração OPA

O Guard MCP Server utiliza o Open Policy Agent (OPA) para validar políticas de segurança:

### Tipos de Validação

1. **RBAC (Role-Based Access Control)**
   - Verifica permissões de service accounts
   - Valida acesso a namespaces e recursos

2. **Secrets Management**
   - Valida acesso a secrets Kubernetes
   - Verifica compliance com políticas de dados sensíveis

3. **Execution Tickets**
   - Valida parametros de tickets antes da execução
   - Verifica nível de segurança (INTERNAL, CONFIDENTIAL, RESTRICTED)

### Exemplo de Política OPA

```rego
package neural_hive_mind

default allow = false

allow {
    input.task_type == "DEPLOY"
    input.security_level == "CONFIDENTIAL"
    input.environment == "production"
    count(input.violations) == 0
}
```

## API das Ferramentas

### validate_security

Valida políticas de segurança para um ExecutionTicket.

```python
await validate_security(
    ticket_id="ticket-123",
    task_type="DEPLOY",
    environment="production",
    security_level="CONFIDENTIAL"
)
```

**Resposta:**
```json
{
  "validation_id": "val-abc123",
  "validation_status": "approved",
  "violations": [],
  "risk_assessment": {
    "level": "LOW",
    "score": 15
  }
}
```

### scan_vulnerabilities

Escanear vulnerabilidades em uma imagem ou código.

```python
await scan_vulnerabilities(
    target="nginx:latest",
    scan_type="container"
)
```

**Tipos de scan:** `container`, `code`, `dependency`, `filesystem`, `repository`

**Resposta:**
```json
{
  "scan_id": "scan-xyz789",
  "scan_status": "completed",
  "vulnerabilities": [
    {
      "vulnerability_id": "CVE-2024-1234",
      "severity": "HIGH",
      "package": "openssl",
      "installed_version": "1.1.1",
      "fixed_version": "1.1.1k"
    }
  ],
  "summary": {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 5
  }
}
```

### detect_threats

Detectar ameaças em tempo real em eventos de segurança.

```python
await detect_threats(
    event_type="authentication",
    event_data={
        "event_id": "event-456",
        "user_id": "user-123",
        "failed_attempts": 7,
        "source_ip": "192.168.1.100"
    }
)
```

**Tipos de evento:** `authentication`, `request_metrics`, `resource_access`, `data_access`

**Resposta:**
```json
{
  "threat_id": "threat-999",
  "threat_found": true,
  "threat_type": "BRUTE_FORCE",
  "severity": "HIGH",
  "confidence": 0.92,
  "recommended_action": "block_ip"
}
```

### check_compliance

Verificar compliance regulatório para um ticket.

```python
await check_compliance(
    ticket_id="ticket-123",
    regulations=["GDPR", "SOC2", "ISO27001"]
)
```

**Regulamentos suportados:** `GDPR`, `SOC2`, `ISO27001`, `PCI_DSS`, `HIPAA`

**Resposta:**
```json
{
  "compliant": true,
  "breaches": [],
  "regulations": {
    "GDPR": {
      "compliant": true,
      "articles_checked": 12
    },
    "SOC2": {
      "compliant": true,
      "criteria_checked": 8
    }
  }
}
```

### remediate_issue

Executar ação de remediação para uma violação de segurança.

```python
await remediate_issue(
    issue_id="issue-789",
    remediation_type="block_ip",
    parameters={"ip": "192.168.1.100", "duration": 3600}
)
```

**Tipos de remediação:** `block_ip`, `kill_process`, `isolate_container`, `revoke_token`, `rollback_deployment`, `manual_intervention`

**Resposta:**
```json
{
  "success": true,
  "remediation_id": "rem-456",
  "status": "completed",
  "message": "IP bloqueado com sucesso"
}
```

## Endpoints HTTP

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/health` | GET | Health check do serviço |
| `/ready` | GET | Readiness check do serviço |
| `/metrics` | GET | Métricas Prometheus |

## Desenvolvimento

### Estrutura de Diretórios

```
guard-mcp-server/
├── src/guard_mcp_server/
│   ├── __init__.py
│   ├── server.py          # Servidor MCP
│   ├── app.py             # Aplicação FastAPI
│   ├── main.py            # Entry point
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py    # Configurações
│   └── tools/
│       ├── __init__.py
│       └── guard_tools.py # Implementação das ferramentas
├── tests/
│   ├── conftest.py
│   └── test_guard_tools_tdd.py
├── helm/
│   └── guard-mcp-server/  # Chart Helm
├── Dockerfile
├── requirements.txt
└── README.md
```

### Executar Testes

```bash
# Testes unitários
pytest tests/ -v

# Testes com cobertura
pytest tests/ --cov=src/guard_mcp_server --cov-report=html

# Testes com relatório HTML
pytest tests/ --cov=src/guard_mcp_server --cov-report=term-missing
```

### Linting e Formatação

```bash
# Linting com ruff
ruff check src/ tests/

# Formatação com black
black src/ tests/

# Type checking com mypy
mypy src/
```

## Monitorização

O servidor expõe métricas Prometheus no endpoint `/metrics`:

- `guard_mcp_requests_total` - Total de requests
- `guard_mcp_request_duration_seconds` - Duração dos requests
- `guard_mcp_validations_total` - Total de validações
- `guard_mcp_scans_total` - Total de scans
- `guard_mcp_threats_detected_total` - Total de ameaças detectadas

## Health Checks

```bash
# Health check
curl http://localhost:3014/health

# Readiness check
curl http://localhost:3014/ready
```

## Troubleshooting

### Problemas Comuns

**Servidor não inicia:**
- Verificar se as portas estão disponíveis
- Confirmar conectividade com Guard Agents e Trivy

**Validações falham:**
- Verificar logs do Guard Agent
- Confirmar políticas OPA estão carregadas

**Scans demoram muito:**
- Ajustar `GUARD_MCP_VALIDATION_TIMEOUT`
- Verificar recursos do Trivy

### Logs

```bash
# Ver logs do container
docker logs guard-mcp-server -f

# Ver logs no Kubernetes
kubectl logs -l app=guard-mcp-server -n neural-hive-mind -f
```

## Contribuição

Ver `/home/jimy/NHM/Neural-Hive-Mind/CLAUDE.md` para diretrizes de desenvolvimento.

## Licença

Neural Hive Mind - Internal Use Only
