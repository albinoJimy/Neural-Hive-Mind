# Testes do ML Inference API

Este diretório contém os testes abrangentes para o serviço ML Inference API.

## Estrutura

```
tests/
├── conftest.py                    # Configuração pytest e fixtures globais
├── unit/                          # Testes unitários
│   ├── test_predictor_service.py  # Testes do serviço de predição
│   ├── test_batch_engine.py       # Testes do engine de batch
│   └── test_circuit_breaker.py    # Testes do circuit breaker
└── integration/                   # Testes de integração
    └── test_api.py                # Testes dos endpoints REST
```

## Executar os Testes

### Todos os testes
```bash
pytest tests/
```

### Apenas unitários
```bash
pytest tests/unit/
```

### Apenas integração
```bash
pytest tests/integration/
```

### Com cobertura
```bash
pytest tests/ --cov=src --cov-report=html --cov-report=term
```

### Com verbosidade
```bash
pytest tests/ -v
```

### Teste específico
```bash
pytest tests/unit/test_predictor_service.py::TestPredictFromText::test_predict_from_text_success -v
```

## Dependências

```bash
pip install pytest pytest-asyncio pytest-cov httpx
```

## Variáveis de Ambiente

As variáveis são configuradas automaticamente no `conftest.py`:

- `MLFLOW_TRACKING_URI`: http://localhost:5000
- `MODEL_NAME`: approval_model
- `REDIS_HOST`: localhost
- `PROMETHEUS_PORT`: 9090
- `ENVIRONMENT`: test

## Padrões Seguidos

1. **AAA Pattern**: Arrange-Act-Assert em todos os testes
2. **Descrições claras**: DADO-QUANDO-ENTÃO em docstrings
3. **Fixtures reutilizáveis**: Configuração centralizada
4. **Async/await**: Testes assíncronos com pytest-asyncio
5. **Mocks**: unittest.mock para isolamento

## Cobertura

- Unitários: ~90% de cobertura alvo
- Integração: Endpoints principais cobertos
- Total: 150+ testes cases
