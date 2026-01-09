# Worker Agents Integration Tests

This directory contains integration tests for the Worker Agents service, covering all four executor types (Build, Deploy, Test, Validate) with support for both mock and real external services.

## Test Structure

```
tests/
├── conftest.py                      # Pytest configuration and fixtures
├── fixtures/
│   ├── __init__.py
│   ├── executor_fixtures.py         # Mock executor and client factories
│   ├── client_fixtures.py           # Mock HTTP server implementations
│   └── opa-policies/
│       └── policy.rego              # Sample OPA policy for tests
├── helpers/
│   ├── __init__.py
│   └── integration_helpers.py       # Test helpers and validators
├── integration/
│   ├── test_build_executor_real.py      # BuildExecutor integration tests
│   ├── test_deploy_executor_real.py     # DeployExecutor integration tests
│   ├── test_test_executor_real.py       # TestExecutor integration tests
│   ├── test_validate_executor_real.py   # ValidateExecutor integration tests
│   └── test_executors_integration_full.py  # Full E2E flow tests
├── scripts/
│   ├── setup-integration-env.sh     # Start Docker services
│   ├── teardown-integration-env.sh  # Stop Docker services
│   └── wait-for-services.sh         # Health check script
└── .env.integration.example         # Environment configuration template
```

## Test Categories

Tests are organized using pytest markers:

| Marker | Description |
|--------|-------------|
| `integration` | All integration tests |
| `executor_integration` | Integration tests for worker agent executors |
| `real_integration` | Tests requiring real external services |
| `argocd` | ArgoCD-specific tests |
| `code_forge` | Code Forge-specific tests |
| `github_actions` | GitHub Actions-specific tests |
| `opa` | OPA policy validation tests |
| `sonarqube` | SonarQube-specific tests |
| `trivy` | Trivy security scanning tests |
| `snyk` | Snyk vulnerability scanning tests |
| `checkov` | Checkov IaC scanning tests |
| `slow` | Tests that take more than 1 minute |

## Testes de Integracao de Executors

### Estrutura

Os testes de integracao de executors estao organizados da seguinte forma:

```
tests/integration/
├── test_deploy_executor_integration.py    # Testes para DeployExecutor (ArgoCD/Flux)
├── test_test_executor_integration.py      # Testes para TestExecutor (GitHub Actions/GitLab CI/Jenkins)
├── test_validate_executor_integration.py  # Testes para ValidateExecutor (OPA/Trivy)
├── test_execute_executor_integration.py   # Testes para ExecuteExecutor (K8s/Docker/Lambda/Local)
├── run_executor_integration_tests.sh      # Script para executar testes
└── fixtures/
    ├── __init__.py
    └── testcontainers_helpers.py          # Helpers para testcontainers
```

### Executar Testes de Executors

```bash
# Todos os testes de integracao de executors
bash tests/integration/run_executor_integration_tests.sh

# Testes especificos por executor
bash tests/integration/run_executor_integration_tests.sh deploy
bash tests/integration/run_executor_integration_tests.sh test
bash tests/integration/run_executor_integration_tests.sh validate
bash tests/integration/run_executor_integration_tests.sh execute

# Com coverage
bash tests/integration/run_executor_integration_tests.sh --cov

# Verbose mode
bash tests/integration/run_executor_integration_tests.sh -v
```

### Cobertura de Cenarios por Executor

| Executor | Cenarios Cobertos | Testes |
|----------|-------------------|--------|
| **DeployExecutor** | ArgoCD success, Flux success, timeout, API error, fallback, retry | 12+ testes |
| **TestExecutor** | GitHub Actions, GitLab CI, Jenkins, local fallback, parsing, retry | 12+ testes |
| **ValidateExecutor** | OPA allow/deny, timeout, API error, Trivy, metricas | 12+ testes |
| **ExecuteExecutor** | K8s, Docker, Lambda, Local, fallback chain, timeout, simulation | 15+ testes |

