"""
Auto-Retrain Orchestrator - Orquestra retreinamento automático baseado em degradação de performance.

Funcionalidades:
- Detecta degradação usando ModelPerformanceMonitor
- Gera novos datasets com AI (generate_training_datasets.py)
- Executa pipeline de treinamento via MLflow
- Monitora conclusão e promove modelo se melhor
- Envia notificações em caso de falha
"""

import os
import sys
import subprocess
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import structlog
from dataclasses import dataclass
import json

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../libraries/python'))

from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger
from neural_hive_specialists.feedback.feedback_collector import FeedbackCollector
from model_performance_monitor import ModelPerformanceMonitor

logger = structlog.get_logger(__name__)


@dataclass
class RetrainResult:
    """Resultado de retreinamento."""
    success: bool
    specialist_type: str
    mlflow_run_id: Optional[str]
    new_metrics: Optional[Dict]
    baseline_metrics: Optional[Dict]
    improved: bool
    error_message: Optional[str] = None
    dataset_path: Optional[str] = None
    duration_seconds: float = 0.0


class AutoRetrainOrchestrator:
    """Orquestrador de retreinamento automático."""

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        mlflow_tracking_uri: Optional[str] = None,
        dataset_num_samples: int = 1000,
        dataset_generation_timeout: int = 1800,  # 30 min
        notification_channels: List[str] = None
    ):
        """
        Inicializa o orquestrador.

        Args:
            mongodb_uri: URI do MongoDB
            mlflow_tracking_uri: URI do MLflow
            dataset_num_samples: Número de amostras para gerar
            dataset_generation_timeout: Timeout para geração de dataset (segundos)
            notification_channels: Canais de notificação ['slack', 'email']
        """
        self.mongodb_uri = mongodb_uri or os.getenv('MONGODB_URI')
        self.mlflow_tracking_uri = mlflow_tracking_uri or os.getenv(
            'MLFLOW_TRACKING_URI', 'http://localhost:5000'
        )
        self.dataset_num_samples = dataset_num_samples
        self.dataset_generation_timeout = dataset_generation_timeout
        self.notification_channels = notification_channels or ['slack']

        # Initialize components
        self.performance_monitor = ModelPerformanceMonitor(
            mlflow_tracking_uri=self.mlflow_tracking_uri,
            mongodb_uri=self.mongodb_uri
        )
        self.retraining_trigger = RetrainingTrigger(
            mongodb_uri=self.mongodb_uri,
            mlflow_tracking_uri=self.mlflow_tracking_uri
        )
        self.feedback_collector = FeedbackCollector(mongodb_uri=self.mongodb_uri)

        logger.info(
            "orchestrator_initialized",
            mlflow_uri=self.mlflow_tracking_uri,
            dataset_num_samples=self.dataset_num_samples,
            notification_channels=self.notification_channels
        )

    def check_performance_and_retrain(
        self,
        specialist_type: str,
        force: bool = False,
        skip_dataset_generation: bool = False,
        dry_run: bool = False
    ) -> RetrainResult:
        """
        Verifica performance e executa retreinamento se necessário.

        Args:
            specialist_type: Tipo do specialist
            force: Forçar retreinamento mesmo se performance OK
            skip_dataset_generation: Usar datasets existentes
            dry_run: Simular sem executar

        Returns:
            RetrainResult
        """
        start_time = time.time()

        logger.info(
            "checking_performance",
            specialist_type=specialist_type,
            force=force,
            dry_run=dry_run
        )

        # 1. Check performance
        report = self.performance_monitor.get_performance_report(specialist_type)

        if not force and not report.is_degraded:
            logger.info(
                "performance_ok_no_retrain_needed",
                specialist_type=specialist_type,
                aggregate_score=report.aggregate_score
            )
            result = RetrainResult(
                success=True,
                specialist_type=specialist_type,
                mlflow_run_id=None,
                new_metrics=None,
                baseline_metrics=None,
                improved=False,
                duration_seconds=time.time() - start_time
            )
            self._safe_export_metrics(result)
            return result

        # Performance degraded or forced - proceed with retrain
        logger.warning(
            "performance_degraded_starting_retrain",
            specialist_type=specialist_type,
            degradation_reasons=report.degradation_reasons,
            force=force
        )

        if dry_run:
            logger.info("dry_run_mode_skipping_actual_retrain")
            result = RetrainResult(
                success=True,
                specialist_type=specialist_type,
                mlflow_run_id="dry-run",
                new_metrics=None,
                baseline_metrics=None,
                improved=False,
                duration_seconds=time.time() - start_time
            )
            self._safe_export_metrics(result)
            return result

        result: Optional[RetrainResult] = None
        try:
            # 2. Generate new datasets (if not skipped)
            dataset_path = None
            if not skip_dataset_generation:
                dataset_path = self._generate_datasets(specialist_type)
                if not dataset_path:
                    raise Exception("Falha na geração de datasets")

            # 3. Merge with feedback data
            merged_dataset_path = self._merge_with_feedback(specialist_type, dataset_path)

            # 4. Trigger training
            mlflow_run_id = self._trigger_training(specialist_type, merged_dataset_path)

            # 5. Monitor completion
            training_success = self._monitor_training(mlflow_run_id)

            if not training_success:
                raise Exception(f"Treinamento falhou - Run ID: {mlflow_run_id}")

            # 6. Compare metrics
            new_metrics, baseline_metrics, improved = self._compare_metrics(
                specialist_type, mlflow_run_id
            )

            # 7. Send success notification
            self._send_notification(
                status='success',
                details={
                    'specialist_type': specialist_type,
                    'mlflow_run_id': mlflow_run_id,
                    'improved': improved,
                    'new_metrics': new_metrics,
                    'baseline_metrics': baseline_metrics
                }
            )

            result = RetrainResult(
                success=True,
                specialist_type=specialist_type,
                mlflow_run_id=mlflow_run_id,
                new_metrics=new_metrics,
                baseline_metrics=baseline_metrics,
                improved=improved,
                dataset_path=dataset_path,
                duration_seconds=time.time() - start_time
            )

            logger.info(
                "retrain_completed_successfully",
                specialist_type=specialist_type,
                mlflow_run_id=mlflow_run_id,
                improved=improved,
                duration_seconds=result.duration_seconds
            )

        except Exception as e:
            logger.error(
                "retrain_failed",
                specialist_type=specialist_type,
                error=str(e)
            )

            # Send failure notification
            self._send_notification(
                status='failed',
                details={
                    'specialist_type': specialist_type,
                    'error_message': str(e)
                }
            )

            result = RetrainResult(
                success=False,
                specialist_type=specialist_type,
                mlflow_run_id=None,
                new_metrics=None,
                baseline_metrics=None,
                improved=False,
                error_message=str(e),
                duration_seconds=time.time() - start_time
            )

        self._safe_export_metrics(result)
        return result

    def _generate_datasets(self, specialist_type: str) -> Optional[str]:
        """
        Gera novos datasets usando generate_training_datasets.py.

        Args:
            specialist_type: Tipo do specialist

        Returns:
            Path do dataset gerado ou None se falhar
        """
        logger.info(
            "generating_datasets",
            specialist_type=specialist_type,
            num_samples=self.dataset_num_samples
        )

        # Path to generation script
        script_path = Path(__file__).parent.parent / 'training' / 'generate_training_datasets.py'

        # Build command
        cmd = [
            sys.executable,
            str(script_path),
            '--specialist-type', specialist_type,
            '--num-samples', str(self.dataset_num_samples)
        ]

        # Add env vars if set
        env = os.environ.copy()
        if os.getenv('LLM_PROVIDER'):
            env['LLM_PROVIDER'] = os.getenv('LLM_PROVIDER')
        if os.getenv('LLM_MODEL'):
            env['LLM_MODEL'] = os.getenv('LLM_MODEL')
        if os.getenv('LLM_BASE_URL'):
            env['LLM_BASE_URL'] = os.getenv('LLM_BASE_URL')

        try:
            # Execute with timeout
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.dataset_generation_timeout
            )

            if result.returncode != 0:
                logger.error(
                    "dataset_generation_failed",
                    stderr=result.stderr,
                    returncode=result.returncode
                )
                return None

            # Parse output to find dataset path
            # Supports two formats:
            # 1. Portuguese: "Dataset salvo em: /path/to/dataset.parquet"
            # 2. English: "Dataset saved to /path/to/dataset.parquet"
            for line in result.stdout.split('\n'):
                dataset_path = None

                if 'Dataset salvo em:' in line:
                    # Portuguese format with colon separator
                    dataset_path = line.split(':')[-1].strip()
                elif 'saved to' in line.lower():
                    # English format without colon - extract path after "saved to"
                    line_lower = line.lower()
                    saved_to_idx = line_lower.index('saved to')
                    # Extract from original line (preserving case) after "saved to "
                    dataset_path = line[saved_to_idx + len('saved to'):].strip()

                if dataset_path:
                    logger.info(
                        "dataset_generated_successfully",
                        dataset_path=dataset_path
                    )
                    return dataset_path

            # Fallback: use default path
            default_path = f"/data/training/{specialist_type}_specialist_dataset.parquet"
            if Path(default_path).exists():
                logger.info(
                    "using_default_dataset_path",
                    dataset_path=default_path
                )
                return default_path

            logger.warning("dataset_path_not_found_in_output")
            return None

        except subprocess.TimeoutExpired:
            logger.error(
                "dataset_generation_timeout",
                timeout=self.dataset_generation_timeout
            )
            return None
        except Exception as e:
            logger.error(
                "dataset_generation_error",
                error=str(e)
            )
            return None

    def _merge_with_feedback(
        self,
        specialist_type: str,
        new_dataset_path: Optional[str]
    ) -> str:
        """
        Merge novos datasets com dados de feedback do MongoDB.

        Args:
            specialist_type: Tipo do specialist
            new_dataset_path: Path do novo dataset

        Returns:
            Path do dataset merged
        """
        try:
            import pandas as pd

            logger.info(
                "merging_with_feedback",
                specialist_type=specialist_type,
                new_dataset_path=new_dataset_path
            )

            # Load new dataset
            if new_dataset_path and Path(new_dataset_path).exists():
                new_df = pd.read_parquet(new_dataset_path)
                logger.info(
                    "new_dataset_loaded",
                    rows=len(new_df)
                )
            else:
                new_df = pd.DataFrame()
                logger.warning("no_new_dataset_using_empty_df")

            # Query recent feedback
            feedback_data = self.feedback_collector.get_recent_feedback(
                specialist_type=specialist_type,
                limit=1000
            )

            if feedback_data:
                # Convert feedback to dataset format
                feedback_df = self._convert_feedback_to_dataset(feedback_data)
                logger.info(
                    "feedback_data_converted",
                    rows=len(feedback_df)
                )

                # Merge
                merged_df = pd.concat([new_df, feedback_df], ignore_index=True)
            else:
                merged_df = new_df
                logger.warning("no_feedback_data_to_merge")

            # Save merged dataset
            merged_path = f"/data/training/{specialist_type}_specialist_merged_{int(time.time())}.parquet"
            merged_df.to_parquet(merged_path, index=False)

            logger.info(
                "datasets_merged_successfully",
                merged_path=merged_path,
                total_rows=len(merged_df)
            )

            return merged_path

        except Exception as e:
            logger.error(
                "merge_failed",
                error=str(e)
            )
            # Fallback to new dataset only
            return new_dataset_path if new_dataset_path else ""

    def _convert_feedback_to_dataset(self, feedback_data: List[Dict]) -> 'pd.DataFrame':
        """
        Converte dados de feedback para formato de dataset.

        Args:
            feedback_data: Lista de documentos de feedback

        Returns:
            DataFrame
        """
        import pandas as pd

        records = []
        for fb in feedback_data:
            # Extract cognitive plan and opinion from feedback context
            record = {
                'cognitive_plan': fb.get('context', {}).get('cognitive_plan', ''),
                'opinion': fb.get('context', {}).get('opinion', ''),
                'rating': fb.get('rating', 0.0),
                'feedback_text': fb.get('feedback_text', ''),
                'source': 'human_feedback'
            }
            records.append(record)

        return pd.DataFrame(records)

    def _trigger_training(self, specialist_type: str, dataset_path: str) -> str:
        """
        Trigger treinamento via RetrainingTrigger.

        Args:
            specialist_type: Tipo do specialist
            dataset_path: Path do dataset

        Returns:
            MLflow run ID
        """
        logger.info(
            "triggering_training",
            specialist_type=specialist_type,
            dataset_path=dataset_path
        )

        # Use RetrainingTrigger infrastructure
        run_id = self.retraining_trigger.trigger_retraining(
            specialist_type=specialist_type,
            dataset_path=dataset_path,
            promote_if_better=True
        )

        logger.info(
            "training_triggered",
            mlflow_run_id=run_id
        )

        return run_id

    def _monitor_training(self, mlflow_run_id: str, timeout: int = 3600) -> bool:
        """
        Monitora conclusão do treinamento.

        Args:
            mlflow_run_id: ID do run MLflow
            timeout: Timeout em segundos (default: 1h)

        Returns:
            True se sucesso, False se falha
        """
        logger.info(
            "monitoring_training",
            mlflow_run_id=mlflow_run_id
        )

        # Use RetrainingTrigger monitor
        status = self.retraining_trigger.monitor_run_status(
            run_id=mlflow_run_id,
            timeout=timeout
        )

        success = status.get('status') == 'FINISHED'

        logger.info(
            "training_monitoring_completed",
            mlflow_run_id=mlflow_run_id,
            success=success,
            status=status
        )

        return success

    def _compare_metrics(
        self,
        specialist_type: str,
        new_run_id: str
    ) -> tuple:
        """
        Compara métricas do novo modelo com baseline.

        Args:
            specialist_type: Tipo do specialist
            new_run_id: Run ID do novo modelo

        Returns:
            Tupla (new_metrics, baseline_metrics, improved)
        """
        import mlflow

        mlflow.set_tracking_uri(self.mlflow_tracking_uri)

        try:
            # Get new run metrics
            new_run = mlflow.get_run(new_run_id)
            new_metrics = new_run.data.metrics

            # Get baseline (current production model)
            report = self.performance_monitor.get_performance_report(specialist_type)
            baseline_metrics = None
            if report.mlflow_metrics:
                baseline_metrics = {
                    'precision': report.mlflow_metrics.precision,
                    'recall': report.mlflow_metrics.recall,
                    'f1_score': report.mlflow_metrics.f1_score
                }

            # Compare F1 scores
            improved = False
            if baseline_metrics:
                improved = new_metrics.get('f1_score', 0) > baseline_metrics.get('f1_score', 0)

            logger.info(
                "metrics_compared",
                new_f1=new_metrics.get('f1_score'),
                baseline_f1=baseline_metrics.get('f1_score') if baseline_metrics else None,
                improved=improved
            )

            return new_metrics, baseline_metrics, improved

        except Exception as e:
            logger.error(
                "metrics_comparison_failed",
                error=str(e)
            )
            return None, None, False

    def _send_notification(self, status: str, details: Dict):
        """
        Envia notificação via Slack/Email.

        Args:
            status: 'success', 'failed', 'warning'
            details: Detalhes da notificação
        """
        if 'slack' in self.notification_channels:
            self._send_slack_notification(status, details)

        if 'email' in self.notification_channels:
            self._send_email_notification(status, details)

    def _send_slack_notification(self, status: str, details: Dict):
        """Envia notificação via Slack."""
        try:
            import requests

            webhook_url = os.getenv('SLACK_WEBHOOK_URL')
            if not webhook_url:
                logger.warning("slack_webhook_url_not_configured")
                return

            # Build message
            emoji = {
                'success': ':white_check_mark:',
                'failed': ':x:',
                'warning': ':warning:'
            }.get(status, ':information_source:')

            text = f"{emoji} *Auto-Retrain {status.upper()}*\n"
            text += f"Specialist: `{details.get('specialist_type', 'N/A')}`\n"

            if status == 'success':
                text += f"Run ID: `{details.get('mlflow_run_id')}`\n"
                text += f"Improved: {details.get('improved', False)}\n"
            elif status == 'failed':
                text += f"Error: {details.get('error_message', 'Unknown')}\n"

            payload = {
                'text': text,
                'channel': os.getenv('SLACK_CHANNEL', '#ml-alerts')
            }

            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()

            logger.info("slack_notification_sent")

        except Exception as e:
            logger.error(
                "slack_notification_failed",
                error=str(e)
            )

    def _send_email_notification(self, status: str, details: Dict):
        """Envia notificação via Email."""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            smtp_host = os.getenv('SMTP_HOST')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_user = os.getenv('SMTP_USER')
            smtp_password = os.getenv('SMTP_PASSWORD')
            recipients = os.getenv('EMAIL_RECIPIENTS', '').split(',')

            if not all([smtp_host, smtp_user, smtp_password, recipients]):
                logger.warning("email_config_incomplete")
                return

            # Build email
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = f"Auto-Retrain {status.upper()} - {details.get('specialist_type', 'N/A')}"

            body = f"""
Auto-Retrain Status: {status.upper()}
Specialist: {details.get('specialist_type', 'N/A')}
Timestamp: {datetime.now().isoformat()}

"""
            if status == 'success':
                body += f"MLflow Run ID: {details.get('mlflow_run_id')}\n"
                body += f"Model Improved: {details.get('improved', False)}\n"
            elif status == 'failed':
                body += f"Error: {details.get('error_message', 'Unknown')}\n"

            msg.attach(MIMEText(body, 'plain'))

            # Send
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            logger.info("email_notification_sent")

        except Exception as e:
            logger.error(
                "email_notification_failed",
                error=str(e)
            )

    def _safe_export_metrics(self, result: Optional[RetrainResult]):
        """Chama exportação de métricas de forma defensiva."""
        try:
            if result is not None:
                self._export_metrics(result)
        except Exception as export_error:
            logger.error("metric_export_wrapper_failed", error=str(export_error))

    def _export_metrics(self, result: RetrainResult):
        """Exporta métricas para Prometheus."""
        try:
            from prometheus_client import CollectorRegistry, Counter, Gauge, push_to_gateway

            pushgateway_url = os.getenv('PROMETHEUS_PUSHGATEWAY_URL')
            if not pushgateway_url:
                logger.warning("pushgateway_url_not_configured")
                return

            registry = CollectorRegistry()

            # Auto-retrain triggered counter
            triggered_counter = Counter(
                'neural_hive_auto_retrain_triggered_total',
                'Total de auto-retrains triggered',
                ['specialist_type', 'status'],
                registry=registry
            )
            triggered_counter.labels(
                specialist_type=result.specialist_type,
                status='success' if result.success else 'failed'
            ).inc()

            # Duration gauge
            duration_gauge = Gauge(
                'neural_hive_auto_retrain_duration_seconds',
                'Duração do auto-retrain em segundos',
                ['specialist_type'],
                registry=registry
            )
            duration_gauge.labels(specialist_type=result.specialist_type).set(
                result.duration_seconds
            )

            # Success counter
            if result.success:
                success_counter = Counter(
                    'neural_hive_auto_retrain_success_total',
                    'Total de auto-retrains bem-sucedidos',
                    ['specialist_type', 'improved'],
                    registry=registry
                )
                success_counter.labels(
                    specialist_type=result.specialist_type,
                    improved=str(result.improved)
                ).inc()

            push_to_gateway(
                pushgateway_url,
                job='auto_retrain_orchestrator',
                registry=registry
            )

            logger.info("metrics_exported_to_prometheus")

        except Exception as e:
            logger.error(
                "prometheus_export_failed",
                error=str(e)
            )

    def cleanup_old_datasets(self, max_age_days: int = 90):
        """
        Remove datasets antigos.

        Args:
            max_age_days: Idade máxima em dias
        """
        try:
            data_dir = Path('/data/training')
            if not data_dir.exists():
                return

            cutoff_date = datetime.now() - timedelta(days=max_age_days)

            for file in data_dir.glob('*.parquet'):
                file_time = datetime.fromtimestamp(file.stat().st_mtime)
                if file_time < cutoff_date:
                    file.unlink()
                    logger.info(
                        "old_dataset_removed",
                        file=str(file),
                        age_days=(datetime.now() - file_time).days
                    )

        except Exception as e:
            logger.error(
                "cleanup_failed",
                error=str(e)
            )


