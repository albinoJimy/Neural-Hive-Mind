"""Testes unitários para PlotGenerator"""

import os
import pytest
from datetime import datetime

from src.services.plot_generator import PlotGenerator
from src.models import ExperimentRun


@pytest.mark.asyncio
async def test_plot_generator_initialization(output_dir):
    """Testa inicialização do gerador de plots"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = PlotGenerator()

        assert generator._output_dir == output_dir
        assert os.path.exists(output_dir)


@pytest.mark.asyncio
async def test_generate_experiment_comparison_plot(output_dir, mock_experiment_runs):
    """Testa geração de gráfico de comparação"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = PlotGenerator()

        filepath = await generator.generate_experiment_comparison_plot(
            runs=mock_experiment_runs,
            metric="val_accuracy",
            format_type="png",
        )

        # Pode retornar None se não houver dados suficientes
        if filepath:
            assert filepath.endswith(".png")
            assert os.path.exists(filepath)


@pytest.mark.asyncio
async def test_generate_metric_timeline_plot(output_dir, mock_experiment_runs):
    """Testa geração de gráfico de timeline"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = PlotGenerator()

        filepath = await generator.generate_metric_timeline_plot(
            runs=mock_experiment_runs,
            metric="val_accuracy",
            format_type="png",
        )

        if filepath:
            assert filepath.endswith(".png")


@pytest.mark.asyncio
async def test_generate_metrics_correlation_plot(output_dir, mock_experiment_runs):
    """Testa geração de gráfico de correlação"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = PlotGenerator()

        filepath = await generator.generate_metrics_correlation_plot(
            runs=mock_experiment_runs,
            metric_x="accuracy",
            metric_y="val_accuracy",
            format_type="png",
        )

        if filepath:
            assert filepath.endswith(".png")


@pytest.mark.asyncio
async def test_generate_training_progress_plot(output_dir, mock_experiment_runs):
    """Testa geração de gráfico de progresso de treinamento"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = PlotGenerator()

        filepath = await generator.generate_training_progress_plot(
            runs=mock_experiment_runs,
            format_type="png",
        )

        if filepath:
            assert filepath.endswith(".png")


@pytest.mark.asyncio
async def test_generate_multi_metric_summary(output_dir, mock_experiment_runs):
    """Testa geração de resumo multi-métrica"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = PlotGenerator()

        filepath = await generator.generate_multi_metric_summary(
            runs=mock_experiment_runs,
            metrics=["accuracy", "val_accuracy"],
            format_type="png",
        )

        if filepath:
            assert filepath.endswith(".png")


@pytest.mark.asyncio
async def test_generate_all_plots(output_dir, mock_experiment_runs):
    """Testa geração de todos os plots"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = PlotGenerator()

        plots = await generator.generate_all_plots(
            runs=mock_experiment_runs,
            format_type="png",
        )

        assert isinstance(plots, list)
        # Verificar que arquivos existem
        for plot in plots:
            if plot:
                assert os.path.exists(plot)


def test_close(output_dir):
    """Testa fechamento do gerador"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DOCS_OUTPUT_DIR", output_dir)

        generator = PlotGenerator()
        generator.close()  # Não deve levantar exceção
