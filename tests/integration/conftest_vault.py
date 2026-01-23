"""
Shared fixtures for Vault integration tests.
This module is imported by all vault rotation test files to share the module cache.
"""
import sys
import os
from unittest.mock import MagicMock

# Cache the module to avoid re-registering prometheus metrics
_vault_integration_module = None

# Path to the services directory
_services_root = os.path.join(os.path.dirname(__file__), '..', '..', 'services', 'orchestrator-dynamic')
_services_src = os.path.join(_services_root, 'src')


def get_vault_integration_class():
    """
    Import OrchestratorVaultClient with all necessary mocks.
    Uses importlib to avoid triggering __init__.py imports.
    Caches the module to avoid Prometheus metric duplication across all test files.
    """
    global _vault_integration_module

    if _vault_integration_module is not None:
        return _vault_integration_module.OrchestratorVaultClient

    # Check if already loaded in a previous test file
    if 'vault_integration_cached' in sys.modules:
        _vault_integration_module = sys.modules['vault_integration_cached']
        return _vault_integration_module.OrchestratorVaultClient

    import importlib.util

    # Mock the security library
    mock_security = MagicMock()
    mock_security.VaultClient = MagicMock()
    sys.modules['neural_hive_security'] = mock_security
    sys.modules['neural_hive_security.vault_client'] = mock_security

    # Add paths if not already added
    if _services_root not in sys.path:
        sys.path.insert(0, _services_root)
    if _services_src not in sys.path:
        sys.path.insert(0, _services_src)

    # Load vault_integration directly without going through __init__.py
    vault_integration_path = os.path.join(_services_src, 'clients', 'vault_integration.py')
    spec = importlib.util.spec_from_file_location("vault_integration_cached", vault_integration_path)
    vault_module = importlib.util.module_from_spec(spec)
    sys.modules['vault_integration_cached'] = vault_module
    spec.loader.exec_module(vault_module)

    _vault_integration_module = vault_module
    return vault_module.OrchestratorVaultClient
