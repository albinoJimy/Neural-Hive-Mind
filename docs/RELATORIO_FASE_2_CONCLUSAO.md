# Conclusão FASE 2: Melhoria de Modelos ML

**Data:** 2026-03-16
**Status:** ⚠️ FASE 2 CONCLUÍDA COM LIMITAÇÕES DE DADOS

## 📊 Resumo dos Resultados

### Experimentos Realizados

| Versão | Features | Samples | F1-Score | Accuracy | Status |
|--------|----------|---------|----------|----------|--------|
| v3 | 40+ (NLP + reasoning) | 485 | 0.5115 | 0.6495 | Enviado para review_required |
| v4 | 4 (básicas) | 485 | 0.5115 | 0.6495 | Enviado para review_required |
| v5 | 8 (semânticas) | 46 | - | - | Apenas 1 classe! |

### Descoberta Crítica

**v5 revelou**: Todos os 46 samples com análise semântica completa são da classe "review_required".

| Classe | Samples com análise semântica |
|--------|------------------------------|
| review_required | 46 (100%) |
| approve | 0 (0%) |
| reject | 0 (0%) |

**Implicação**: A análise semântica só é executada para casos marcados como "review_required". Casos "approve" e "reject" não recebem análise completa.

## 🔍 Análise de Root Cause

### Problema 1: Loop de Feedback Vicioso

```
Caso novo → Análise semântica → Recomendação → review_required
Caso claro → Sem análise semântica → Recomendação → approve/reject
```

Os casos "approve" e "reject" são precisamente os casos **claros** que não precisam de análise semântica profunda. Mas isso significa que nunca teremos dados semânticos para essas classes!

### Problema 2: Features Constantes

Mesmo para a classe "review_required", as features ML têm baixa variância:

| Feature | Mean | Std Dev | Observação |
|---------|------|---------|------------|
| confidence | 0.112 | 0.061 | Variância baixa |
| risk | 0.582 | 0.036 | Variância baixa |
| rf_security | 0.073 | 0.044 | Variância muito baixa |

### Problema 3: Dados Sintéticos Históricos

Todos os feedbacks históricos para "approve" e "reject" têm features constantes (0.5) porque foram coletados quando o modelo retornava confiança genérica.

## ✅ Conquistas Técnicas

1. **Pipeline de retraining funcional** - Scripts executam completamente
2. **Schema de feedback enriquecido** - v2.0.0 com 11 novos campos
3. **NLPFeatureExtractor implementado** - 30+ features prontas para uso
4. **Feature importância calculada** - `confidence` é o fator principal
5. **Biblioteca de feature extraction** - Com testes e exemplos

## ⚠️ Limitações Identificadas

### Dados
- **Zero amostras** "approve"/"reject" com análise semântica
- **Features constantes** (std=0) para classes minoritárias
- **Desbalanceamento severo** (65.7% "review_required")

### Pipeline
- **`intent_raw_text` vazio** em 100% dos feedbacks históricos
- **Análise semântica condicional** - só executada para casos incertos

## 🚀 Recomendações para FASE 3

### 1. Mudar Estratégia de Coleta (CRÍTICO)

**Atual**: Coletar feedback apenas de casos review_required
**Proposto**: Coletar feedback de AMBOS tipos de caso

```python
# Sempre executar análise semântica, independente da recomendação
opinion = specialist.evaluate(intent)
semantic_analysis = semantic_analyzer.analyze(intent)

# Sempre salvar com análise completa
feedback = {
    "opinion_id": opinion.id,
    "human_recommendation": "approve",  # OU "review_required"
    "reasoning_factors": semantic_analysis.factors,  # SEMPRE completos
    "intent_raw_text": intent.raw_text,  # CRÍTICO
}
```

### 2. Implementar Captura de Texto (CRÍTICO)

```python
# No orchestrator / approval-service
feedback_data = {
    "opinion_id": opinion.id,
    "human_recommendation": recommendation,
    "intent_raw_text": intent.raw_text,  # ADICIONAR
    "intent_id": intent.id,
    "trace_id": trace_id,
}
```

### 3. Coleta Ativa de Dados Balanceados

- Para cada 10 feedbacks "review_required", coletar 2 "approve" e 2 "reject"
- Selecionar casos claros propositalmente para ter variedade
- Usar active learning para identificar casos valiosos

### 4. Alternativa: Mude para 2 Classes

Em vez de 3 classes (approve, reject, review_required), usar 2:

- **clear**: approve ou reject (confiança > 0.7)
- **uncertain**: necessita revisão (confiança < 0.7)

Isso elimina o problema de discriminação entre approve e reject.

## 📋 Arquivos Criados

```
ml_pipelines/training/
├── retrain_with_enriched_features.py  # v3 - 40+ features
├── retrain_v4_basic_features.py        # v4 - 4 features básicas
└── retrain_v5_semantic_features.py     # v5 - 8 features semânticas

libraries/python/neural_hive_specialists/
└── feature_extraction/
    ├── nlp_feature_extractor.py        # 30+ features NLP
    ├── examples/nlp_features_demo.py   # Demo
    └── tests/test_nlp_feature_extractor.py  # Testes

docs/
├── PLANO_MELHORIA_MODELOS_ML.md        # Plano original
├── RELATORIO_ENRIQUECIMENTO_FEEDBACK.md # Migração v2.0.0
├── RELATORIO_RETRAINING_V4_MARCO_2026.md # Resultados v4
└── RELATORIO_FASE_2_CONCLUSAO.md       # Este arquivo
```

## 🎯 Próximos Passos Prioritários

1. **Implementar captura de `intent_raw_text`** (1-2 dias)
2. **Modificar pipeline para SEMPRE analisar semanticamente** (1 dia)
3. **Coletar 100+ feedbacks balanceados** (1-2 semanas)
4. **Retreinar com dados balanceados** (após coleta)

## 📊 Métricas de Sucesso da FASE 2

| Métrica | Antes | Depois | Target | Status |
|---------|-------|--------|--------|--------|
| Schema version | 1.0.0 | 2.0.0 | - | ✅ |
| Feedbacks enriquecidos | 0 | 2402 | 2402 | ✅ |
| NLPFeatureExtractor | - | ✅ | ✅ | ✅ |
| Pipeline de retraining | - | ✅ | ✅ | ✅ |
| Samples semânticos approve | 0 | 0 | >20 | ❌ |
| Samples semânticos reject | 0 | 0 | >20 | ❌ |
| intent_raw_text populado | 0% | 0% | 100% | ❌ |
| Precision (approve) | 0.00 | 0.00 | >0.5 | ❌ |
| Precision (reject) | 0.00 | 0.00 | >0.5 | ❌ |

## 💡 Lições Aprendidas

1. **Qualidade dos dados > Quantidade de features**: 46 samples perfeitos > 485 samples ruins
2. **Pipeline de coleta é mais importante que algoritmo**: Se não coletarmos dados balanceados, nenhum algoritmo vai funcionar
3. **Análise semântica deve ser sempre executada**: Não apenas para casos incertos
4. **Texto da intenção é crítico**: Sem texto, NLP features não funcionam

## 🏁 Conclusão

A FASE 2 estabeleceu a **infraestrutura técnica necessária** (schema, pipeline, features), mas revelou que o **problema fundamental é a qualidade dos dados**. A FASE 3 deve focar em **mudar a estratégia de coleta de dados** para obter um dataset balanceado e discriminativo.
