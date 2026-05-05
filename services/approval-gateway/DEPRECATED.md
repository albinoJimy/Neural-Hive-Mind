# ⚠️ DEPRECATED - Approval Gateway

**Status:** **DEPRECATED** - Este serviço foi substituído pelo **approval-service** (porta :8004)

## Data de Deprecação

**2026-05-05** - Unified Gateway Architecture (T13)

## Motivo

O approval-gateway (porta :8017) foi consolidado no approval-service (porta :8004) como parte da arquitetura unificada. O approval-service agora:

1. Usa **Approval Core Package** (`neural_hive_approval_common`) para lógica compartilhada
2. Expõe todos os endpoints de aprovação via REST API
3. Integra com NLU/PII Services via gRPC
4. Fornece funcionalidades adicionais (Active Learning, ML Management, Dashboard)

## Migração

### Clientes usando `approval-gateway:8017`

Mudar para `approval-service:8004`. Os endpoints equivalentes estão disponíveis:

| Approval Gateway (Antigo) | Approval Service (Novo) |
|---------------------------|-------------------------|
| `POST /approve` | `POST /api/v1/approvals/{plan_id}/approve` |
| `GET /{request_id}` | `GET /api/v1/approvals/{plan_id}` |
| `PUT /approve/{request_id}` | `POST /api/v1/approvals/{plan_id}/approve` |
| `GET ""` (listar) | `GET /api/v1/approvals/pending` |
| `GET /metrics` | `GET /api/v1/approvals/stats` |
| `POST /expire` | Verificar implementação específica |

### Porta

- **Antigo:** `approval-gateway:8017`
- **Novo:** `approval-service:8004`

## Compatibilidade

O approval-service mantém compatibilidade com o Approval Core Package para:
- Modelos de dados (`ApprovalRequest`, `ApprovalDecision`, `RiskBand`)
- Lógica de decisão
- Integração Kafka

## Timeline de Remoção

- **2026-05-05:** Marcado como DEPRECATED
- **2026-06-01 (planejado):** Service pode ser removido após migração completa dos clientes

## Contato

Para dúvidas sobre migração, consulte a equipe de arquitetura ou o spec:
`.agent-os/specs/2026-05-01-unified-gateway-architecture/spec.md`
