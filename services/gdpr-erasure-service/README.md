# GDPR Erasure Service

> **Gap P0-7** — Right to Erasure conforme GDPR Artigo 17

## Descrição

Microserviço para gerenciar solicitações de exclusão de dados pessoais (Right to be Forgotten) conforme exigido pelo GDPR Artigo 17.

## Funcionalidades

- ✅ Solicitação de exclusão via email com token de verificação SHA-256
- ✅ Workflow de estados: PENDING → VERIFIED → PROCESSING → COMPLETED
- ✅ 3 escopos: MINIMAL, STANDARD, FULL
- ✅ 8 tipos de dados mapeados para 6 serviços externos
- ✅ PII masking em logs
- ✅ Health checks para MongoDB, Redis, Kafka

## Endpoints API

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/v1/gdpr/erasure` | Criar solicitação de exclusão |
| POST | `/api/v1/gdpr/erasure/{id}/verify` | Verificar token por email |
| POST | `/api/v1/gdpr/erasure/{id}/process` | Iniciar processamento |
| GET | `/api/v1/gdpr/erasure/{id}` | Consultar status |

## Desenvolvimento Local

```bash
# Subir infraestrutura + serviço
docker-compose up -d

# Ver logs
docker-compose logs -f gdpr-erasure-service

# Testar health check
curl http://localhost:8010/api/v1/health

# Testar ready check
curl http://localhost:8010/api/v1/health/ready

# Criar solicitação de exclusão
curl -X POST "http://localhost:8010/api/v1/gdpr/erasure?user_id=user-123" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "scope": "standard",
    "data_types": ["approvals"],
    "reason": "Testing erasure"
  }'

# Verificar status
curl http://localhost:8010/api/v1/gdpr/erasure/{request_id}

# Derrubar
docker-compose down
```

## Testes

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar testes
pytest tests/ -v

# Com coverage
pytest tests/ --cov=src --cov-report=html

# Ver relatório de coverage
xdg-open htmlcov/index.html
```

## Deploy em Kubernetes

```bash
# Aplicar manifestos
kubectl apply -f deploy.yaml

# Verificar deployment
kubectl rollout status deployment/gdpr-erasure-service -n nhm-services

# Ver logs
kubectl logs -f deployment/gdpr-erasure-service -n nhm-services

# Scale manual
kubectl scale deployment/gdpr-erasure-service --replicas=3 -n nhm-services
```

## Variáveis de Ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `API_HOST` | Host da API | `0.0.0.0` |
| `API_PORT` | Porta da API | `8010` |
| `MONGODB_URL` | URL MongoDB | `mongodb://localhost:27017` |
| `MONGODB_DATABASE` | Database MongoDB | `nhmgdpr` |
| `REDIS_URL` | URL Redis | `redis://localhost:6379/0` |
| `REDIS_TOKEN_TTL` | TTL token (segundos) | `3600` |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers | `localhost:9092` |
| `VERIFICATION_TOKEN_SALT` | Salt para token SHA-256 | - |
| `ERASURE_RETENTION_DAYS` | Retenção dados (dias) | `90` |
| `CORS_ORIGINS` | Origins permitidas | `*` |

## Tipos de Dados

| DataType | Service Alvo |
|----------|--------------|
| `approvals` | approval-service |
| `specialist_feedback` | approval-service |
| `continuous_feedback` | approval-service |
| `consensus_history` | consensus-engine |
| `execution_tickets` | execution-ticket-service |
| `memory_entries` | memory-layer-api |
| `intent_history` | gateway-intencoes |
| `metrics_logs` | observability |

## Workflow de Estados

```
PENDING_VERIFICATION (token enviado por email)
         ↓
    [token verificado]
         ↓
       VERIFIED
         ↓
 [usuário confirma / auto-process]
         ↓
     PROCESSING (comandos enviados aos serviços)
         ↓
 [todos serviços respondem]
         ↓
  ┌──────┴──────┐
  ↓             ↓
COMPLETED   PARTIALLY_COMPLETED
  ↓             ↓
 (cleanup após 90 dias)
```

## Kafka Topics

| Topic | Tipo | Descrição |
|-------|------|-----------|
| `gdpr.erasure.commands` | Producer | Envia comandos de exclusão para serviços |
| `gdpr.erasure.reports` | Consumer | Recebe relatórios de conclusão dos serviços |

## Monitoramento

### Métricas (Prometheus)

- `gdpr_erasure_requests_total` — Total de solicitações
- `gdpr_erasure_requests_by_status` — Solicitações por status
- `gdpr_erasure_processing_duration_seconds` — Duração do processamento

### Health Checks

- `/api/v1/health` — Liveness (serviço rodando)
- `/api/v1/health/ready` — Readiness (dependências OK)

## Segurança

- ✅ Tokens SHA-256 com salt único
- ✅ TTL de 1 hora para tokens
- ✅ PII masking em logs
- ✅ Verificação de email obrigatória
- ✅ Rate limiting recomendado via ingress

## GDPR Compliance

- ✅ Resposta dentro de 30 dias (monitoramento via dashboard)
- ✅ Retenção mínima de 90 dias para auditoria
- ✅ Exclusão em múltiplos serviços (multi-system)
- ✅ Confirmação de email (prova de consentimento)
- ✅ Log de todas as operações

## Próximos Passos

1. **Email integration** — Enviar tokens via SMTP/SES
2. **Dashboard** — Interface administrativa para monitoring
3. **Service deleters** — Implementar lógica de exclusão nos serviços externos
4. **Rate limiting** — Proteger contra abuso da API

## Licença

MIT — Neural Hive-Mind Project
