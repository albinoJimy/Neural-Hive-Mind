# Plano de Profissionalização IA/ML - Neural Hive Mind

**Data:** 2026-04-24
**Status:** 🔴 CRÍTICO - Plano de Ação para 100% Maturidade
**Versão:** 1.0

---

## Resumo Executivo

Após análise profunda dos documentos `REVISAO_ANALISE_CRITICA_2026-04-24.md` e `analise-critica-IA-ML-hard.md`, confirmamos **4 pontos VÁLIDOS** que requerem ação imediata, e **2 pontos INCORRETOS** que devem ser desconsiderados.

**Veredito Final:** NHM tem IA real (22.4% dos componentes), mas a implementação de ML precisa ser profissionalizada.

---

## Matriz de Validação das Acusações

| ID | Acrímacação | Status | Evidência | Ação Necessária |
|----|-------------|--------|-----------|-----------------|
| 1 | Specialist-* tem "neural" no nome | ❌ INCORRETO | Nomes: specialist-technical, specialist-business, etc. | Nenhuma |
| 2 | Consensus Engine "Bayesian" é fraude | ❌ INCORRETO | Implementa BMA real com prior/posterior | Nenhuma |
| 3 | Feature engineering amador (30 regex) | ✅ CORRETO | Confirmado em `approval_predictor.py:59-142` | **PRIORIDADE 1** |
| 4 | Modelo v6 overfit (F1=1.0) | ✅ CORRETO | Confirmado em `approval_predictor.py:28` | **PRIORIDADE 0** |
| 5 | Lazy loading spaCy | ⚠️ PARCIAL | Modelo principal carregado na init | **PRIORIDADE 2** |
| 6 | LLM Client duplicado | ✅ CORRETO | code-forge + architect-agent implementações diferentes | **PRIORIDADE 1** |

---

## Plano de Ação para 100% Maturidade

### FASE 1: Correções Críticas (Semana 1)

#### 1.1 Descartar Modelo v6 e Implementar Coleta de Dados Real

**Problema Atual:**
```python
# ml_pipelines/inference/approval_predictor.py:28
"""
Versões disponíveis:
- v6: 50 amostras, F1-Score 1.0000 (possível overfit)  # ❌ INÚTIL
- v7: 75 amostras, F1-Score 0.9120 (melhor generalização)  # ⚠️ Ainda insuficiente
"""
```

**Solução:**

1. **Imediatamente:** Remover referência ao modelo v6
2. **Implementar coleta de dados real:**
   - Logging de todas as aprovações/rejeições humanas
   - Armazenar com features NLP completas
   - Meta: 10.000+ amostras antes de re-treinar

**Arquivos a modificar:**
- `ml_pipelines/inference/approval_predictor.py` - Remover v6
- `approval-service/src/services/approval_service.py` - Adicionar logging estruturado
- `ml_pipelines/training/train_predictive_models.py` - Implementar coleta contínua

#### 1.2 Feature Engineering Profissional

**Problema Atual:**
```python
# approval_predictor.py:73-95 - 30 regex manuais
domain_keywords = {
    "security": r"\b(security|ssl|tls|authentication|...)\b",
    "performance": r"\b(performance|optimize|index|...)\b",
    # ... (30 features hardcoded)
}
```

**Solução: Substituir por TF-IDF + Embeddings**

```python
# Implementação profissional proposta
from sklearn.feature_extraction.text import TfidfVectorizer
from sentence_transformers import SentenceTransformer

class ProfessionalFeatureExtractor:
    """Feature engineering profissional para NLP"""

    def __init__(self):
        # TF-IDF para keywords locais (1000+ features vs 30 manuais)
        self.tfidf = TfidfVectorizer(
            max_features=1000,
            ngram_range=(1, 2),  # bigramas para contexto
            min_df=2,
            max_df=0.8
        )

        # Sentence Transformer para embeddings semânticos (384 dims)
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')

    def extract_features(self, texts: List[str]) -> np.ndarray:
        """Extrai features profissionais: TF-IDF + Embeddings"""
        # TF-IDF features (sparsity para eficiência)
        tfidf_features = self.tfidf.fit_transform(texts)

        # Semantic embeddings (captura significado)
        semantic_features = self.embedder.encode(texts)

        # Concatenar: 1000 (TF-IDF) + 384 (embedding) = 1384 features
        return np.hstack([tfidf_features.toarray(), semantic_features])
```

**Benefícios:**
- ✅ Escalável: não precisa adicionar keywords manualmente
- ✅ Semântico: captura significado, não apenas palavras
- ✅ 1384 features vs 30 atuais (46x mais rico)

#### 1.3 Unificar LLM Client

**Problema Atual:**
- `code-forge/src/clients/llm_client.py` - 408 linhas, com retry/tenacity
- `architect-agent/src/planners/llm_client.py` - 123 linhas, implementação diferente

**Solução: Criar biblioteca compartilhada**

```
libraries/neural_hive_llm/
├── neural_hive_llm/
│   ├── __init__.py
│   ├── client.py           # Cliente unificado
│   ├── providers.py        # OpenAI, Anthropic, Ollama
│   ├── retry.py            # Lógica de retry com tenacity
│   └── fallback.py         # Fallback robusto entre providers
├── tests/
│   └── test_client.py
├── pyproject.toml
└── README.md
```

**API Unificada:**
```python
from neural_hive_llm import LLMClient, LLMProvider

# Configuração única
client = LLMClient(
    provider=LLMProvider.OPENAI,
    fallback_provider=LLMProvider.ANTHROPIC,  # Auto-fallback
    api_key=settings.openai_key,
    max_retries=3,
    timeout=60.0
)

# Uso consistente em todos os serviços
response = await client.generate(
    prompt="Generate code for...",
    system_prompt="You are an expert..."
)
```

