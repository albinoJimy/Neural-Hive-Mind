# TICKET 1.1: Análise Completa do approval_predictor.py

> **Data:** 2026-04-24
> **Arquivo Analisado:** `ml_pipelines/inference/approval_predictor.py`
> **Linhas de Código:** 340 linhas
> **Status:** Análise Completa

---

## 1. Visão Geral

### 1.1 Propósito
O `ApprovalPredictor` é o componente principal de inferência ML para aprovação de planos cognitivos. Carrega modelos treinados (v6/v7) e realiza predições sobre texto de intenções.

### 1.2 Arquitetura Atual
```
┌─────────────────────────────────────────────────────────────┐
│                    ApprovalPredictor                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │User Intention│───▶│extract_nlp   │───▶│30 features   │ │
│  │(text)        │    │_features()   │    │(regex-based) │ │
│  └──────────────┘    └──────────────┘    └──────┬───────┘ │
│                                                  │          │
│                                                  ▼          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │Model Loading │    │Feature Order │    │predict_from  │ │
│  │(pickle)      │    │(30 colunas)  │    │_text()       │ │
│  └──────────────┘    └──────────────┘    └──────┬───────┘ │
│                                                  │          │
│                                                  ▼          │
│  ┌────────────────────────────────────────────────────────┐ │
│  │Decision: approve/reject/review_required + confidence    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Mapeamento Completo das 30 Regex Manuais

### 2.1 Categorias de Features

#### A. Domínios (5 regex)
| # | Feature | Regex Pattern | Linha |
|---|---------|---------------|-------|
| 1 | `domain_security` | `\b(security\|ssl\|tls\|authentication\|authorization\|password\|login)\b` | 74 |
| 2 | `domain_performance` | `\b(performance\|optimize\|index\|cache\|speed\|latency\|query)\b` | 75 |
| 3 | `domain_database` | `\b(database\|db\|sql\|mongo\|query\|table\|schema\|migration)\b` | 76 |
| 4 | `domain_devops` | `\b(deploy\|container\|docker\|kubernetes\|ci/cd\|pipeline\|build)\b` | 77 |
| 5 | `domain_testing` | `\b(test\|testing\|unit\|integration\|e2e\|coverage)\b` | 78 |

#### B. Ações (5 regex)
| # | Feature | Regex Pattern | Linha |
|---|---------|---------------|-------|
| 6 | `action_create` | `\b(create\|add\|insert\|new\|make)\b` | 87 |
| 7 | `action_update` | `\b(update\|modify\|change\|edit\|alter)\b` | 88 |
| 8 | `action_delete` | `\b(delete\|drop\|remove\|destroy\|clean)\b` | 89 |
| 9 | `action_read` | `\b(get\|fetch\|select\|read\|query\|find)\b` | 90 |
| 10 | `action_deploy` | `\b(deploy\|release\|publish\|ship)\b` | 91 |

#### C. Palavras-chave de Risco (3 regex)
| # | Feature | Regex Pattern | Linha |
|---|---------|---------------|-------|
| 11 | `has_backup` | `\bbackup\|save\|preserve\|restore\b` | 101 |
| 12 | `has_verification` | `\bverify\|validation\|check\|confirm\|test\b` | 104 |
| 13 | `has_all` | `\ball\b.*\b(users\|records\|data\|tables)\b` | 107 |

#### D. Métricas de Risco (3 regex)
| # | Feature | Regex Pattern | Linha |
|---|---------|---------------|-------|
| 14 | `risk_high` | `\b(delete\|drop\|destroy\|remove\|disable)\b` | 114 |
| 15 | `risk_medium` | `\b(update\|change\|modify\|alter)\b` | 117 |
| 16 | `risk_low` | `\b(create\|add\|verify\|check\|test\|backup)\b` | 120 |

#### E. Domínio Primário (5 features derivadas)
| # | Feature | Lógica de Derivação | Linha |
|---|---------|-------------------|-------|
| 17 | `primary_domain_security` | `max(domain_scores) == "security"` | 132 |
| 18 | `primary_domain_performance` | `max(domain_scores) == "performance"` | 132 |
| 19 | `primary_domain_database` | `max(domain_scores) == "database"` | 132 |
| 20 | `primary_domain_devops` | `max(domain_scores) == "devops"` | 132 |
| 21 | `primary_domain_testing` | `max(domain_scores) == "testing"` | 132 |

#### F. Ação Primária (5 features derivadas)
| # | Feature | Lógica de Derivação | Linha |
|---|---------|-------------------|-------|
| 22 | `primary_action_create` | `max(action_scores) == "create"` | 138 |
| 23 | `primary_action_update` | `max(action_scores) == "update"` | 138 |
| 24 | `primary_action_delete` | `max(action_scores) == "delete"` | 138 |
| 25 | `primary_action_read` | `max(action_scores) == "read"` | 138 |
| 26 | `primary_action_deploy` | `max(action_scores) == "deploy"` | 138 |

#### G. Métricas de Texto (2 features, não-regex)
| # | Feature | Tipo | Linha |
|---|---------|------|-------|
| 27 | `text_length_chars` | `len(text)` | 110 |
| 28 | `text_length_words` | `len(text.split())` | 111 |

#### H. Score de Risco (1 feature derivada)
| # | Feature | Lógica de Derivação | Linha |
|---|---------|-------------------|-------|
| 29 | `simple_risk_score` | `min(1.0, dangerous_count * 0.3)` | 127 |

#### I. Feature Externa (1 feature de input)
| # | Feature | Tipo | Linha |
|---|---------|------|-------|
| 30 | `specialist_confidence` | Input parameter (0.0-1.0) | 150 |

### 2.2 Total de Regex Manuais
- **16 regex únicas** (domínios + ações + palavras-chave + risco)
- **13 features derivadas** (domínios primários + ações primárias + risk_score)
- **2 features de texto** (length-based)
- **1 feature de input** (specialist_confidence)
- **TOTAL: 30 features**

---

## 3. Formato Atual das Features

### 3.1 Ordem de Features (Array de 30 posições)
```python
feature_order = [
    # Input (1)
    "specialist_confidence",

    # Domínios (5)
    "domain_security",
    "domain_performance",
    "domain_database",
    "domain_devops",
    "domain_testing",

    # Ações (5)
    "action_create",
    "action_update",
    "action_delete",
    "action_read",
    "action_deploy",

    # Palavras-chave (3)
    "has_backup",
    "has_verification",
    "has_all",

    # Métricas de texto (2)
    "text_length_chars",
    "text_length_words",

    # Risco (4)
    "risk_high",
    "risk_medium",
    "risk_low",
    "simple_risk_score",

    # Domínio primário (5)
    "primary_domain_security",
    "primary_domain_performance",
    "primary_domain_database",
    "primary_domain_devops",
    "primary_domain_testing",

    # Ação primária (5)
    "primary_action_create",
    "primary_action_update",
    "primary_action_delete",
    "primary_action_read",
    "primary_action_deploy",
]
```

### 3.2 Tipos de Features
| Categoria | Features | Tipo | Range |
|-----------|----------|------|-------|
| Input | `specialist_confidence` | float | 0.0 - 1.0 |
| Domínios | 5 features | binary | 0.0 ou 1.0 |
| Ações | 5 features | binary | 0.0 ou 1.0 |
| Palavras-chave | 3 features | binary | 0.0 ou 1.0 |
| Texto | 2 features | integer | >= 0 |
| Risco | 4 features | float | 0.0 - 1.0 |
| Domínio primário | 5 features | binary | 0.0 ou 1.0 |
| Ação primária | 5 features | binary | 0.0 ou 1.0 |

### 3.3 Valor Padrão
```python
nlp_features.get(f, 0.0)  # Todas as features default para 0.0 se não encontradas
```

---

## 4. Fluxo do Método `predict_from_text()`

### 4.1 Diagrama de Fluxo
```
┌─────────────────────────────────────────────────────────────────────┐
│                         predict_from_text()                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. VALIDAÇÃO                                                        │
│     └── if not self.model → raise RuntimeError                      │
│                                                                      │
│  2. EXTRAÇÃO DE FEATURES (extract_nlp_features)                     │
│     ├── Domínios: 5 regex (domain_*)                               │
│     ├── Ações: 5 regex (action_*)                                  │
│     ├── Palavras-chave: 3 regex (has_*)                            │
│     ├── Texto: 2 features (text_length_*)                          │
│     ├── Risco: 3 regex (risk_*)                                    │
│     ├── Score: 1 derived (simple_risk_score)                       │
│     ├── Domínio primário: 5 derived (primary_domain_*)             │
│     └── Ação primária: 5 derived (primary_action_*)                │
│                                                                      │
│  3. ORDENAÇÃO DE FEATURES                                            │
│     └── feature_order array (30 posições fixas)                     │
│                                                                      │
│  4. OVERRIDE DE specialist_confidence                                │
│     └── features[0][0] = specialist_confidence                      │
│                                                                      │
│  5. PREDIÇÃO                                                         │
│     ├── decision = model.predict(features)                          │
│     └── probabilities = model.predict_proba(features)               │
│                                                                      │
│  6. RETORNO                                                          │
│     {                                                                │
│       "decision": "approve/reject/review_required",                 │
│       "confidence": 0.0-1.0,                                         │
│       "probabilities": {class: prob},                               │
│       "model_version": "v6/v7"                                      │
│     }                                                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Pontos de Entrada
1. **`predict_from_text(text, specialist_confidence)`** - Principal
2. **`predict_from_nlp_features(nlp_features, specialist_confidence)`** - Alternativo (features já extraídas)

