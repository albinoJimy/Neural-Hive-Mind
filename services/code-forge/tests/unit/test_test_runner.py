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
        sample_pipeline_context
    ):
        """Deve executar testes com sucesso."""
        from services.code_forge.src.services.test_runner import TestRunner

        runner = TestRunner(min_coverage=0.8)

        await runner.run_tests(sample_pipeline_context)

        assert len(sample_pipeline_context.validation_results) == 1
        result = sample_pipeline_context.validation_results[0]
        assert result.status.value == 'PASSED'
        assert result.score == 0.95

    @pytest.mark.asyncio
    async def test_run_tests_adds_validation_result(
        self,
        sample_pipeline_context
    ):
        """Deve adicionar ValidationResult ao contexto."""
        from services.code_forge.src.services.test_runner import TestRunner
        from services.code_forge.src.models.artifact import ValidationType

        runner = TestRunner(min_coverage=0.8)

        await runner.run_tests(sample_pipeline_context)

        result = sample_pipeline_context.validation_results[0]
        assert result.validation_type == ValidationType.UNIT_TEST
        assert result.tool_name == 'pytest'
        assert result.tool_version == '7.4.0'


class TestTestRunnerCoverageThreshold:
    """Testes de threshold de cobertura."""

    @pytest.mark.asyncio
    async def test_default_min_coverage(
        self,
        sample_pipeline_context
    ):
        """Deve usar min_coverage padrao de 0.8."""
        from services.code_forge.src.services.test_runner import TestRunner

        runner = TestRunner()

        assert runner.min_coverage == 0.8

    @pytest.mark.asyncio
    async def test_custom_min_coverage(
        self,
        sample_pipeline_context
    ):
        """Deve aceitar min_coverage customizado."""
        from services.code_forge.src.services.test_runner import TestRunner

        runner = TestRunner(min_coverage=0.9)

        assert runner.min_coverage == 0.9


class TestTestRunnerValidationResult:
    """Testes de criacao de ValidationResult."""

    @pytest.mark.asyncio
    async def test_validation_result_no_issues(
        self,
        sample_pipeline_context
    ):
        """Deve criar resultado sem issues."""
        from services.code_forge.src.services.test_runner import TestRunner

        runner = TestRunner()

        await runner.run_tests(sample_pipeline_context)

        result = sample_pipeline_context.validation_results[0]
        assert result.issues_count == 0
        assert result.critical_issues == 0
        assert result.high_issues == 0
        assert result.medium_issues == 0
        assert result.low_issues == 0

    @pytest.mark.asyncio
    async def test_validation_result_has_duration(
        self,
        sample_pipeline_context
    ):
        """Deve incluir duracao na execucao."""
        from services.code_forge.src.services.test_runner import TestRunner

        runner = TestRunner()

        await runner.run_tests(sample_pipeline_context)

        result = sample_pipeline_context.validation_results[0]
        assert result.duration_ms == 5000

    @pytest.mark.asyncio
    async def test_validation_result_has_timestamp(
        self,
        sample_pipeline_context
    ):
        """Deve incluir timestamp de execucao."""
        from services.code_forge.src.services.test_runner import TestRunner

        runner = TestRunner()

        await runner.run_tests(sample_pipeline_context)

        result = sample_pipeline_context.validation_results[0]
        assert result.executed_at is not None
        assert isinstance(result.executed_at, datetime)
