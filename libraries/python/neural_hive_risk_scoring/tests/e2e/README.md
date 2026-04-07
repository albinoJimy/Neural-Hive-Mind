# E2E Tests - neural_hive_risk_scoring

Testes de ponta a ponta (End-to-End) para a biblioteca `neural_hive_risk_scoring`.

## Visão Geral

Os testes E2E validam o fluxo completo de avaliação de risco, integrando todos os componentes da biblioteca:

- **RiskScoringEngine**: Orquestração principal
- **RiskCalculator**: Cálculo base de scores
- **RiskEnsemble**: Refinamento ensemble
- **RiskHistoryManager**: Rastreamento histórico
- **RiskAlertManager**: Geração de alertas
- **RiskScoringMetrics**: Métricas Prometheus

## Estrutura dos Testes

```
tests/e2e/
├── __init__.py
├── conftest.py           # Fixtures específicas E2E
├── test_e2e_risk_scoring.py  # Suite principal E2E
└── README.md             # Este arquivo
```

## Categorias de Testes

### 1. TestE2ERiskScoringPipeline
Valida o pipeline completo de avaliação:
- Fluxo de avaliação completa
- Scoring ensemble
- Rastreamento histórico
- Geração de alertas
- Registro de métricas

### 2. TestE2ERiskBands
Valida classificação em bandas de risco:
- VERY_LOW (0.0 - 0.2)
- LOW (0.2 - 0.4)
- MEDIUM (0.4 - 0.6)
- HIGH (0.6 - 0.8)
- CRITICAL (0.8 - 1.0)

### 3. TestE2EIntegration
Valida integração entre componentes:
- Calculator + Ensemble
- History + Alerts
- Avaliações concorrentes

### 4. TestE2EErrorHandling
Valida tratamento de erros:
- Votos vazios
- Votos malformados
- Dados faltantes

### 5. TestE2EPerformance
Valida requisitos de performance:
- Latência de avaliação (< 100ms)
- Lote de avaliações (< 50ms média)
- Efetividade de cache

## Executar Testes

### Todos os testes E2E
```bash
pytest libraries/python/neural_hive_risk_scoring/tests/e2e/ -v
```

### Apenas testes marcados como E2E
```bash
pytest -m e2e libraries/python/neural_hive_risk_scoring/tests/e2e/ -v
```

### Apenas testes de performance
```bash
pytest -m performance libraries/python/neural_hive_risk_scoring/tests/e2e/ -v
```

### Com coverage
```bash
pytest libraries/python/neural_hive_risk_scoring/tests/e2e/ --cov=risk_scoring --cov-report=html
```

## Fixtures Disponíveis

### Configuração
- `e2e_config`: Configuração base para testes E2E
- `e2e_timestamp`: Timestamp consistente
- `sample_decision_context`: Contexto de decisão exemplo

### Cenários de Baixo Risco
- `low_risk_scenario`: Dados de domínio de baixo risco
- `low_risk_votes`: Votos de especialistas de baixo risco

### Cenários de Alto Risco
- `high_risk_scenario`: Dados de domínio de alto risco
- `high_risk_votes`: Votos de especialistas de alto risco

### Cenários Mistas
- `mixed_risk_votes`: Votos mistos (consenso dividido)

### Mocks
- `mock_async_mongodb`: Cliente MongoDB mockado

### Performance
- `e2e_performance_thresholds`: Limites de performance

## Requisitos de Performance

| Métrica | Limite | Descrição |
|---------|-------|-----------|
| `max_assessment_latency_ms` | 100 | Latência máxima de avaliação |
| `max_batch_avg_latency_ms` | 50 | Latência média em lote |
| `max_cache_lookup_ms` | 1 | Lookup de cache |
| `min_cache_hit_rate` | 0.5 | Taxa mínima de cache hit |

## Integração CI/CD

Os testes E2E são executados automaticamente no pipeline CI/CD:

```yaml
# .github/workflows/test-risk-scoring.yml
- name: Run E2E tests
  run: |
    pytest libraries/python/neural_hive_risk_scoring/tests/e2e/ -v --tb=short
```

## Troubleshooting

### Testes falham com import errors
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/libraries/python"
pytest libraries/python/neural_hive_risk_scoring/tests/e2e/ -v
```

### Testes de performance falham
- Verificar se há outros processos consumindo CPU
- Executar em modo isolado (sem outros testes)

### Mock MongoDB não funciona
- Verificar se pymongo está instalado
- Os mocks usam unittest.mock.AsyncMock

## Adicionando Novos Testes

1. Criar nova classe de testes herdando padrões existentes
2. Usar fixtures do `conftest.py` quando possível
3. Marcar com `@pytest.mark.e2e` se apropriado
4. Seguir convenções de nomenclatura: `test_e2e_*`

Exemplo:
```python
class TestE2EMyFeature:
    """Testes E2E da minha feature."""

    @pytest.mark.asyncio
    async def test_my_feature_flow(self, risk_engine, low_risk_scenario):
        """Testa fluxo completo da minha feature."""
        result = await risk_engine.my_feature(low_risk_scenario)
        assert result is not None
```
