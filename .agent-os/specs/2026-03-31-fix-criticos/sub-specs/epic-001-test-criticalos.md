# EPIC-001: Fix Test Críticos

**ID:** EPIC-001
**Status:** Pending
**Priority:** P0 - Blocker
**Effort:** XL (3 semanas)
**Related Services:** worker-agents, semantic-translation-engine, specialist-behavior

---

## Resumo Executivo

Este Epic aborda 3 issues críticos que impedem a execução de 30+ testes no CI/CD:
1. **C1: worker-agents** - 12 testes falhando por import errors
2. **C2: semantic-translation-engine** - 18 testes NLP falhando (numpy/spaCy)
3. **C3: specialist-behavior** - 61 testes sem coverage real (mock-only)

---

## Ticket EPIC-001-01: Fix Import Errors worker-agents

**ID:** TICKET-EPIC-001-01
**Priority:** P0
**Effort:** M (1 semana)
**Service:** worker-agents

### Problema
12 testes falham com `ImportError: attempted relative import beyond top-level package`

### Análise Técnica
**Arquivos afetados:**
- `src/executors/deploy_executor.py`
- `src/executors/build_executor.py`
- `src/executors/test_executor.py`
- `src/executors/validate_executor.py`
- `src/executors/execute_executor.py`
- `src/executors/compensate_executor.py`

**Causa raiz:** Imports relativos `from ..clients.argocd_client import ...` falham quando pytest adiciona `src` ao sys.path.

**Imports problemáticos:**
```python
# INCORRETO
from ..clients.argocd_client import ArgoCDClient
from ..clients.code_forge_client import CodeForgeClient
from ..clients.flux_client import FluxClient

# CORRETO
from clients.argocd_client import ArgoCDClient
from clients.code_forge_client import CodeForgeClient
from clients.flux_client import FluxClient
```

### Solução

**Passo 1:** Modificar imports relativos para absolutos em todos os executors

**Arquivo:** `src/executors/deploy_executor.py`
```python
# Linha ~15 - Substituir
from ..clients.argocd_client import (
    ArgoCDClient,
    ArgoCDAPIError,
    ...
)

# Por
from clients.argocd_client import (
    ArgoCDClient,
    ArgoCDAPIError,
    ...
)
```

**Arquivo:** `src/executors/build_executor.py`
```python
# Substituir
from ..clients.code_forge_client import CodeForgeClient, PipelineStatus

# Por
from clients.code_forge_client import CodeForgeClient, PipelineStatus
```

**Passo 2:** Executar testes para validar
```bash
cd services/worker-agents
python3 -m pytest tests/ -v --tb=short
```

### Testes Esperados Passando
1. `test_build_executor_integration`
2. `test_deploy_executor_integration`
3. `test_test_executor_integration`
4. `test_validate_executor_integration`
5. `test_execute_executor_integration`
6. `test_compensate_executor_integration`
7. `test_executors_real`
8. `test_build_executor_real`
9. `test_executors_integration_full`
10. `test_kafka_ticket_consumer_avro`
11. `test_kafka_ticket_consumer_backpressure`
12. `test_result_producer_avro`

### Critérios de Aceite
- [ ] Todos os 12 testes passam
- [ ] Zero ImportError
- [ ] Imports consistentes em todos os executors
- [ ] CI/CD verde

---

## Ticket EPIC-001-02: Fix NLP Tests semantic-translation-engine

**ID:** TICKET-EPIC-001-02
**Priority:** P0
**Effort:** M (1 semana)
**Service:** semantic-translation-engine

### Problema
18 testes NLP falham com `ValueError: numpy.dtype size changed, may indicate binary incompatibility`

### Análise Técnica
**Versões problemáticas:**
- numpy: 2.2.6 (causa erro)
- spaCy: 3.7.2
- thinc: 8.2.5

**Causa:** numpy 2.x mudou a estrutura de numpy.dtype, quebrando compatibilidade binária com thinc compilado.

**Testes falhando (18):**
1-4. TestNLPProcessorExtractKeywords (4 testes)
5-11. TestNLPProcessorExtractObjectives (7 testes)
12-14. TestNLPProcessorExtractEntities (3 testes)
15-16. TestNLPProcessorLanguageDetection (2 testes)
17-18. TestSemanticParserWithNLP (2 testes)

### Solução

**Opção Recomendada: Downgrade numpy**

**Passo 1:** Modificar requirements.txt
```bash
# services/semantic-translation-engine/requirements.txt

# Substituir
numpy>=2.0.0

# Por
numpy==1.26.4
```

**Passo 2:** Reinstalar dependências
```bash
cd services/semantic-translation-engine
pip install numpy==1.26.4
pip install -r requirements.txt
```

**Passo 3:** Baixar modelos spaCy (se necessário)
```bash
python3 -m spacy download en_core_web_sm
python3 -m spacy download pt_core_news_sm
```

**Passo 4:** Executar testes
```bash
python3 -m pytest tests/unit/test_nlp_processor.py -v
python3 -m pytest tests/integration/test_semantic_parser_with_nlp.py -v
```

### Critérios de Aceite
- [ ] Todos os 18 testes NLP passam
- [ ] Zero ValueError de numpy.dtype
- [ ] Modelos spaCy carregando corretamente
- [ ] CI/CD verde

### Plano de Contingência
Se downgrade numpy causar conflitos:
- Considerar upgrade spaCy para 3.8+ (não testado)
- Ou usar fallback heurístico temporariamente

---

