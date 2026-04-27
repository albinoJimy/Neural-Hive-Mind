"""Testes unitários para DocumentScheduler"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.models import DocumentType, InsightConfidence
from src.scheduler.document_scheduler import DocumentScheduler


@pytest.fixture()
def mock_repository():
    """Mock do DocumentRepository"""
    repo = AsyncMock()
    repo.save = AsyncMock(return_value="test_doc_id")
    return repo


@pytest.fixture()
def mock_insight_extractor():
    """Mock do ExperimentInsightExtractor"""
    extractor = AsyncMock()
    extractor.get_runs_by_period = AsyncMock(return_value=[])
    extractor.extract_insights_from_runs = AsyncMock(return_value=[])
    return extractor


@pytest.fixture()
def mock_report_generator():
    """Mock do MarkdownReportGenerator"""
    generator = AsyncMock()
    generator.initialize = AsyncMock()
    return generator


@pytest.fixture()
def scheduler(mock_repository, mock_insight_extractor, mock_report_generator):
    """Fixture do DocumentScheduler"""
    return DocumentScheduler(
        repository=mock_repository,
        insight_extractor=mock_insight_extractor,
        report_generator=mock_report_generator,
    )


class TestDocumentScheduler:
    """Testes para DocumentScheduler"""

    @pytest.mark.asyncio()
    async def test_start_scheduler(self, scheduler):
        """Testa inicialização do scheduler"""
        await scheduler.start()

        assert scheduler.is_running()
        assert scheduler.scheduler is not None
        assert scheduler.scheduler.running

        await scheduler.stop()

    @pytest.mark.asyncio()
    async def test_start_scheduler_disabled(self, scheduler):
        """Testa que scheduler não inicia quando desabilitado"""
        with patch("src.scheduler.document_scheduler.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(scheduler_enabled=False)

            scheduler_disabled = DocumentScheduler(
                repository=scheduler.repository,
                insight_extractor=scheduler.insight_extractor,
                report_generator=scheduler.report_generator,
            )

            await scheduler_disabled.start()

            assert not scheduler_disabled.is_running()

    @pytest.mark.asyncio()
    async def test_generate_daily_report_no_experiments(self, scheduler):
        """Testa geração de relatório diário sem experimentos"""
        await scheduler._generate_daily_report()

        # Não deve chamar save se não há experimentos
        scheduler.repository.save.assert_not_called()

    @pytest.mark.asyncio()
    async def test_generate_daily_report_with_experiments(
        self, scheduler, mock_insight_extractor, mock_repository
    ):
        """Testa geração de relatório diário com experimentos"""
        from src.models import ExperimentRun, Insight

        # Mock experiment runs
        mock_run = ExperimentRun(
            run_id="test_run_id",
            experiment_id=1,
            name="test_experiment",
            status="FINISHED",
            start_time=datetime.now(timezone.utc) - timedelta(days=1),
            end_time=datetime.now(timezone.utc) - timedelta(days=1),
            metrics={"accuracy": 0.85},
            params={"lr": "0.001"},
            tags={},
        )
        mock_insight_extractor.get_runs_by_period = AsyncMock(return_value=[mock_run])

        # Mock insights
        mock_insight = Insight(
            title="Test Insight",
            description="Test description",
            evidence={"accuracy": 0.85},
            confidence=InsightConfidence.HIGH,
            experiment_ids=["test_run_id"],
            category="performance",
        )
        mock_insight_extractor.extract_insights_from_runs = AsyncMock(return_value=[mock_insight])

        await scheduler._generate_daily_report()

        # Deve salvar o documento
        mock_repository.save.assert_called_once()
        call_args = mock_repository.save.call_args[0][0]
        assert call_args.type == DocumentType.DAILY_SUMMARY
        assert "Relatório de Aprendizado Diário" in call_args.title

    @pytest.mark.asyncio()
    async def test_generate_weekly_report(self, scheduler):
        """Testa geração de relatório semanal"""
        await scheduler._generate_weekly_report()

        # Sem experimentos mockados, não deve salvar
        scheduler.repository.save.assert_not_called()

    @pytest.mark.asyncio()
    async def test_generate_monthly_report(self, scheduler):
        """Testa geração de relatório mensal"""
        await scheduler._generate_monthly_report()

        # Sem experimentos mockados, não deve salvar
        scheduler.repository.save.assert_not_called()

    @pytest.mark.asyncio()
    async def test_trigger_manual_report(self, scheduler, mock_insight_extractor, mock_repository):
        """Testa trigger manual de relatório"""
        from src.models import ExperimentRun

        # Mock experiment runs
        mock_run = ExperimentRun(
            run_id="test_run_id",
            experiment_id=1,
            name="test_experiment",
            status="FINISHED",
            start_time=datetime.now(timezone.utc) - timedelta(days=1),
            end_time=datetime.now(timezone.utc),
            metrics={"accuracy": 0.85},
            params={},
            tags={},
        )
        mock_insight_extractor.get_runs_by_period = AsyncMock(return_value=[mock_run])
        mock_insight_extractor.extract_insights_from_runs = AsyncMock(return_value=[])

        period_start = datetime.now(timezone.utc) - timedelta(days=1)
        period_end = datetime.now(timezone.utc)

        doc_id = await scheduler.trigger_manual_report(
            DocumentType.WEEKLY_SUMMARY, period_start, period_end
        )

        assert doc_id == "test_doc_id"
        mock_repository.save.assert_called_once()

    @pytest.mark.asyncio()
    async def test_trigger_manual_report_no_experiments(self, scheduler, mock_insight_extractor):
        """Testa trigger manual sem experimentos"""
        mock_insight_extractor.get_runs_by_period = AsyncMock(return_value=[])

        period_start = datetime.now(timezone.utc) - timedelta(days=1)
        period_end = datetime.now(timezone.utc)

        doc_id = await scheduler.trigger_manual_report(
            DocumentType.DAILY_SUMMARY, period_start, period_end
        )

        assert doc_id is None

    def test_generate_period_summary(self, scheduler):
        """Testa geração de resumo do período"""
        from src.models import ExperimentRun, Insight

        mock_runs = [
            ExperimentRun(
                run_id="r1",
                experiment_id=1,
                name="exp1",
                status="FINISHED",
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                metrics={},
                params={},
                tags={},
            ),
            ExperimentRun(
                run_id="r2",
                experiment_id=1,
                name="exp2",
                status="FAILED",
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                metrics={},
                params={},
                tags={},
            ),
        ]

        mock_insights = [
            Insight(
                title="High Confidence Insight",
                description="Test",
                evidence={},
                confidence=InsightConfidence.HIGH,
                experiment_ids=["r1"],
                category="performance",
            )
        ]

        summary = scheduler._generate_period_summary(mock_runs, mock_insights, "diário")

        assert "diário" in summary
        assert "2 experimentos" in summary
        assert "1 de alta confiança" in summary

    def test_generate_recommendations(self, scheduler):
        """Testa geração de recomendações"""
        from src.models import Insight

        insights = [
            Insight(
                title="Performance Insight",
                description="Test",
                evidence={},
                confidence=InsightConfidence.HIGH,
                experiment_ids=[],
                category="performance",
            ),
            Insight(
                title="Improvement Insight",
                description="Test",
                evidence={},
                confidence=InsightConfidence.HIGH,
                experiment_ids=[],
                category="improvement",
            ),
        ]

        recommendations = scheduler._generate_recommendations(insights)

        assert len(recommendations) > 0
        assert any("performance" in r.lower() for r in recommendations)
        assert any("promover" in r.lower() for r in recommendations)

    @pytest.mark.asyncio()
    async def test_get_next_run_times(self, scheduler):
        """Testa obtenção dos próximos horários de execução"""
        await scheduler.start()

        next_runs = scheduler.get_next_run_times()

        assert isinstance(next_runs, dict)
        assert "daily_report" in next_runs
        assert "weekly_report" in next_runs
        assert "monthly_report" in next_runs

        await scheduler.stop()

    @pytest.mark.asyncio()
    async def test_stop_scheduler(self, scheduler):
        """Testa parada do scheduler"""
        await scheduler.start()
        assert scheduler.is_running()

        await scheduler.stop()
        assert not scheduler.is_running()
