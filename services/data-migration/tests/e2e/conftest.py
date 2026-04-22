"""Pytest configuration e fixtures para testes E2E."""


def pytest_configure(config):
    """Registra marcadores customizados."""
    config.addinivalue_line("markers", "e2e: mark test as E2E test")
