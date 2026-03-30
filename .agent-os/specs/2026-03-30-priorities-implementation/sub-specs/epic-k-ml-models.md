# Sub-Spec: Epic K - Modelos ML para Especialistas

## Objetivo

Treinar 5 modelos ML (um por especialista) e integrar nos serviços especialistas para usar modelos em produção.

## Scripts de Treino

### 1. train_business_specialist.py
**Arquivo:** `ml_pipelines/training/train_business_specialist.py`
**Funcionalidades:**
- Dataset sintético para business (1000+ amostras)
- Features: business value, ROI, cost-benefit, process efficiency
- Treinar GradientBoostingClassifier
- Salvar no MLflow

```python
def generate_business_dataset(n_samples=1000):
    """Gera dataset sintético para especialista business."""
    np.random.seed(42)

    X = pd.DataFrame({
        "business_value": np.random.uniform(0, 1, n_samples),
        "roi_score": np.random.uniform(0, 1, n_samples),
        "cost_benefit_ratio": np.random.uniform(0, 1, n_samples),
        "process_efficiency": np.random.uniform(0, 1, n_samples),
        "strategic_alignment": np.random.uniform(0, 1, n_samples),
        "market_impact": np.random.uniform(0, 1, n_samples),
    })

    # Regra: approve se business_value + roi_score > 1.2
    y = (X["business_value"] + X["roi_score"] > 1.2).astype(int)

    return X, y

def main():
    X, y = generate_business_dataset(1000)

    model = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=5,
        random_state=42
    )

    model.fit(X, y)

    mlflow.sklearn.log_model(
        model,
        "business_specialist_model",
        registered_model_name="BusinessSpecialistModel"
    )
```

### 2. train_technical_specialist.py
**Arquivo:** `ml_pipelines/training/train_technical_specialist.py`
**Funcionalidades:** Similar ao business_specialist
**Features:** code-quality, security-score, performance-score, complexity-score

### 3. train_architecture_specialist.py
**Arquivo:** `ml_pipelines/training/train_architecture_specialist.py`
**Funcionalidades:** Similar ao business_specialist
**Features:** solid-compliance, design-pattern-score, coupling-score, cohesion-score

### 4. train_behavior_specialist.py
**Arquivo:** `ml_pipelines/training/train_behavior_specialist.py`
**Funcionalidades:** Similar ao business_specialist
**Features:** accessibility-score, ux-score, usability-score, user-satisfaction

### 5. train_evolution_specialist.py
**Arquivo:** `ml_pipelines/training/train_evolution_specialist.py`
**Funcionalidades:** Similar ao business_specialist
**Features:** maintainability-score, scalability-score, extensibility-score, tech-debt-score

## Integração nos Especialistas

### Arquivos a modificar
- `services/specialist-business/src/specialist.py`
- `services/specialist-technical/src/specialist.py`
- `services/specialist-architecture/src/specialist.py`
- `services/specialist-behavior/src/specialist.py`
- `services/specialist-evolution/src/specialist.py`

### Integração
```python
# ANTES (usando apenas heurísticas)
class BusinessSpecialist(BaseSpecialist):
    def _evaluate_plan_internal(self, plan: dict) -> Opinion:
        # Apenas heurísticas
        score = self._calculate_heuristic_score(plan)
        return Opinion(...)

# DEPOIS (modelo ML + heurísticas)
class BusinessSpecialist(BaseSpecialist):
    def __init__(self, ...):
        super().__init__(...)
        self.ml_model = None
        self._load_ml_model()

    def _load_ml_model(self):
        """Carrega modelo do MLflow."""
        try:
            import mlflow
            self.ml_model = mlflow.pyfunc.load_model("models:/BusinessSpecialistModel/Production")
        except Exception as e:
            logger.warning(f"Failed to load ML model: {e}, using heuristics only")

    def _evaluate_plan_internal(self, plan: dict) -> Opinion:
        # Usar modelo ML se disponível
        if self.ml_model is not None:
            features = self._extract_features(plan)
            ml_score = self.ml_model.predict(features)[0]
            heuristic_score = self._calculate_heuristic_score(plan)

            # Combinar ML + heurística
            final_score = 0.7 * ml_score + 0.3 * heuristic_score
        else:
            # Fallback para heurísticas
            final_score = self._calculate_heuristic_score(plan)

        return Opinion(..., confidence=final_score)
```

## Configuração MLflow

```python
# services/specialist-business/src/config/settings.py
MLFLOW_TRACKING_URI: str = Field(default="http://mlflow.neural-hive.svc.cluster.local:5000")
BUSINESS_SPECIALIST_MODEL_NAME: str = Field(default="BusinessSpecialistModel")
BUSINESS_SPECIALIST_MODEL_VERSION: str = Field(default="Production")
```

## Deploy

```bash
# Executar treino
python ml_pipelines/training/train_business_specialist.py
python ml_pipelines/training/train_technical_specialist.py
python ml_pipelines/training/train_architecture_specialist.py
python ml_pipelines/training/train_behavior_specialist.py
python ml_pipelines/training/train_evolution_specialist.py

# Verificar modelos no MLflow
mlflow ui
# Navegar para models -> BusinessSpecialistModel -> versions

# Verificar integração
kubectl logs -f specialist-business | grep "ML model"
```

## Testes

```python
def test_specialist_with_ml_model():
    """Testa especialista usando modelo ML."""
    specialist = BusinessSpecialist(config=MockConfig())

    # Given: plano com features
    plan = sample_cognitive_plan()

    # When: avaliar
    opinion = specialist._evaluate_plan_internal(plan)

    # Then: opinião gerada
    assert opinion.recommendation in ["approve", "reject"]
    assert opinion.confidence >= 0.0
    assert opinion.confidence <= 1.0

def test_specialist_ml_model_fallback():
    """Testa fallback para heurísticas se ML falhar."""
    specialist = BusinessSpecialist(config=MockConfig())
    specialist.ml_model = None  # Simular falha

    plan = sample_cognitive_plan()
    opinion = specialist._evaluate_plan_internal(plan)

    # Deve usar heurísticas
    assert opinion.recommendation in ["approve", "reject"]
```

## Verificação

```bash
# Verificar modelos treinados
mlflow models ls | grep -E "(Business|Technical|Architecture|Behavior|Evolution)SpecialistModel"

# Verificar integração
kubectl logs -f specialist-business | grep "ML model loaded"
kubectl logs -f specialist-technical | grep "ML model loaded"
kubectl logs -f specialist-architecture | grep "ML model loaded"
kubectl logs -f specialist-behavior | grep "ML model loaded"
kubectl logs -f specialist-evolution | grep "ML model loaded"

# Testar predição
curl -X POST http://specialist-business.neural-hive.svc.cluster.local:50051/specialist.BusinessSpecialist/EvaluatePlan \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "test"}'
```
