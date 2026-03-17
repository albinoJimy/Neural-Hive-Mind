# Relatório Retraining V6 - NLP Features

**Data:** 2026-03-17
**Status:** ✅ SUCESSO
**F1-Score:** 0.9120

## Resumo Executivo

O modelo v6 treinado com features NLP alcançou **F1-Score de 0.91**, superando largamente a meta de 0.7 e o baseline de 0.51. Isto representa uma melhoria de **78%** sobre o modelo anterior.

## Dados de Treino

| Métrica | Valor |
|---------|-------|
| Total de feedbacks | 75 |
| Treino | 52 (70%) |
| Teste | 23 (30%) |
| Features | 30 |

## Distribuição de Classes

| Classe | Treino | Teste | Total |
|--------|--------|-------|-------|
| approve | 25 | 11 | 36 (48%) |
| reject | 14 | 6 | 20 (27%) |
| review_required | 13 | 6 | 19 (25%) |

## Resultados por Modelo

### RandomForest
- **F1-Score:** 0.9120
- **Precision:** 0.9255
- **Recall:** 0.9130

### GradientBoosting
- **F1-Score:** 0.9120
- **Precision:** 0.9255
- **Recall:** 0.9130

## Feature Importance (Top 10)

| Feature | Importância |
|---------|-------------|
| specialist_confidence | 0.5731 |
| simple_risk_score | 0.2232 |
| text_length_chars | 0.0751 |
| text_length_words | 0.0400 |
| primary_action_create | 0.0190 |
| risk_high | 0.0144 |
| action_delete | 0.0129 |
| primary_action_delete | 0.0076 |
| primary_domain_security | 0.0062 |
| domain_database | 0.0056 |

## MLflow Run

**Run ID:** `retraining_v6_nlp_20260317_142249`
**URL:** http://mlflow.mlflow.svc.cluster.local:5000/#/experiments/25/runs/b2e9b27c3dd04cd7a0b24be8a97814b0

## Próximos Passos

1. ✅ Treino concluído com sucesso
2. ⏳ Deploy do modelo v6 para produção
3. ⏳ Monitoramento de performance em produção
4. ⏳ Coleta de mais feedbacks para validação

## Conclusão

O modelo v6 com NLP features está pronto para deploy. Com F1-Score de 0.91 e dados balanceados, espera-se uma melhoria significativa na qualidade das recomendações de aprovação.
