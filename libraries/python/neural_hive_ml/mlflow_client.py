"""MLflow Client para Approval Models - Online Learning."""

from typing import Any, Dict, List, Optional
import logging
import mlflow
from mlflow.tracking import MlflowClient
from mlflow.exceptions import MlflowException

logger = logging.getLogger(__name__)


class MLflowClient:
    """
    Cliente MLflow especializado para Approval Models.

    Gerencia versionamento, registro e promoção de modelos de aprovação
    com suporte a feature importance e metadados específicos.
    """

    def __init__(
        self,
        tracking_uri: Optional[str] = None,
        experiment_prefix: str = "approval-models",
    ):
        """
        Inicializa o cliente MLflow.

        Args:
            tracking_uri: URI do servidor MLflow (ex: http://mlflow:5000)
            experiment_prefix: Prefixo para nomes de experimentos
        """
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)

        self.client = MlflowClient()
        self.experiment_prefix = experiment_prefix
        logger.info(f"MLflowClient inicializado com URI: {tracking_uri or 'default'}")

    def log_model(
        self,
        model: Any,
        version: str,
        metrics: Dict[str, float],
        params: Dict[str, Any],
        feature_importance: Optional[Dict[str, float]] = None,
        n_samples: int = 0,
        run_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Registra modelo no MLflow com metadados completos.

        Args:
            model: Modelo treinado (scikit-learn)
            version: Versão do modelo (ex: "v9")
            metrics: Métricas de avaliação (f1_score, accuracy, precision, recall)
            params: Hiperparâmetros do modelo
            feature_importance: Importância das features
            n_samples: Número de amostras usadas no treino
            run_id: Run ID existente (se None, cria novo run)
            tags: Tags adicionais

        Returns:
            Versão do modelo registrado

        Raises:
            Exception: Se falhar ao registrar modelo
        """
        try:
            model_name = f"approval-model-{version}"

            if run_id:
                # Usa run existente
                with mlflow.start_run(run_id=run_id):
                    return self._log_metrics_and_model(
                        model,
                        model_name,
                        metrics,
                        params,
                        feature_importance,
                        n_samples,
                        tags,
                    )
            else:
                # Cria novo run
                experiment_name = f"{self.experiment_prefix}-{version}"
                experiment = mlflow.get_experiment_by_name(experiment_name)

                if experiment is None:
                    experiment_id = mlflow.create_experiment(experiment_name)
                    logger.info(f"Criado experimento {experiment_name}")
                else:
                    experiment_id = experiment.experiment_id

                with mlflow.start_run(experiment_id=experiment_id):
                    return self._log_metrics_and_model(
                        model,
                        model_name,
                        metrics,
                        params,
                        feature_importance,
                        n_samples,
                        tags,
                    )

        except Exception as e:
            logger.error(f"Erro ao registrar modelo {version}: {e}")
            raise

    def _log_metrics_and_model(
        self,
        model: Any,
        model_name: str,
        metrics: Dict[str, float],
        params: Dict[str, Any],
        feature_importance: Optional[Dict[str, float]],
        n_samples: int,
        tags: Optional[Dict[str, str]],
    ) -> str:
        """Helper para logar métricas e modelo."""
        # Log params
        for param_name, param_value in params.items():
            mlflow.log_param(param_name, param_value)

        # Log metrics
        for metric_name, metric_value in metrics.items():
            mlflow.log_metric(metric_name, metric_value)

        # Log n_samples
        mlflow.log_metric("n_samples", n_samples)

        # Log feature importance como tags (para fácil acesso)
        if feature_importance:
            for feat_name, importance in feature_importance.items():
                mlflow.set_tag(f"feature_importance_{feat_name}", importance)

        # Log tags padrão
        default_tags = {"model_type": "approval", "n_samples": str(n_samples)}
        all_tags = {**default_tags, **(tags or {})}
        for tag_name, tag_value in all_tags.items():
            mlflow.set_tag(tag_name, tag_value)

        # Log model
        model_info = mlflow.sklearn.log_model(
            model, artifact_path="model", registered_model_name=model_name
        )

        registered_version = model_info.registered_model_version
        logger.info(f"Modelo {model_name} registrado como versão {registered_version}")
        return registered_version

    def register_model(self, model_name: str, run_id: str) -> None:
        """
        Registra modelo em run existente.

        Args:
            model_name: Nome do modelo
            run_id: ID do run MLflow
        """
        try:
            model_version = mlflow.register_model(
                artifact_uri=f"runs:/{run_id}/model", name=model_name
            )
            logger.info(f"Modelo {model_name} registrado como v{model_version.version}")
        except MlflowException as e:
            logger.error(f"Erro ao registrar modelo {model_name}: {e}")
            raise

    def get_model_version(
        self, model_name: str, stage: str = "Staging"
    ) -> Optional[Dict[str, Any]]:
        """
        Obtém metadados de versão específica do modelo.

        Args:
            model_name: Nome do modelo (ex: "approval-model-v9")
            stage: Estágio (Production, Staging, Archived)

        Returns:
            Dicionário com metadados ou None se não encontrado
        """
        try:
            versions = self.client.get_latest_versions(model_name, stages=[stage])

            if not versions:
                logger.warning(
                    f"Nenhuma versão encontrada para {model_name} em {stage}"
                )
                return None

            version = versions[0]
            run = self.client.get_run(version.run_id)

            # Extrai feature importance das tags
            feature_importance = {}
            for key, value in run.data.tags.items():
                if key.startswith("feature_importance_"):
                    feat_name = key.replace("feature_importance_", "")
                    feature_importance[feat_name] = float(value)

            return {
                "version": version.version,
                "stage": version.current_stage,
                "run_id": version.run_id,
                "creation_timestamp": version.creation_timestamp,
                "f1_score": run.data.metrics.get("f1_score"),
                "accuracy": run.data.metrics.get("accuracy"),
                "precision": run.data.metrics.get("precision"),
                "recall": run.data.metrics.get("recall"),
                "n_samples": run.data.metrics.get("n_samples", 0),
                "feature_importance": feature_importance,
                "metrics": dict(run.data.metrics),
                "params": dict(run.data.params),
                "tags": dict(run.data.tags),
            }

        except MlflowException as e:
            logger.error(f"Erro ao buscar versão de {model_name}: {e}")
            return None

    def promote_model(
        self,
        model_name: str,
        version: str,
        stage: str = "Production",
        archive_current: bool = True,
    ) -> None:
        """
        Promove modelo para estágio específico.

        Args:
            model_name: Nome do modelo
            version: Versão do modelo
            stage: Estágio de destino (Production, Staging, Archived)
            archive_current: Se True, arquiva versão atual no Production
        """
        try:
            # Se promovendo para Production, arquiva versão atual
            if archive_current and stage == "Production":
                current_versions = self.client.get_latest_versions(
                    model_name, stages=["Production"]
                )
                for current_version in current_versions:
                    if current_version.version != version:
                        logger.info(
                            f"Arquivando versão atual {current_version.version}"
                        )
                        self.client.transition_model_version_stage(
                            name=model_name,
                            version=current_version.version,
                            stage="Archived",
                        )

            # Promove nova versão
            self.client.transition_model_version_stage(
                name=model_name, version=version, stage=stage
            )

            logger.info(f"Modelo {model_name} v{version} promovido para {stage}")

        except MlflowException as e:
            logger.error(f"Erro ao promover modelo {model_name}: {e}")
            raise

    def list_models(self, filter_string: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista modelos registrados.

        Args:
            filter_string: Filtro MLflow (ex: "name like 'approval-model%'")

        Returns:
            Lista de modelos com metadados
        """
        try:
            models = self.client.search_registered_models(filter_string=filter_string)

            return [
                {
                    "name": model.name,
                    "creation_timestamp": model.creation_timestamp,
                    "last_updated_timestamp": model.last_updated_timestamp,
                    "description": model.description,
                    "latest_versions": [
                        {
                            "version": v.version,
                            "stage": v.current_stage,
                            "creation_timestamp": v.creation_timestamp,
                        }
                        for v in model.latest_versions
                    ],
                }
                for model in models
            ]

        except MlflowException as e:
            logger.error(f"Erro ao listar modelos: {e}")
            return []

    def get_latest_run_id(
        self, model_name: str, stage: str = "Staging"
    ) -> Optional[str]:
        """
        Obtém run_id da versão mais recente.

        Args:
            model_name: Nome do modelo
            stage: Estágio para buscar

        Returns:
            Run ID ou None se não encontrado
        """
        try:
            versions = self.client.get_latest_versions(model_name, stages=[stage])
            if versions:
                return versions[0].run_id
            return None
        except MlflowException:
            return None

    def delete_model(self, model_name: str, version: str) -> None:
        """
        Deleta versão específica do modelo.

        Args:
            model_name: Nome do modelo
            version: Versão a deletar
        """
        try:
            self.client.delete_model_version(name=model_name, version=version)
            logger.info(f"Modelo {model_name} v{version} deletado")
        except MlflowException as e:
            logger.error(f"Erro ao deletar modelo: {e}")
            raise

    def get_run_history(self, model_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Obtém histórico de runs de um modelo.

        Args:
            model_name: Nome do modelo (sem prefixo)
            limit: Número máximo de runs

        Returns:
            Lista de runs com métricas
        """
        try:
            experiment_name = f"{self.experiment_prefix}-{model_name}"
            experiment = mlflow.get_experiment_by_name(experiment_name)

            if not experiment:
                return []

            runs = self.client.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=["start_time DESC"],
                max_results=limit,
            )

            return [
                {
                    "run_id": run.info.run_id,
                    "start_time": run.info.start_time,
                    "status": run.info.status,
                    "metrics": run.data.metrics,
                    "params": run.data.params,
                }
                for run in runs
            ]

        except MlflowException as e:
            logger.error(f"Erro ao buscar histórico: {e}")
            return []