### Fixtures Disponiveis

Os testes utilizam fixtures mockadas em `conftest.py`:

- `mock_argocd_client`: Cliente ArgoCD mockado
- `mock_flux_client`: Cliente Flux mockado
- `mock_github_actions_client`: Cliente GitHub Actions mockado
- `mock_gitlab_ci_client`: Cliente GitLab CI mockado
- `mock_jenkins_client`: Cliente Jenkins mockado
- `mock_opa_client`: Cliente OPA mockado
- `mock_k8s_jobs_client`: Cliente Kubernetes Jobs mockado
- `mock_docker_runtime_client`: Cliente Docker mockado
- `mock_lambda_runtime_client`: Cliente Lambda mockado
- `mock_local_runtime_client`: Cliente Local mockado

### Testcontainers (Opcional)

Para testes mais realistas, helpers de testcontainers estao disponiveis em `fixtures/testcontainers_helpers.py`:

```python
from fixtures.testcontainers_helpers import start_opa_container

# Iniciar container OPA real
container = start_opa_container()
opa_url = get_container_url(container, 8181)

# Executar testes...

container.stop()
```

## Running Tests

### Quick Start (Mock Mode)

Run all integration tests with mocked services:

```bash
cd services/worker-agents
pytest tests/integration/ -m "integration and not real_integration" -v
```

### With Docker Services

1. Start the test environment:

```bash
./tests/scripts/setup-integration-env.sh
```

2. Run tests:

```bash
pytest tests/integration/ -m "integration and not real_integration" -v --tb=short
```

3. Stop services:

```bash
./tests/scripts/teardown-integration-env.sh
```

### Using Docker Compose Profiles

```bash
# Minimal services (OPA + Redis)
./tests/scripts/setup-integration-env.sh

# With Kafka
./tests/scripts/setup-integration-env.sh --kafka

# Full profile (includes ArgoCD, SonarQube)
./tests/scripts/setup-integration-env.sh --full

# Mock profile (lightweight mocks only)
./tests/scripts/setup-integration-env.sh --mock
```

### Real Integration Tests

To run tests against real external services:

1. Copy and configure the environment file:

```bash
cp tests/.env.integration.example tests/.env.integration
# Edit .env.integration with real service credentials
```

2. Set the test mode:

```bash
export INTEGRATION_TEST_MODE=real
```

3. Run real integration tests:

```bash
pytest tests/integration/ -m "real_integration" -v
```

## Test Modes

The `INTEGRATION_TEST_MODE` environment variable controls test behavior:

| Mode | Description |
|------|-------------|
| `mock` (default) | Use mocked services only |
| `real` | Use real external services |
| `hybrid` | Use real where available, mock otherwise |

## Environment Variables

See `.env.integration.example` for all available configuration options:

### Core Configuration

```bash
INTEGRATION_TEST_MODE=mock  # mock | real | hybrid
TEST_TIMEOUT_SECONDS=300
PYTEST_TIMEOUT=300
```

### Service Configuration

```bash
# Code Forge
CODE_FORGE_URL=http://localhost:8000
CODE_FORGE_ENABLED=true

# ArgoCD
ARGOCD_URL=http://localhost:8081
ARGOCD_TOKEN=<your-token>
ARGOCD_ENABLED=false

# OPA
OPA_URL=http://localhost:8181
OPA_ENABLED=true

# GitHub Actions
GITHUB_TOKEN=<your-token>
GITHUB_ACTIONS_ENABLED=false

# SonarQube
SONARQUBE_URL=http://localhost:9000
SONARQUBE_TOKEN=<your-token>
SONARQUBE_ENABLED=false

# Redis
REDIS_URL=redis://localhost:6379
REDIS_ENABLED=true
```

## Writing Tests

### Using Test Helpers

