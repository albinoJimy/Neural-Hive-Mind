"""
Model Performance Monitor - Monitora métricas de modelos e feedback para detectar degradação.

Funcionalidades:
- Consulta métricas do MLflow (precision, recall, F1)
- Consulta estatísticas de feedback do MongoDB
- Calcula score agregado de performance
- Detecta degradação baseado em thresholds
- Exporta métricas para Prometheus
"""

import os
import sys
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import structlog
from dataclasses import dataclass
import pandas as pd

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../libraries/python'))

from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.feedback.feedback_collector import FeedbackCollector
from neural_hive_specialists.mlflow_client import MLflowClient
import mlflow
from mlflow.tracking import MlflowClient as TrackingClient

logger = structlog.get_logger(__name__)


@dataclass
class PerformanceMetrics:
    """Métricas de performance do modelo."""
    precision: float
    recall: float
    f1_score: float
    accuracy: Optional[float] = None
    run_id: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class FeedbackStats:
    """Estatísticas de feedback."""
    avg_rating: float
    total_count: int
    positive_count: int
    negative_count: int
    neutral_count: int


@dataclass
class PerformanceReport:
    """Relatório completo de performance."""
    specialist_type: str
    mlflow_metrics: Optional[PerformanceMetrics]
    feedback_stats: Optional[FeedbackStats]
    aggregate_score: float
    is_degraded: bool
    degradation_reasons: List[str]
    timestamp: datetime
    recommendations: List[str]


