# Analise SHAP Values - Explainability API
**Data:** 2026-03-31
**Servico:** explainability-api
**Status:** SHAP IMPLEMENTADO mas com LIMITACOES

---

## 1. Resumo Executivo

O servico `explainability-api` possui uma implementacao de SHAP **PARCIAL**:
- A classe `ShapCalculator` existe e esta funcional
- A biblioteca `shap` 0.48.0 esta instalada
- **Porem:** NAO utiliza a biblioteca SHAP real - usa implementacao propria simplificada
- O Kernel SHAP e "emulado" com heuristica em vez de valores SHAP verdadeiros

**Veredito:** SHAP values estao **FUNCIONAIS** mas **NAO sao valores SHAP matematicamente corretos**. E uma aproximacao heuristica.

---

## 2. Codigo Existente

### 2.1 Arquivo: `src/services/shap_calculator.py`

**Status:** Implementado (316 linhas)

**Classe principal:** `ShapCalculator`

**Metodos implementados:**
- `__init__(n_background_samples=10)` - Inicializacao
- `calculate_shap(decision_data, features)` - Calculo principal
- `_extract_feature_values()` - Extrai valores dos votos
- `_get_feature_value()` - Mapeamento de features
- `_calculate_base_value()` - Valor base (media esperada)
- `_calculate_kernel_shap()` - **IMPLEMENTACAO PROPRIA** (nao usa shap library)
- `_decision_to_numeric()` - Converte decisao texto para numero
- `batch_calculate_shap()` - Processamento em lote
- `format_explanation()` - Formata texto legivel

**Features suportadas:**
- `confidence` - Confianca do especialista
- `risk` - Risco avaliado
- `seniority_multiplier` - Multiplicador de senioridade

**Mapeamento de decisao:**
```python
approve -> 1.0
conditional -> 0.5
review_required -> 0.0
reject -> -1.0
needs_revision -> -0.5
```

### 2.2 Dependencias

**requirements.txt NAO contem SHAP:**
```
# SHAP nao listado mas instalado via pip
```

**Verificacao:**
```bash
$ pip list | grep shap
shap    0.48.0  # INSTALADO mas NAO usado no codigo
```

**Importacao:** A biblioteca SHAP nunca e importada:
```bash
# Nenhuma ocorrencia de "import shap" no codigo
```

---

## 3. Implementacao Atual vs SHAP Real

### 3.1 Implementacao Atual (Heuristica)

```python
def _calculate_kernel_shap(self, feature_values, base_value, decision_data):
    """
    Calcula valores SHAP usando Kernel SHAP simplificado.

    Implementacao simplificada que estima contribuição marginal
    de cada feature para a decisao final.
    """
    shap_values = {}

    # Obter decisao final como valor numerico (-1 a 1)
    final_decision_num = self._decision_to_numeric(decision_data.get('final_decision', 'approve'))

    # Para cada feature, calcular contribuição marginal
    for feature, values in feature_values.items():
        avg_value = np.mean(values)

        # CONTRIBUICAO HEURISTICA (nao SHAP real):
        if feature == 'confidence':
            contribution = (avg_value - 0.5) * 1.5  # Peso arbitrario
        elif feature == 'risk':
            contribution = -(avg_value - 0.5) * 1.3  # Peso arbitrario
        elif feature == 'seniority_multiplier':
            contribution = (avg_value - 1.0) * 0.3   # Peso arbitrario
        else:
            contribution = (avg_value - 0.5) * 0.5

        # Normalizar e escalar para soma aproximada
        shap_values[feature] = max(-1.0, min(1.0, contribution))
```

### 3.2 SHAP Real (biblioteca shap)

O que estaria faltando para SHAP real:

```python
import shap

# 1. Precisaria de um modelo treinado (sklearn, xgboost, etc.)
# 2. Criar explainer com dados de background
explainer = shap.KernelExplainer(model, background_data)

# 3. Calcular SHAP values
shap_values = explainer.shap_values(X)

# 4. Propriedades matematicas garantidas:
#    - Local accuracy: sum(shap) + base_value = f(x)
#    - Missingness: features ausentes tem shap = 0
#    - Consistency: ordem de importancia preservada
```

---

## 4. Gaps Identificados

### Gap 1: Nao ha modelo ML subjacente

