# Testing Strategy - Neural Hive Mind

Este documento descreve a estrategia de testes para a plataforma Neural Hive Mind,
incluindo estrutura, padroes, fixtures compartilhados e melhores praticas.

## Estrutura de Testes

```
services/
├── code-forge/
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py          # Fixtures globais do servico
│       ├── unit/
│       │   ├── __init__.py
│       │   ├── conftest.py      # Fixtures especificos para unit tests
│       │   ├── test_template_selector.py
│       │   ├── test_code_composer.py
│       │   ├── test_validator.py
│       │   └── ...
│       └── integration/
│           ├── __init__.py
│           └── ...
├── mcp-tool-catalog/
│   └── tests/
│       ├── conftest.py
│       └── unit/
│           ├── test_genetic_tool_selector.py
│           ├── test_tool_registry.py
│           └── ...
└── worker-agents/
    └── tests/
        ├── conftest.py
        └── unit/
            ├── test_github_actions_client.py
            ├── test_jenkins_client.py
            └── ...
```

## Tipos de Testes

### Unit Tests

Testes isolados de componentes individuais com dependencias mockadas.

**Localizacao:** `tests/unit/`

**Caracteristicas:**
- Sem dependencias externas (MongoDB, Redis, Kafka, etc.)
- Todas as dependencias sao mockadas
- Execucao rapida (< 1 segundo por teste)
- Cobertura minima: 80%

**Exemplo:**

```python
@pytest.mark.asyncio
async def test_template_selector_mcp_integration(
    mock_mcp_client,
    mock_redis_client,
    sample_ticket
):
    """Deve selecionar template via MCP."""
    from src.services.template_selector import TemplateSelector

    selector = TemplateSelector(
        mcp_client=mock_mcp_client,
        redis_client=mock_redis_client
    )

    result = await selector.select_template(sample_ticket)

    assert result is not None
    mock_mcp_client.request_tool_selection.assert_called_once()
```

### Integration Tests

Testes que verificam integracao entre componentes.

**Localizacao:** `tests/integration/`

**Caracteristicas:**
- Podem usar servicos reais ou simulados
- Modo `mock` (padrao) ou `real`
- Execucao mais lenta (1-30 segundos por teste)

**Configuracao:**

```bash
# Modo mock (padrao)
export INTEGRATION_TEST_MODE=mock
pytest tests/integration/

# Modo real (requer servicos externos)
export INTEGRATION_TEST_MODE=real
pytest tests/integration/ -m real_integration
```

## Fixtures Compartilhados

### conftest.py Padrao

Todo servico deve ter um `tests/conftest.py` com fixtures basicos:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_mongodb_client():
    """Mock para MongoDB client."""
    client = AsyncMock()
    client.insert_one = AsyncMock(return_value=MagicMock(inserted_id='test-id'))
    client.find_one = AsyncMock(return_value={})
    return client