---

## 5. Features Críticas a Preservar

### 5.1 Features de Negócio (Alta Prioridade)
Estas features têm impacto direto na decisão de aprovação:

| Feature | Razão | Preservar Como |
|---------|-------|----------------|
| `specialist_confidence` | Input humano, crucial | Parâmetro separado |
| `risk_high` | Detecta operações perigosas | Feature de risco do extractor |
| `risk_medium` | Detecta modificações | Feature de risco do extractor |
| `has_backup` | Mitigação de risco | Feature de segurança do extractor |
| `has_verification` | Mitigação de risco | Feature de segurança do extractor |
| `has_all` | Detecta bulk operations | Feature de escopo do extractor |

### 5.2 Features de Contexto (Média Prioridade)
| Feature | Razão | Preservar Como |
|---------|-------|----------------|
| Domínios (5) | Categoria da intenção | Features de domínio do extractor |
| Ações (5) | Tipo de operação | Features de ação do extractor |
| `text_length_chars` | Complexidade da intenção | Métrica de texto do extractor |
| `text_length_words` | Complexidade da intenção | Métrica de texto do extractor |

### 5.3 Features Derivadas (Baixa Prioridade - podem ser recriadas)
| Feature | Razão | Ação |
|---------|-------|------|
| `primary_domain_*` (5) | Derivado de `domain_*` | Recriar no adapter |
| `primary_action_*` (5) | Derivado de `action_*` | Recriar no adapter |
| `risk_low` | Derivado de keywords | Recriar no adapter |
| `simple_risk_score` | Derivado de `risk_high` | Recriar no adapter |