**Problema:** SHAP requer um modelo `f(x)` para explicar.
- `ShapCalculator` assume que pode explicar "direto"
- SHAP real precisa de um modelo treinado (sklearn, xgboost, etc.)

**Impacto:** Os valores sao heuristica, nao SHAP matematico.

### Gap 2: Biblioteca SHAP nao e importada

**Problema:** A biblioteca `shap` esta instalada mas nunca importada.
- O codigo numpy heuristica nao usa shap.Explainer
- Os valores calculados sao "SHAP-like" mas nao SHAP

**Impacto:** Enganosos - o metodo se chama SHAP mas nao usa a biblioteca.

### Gap 3: Kernel SHAP nao e implementado

**Problema:** O metodo `_calculate_kernel_shap()` e um nome enganoso.
- Kernel SHAP real usa weighted linear regression
- A implementacao usa heuristica simples de pesos

**Impacto:** Sem garantias matematicas de SHAP.

### Gap 4: Base value arbitrario

**Problema:** `_calculate_base_value()` usa aproximacao simples.
```python
def _calculate_base_value(self, feature_values, decision_data):
    if 'aggregated_confidence' in decision_data:
        conf = decision_data['aggregated_confidence']
        risk = decision_data.get('aggregated_risk', 0.5)
        return (conf - risk) * 2 - 1  # Formula arbitraria
    return 0.0  # Neutro sem informacao
```

**Impacto:** Base value nao representa E[f(X)] matematicamente.

### Gap 5: Testes unitarios dao falso positivo

**Problema:** Os testes verificam comportamento, nao corretude matematica.
```python
def test_shap_values_sum_to_approximate_prediction(self, sample_decision_data):
    """Testa que valores SHAP somam aproximadamente a predicao."""
    # Teste passa mesmo com heuristica
    assert -1.0 <= shap_sum <= 2.0  # Muito fraco
```

**Impacto:** Testes nao validam se sao valores SHAP reais.

---

## 5. Arquitetura SHAP Proposta

### 5.1 Opcao A: SHAP com Modelo Wrapper (Recomendado)

```python
import shap
from sklearn.ensemble import RandomForestClassifier
from typing import Dict, Any, List
import numpy as np

class ModelBasedShapCalculator:
    """
    Calculadora de SHAP com modelo ML wrapper.

    Esta abordagem cria um modelo simples que aprende
    o padrao de decisoes e usa SHAP real para explica-lo.
    """

    def __init__(self, n_background_samples: int = 100):
        self.n_background_samples = n_background_samples
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.explainer = None
        self.feature_names = ['confidence', 'risk', 'seniority_multiplier']
        self.is_trained = False

    def train_from_history(self, historical_decisions: List[Dict[str, Any]]):
        """
        Treina modelo a partir de decisoes historicas.

        Args:
            historical_decisions: Lista de decisoes passadas com features e outcome
        """
        X = []  # Features
        y = []  # Labels (approve=1, reject=0)

        for decision in historical_decisions:
            features = self._extract_features(decision)
            label = 1 if decision.get('final_decision') == 'approve' else 0
            X.append(features)
            y.append(label)

        X = np.array(X)
        y = np.array(y)

        # Treinar modelo
        self.model.fit(X, y)

        # Criar explainer SHAP com dados de background
        background = shap.sample(X, min(self.n_background_samples, len(X)))
        self.explainer = shap.TreeExplainer(self.model, data=background)

        self.is_trained = True

    def calculate_shap(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calcula valores SHAP reais para uma decisao.

        Usa SHAP library com modelo treinado.
        """
        if not self.is_trained:
            raise ValueError("Model not trained. Call train_from_history() first.")

        # Extrair features da decisao
        X = self._extract_features(decision_data).reshape(1, -1)

        # Calcular SHAP values (SHAP REAL)
        shap_values = self.explainer.shap_values(X)

        # Base value (E[f(X)])
        base_value = self.explainer.expected_value

        # Organizar resultado
        feature_attribution = {
            name: float(shap_values[0][i])
            for i, name in enumerate(self.feature_names)
        }

        return {
            'feature_attribution': feature_attribution,
            'base_value': float(base_value),
            'method': 'tree_shap',  # Metodo real SHAP
            'num_features': len(self.feature_names),
            'model_type': 'RandomForest'
        }

    def _extract_features(self, decision_data: Dict[str, Any]) -> List[float]:
        """Extrai features numericas da decisao."""
        votes = decision_data.get('specialist_votes', [])

        if not votes:
            return [0.5, 0.5, 1.0]  # Default

        # Media das features
        confidences = [v.get('confidence_score', 0.5) for v in votes]
        risks = [v.get('risk_score', 0.5) for v in votes]
        seniorities = [v.get('seniority_multiplier', 1.0) for v in votes]

        return [
            np.mean(confidences),
            np.mean(risks),
            np.mean(seniorities)
        ]
```

