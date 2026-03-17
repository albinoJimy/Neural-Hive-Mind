# Plano de Melhoria - Modelos ML Especialistas

**Data:** 2026-03-16
**Status:** Análise Concluída

## 📊 Resumo Executivo

A análise dos 2402 feedbacks coletados revelou que os modelos ML atuais dos especialistas não estão capturando o padrão de decisão humana. A taxa de concordância especialista ↔ humano é de apenas 56.3%, e quando o humano dá rating alto (≥0.7), a concordância cai para 0%.

## 🔍 Problemas Identificados

### 1. Modelos Treinados com Dados Sintéticos
- Confidence score sempre retorna 0.5 (valor genérico)
- Recomendação sempre é "review_required" (conservador)
- Não há correlação entre features geradas e decisão humana

### 2. Features Não-Preditivas
- Features atuais (confidence, risk, semantic_scores) não predizem a decisão humana
- Mesmo com 17 features ricas, F1-score ficou em 0.51
- Feature importance mostra que `complexity_score` e `num_tasks` são mais relevantes

### 3. Dados Desbalanceados
- 65.6% dos feedbacks são "review_required"
- Apenas 18.1% "approve" e 16.3% "reject"
- Modelo tende a prever a classe majoritária

## 🎯 Plano de Ação

### Fase 1: Melhoria Imediata (1-2 semanas)

#### 1.1 Coleta de Mais Features no Momento da Decisão
**Status:** 🔴 Crítico

Atualmente, os feedbacks humanos são coletados **após** a decisão do especialista. Precisamos capturar mais contexto:

```python
# Adicionar ao feedback collection:
{
    "opinion_id": "...",
    "human_recommendation": "approve",
    "human_rating": 0.9,
    # NOVOS CAMPOS:
    "intent_raw_text": "...",        # Texto original da intenção
    "plan_summary": "...",            # Resumo do plano gerado
    "cognitive_plan_snapshot": {},    # Plano completo no momento
    "user_context": {},               # Contexto do usuário
    "timestamp": "2026-03-16..."
}
```

#### 1.2 Engenharia de Features Baseada em NLP
**Status:** 🟡 Importante

Extrair features linguísticas do texto da intenção:
- Comprimento do texto
- Palavras-chave técnicas
- Complexidade da linguagem
- Sentimento aproximado
- Domínio (security, performance, architecture, etc.)

#### 1.3 Modelo de Backup para Casos de Baixa Confiança
**Status:** 🟢 Fácil vitória

Quando confiança < 0.6, usar:
- Approve para cases simples
- Reject para patterns claramente ruins
- Review_required para casos complexos

### Fase 2: Retraining com Novas Features (2-4 semanas)

#### 2.1 Pipeline de Features Enriquecido
```python
# Novas features a extrair:
- Intent text embeddings (BERT/transformer)
- Code diff metrics (se aplicável)
- Historical performance (se usuário repetido)
- Time of day, day of week
- Previous decisions by same human reviewer
```

#### 2.2 Ensemble de Modelos
```python
# Combinar múltiplos modelos:
- Random Forest (para features tabulares)
- Gradient Boosting (para features numéricas)
- Logistic Regression (para interpretabilidade)
- Neural Network (para embeddings de texto)
```

#### 2.3 Cross-Validation Robusto
- K-fold estratificado (5-10 folds)
- Validação temporal (verificar overfitting temporal)
- Calibração de probabilidades

### Fase 3: Monitoramento e Feedback Loop (contínuo)

#### 3.1 Métricas de Produção
- Taxa de concordância em tempo real
- Distribuição de confiança
- Tasa de rejeição de políticas (deve ser <5%)

#### 3.2 Retraining Automático
- Trigger semanal se >=100 novos feedbacks
- Drift detection (se distribuição mudar >20%)
- A/B testing de novos modelos

## 📊 Critérios de Sucesso

| Métrica | Atual | Target (Fase 1) | Target (Fase 2) | Target (Final) |
|---------|-------|-----------------|-----------------|----------------|
| Precisão intenções críticas | ~60% | 70% | 80% | >90% |
| Concordância especialista-humano | 56% | 70% | 80% | >85% |
| Taxa rejeição políticas | ~8% | <7% | <6% | <5% |
| Confiança média (decisões claras) | 0.5 | 0.6 | 0.75 | >0.8 |

## 🔄 Próximos Passos Imediatos

1. ✅ Análise de dados realizada (2026-03-16)
2. 🔴 Implementar coleta de features adicionais no feedback
3. 🔴 Criar pipeline de NLP features
4. 🟡 Retreinar modelos com novas features
5. 🟡 Deploy A/B test
6. 🟢 Monitorar e iterar

## 📝 Observações

- **Dados sintéticos não funcionaram** - Descartar approach
- **2402 feedbacks é um bom começo** mas precisa de mais contexto
- **Features linguísticas podem ser a chave** - Intenção contém muito contexto não capturado
- **Calibração humana é inconsistente** - Mesmo humano pode ter discordância
