"""Gerador de gráficos para relatórios de aprendizado"""

import os
from datetime import datetime
from typing import Optional

import matplotlib.pyplot as plt
import structlog
from src.config import get_settings
from src.models import ExperimentRun

logger = structlog.get_logger()


class PlotGenerator:
    """Gera gráficos para inclusão em relatórios"""

    def __init__(self):
        """Inicializa o gerador"""
        self.settings = get_settings()
        self._output_dir = self.settings.docs_output_dir

        # Criar diretório de saída
        os.makedirs(self._output_dir, exist_ok=True)

        # Configurar matplotlib
        plt.style.use("seaborn-v0_8-darkgrid")

    async def generate_experiment_comparison_plot(
        self,
        runs: list[ExperimentRun],
        metric: str = "val_accuracy",
        format_type: str = "png",
    ) -> Optional[str]:
        """Gera gráfico de comparação entre experimentos

        Args:
            runs: Lista de experiment runs
            metric: Métrica para comparar
            format_type: Formato de saída (png/svg/html)

        Returns:
            Caminho do arquivo gerado ou None
        """
        try:
            # Filtrar runs que têm a métrica
            valid_runs = [r for r in runs if metric in r.metrics]

            if len(valid_runs) < 2:
                logger.warning(
                    "Poucos runs com métrica para gráfico",
                    metric=metric,
                    count=len(valid_runs),
                )
                return None

            # Ordenar por valor da métrica
            sorted_runs = sorted(valid_runs, key=lambda r: r.metrics[metric], reverse=True)

            # Criar figura
            fig, ax = plt.subplots(figsize=(12, 6))

            names = [r.name[:20] for r in sorted_runs]
            values = [r.metrics[metric] for r in sorted_runs]

            # Cores baseadas em status
            colors = ["#2ecc71" if r.status == "FINISHED" else "#e74c3c" for r in sorted_runs]

            bars = ax.barh(names, values, color=colors)
            ax.set_xlabel(metric.replace("_", " ").title())
            ax.set_ylabel("Experimento")
            ax.set_title(f"Comparação de {metric.replace('_', ' ')} por Experimento")
            ax.set_xlim(0, max(values) * 1.1)

            # Adicionar valores nas barras
            for bar, value in zip(bars, values):
                width = bar.get_width()
                ax.text(
                    width + 0.001,
                    bar.get_y() + bar.get_height() / 2,
                    f"{value:.4f}",
                    ha="left",
                    va="center",
                    fontsize=9,
                )

            plt.tight_layout()

            # Salvar
            filepath = await self._save_plot(fig, f"comparison_{metric}", format_type)
            plt.close(fig)

            return filepath

        except Exception as e:
            logger.error("Erro ao gerar gráfico de comparação", error=str(e), exc_info=True)
            return None

    async def generate_metric_timeline_plot(
        self,
        runs: list[ExperimentRun],
        metric: str = "val_accuracy",
        format_type: str = "png",
    ) -> Optional[str]:
        """Gera gráfico de linha mostrando evolução temporal

        Args:
            runs: Lista de experiment runs
            metric: Métrica para plotar
            format_type: Formato de saída

        Returns:
            Caminho do arquivo gerado ou None
        """
        try:
            # Filtrar runs com data e métrica
            valid_runs = [
                r for r in runs if r.start_time and metric in r.metrics and r.status == "FINISHED"
            ]

            if len(valid_runs) < 2:
                return None

            # Ordenar por data
            sorted_runs = sorted(valid_runs, key=lambda r: r.start_time)

            # Criar figura
            fig, ax = plt.subplots(figsize=(12, 6))

            dates = [r.start_time for r in sorted_runs]
            values = [r.metrics[metric] for r in sorted_runs]

            ax.plot(dates, values, marker="o", linewidth=2, markersize=6)
            ax.fill_between(dates, values, alpha=0.3)

            ax.set_xlabel("Data")
            ax.set_ylabel(metric.replace("_", " ").title())
            ax.set_title(f"Evolução de {metric.replace('_', ' ')} ao Longo do Tempo")
            ax.grid(True, alpha=0.3)

            # Formatar datas
            fig.autofmt_xdate()

            plt.tight_layout()

            # Salvar
            filepath = await self._save_plot(fig, f"timeline_{metric}", format_type)
            plt.close(fig)

            return filepath

        except Exception as e:
            logger.error("Erro ao gerar gráfico de timeline", error=str(e), exc_info=True)
            return None

    async def generate_metrics_correlation_plot(
        self,
        runs: list[ExperimentRun],
        metric_x: str = "accuracy",
        metric_y: str = "val_accuracy",
        format_type: str = "png",
    ) -> Optional[str]:
        """Gera gráfico de dispersão mostrando correlação entre métricas

        Args:
            runs: Lista de experiment runs
            metric_x: Métrica para eixo X
            metric_y: Métrica para eixo Y
            format_type: Formato de saída

        Returns:
            Caminho do arquivo gerado ou None
        """
        try:
            # Filtrar runs com ambas as métricas
            valid_runs = [r for r in runs if metric_x in r.metrics and metric_y in r.metrics]

            if len(valid_runs) < 3:
                return None

            # Criar figura
            fig, ax = plt.subplots(figsize=(10, 8))

            x_values = [r.metrics[metric_x] for r in valid_runs]
            y_values = [r.metrics[metric_y] for r in valid_runs]

            # Scatter plot
            scatter = ax.scatter(
                x_values,
                y_values,
                c=[i for i in range(len(valid_runs))],
                cmap="viridis",
                s=100,
                alpha=0.7,
                edgecolors="black",
                linewidth=0.5,
            )

            # Linha de referência (y=x)
            min_val = min(min(x_values), min(y_values))
            max_val = max(max(x_values), max(y_values))
            ax.plot([min_val, max_val], [min_val, max_val], "r--", alpha=0.5, label="y=x")

            ax.set_xlabel(metric_x.replace("_", " ").title())
            ax.set_ylabel(metric_y.replace("_", " ").Title())
            ax.set_title(f"Correlação: {metric_x} vs {metric_y}")
            ax.grid(True, alpha=0.3)
            ax.legend()

            plt.tight_layout()

            # Salvar
            filepath = await self._save_plot(fig, f"correlation_{metric_x}_{metric_y}", format_type)
            plt.close(fig)

            return filepath

        except Exception as e:
            logger.error("Erro ao gerar gráfico de correlação", error=str(e), exc_info=True)
            return None

    async def generate_training_progress_plot(
        self,
        runs: list[ExperimentRun],
        format_type: str = "png",
    ) -> Optional[str]:
        """Gera gráfico mostrando progresso de treinamento

        Args:
            runs: Lista de experiment runs
            format_type: Formato de saída

        Returns:
            Caminho do arquivo gerado ou None
        """
        try:
            # Buscar runs com métricas de treino/validação
            valid_runs = [
                r for r in runs if "training_loss" in r.metrics or "val_loss" in r.metrics
            ]

            if not valid_runs:
                return None

            # Criar figura
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

            # Loss plot
            if any("training_loss" in r.metrics for r in valid_runs):
                sorted_runs = sorted(valid_runs, key=lambda r: r.start_time or datetime.min)
                x = list(range(len(sorted_runs)))
                train_losses = [r.metrics.get("training_loss", float("nan")) for r in sorted_runs]
                val_losses = [r.metrics.get("val_loss", float("nan")) for r in sorted_runs]

                ax1.plot(x, train_losses, marker="o", label="Training Loss", linewidth=2)
                ax1.plot(x, val_losses, marker="s", label="Validation Loss", linewidth=2)
                ax1.set_xlabel("Run")
                ax1.set_ylabel("Loss")
                ax1.set_title("Evolução de Loss")
                ax1.legend()
                ax1.grid(True, alpha=0.3)

            # Accuracy plot
            if any("accuracy" in r.metrics for r in valid_runs):
                sorted_runs = sorted(valid_runs, key=lambda r: r.start_time or datetime.min)
                x = list(range(len(sorted_runs)))
                train_accs = [r.metrics.get("accuracy", float("nan")) for r in sorted_runs]
                val_accs = [r.metrics.get("val_accuracy", float("nan")) for r in sorted_runs]

                ax2.plot(x, train_accs, marker="o", label="Training Acc", linewidth=2)
                ax2.plot(x, val_accs, marker="s", label="Validation Acc", linewidth=2)
                ax2.set_xlabel("Run")
                ax2.set_ylabel("Accuracy")
                ax2.set_title("Evolução de Accuracy")
                ax2.legend()
                ax2.grid(True, alpha=0.3)

            plt.tight_layout()

            # Salvar
            filepath = await self._save_plot(fig, "training_progress", format_type)
            plt.close(fig)

            return filepath

        except Exception as e:
            logger.error("Erro ao gerar gráfico de progresso", error=str(e), exc_info=True)
            return None

    async def generate_multi_metric_summary(
        self,
        runs: list[ExperimentRun],
        metrics: list[str] = None,
        format_type: str = "png",
    ) -> Optional[str]:
        """Gera gráfico resumido com múltiplas métricas

        Args:
            runs: Lista de experiment runs
            metrics: Lista de métricas para incluir
            format_type: Formato de saída

        Returns:
            Caminho do arquivo gerado ou None
        """
        try:
            if metrics is None:
                metrics = ["accuracy", "val_accuracy", "precision", "recall", "f1"]

            # Criar figura
            n_metrics = len(metrics)
            fig, axes = plt.subplots(1, n_metrics, figsize=(4 * n_metrics, 4))
            if n_metrics == 1:
                axes = [axes]

            for i, metric in enumerate(metrics):
                valid_runs = [r for r in runs if metric in r.metrics]

                if valid_runs:
                    values = [r.metrics[metric] for r in valid_runs]
                    axes[i].boxplot(values, vert=True)
                    axes[i].set_ylabel(metric.replace("_", " ").title())
                    axes[i].set_title(f"Distribuição de {metric.replace('_', ' ')}")
                    axes[i].grid(True, alpha=0.3)
                else:
                    axes[i].text(
                        0.5,
                        0.5,
                        "Sem dados",
                        ha="center",
                        va="center",
                        transform=axes[i].transAxes,
                    )
                    axes[i].set_title(f"{metric.replace('_', ' ')}")

            plt.tight_layout()

            # Salvar
            filepath = await self._save_plot(fig, "multi_metric_summary", format_type)
            plt.close(fig)

            return filepath

        except Exception as e:
            logger.error("Erro ao gerar gráfico multi-métrica", error=str(e), exc_info=True)
            return None

    async def _save_plot(self, fig: plt.Figure, name: str, format_type: str) -> str:
        """Salva gráfico em arquivo

        Args:
            fig: Figura matplotlib
            name: Nome base do arquivo
            format_type: Formato (png/svg)

        Returns:
            Caminho do arquivo
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{name}.{format_type}"
        filepath = os.path.join(self._output_dir, filename)

        dpi = 150 if format_type == "png" else None
        fig.savefig(filepath, format=format_type, dpi=dpi, bbox_inches="tight")

        logger.info("Gráfico salvo", path=filepath)
        return filepath

    async def generate_all_plots(
        self,
        runs: list[ExperimentRun],
        format_type: str = "png",
    ) -> list[str]:
        """Gera todos os gráficos disponíveis

        Args:
            runs: Lista de experiment runs
            format_type: Formato de saída

        Returns:
            Lista de caminhos dos arquivos gerados
        """
        plots = []

        # Comparação de accuracy
        plot = await self.generate_experiment_comparison_plot(runs, "val_accuracy", format_type)
        if plot:
            plots.append(plot)

        # Timeline de accuracy
        plot = await self.generate_metric_timeline_plot(runs, "val_accuracy", format_type)
        if plot:
            plots.append(plot)

        # Correlação train/val
        plot = await self.generate_metrics_correlation_plot(
            runs, "accuracy", "val_accuracy", format_type
        )
        if plot:
            plots.append(plot)

        # Progresso de treinamento
        plot = await self.generate_training_progress_plot(runs, format_type)
        if plot:
            plots.append(plot)

        # Resumo multi-métrica
        plot = await self.generate_multi_metric_summary(runs, format_type=format_type)
        if plot:
            plots.append(plot)

        logger.info("Gráficos gerados", total=len(plots))
        return plots

    async def close(self) -> None:
        """Fecha recursos"""
        plt.close("all")
