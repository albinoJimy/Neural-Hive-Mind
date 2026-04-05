# EPIC-204: SHAP Values Implementation

**ID:** EPIC-204
**Status:** Pending
**Priority:** P1 - Alta
**Effort:** L (3 semanas)
**Related Service:** explainability-api

---

## Resumo Executivo

Implementar cálculo real de SHAP values para explicar decisões do sistema. Atualmente existe uma heurística "fake SHAP" que usa pesos arbitrários. É necessário treinar um modelo ML nas decisões históricas e usar a biblioteca SHAP real. Completude atual: 30% (API existe, SHAP é fake).

---

## Análise Técnica

### Situação Atual

```python
# ATUAL: SHAP fake (heurística)
class ShapCalculator:
    def _calculate_kernel_shap(self, feature_values: Dict) -> Dict:
        # Pesos ARBITRÁRIOS, não SHAP matemático
        contributions = {}
        for feature, avg_value in feature_values.items():
            if feature == 'confidence':
                contribution = (avg_value - 0.5) * 1.5  # arbitrário!
            elif feature == 'risk':
                contribution = -(avg_value - 0.5) * 1.3  # arbitrario!
            contributions[feature] = contribution
        return contributions
```

### Problemas

| Problema | Descrição | Impacto |
|----------|-----------|---------|
| **Sem modelo ML** | SHAP requer f(x), não há modelo subjacente | Crítico |
| **Biblioteca não usada** | `shap` 0.48.0 instalada mas nunca importada | Alto |
| **Base value arbitrário** | Não é E[f(X)], é hardcoded 0.5 | Alto |
| **Testes falsos** | Testam funcionalidade, não corretude | Médio |

### Solução Proposta

**ModelBasedShapCalculator:**
1. Treinar modelo sklearn nas decisões históricas
2. Usar SHAP real (TreeExplainer ou KernelExplainer)
3. Calcular SHAP values matemáticos corretos
4. Fornecer explicações com garantias teóricas

---

## Ticket EPIC-204-01: Modelo ML para SHAP

**ID:** TICKET-EPIC-204-01
**Priority:** Alta
**Effort:** XL (1 semana)

### Tasks

- [ ] 204.01 Criar `src/models/shap_model.py`
- [ ] 204.02 Implementar `DecisionWrapperModel` - wrapper sklearn
- [ ] 204.03 Implementar `FeatureExtractor` - extrai features de decisões
- [ ] 204.04 Implementar `ModelTrainer` - treina modelo histórico
- [ ] 204.05 Criar `ml/shap_training.py` - script de treino
- [ ] 204.06 Implementar coleta de decisões históricas
- [ ] 204.07 Implementar pipeline de treino sklearn
- [ ] 204.08 Implementar persistência do modelo treinado
- [ ] 204.09 Testar treinamento com dados reais
- [ ] 204.10 Validar performance do modelo (accuracy > 0.8)

### Modelo sklearn Proposto

```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import joblib

class DecisionWrapperModel:
    """Wrapper que transforma decisões em features para sklearn."""
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42
        )
        self.feature_names = [
            'confidence', 'risk', 'complexity', 'urgency',
            'resource_usage', 'error_rate', 'latency', 'throughput'
        ]
    
    def extract_features(
        self, 
        decision_data: Dict[str, Any]
    ) -> np.ndarray:
        """Extrai features de uma decisão para treinamento/predição."""
        features = []
        for fname in self.feature_names:
            value = decision_data.get(fname, 0.0)
            features.append(value)
        return np.array(features).reshape(1, -1)
    
    def train(
        self,
        historical_decisions: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Treina modelo com decisões históricas."""
        
        # Extrair features e labels
        X = np.array([
            self.extract_features(d)[0] 
            for d in historical_decisions
        ])
        y = np.array([
            1 if d.get('approved', False) else 0
            for d in historical_decisions
        ])
        
        # Normalizar
        X_scaled = self.scaler.fit_transform(X)
        
        # Treinar
        self.model.fit(X_scaled, y)
        
        # Métricas
        accuracy = self.model.score(X_scaled, y)
        
        return {"accuracy": accuracy, "samples": len(historical_decisions)}
    
    def predict_proba(
        self,
        decision_data: Dict[str, Any]
    ) -> float:
        """Prediz probabilidade de aprovação."""
        X = self.extract_features(decision_data)
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)[0][1]
    
    def save(self, path: str):
        """Salva modelo treinado."""
        joblib.dump({
            'model': self.model,
            'scaler': self.scaler,
            'feature_names': self.feature_names
        }, path)
    
    def load(self, path: str):
        """Carrega modelo treinado."""
        data = joblib.load(path)
        self.model = data['model']
        self.scaler = data['scaler']
        self.feature_names = data['feature_names']
```

### Script de Treino

