# Relatório: Retraining Modelos ML - Análise de Resultados

**Data:** 2026-03-16
**Script:** `retrain_v4_basic_features.py`
**Status:** ❌ Modelo treinado mas com limitações severas

## 📊 Resultados do Treinamento

### Métricas Globais
| Modelo | F1-Score | Accuracy | Status |
|--------|----------|----------|--------|
| GradientBoosting | 0.5115 | 0.6495 | ✅ Melhor |
| RandomForest | 0.1187 | 0.2165 | ❌ Ruim |

### Feature Importance (GradientBoosting)
| Feature | Importância | Observação |
|---------|-------------|------------|
| confidence | 0.6147 | Predominante |
| rf_ml_risk | 0.2221 | Moderada |
| rf_ml_confidence | 0.1632 | Baixa |
| risk | 0.0000 | Nula |

### Classification Report
```
                 precision    recall  f1-score   support
       reject       0.00      0.00      0.00        16
      approve       0.00      0.00      0.00        18
review_required    0.65      1.00      0.79        63
```

## 🔍 Análise: Por Que o Modelo Falha?

### Problema 1: Features Constantes nas Classes Minoritárias

| Classe | Confidence Mean | Risk Mean | ML Conf Mean | ML Risk Mean | Std Dev |
|--------|-----------------|-----------|--------------|--------------|---------|
| reject | **0.500** | **0.500** | **0.500** | **0.500** | 0.000 |
| approve | **0.500** | **0.500** | **0.500** | **0.500** | 0.000 |
| review_required | 0.444 | 0.512 | 0.500 | 0.500 | 0.139 |

**Interpretação:** Os feedbacks "reject" e "approve" foram coletados quando o modelo retornava confiança 0.5 para TODAS as opiniões. Não há features discriminativas para essas classes.

### Problema 2: Desbalanceamento de Classes

- **review_required:** 65.7% (318/485 amostras)
- **approve:** 18.0% (88/485 amostras)
- **reject:** 16.2% (79/485 amostras)

O modelo aprende que prever "review_required" minimiza o erro.

## 📈 Comparação com Baseline

| Métrica | Antes (v1-v2) | Depois (v4) | Delta |
|---------|---------------|-------------|-------|
| Accuracy (global) | ~0.50 | 0.6495 | +30% |
| F1-Score (weighted) | ~0.33 | 0.5115 | +55% |
| Precision (reject) | 0.00 | 0.00 | Sem mudança |
| Precision (approve) | 0.00 | 0.00 | Sem mudança |

**Observação:** Melhoria marginal apenas na classe majoritária.

## ✅ Conquistas

1. **Pipeline de retraining funcional** - Script executa completamente
2. **Features enriquecidas migradas** - 2402/2402 feedbacks com schema v2.0.0
3. **Feature extraction implementada** - NLPFeatureExtractor com 30+ features
4. **Modelo treinado e salvo** - `/tmp/ml_models/technical/technical_evaluator_v4_basic.pkl`
5. **Feature importance calculada** - `confidence` é o fator principal

## ⚠️ Limitações Identificadas

### Técnica
- **Features discriminativas ausentes:** Dados históricos não têm variância para classes minoritárias
- **Features NLP não populadas:** Campo `intent_raw_text` vazio em 100% dos feedbacks
- **Reasoning factors semânticos:** Apenas 9.5% (46/485) dos dados têm análise semântica

### Operacional
- **Coleta de feedback incompleta:** Clientes não enviam `intent_raw_text`
- **Modelos antigos retornavam 0.5:** Sem variância nas features históricas

## 🚀 Recomendações

### Imediato (Curto Prazo)

1. **Implementar captura de `intent_raw_text`**
   - Modificar `feedback_collector` para aceitar texto da intenção
   - Atualizar clientes que enviam feedback (orchestrator, approval-service)
   - Executar migração para preencher campo retroativamente (se possível)

2. **Coletar feedbacks balanceados**
   - Criar campanha de coleta focada em casos "approve" e "reject"
   - Priorizar revisão de casos onde confiança NÃO é 0.5

3. **Usar features semânticas existentes**
   - Treinar modelo apenas com os 46 samples (9.5%) que têm reasoning_factors semânticos
   - Validar se features semânticas (security, architecture, etc.) discriminam melhor

### Médio Prazo

4. **Implementar active learning**
   - Identificar casos de baixa confiança para revisão humana prioritária
   - Usar incerteza do modelo para selecionar amostras valiosas

5. **Ajustar threshold de decisão**
   - Em vez de 3 classes, usar 2: "approve/reject" + "uncertain"
   - Deixar casos incertos para revisão humana

6. **Investigar ensemble com modelos semânticos**
   - Combinar outputs de análise semântica com predição ML
   - Usar features textuais diretamente (TF-IDF, embeddings)

### Longo Prazo

7. **Reimplementar pipeline de treinamento**
   - Treinar modelos específicos por domínio (security, performance, etc.)
   - Usar transformer-based models para entender texto da intenção

8. **MLOps: monitoramento e drift detection**
   - Alertar quando distribuição de features mudar
   - Retreinar automaticamente quando performance cair

## 📁 Arquivos Criados

```
ml_pipelines/training/
├── retrain_with_enriched_features.py  # v3 - com features NLP (não populadas)
└── retrain_v4_basic_features.py        # v4 - apenas features básicas

libraries/python/neural_hive_specialists/
└── feature_extraction/
    ├── nlp_feature_extractor.py        # Extrator de 30+ features
    ├── examples/nlp_features_demo.py   # Demo de uso
    └── tests/test_nlp_feature_extractor.py  # Testes unitários
```

## 🔬 Próximos Experimentos Sugeridos

1. **Treinar com apenas 46 samples semânticos**
   - Verificar se features semânticas discriminam melhor
   - Usar técnicas de few-shot learning

2. **One-class classification**
   - Treinar separado para cada classe
   - Usar anomaly detection para casos fora da distribuição

3. **Aumentar dataset com data augmentation**
   - Gerar variações de intenções existentes
   - Usar LLM para gerar intenções similares

## 📋 Conclusão

O modelo v4 representa um passo técnico importante (pipeline funcional, features enriquecidas), mas **não resolve o problema de negócio** (confiança baixa) porque os dados históricos não têm informações discriminativas para as classes mais importantes ("approve" e "reject").

**Próximo passo crítico:** Implementar captura de `intent_raw_text` e coletar feedbacks balanceados com features semânticas.