---

## 6. Modelo Atual (v6/v7)

### 6.1 Informações do Modelo
```python
{
    "version": "v6" ou "v7",
    "trained_at": "timestamp",
    "features": [lista de 30 features],
    "metrics": {"f1_score": float, "accuracy": float},
    "training_samples": 50 (v6) ou 75 (v7)
}
```

### 6.2 Limitações do Modelo Atual
1. **Overfitting v6**: F1-Score 1.0000 com apenas 50 amostras
2. **Amostra limitada v7**: Apenas 75 amostras para treino
3. **Features baseadas em regex**: Frágil a variações de linguagem
4. **Sem embedding**: Não captura semântica, apenas padrões de texto

---

## 7. Problemas Identificados

### 7.1 Problemas Técnicos
1. **Acoplamento forte**: 30 regex manuais hardcoded
2. **Manutenibilidade**: Nova keyword = alterar código
3. **Extensibilidade**: Difícil adicionar novos domínios/ações
4. **Performance**: 16 regex compiladas a cada predict

### 7.2 Problemas de Qualidade de Predição
1. **Falsos negativos**: "Drop table users" pode ser aprovado se tiver "backup"
2. **Falsos positivos**: "Create backup of delete script" pode ser rejeitado
3. **Semântica limitada**: "Remove user" vs "Delete user" = mesma feature
4. **Contexto perdido**: "Add user to admin group" vs "Add admin to user group"

