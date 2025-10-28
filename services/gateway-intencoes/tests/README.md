# Tests for Gateway Intencoes Service

This directory contains comprehensive tests for the gateway-intencoes service, including both unit and integration tests.

## Structure

```
tests/
├── unit/                      # Unit tests (no external dependencies)
│   ├── test_redis_client.py   # Redis client tests with mocks
│   └── test_oauth2_validator.py # OAuth2 validator tests with mocks
├── integration/               # Integration tests (require external services)
│   ├── test_redis_integration.py # Real Redis cluster tests
│   └── test_keycloak_integration.py # Real Keycloak tests
└── README.md                 # This file
```

## Test Categories

### Unit Tests

Unit tests run quickly and don't require external services. They use mocks and stubs to test business logic in isolation.

**Coverage includes:**
- Redis client operations (get, set, delete, pipeline)
- Circuit breaker functionality
- OAuth2 token validation logic
- JWKS caching behavior
- Error handling and edge cases

**Run unit tests:**
```bash
# Fast unit tests only
python run_tests.py --type unit

# With coverage
python run_tests.py --type unit --coverage

# Parallel execution
python run_tests.py --type unit --parallel
```

### Integration Tests

Integration tests validate the complete functionality against real external services using testcontainers.

**Redis Integration Tests:**
- Real Redis Cluster operations
- Pipeline operations across different hash slots
- TTL expiration behavior
- Connection failure recovery
- Circuit breaker integration

**Keycloak Integration Tests:**
- Real JWT token validation
- JWKS fetching and caching
- Token introspection
- User info retrieval
- Failure scenario handling

**Requirements:**
- Docker (for testcontainers)
- Available ports for test containers

**Run integration tests:**
```bash
# Integration tests only (requires Docker)
python run_tests.py --type integration

# All tests (unit + integration)
python run_tests.py --type all
```

## Key Features Tested

### Redis Client
- ✅ Cluster-aware pipeline operations
- ✅ Hash slot grouping and execution
- ✅ Circuit breaker protection
- ✅ TTL and expiration handling
- ✅ JSON serialization/deserialization
- ✅ Connection failure recovery
- ✅ Distributed locking
- ✅ Cache statistics and metrics

### OAuth2 Validator
- ✅ JWT token validation with signature verification
- ✅ JWKS fetching and caching with TTL
- ✅ Token introspection via Keycloak API
- ✅ User info retrieval
- ✅ Offline token validation (development mode)
- ✅ Custom claims and role validation
- ✅ Error handling for various failure scenarios
- ✅ Concurrent request handling

## Running Tests

### Prerequisites

Install test dependencies:
```bash
pip install -r requirements-test.txt
```

### Test Commands

```bash
# Unit tests only (fast)
pytest -m "not integration"

# Integration tests only (requires Docker)
pytest -m integration

# All tests
pytest

# With coverage report
pytest --cov=src --cov-report=html

# Parallel execution
pytest -n auto

# Verbose output
pytest -v

# Using the test runner script
python run_tests.py --help
```

### Test Markers

Tests are marked with pytest markers for easy filtering:

- `@pytest.mark.unit` - Unit tests (default)
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Tests that take longer to run

## Configuration

Test configuration is defined in `pytest.ini`:
- Minimum coverage threshold: 80%
- Async test support enabled
- Coverage reports in HTML and XML formats
- Strict marker and configuration validation

## CI/CD Integration

The tests are designed for CI/CD pipelines:

1. **Pull Requests**: Run unit tests on every PR
2. **Nightly/Scheduled**: Run full integration test suite
3. **Coverage Reports**: Generate and publish coverage metrics
4. **Quality Gates**: Enforce minimum coverage thresholds

### GitHub Actions Example

```yaml
# Unit tests on every PR
- name: Run Unit Tests
  run: python run_tests.py --type unit --coverage --parallel

# Integration tests on schedule or label
- name: Run Integration Tests
  if: contains(github.event.label.name, 'integration-tests')
  run: python run_tests.py --type integration
```

## Troubleshooting

### Common Issues

1. **Testcontainers not starting**: Ensure Docker is running and accessible
2. **Redis connection errors**: Check if Redis container ports are available
3. **Keycloak startup timeout**: Increase wait time for Keycloak container readiness
4. **Import errors**: Ensure the `src` directory is in Python path

### Skip Integration Tests

If Docker is not available, integration tests will be automatically skipped:

```bash
# This will only run unit tests if testcontainers is not available
pytest
```

### Debug Test Failures

```bash
# Verbose output with full stack traces
pytest -vvv --tb=long

# Run specific test file
pytest tests/unit/test_redis_client.py -v

# Run specific test method
pytest tests/unit/test_redis_client.py::TestRedisClient::test_pipeline_single_slot -v
```

## Contributing

When adding new tests:

1. **Unit tests**: Mock external dependencies, focus on business logic
2. **Integration tests**: Use testcontainers for real service integration
3. **Coverage**: Maintain >80% code coverage
4. **Documentation**: Update this README for new test categories
5. **Markers**: Use appropriate pytest markers for test classification

## Performance Considerations

- Unit tests should complete in <5 seconds total
- Integration tests may take 30-60 seconds due to container startup
- Use `pytest -n auto` for parallel execution to speed up test runs
- Consider test order and dependencies when running in parallel