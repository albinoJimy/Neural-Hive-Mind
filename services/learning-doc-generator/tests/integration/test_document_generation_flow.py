"""Testes de integração para fluxo de geração de documentos"""

import os
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.services import (
    DocumentRepository,
    ExperimentInsightExtractor,
    MarkdownReportGenerator,
    PlotGenerator,
)
from src.models import DocumentFormat, DocumentStatus, DocumentType, LearningDocument


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_document_generation_flow(mock_experiment_runs, output_dir):
    """Testa fluxo completo de geração de documento"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("MONGODB_URI", "mongodb://localhost:27017")
        m.setenv("MONGODB_DATABASE", "test_db")
        m.setenv("MONGODB_COLLECTION", "test_docs")
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        # Inicializar componentes
        repo = DocumentRepository()
        repo._collection = AsyncMock()

        # Mock insert_one
        mock_result = MagicMock()
        mock_result.inserted_id = "doc_test_001"
        repo._collection.insert_one = AsyncMock(return_value=mock_result)
        repo._collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        extractor = ExperimentInsightExtractor()
        extractor._mlflow_client = MagicMock()

        # Mock fetch
        extractor.fetch_experiment_runs = AsyncMock(return_value=mock_experiment_runs)

        generator = MarkdownReportGenerator()
        await generator.initialize()

        plot_gen = PlotGenerator()
        plot_gen.generate_all_plots = AsyncMock(return_value=[])

        # Criar documento inicial
        document = LearningDocument(
            title="Test Integration Document",
            type=DocumentType.EXPERIMENT_REPORT,
            status=DocumentStatus.PENDING,
            period_start=datetime(2026, 1, 1),
            period_end=datetime(2026, 1, 7),
        )

        # Salvar
        doc_id = await repo.save(document)
        assert doc_id is not None

        # Buscar runs
        runs = await extractor.fetch_experiment_runs(max_runs=100)
        assert len(runs) > 0

        # Extrair insights
        insights = await extractor.extract_insights(runs)
        assert len(insights) > 0

        # Gerar resumo
        summary = await extractor.generate_summary(runs)
        assert len(summary) > 0

        # Gerar recomendações
        recommendations = await extractor.generate_recommendations(insights, runs)
        assert len(recommendations) >= 0

        # Gerar plots
        plots = await plot_gen.generate_all_plots(runs)
        assert isinstance(plots, list)

        # Atualizar documento
        document.experiment_runs = runs
        document.insights = insights
        document.summary = summary
        document.recommendations = recommendations
        document.plots = plots
        document.generated_at = datetime.utcnow()

        # Gerar Markdown
        markdown_content = await generator.generate(document)
        assert len(markdown_content) > 0
        assert "# Test Integration Document" in markdown_content

        # Salvar arquivo
        filepath = await generator.save_to_file(document, markdown_content)
        assert filepath is not None
        assert os.path.exists(filepath)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_weekly_report_generation(mock_experiment_runs, output_dir):
    """Testa geração de relatório semanal"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = MarkdownReportGenerator()
        await generator.initialize()

        extractor = ExperimentInsightExtractor()
        insights = await extractor.extract_insights(mock_experiment_runs)
        summary = await extractor.generate_summary(mock_experiment_runs)
        recommendations = await extractor.generate_recommendations(
            insights, mock_experiment_runs
        )

        document = LearningDocument(
            title="Relatório Semanal - 2026-01-01",
            type=DocumentType.WEEKLY_SUMMARY,
            status=DocumentStatus.COMPLETED,
            generated_at=datetime.utcnow(),
            period_start=datetime(2026, 1, 1),
            period_end=datetime(2026, 1, 7),
            summary=summary,
            insights=insights,
            experiment_runs=mock_experiment_runs,
            recommendations=recommendations,
        )

        content = await generator.generate(document)

        assert "Semanal" in content
        assert "2026-01-01" in content or "2026-01-07" in content
        assert summary in content


@pytest.mark.asyncio
@pytest.mark.integration
async def test_promotion_report_generation(mock_experiment_runs, output_dir):
    """Testa geração de relatório de promoção"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = MarkdownReportGenerator()
        await generator.initialize()

        # Selecionar melhor run
        best_run = max(
            [r for r in mock_experiment_runs if r.status == "FINISHED"],
            key=lambda r: r.metrics.get("val_accuracy", 0),
        )

        document = LearningDocument(
            title=f"Promoção - {best_run.name}",
            type=DocumentType.PROMOTION_REPORT,
            status=DocumentStatus.COMPLETED,
            generated_at=datetime.utcnow(),
            summary=f"Modelo {best_run.name} pronto para produção",
            experiment_runs=[best_run],
            metadata={
                "approved_by": "data_scientist",
                "approved_for_production": True,
                "approval_date": datetime.utcnow().isoformat(),
            },
        )

        content = await generator.generate(document)

        assert "Promoção de Modelo" in content
        assert best_run.name in content


@pytest.mark.asyncio
@pytest.mark.integration
async def test_repository_lifecycle(output_dir):
    """Testa ciclo de vida do repositório"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("MONGODB_URI", "mongodb://localhost:27017")
        m.setenv("MONGODB_DATABASE", "test_db")
        m.setenv("MONGODB_COLLECTION", "test_docs")

        repo = DocumentRepository()
        repo._collection = AsyncMock()

        # Insert
        mock_insert = MagicMock()
        mock_insert.inserted_id = "doc_lifecycle_001"
        repo._collection.insert_one = AsyncMock(return_value=mock_insert)

        # Update
        mock_update = MagicMock()
        mock_update.modified_count = 1
        repo._collection.update_one = AsyncMock(return_value=mock_update)

        # Find
        doc_dict = {
            "_id": "doc_lifecycle_001",
            "title": "Lifecycle Test",
            "type": "experiment_report",
            "status": "pending",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        repo._collection.find_one = AsyncMock(return_value=doc_dict)

        # Criar
        document = LearningDocument(
            title="Lifecycle Test",
            type=DocumentType.EXPERIMENT_REPORT,
            status=DocumentStatus.PENDING,
        )
        doc_id = await repo.save(document)
        assert doc_id == "doc_lifecycle_001"

        # Buscar
        found = await repo.get_by_id(doc_id)
        assert found is not None
        assert found.title == "Lifecycle Test"

        # Atualizar
        found.status = DocumentStatus.COMPLETED
        success = await repo.update(doc_id, found)
        assert success is True

        # Atualizar status
        success = await repo.update_status(doc_id, DocumentStatus.COMPLETED)
        assert success is True
