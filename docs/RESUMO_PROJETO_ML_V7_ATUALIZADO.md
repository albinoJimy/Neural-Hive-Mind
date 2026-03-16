# Resumo: Projeto ML - Modelo v7 em Produção

**Data:** 2026-03-16
**Status:** ✅ PRODUÇÃO (v7 Deployado + CronJob Ativo)
**Commits:** `05ca2b2`, `c9b5e5f`

## Deploy Concluído

### Approval Service com ML Predictor v7
- **Imagem:** `ghcr.io/albinojimy/neural-hive-mind/approval-service:05ca2b2`
- **Modelo:** `/app/ml_models/nhm_approval_model.pkl` (v7 internal)
- **Arquivo fonte:** `nhm_approval_model_v7.pkl`
- **Inferência:** `/app/ml_pipelines/inference/approval_predictor.py`

### Endpoints Disponíveis
- `GET /api/v1/approvals/{plan_id}/ml-prediction` - Obter predição ML
- `GET /api/v1/approvals/{plan_id}/auto-decision` - Verificar decisão automática

### Configurações (Variáveis de Ambiente)
```bash
ENABLE_ML_PREDICTION=true
ML_MODEL_PATH=/app/ml_models/nhm_approval_model.pkl
ML_AUTO_APPROVE_THRESHOLD=0.7
ML_AUTO_REJECT_THRESHOLD=0.7
ML_MAX_RISK_FOR_AUTO=low
```

## Modelos Treinados

| Versão | Amostras | F1-Score | Precision | Recall | Arquivo |
|---------|----------|----------|-----------|--------|--------|
| v6 | 50 | 1.0000 | 1.0000 | 1.0000 | `nhm_approval_model_v6.pkl` |
| v7 | 75 | 0.9120 | 0.9255 | 0.9130 | `nhm_approval_model_v7.pkl` |

**Nota:** Modelo v6 tem F1-Score perfeito mas pode ter overfit. Modelo v7 tem melhor generalização.

## Dataset Atual

```
Total com NLP features: 75
Distribuição:
  - approve: 36 (48%)
  - reject: 20 (27%)
  - review_required: 19 (25%)
```

## Top Features (v7)

1. **specialist_confidence** (0.5731) - Confiança do especialista
2. **simple_risk_score** (0.2232) - Score de risco baseado em palavras-chave
3. **text_length_chars** (0.0751) - Comprimento do texto
4. **text_length_words** (0.0400) - Número de palavras
5. **primary_action_create** (0.0190) - Ação primária é criar

## Testes de Predição

| Intenção | Decisão | Confiança |
|----------|---------|-----------|
| Create new user with email verification | approve | 73% |
| Delete all records without backup | reject | 56% |
| Add index for query performance | approve | 74% |
| Enable two-factor authentication | approve | 59% |
| Grant admin privileges to all users | reject | (bloqueado) |

## Scripts Disponíveis

- `scripts/generate_diverse_intents.py` - Gerar intenções de teste
- `ml_pipelines/training/retrain_scheduled.py` - Retreinamento programado
- `ml_pipelines/inference/approval_predictor.py` - API de inferência

## Próximos Passos

1. **Coletar mais feedbacks** (meta: 200+)
2. **CronJob ativo** - Retreinamento automático segundas 2am UTC
3. **Habilitar decisões automáticas** em produção
4. **Monitorar performance** do modelo em produção

## CronJob de Retraining

- **Nome:** `approval-model-retraining`
- **Schedule:** `0 2 * * 1` (Segundas 2am UTC)
- **Namespace:** `neural-hive`
- **Testado:** F1-Score 0.8990 com 75 amostras

O CronJob treina o modelo automaticamente e salva metadata no MongoDB.
Para deploy do novo modelo, treinar localmente e atualizar Dockerfile.

## Commits Relevantes

- `8cad813` - Modelo ML v6 com features NLP
- `251da17` - Integração ML predictor com approval service
- `19ba7c7` - Scripts para coleta contínua e retraining
- `521050b` - Modelo v7 treinado com 75 feedbacks
- `05ca2b2` - Deploy modelo v7 para produção (F1-Score 0.9120)
