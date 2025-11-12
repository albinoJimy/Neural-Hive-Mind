"""
Cliente wrapper para integração com MLflow.
"""

import mlflow
from mlflow.tracking import MlflowClient as MLflowTrackingClient
from typing import Any, Dict, Optional
from datetime import datetime
import time
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from circuitbreaker import CircuitBreaker, CircuitBreakerError
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from .config import SpecialistConfig

logger = structlog.get_logger()


class MLflowClient:
    """Cliente para gerenciar modelos e experimentos no MLflow."""

    def __init__(self, config: SpecialistConfig, metrics=None):
        self.config = config
        self._client: Optional[MLflowTrackingClient] = None
        self._model_cache = {}
        self._enabled = False
        self._experiment_id = None
        self._metrics = metrics
        self._circuit_breaker_state = 'closed'
        self._was_open = False
        self.used_expired_cache_recently = False

        # Initialize circuit breaker state in metrics
        if metrics:
            metrics.set_circuit_breaker_state('mlflow', 'closed')

        # Initialize circuit breakers conditionally
        self._load_model_breaker = None
        self._experiment_breaker = None
        if config.enable_circuit_breaker:
            self._load_model_breaker = CircuitBreaker(
                failure_threshold=config.circuit_breaker_failure_threshold,
                recovery_timeout=config.circuit_breaker_recovery_timeout,
                expected_exception=Exception,
                name='mlflow_load_model'
            )
            self._experiment_breaker = CircuitBreaker(
                failure_threshold=config.circuit_breaker_failure_threshold,
                recovery_timeout=config.circuit_breaker_recovery_timeout,
                expected_exception=Exception,
                name='mlflow_get_or_create_experiment'
            )

        # Get tracer if available
        self.tracer = trace.get_tracer(__name__)

        # Tentar inicializar conexão com MLflow
        self._bootstrap()

    @property
    def client(self) -> MLflowTrackingClient:
        """Lazy initialization do cliente MLflow."""
        if self._client is None:
            self._client = MLflowTrackingClient(tracking_uri=self.config.mlflow_tracking_uri)
        return self._client

    def _get_or_create_experiment(self, experiment_name: str) -> str:
        """Obtém ou cria um experimento MLflow com circuit breaker e retry."""
        if self.config.enable_circuit_breaker and self._experiment_breaker:
            return self._experiment_breaker.call(self._get_or_create_experiment_impl, experiment_name)
        else:
            return self._get_or_create_experiment_impl(experiment_name)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _get_or_create_experiment_impl(self, experiment_name: str) -> str:
        """Implementação interna de _get_or_create_experiment com timeout."""
        def _create_experiment():
            try:
                experiment = self.client.get_experiment_by_name(experiment_name)
                if experiment is not None:
                    return experiment.experiment_id

                # Criar novo experimento
                experiment_id = self.client.create_experiment(experiment_name)
                logger.info(
                    "Created new MLflow experiment",
                    experiment_name=experiment_name,
                    experiment_id=experiment_id
                )
                return experiment_id
            except Exception as e:
                if self._metrics:
                    self._metrics.increment_circuit_breaker_failure('mlflow', type(e).__name__)
                logger.error(
                    "Failed to get or create experiment",
                    experiment_name=experiment_name,
                    error=str(e)
                )
                raise

        # Executar com timeout de 5 segundos
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_create_experiment)
            try:
                result = future.result(timeout=5.0)

                # Check if recovering from open state
                if self._was_open:
                    if self._metrics:
                        self._metrics.increment_circuit_breaker_success_after_halfopen('mlflow')
                    self._circuit_breaker_state = 'closed'
                    if self._metrics:
                        self._metrics.set_circuit_breaker_state('mlflow', 'closed')
                    self._was_open = False
                    logger.info("Circuit breaker recovered to closed state", client='mlflow')

                return result
            except FuturesTimeoutError:
                if self._metrics:
                    self._metrics.increment_circuit_breaker_failure('mlflow', 'TimeoutError')
                logger.warning(
                    "MLflow experiment creation timed out after 5 seconds",
                    experiment_name=experiment_name
                )
                raise TimeoutError("MLflow operation timed out")

    def _on_circuit_breaker_state_change(self, old_state: str, new_state: str):
        """Callback para mudanças de estado do circuit breaker."""
        if self._metrics:
            self._metrics.set_circuit_breaker_state('mlflow', new_state)
            self._metrics.increment_circuit_breaker_transition('mlflow', old_state, new_state)

        logger.info(
            "Circuit breaker state changed",
            client='mlflow',
            old_state=old_state,
            new_state=new_state
        )

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Verifica se o cache é válido baseado no TTL."""
        if cache_key not in self._model_cache:
            return False

        cached_entry = self._model_cache[cache_key]
        if 'timestamp' not in cached_entry:
            return True  # Cache antigo sem timestamp

        elapsed = time.time() - cached_entry['timestamp']
        return elapsed < self.config.mlflow_cache_ttl_seconds

    def load_model(self, model_name: str, stage: str = "Production") -> Any:
        """
        Carrega modelo do registry.

        Args:
            model_name: Nome do modelo registrado
            stage: Stage do modelo (Production, Staging, Archived, None)

        Returns:
            Modelo carregado (sklearn, pytorch, etc.)
        """
        if self.config.enable_circuit_breaker and self._load_model_breaker:
            return self._load_model_breaker.call(self.load_model_impl, model_name, stage)
        else:
            return self.load_model_impl(model_name, stage)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def load_model_impl(self, model_name: str, stage: str = "Production") -> Any:
        """
        Internal implementation of load_model.

        Args:
            model_name: Nome do modelo registrado
            stage: Stage do modelo (Production, Staging, Archived, None)

        Returns:
            Modelo carregado (sklearn, pytorch, etc.)
        """
        cache_key = f"{model_name}:{stage}"

        with self.tracer.start_as_current_span("mlflow.load_model") as span:
            span.set_attribute("mlflow.model.name", model_name)
            span.set_attribute("mlflow.model.stage", stage)
            span.set_attribute("mlflow.cache.hit", self._is_cache_valid(cache_key))

            try:
                # Verificar cache válido
                if self._is_cache_valid(cache_key):
                    logger.debug("Loading model from cache", model_name=model_name, stage=stage)
                    model = self._model_cache[cache_key]['model']

                    # Check if recovering from open state
                    if self._was_open:
                        if self._metrics:
                            self._metrics.increment_circuit_breaker_success_after_halfopen('mlflow')
                        self._circuit_breaker_state = 'closed'
                        if self._metrics:
                            self._metrics.set_circuit_breaker_state('mlflow', 'closed')
                        self._was_open = False
                        logger.info("Circuit breaker recovered to closed state", client='mlflow')

                    span.set_status(Status(StatusCode.OK))
                    return model

                logger.info("Loading model from MLflow", model_name=model_name, stage=stage)

                # Buscar versão do modelo no stage especificado
                model_uri = f"models:/{model_name}/{stage}"
                model = mlflow.pyfunc.load_model(model_uri)

                # Cachear modelo com timestamp
                self._model_cache[cache_key] = {
                    'model': model,
                    'timestamp': time.time()
                }

                # Obter metadados do modelo
                metadata = self.get_model_metadata(model_name, stage)
                if metadata:
                    span.set_attribute("mlflow.model.version", metadata.get('version', 'unknown'))
                    span.set_attribute("mlflow.model.run_id", metadata.get('run_id', ''))

                # Check if recovering from open state
                if self._was_open:
                    if self._metrics:
                        self._metrics.increment_circuit_breaker_success_after_halfopen('mlflow')
                    self._circuit_breaker_state = 'closed'
                    if self._metrics:
                        self._metrics.set_circuit_breaker_state('mlflow', 'closed')
                    self._was_open = False
                    logger.info("Circuit breaker recovered to closed state", client='mlflow')

                # Fresh model loaded, clear expired cache flag
                self.used_expired_cache_recently = False

                logger.info(
                    "Model loaded successfully",
                    model_name=model_name,
                    stage=stage
                )

                span.set_status(Status(StatusCode.OK))
                return model

            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))

                if self._metrics:
                    self._metrics.increment_circuit_breaker_failure('mlflow', type(e).__name__)

                logger.error(
                    "Failed to load model from MLflow",
                    model_name=model_name,
                    stage=stage,
                    error=str(e)
                )
                raise

    def log_evaluation(
        self,
        opinion: Dict[str, Any],
        plan_id: str,
        intent_id: str
    ):
        """
        Registra avaliação no MLflow.

        Args:
            opinion: Parecer do especialista
            plan_id: ID do plano avaliado
            intent_id: ID da intenção original
        """
        if self._experiment_id is None:
            logger.warning("No experiment set, skipping MLflow logging")
            return

        with self.tracer.start_as_current_span("mlflow.log_evaluation") as span:
            span.set_attribute("mlflow.plan.id", plan_id)
            span.set_attribute("mlflow.intent.id", intent_id)
            span.set_attribute("mlflow.confidence.score", opinion.get('confidence_score', 0.0))

            try:
                # Ensure mlflow global API points to the same tracking server
                mlflow.set_tracking_uri(self.config.mlflow_tracking_uri)

                with mlflow.start_run(experiment_id=self._experiment_id):
                    # Log params
                    mlflow.log_param("plan_id", plan_id)
                    mlflow.log_param("intent_id", intent_id)
                    mlflow.log_param("specialist_type", self.config.specialist_type)

                    # Log metrics
                    mlflow.log_metric("confidence_score", opinion['confidence_score'])
                    mlflow.log_metric("risk_score", opinion['risk_score'])

                    # Log tags
                    mlflow.set_tag("recommendation", opinion['recommendation'])

                    logger.debug(
                        "Evaluation logged to MLflow",
                        plan_id=plan_id,
                        confidence_score=opinion['confidence_score']
                    )

                span.set_status(Status(StatusCode.OK))

            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))

                logger.warning(
                    "Failed to log evaluation to MLflow",
                    plan_id=plan_id,
                    error=str(e)
                )

    def get_model_metadata(self, model_name: str, stage: str) -> Dict[str, Any]:
        """
        Obtém metadados do modelo.

        Args:
            model_name: Nome do modelo
            stage: Stage do modelo

        Returns:
            Dicionário com metadados
        """
        with self.tracer.start_as_current_span("mlflow.get_model_metadata") as span:
            span.set_attribute("mlflow.model.name", model_name)
            span.set_attribute("mlflow.model.stage", stage)

            try:
                # Buscar versões do modelo
                versions = self.client.search_model_versions(f"name='{model_name}'")

                # Filtrar por stage
                for version in versions:
                    if version.current_stage == stage:
                        metadata = {
                            'version': version.version,
                            'creation_timestamp': version.creation_timestamp,
                            'last_updated_timestamp': version.last_updated_timestamp,
                            'description': version.description,
                            'tags': version.tags,
                            'run_id': version.run_id
                        }
                        span.set_status(Status(StatusCode.OK))
                        return metadata

                logger.warning(
                    "No model version found for stage",
                    model_name=model_name,
                    stage=stage
                )
                span.set_status(Status(StatusCode.OK))
                return {}

            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))

                logger.error(
                    "Failed to get model metadata",
                    model_name=model_name,
                    stage=stage,
                    error=str(e)
                )
                return {}

    def get_last_model_update(self) -> Optional[str]:
        """
        Retorna timestamp da última atualização do modelo.

        Returns:
            ISO-8601 string se timestamp disponível, None caso contrário
        """
        try:
            metadata = self.get_model_metadata(
                self.config.mlflow_model_name,
                self.config.mlflow_model_stage
            )

            if metadata and 'last_updated_timestamp' in metadata:
                timestamp_ms = metadata['last_updated_timestamp']
                dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
                return dt.isoformat()

            return None

        except Exception as e:
            logger.warning(
                "Failed to get last model update",
                error=str(e)
            )
            return None

    def load_model_with_fallback(self, model_name: str, stage: str = "Production") -> Any:
        """
        Carrega modelo com fallback para cache expirado.

        Args:
            model_name: Nome do modelo registrado
            stage: Stage do modelo

        Returns:
            Modelo carregado ou None se falhar
        """
        try:
            return self.load_model(model_name, stage)
        except CircuitBreakerError:
            # Update circuit breaker state
            self._circuit_breaker_state = 'open'
            if self._metrics:
                self._metrics.set_circuit_breaker_state('mlflow', 'open')
                self._metrics.increment_circuit_breaker_failure('mlflow', 'CircuitBreakerError')
            self._was_open = True

            logger.warning(
                "Circuit breaker open, falling back to cached model",
                model_name=model_name,
                stage=stage
            )

            # Usar cache mesmo se expirado
            cache_key = f"{model_name}:{stage}"
            if cache_key in self._model_cache:
                if self._metrics:
                    self._metrics.increment_fallback_invocation('mlflow', 'cached_model')

                # Mark that we used expired cache
                self.used_expired_cache_recently = True

                logger.info("Using expired cached model", model_name=model_name, stage=stage)
                return self._model_cache[cache_key].get('model')

            logger.error("No cached model available", model_name=model_name, stage=stage)
            return None
        except Exception as e:
            logger.error(
                "Failed to load model with fallback",
                model_name=model_name,
                stage=stage,
                error=str(e)
            )
            return None

    def _bootstrap(self):
        """
        Inicializa e verifica conectividade com MLflow.
        Define _enabled=True se conectividade for bem-sucedida.
        """
        try:
            logger.info("Tentando inicializar conexão com MLflow", tracking_uri=self.config.mlflow_tracking_uri)

            # Tentar buscar experimentos para verificar conectividade
            self.client.search_experiments(max_results=1)

            # Se chegou aqui, MLflow está acessível
            self._enabled = True

            # Set experiment_id after successful connectivity
            self._experiment_id = self._get_or_create_experiment(self.config.mlflow_experiment_name)

            logger.info(
                "MLflow client habilitado com sucesso",
                tracking_uri=self.config.mlflow_tracking_uri,
                experiment_name=self.config.mlflow_experiment_name,
                experiment_id=self._experiment_id
            )
        except Exception as e:
            logger.warning(
                "MLflow client desabilitado - não disponível no ambiente",
                tracking_uri=self.config.mlflow_tracking_uri,
                error=str(e)
            )
            self._enabled = False

    def is_enabled(self) -> bool:
        """Retorna se MLflow está habilitado e disponível."""
        return self._enabled

    def is_connected(self) -> bool:
        """Verifica conectividade com MLflow."""
        try:
            # Tentar listar experiments
            self.client.search_experiments(max_results=1)
            return True
        except Exception as e:
            logger.warning("MLflow not connected", error=str(e))
            return False

    def get_circuit_breaker_state(self) -> str:
        """Retorna o estado atual do circuit breaker."""
        return self._circuit_breaker_state