class ModelPerformanceMonitor:
    """Monitor de performance de modelos com integração MLflow e feedback."""

    def __init__(
        self,
        mlflow_tracking_uri: Optional[str] = None,
        mongodb_uri: Optional[str] = None,
        precision_threshold: float = 0.75,
        recall_threshold: float = 0.70,
        f1_threshold: float = 0.72,
        feedback_avg_threshold: float = 0.6,
        mlflow_weight: float = 0.7,
        feedback_weight: float = 0.3
    ):
        """
        Inicializa o monitor.

        Args:
            mlflow_tracking_uri: URI do servidor MLflow
            mongodb_uri: URI do MongoDB
            precision_threshold: Threshold mínimo de precision
            recall_threshold: Threshold mínimo de recall
            f1_threshold: Threshold mínimo de F1
            feedback_avg_threshold: Threshold mínimo de feedback médio
            mlflow_weight: Peso das métricas MLflow no score agregado
            feedback_weight: Peso do feedback no score agregado
        """
        self.mlflow_tracking_uri = mlflow_tracking_uri or os.getenv(
            'MLFLOW_TRACKING_URI', 'http://localhost:5000'
        )
        self.mongodb_uri = mongodb_uri or os.getenv('MONGODB_URI')

        # Thresholds
        self.precision_threshold = precision_threshold
        self.recall_threshold = recall_threshold
        self.f1_threshold = f1_threshold
        self.feedback_avg_threshold = feedback_avg_threshold

        # Weights
        self.mlflow_weight = mlflow_weight
        self.feedback_weight = feedback_weight

        # Initialize clients
        mlflow.set_tracking_uri(self.mlflow_tracking_uri)
        self.tracking_client = TrackingClient(self.mlflow_tracking_uri)

        # Initialize feedback collector
        self.feedback_collector = FeedbackCollector(mongodb_uri=self.mongodb_uri)

        logger.info(
            "monitor_initialized",
            mlflow_uri=self.mlflow_tracking_uri,
            thresholds={
                "precision": self.precision_threshold,
                "recall": self.recall_threshold,
                "f1": self.f1_threshold,
                "feedback_avg": self.feedback_avg_threshold
            }
        )

    def query_mlflow_metrics(
        self,
        specialist_type: str,
        last_n_runs: int = 100
    ) -> Optional[PerformanceMetrics]:
        """
        Consulta métricas do MLflow para um specialist.

        Args:
            specialist_type: Tipo do specialist (technical, business, etc.)
            last_n_runs: Número de runs recentes para analisar

        Returns:
            PerformanceMetrics ou None se não encontrado
        """
        try:
            experiment_name = f"{specialist_type}-specialist"

            # Get experiment
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if not experiment:
                logger.warning(
                    "experiment_not_found",
                    experiment_name=experiment_name
                )
                return None

            # Search runs
            runs = self.tracking_client.search_runs(
                experiment_ids=[experiment.experiment_id],
                filter_string="",
                max_results=last_n_runs,
                order_by=["start_time DESC"]
            )

            if not runs:
                logger.warning(
                    "no_runs_found",
                    experiment_name=experiment_name
                )
                return None

            # Get latest production run or latest run
            production_runs = [r for r in runs if r.data.tags.get('stage') == 'Production']
            latest_run = production_runs[0] if production_runs else runs[0]

            # Extract metrics
            metrics = latest_run.data.metrics

            performance = PerformanceMetrics(
                precision=metrics.get('precision', 0.0),
                recall=metrics.get('recall', 0.0),
                f1_score=metrics.get('f1_score', 0.0),
                accuracy=metrics.get('accuracy'),
                run_id=latest_run.info.run_id,
                timestamp=datetime.fromtimestamp(latest_run.info.start_time / 1000)
            )

            logger.info(
                "mlflow_metrics_retrieved",
                specialist_type=specialist_type,
                run_id=performance.run_id,
                precision=performance.precision,
                recall=performance.recall,
                f1=performance.f1_score
            )

            return performance

        except Exception as e:
            logger.error(
                "mlflow_query_failed",
                specialist_type=specialist_type,
                error=str(e)
            )
            return None

    def query_feedback_statistics(
        self,
        specialist_type: str,
        window_days: int = 30
    ) -> Optional[FeedbackStats]:
        """
        Consulta estatísticas de feedback do MongoDB.

        Args:
            specialist_type: Tipo do specialist
            window_days: Janela de dias para considerar feedback

        Returns:
            FeedbackStats ou None se não encontrado
        """
        try:
            # Use existing FeedbackCollector
            stats = self.feedback_collector.get_feedback_statistics(
                specialist_type=specialist_type,
                window_days=window_days
            )

            if not stats:
                logger.warning(
                    "no_feedback_found",
                    specialist_type=specialist_type
                )
                return None

            feedback_stats = FeedbackStats(
                avg_rating=stats.get('avg_rating', 0.0),
                total_count=stats.get('total_count', 0),
                positive_count=stats.get('rating_distribution', {}).get('positive', 0),
                negative_count=stats.get('rating_distribution', {}).get('negative', 0),
                neutral_count=stats.get('rating_distribution', {}).get('neutral', 0)
            )

            logger.info(
                "feedback_stats_retrieved",
                specialist_type=specialist_type,
                avg_rating=feedback_stats.avg_rating,
                total_count=feedback_stats.total_count
            )

            return feedback_stats

        except Exception as e:
            logger.error(
                "feedback_query_failed",
                specialist_type=specialist_type,
                error=str(e)
            )
            return None

    def calculate_aggregate_score(
        self,
        mlflow_metrics: Optional[PerformanceMetrics],
        feedback_stats: Optional[FeedbackStats]
    ) -> float:
        """
        Calcula score agregado de performance.

        Fórmula: (MLflow F1 * 0.7) + (Feedback Avg * 0.3)

        Args:
            mlflow_metrics: Métricas do MLflow
            feedback_stats: Estatísticas de feedback

        Returns:
            Score agregado (0.0 - 1.0)
        """
        mlflow_score = 0.0
        if mlflow_metrics:
            mlflow_score = mlflow_metrics.f1_score

        feedback_score = 0.0
        if feedback_stats:
            feedback_score = feedback_stats.avg_rating

        aggregate = (mlflow_score * self.mlflow_weight) + (feedback_score * self.feedback_weight)

        logger.info(
            "aggregate_score_calculated",
            mlflow_score=mlflow_score,
            feedback_score=feedback_score,
            aggregate=aggregate
        )

        return aggregate

    def detect_degradation(
        self,
        mlflow_metrics: Optional[PerformanceMetrics],
        feedback_stats: Optional[FeedbackStats],
        aggregate_score: float
    ) -> Tuple[bool, List[str]]:
        """
        Detecta degradação de performance.

        Args:
            mlflow_metrics: Métricas do MLflow
            feedback_stats: Estatísticas de feedback
            aggregate_score: Score agregado

        Returns:
            Tupla (is_degraded, reasons)
        """
        reasons = []

        # Check MLflow metrics
        if mlflow_metrics:
            if mlflow_metrics.precision < self.precision_threshold:
                reasons.append(
                    f"Precision ({mlflow_metrics.precision:.3f}) abaixo do threshold ({self.precision_threshold})"
                )
            if mlflow_metrics.recall < self.recall_threshold:
                reasons.append(
                    f"Recall ({mlflow_metrics.recall:.3f}) abaixo do threshold ({self.recall_threshold})"
                )
            if mlflow_metrics.f1_score < self.f1_threshold:
                reasons.append(
                    f"F1 Score ({mlflow_metrics.f1_score:.3f}) abaixo do threshold ({self.f1_threshold})"
                )

        # Check feedback
        if feedback_stats:
            if feedback_stats.avg_rating < self.feedback_avg_threshold:
                reasons.append(
                    f"Feedback médio ({feedback_stats.avg_rating:.3f}) abaixo do threshold ({self.feedback_avg_threshold})"
                )

        # Check aggregate
        if aggregate_score < 0.65:
            reasons.append(
                f"Score agregado ({aggregate_score:.3f}) abaixo do threshold (0.65)"
            )

        is_degraded = len(reasons) > 0

        if is_degraded:
            logger.warning(
                "degradation_detected",
                reasons=reasons
            )
        else:
            logger.info("performance_ok")

        return is_degraded, reasons

    def get_performance_report(
        self,
        specialist_type: str,
        last_n_runs: int = 100,
        window_days: int = 30
    ) -> PerformanceReport:
        """
        Gera relatório completo de performance.

        Args:
            specialist_type: Tipo do specialist
            last_n_runs: Número de runs MLflow para analisar
            window_days: Janela de dias para feedback

        Returns:
            PerformanceReport
        """
        logger.info(
            "generating_performance_report",
            specialist_type=specialist_type
        )

        # Query metrics
        mlflow_metrics = self.query_mlflow_metrics(specialist_type, last_n_runs)
        feedback_stats = self.query_feedback_statistics(specialist_type, window_days)

        # Calculate aggregate score
        aggregate_score = self.calculate_aggregate_score(mlflow_metrics, feedback_stats)

        # Detect degradation
        is_degraded, degradation_reasons = self.detect_degradation(
            mlflow_metrics, feedback_stats, aggregate_score
        )

        # Generate recommendations
        recommendations = []
        if is_degraded:
            recommendations.append("Considerar retreinamento do modelo")
            recommendations.append("Revisar feedback recente para identificar problemas")
            recommendations.append("Verificar mudanças no padrão de dados")
        else:
            recommendations.append("Performance dentro dos thresholds esperados")
            recommendations.append("Continuar monitoramento regular")

        report = PerformanceReport(
            specialist_type=specialist_type,
            mlflow_metrics=mlflow_metrics,
            feedback_stats=feedback_stats,
            aggregate_score=aggregate_score,
            is_degraded=is_degraded,
            degradation_reasons=degradation_reasons,
            timestamp=datetime.now(),
            recommendations=recommendations
        )

        logger.info(
            "performance_report_generated",
            specialist_type=specialist_type,
            aggregate_score=aggregate_score,
            is_degraded=is_degraded
        )

        return report

    def export_metrics_to_prometheus(
        self,
        report: PerformanceReport,
        pushgateway_url: Optional[str] = None
    ):
        """
        Exporta métricas para Prometheus Pushgateway.

        Args:
            report: Relatório de performance
            pushgateway_url: URL do Pushgateway
        """
        try:
            from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

            registry = CollectorRegistry()

            # Performance score
            score_gauge = Gauge(
                'neural_hive_model_performance_score',
                'Score agregado de performance do modelo',
                ['specialist_type'],
                registry=registry
            )
            score_gauge.labels(specialist_type=report.specialist_type).set(report.aggregate_score)

            # Degradation detected
            degradation_gauge = Gauge(
                'neural_hive_model_degradation_detected',
                'Indica se degradação foi detectada (1=sim, 0=não)',
                ['specialist_type'],
                registry=registry
            )
            degradation_gauge.labels(specialist_type=report.specialist_type).set(
                1 if report.is_degraded else 0
            )

            # MLflow metrics
            if report.mlflow_metrics:
                precision_gauge = Gauge(
                    'neural_hive_mlflow_model_precision',
                    'Precision do modelo',
                    ['specialist_type'],
                    registry=registry
                )
                precision_gauge.labels(specialist_type=report.specialist_type).set(
                    report.mlflow_metrics.precision
                )

                recall_gauge = Gauge(
                    'neural_hive_mlflow_model_recall',
                    'Recall do modelo',
                    ['specialist_type'],
                    registry=registry
                )
                recall_gauge.labels(specialist_type=report.specialist_type).set(
                    report.mlflow_metrics.recall
                )

                f1_gauge = Gauge(
                    'neural_hive_mlflow_model_f1',
                    'F1 Score do modelo',
                    ['specialist_type'],
                    registry=registry
                )
                f1_gauge.labels(specialist_type=report.specialist_type).set(
                    report.mlflow_metrics.f1_score
                )

            # Push to gateway
            if pushgateway_url:
                push_to_gateway(
                    pushgateway_url,
                    job='model_performance_monitor',
                    registry=registry
                )
                logger.info(
                    "metrics_exported_to_prometheus",
                    pushgateway_url=pushgateway_url
                )

        except Exception as e:
            logger.error(
                "prometheus_export_failed",
                error=str(e)
            )