def main():
    """CLI para execução do orquestrador."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Auto-Retrain Orchestrator'
    )
    parser.add_argument(
        '--specialist-type',
        help='Tipo do specialist (default: all)',
        default='all'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Forçar retreinamento mesmo se performance OK'
    )
    parser.add_argument(
        '--skip-dataset-generation',
        action='store_true',
        help='Usar datasets existentes'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simular sem executar'
    )
    parser.add_argument(
        '--notification-channels',
        default='slack',
        help='Canais de notificação separados por vírgula (slack,email)'
    )

    args = parser.parse_args()

    # Initialize orchestrator
    orchestrator = AutoRetrainOrchestrator(
        notification_channels=args.notification_channels.split(',')
    )

    # Determine specialists to process
    if args.specialist_type == 'all':
        specialist_types = ['technical', 'business', 'behavior', 'evolution', 'architecture']
    else:
        specialist_types = [args.specialist_type]

    # Process each specialist
    results = []
    for specialist_type in specialist_types:
        logger.info(
            "processing_specialist",
            specialist_type=specialist_type
        )

        result = orchestrator.check_performance_and_retrain(
            specialist_type=specialist_type,
            force=args.force,
            skip_dataset_generation=args.skip_dataset_generation,
            dry_run=args.dry_run
        )

        results.append(result)

        # Print result
        print(f"\n{'='*60}")
        print(f"Specialist: {result.specialist_type}")
        print(f"Success: {result.success}")
        if result.mlflow_run_id:
            print(f"Run ID: {result.mlflow_run_id}")
            print(f"Improved: {result.improved}")
        if result.error_message:
            print(f"Error: {result.error_message}")
        print(f"Duration: {result.duration_seconds:.2f}s")
        print(f"{'='*60}\n")

    # Cleanup old datasets
    logger.info("cleaning_up_old_datasets")
    orchestrator.cleanup_old_datasets()

    # Exit code
    all_success = all(r.success for r in results)
    sys.exit(0 if all_success else 1)


if __name__ == '__main__':
    main()