```python
# ml/shap_training.py
import asyncio
from src.models.shap_model import DecisionWrapperModel
from src.clients.mongodb_client import MongoDBClient

async def train_shap_model():
    # Coletar decisões históricas
    mongo_client = MongoDBClient()
    
    # Buscar últimas 1000 decisões
    decisions = await mongo_client.get_recent_decisions(limit=1000)
    
    # Treinar modelo
    model = DecisionWrapperModel()
    metrics = model.train(decisions)
    
    print(f"Model trained with accuracy: {metrics['accuracy']}")
    
    # Salvar modelo
    model.save("models/shap_model_v1.joblib")
    
    return metrics

if __name__ == "__main__":
    asyncio.run(train_shap_model())
```

### Critérios de Aceite
- [ ] DecisionWrapperModel criado
- [ ] Extração de features funcionando
- [ ] Treino com dados históricos funcionando
- [ ] Accuracy > 0.8
- [ ] Modelo salvo/carregado corretamente

---

## Ticket EPIC-204-02: SHAP Calculator Real

**ID:** TICKET-EPIC-204-02
**Priority:** Alta
**Effort:** XL (1 semana)

### Tasks

- [ ] 204.11 Criar `src/services/model_based_shap.py`
- [ ] 204.12 Implementar `ModelBasedShapCalculator`
- [ ] 204.13 Integrar biblioteca SHAP real
- [ ] 204.14 Implementar `calculate_shap()` - SHAP real
- [ ] 204.15 Implementar `calculate_feature_importance()`
- [ ] 204.16 Implementar `generate_waterfall_plot()`
- [ ] 204.17 Implementar `generate_summary_plot()`
- [ ] 204.18 Criar tests/test_model_based_shap.py
- [ ] 204.19 Validar SHAP values vs heurística
- [ ] 204.20 Testar com decisões reais

### ModelBasedShapCalculator

```python
import shap
from src.models.shap_model import DecisionWrapperModel

class ModelBasedShapCalculator:
    """Calculadora de SHAP usando biblioteca SHAP real."""
    
    def __init__(self, model_path: str):
        self.model_wrapper = DecisionWrapperModel()
        self.model_wrapper.load(model_path)
        
        # Criar explainer SHAP REAL
        # Usar KernelExplainer para modelos não-árvore
        # ou TreeExplainer para RandomForest
        self.explainer = shap.TreeExplainer(
            self.model_wrapper.model,
            feature_perturbation='interventional'
        )
        
        # Background dataset para SHAP
        self.background_data = self._load_background_data()
    
    def calculate_shap(
        self,
        decision_data: Dict[str, Any]
    ) -> SHAPResult:
        """Calcula SHAP values REAIS (não heurística)."""
        
        # Extrair features
        X = self.model_wrapper.extract_features(decision_data)
        X_scaled = self.model_wrapper.scaler.transform(X)
        
        # Calcular SHAP values
        shap_values = self.explainer.shap_values(X_scaled)
        
        # Base value (E[f(X)])
        base_value = self.explainer.expected_value
        
        # Feature importance
        feature_importance = dict(zip(
            self.model_wrapper.feature_names,
            shap_values[0].tolist()
        ))
        
        return SHAPResult(
            method="tree_shap",
            base_value=base_value.tolist(),
            feature_attribution=feature_importance,
            shap_values=shap_values[0].tolist(),
            model_prediction=float(self.model_wrapper.predict_proba(decision_data))
        )
    
    def calculate_feature_importance(
        self,
        decisions: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Calcula importância média das features."""
        
        X = np.array([
            self.model_wrapper.extract_features(d)[0]
            for d in decisions
        ])
        X_scaled = self.model_wrapper.scaler.transform(X)
        
        # SHAP values para todas as decisões
        shap_values = self.explainer.shap_values(X_scaled)
        
        # Importância média (valor absoluto)
        importance = np.abs(shap_values).mean(axis=0)
        
        return dict(zip(
            self.model_wrapper.feature_names,
            importance.tolist()
        ))
    
    def generate_waterfall_plot(
        self,
        decision_data: Dict[str, Any],
        output_path: str
    ) -> str:
        """Gera waterfall plot SHAP."""
        
        # Calcular SHAP
        result = self.calculate_shap(decision_data)
        
        # Criar plot
        shap.plots.waterfall(
            self.explainer,
            max_features=10,
            show=False
        )
        
        # Salvar
        import matplotlib.pyplot as plt
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return output_path
    
    def _load_background_data(self) -> np.ndarray:
        """Carrega dados de fundo para SHAP."""
        # Em produção, carregar amostras reais
        # Por ora, usar dados sintéticos
        import numpy as np
        return np.random.randn(100, len(self.model_wrapper.feature_names))
```

