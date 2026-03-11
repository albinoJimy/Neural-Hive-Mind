"""
Conftest para testes E2E do Code Forge.

Importa fixtures do conftest unitário para reutilização.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

# Adicionar caminho para fixtures do unit conftest
sys.path.insert(0, str(Path(__file__).parent.parent))

# Importar todas as fixtures do conftest unitário
from tests.unit.conftest import *


@pytest.fixture
def mock_test_runner():
    """TestRunner mockado que não executa subprocess reais."""
    from src.services.test_runner import TestRunner

    test_runner = TestRunner(mongodb_client=AsyncMock())

    # Mock do run_tests para evitar execução real de subprocess
    async def mock_run_tests(context):
        """Mock que simula testes passando sem executar subprocess"""
        from src.models.artifact import ValidationResult, ValidationType, ValidationStatus
        from datetime import datetime

        # Adicionar resultado de teste bem-sucedido
        test_result = ValidationResult(
            validation_type=ValidationType.UNIT_TEST,
            tool_name='pytest',
            tool_version='7.4.0',
            status=ValidationStatus.PASSED,
            score=0.90,
            issues_count=0,
            critical_issues=0,
            high_issues=0,
            medium_issues=0,
            low_issues=0,
            executed_at=datetime.now(),
            duration_ms=100
        )
        context.add_validation(test_result)

    # Aplicar o mock
    test_runner.run_tests = mock_run_tests
    return test_runner


# Re-exportar mock_test_runner
__all__ = ['mock_test_runner']