def main():
    """CLI para execução do monitor."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description='Monitor de performance de modelos'
    )
    parser.add_argument(
        '--specialist-type',
        required=True,
        help='Tipo do specialist (technical, business, etc.)'
    )
    parser.add_argument(
        '--last-n-runs',
        type=int,
        default=100,
        help='Número de runs MLflow para analisar (default: 100)'
    )
    parser.add_argument(
        '--window-days',
        type=int,
        default=30,
        help='Janela de dias para feedback (default: 30)'
    )
    parser.add_argument(
        '--output-format',
        choices=['json', 'text'],
        default='text',
        help='Formato de saída (default: text)'
    )
    parser.add_argument(
        '--export-metrics',
        help='URL do Prometheus Pushgateway para exportar métricas'
    )

    args = parser.parse_args()

    # Initialize monitor
    monitor = ModelPerformanceMonitor()

    # Generate report
    report = monitor.get_performance_report(
        specialist_type=args.specialist_type,
        last_n_runs=args.last_n_runs,
        window_days=args.window_days
    )

    # Export metrics
    if args.export_metrics:
        monitor.export_metrics_to_prometheus(report, args.export_metrics)

    # Output report
    if args.output_format == 'json':
        report_dict = {
            'specialist_type': report.specialist_type,
            'aggregate_score': report.aggregate_score,
            'is_degraded': report.is_degraded,
            'degradation_reasons': report.degradation_reasons,
            'recommendations': report.recommendations,
            'timestamp': report.timestamp.isoformat(),
            'mlflow_metrics': {
                'precision': report.mlflow_metrics.precision,
                'recall': report.mlflow_metrics.recall,
                'f1_score': report.mlflow_metrics.f1_score,
                'run_id': report.mlflow_metrics.run_id
            } if report.mlflow_metrics else None,
            'feedback_stats': {
                'avg_rating': report.feedback_stats.avg_rating,
                'total_count': report.feedback_stats.total_count,
                'positive_count': report.feedback_stats.positive_count,
                'negative_count': report.feedback_stats.negative_count
            } if report.feedback_stats else None
        }
        print(json.dumps(report_dict, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"RELATÓRIO DE PERFORMANCE - {report.specialist_type}")
        print(f"{'='*60}\n")

        print(f"Timestamp: {report.timestamp.isoformat()}")
        print(f"Score Agregado: {report.aggregate_score:.3f}")
        print(f"Status: {'⚠️  DEGRADADO' if report.is_degraded else '✅ OK'}\n")

        if report.mlflow_metrics:
            print("MLflow Metrics:")
            print(f"  - Precision: {report.mlflow_metrics.precision:.3f}")
            print(f"  - Recall: {report.mlflow_metrics.recall:.3f}")
            print(f"  - F1 Score: {report.mlflow_metrics.f1_score:.3f}")
            print(f"  - Run ID: {report.mlflow_metrics.run_id}\n")

        if report.feedback_stats:
            print("Feedback Stats:")
            print(f"  - Média: {report.feedback_stats.avg_rating:.3f}")
            print(f"  - Total: {report.feedback_stats.total_count}")
            print(f"  - Positivo: {report.feedback_stats.positive_count}")
            print(f"  - Negativo: {report.feedback_stats.negative_count}\n")

        if report.degradation_reasons:
            print("Razões de Degradação:")
            for reason in report.degradation_reasons:
                print(f"  - {reason}")
            print()

        print("Recomendações:")
        for rec in report.recommendations:
            print(f"  - {rec}")
        print()

    # Exit code
    sys.exit(1 if report.is_degraded else 0)


if __name__ == '__main__':
    main()