---

## 8. Recomendações para Migração

### 8.1 Estratégia de Preservação
```python
# NOVO: FeatureExtractor Profissional
new_features = feature_extractor.extract(text)
# Resultado: {
#   "embeddings": [...],
#   "tfidf_features": {...},
#   "semantic_features": {...}
# }

# ADAPTER: Converter para formato compatível
compatible_features = adapter.to_legacy_format(new_features)
# Resultado: {
#   "specialist_confidence": 0.5,  # Preservado
#   "domain_security": 0.9,        # Mapeado de semantic_features
#   "risk_high": 0.8,              # Mapeado de semantic_features
#   ...
# }
```

### 8.2 Features que Devem ser Mapeadas 1:1
| Feature Legada | Fonte Nova |
|----------------|------------|
| `specialist_confidence` | Input parameter (preservar) |
| `domain_*` (5) | `semantic_features.domains` |
| `action_*` (5) | `semantic_features.actions` |
| `risk_high/medium/low` | `semantic_features.risk_level` |
| `has_backup` | `semantic_features.has_mitigation` |
| `has_verification` | `semantic_features.has_verification` |
| `text_length_*` | `text_metrics.length_*` |

### 8.3 Features que Devem ser Recalculadas
| Feature Legada | Cálculo |
|----------------|---------|
| `primary_domain_*` (5) | `argmax(domain_*)` |
| `primary_action_*` (5) | `argmax(action_*)` |
| `simple_risk_score` | `weighted_sum(risk_*)` |

---

## 9. Conclusão

### 9.1 Resumo
- **30 features manuais** identificadas e mapeadas
- **16 regex únicas** que precisam ser substituídas
- **30 posições fixas** no array de features (ordem crítica)
- **3 categorias de features**: input, binary, float

### 9.2 Próximos Passos (TICKET 1.2)
1. Analisar `neural_hive_specialists/feature_extraction/feature_extractor.py`
2. Entender API do `FeatureExtractor`
3. Entender API do `EmbeddingsGenerator`
4. Verificar testes existentes
5. Documentar formato de saída (TF-IDF + embeddings)

### 9.3 Riscos de Migração
| Risco | Mitigação |
|-------|-----------|
| Mudança de predições | Feature flag + A/B testing |
| Performance degradation | Benchmark latência |
| Novos tipos de erro | Testes de regressão |

---

## 10. Apêndice: Código de Referência

### 10.1 Exemplo de Uso Atual
```python
from ml_pipelines.inference.approval_predictor import ApprovalPredictor

predictor = ApprovalPredictor()
result = predictor.predict_from_text(
    "Delete all records from users table",
    specialist_confidence=0.7
)

# Resultado:
# {
#   "decision": "reject",
#   "confidence": 0.95,
#   "probabilities": {"approve": 0.05, "reject": 0.95},
#   "model_version": "v7"
# }
```

### 10.2 Exemplo de Features Extraídas
```python
# Text: "Delete all records from users table"
features = predictor.extract_nlp_features(text)

# Resultado (30 features):
# {
#   "domain_security": 0.0,
#   "domain_database": 1.0,
#   "action_delete": 1.0,
#   "has_all": 1.0,
#   "risk_high": 1.0,
#   "simple_risk_score": 0.9,  # delete + all = 2 * 0.3
#   "primary_action_delete": 1.0,
#   "primary_domain_database": 1.0,
#   ...
# }
```

---

**Fim do Relatório - TICKET 1.1 Completo**
