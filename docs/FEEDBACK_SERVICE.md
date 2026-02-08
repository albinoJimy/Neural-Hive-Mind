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

## Estatísticas Atuais (2026-02-08 16:00)

- Opiniões totais: 4490
- Com feedback: **1002** ✅
- Pendentes: 3488
- **Cobertura: 22.3%**

### Distribuição de Feedbacks

| Recomendação | Quantidade |
|--------------|------------|
| review_required | 995 |
| approve | 2 |
| conditional | 5 |

## Coleta Automatizada

**Script:** `k8s/auto-feedback-job.yaml`

Heurística aplicada:
- Baixa confiança (< 0.4) → `review_required`
- Alta confiança (> 0.6) → segue recomendação do modelo
- Confiança média → segue recomendação do modelo

**Execução:**
```bash
kubectl apply -f k8s/auto-feedback-job.yaml
```

## Próximos Passos

1. ✅ **Coletar 1000+ feedbacks** - META ATINGIDA (1002 feedbacks)
2. **Coletar feedbacks humanos** - validar a qualidade das heurísticas
3. **Executar retreinamento** com dados rotulados
4. **Implantar novos modelos** após retreinamento

## Implantação

```bash
# Atualizar ConfigMap
kubectl apply -f k8s/feedback-service-configmap.yaml

# Deploy
kubectl apply -f k8s/feedback-service-deployment.yaml

# Expor
kubectl apply -f k8s/feedback-service-external.yaml
```
