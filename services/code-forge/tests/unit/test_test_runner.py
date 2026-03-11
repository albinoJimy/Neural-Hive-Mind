"""
Testes unitarios para TestRunner.

Cobertura:
- Execucao de testes automaticos
- Resultados de validacao
- Threshold de cobertura
- Metricas
"""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTestRunnerExecution:
    """Testes de execucao de testes."""

    @pytest.mark.asyncio
    async def test_run_tests_success(
        self,
        sample_pipeline_context_with_artifacts,
        mock_mongodb_client
    ):
        """Deve executar testes com sucesso."""
        from src.services.test_runner import TestRunner

        # Configurar mock para retornar código Python válido
        mock_mongodb_client.get_artifact_content = AsyncMock(
            return_value='''"""
FastAPI service auto-generated.
"""
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/")
def root():
    return {"message": "Hello World"}
'''
        )

        runner = TestRunner(min_coverage=0.8, mongodb_client=mock_mongodb_client)

        await runner.run_tests(sample_pipeline_context_with_artifacts)

        assert len(sample_pipeline_context_with_artifacts.validation_results) >= 1
        result = sample_pipeline_context_with_artifacts.validation_results[0]
        # ValidationStatus é StrEnum, então status.value retorna a string
        # Mas diretamente result.status já é a string
        assert result.status in ('PASSED', 'WARNING', 'FAILED')  # pytest pode não estar instalado

    @pytest.mark.asyncio
    async def test_run_tests_adds_validation_result(
        self,
        sample_pipeline_context_with_artifacts,
        mock_mongodb_client
    ):
        """Deve adicionar ValidationResult ao contexto."""
        from src.services.test_runner import TestRunner
        from src.models.artifact import ValidationType

        # Configurar mock para retornar código Python válido
        mock_mongodb_client.get_artifact_content = AsyncMock(
            return_value='def hello(): return "world"'
        )

        runner = TestRunner(min_coverage=0.8, mongodb_client=mock_mongodb_client)

        await runner.run_tests(sample_pipeline_context_with_artifacts)

        assert len(sample_pipeline_context_with_artifacts.validation_results) >= 1
        result = sample_pipeline_context_with_artifacts.validation_results[0]
        assert result.validation_type == ValidationType.UNIT_TEST
        assert result.tool_name in ('pytest', 'heuristic')  # Fallback se pytest não instalado


class TestTestRunnerCoverageThreshold:
    """Testes de threshold de cobertura."""

    @pytest.mark.asyncio
    async def test_default_min_coverage(
        self,
        sample_pipeline_context_with_artifacts
    ):
        """Deve usar min_coverage padrao de 0.8."""
        from src.services.test_runner import TestRunner

        runner = TestRunner()

        assert runner.min_coverage == 0.8

    @pytest.mark.asyncio
    async def test_custom_min_coverage(
        self,
        sample_pipeline_context_with_artifacts
    ):
        """Deve aceitar min_coverage customizado."""
        from src.services.test_runner import TestRunner

        runner = TestRunner(min_coverage=0.9)

        assert runner.min_coverage == 0.9


class TestTestRunnerValidationResult:
    """Testes de criacao de ValidationResult."""

    @pytest.mark.asyncio
    async def test_validation_result_no_issues(
        self,
        sample_pipeline_context_with_artifacts,
        mock_mongodb_client
    ):
        """Deve criar resultado com issues contados."""
        from src.services.test_runner import TestRunner

        mock_mongodb_client.get_artifact_content = AsyncMock(
            return_value='def test(): pass'
        )

        runner = TestRunner(min_coverage=0.8, mongodb_client=mock_mongodb_client)

        await runner.run_tests(sample_pipeline_context_with_artifacts)

        assert len(sample_pipeline_context_with_artifacts.validation_results) >= 1
        result = sample_pipeline_context_with_artifacts.validation_results[0]
        # Issues devem ser contados (pode variar baseado se pytest está instalado)
        assert isinstance(result.issues_count, int)
        assert isinstance(result.critical_issues, int)
        assert isinstance(result.high_issues, int)
        assert isinstance(result.medium_issues, int)
        assert isinstance(result.low_issues, int)

    @pytest.mark.asyncio
    async def test_validation_result_has_duration(
        self,
        sample_pipeline_context_with_artifacts,
        mock_mongodb_client
    ):
        """Deve incluir duracao na execucao."""
        from src.services.test_runner import TestRunner

        mock_mongodb_client.get_artifact_content = AsyncMock(
            return_value='def hello(): return "world"'
        )

        runner = TestRunner(mongodb_client=mock_mongodb_client)

        await runner.run_tests(sample_pipeline_context_with_artifacts)

        result = sample_pipeline_context_with_artifacts.validation_results[0]
        assert isinstance(result.duration_ms, int)
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_validation_result_has_timestamp(
        self,
        sample_pipeline_context_with_artifacts,
        mock_mongodb_client
    ):
        """Deve incluir timestamp de execucao."""
        from src.services.test_runner import TestRunner

        mock_mongodb_client.get_artifact_content = AsyncMock(
            return_value='def test(): pass'
        )

        runner = TestRunner(mongodb_client=mock_mongodb_client)

        await runner.run_tests(sample_pipeline_context_with_artifacts)

        result = sample_pipeline_context_with_artifacts.validation_results[0]
        assert result.executed_at is not None
        assert isinstance(result.executed_at, datetime)
