from typing import Any, Dict, List, Optional

import structlog
import mlflow
from mlflow.tracking import MlflowClient as MLflowTrackingClient
from mlflow.entities import Metric, Param

from src.config.settings import get_settings

logger = structlog.get_logger()


class MLflowClient:
    """Cliente MLflow para tracking de experimentos e versionamento de políticas."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.client: Optional[MLflowTrackingClient] = None
        self.experiment_id: Optional[str] = None

    def connect(self):
        """Inicializar cliente MLflow."""
        try:
            mlflow.set_tracking_uri(self.settings.mlflow_tracking_uri)
            self.client = MLflowTrackingClient()

            # Criar ou obter experiment
            try:
                experiment = self.client.get_experiment_by_name(self.settings.mlflow_experiment_name)
                if experiment:
                    self.experiment_id = experiment.experiment_id
                else:
                    self.experiment_id = self.client.create_experiment(self.settings.mlflow_experiment_name)
            except Exception:
                self.experiment_id = self.client.create_experiment(self.settings.mlflow_experiment_name)

            logger.info(
                "mlflow_connected",
                tracking_uri=self.settings.mlflow_tracking_uri,
                experiment=self.settings.mlflow_experiment_name,
                experiment_id=self.experiment_id,
            )
        except Exception as e:
            logger.error("mlflow_connection_failed", error=str(e))
            raise

    def start_experiment_run(self, experiment_name: str, run_name: str, tags: Optional[Dict] = None) -> str:
        """Iniciar run de experimento."""
        try:
            run = self.client.create_run(experiment_id=self.experiment_id, run_name=run_name, tags=tags or {})

            logger.info("mlflow_run_started", run_id=run.info.run_id, run_name=run_name)
            return run.info.run_id
        except Exception as e:
            logger.error("mlflow_run_start_failed", run_name=run_name, error=str(e))
            raise

    def log_params(self, run_id: str, params: Dict[str, Any]):
        """Logar parâmetros do experimento."""
        try:
            for key, value in params.items():
                self.client.log_param(run_id, key, str(value))

            logger.debug("mlflow_params_logged", run_id=run_id, count=len(params))
        except Exception as e:
            logger.error("mlflow_params_log_failed", run_id=run_id, error=str(e))

    def log_metrics(self, run_id: str, metrics: Dict[str, float], step: Optional[int] = None):
        """Logar métricas."""
        try:
            for key, value in metrics.items():
                self.client.log_metric(run_id, key, value, step=step)

            logger.debug("mlflow_metrics_logged", run_id=run_id, count=len(metrics), step=step)
        except Exception as e:
            logger.error("mlflow_metrics_log_failed", run_id=run_id, error=str(e))

    def log_artifact(self, run_id: str, artifact_path: str, artifact: Any):
        """Logar artefato."""
        try:
            # Salvar artefato localmente temporariamente
            import json
            import tempfile
            import os

            with tempfile.TemporaryDirectory() as tmpdir:
                file_path = os.path.join(tmpdir, os.path.basename(artifact_path))

                # Serializar artefato
                with open(file_path, "w") as f:
                    if isinstance(artifact, dict):
                        json.dump(artifact, f, indent=2)
                    else:
                        f.write(str(artifact))

                # Fazer upload
                self.client.log_artifact(run_id, file_path, artifact_path=artifact_path)

            logger.debug("mlflow_artifact_logged", run_id=run_id, path=artifact_path)
        except Exception as e:
            logger.error("mlflow_artifact_log_failed", run_id=run_id, path=artifact_path, error=str(e))

    def end_run(self, run_id: str, status: str = "FINISHED"):
        """Finalizar run."""
        try:
            self.client.set_terminated(run_id, status)
            logger.info("mlflow_run_ended", run_id=run_id, status=status)
        except Exception as e:
            logger.error("mlflow_run_end_failed", run_id=run_id, error=str(e))

    def register_policy_version(self, policy_name: str, policy_config: Dict, version: str) -> bool:
        """Registrar versão de política no Model Registry."""
        try:
            # Criar run temporário para registrar política
            run_id = self.start_experiment_run(
                experiment_name=self.settings.mlflow_experiment_name,
                run_name=f"{policy_name}_v{version}",
                tags={"policy_name": policy_name, "version": version, "type": "policy"},
            )

            # Logar configuração da política
            self.log_params(run_id, policy_config)

            # Logar como artefato
            self.log_artifact(run_id, f"policies/{policy_name}", policy_config)

            # Finalizar run
            self.end_run(run_id, "FINISHED")

            logger.info("policy_registered", policy_name=policy_name, version=version, run_id=run_id)
            return True
        except Exception as e:
            logger.error("policy_registration_failed", policy_name=policy_name, version=version, error=str(e))
            return False

    def get_policy_version(self, policy_name: str, version: str) -> Optional[Dict]:
        """Recuperar versão de política."""
        try:
            # Buscar run com tags específicas
            runs = self.client.search_runs(
                experiment_ids=[self.experiment_id],
                filter_string=f"tags.policy_name = '{policy_name}' and tags.version = '{version}'",
                max_results=1,
            )

            if runs:
                run = runs[0]
                # Recuperar parâmetros como dict
                policy_config = {param.key: param.value for param in run.data.params}
                logger.info("policy_retrieved", policy_name=policy_name, version=version)
                return policy_config

            logger.warning("policy_not_found", policy_name=policy_name, version=version)
            return None
        except Exception as e:
            logger.error("policy_retrieval_failed", policy_name=policy_name, version=version, error=str(e))
            return None

    def compare_runs(self, run_ids: List[str], metric_names: List[str]) -> Dict[str, Dict[str, float]]:
        """Comparar runs de experimentos."""
        try:
            comparison = {}

            for run_id in run_ids:
                run = self.client.get_run(run_id)
                comparison[run_id] = {}

                for metric_name in metric_names:
                    metric = run.data.metrics.get(metric_name)
                    comparison[run_id][metric_name] = metric if metric else 0.0

            logger.info("runs_compared", run_count=len(run_ids), metric_count=len(metric_names))
            return comparison
        except Exception as e:
            logger.error("runs_comparison_failed", error=str(e))
            return {}

    def get_best_run(self, experiment_name: str, metric_name: str, maximize: bool = True) -> Optional[str]:
        """Obter melhor run por métrica."""
        try:
            # Buscar runs ordenados pela métrica
            order_by = [f"metrics.{metric_name} {'DESC' if maximize else 'ASC'}"]

            runs = self.client.search_runs(
                experiment_ids=[self.experiment_id], order_by=order_by, max_results=1
            )

            if runs:
                best_run = runs[0]
                logger.info(
                    "best_run_found",
                    run_id=best_run.info.run_id,
                    metric=metric_name,
                    value=best_run.data.metrics.get(metric_name),
                )
                return best_run.info.run_id

            return None
        except Exception as e:
            logger.error("best_run_search_failed", metric=metric_name, error=str(e))
            return None