```python
from tests.helpers.integration_helpers import ExecutorTestHelper, ResultValidator

# Create test tickets
ticket = ExecutorTestHelper.create_build_ticket(
    artifact_id='my-app',
    branch='main',
    commit_sha='abc123',
)

# Validate results
ResultValidator.assert_success(result)
ResultValidator.assert_simulated(result, expected=False)
ResultValidator.assert_has_output(result, 'pipeline_id', 'artifact_id')
```

### Using Mock Clients

```python
from tests.fixtures.executor_fixtures import create_mock_code_forge_client

# Create a mock that returns success
mock_client = create_mock_code_forge_client(
    pipeline_id='pipeline-123',
    status='completed',
)

# Create a mock that fails
mock_client = create_mock_code_forge_client(
    should_fail=True,
)

# Create a mock that fails then succeeds (for retry testing)
mock_client = create_mock_code_forge_client(
    pipeline_id='pipeline-123',
    status='completed',
    fail_after_retries=2,  # Fails first 2 attempts
)
```

### Test Class Example

```python
import pytest
from tests.fixtures.executor_fixtures import create_mock_code_forge_client
from tests.helpers.integration_helpers import ExecutorTestHelper, ResultValidator

pytestmark = [pytest.mark.integration]

class TestMyFeature:
    @pytest.mark.asyncio
    async def test_build_with_mock(self, worker_config, mock_vault_client, mock_metrics):
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        mock_client = create_mock_code_forge_client(status='completed')

        executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket(artifact_id='test')
        result = await executor.execute(ticket)

        ResultValidator.assert_success(result)

@pytest.mark.real_integration
@pytest.mark.code_forge
class TestRealCodeForge:
    """These tests only run when CODE_FORGE_URL is configured."""

    @pytest.mark.asyncio
    async def test_real_build(self, worker_config, mock_vault_client, mock_metrics):
        # Will be skipped if INTEGRATION_TEST_MODE=mock
        pass
```

## CI/CD Integration

The integration tests run in GitHub Actions via the `test-and-coverage.yml` workflow:

```yaml
worker-agents-integration:
  name: Worker Agents Integration Tests
  runs-on: ubuntu-latest
  services:
    opa:
      image: openpolicyagent/opa:latest
      ports:
        - 8181:8181
    redis:
      image: redis:7-alpine
      ports:
        - 6379:6379
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
    - name: Install dependencies
      run: pip install -r services/worker-agents/requirements.txt
    - name: Run integration tests
      env:
        INTEGRATION_TEST_MODE: mock
        OPA_URL: http://localhost:8181
        REDIS_URL: redis://localhost:6379
      run: |
        pytest tests/integration/ \
          -m "integration and not real_integration" \
          --cov=src \
          --cov-report=xml
```

## Test Coverage Goals

- **Unit tests**: 80%+ coverage
- **Integration tests**: 80%+ coverage of executor code paths
- **E2E tests**: Cover critical workflows (build-deploy-test-validate)

## Troubleshooting

### Common Issues

**Tests skip with "OPA_URL not configured"**

Ensure the environment is properly configured:
```bash
export OPA_URL=http://localhost:8181
./tests/scripts/setup-integration-env.sh
```

**Connection refused errors**

Services may not be ready. Increase wait time:
```bash
./tests/scripts/wait-for-services.sh 180  # Wait up to 180 seconds
```

**Tests timeout**

Increase the test timeout:
```bash
export PYTEST_TIMEOUT=600
pytest tests/integration/ --timeout=600
```

### Debug Mode

Run tests with verbose output:
```bash
pytest tests/integration/ -v --tb=long --capture=no
```

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
pytest tests/integration/ -v
```

## Contributing

When adding new tests:

1. Use appropriate markers for test categorization
2. Use `ExecutorTestHelper` and `ResultValidator` for consistency
3. Support both mock and real service modes where applicable
4. Add any new environment variables to `.env.integration.example`
5. Update this README if adding new test categories