### 5.2 Opcao B: SHAP KernelExplain (Simples)

```python
import shap
import numpy as np
from typing import Dict, Any, List

class KernelShapCalculator:
    """
    Calculadora de SHAP usando KernelExplainer.

    Usa SHAP library com funcao arbitrária (sem modelo).
    """

    def __init__(self, n_background_samples: int = 50):
        self.n_background_samples = n_background_samples
        self.explainer = None
        self.feature_names = ['confidence', 'risk', 'seniority_multiplier']

    def _decision_function(self, X):
        """
        Funcao que a decisao dadas as features.

        Esta funcao representa o "modelo" que SHAP vai explicar.
        """
        # Funcao simples que representa logica de decisao
        confidence, risk, seniority = X

        # Decisao = weighted combination
        score = (confidence * 1.5) - (risk * 1.3) + ((seniority - 1.0) * 0.3)

        return score

    def initialize_explainer(self, background_data: np.ndarray):
        """Inicializa explainer SHAP com dados de fundo."""
        self.explainer = shap.KernelExplainer(
            self._decision_function,
            background_data
        )

    def calculate_shap(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula valores SHAP reais."""
        if self.explainer is None:
            # Criar background padrao se nao inicializado
            background = np.array([[0.5, 0.5, 1.0]] * self.n_background_samples)
            self.initialize_explainer(background)

        # Extrair features
        X = self._extract_features(decision_data).reshape(1, -1)

        # Calcular SHAP values (SHAP REAL)
        shap_values = self.explainer.shap_values(X)

        return {
            'feature_attribution': {
                name: float(shap_values[0][i])
                for i, name in enumerate(self.feature_names)
            },
            'base_value': float(self.explainer.expected_value),
            'method': 'kernel_shap',  # SHAP REAL
            'num_features': len(self.feature_names)
        }

    def _extract_features(self, decision_data: Dict[str, Any]) -> List[float]:
        """Extrai features numericas."""
        votes = decision_data.get('specialist_votes', [])
        if not votes:
            return [0.5, 0.5, 1.0]

        return [
            np.mean([v.get('confidence_score', 0.5) for v in votes]),
            np.mean([v.get('risk_score', 0.5) for v in votes]),
            np.mean([v.get('seniority_multiplier', 1.0) for v in votes])
        ]
```

---

## 6. Lista de Arquivos a Criar/Modificar

### 6.1 Arquivos Novos

| Arquivo | Propósito | Linhas estimadas |
|---------|-----------|------------------|
| `src/services/model_based_shap.py` | SHAP com modelo wrapper | ~200 |
| `src/services/kernel_shap_wrapper.py` | SHAP KernelExplainer wrapper | ~150 |
| `src/models/shap_model.py` | Modelo sklearn para SHAP | ~100 |
| `ml/shap_training.py` | Script de treino do modelo | ~150 |
| `tests/test_model_based_shap.py` | Testes SHAP real | ~250 |

### 6.2 Arquivos a Modificar

| Arquivo | Modificacao | Linhas |
|---------|-------------|--------|
| `src/services/shap_calculator.py` | Refatorar para usar SHAP library | +150/-100 |
| `requirements.txt` | Adicionar scikit-learn | +2 |
| `src/main.py` | Adicionar treinamento de modelo | +20 |
| `README.md` | Documentar novo metodo SHAP | +30 |
| `tests/test_shap_calculator.py` | Atualizar testes | +50 |

### 6.3 Dependencias a Adicionar

```txt
# ML para SHAP values
scikit-learn>=1.3.0
shap>=0.42.0  # Ja instalado, mas documentar
```

---

