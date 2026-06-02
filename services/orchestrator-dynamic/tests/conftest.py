"""
Conftest global para testes do orchestrator-dynamic.

Configura sys.path para permitir imports do src e das bibliotecas neural_hive.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Configurar sys.path para imports
# =============================================================================

# Adicionar libraries/python/neural_hive_* ao sys.path
# Cada pacote neural_hive precisa estar no path individualmente
libs_base = Path(__file__).parent.parent.parent.parent / "libraries" / "python"

# Para cada biblioteca neural_hive, adicionar o diretório que contém o __init__.py
for pkg_dir in libs_base.glob("neural_hive_*"):
    if pkg_dir.is_dir():
        # Verificar se o __init__.py está no subdiretório com o mesmo nome
        subdir = pkg_dir / pkg_dir.name
        if subdir.is_dir() and (subdir / "__init__.py").exists():
            # Estrutura: neural_hive_xxx/neural_hive_xxx/__init__.py
            if str(pkg_dir) not in sys.path:
                sys.path.insert(0, str(pkg_dir))
        elif (pkg_dir / "__init__.py").exists():
            # Estrutura: neural_hive_xxx/__init__.py
            if str(pkg_dir.parent) not in sys.path:
                sys.path.insert(0, str(pkg_dir.parent))

# Também adicionar libs/ se existir
libs_alt = Path(__file__).parent.parent.parent.parent / "libs"
if libs_alt.is_dir():
    for pkg_dir in libs_alt.glob("neural_hive_*"):
        if pkg_dir.is_dir() and str(pkg_dir) not in sys.path:
            sys.path.insert(0, str(pkg_dir))

# Adicionar neural_hive_integration (está fora de libraries/python)
integration_lib = (
    Path(__file__).parent.parent.parent.parent / "libraries" / "neural_hive_integration"
)
if integration_lib.is_dir() and str(integration_lib) not in sys.path:
    sys.path.insert(0, str(integration_lib))

# Adicionar src ao path
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)


def pytest_configure(config):
    """Hook para configurar pytest antes da coleta de testes."""
    # Mock get_metrics ANTES de qualquer import de src.main
    mock_metrics = MagicMock()
    mock_metrics.trace_context_extraction_total = MagicMock()
    mock_metrics.trace_context_extraction_total.labels = MagicMock(
        return_value=mock_metrics.trace_context_extraction_total
    )
    mock_metrics.trace_context_extraction_total.inc = MagicMock()
    mock_metrics.trace_context_extraction_success_total = MagicMock()
    mock_metrics.trace_context_extraction_success_total.labels = MagicMock(
        return_value=mock_metrics.trace_context_extraction_success_total
    )
    mock_metrics.trace_context_extraction_success_total.inc = MagicMock()
    mock_metrics.trace_context_extraction_failure_total = MagicMock()
    mock_metrics.trace_context_extraction_failure_total.labels = MagicMock(
        return_value=mock_metrics.trace_context_extraction_failure_total
    )
    mock_metrics.trace_context_extraction_failure_total.inc = MagicMock()
    mock_metrics.trace_parent_missing_total = MagicMock()
    mock_metrics.trace_parent_missing_total.labels = MagicMock(
        return_value=mock_metrics.trace_parent_missing_total
    )
    mock_metrics.trace_parent_missing_total.inc = MagicMock()
    mock_metrics.config = MagicMock()
    mock_metrics.config.common_labels = {}

    # Patch get_metrics no nível do módulo neural_hive_observability
    import neural_hive_observability as obs

    obs._metrics = mock_metrics  # Sobrescrever a property com o mock real

    # Também patchar a função get_metrics
    with patch.object(obs, "get_metrics", return_value=mock_metrics):
        pass  # O patch persiste porque modificamos o módulo diretamente


@pytest.fixture(autouse=True)
def mock_settings_global():
    """Mock global das configurações para todos os testes."""
    from src.config.settings import OrchestratorSettings

    with patch("src.config.get_settings") as mock_get_settings:
        mock_config = OrchestratorSettings(
            # Campos obrigatórios
            kafka_bootstrap_servers="localhost:9092",
            postgres_host="localhost",
            postgres_user="test",
            postgres_password="test",
            mongodb_uri="mongodb://localhost:27017",
            redis_cluster_nodes="localhost:6379",
            # Configurações de teste
            temporal_workflow_id_prefix="nhm-",
            temporal_task_queue="orchestration-tasks",
            # OPA desabilitado para testes (evita erros de campos faltantes)
            enable_opa_authorization=False,
            opa_enabled=False,
        )
        mock_get_settings.return_value = mock_config
        yield mock_config
