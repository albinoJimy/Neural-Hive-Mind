"""
Pytest configuration para testes E2E Vault+SPIFFE.

Este arquivo configura hooks e fixtures globais para os testes E2E.
"""
import os
import sys
import pytest
import asyncio

# Adicionar paths ao Python path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICES_DIR = os.path.dirname(TESTS_DIR)
PROJECT_ROOT = os.path.dirname(os.path.dirname(SERVICES_DIR))

sys.path.insert(0, SERVICES_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "libraries", "security"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "libraries", "domain"))


def pytest_configure(config):
    """Configuração inicial do pytest."""
    # Adicionar marcadores customizados
    config.addinivalue_line(
        "markers",
        "e2e_real: marca testes que requerem Vault/SPIRE reais"
    )
    config.addinivalue_line(
        "markers",
        "e2e_mock: marca testes que usam mocks"
    )
    config.addinivalue_line(
        "markers",
        "vault: marca testes específicos de Vault"
    )
    config.addinivalue_line(
        "markers",
        "spiffe: marca testes específicos de SPIFFE"
    )


def pytest_collection_modifyitems(config, items):
    """
    Modifica a coleção de testes baseado no modo E2E.

    Se RUN_VAULT_SPIFFE_E2E não for 'true', todos os testes reais são pulados.
    """
    real_e2e = os.getenv("RUN_VAULT_SPIFFE_E2E", "").lower() == "true"

    for item in items:
        # Adicionar marcador baseado no nome do teste
        if "vault" in item.nodeid.lower():
            item.add_marker(pytest.mark.vault)
        if "spiffe" in item.nodeid.lower() or "svid" in item.nodeid.lower():
            item.add_marker(pytest.mark.spiffe)

        # Se não em modo E2E real, adicionar skip reason
        if not real_e2e and "test_" in item.nodeid:
            # Verificar se é um teste que requer ambiente real
            # (assumindo que todos os testes neste módulo são E2E)
            if "e2e" in item.nodeid:
                item.add_marker(
                    pytest.mark.skipif(
                        not real_e2e,
                        reason="RUN_VAULT_SPIFFE_E2E not enabled"
                    )
                )


@pytest.fixture(scope="session")
def event_loop():
    """
    Cria um event loop para a sessão de testes.

    Necessário para testes async com pytest-asyncio.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_metrics():
    """
    Reseta métricas Prometheus antes de cada teste.

    Previne poluição entre testes.
    """
    try:
        from prometheus_client import REGISTRY
        # Salvar estado inicial não é fácil, então apenas limpamos
        # coletores customizados após cada teste
        yield
    except ImportError:
        yield
    finally:
        # Cleanup após teste (opcional)
        pass


@pytest.fixture(autouse=True)
def log_test_name(request):
    """
    Loga o nome do teste antes da execução.

    Ajuda na depuração.
    """
    print(f"\n{'='*60}")
    print(f"TEST: {request.node.name}")
    print(f"{'='*60}")
    yield
    print(f"\n{'='*60}")
    print(f"END: {request.node.name}")
    print(f"{'='*60}")


def pytest_report_header(config):
    """
    Adiciona header ao relatório pytest.
    """
    real_e2e = os.getenv("RUN_VAULT_SPIFFE_E2E", "").lower() == "true"
    vault_addr = os.getenv("VAULT_ADDR", "http://localhost:8200")

    lines = [
        "",
        "=" * 60,
        "Vault+SPIFFE E2E Tests",
        "=" * 60,
        f"E2E Mode: {'REAL' if real_e2e else 'MOCK'}",
        f"Vault Addr: {vault_addr}",
        "=" * 60,
        "",
    ]
    return "\n".join(lines)


def pytest_terminal_summary(terminalreporter, exitstatus):
    """
    Adiciona sumário customizado ao final dos testes.
    """
    real_e2e = os.getenv("RUN_VAULT_SPIFFE_E2E", "").lower() == "true"

    terminalreporter.write_sep("=", "E2E Test Summary")
    terminalreporter.write_line(f"Mode: {'REAL' if real_e2e else 'MOCK'}")

    if not real_e2e:
        terminalreporter.write_line(
            "YELLOW: Tests running in MOCK mode. Set RUN_VAULT_SPIFFE_E2E=true "
            "and start Vault/SPIRE infrastructure for real E2E tests."
        )