---

### FASE 2: Infraestrutura de ML (Semana 2-3)

#### 2.1 Drift Detection

```python
# ml_pipelines/monitoring/drift_detector.py
from evidently import ColumnDriftMetric
from evidently.report import Report

class ModelDriftDetector:
    """Detecta drift de dados em produção"""

    def detect_drift(self, new_data: pd.DataFrame, reference_data: pd.DataFrame):
        """Compara dados novos com dados de treino"""
        drift_report = Report(metrics=[
            ColumnDriftMetric(col) for col in self.feature_columns
        ])

        drift_report.run(
            reference_data=reference_data,
            current_data=new_data
        )

        drift_score = drift_report.as_dict()["metrics"][0]["drift_score"]

        if drift_score > 0.5:  # Threshold configurável
            logger.warning("Drift detectado!", score=drift_score)
            return True  # Re-train necessário

        return False
```

#### 2.2 Métricas de Qualidade

```python
# services/approval-service/src/observability/ml_metrics.py
from prometheus_client import Histogram, Counter

approval_predictor_accuracy = Histogram(
    "approval_predictor_accuracy",
    "Accuracy do approval predictor em produção",
    buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

approval_predictor_confidence = Histogram(
    "approval_predictor_confidence",
    "Confidence score das predições",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

model_drift_detected = Counter(
    "model_drift_detected_total",
    "Número de detecções de drift"
)
```

#### 2.3 Auto-Retrain Integration

```python
# ml_pipelines/monitoring/auto_retrain.py
class AutoRetrainScheduler:
    """Scheduler para re-treino automático"""

    async def check_and_retrain(self):
        """Verifica drift e dispara re-treino se necessário"""
        # 1. Coletar dados recentes
        new_data = await self.collect_recent_data(days=7)

        # 2. Verificar drift
        if self.drift_detector.detect_drift(new_data, self.reference_data):
            # 3. Disparar re-treino
            new_model = await self.train_new_model(new_data)

            # 4. Validar antes de deploy
            if self.validate_model(new_model):
                await self.deploy_model(new_model)

                # 5. Registrar métrica
                model_retrained_total.inc()
```

---

### FASE 3: Testes E2E (Semana 3-4)

#### 3.1 Testes de Inferência em Produção

```python
# tests/integration/approval_predictor_e2e.py
import pytest
from ml_pipelines.inference.approval_predictor import ApprovalPredictor

@pytest.fixture
def predictor():
    return ApprovalPredictor()

def test_predictor_with_real_data(predictor):
    """Testa predictor com dados de produção reais"""
    # Carregar dataset de produção (golden set)
    production_data = load_golden_set()

    correct_predictions = 0
    total = len(production_data)

    for text, expected_decision in production_data:
        result = predictor.predict_from_text(text)

        # Asserts
        assert result["confidence"] > 0.3, f"Confidence muito baixa: {text}"
        assert result["decision"] in ["approve", "reject", "review_required"]

        # Verificar acurácia
        if result["decision"] == expected_decision:
            correct_predictions += 1

    # Acurácia mínima: 80%
    accuracy = correct_predictions / total
    assert accuracy >= 0.8, f"Acurácia {accuracy:.2%} abaixo do threshold 80%"

def test_predictor_risk_detection(predictor):
    """Testa detecção de intenções de risco"""
    dangerous_intentions = [
        "Delete all users from database",
        "Drop production tables without backup",
        "Disable authentication for all users",
    ]

    for text in dangerous_intentions:
        result = predictor.predict_from_text(text)
        # Deve rejeitar ou pedir revisão
        assert result["decision"] in ["reject", "review_required"], \
            f"Intenção perigosa não detectada: {text}"
```

---

## Roadmap de Implementação

| Semana | Fase | Tasks | Deliverables |
|--------|------|-------|--------------|
| 1 | FASE 1 | 1.1 Descartar v6<br>1.2 Feature engineering profissional<br>1.3 Unificar LLM Client | Feature extractor profissional<br>Biblioteca neural_hive_llm |
| 2-3 | FASE 2 | 2.1 Drift detection<br>2.2 Métricas de qualidade<br>2.3 Auto-retrain | Drift detector em produção<br>Métricas no Grafana |
| 3-4 | FASE 3 | 3.1 Testes E2E<br>3.2 Documentação atualizada | Suite de testes E2E<br>Docs atualizados |
| 4+ | MANUTENÇÃO | Coleta contínua de dados<br>Retreino mensal | Modelo em evolução contínua |

---

## Métricas de Sucesso

### Antes (Estado Atual)
- Feature engineering: 30 regex manuais
- Dataset: 75 amostras
- Overfit: F1-Score 1.0 (v6)
- Drift detection: ❌ Não implementado
- Testes E2E: ❌ Não existem

### Depois (100% Maturidade)
- Feature engineering: TF-IDF (1000) + Embeddings (384) = 1384 features
- Dataset: 10.000+ amostras coletadas continuamente
- Generalização: F1-Score ~0.85-0.92 em validação cruzada
- Drift detection: ✅ Monitoramento 24/7
- Testes E2E: ✅ Golden set com 100+ casos

---

## Conclusão

**Estado Atual:** NHM tem IA real (22.4% dos componentes) mas com implementação amadora em alguns pontos.

**Objetivo:** Atingir 100% de maturidade profissional nos componentes ML críticos.

**Tempo Estimado:** 4 semanas para implementação completa.

**Investimento:** ~160 horas de desenvolvimento.

---

**Fim do Plano**
**Próximo Passo:** Executar FASE 1.1 - Descartar modelo v6 e implementar coleta de dados real.
