"""Testes unitários para MarkdownReportGenerator"""

from datetime import datetime

import pytest
from src.models import (
    DocumentStatus,
    DocumentType,
    Insight,
    InsightConfidence,
    LearningDocument,
)
from src.services.markdown_report_generator import MarkdownReportGenerator


@pytest.mark.asyncio()
async def test_generator_initialization(output_dir):
    """Testa inicialização do gerador"""
    with pytest.MonkeyPatch.context() as m:
        # Patch settings
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = MarkdownReportGenerator()
        await generator.initialize()

        assert generator._jinja_env is not None
        assert generator._output_dir == output_dir


@pytest.mark.asyncio()
async def test_generate_experiment_report(output_dir, mock_experiment_runs, mock_insights):
    """Testa geração de relatório de experimento"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = MarkdownReportGenerator()
        await generator.initialize()

        document = LearningDocument(
            title="Relatório de Experimentos",
            type=DocumentType.EXPERIMENT_REPORT,
            status=DocumentStatus.COMPLETED,
            generated_at=datetime.utcnow(),
            summary="Resumo executivo do relatório",
            insights=mock_insights,
            experiment_runs=mock_experiment_runs,
            recommendations=["Recomendação 1", "Recomendação 2"],
        )

        content = await generator.generate(document)

        assert isinstance(content, str)
        assert len(content) > 0
        assert "# Relatório de Experimentos" in content
        assert "Resumo executivo" in content


@pytest.mark.asyncio()
async def test_generate_weekly_summary(output_dir, mock_experiment_runs):
    """Testa geração de relatório semanal"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = MarkdownReportGenerator()
        await generator.initialize()

        document = LearningDocument(
            title="Relatório Semanal",
            type=DocumentType.WEEKLY_SUMMARY,
            status=DocumentStatus.COMPLETED,
            generated_at=datetime.utcnow(),
            period_start=datetime(2026, 1, 1),
            period_end=datetime(2026, 1, 7),
            summary="Resumo da semana",
            experiment_runs=mock_experiment_runs,
        )

        content = await generator.generate(document)

        assert "Relatório Semanal" in content
        assert "Semanal" in content


@pytest.mark.asyncio()
async def test_generate_promotion_report(output_dir, mock_experiment_runs):
    """Testa geração de relatório de promoção"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = MarkdownReportGenerator()
        await generator.initialize()

        document = LearningDocument(
            title="Relatório de Promoção",
            type=DocumentType.PROMOTION_REPORT,
            status=DocumentStatus.COMPLETED,
            generated_at=datetime.utcnow(),
            summary="Modelo pronto para produção",
            experiment_runs=mock_experiment_runs,
            metadata={"approved_by": "data_scientist", "approved_for_production": True},
        )

        content = await generator.generate(document)

        assert "Promoção de Modelo" in content
        assert "Aprovado para produção" in content


@pytest.mark.asyncio()
async def test_generate_rollback_analysis(output_dir):
    """Testa geração de análise de rollback"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = MarkdownReportGenerator()
        await generator.initialize()

        document = LearningDocument(
            title="Análise de Rollback",
            type=DocumentType.ROLLBACK_ANALYSIS,
            status=DocumentStatus.COMPLETED,
            generated_at=datetime.utcnow(),
            summary="Rollback devido à degradação de performance",
            metadata={"rollback_reason": "high_latency", "detected_by": "monitoring"},
        )

        content = await generator.generate(document)

        assert "Rollback" in content
        assert "Incidente" in content


@pytest.mark.asyncio()
async def test_save_to_file(output_dir, mock_experiment_runs):
    """Testa salvar conteúdo em arquivo"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = MarkdownReportGenerator()
        await generator.initialize()

        document = LearningDocument(
            title="Test Document",
            type=DocumentType.EXPERIMENT_REPORT,
            status=DocumentStatus.COMPLETED,
        )

        content = "# Test Document\n\nThis is a test."
        filepath = await generator.save_to_file(document, content)

        assert filepath is not None
        assert filepath.startswith(output_dir)

        # Verificar que arquivo foi criado
        import os

        assert os.path.exists(filepath)

        # Ler e verificar conteúdo
        with open(filepath) as f:
            saved_content = f.read()
        assert saved_content == content


def test_format_insight():
    """Testa formatação de insight"""
    generator = MarkdownReportGenerator()

    insight = Insight(
        title="Test Insight",
        description="Test description",
        evidence={"metric": 0.85},
        confidence=InsightConfidence.HIGH,
    )

    formatted = generator._format_insight(insight)

    assert "Test Insight" in formatted
    assert "Test description" in formatted
    assert "HIGH" in formatted


def test_format_metric():
    """Testa formatação de métrica"""
    generator = MarkdownReportGenerator()

    assert generator._format_metric(0.851234) == "0.8512"
    assert generator._format_metric(123.456) == "123.46"
    assert generator._format_metric(1.5) == "1.500"


def test_format_duration():
    """Testa formatação de duração"""
    generator = MarkdownReportGenerator()

    assert generator._format_duration(30) == "30.0s"
    assert generator._format_duration(90) == "1.5m"
    assert generator._format_duration(7200) == "2.0h"


def test_calculate_improvement():
    """Testa cálculo de melhoria"""
    generator = MarkdownReportGenerator()

    assert generator._calculate_improvement(0.9, 0.8) == 12.5
    assert generator._calculate_improvement(0.7, 0.8) == -12.5
    assert generator._calculate_improvement(0.8, 0.0) == 0.0