@pytest.fixture
def mock_redis_client():
    """Mock para Redis client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=True)
    return client

@pytest.fixture
def mock_metrics():
    """Mock para Prometheus metrics."""
    metrics = MagicMock()
    metrics.counter = MagicMock()
    metrics.counter.labels.return_value.inc = MagicMock()
    metrics.histogram = MagicMock()
    metrics.histogram.labels.return_value.observe = MagicMock()
    return metrics
```

### Fixtures Especificos por Servico

#### Code Forge

```python
@pytest.fixture
def mock_mcp_client():
    """Mock para MCPToolCatalogClient."""
    client = AsyncMock()
    client.request_tool_selection = AsyncMock(return_value={
        'request_id': str(uuid.uuid4()),
        'selected_tools': [],
        'total_fitness_score': 0.88,
        'selection_method': 'GENETIC_ALGORITHM'
    })
    return client

@pytest.fixture
def sample_ticket():
    """Ticket de execucao sample."""
    return {
        'ticket_id': str(uuid.uuid4()),
        'artifact_type': 'CODE',
        'language': 'python',
        'description': 'Test component'
    }
```

#### MCP Tool Catalog

```python
@pytest.fixture
def cli_tool():
    """Ferramenta CLI sample."""
    from src.models.tool_descriptor import ToolDescriptor, ToolCategory, IntegrationType

    return ToolDescriptor(
        tool_id='pytest-001',
        tool_name='pytest',
        category=ToolCategory.VALIDATION,
        integration_type=IntegrationType.CLI,
        version='8.0.0',
        reputation_score=0.95
    )
```

#### Worker Agents

```python
@pytest.fixture
def worker_config():
    """Configuracao do Worker Agent."""
    from src.config.settings import WorkerAgentSettings

    return WorkerAgentSettings(
        service_name='worker-agents-test',
        argocd_enabled=False,
        opa_enabled=True
    )

@pytest.fixture
def deploy_ticket():
    """Ticket de deploy sample."""
    return {
        'ticket_id': str(uuid.uuid4()),
        'task_type': 'DEPLOY',
        'parameters': {
            'namespace': 'test-ns',
            'deployment_name': 'test-app'
        }
    }
```

## Configuracao pytest.ini

```ini
[pytest]
pythonpath = .
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
    --disable-warnings
    --cov=src
    --cov-report=term-missing
    --cov-report=html
    --cov-report=xml
    --cov-fail-under=80
    --junit-xml=test-results/junit.xml
    --asyncio-mode=auto
markers =
    asyncio: mark test as async
    unit: mark test as unit test
    integration: mark test as integration test
    slow: mark test as slow running
```

## Scripts de Execucao

### run-tests.sh

Cada servico possui um script `run-tests.sh`:

```bash
# Executar todos os testes
./run-tests.sh

# Apenas testes unitarios
./run-tests.sh unit

# Apenas testes de integracao
./run-tests.sh integration

# Com relatorio de cobertura detalhado
./run-tests.sh coverage
```

### validate-test-coverage.sh

Script global para validar cobertura:

```bash
# Validar todos os servicos
./scripts/validate-test-coverage.sh

# Validar servico especifico
./scripts/validate-test-coverage.sh code-forge

# Gerar relatorio
./scripts/validate-test-coverage.sh --report
```

## CI/CD Integration

### GitHub Actions

O workflow `test-and-coverage.yml` executa:

1. **Unit Tests** - Todas as versoes Python (3.11, 3.12)
2. **Integration Tests** - Com servicos Docker (MongoDB, Redis, Neo4j, Kafka)
3. **Service Tests** - Testes especificos por servico
4. **Code Forge Tests** - Testes do Code Forge
5. **MCP Tool Catalog Tests** - Testes do MCP Tool Catalog
6. **Quality Gate** - Verifica threshold de cobertura (85%)

### Coverage Reports

- **Codecov** - Upload automatico de reports
- **Artifacts** - Reports salvos como artifacts do workflow
- **HTML Reports** - Disponivel em `htmlcov/index.html`

## Melhores Praticas

### 1. Organizacao de Testes

- Um arquivo de teste por modulo fonte
- Classes de teste agrupam testes relacionados
- Nomes descritivos: `test_<scenario>_<expected_behavior>`

### 2. Mocking

- Use `AsyncMock` para funcoes async
- Use `MagicMock` para funcoes sync
- Mock apenas dependencias externas, nao a logica de negocio

### 3. Fixtures

- Prefira fixtures sobre setup/teardown
- Reutilize fixtures atraves de conftest.py
- Use scope apropriado (`function`, `class`, `module`, `session`)

### 4. Assertions

- Uma assertion principal por teste
- Use mensagens de erro descritivas
- Verifique tanto sucesso quanto falha

### 5. Cobertura

- Minimo 80% para unit tests
- Foque em caminhos criticos
- Nao escreva testes apenas para cobertura

## Executando Testes Localmente

```bash
# Instalar dependencias de teste
pip install pytest pytest-asyncio pytest-cov

# Navegar para o servico
cd services/code-forge

# Executar testes
pytest tests/unit/ -v

# Com cobertura
pytest tests/unit/ --cov=src --cov-report=html

# Abrir relatorio
open htmlcov/index.html
```

## Troubleshooting

### Testes Async Falhando

Verifique se `pytest-asyncio` esta instalado e configurado:

```ini
# pytest.ini
addopts = --asyncio-mode=auto
```

### Import Errors

Verifique `pythonpath` no pytest.ini:

```ini
pythonpath = .
```

### Coverage Incorreta

Verifique se `--cov=src` esta apontando para o diretorio correto.

### Fixtures Nao Encontrados

Certifique-se que `conftest.py` esta no diretorio correto e nao tem erros de sintaxe.
