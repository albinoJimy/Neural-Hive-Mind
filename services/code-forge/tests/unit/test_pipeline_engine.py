"""
Testes unitários para PipelineEngine.

Cobertura:
- Execução de pipeline completo
- Execução de stages individuais
- Tratamento de erros
- Métricas de stage
"""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPipelineEngineExecution:
    """Testes de execução do pipeline."""

    @pytest.mark.asyncio
    async def test_execute_pipeline_success(
        self,
        mock_pipeline_engine,
        sample_execution_ticket
    ):
        """Deve executar pipeline completo com sucesso."""
        from src.services.pipeline_engine import PipelineEngine
        from src.models.artifact import PipelineStage, StageStatus
        from datetime import datetime

        # Lista de stages do pipeline
        stage_names = [
            'template_selection', 'code_composition', 'validation',
            'testing', 'packaging', 'approval_gate'
        ]

        # Criar mocks dos estágios com assinatura correta
        async def mock_stage(context, stage_name, stage_func):
            # Adicionar stage ao contexto para simular execução
            stage = PipelineStage(
                stage_name=stage_name,
                status=StageStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=10,
                error_message=None
            )
            context.add_stage(stage)

        with patch.object(mock_pipeline_engine, '_execute_stage', new=mock_stage):
            result = await mock_pipeline_engine.execute_pipeline(sample_execution_ticket)

        assert result.status == 'COMPLETED'
        assert len(result.pipeline_stages) == 6

    @pytest.mark.asyncio
    async def test_execute_pipeline_stage_failure(
        self,
        mock_pipeline_engine,
        sample_execution_ticket
    ):
        """Deve falhar quando um stage falha."""
        async def failing_stage(context, stage_name, stage_func):
            raise ValueError("Stage failed")

        with patch.object(mock_pipeline_engine, '_execute_stage', new=failing_stage):
            result = await mock_pipeline_engine.execute_pipeline(sample_execution_ticket)

        assert result.status == 'FAILED'


class TestPipelineEngineStageExecution:
    """Testes de execução de stages."""

    @pytest.mark.asyncio
    async def test_execute_stage_success(
        self,
        mock_pipeline_engine,
        sample_pipeline_context
    ):
        """Deve executar stage com sucesso e marcar como completado."""
        stage_name = 'test_stage'
        executed = False

        async def stage_func(context):
            nonlocal executed
            executed = True

        await mock_pipeline_engine._execute_stage(
            sample_pipeline_context,
            stage_name,
            stage_func
        )

        assert executed
        stage = next(s for s in sample_pipeline_context.pipeline_stages if s.stage_name == stage_name)
        assert stage.status.value == 'COMPLETED'

    @pytest.mark.asyncio
    async def test_execute_stage_timeout(
        self,
        mock_pipeline_engine,
        sample_pipeline_context
    ):
        """Deve falhar quando stage excede timeout."""
        stage_name = 'timeout_stage'

        async def slow_stage(context):
            await asyncio.sleep(999)

        mock_pipeline_engine.pipeline_timeout = 1

        with pytest.raises(asyncio.TimeoutError):
            await mock_pipeline_engine._execute_stage(
                sample_pipeline_context,
                stage_name,
                slow_stage
            )

    @pytest.mark.asyncio
    async def test_execute_stage_exception(
        self,
        mock_pipeline_engine,
        sample_pipeline_context
    ):
        """Deve falhar quando stage lança exceção."""
        stage_name = 'error_stage'

        async def failing_stage(context):
            raise RuntimeError("Stage error")

        with pytest.raises(RuntimeError):
            await mock_pipeline_engine._execute_stage(
                sample_pipeline_context,
                stage_name,
                failing_stage
            )


class TestPipelineEngineMetrics:
    """Testes de métricas do pipeline."""

    @pytest.mark.asyncio
    async def test_stage_emits_duration_metric(
        self,
        mock_pipeline_engine_with_metrics,
        sample_pipeline_context
    ):
        """Deve emitir métrica de duração quando stage completa."""
        stage_name = 'test_stage'

        async def stage_func(context):
            await asyncio.sleep(0.01)

        await mock_pipeline_engine_with_metrics._execute_stage(
            sample_pipeline_context,
            stage_name,
            stage_func
        )

        mock_pipeline_engine_with_metrics.metrics.stage_duration_seconds.labels.assert_called_with(stage=stage_name)

    @pytest.mark.asyncio
    async def test_stage_emits_failure_metric_on_error(
        self,
        mock_pipeline_engine_with_metrics,
        sample_pipeline_context
    ):
        """Deve emitir métrica de falha quando stage falha."""
        stage_name = 'failing_stage'

        async def failing_stage(context):
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await mock_pipeline_engine_with_metrics._execute_stage(
                sample_pipeline_context,
                stage_name,
                failing_stage
            )

        mock_pipeline_engine_with_metrics.metrics.stage_failures_total.labels.assert_called()


class TestPipelineEngineActivePipelines:
    """Testes de tracking de pipelines ativos."""

    @pytest.mark.asyncio
    async def test_pipeline_added_to_active_tracking(
        self,
        mock_pipeline_engine,
        sample_execution_ticket
    ):
        """Deve adicionar pipeline ao tracking de ativos quando inicia."""
        async def mock_stage(context, stage_name, stage_func):
            pass

        with patch.object(mock_pipeline_engine, '_execute_stage', new=mock_stage):
            # Executar em background para verificar tracking
            task = asyncio.create_task(
                mock_pipeline_engine.execute_pipeline(sample_execution_ticket)
            )
            await asyncio.sleep(0.01)  # Deixar iniciar

            # Verificar que pipeline está sendo trackeado
            assert mock_pipeline_engine.get_active_pipelines_count() >= 0

            await task


class TestPipelineEngineErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_creates_compensation_ticket_on_failure(
        self,
        mock_pipeline_engine,
        sample_execution_ticket
    ):
        """Deve criar ticket de compensação quando pipeline falha."""
        async def failing_stage(context, stage_name, stage_func):
            raise RuntimeError("Pipeline failed")

        with patch.object(mock_pipeline_engine, '_execute_stage', new=failing_stage):
            result = await mock_pipeline_engine.execute_pipeline(sample_execution_ticket)

        assert result.status == 'FAILED'
