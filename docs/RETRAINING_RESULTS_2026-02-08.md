# ML Retraining Results - 2026-02-08

## Dataset de Feedback

**Total**: 2402 feedbacks coletados

### Distribuição Global

| Recomendação | Quantidade | % |
|--------------|-----------|---|
| review_required | 1555 | 64.7% |
| approve | 482 | 20.1% |
| reject | 360 | 15.0% |
| conditional | 5 | 0.2% |

### Por Especialista

| Especialista | Feedbacks | Approve | Reject | Review |
|--------------|-----------|---------|--------|--------|
| technical | 485 | ~98 | ~73 | ~314 |
| architecture | 480 | ~96 | ~72 | ~312 |
| evolution | 480 | ~96 | ~72 | ~312 |
| business | 479 | ~96 | ~71 | ~312 |
| behavior | 478 | ~96 | ~70 | ~312 |

## Resultados do Retreinamento

### Tentativa 1: Com feature `human_rating`

**Problema**: Data leakage - `human_rating` é derivado do próprio feedback.

| Métrica | Valor |
|---------|-------|
| Accuracy | 1.000 |
| Precision | 1.000 |
| Recall | 1.000 |
| F1 Score | 1.000 |

**Feature Importances**:
- human_rating: 95.97%
- confidence_score: 1.30%
- (outras: <1%)

**Conclusão**: Modelo inválido devido a data leakage.

### Tentativa 2: Sem `human_rating` (V2)

**Dataset**: 479 feedbacks business (20% approve)

| Métrica | Valor |
|---------|-------|
| Accuracy | 0.802 |
| Precision (approve) | 0.000 |
| Recall (approve) | 0.000 |
| F1 (approve) | 0.000 |
| AUC-ROC | 0.552 |
| CV F1 (mean) | 0.000 |

**Feature Importances**:
- confidence_score: 69.2%
- opinion_rec_review: 30.8%
- (outras: 0%)

**Conclusão**: O modelo **não consegue prever a classe positiva**.

## Análise do Problema

### Causa Raiz

As features originais do modelo (**confidence_score**, **risk_score**, **opinion_rec_**)
têm **pouco poder preditivo** para diferenciar approve de reject/review.

### Por que as features são insuficientes?

1. **Confidence Score ~50%**: Treinado com dados sintéticos, o modelo sempre tem baixa confiança
2. **Recomendação do Modelo**: Sempre "review_required" quando confiança < 0.7
3. **Sem contexto do plano**: As features não incluem informações sobre:
   - Complexidade do plano
   - Tipo de mudança solicitada
   - Setor da aplicação
   - Histórico do cliente

## Soluções Propostas

### Opção 1: Engenharia de Features Melhorada

Adicionar features derivadas das opiniões:
- Complexidade do plano (número de tarefas, dependências)
- Tipo de mudança (feature, bug, refactor, etc)
- Setor/prioridade
- Idade da intenção
- Métricas do negócio associadas

### Opção 2: Usar Features do Plano

Incluir features do plano original:
- `plan_complexity`: Número de tarefas, dependências
- `intent_type`: Tipo de mudança
- `business_domain`: Domínio do negócio
- `priority`: Prioridade do ticket

### Opção 3: Aumentar Dataset com Features Reais

Usar o Real Data Collector para incluir features ricas:
- Ver `/ml_pipelines/training/real_data_collector.py`
- Coletar dados históricos com features adicionais

## MLflow Runs

| Run ID | Modelo | Status | Notas |
|--------|-------|--------|-------|
| fa606c9601d641239886722087844472 | RF | Data leakage | human_rating como feature |
| 8fca481c1b424230930336a1bb33cfa3 | GB | Baixa performance | Não prevê classe positiva |

## Conclusão

O retreinamento com features atuais **não é eficaz**. Precisamos:

1. ✅ **Dataset balanceado** - Atingido (2402 feedbacks, 20% approve)
2. ⚠️ **Features preditivas** - Insuficientes
3. 🔄 **Engenharia de features** - Próximo passo necessário

---

**Data**: 2026-02-08
**Status**: Coleta completa, Retreinamento requer melhor engenharia de features
