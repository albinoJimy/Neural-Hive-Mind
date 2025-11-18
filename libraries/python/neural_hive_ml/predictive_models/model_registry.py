"""Gerenciador unificado de modelos com MLflow."""

from typing import Any, Dict, List, Optional
import logging
import mlflow
from mlflow.tracking import MlflowClient
from datetime import datetime

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Gerenciador centralizado de modelos MLflow."""

    def __init__(self, tracking_uri: Optional[str] = None, experiment_prefix: str = "neural-hive-ml"):
        """
        Inicializa o registry de modelos.

        Args:
            tracking_uri: URI do servidor MLflow
            experiment_prefix: Prefixo para nomes de experimentos
        """
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)

        self.client = MlflowClient()
        self.experiment_prefix = experiment_prefix

    def save_model(
        self,
        model: Any,
        model_name: str,
        metrics: Dict[str, float],
        params: Dict[str, Any],
        tags: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Salva modelo no MLflow registry.

        Args:
            model: Modelo treinado
            model_name: Nome do modelo
            metrics: Métricas de avaliação
            params: Parâmetros de treinamento
            tags: Tags adicionais

        Returns:
            Versão do modelo salvo
        """
        try:
            experiment_name = f"{self.experiment_prefix}-{model_name}"
            experiment = mlflow.get_experiment_by_name(experiment_name)

            if experiment is None:
                experiment_id = mlflow.create_experiment(experiment_name)
            else:
                experiment_id = experiment.experiment_id

            with mlflow.start_run(experiment_id=experiment_id):
                # Log parameters
                for param_name, param_value in params.items():
                    mlflow.log_param(param_name, param_value)

                # Log metrics
                for metric_name, metric_value in metrics.items():
                    mlflow.log_metric(metric_name, metric_value)

                # Log tags
                default_tags = {
                    "training_date": datetime.now().isoformat(),
                    "model_type": model_name
                }
                all_tags = {**default_tags, **(tags or {})}
                for tag_name, tag_value in all_tags.items():
                    mlflow.set_tag(tag_name, tag_value)

                # Log model
                model_info = mlflow.sklearn.log_model(
                    model,
                    artifact_path="model",
                    registered_model_name=model_name
                )

                version = model_info.registered_model_version
                logger.info(f"Modelo {model_name} salvo com versão {version}")
                return version

        except Exception as e:
            logger.error(f"Erro ao salvar modelo {model_name}: {e}")
            raise

    def load_model(
        self,
        model_name: str,
        stage: str = "Production"
    ) -> Any:
        """
        Carrega modelo do MLflow registry.

        Args:
            model_name: Nome do modelo
            stage: Estágio (Production/Staging/None)

        Returns:
            Modelo carregado
        """
        try:
            model_uri = f"models:/{model_name}/{stage}"
            model = mlflow.sklearn.load_model(model_uri)
            logger.info(f"Modelo {model_name} carregado do estágio {stage}")
            return model

        except Exception as e:
            logger.warning(f"Erro ao carregar modelo {model_name} ({stage}): {e}")
            return None

    def promote_model(
        self,
        model_name: str,
        version: str,
        stage: str = "Production"
    ) -> None:
        """
        Promove modelo para estágio específico.

        Args:
            model_name: Nome do modelo
            version: Versão do modelo
            stage: Estágio de destino (Production/Staging/Archived)
        """
        try:
            # Archive current Production models
            if stage == "Production":
                current_versions = self.client.get_latest_versions(
                    model_name,
                    stages=["Production"]
                )
                for current_version in current_versions:
                    self.client.transition_model_version_stage(
                        name=model_name,
                        version=current_version.version,
                        stage="Archived"
                    )

            # Promote new version
            self.client.transition_model_version_stage(
                name=model_name,
                version=version,
                stage=stage
            )

            logger.info(f"Modelo {model_name} v{version} promovido para {stage}")

        except Exception as e:
            logger.error(f"Erro ao promover modelo {model_name}: {e}")
            raise

    def get_model_metadata(
        self,
        model_name: str,
        stage: str = "Production"
    ) -> Dict[str, Any]:
        """
        Obtém metadados do modelo.

        Args:
            model_name: Nome do modelo
            stage: Estágio do modelo

        Returns:
            Dicionário com metadados
        """
        try:
            versions = self.client.get_latest_versions(model_name, stages=[stage])

            if not versions:
                return {}

            version = versions[0]
            run = self.client.get_run(version.run_id)

            return {
                "version": version.version,
                "stage": version.current_stage,
                "creation_timestamp": version.creation_timestamp,
                "last_updated_timestamp": version.last_updated_timestamp,
                "metrics": run.data.metrics,
                "params": run.data.params,
                "tags": run.data.tags
            }

        except Exception as e:
            logger.error(f"Erro ao obter metadados de {model_name}: {e}")
            return {}

    def list_models(
        self,
        filter_string: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lista modelos registrados.

        Args:
            filter_string: Filtro para nomes de modelos

        Returns:
            Lista de modelos com metadados
        """
        try:
            models = self.client.search_registered_models(
                filter_string=filter_string
            )

            return [
                {
                    "name": model.name,
                    "creation_timestamp": model.creation_timestamp,
                    "last_updated_timestamp": model.last_updated_timestamp,
                    "description": model.description,
                    "latest_versions": [
                        {
                            "version": v.version,
                            "stage": v.current_stage
                        }
                        for v in model.latest_versions
                    ]
                }
                for model in models
            ]

        except Exception as e:
            logger.error(f"Erro ao listar modelos: {e}")
            return []

    def archive_model(
        self,
        model_name: str,
        version: str
    ) -> None:
        """
        Arquiva versão específica do modelo.

        Args:
            model_name: Nome do modelo
            version: Versão a arquivar
        """
        try:
            self.client.transition_model_version_stage(
                name=model_name,
                version=version,
                stage="Archived"
            )
            logger.info(f"Modelo {model_name} v{version} arquivado")

        except Exception as e:
            logger.error(f"Erro ao arquivar modelo {model_name}: {e}")
            raise