## 7. Recomendacoes

### 7.1 Curto Prazo (MVP)

1. **Manter heuristica atual** - Funcional para uso atual
2. **Documentar limitacao** - Adicionar aviso no README
3. **Renomear metodo** - `_calculate_kernel_shap()` -> `_calculate_heuristic_attribution()`

### 7.2 Medio Prazo (Recomendado)

1. Implementar `ModelBasedShapCalculator`
2. Treinar modelo simples com decisoes historicas
3. Manter ambos os metodos (heuristico + SHAP real)
4. Feature flag para escolher metodo

### 7.3 Longo Prazo (Ideal)

1. Integrar com modelo ML do approval-service
2. Usar SHAP values do modelo de aprovacao
3. Adicionar visualizacoes SHAP (waterfall, dependence)
4. SHAP global analysis (feature importance agregado)

---

## 8. Diagrama de Integracao Proposta

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXPLAINABILITY API                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────┐    ┌──────────────────────┐          │
│  │ ConsensusDecision   │    │ HistoricalDecisions  │          │
│  │ Consumer            │    │ (MongoDB)            │          │
│  └─────────┬───────────┘    └──────────┬───────────┘          │
│            │                           │                         │
│            ▼                           ▼                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           ShapCalculator (refatorado)                   │   │
│  │  ┌─────────────────┐  ┌───────────────────────────┐    │   │
│  │  │ HeuristicMode   │  │ ModelBasedMode (NOVO)     │    │   │
│  │  │ (atual)         │  │                           │    │   │
│  │  │ - Rapido        │  │ - SHAP real              │    │   │
│  │  │ - Sem treinamento│ │ - Modelo sklearn         │    │   │
│  │  │ - Aproximado    │  │ - Matematicamente correto│    │   │
│  │  └─────────────────┘  └───────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              SHAP Library (shap>=0.42)                  │   │
│  │  - TreeExplainer / KernelExplainer                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## 9. Exemplo de Uso Proposto

### 9.1 Treinamento do Modelo (One-time)

```python
from src.services.model_based_shap import ModelBasedShapCalculator

# Buscar decisoes historicas do MongoDB
historical_decisions = await db.consensus_decisions.find({}).to_list(1000)

# Criar calculadora e treinar
shap_calc = ModelBasedShapCalculator()
shap_calc.train_from_history(historical_decisions)

# Salvar modelo (pickle ou joblib)
import joblib
joblib.dump(shap_calc, 'models/shap_calculator.pkl')
```

### 9.2 Uso em Producao

```python
from src.services.model_based_shap import ModelBasedShapCalculator
import joblib

# Carregar modelo treinado
shap_calc = joblib.load('models/shap_calculator.pkl')

# Calcular SHAP para nova decisao
shap_result = shap_calc.calculate_shap({
    'specialist_votes': [
        {'confidence_score': 0.85, 'risk_score': 0.15, 'seniority_multiplier': 1.5},
        {'confidence_score': 0.90, 'risk_score': 0.10, 'seniority_multiplier': 2.0},
    ],
    'final_decision': 'approve'
})

# Resultado com SHAP REAL
print(shap_result)
# {
#     'feature_attribution': {
#         'confidence': 0.0234,    # SHAP value real
#         'risk': -0.0156,         # SHAP value real
#         'seniority_multiplier': 0.0078
#     },
#     'base_value': 0.5123,       # E[f(X)] real
#     'method': 'tree_shap',
#     'model_type': 'RandomForest'
# }
```

---

## 10. Conclusao

**Status Atual:**
- SHAP esta implementado como heuristica funcional
- A biblioteca `shap` esta instalada mas nao utilizada
- Os valores sao "SHAP-like" mas nao SHAP matematico

**Gaps:**
1. Nao ha modelo ML subjacente para SHAP explicar
2. Implementacao heuristica nao usa shap.Explainer
3. Base value e calculos sao aproximacoes

**Recomendacao:**
Implementar `ModelBasedShapCalculator` que treina um modelo simples nas decisoes historicas e usa SHAP real para explica-lo. Isso fornece valores SHAP matematicamente corretos mantendo a funcionalidade.

---

**Documento gerado:** 2026-03-31
**Analise por:** Claude Opus 4.6
**Repositorio:** Neural-Hive-Mind
