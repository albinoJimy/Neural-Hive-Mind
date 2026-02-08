# Serviço de Coleta de Feedback

## Status

✅ **Implantado e Funcional** (2026-02-08)

## Interface Web

Uma interface web amigável está disponível para facilitar a coleta de feedback:

**URL:** `http://37.60.241.150:30080`

A interface permite:
- Visualizar opiniões pendentes de forma organizada
- Filtrar por tipo de especialista
- Submeter feedback com poucos cliques
- Acompanhar estatísticas de progresso

## Descrição

Serviço HTTP para coleta de feedback humano sobre opiniões dos especialistas ML. O feedback coletado será usado para retreinar os modelos com dados reais rotulados.

## Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/` | Interface web de coleta |
| GET | `/health` | Health check |
| GET | `/api/v1/feedback/stats` | Estatísticas de feedback coletado |
| GET | `/api/v1/opinions/pending` | Lista opiniões pendentes de feedback |
| POST | `/api/v1/feedback` | Submeter feedback sobre uma opinião |

## Acesso Externo

- **URL**: `http://37.60.241.150:30080`
- **Serviço**: `feedback-collection-service-external` (NodePort 30080)

## Exemplo de Uso

### Listar opiniões pendentes
```bash
curl "http://37.60.241.150:30080/api/v1/opinions/pending?limit=10"
```

### Submeter feedback
```bash
curl -X POST "http://37.60.241.150:30080/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "opinion_id": "<opinion_id>",
    "human_recommendation": "approve",
    "human_rating": 0.9,
    "feedback_notes": "Opinião correta"
  }'
```

### Estatísticas
```bash
curl "http://37.60.241.150:30080/api/v1/feedback/stats"
```

## Campos do Feedback

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `opinion_id` | string | ID da opinião sendo avaliada |
| `human_recommendation` | string | `approve`, `reject`, ou `review_required` |
| `human_rating` | float | Rating de concordância (0.0 - 1.0) |
| `feedback_notes` | string | Notas textuais (opcional) |

## Armazenamento

- **Collection**: `specialist_feedback` (MongoDB)
- **Opiniões**: `specialist_opinions` (MongoDB)

## Estatísticas Atuais (2026-02-08 14:42)

- Opiniões totais: 4490
- Com feedback: 1
- Pendentes: 4489

## Próximos Passos

1. **Coletar 1000+ feedbacks** - Meta para retreinamento
2. **Priorizar opiniões** com baixa confiança
3. **Executar retreinamento** com dados rotulados

## Implantação

```bash
# Atualizar ConfigMap
kubectl apply -f k8s/feedback-service-configmap.yaml

# Deploy
kubectl apply -f k8s/feedback-service-deployment.yaml

# Expor
kubectl apply -f k8s/feedback-service-external.yaml
```
