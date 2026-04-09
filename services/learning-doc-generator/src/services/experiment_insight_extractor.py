"""Extractor de insights de experimentos MLflow"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings
from src.models import ExperimentRun, Insight, InsightConfidence

logger = structlog.get_logger()


class ExperimentInsightExtractor:
    """Extrai insights de experimentos MLflow"""

    def __init__(self):
        """Inicializa o extractor"""
        self.settings = get_settings()
        self._mlflow_client = None

    async def initialize(self) -> None:
        """Inicializa a conexão com MLflow"""
        try:
            import mlflow

            mlflow.set_tracking_uri(self.settings.mlflow_tracking_uri)
            self._mlflow_client = mlflow.tracking.MlflowClient()
            logger.info(
                "MLflow client inicializado", uri=self.settings.mlflow_tracking_uri
            )
        except Exception as e:
            logger.error("Erro ao inicializar MLflow client", error=str(e), exc_info=True)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _get_run_safe(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Busca run de forma segura com retry"""
        try:
            run = self._mlflow_client.get_run(run_id)
            return run.to_dictionary()
        except Exception as e:
            logger.warning("Erro ao buscar run", run_id=run_id, error=str(e))
            return None

    async def fetch_experiment_runs(
        self,
        experiment_ids: Optional[List[int]] = None,
        run_ids: Optional[List[str]] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        max_runs: int = 100,
    ) -> List[ExperimentRun]:
        """Busca runs de experimento do MLflow

        Args:
            experiment_ids: IDs dos experimentos
            run_ids: IDs específicos de runs
            period_start: Data de início do período
            period_end: Data de fim do período
            max_runs: Número máximo de runs

        Returns:
            Lista de ExperimentRun
        """
        runs_data = []

        try:
            if run_ids:
                # Buscar runs específicos
                for run_id in run_ids[:max_runs]:
                    run_dict = await self._get_run_safe(run_id)
                    if run_dict:
                        runs_data.append(run_dict)

            else:
                # Buscar por experimento
                from mlflow.entities import ViewType

                if experiment_ids is None:
                    # Listar todos os experimentos
                    experiments = self._mlflow_client.search_experiments(
                        view_type=ViewType.ACTIVE_ONLY
                    )
                    experiment_ids = [exp.experiment_id for exp in experiments]

                for exp_id in experiment_ids:
                    # Buscar runs do experimento
                    runs = self._mlflow_client.search_runs(
                        experiment_ids=[exp_id],
                        order_by=["start_time DESC"],
                        max_results=max_runs // len(experiment_ids) if experiment_ids else max_runs,
                    )

                    for run in runs:
                        run_dict = run.to_dictionary()
                        # Filtrar por período se especificado
                        if period_start or period_end:
                            start_time = run_dict.get("info", {}).get("start_time")
                            if start_time:
                                start_dt = datetime.fromtimestamp(start_time / 1000)
                                if period_start and start_dt < period_start:
                                    continue
                                if period_end and start_dt > period_end:
                                    continue

                        runs_data.append(run_dict)

                        if len(runs_data) >= max_runs:
                            break

                    if len(runs_data) >= max_runs:
                        break

        except Exception as e:
            logger.error("Erro ao buscar experiment runs", error=str(e), exc_info=True)

        # Converter para ExperimentRun
        experiment_runs = []
        for run_dict in runs_data:
            try:
                info = run_dict.get("info", {})
                data = run_dict.get("data", {})

                experiment_run = ExperimentRun(
                    run_id=info.get("run_id", ""),
                    experiment_id=info.get("experiment_id", 0),
                    name=info.get("run_name", ""),
                    status=info.get("status", ""),
                    start_time=self._parse_timestamp(info.get("start_time")),
                    end_time=self._parse_timestamp(info.get("end_time")),
                    metrics=self._extract_metrics(data.get("metrics", [])),
                    params={m["key"]: m["value"] for m in data.get("params", [])},
                    tags={t["key"]: t["value"] for t in data.get("tags", [])},
                    artifact_uri=info.get("artifact_uri"),
                )
                experiment_runs.append(experiment_run)
            except Exception as e:
                logger.warning("Erro ao converter run", error=str(e))
                continue

        logger.info(
            "Experiment runs fetched",
            count=len(experiment_runs),
            max_runs=max_runs,
        )
        return experiment_runs

    def _parse_timestamp(self, ts_ms: Optional[int]) -> Optional[datetime]:
        """Converte timestamp em ms para datetime"""
        if ts_ms:
            return datetime.fromtimestamp(ts_ms / 1000)
        return None

    def _extract_metrics(self, metrics_data: List[Dict[str, Any]]) -> Dict[str, float]:
        """Extrai métricas do formato MLflow"""
        return {m["key"]: m["value"] for m in metrics_data if m.get("value") is not None}

    async def extract_insights(
        self, runs: List[ExperimentRun], baseline_run_id: Optional[str] = None
    ) -> List[Insight]:
        """Extrai insights de uma lista de runs

        Args:
            runs: Lista de experiment runs
            baseline_run_id: ID do run baseline para comparação

        Returns:
            Lista de insights
        """
        insights = []

        if not runs:
            return insights

        # Buscar baseline se especificado
        baseline_metrics = {}
        if baseline_run_id:
            for run in runs:
                if run.run_id == baseline_run_id:
                    baseline_metrics = run.metrics
                    break

        # Agrupar runs por experimento
        runs_by_experiment: Dict[int, List[ExperimentRun]] = {}
        for run in runs:
            if run.experiment_id not in runs_by_experiment:
                runs_by_experiment[run.experiment_id] = []
            runs_by_experiment[run.experiment_id].append(run)

        # Extrair insights para cada experimento
        for exp_id, exp_runs in runs_by_experiment.items():
            insights.extend(await self._extract_experiment_insights(exp_runs, baseline_metrics))

        # Extrair insights de tendências
        insights.extend(await self._extract_trend_insights(runs))

        # Extrair insights de performance
        insights.extend(await self._extract_performance_insights(runs, baseline_metrics))

        logger.info("Insights extraídos", total=len(insights))
        return insights

    async def get_runs_by_period(
        self,
        start_time: datetime,
        end_time: datetime,
        experiment_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[ExperimentRun]:
        """Busca runs por período

        Args:
            start_time: Data de início
            end_time: Data de fim
            experiment_id: ID do experimento (opcional)
            limit: Número máximo de runs

        Returns:
            Lista de ExperimentRun
        """
        return await self.fetch_experiment_runs(
            experiment_ids=[experiment_id] if experiment_id else None,
            period_start=start_time,
            period_end=end_time,
            max_runs=limit,
        )

    async def get_run_by_id(self, run_id: str):
        """Busca um run específico por ID

        Args:
            run_id: ID do run MLflow

        Returns:
            Objeto run do MLflow ou None
        """
        try:
            return self._mlflow_client.get_run(run_id)
        except Exception as e:
            logger.error("Erro ao buscar run por ID", run_id=run_id, error=str(e))
            return None

    async def extract_insights_from_runs(
        self, runs: List[ExperimentRun]
    ) -> List[Insight]:
        """Extrai insights de uma lista de runs (alias para extract_insights)

        Args:
            runs: Lista de experiment runs

        Returns:
            Lista de insights
        """
        return await self.extract_insights(runs)

    async def _extract_experiment_insights(
        self, runs: List[ExperimentRun], baseline_metrics: Dict[str, float]
    ) -> List[Insight]:
        """Extrai insights específicos de um experimento"""
        insights = []

        if not runs:
            return insights

        # Encontrar melhor run
        best_run = max(runs, key=lambda r: r.metrics.get("val_accuracy", 0))

        # Insight: Melhor modelo
        if best_run.metrics:
            insights.append(
                Insight(
                    title="Melhor modelo identificado",
                    description=f"O run {best_run.name} obteve o melhor desempenho.",
                    evidence=best_run.metrics,
                    confidence=InsightConfidence.HIGH,
                    experiment_ids=[best_run.run_id],
                    category="performance",
                )
            )

        # Comparar com baseline
        if baseline_metrics:
            for metric_name in ["accuracy", "val_accuracy", "f1", "precision", "recall"]:
                if metric_name in best_run.metrics and metric_name in baseline_metrics:
                    current_value = best_run.metrics[metric_name]
                    baseline_value = baseline_metrics[metric_name]
                    improvement = ((current_value - baseline_value) / baseline_value) * 100

                    if improvement > 5:
                        insights.append(
                            Insight(
                                title=f"Melhora em {metric_name}",
                                description=f"{metric_name} melhorou {improvement:.1f}% em relação ao baseline",
                                evidence={
                                    "current": current_value,
                                    "baseline": baseline_value,
                                    "improvement_percent": improvement,
                                },
                                confidence=InsightConfidence.HIGH
                                if improvement > 10
                                else InsightConfidence.MEDIUM,
                                experiment_ids=[best_run.run_id],
                                category="improvement",
                            )
                        )
                    elif improvement < -5:
                        insights.append(
                            Insight(
                                title=f"Regressão em {metric_name}",
                                description=f"{metric_name} piorou {abs(improvement):.1f}% em relação ao baseline",
                                evidence={
                                    "current": current_value,
                                    "baseline": baseline_value,
                                    "regression_percent": abs(improvement),
                                },
                                confidence=InsightConfidence.HIGH,
                                experiment_ids=[best_run.run_id],
                                category="regression",
                            )
                        )

        return insights

    async def _extract_trend_insights(self, runs: List[ExperimentRun]) -> List[Insight]:
        """Extrai insights de tendências entre runs"""
        insights = []

        if len(runs) < 3:
            return insights

        # Ordenar por data
        sorted_runs = sorted([r for r in runs if r.start_time], key=lambda r: r.start_time)

        # Analisar tendência de accuracy
        accuracies = []
        for run in sorted_runs:
            if "val_accuracy" in run.metrics:
                accuracies.append((run.start_time, run.metrics["val_accuracy"], run.run_id))

        if len(accuracies) >= 3:
            # Calcular tendência
            values = [a[1] for a in accuracies]
            if values[-1] > values[0]:
                improvement = ((values[-1] - values[0]) / values[0]) * 100
                insights.append(
                    Insight(
                        title="Tendência de melhoria observada",
                        description=f"val_accuracy melhorou {improvement:.1f}% ao longo de {len(accuracies)} runs",
                        evidence={
                            "start_value": values[0],
                            "end_value": values[-1],
                            "improvement_percent": improvement,
                            "runs_count": len(accuracies),
                        },
                        confidence=InsightConfidence.MEDIUM,
                        experiment_ids=[a[2] for a in accuracies],
                        category="trend",
                    )
                )

        return insights

    async def _extract_performance_insights(
        self, runs: List[ExperimentRun], baseline_metrics: Dict[str, float]
    ) -> List[Insight]:
        """Extrai insights de performance"""
        insights = []

        # Analisar duração dos runs
        durations = []
        for run in runs:
            if run.start_time and run.end_time:
                duration = (run.end_time - run.start_time).total_seconds()
                durations.append((run.run_id, duration))

        if durations:
            avg_duration = sum(d[1] for d in durations) / len(durations)
            insights.append(
                Insight(
                    title="Tempo médio de treinamento",
                    description=f"Os runs levaram em média {avg_duration:.1f} segundos para completar",
                    evidence={
                        "avg_duration_seconds": avg_duration,
                        "runs_analyzed": len(durations),
                    },
                    confidence=InsightConfidence.HIGH,
                    experiment_ids=[d[0] for d in durations],
                    category="performance",
                )
            )

        return insights

    async def generate_summary(self, runs: List[ExperimentRun]) -> str:
        """Gera um resumo executivo dos runs

        Args:
            runs: Lista de experiment runs

        Returns:
            String com resumo
        """
        if not runs:
            return "Nenhum experimento encontrado para análise."

        total_runs = len(runs)
        completed_runs = sum(1 for r in runs if r.status == "FINISHED")
        failed_runs = sum(1 for r in runs if r.status == "FAILED")

        summary_lines = [
            f"Analisados {total_runs} experimentos.",
            f"{completed_runs} concluídos com sucesso.",
        ]

        if failed_runs > 0:
            summary_lines.append(f"{failed_runs} falharam.")

        # Melhor run
        best_run = max(
            (r for r in runs if r.status == "FINISHED"),
            key=lambda r: r.metrics.get("val_accuracy", 0),
            default=None,
        )

        if best_run:
            summary_lines.append(
                f"Melhor accuracy: {best_run.metrics.get('val_accuracy', 0):.4f} (run: {best_run.name})"
            )

        return " ".join(summary_lines)

    async def generate_recommendations(
        self, insights: List[Insight], runs: List[ExperimentRun]
    ) -> List[str]:
        """Gera recomendações baseado nos insights

        Args:
            insights: Lista de insights extraídos
            runs: Lista de experiment runs

        Returns:
            Lista de recomendações
        """
        recommendations = []

        # Analisar insights de regressão
        regressions = [i for i in insights if i.category == "regression"]
        if regressions:
            recommendations.append(
                "Investigar causas de regressão identificadas antes de promover modelo."
            )

        # Analisar insights de melhoria
        improvements = [i for i in insights if i.category == "improvement"]
        if improvements:
            recommendations.append(
                "Considerar promover o modelo com melhor desempenho para staging."
            )

        # Analisar falhas
        failed_runs = sum(1 for r in runs if r.status == "FAILED")
        if failed_runs > len(runs) * 0.2:
            recommendations.append(
                "Alta taxa de falhas detectada - revisar configuração dos experimentos."
            )

        # Recomendação de feature engineering
        if not recommendations:
            recommendations.append(
                "Continuar experimentando com diferentes hiperparâmetros."
            )

        return recommendations

    async def close(self) -> None:
        """Fecha conexões"""
        self._mlflow_client = None
