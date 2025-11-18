"""
Model Registry para gerenciamento de modelos ML no MLflow.

Gerencia lifecycle de modelos Prophet/ARIMA (LoadPredictor) e políticas RL (SchedulingOptimizer).
"""

import asyncio
import logging
import pickle
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

import mlflow
from mlflow.tracking import MlflowClient as MLflowTrackingClient

logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Registry de modelos ML para optimizer-agents.

    Integra com MLflow para versionamento, promoção e retrieval de:
    - Modelos Prophet/ARIMA de previsão de carga
    - Q-tables de políticas de agendamento RL
    """

    def __init__(self, mlflow_client, config: Dict):
        """
        Args:
            mlflow_client: Cliente MLflow existente
            config: Configuração
        """
        self.mlflow_client = mlflow_client
        self.config = config

        # Experiment name específico para scheduling
        self.experiment_name = 'optimizer-agents-predictive-scheduling'

        # Cache em memória de modelos (TTL 1 hora)
        self._model_cache: Dict[str, Dict] = {}
        self._cache_ttl = config.get('ml_model_cache_ttl_seconds', 3600)

        self._initialized = False

    async def initialize(self) -> None:
        """Conecta ao MLflow e cria/obtém experiment."""
        if self._initialized:
            return

        logger.info("Inicializando ModelRegistry...")

        try:
            # MLflow tracking URI
            tracking_uri = self.config.get('mlflow_tracking_uri', 'http://mlflow.mlflow.svc.cluster.local:5000')
            mlflow.set_tracking_uri(tracking_uri)

            # Criar ou obter experiment
            try:
                experiment = mlflow.get_experiment_by_name(self.experiment_name)
                if experiment:
                    self.experiment_id = experiment.experiment_id
                else:
                    self.experiment_id = mlflow.create_experiment(self.experiment_name)
            except Exception:
                self.experiment_id = mlflow.create_experiment(self.experiment_name)

            logger.info(f"ModelRegistry conectado: experiment_id={self.experiment_id}")
            self._initialized = True

        except Exception as e:
            logger.error(f"Erro ao inicializar ModelRegistry: {e}")
            raise

    async def save_load_model(
        self,
        model: Any,
        model_name: str,
        metrics: Dict[str, float],
        params: Dict[str, Any]
    ) -> str:
        """
        Salva modelo de previsão de carga (Prophet/ARIMA) no MLflow.

        Args:
            model: Modelo Prophet ou ARIMA treinado
            model_name: Nome do modelo (ex: 'load_predictor_60m')
            metrics: Métricas de avaliação (MAE, MAPE, RMSE)
            params: Parâmetros do modelo

        Returns:
            Run ID do MLflow
        """
        logger.info(f"Salvando modelo {model_name} no MLflow")

        try:
            # Iniciar run
            with mlflow.start_run(experiment_id=self.experiment_id, run_name=model_name) as run:
                run_id = run.info.run_id

                # Logar parâmetros
                mlflow.log_params(params)

                # Logar métricas
                mlflow.log_metrics(metrics)

                # Salvar modelo
                # Prophet tem suporte nativo no MLflow
                if hasattr(model, 'predict') and hasattr(model, 'history'):
                    # Modelo Prophet
                    mlflow.pyfunc.log_model(
                        artifact_path='model',
                        python_model=ProphetModelWrapper(model),
                        conda_env={
                            'dependencies': [
                                'python=3.11',
                                'prophet==1.1.5',
                                'pandas',
                                'numpy',
                            ]
                        }
                    )
                else:
                    # Modelo ARIMA ou outro
                    with tempfile.NamedTemporaryFile(mode='wb', suffix='.pkl', delete=False) as f:
                        pickle.dump(model, f)
                        mlflow.log_artifact(f.name, artifact_path='model')

                # Tags para facilitar busca
                mlflow.set_tags({
                    'model_type': 'load_predictor',
                    'framework': 'prophet' if hasattr(model, 'history') else 'arima',
                    'timestamp': datetime.utcnow().isoformat(),
                })

                # Auto-promoção se MAPE < 20%
                if metrics.get('mape', 100) < 20.0:
                    await self.promote_model(model_name, run_id, stage='Production')
                    logger.info(f"Modelo {model_name} promovido automaticamente (MAPE={metrics['mape']:.2f}%)")

                logger.info(f"Modelo {model_name} salvo: run_id={run_id}, MAPE={metrics.get('mape', 0):.2f}%")
                return run_id

        except Exception as e:
            logger.error(f"Erro ao salvar modelo {model_name}: {e}")
            raise

    async def load_load_model(
        self,
        model_name: str,
        stage: str = 'Production'
    ) -> Optional[Dict]:
        """
        Carrega modelo de previsão de carga do MLflow.

        Args:
            model_name: Nome do modelo
            stage: Stage do modelo ('Production', 'Staging', etc)

        Returns:
            Dict com 'model', 'metrics', 'params', 'run_id'
        """
        # Verificar cache
        cache_key = f"{model_name}:{stage}"
        cached = self._get_from_cache(cache_key)
        if cached:
            logger.debug(f"Modelo {model_name} recuperado do cache")
            return cached

        logger.info(f"Carregando modelo {model_name} (stage={stage})")

        try:
            # Buscar runs com tag model_type=load_predictor e ordenar por timestamp
            client = MLflowTrackingClient()
            runs = client.search_runs(
                experiment_ids=[self.experiment_id],
                filter_string=f"tags.model_type = 'load_predictor' and run_name = '{model_name}'",
                order_by=['start_time DESC'],
                max_results=1
            )

            if not runs:
                logger.warning(f"Modelo {model_name} não encontrado")
                return None

            run = runs[0]
            run_id = run.info.run_id

            # Recuperar artefato do modelo
            artifact_uri = f"runs:/{run_id}/model"

            try:
                # Tentar carregar como pyfunc (Prophet)
                pyfunc_model = mlflow.pyfunc.load_model(artifact_uri)
                # Extrair modelo Prophet nativo do wrapper
                if hasattr(pyfunc_model, '_model_impl') and hasattr(pyfunc_model._model_impl, 'python_model'):
                    model = pyfunc_model._model_impl.python_model.model
                else:
                    # Se não conseguir extrair, usar o pyfunc diretamente
                    model = pyfunc_model
            except Exception:
                # Fallback: carregar pickle
                artifact_path = client.download_artifacts(run_id, 'model')
                with open(artifact_path, 'rb') as f:
                    model = pickle.load(f)

            # Recuperar métricas e params
            metrics = {key: value for key, value in run.data.metrics.items()}
            params = {key: value for key, value in run.data.params.items()}

            result = {
                'model': model,
                'metrics': metrics,
                'params': params,
                'run_id': run_id,
            }

            # Cachear
            self._add_to_cache(cache_key, result)

            logger.info(f"Modelo {model_name} carregado: run_id={run_id}")
            return result

        except Exception as e:
            logger.error(f"Erro ao carregar modelo {model_name}: {e}")
            return None

    async def save_scheduling_policy(
        self,
        q_table: Dict,
        metrics: Dict[str, float]
    ) -> str:
        """
        Salva Q-table de política de agendamento no MLflow.

        Args:
            q_table: Q-table (state_hash -> {action -> Q-value})
            metrics: Métricas de performance (average_reward, etc)

        Returns:
            Run ID
        """
        logger.info("Salvando política de agendamento no MLflow")

        try:
            with mlflow.start_run(experiment_id=self.experiment_id, run_name='scheduling_policy') as run:
                run_id = run.info.run_id

                # Logar métricas
                mlflow.log_metrics(metrics)

                # Logar parâmetros
                mlflow.log_params({
                    'states_explored': len(q_table),
                    'updates_count': metrics.get('updates_count', 0),
                })

                # Serializar Q-table como pickle
                with tempfile.NamedTemporaryFile(mode='wb', suffix='.pkl', delete=False) as f:
                    pickle.dump(q_table, f)
                    mlflow.log_artifact(f.name, artifact_path='q_table')

                # Tags
                mlflow.set_tags({
                    'model_type': 'scheduling_policy',
                    'framework': 'q_learning',
                    'timestamp': datetime.utcnow().isoformat(),
                })

                # Auto-promoção se reward > 0.5
                if metrics.get('average_reward', 0) > 0.5:
                    await self.promote_model('scheduling_policy', run_id, stage='Production')
                    logger.info(f"Política promovida (reward={metrics['average_reward']:.3f})")

                logger.info(f"Política salva: run_id={run_id}, states={len(q_table)}")
                return run_id

        except Exception as e:
            logger.error(f"Erro ao salvar política: {e}")
            raise

    async def load_scheduling_policy(self) -> Optional[Dict]:
        """
        Carrega Q-table de política de agendamento do MLflow.

        Returns:
            Dict com 'q_table', 'metrics', 'run_id'
        """
        # Verificar cache
        cache_key = "scheduling_policy:Production"
        cached = self._get_from_cache(cache_key)
        if cached:
            logger.debug("Política recuperada do cache")
            return cached

        logger.info("Carregando política de agendamento")

        try:
            client = MLflowTrackingClient()
            runs = client.search_runs(
                experiment_ids=[self.experiment_id],
                filter_string="tags.model_type = 'scheduling_policy'",
                order_by=['start_time DESC'],
                max_results=1
            )

            if not runs:
                logger.warning("Política não encontrada")
                return None

            run = runs[0]
            run_id = run.info.run_id

            # Baixar artefato
            artifact_path = client.download_artifacts(run_id, 'q_table')

            # Deserializar Q-table
            with open(artifact_path, 'rb') as f:
                q_table = pickle.load(f)

            metrics = {key: value for key, value in run.data.metrics.items()}

            result = {
                'q_table': q_table,
                'metrics': metrics,
                'run_id': run_id,
            }

            # Cachear
            self._add_to_cache(cache_key, result)

            logger.info(f"Política carregada: run_id={run_id}, states={len(q_table)}")
            return result

        except Exception as e:
            logger.error(f"Erro ao carregar política: {e}")
            return None

    async def promote_model(
        self,
        model_name: str,
        run_id: str,
        stage: str = 'Production'
    ) -> bool:
        """
        Promove modelo para stage especificado.

        Args:
            model_name: Nome do modelo
            run_id: Run ID a promover
            stage: Stage alvo ('Staging', 'Production')

        Returns:
            True se sucesso
        """
        try:
            # MLflow Model Registry requer registered model
            # Para simplificar, usamos tags
            client = MLflowTrackingClient()
            client.set_tag(run_id, f'stage', stage)

            logger.info(f"Modelo {model_name} promovido para {stage}: run_id={run_id}")
            return True

        except Exception as e:
            logger.error(f"Erro ao promover modelo {model_name}: {e}")
            return False

    async def get_model_metadata(self, model_name: str) -> Optional[Dict]:
        """
        Obtém metadados do modelo.

        Args:
            model_name: Nome do modelo

        Returns:
            Dict com metrics, params, tags, run_id
        """
        try:
            client = MLflowTrackingClient()
            runs = client.search_runs(
                experiment_ids=[self.experiment_id],
                filter_string=f"run_name = '{model_name}'",
                order_by=['start_time DESC'],
                max_results=1
            )

            if not runs:
                return None

            run = runs[0]

            return {
                'run_id': run.info.run_id,
                'metrics': {k: v for k, v in run.data.metrics.items()},
                'params': {k: v for k, v in run.data.params.items()},
                'tags': {k: v for k, v in run.data.tags.items()},
                'start_time': run.info.start_time,
                'end_time': run.info.end_time,
            }

        except Exception as e:
            logger.error(f"Erro ao obter metadata de {model_name}: {e}")
            return None

    async def list_models(self, model_type: Optional[str] = None) -> List[Dict]:
        """
        Lista modelos registrados.

        Args:
            model_type: Filtrar por tipo ('load_predictor', 'scheduling_policy')

        Returns:
            Lista de dicts com info dos modelos
        """
        try:
            client = MLflowTrackingClient()

            filter_str = f"tags.model_type = '{model_type}'" if model_type else ""

            runs = client.search_runs(
                experiment_ids=[self.experiment_id],
                filter_string=filter_str,
                order_by=['start_time DESC'],
                max_results=100
            )

            models = []
            for run in runs:
                models.append({
                    'run_id': run.info.run_id,
                    'run_name': run.data.tags.get('mlflow.runName', 'unknown'),
                    'model_type': run.data.tags.get('model_type', 'unknown'),
                    'framework': run.data.tags.get('framework', 'unknown'),
                    'metrics': {k: v for k, v in run.data.metrics.items()},
                    'start_time': datetime.fromtimestamp(run.info.start_time / 1000).isoformat(),
                })

            logger.info(f"Listados {len(models)} modelos (type={model_type})")
            return models

        except Exception as e:
            logger.error(f"Erro ao listar modelos: {e}")
            return []

    def _get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Recupera modelo do cache em memória."""
        if cache_key in self._model_cache:
            cached = self._model_cache[cache_key]
            # Verificar TTL
            age = (datetime.utcnow() - cached['cached_at']).total_seconds()
            if age < self._cache_ttl:
                return cached['data']
            else:
                # Expirado
                del self._model_cache[cache_key]
        return None

    def _add_to_cache(self, cache_key: str, data: Dict) -> None:
        """Adiciona modelo ao cache."""
        self._model_cache[cache_key] = {
            'data': data,
            'cached_at': datetime.utcnow(),
        }


class ProphetModelWrapper(mlflow.pyfunc.PythonModel):
    """
    Wrapper para modelos Prophet para serialização no MLflow.
    """

    def __init__(self, prophet_model):
        self.model = prophet_model

    def predict(self, context, model_input):
        """
        Predição usando Prophet.

        Args:
            model_input: DataFrame com coluna 'ds'

        Returns:
            Previsões
        """
        return self.model.predict(model_input)
