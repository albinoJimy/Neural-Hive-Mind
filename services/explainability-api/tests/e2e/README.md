# E2E Tests - Explainability API v3

Testes de ponta a ponta (End-to-End) para a Explainability API v3.

## Visão Geral

Os testes E2E validam o fluxo completo de geração de explicações hierárquicas, integrando:

- **V3ExplanationService**: Serviço principal
- **HierarchicalExplainer**: Breakdown por senioridade
- **CounterfactualAnalyzer**: Análise contrafactual
- **TemporalTracker**: Análise temporal
- **MongoDB**: Persistência de dados

## Estrutura dos Testes

```
tests/e2e/
├── __init__.py
├── test_e2e_explainability.py  # Suite principal E2E
└── README.md  # Este arquivo
```

## Categorias de Testes

### 1. TestE2EFullExplanation
Valida o fluxo completo de explicação:
- Explicação básica
- Com análise contrafactual
- Com análise temporal

### 2. TestE2EHierarchicalBreakdown
Valida breakdown hierárquico:
- Níveis de senioridade
- Nível dominante
- Força de consenso

### 3. TestE2EIndividualContributions
Valida contribuições individuais:
- Ordenação por rank
- Campos obrigatórios

### 4. TestE2EBatchExplanations
Valida explicações em lote:
- Fluxo básico
- Com falhas

### 5. TestE2EErrorHandling
Valida tratamento de erros:
- Decisões inexistentes
- Votos vazios

### 6. TestE2EIntegration
Valida integração entre componentes:
- HierarchicalExplainer
- CounterfactualAnalyzer
- TemporalTracker

### 7. TestE2EPerformance
Valida requisitos de performance:
- Latência de explicação (< 500ms)
- Lote de explicações

## Executar Testes

### Todos os testes E2E
```bash
pytest services/explainability-api/tests/e2e/ -v
```

### Com cobertura
```bash
pytest services/explainability-api/tests/e2e/ --cov=src --cov-report=html
```

### Apenas uma classe de testes
```bash
pytest services/explainability-api/tests/e2e/test_e2e_explainability.py::TestE2EFullExplanation -v
```

## Requisitos de Performance

| Métrica | Limite | Descrição |
|---------|-------|-----------|
| `max_full_explanation_latency_ms` | 500 | Latência máxima explicação completa |
| `max_batch_avg_latency_ms` | 200 | Latência média em lote |

## Fixtures Principais

### sample_decision_votes
Votos de especialistas de exemplo para testes.

### sample_consensus_decision
Decisão de consenso completa com votos.

### mock_mongodb
Cliente MongoDB mockado para testes.

### v3_service
Instância do V3ExplanationService configurada.

## Integração CI/CD

```yaml
- name: Run E2E tests
  run: |
    pytest services/explainability-api/tests/e2e/ -v --tb=short
```

## Troubleshooting

### Testes falham com import errors
```bash
export PYTHONPATH="${PYTHONPATH}:services/explainability-api/src"
pytest services/explainability-api/tests/e2e/ -v
```

### Testes de performance falham
- Verificar carga da máquina
- Executar isoladamente

## Adicionando Novos Testes

```python
class TestE2EMyFeature:
    """Testes E2E da minha feature."""

    @pytest.mark.asyncio
    async def test_my_feature_flow(self, v3_service):
        """Testa fluxo completo da minha feature."""
        result = await v3_service.my_feature_method()
        assert result is not None
```