## Ticket EPIC-001-03: Refactor Tests specialist-behavior

**ID:** TICKET-EPIC-001-03
**Priority:** P0
**Effort:** L (2 semanas)
**Service:** specialist-behavior

### Problema
61 testes passam mas 0% coverage real porque testam mocks em vez do código fonte.

### Análise Técnica
**Código fonte existente (não testado):**
- `src/specialist.py` - BehaviorSpecialist (515 linhas)
- `src/config.py` - BehaviorSpecialistConfig (395 linhas)
- `src/main.py` - Entry point (159 linhas)
- `src/http_server.py` - HealthHandler (131 linhas)
- `src/http_server_fastapi.py` - FastAPI server (354 linhas)

**Testes atuais:**
- Usam classes Mock reimplementadas manualmente
- Não importam código de `src/`
- Testam comportamento esperado, não implementação real

### Solução

**Fase 1: Corrigir Importações**
```python
# tests/test_behavior_specialist.py
from specialist import BehaviorSpecialist
from config import BehaviorSpecialistConfig
from unittest.mock import MagicMock, patch
```

**Fase 2: Testar Classe Principal**

**Arquivo NOVO:** `tests/test_specialist_class.py`
```python
import pytest
from specialist import BehaviorSpecialist
from config import BehaviorSpecialistConfig

class TestBehaviorSpecialist:
    def test_initialization(self):
        config = BehaviorSpecialistConfig()
        specialist = BehaviorSpecialist(config)
        assert specialist._get_specialist_type() == "behavior"

    def test_load_model_with_mlflow(self):
        # Mock MLflow client
        with patch('specialist.mlflow') as mock_mlflow:
            config = BehaviorSpecialistConfig()
            specialist = BehaviorSpecialist(config)
            specialist._load_model()
            assert specialist._model is not None

    # Mais testes...
```

**Fase 3: Testar Métodos Privados**

**Arquivo NOVO:** `tests/test_specialist_methods.py`
```python
import pytest
from specialist import BehaviorSpecialist
from config import BehaviorSpecialistConfig

class TestBehaviorSpecialistMethods:
    def test_analyze_usability(self):
        config = BehaviorSpecialistConfig()
        specialist = BehaviorSpecialist(config)
        plan = create_test_plan()

        usability = specialist._analyze_usability(plan)
        assert usability is not None
        assert 0 <= usability <= 1

    def test_analyze_accessibility(self):
        # Similar pattern
        pass

    def test_calculate_behavioral_risk(self):
        # Similar pattern
        pass
```

**Fase 4: Testar Servidores HTTP**

**Arquivo NOVO:** `tests/test_http_servers.py`
```python
from http_server import HealthHandler

class TestHealthHandler:
    def test_health_endpoint(self):
        handler = HealthHandler()
        response = handler.do_GET()
        assert response.status == 200

    def test_ready_endpoint(self):
        # Similar pattern
        pass

    def test_metrics_endpoint(self):
        # Similar pattern
        pass
```

**Fase 5: Testes de Integração**

**Arquivo NOVO:** `tests/integration/test_evaluate_plan.py`
```python
import pytest
from specialist import BehaviorSpecialist
from config import BehaviorSpecialistConfig

class TestEvaluatePlanIntegration:
    def test_full_evaluation_flow(self):
        config = BehaviorSpecialistConfig()
        specialist = BehaviorSpecialist(config)
        plan = create_complete_test_plan()

        result = specialist._evaluate_plan_internal(plan)
        assert result is not None
        assert result.recommendation is not None
        assert result.reasoning is not None
```

### Critérios de Aceite
- [ ] Testes importam código real de `src/`
- [ ] Coverage real > 70%
- [ ] Todos os métodos principais testados
- [ ] Servidores HTTP testados
- [ ] Testes de integração passam
- [ ] 61 testes originais migrados ou substituídos

### Estrutura Final de Testes
```
tests/
├── conftest.py (atualizado)
├── test_behavior_specialist.py (mantido, atualizado)
├── test_specialist_class.py (NOVO)
├── test_specialist_methods.py (NOVO)
├── test_config.py (NOVO)
├── test_http_servers.py (NOVO)
├── test_fastapi_server.py (NOVO)
├── test_ml_integration.py (atualizado)
└── integration/
    ├── test_evaluate_plan.py (NOVO)
    └── test_lifecycle.py (NOVO)
```

---

## Resumo do Epic

| Ticket | Service | Effort | Testes Impactados |
|--------|---------|--------|-------------------|
| EPIC-001-01 | worker-agents | 1 semana | 12 |
| EPIC-001-02 | semantic-translation-engine | 1 semana | 18 |
| EPIC-001-03 | specialist-behavior | 2 semanas | 61 |
| **TOTAL** | | **4 semanas** | **91 testes** |

---

## Dependências

- **EPIC-001-01** pode ser feito em paralelo com EPIC-001-02
- **EPIC-001-03** depende de completude dos anteriores (melhor práticas)

## Ordem de Execução Recomendada

1. **Semana 1:** EPIC-001-01 (worker-agents) + EPIC-001-02 (semantic-translation-engine) - paralelo
2. **Semana 2-3:** EPIC-001-03 (specialist-behavior)
3. **Semana 4:** Buffer para testes finais e documentação

---

## Handoff para Claude Code

Para executar este Epic, use:
```
@~/.agent-os/instructions/execute-tasks.md

Epic: EPIC-001 - Fix Test Críticos
Tickets: EPIC-001-01, EPIC-001-02, EPIC-001-03
```
