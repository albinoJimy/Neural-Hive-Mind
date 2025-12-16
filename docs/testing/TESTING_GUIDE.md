# Guia de Testes - Neural Hive-Mind

## Visão Geral

O projeto Neural Hive-Mind mantém **85% de cobertura de testes** através de:
- Testes unitários (isolados, rápidos)
- Testes de integração (com containers)
- Testes E2E (Kubernetes)
- Quality gates automáticos no CI/CD

## Executar Testes Localmente

### Testes Unitários
```bash
pytest libraries/python/neural_hive_specialists/tests/ -m "unit"
```

### Testes de Integração
```bash
pytest tests/integration/ -m "integration"
```

### Validar Coverage
```bash
./scripts/validation/validate-coverage.sh
```
> Certifique-se de ter o pacote `coverage` instalado (presente em `requirements-dev.txt`).

## Estrutura de Testes

### Markers
- `@pytest.mark.unit` - Testes unitários isolados
- `@pytest.mark.integration` - Testes com containers
- `@pytest.mark.e2e` - Testes end-to-end
- `@pytest.mark.slow` - Testes >5s
- `@pytest.mark.benchmark` - Testes de performance

### Fixtures
Ver `conftest.py` para fixtures compartilhadas:
- `mock_config` - Configuração de teste
- `mongodb_container` - Container MongoDB
- `redis_container` - Container Redis
- `mock_mlflow_client` - MLflow mockado
- `mock_ledger_client` - Ledger mockado

## Quality Gates

### CI/CD
- Coverage >= 85% (fail se abaixo)
- Todos os testes devem passar
- Lint (flake8, black, mypy) sem erros

### Pre-commit
Configurar pre-commit hook:
```bash
# .git/hooks/pre-commit
#!/bin/bash
./scripts/validation/validate-coverage.sh
```

## Adicionar Novos Testes

### Template de Teste Unitário
```python
import pytest
from unittest.mock import Mock

@pytest.mark.unit
def test_my_function(mock_config):
    # Arrange
    input_data = {"key": "value"}
    
    # Act
    result = my_function(input_data)
    
    # Assert
    assert result is not None
    assert result["status"] == "success"
```

### Template de Teste de Integração
```python
import pytest

@pytest.mark.integration
@pytest.mark.asyncio
async def test_my_integration(mongodb_container):
    # Arrange
    client = MongoClient(mongodb_container.get_connection_url())
    
    # Act
    result = await my_async_function(client)
    
    # Assert
    assert result is not None
```

## Troubleshooting

### Coverage Baixo
1. Executar com `--cov-report=html` para ver linhas não cobertas
2. Adicionar testes para branches não testados
3. Verificar se fixtures estão mockando corretamente

### Testes Lentos
1. Usar `@pytest.mark.slow` para testes >5s
2. Executar apenas testes rápidos: `pytest -m "not slow"`
3. Usar testcontainers com escopo de sessão

### Testes Flaky
1. Adicionar retry com `@pytest.mark.flaky(reruns=3)`
2. Aumentar timeouts
3. Usar fixtures com cleanup adequado
