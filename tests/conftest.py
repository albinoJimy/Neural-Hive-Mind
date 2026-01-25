"""
Root pytest configuration for Neural Hive Mind tests.

This top-level conftest handles pytest_plugins registration
to comply with pytest requirements.
"""

import logging

import pytest

# Configure logging for all tests
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Register fixture modules at top level (required by pytest)
# These are conditionally loaded - missing modules are skipped
pytest_plugins = []

_fixture_modules = [
    "tests.e2e.fixtures.kubernetes",
    "tests.e2e.fixtures.kafka",
    "tests.e2e.fixtures.databases",
    "tests.e2e.fixtures.services",
    "tests.e2e.fixtures.test_data",
    "tests.e2e.fixtures.schema_registry",
    "tests.e2e.fixtures.avro_helpers",
    "tests.e2e.fixtures.specialists",
    "tests.e2e.fixtures.circuit_breakers",
]

for module in _fixture_modules:
    try:
        __import__(module)
        pytest_plugins.append(module)
    except ImportError:
        pass


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    # Markers are also defined in pytest.ini but we ensure they're registered
    pass
