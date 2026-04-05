# Resumo: Analise SHAP Values - Explainability API

**Data:** 2026-03-31
**Servico:** explainability-api
**Status:** IMPLEMENTADO (heuristica) - GAPS identificados

---

## Descoberta Principal

O servico possui `ShapCalculator` funcionando, mas **NAO usa a biblioteca SHAP real**.

### O que existe:
- Classe `ShapCalculator` em `src/services/shap_calculator.py` (316 linhas)
- Biblioteca `shap` 0.48.0 instalada
- Testes unitarios em `tests/test_shap_calculator.py` (292 linhas)
- Calculo de "feature attribution" funcionando

### O que falta:
- **A biblioteca SHAP nao e importada** - implementacao heuristica propria
- **Nao ha modelo ML subjacente** - SHAP requer um modelo f(x) para explicar
- **Kernel SHAP e "emulado"** - usa pesos arbitrarios em vez de SHAP matematico

---

## Implementacao Atual (Heuristica)

```python
# shap_calculator.py linha ~144-195
def _calculate_kernel_shap(self, feature_values, base_value, decision_data):
    """Kernel SHAP simplificado (NAO e SHAP real)."""
    shap_values = {}

    for feature, values in feature_values.items():
        avg_value = np.mean(values)

        # PESOS ARBITRARIOS (nao SHAP):
        if feature == 'confidence':
            contribution = (avg_value - 0.5) * 1.5  # arbitrario
        elif feature == 'risk':
            contribution = -(avg_value - 0.5) * 1.3  # arbitrario
        elif feature == 'seniority_multiplier':
            contribution = (avg_value - 1.0) * 0.3   # arbitrario

        shap_values[feature] = max(-1.0, min(1.0, contribution))

    return shap_values  # Valores "SHAP-like" mas nao SHAP matematico
```

---

## Gaps Identificados

| Gap | Descricao | Impacto |
|-----|-----------|---------|
| 1 | Nao ha modelo ML | SHAP requer f(x) para explicar |
| 2 | Biblioteca nao importada | Valores sao heuristica, nao SHAP |
| 3 | Kernel SHAP fake | Usa pesos arbitrarios |
| 4 | Base value arbitrario | Nao representa E[f(X)] |
| 5 | Testes fracos | Nao validam corretude matematica |

---

## Solucao Proposta

### Opcao A: ModelBasedShapCalculator (Recomendado)

```python
import shap
from sklearn.ensemble import RandomForestClassifier

class ModelBasedShapCalculator:
    """SHAP REAL com modelo wrapper."""

    def __init__(self):
        self.model = RandomForestClassifier()
        self.explainer = None  # Sera shap.TreeExplainer

    def train_from_history(self, historical_decisions):
        """Treina modelo em decisoes passadas."""
        X, y = self._prepare_training_data(historical_decisions)
        self.model.fit(X, y)

        # Criar explainer SHAP REAL
        background = shap.sample(X, 100)
        self.explainer = shap.TreeExplainer(self.model, background)

    def calculate_shap(self, decision_data):
        """Calcula SHAP REAL (nao heuristica)."""
        X = self._extract_features(decision_data)
        shap_values = self.explainer.shap_values(X)  # SHAP REAL
        return {
            'feature_attribution': shap_values,
            'base_value': self.explainer.expected_value,  # E[f(X)] REAL
            'method': 'tree_shap'  # SHAP REAL
        }
```

---

## Arquivos a Criar/Modificar

### Novos:
- `src/services/model_based_shap.py` - SHAP com modelo wrapper (~200 linhas)
- `src/models/shap_model.py` - Modelo sklearn (~100 linhas)
- `ml/shap_training.py` - Script de treino (~150 linhas)
- `tests/test_model_based_shap.py` - Testes SHAP real (~250 linhas)

### Modificar:
- `src/services/shap_calculator.py` - Adicionar opcao SHAP real
- `requirements.txt` - Adicionar scikit-learn>=1.3.0
- `README.md` - Documentar novo metodo

---

## Recomendacao

### Curto Prazo:
- Manter heuristica atual (funcional)
- Documentar limitacao no README
- Renomear metodo para `_calculate_heuristic_attribution()`

### Medio Prazo:
- Implementar `ModelBasedShapCalculator`
- Treinar modelo com decisoes historicas
- Manter ambos os metodos com feature flag

### Longo Prazo:
- Integrar com modelo ML do approval-service
- Usar SHAP values do modelo de aprovacao
- Adicionar visualizacoes SHAP (waterfall, dependence)

---

## Resumo Tecnico

| Aspecto | Status | Acao Necessaria |
|---------|--------|-----------------|
| Biblioteca shap | Instalada (0.48.0) | Importar e usar |
| ShapCalculator | Implementado | Refatorar para SHAP real |
| Modelo ML | Nao existe | Criar modelo wrapper |
| Testes | Funcionais | Atualizar para SHAP real |
| Documentacao | Incompleta | Adicionar aviso de limitacao |

---

**Analise completa:** `docs/ANALISE_SHAP_VALUES_EXPLAINABILITY_API_2026-03-31.md`