### Critérios de Aceite
- [ ] ModelBasedShapCalculator criado
- [ ] Biblioteca SHAP integrada
- [ ] calculate_shap() retornando valores reais
- [ ] Waterfall plots gerando
- [ ] Testes validando corretude

---

## Ticket EPIC-204-03: Integração API

**ID:** TICKET-EPIC-204-03
**Priority:** Alta
**Effort:** M (4 dias)

### Tasks

- [ ] 204.21 Modificar `src/main.py` - carregar modelo SHAP
- [ ] 204.22 Modificar `src/api/explainability.py`
- [ ] 204.23 Adicionar endpoint usando ModelBasedShapCalculator
- [ ] 204.24 Adicionar endpoint `GET /api/v1/explain/feature-importance`
- [ ] 204.25 Adicionar endpoint `GET /api/v1/explain/waterfall/{decision_id}`
- [ ] 204.26 Manter heurística como fallback
- [ ] 204.27 Adicionar flag `use_real_shap` na config
- [ ] 204.28 Testar integração completa
- [ ] 204.29 Documentar mudanças na API

### API Refatorada

```python
# src/api/explainability.py
from src.services.model_based_shap import ModelBasedShapCalculator

class ExplainabilityRouter:
    def __init__(
        self,
        config: Settings,
        shap_calculator: ModelBasedShapCalculator  # NOVO
    ):
        self.config = config
        self.shap_calculator = shap_calculator
    
    @router.post("/api/v1/explain/{decision_id}")
    async def explain_decision(
        self,
        decision_id: str,
        use_real_shap: bool = True
    ) -> ExplanationResponse:
        """Explica decisão usando SHAP real ou heurística."""
        
        # Buscar decisão
        decision = await self.get_decision(decision_id)
        
        if use_real_shap and self.shap_calculator:
            # SHAP REAL (novo)
            result = await self.shap_calculator.calculate_shap(decision)
            method = "tree_shap"
        else:
            # Heurística (existente, como fallback)
            result = await self.heuristic_calculator.calculate(decision)
            method = "heuristic"
        
        return ExplanationResponse(
            decision_id=decision_id,
            explanation=result,
            method=method,
            generated_at=datetime.now(timezone.utc)
        )
```

### Critérios de Aceite
- [ ] API integrada com SHAP real
- [ ] Endpoint `explain` usando ModelBasedShapCalculator
- [ ] Fallback para heurística funcionando
- [ ] Feature importance endpoint funcionando
- [ ] Waterfall plots gerando

---

## Ticket EPIC-204-04: Treino Contínuo

**ID:** TICKET-EPIC-204-04
**Priority:** Média
**Effort:** S (3 dias)

### Tasks

- [ ] 204.30 Implementar retreino automático mensal
- [ ] 204.31 Implementar validação de modelo antes do deploy
- [ ] 204.32 Implementar rollback se performance cai
- [ ] 204.33 Adicionar métricas de modelo monitoramento
- [ ] 204.34 Testar ciclo de treino → validação → deploy

### Critérios de Aceite
- [ ] Retreino automático funcionando
- [ ] Validação antes de deploy funcionando
- [ ] Rollback automático funcionando

---

## Resumo do Epic

| Ticket | Descrição | Effort | Deliverables |
|--------|-----------|--------|--------------|
| EPIC-204-01 | Modelo ML para SHAP | 1 semana | DecisionWrapperModel |
| EPIC-204-02 | SHAP Calculator Real | 1 semana | ModelBasedShapCalculator |
| EPIC-204-03 | Integração API | 4 dias | API + endpoints |
| EPIC-204-04 | Treino Contínuo | 3 dias | Retreino automático |
| **TOTAL** | | **3 semanas** | **SHAP real implementado** |

---

## Arquitetura Final

```
                    ┌─────────────────────────────────────┐
                    │            API Layer                │
                    │  POST /api/v1/explain/{decision_id} ││
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │      ExplainabilityRouter           │
                    │  - explain_decision()               │
                    │  - feature_importance()             │
                    └─────────────────┬───────────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
    ┌───────────────────────┐                  ┌──────────────────────┐
    │ ModelBasedShapCalc    │                  │ HeuristicCalc       │
    │ (SHAP real)           │                  │ (fallback)          │
    │ - shap.TreeExplainer  │                  │ - pesos arbitrários  │
    └───────────┬───────────┘                  └──────────────────────┘
                │
    ┌───────────▼───────────┐
    │ DecisionWrapperModel  │
    │ (sklearn RandomForest)│
    │ - predict_proba()     │
    │ - feature_names       │
    └───────────────────────┘
```

---

## Handoff para Claude Code

```
@~/.agent-os/instructions/execute-tasks.md

Epic: EPIC-204 - SHAP Values Implementation
Spec: .agent-os/specs/2026-03-31-sprint2-features-incompletas/
```
