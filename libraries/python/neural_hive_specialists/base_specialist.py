"""
Classe base abstrata para todos os especialistas neurais.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import time
import json
import hashlib
import uuid
from datetime import datetime
from contextlib import nullcontext
import structlog
import numpy as np
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from .config import SpecialistConfig
from .mlflow_client import MLflowClient
from .ledger_client import LedgerClient
from .explainability_generator import ExplainabilityGenerator
from .metrics import SpecialistMetrics
from .feature_extraction import FeatureExtractor
from .semantic_pipeline import SemanticPipeline
from .feature_store import FeatureStore
from .opinion_cache import OpinionCache
from .compliance import ComplianceLayer
from pydantic import ValidationError
from .schemas import (
    CognitivePlanSchema,
    PlanValidationError,
    PlanVersionIncompatibleError,
    TaskDependencyError,
    is_version_compatible
)
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = structlog.get_logger()


class BaseSpecialist(ABC):
    """
    Classe base abstrata para especialistas neurais.

    Esta classe fornece a infraestrutura base para todos os especialistas,
    incluindo:
    - Validação de planos cognitivos
    - Inferência de modelo ML com fallback
    - Geração de explicabilidade
    - Cache de opinião (opcional)
    - Persistência no ledger
    - Métricas Prometheus

    Para especialistas que requerem cache obrigatório, use CachedSpecialist.

    Exemplo:
        class TechnicalSpecialist(BaseSpecialist):
            def _get_specialist_type(self) -> str:
                return 'technical'

            def _load_model(self) -> Any:
                return self.mlflow_client.load_model_with_fallback(...)

            def _evaluate_plan_internal(self, cognitive_plan, context):
                # Lógica de avaliação específica
                return {
                    'confidence_score': 0.9,
                    'risk_score': 0.1,
                    'recommendation': 'approve',
                    ...
                }
    """

    def __init__(self, config: SpecialistConfig):
        self.config = config
        self.specialist_type = self._get_specialist_type()
        self.version = config.specialist_version

        logger.info(
            "Initializing specialist",
            specialist_type=self.specialist_type,
            version=self.version,
            supported_plan_versions=config.supported_plan_versions
        )

        # Inicializar métricas primeiro
        self.metrics = SpecialistMetrics(config, self.specialist_type)

        # Inicializar componentes com referência de métricas
        try:
            self.mlflow_client = MLflowClient(config, metrics=self.metrics)
        except Exception as e:
            logger.warning(
                "MLflow client unavailable - continuing without ML models",
                error=str(e)
            )
            self.mlflow_client = None

        # Inicializar ledger respeitando flags enable_ledger e ledger_required
        if not config.enable_ledger:
            logger.info("Ledger disabled via configuration (enable_ledger=False)")
            self.ledger_client = None
        else:
            try:
                self.ledger_client = LedgerClient(config, metrics=self.metrics)
                logger.info("Ledger client initialized successfully")
            except Exception as e:
                if config.ledger_required:
                    logger.error(
                        "Ledger is required but unavailable - failing initialization",
                        error=str(e),
                        ledger_required=True
                    )
                    raise RuntimeError(f"Ledger required but unavailable: {e}")
                else:
                    logger.warning(
                        "Ledger client unavailable - continuing without ledger persistence",
                        error=str(e),
                        degraded_mode=True
                    )
                    self.ledger_client = None

        # Inicializar feature store
        try:
            self.feature_store = FeatureStore(
                mongodb_uri=config.mongodb_uri,
                mongodb_database=config.mongodb_database,
                redis_cluster_nodes=config.redis_cluster_nodes,
                redis_password=config.redis_password,
                redis_ssl_enabled=config.redis_ssl_enabled,
                cache_ttl_seconds=config.redis_cache_ttl
            )
            logger.info("Feature store initialized")
        except Exception as e:
            logger.warning("Feature store unavailable - continuing without persistence", error=str(e))
            self.feature_store = None

        # Inicializar opinion cache
        self.opinion_cache = None
        if config.opinion_cache_enabled and config.enable_caching:
            try:
                self.opinion_cache = OpinionCache(
                    redis_cluster_nodes=config.redis_cluster_nodes,
                    redis_password=config.redis_password,
                    redis_ssl_enabled=config.redis_ssl_enabled,
                    cache_ttl_seconds=config.opinion_cache_ttl_seconds,
                    key_prefix=config.opinion_cache_key_prefix,
                    specialist_type=self.specialist_type
                )
                logger.info("Opinion cache initialized")
            except Exception as e:
                logger.warning("Opinion cache unavailable - continuing without cache", error=str(e))
                self.opinion_cache = None

        # Inicializar feature extractor ANTES de explainability
        self.feature_extractor = FeatureExtractor(config={
            'ontology_path': config.ontology_path if hasattr(config, 'ontology_path') else None,
            'embeddings_model': config.embeddings_model if hasattr(config, 'embeddings_model') else 'paraphrase-multilingual-MiniLM-L12-v2',
            'embedding_cache_size': config.embedding_cache_size if hasattr(config, 'embedding_cache_size') else 1000,
            'embedding_batch_size': config.embedding_batch_size if hasattr(config, 'embedding_batch_size') else 32,
            'embedding_cache_enabled': config.embedding_cache_enabled if hasattr(config, 'embedding_cache_enabled') else True,
            'embedding_cache_ttl_seconds': config.embedding_cache_ttl_seconds if hasattr(config, 'embedding_cache_ttl_seconds') else None,
            'semantic_similarity_threshold': config.semantic_similarity_threshold if hasattr(config, 'semantic_similarity_threshold') else 0.7
        }, metrics=self.metrics)

        # Inicializar semantic pipeline (substitui heurísticas de string-match)
        self.semantic_pipeline = SemanticPipeline(
            config=config.__dict__ if hasattr(config, '__dict__') else config,
            feature_extractor=self.feature_extractor
        )

        # Passar feature_extractor para ExplainabilityGenerator
        self.explainability_gen = ExplainabilityGenerator(
            config,
            metrics=self.metrics,
            feature_extractor=self.feature_extractor
        )

        # Inicializar drift monitoring se habilitado
        self.drift_detector = None
        self.evidently_monitor = None
        if config.enable_drift_monitoring:
            try:
                from .drift_monitoring.evidently_monitor import EvidentlyMonitor
                from .drift_monitoring.drift_detector import DriftDetector
                from .drift_monitoring.drift_alerts import DriftAlerter

                # Construir EvidentlyMonitor com config dict contendo drift_reference_dataset_path
                self.evidently_monitor = EvidentlyMonitor({
                    'drift_reference_dataset_path': config.drift_reference_dataset_path
                })

                drift_alerter = DriftAlerter(config={})

                self.drift_detector = DriftDetector(
                    config={
                        'drift_detection_window_hours': config.drift_detection_window_hours,
                        'drift_threshold_psi': config.drift_threshold_psi,
                        'drift_check_interval_minutes': 60
                    },
                    evidently_monitor=self.evidently_monitor,
                    drift_alerter=drift_alerter,
                    ledger_client=self.ledger_client
                )

                # Iniciar monitoramento em background quando event loop estiver disponível
                try:
                    import asyncio
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.drift_detector.start_monitoring())
                    logger.info("Drift monitoring background task started")
                except RuntimeError:
                    logger.info("Async loop not available; drift checks will need to be triggered externally")

                logger.info("Drift monitoring initialized")
            except Exception as e:
                logger.warning("Drift monitoring unavailable", error=str(e))
                self.drift_detector = None
                self.evidently_monitor = None

        # Inicializar Compliance Layer (PII detection, encryption, audit)
        self.compliance_layer = None
        if config.enable_compliance_layer:
            try:
                self.compliance_layer = ComplianceLayer(
                    config=config,
                    specialist_type=self.specialist_type,
                    metrics=self.metrics
                )
                logger.info("ComplianceLayer initialized")
            except Exception as e:
                logger.error("Failed to initialize ComplianceLayer", error=str(e))
                # Continuar sem compliance layer (degradação graciosa)

        # Inicializar OpenTelemetry tracer
        self.tracer = None
        if config.enable_tracing:
            try:
                from neural_hive_observability import init_tracing, get_tracer
                from neural_hive_observability.config import ObservabilityConfig

                # Criar config de observabilidade
                obs_config = ObservabilityConfig(
                    service_name=config.service_name,
                    service_version=config.specialist_version,
                    neural_hive_component='specialist',
                    neural_hive_layer='evaluation',
                    neural_hive_domain=self.specialist_type,
                    otel_endpoint=config.otel_endpoint,
                    environment=config.environment,
                    trace_batch_size=config.trace_batch_size,
                    trace_export_timeout_ms=config.trace_export_timeout_ms
                )

                # Inicializar tracing
                init_tracing(obs_config)
                self.tracer = get_tracer()

                logger.info(
                    "OpenTelemetry tracing initialized",
                    specialist_type=self.specialist_type,
                    otel_endpoint=config.otel_endpoint,
                    sampling_rate=config.trace_sampling_rate
                )
            except Exception as e:
                logger.warning(
                    "Failed to initialize tracing - continuing without",
                    error=str(e),
                    specialist_type=self.specialist_type
                )
                self.tracer = None

        # Carregar modelo
        if self.tracer:
            with self.tracer.start_as_current_span("specialist.load_model") as span:
                span.set_attribute("model.name", config.mlflow_model_name)
                span.set_attribute("model.stage", config.mlflow_model_stage)
                try:
                    start = time.time()
                    self.model = self._load_model()
                    span.set_attribute("loading.time_ms", int((time.time() - start) * 1000))
                    span.set_attribute("model.version", self._get_model_version())
                    span.set_status(Status(StatusCode.OK))
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
        else:
            self.model = self._load_model()

        logger.info(
            "Specialist initialized successfully",
            specialist_type=self.specialist_type,
            model_loaded=self.model is not None,
            feature_extractor_ready=True,
            semantic_pipeline_ready=True,
            drift_monitoring_enabled=self.drift_detector is not None
        )

    @abstractmethod
    def _get_specialist_type(self) -> str:
        """Retorna tipo do especialista (business, technical, etc.)."""
        pass

    @abstractmethod
    def _load_model(self) -> Any:
        """
        Carrega modelo do MLflow ou inicializa heurísticas.

        Subclasses devem usar mlflow_client.load_model_with_fallback()
        ao invés de load_model() diretamente para resiliência.

        Exemplo:
            if self.mlflow_client:
                model = self.mlflow_client.load_model_with_fallback(
                    self.config.mlflow_model_name,
                    self.config.mlflow_model_stage
                )
                return model
            return None
        """
        pass

    @abstractmethod
    def _evaluate_plan_internal(
        self,
        cognitive_plan: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Lógica específica de avaliação do especialista.

        Deve retornar dicionário com:
        - confidence_score: float (0.0-1.0)
        - risk_score: float (0.0-1.0)
        - recommendation: str (approve, reject, review_required, conditional)
        - reasoning_summary: str
        - reasoning_factors: List[Dict]
        - mitigations: List[Dict] (opcional)
        - metadata: Dict (opcional)
        """
        pass

    def _predict_with_model(
        self,
        cognitive_plan: Dict[str, Any],
        timeout_ms: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Executa inferência de modelo com timeout e fallback.

        Args:
            cognitive_plan: Plano cognitivo validado
            timeout_ms: Timeout em milissegundos (usa config se None)

        Returns:
            Resultado da predição ou None se falhar
        """
        include_embeddings = self.model is not None
        if self.model is None:
            logger.debug("Model not available, skipping ML inference and embeddings")
            return None

        timeout_seconds = (timeout_ms or self.config.model_inference_timeout_ms) / 1000.0

        try:
            # Extrair features sob span dedicado
            plan_id = cognitive_plan.get('plan_id')
            if self.tracer:
                with self.tracer.start_as_current_span("specialist.extract_features") as span:
                    try:
                        start_time = time.time()
                        features = self.feature_extractor.extract_features(
                            cognitive_plan,
                            include_embeddings=include_embeddings
                        )
                        feature_vector = features['aggregated_features']
                        feature_extraction_time = time.time() - start_time

                        # Definir atributos do span
                        if plan_id:
                            span.set_attribute("plan.id", plan_id)
                        span.set_attribute("features.count", len(feature_vector) if hasattr(feature_vector, '__len__') else 0)
                        span.set_attribute("extraction.time_ms", int(feature_extraction_time * 1000))

                        logger.debug(
                            "Features extracted",
                            num_features=len(feature_vector),
                            extraction_time_ms=int(feature_extraction_time * 1000)
                        )

                        # Salvar features no feature store
                        if self.feature_store and plan_id:
                            try:
                                self.feature_store.save_features(plan_id, features)
                            except Exception as e:
                                logger.warning("Failed to save features to store", plan_id=plan_id, error=str(e))

                        # Registrar features para monitoramento de drift
                        if self.drift_detector:
                            try:
                                with self.tracer.start_as_current_span("specialist.drift_detection") as span:
                                    span.set_attribute("drift.threshold", getattr(self.drift_detector, "threshold_psi", None))
                                    span.set_attribute("drift.detected", False)
                                    span.set_attribute("drift.psi_score", 0.0)
                                    self.drift_detector.log_evaluation_features(features['aggregated_features'])
                                    span.set_status(Status(StatusCode.OK))
                            except Exception as e:
                                if 'span' in locals():
                                    span.record_exception(e)
                                    span.set_status(Status(StatusCode.ERROR, str(e)))
                                logger.warning("Failed to log features for drift monitoring", error=str(e))

                        span.set_status(Status(StatusCode.OK))
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise
            else:
                start_time = time.time()
                features = self.feature_extractor.extract_features(
                    cognitive_plan,
                    include_embeddings=include_embeddings
                )
                feature_vector = features['aggregated_features']
                feature_extraction_time = time.time() - start_time

                logger.debug(
                    "Features extracted",
                    num_features=len(feature_vector),
                    extraction_time_ms=int(feature_extraction_time * 1000)
                )

                # Salvar features no feature store
                if self.feature_store and plan_id:
                    try:
                        self.feature_store.save_features(plan_id, features)
                    except Exception as e:
                        logger.warning("Failed to save features to store", plan_id=plan_id, error=str(e))

                # Registrar features para monitoramento de drift
                if self.drift_detector:
                    try:
                        self.drift_detector.log_evaluation_features(features['aggregated_features'])
                    except Exception as e:
                        logger.warning("Failed to log features for drift monitoring", error=str(e))

            # Executar inferência com timeout
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

            def _run_inference():
                # Converter features para DataFrame com schema consistente
                import pandas as pd

                # Importar definições centralizadas de features
                try:
                    import sys
                    sys.path.insert(0, '/app/ml_pipelines')
                    from feature_store.feature_definitions import get_feature_names
                    feature_names = get_feature_names()
                except Exception as e:
                    logger.warning("Could not load feature names, using default order", error=str(e))
                    feature_names = None

                # Construir DataFrame com ordem estável de colunas
                if feature_names:
                    # Criar dicionário com valores padrão
                    feature_dict = {name: 0.0 for name in feature_names}

                    # Preencher com features extraídas (feature_vector é um dict)
                    if isinstance(feature_vector, dict):
                        for key, value in feature_vector.items():
                            if key in feature_dict:
                                feature_dict[key] = value
                    else:
                        # Se feature_vector for array, usar ordem das features
                        for i, value in enumerate(feature_vector):
                            if i < len(feature_names):
                                feature_dict[feature_names[i]] = value

                    feature_df = pd.DataFrame([feature_dict])
                else:
                    # Fallback: usar feature_vector diretamente
                    feature_df = pd.DataFrame([feature_vector])

                # Predição - tentar predict_proba para obter probabilidades calibradas
                try:
                    if hasattr(self.model, 'predict_proba'):
                        prediction = self.model.predict_proba(feature_df)
                        prediction_method = 'predict_proba'
                        logger.info(
                            "Using predict_proba for probabilistic inference",
                            plan_id=cognitive_plan.get('plan_id'),
                            model_version=self._get_model_version()
                        )
                    else:
                        # Fallback para predict se predict_proba não estiver disponível
                        prediction = self.model.predict(feature_df)
                        prediction_method = 'predict'
                        logger.warning(
                            "Model does not support predict_proba, falling back to predict",
                            plan_id=cognitive_plan.get('plan_id'),
                            model_version=self._get_model_version(),
                            model_type=type(self.model).__name__
                        )
                except Exception as e:
                    # Fallback se predict_proba falhar (captura qualquer tipo de erro)
                    logger.warning(
                        "predict_proba failed, falling back to predict",
                        plan_id=cognitive_plan.get('plan_id'),
                        error_type=type(e).__name__,
                        error=str(e)
                    )
                    prediction = self.model.predict(feature_df)
                    prediction_method = 'predict_fallback'

                # Log input/output para auditoria
                logger.info(
                    "Model inference completed",
                    plan_id=cognitive_plan.get('plan_id'),
                    model_version=self._get_model_version(),
                    prediction_method=prediction_method,
                    prediction=prediction.tolist() if hasattr(prediction, 'tolist') else prediction
                )

                return prediction, prediction_method

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_inference)
                try:
                    # Medir tempo de inferência
                    inference_start = time.time()
                    prediction, prediction_method = future.result(timeout=timeout_seconds)
                    inference_duration = time.time() - inference_start

                    # Registrar métrica de duração de inferência
                    model_version = self._get_model_version()
                    self.metrics.model_inference_duration.labels(
                        specialist_type=self.specialist_type,
                        model_version=model_version
                    ).observe(inference_duration)

                    # Registrar sucesso de inferência
                    self.metrics.model_inference_total.labels(
                        specialist_type=self.specialist_type,
                        status='success'
                    ).inc()

                    # Passar prediction_method nas features para parsing correto
                    features['prediction_method'] = prediction_method

                    # Converter predição para formato padronizado
                    result = self._parse_model_prediction(prediction, features)
                    result['metadata']['model_source'] = 'ml_model'
                    result['metadata']['model_version'] = model_version
                    result['metadata']['feature_extraction_time_ms'] = int(feature_extraction_time * 1000)
                    result['metadata']['inference_duration_ms'] = int(inference_duration * 1000)
                    result['metadata']['mlflow_model_signature_version'] = self.config.mlflow_model_signature_version
                    result['metadata']['prediction_method'] = prediction_method

                    # Adicionar feature_id se features foram persistidas
                    if self.feature_store and plan_id:
                        result['metadata']['feature_id'] = plan_id

                    return result

                except FuturesTimeoutError:
                    logger.warning(
                        "Model inference timed out",
                        timeout_seconds=timeout_seconds,
                        plan_id=cognitive_plan.get('plan_id')
                    )
                    self.metrics.model_inference_total.labels(
                        specialist_type=self.specialist_type,
                        status='timeout'
                    ).inc()
                    self.metrics.increment_model_timeout()
                    return None

        except Exception as e:
            logger.error(
                "Model inference failed",
                plan_id=cognitive_plan.get('plan_id'),
                error=str(e),
                exc_info=True
            )
            self.metrics.model_inference_total.labels(
                specialist_type=self.specialist_type,
                status='error'
            ).inc()
            self.metrics.increment_model_error()
            return None

    def _get_model_version(self) -> str:
        """Retorna versão do modelo carregado."""
        if self.mlflow_client:
            metadata = self.mlflow_client.get_model_metadata(
                self.config.mlflow_model_name,
                self.config.mlflow_model_stage
            )
            return metadata.get('version', 'unknown')
        return 'unknown'

    def _parse_model_prediction(self, prediction: Any, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converte predição do modelo para formato padronizado.

        Suporta múltiplos formatos de saída: numpy arrays, pandas DataFrames,
        listas, dicionários.

        Comportamento de parsing baseado em prediction_method (passado via features):
        - 'predict_proba': Extrai probabilidade da classe positiva (índice 1) de array
          2D com shape [1, n_classes]. confidence = P(classe_positiva), risk = 1 - confidence.
          Para classificação binária (n_classes=2), as probabilidades são complementares.
          Para multiclasse (n_classes>2), usa-se P(classe_positiva) como medida de confiança.
        - 'predict' ou outros: Trata array como formato legado [confidence, risk] onde
          coluna 0 é confidence e coluna 1 é risk (valores independentes).

        Subclasses devem sobrescrever se necessário.

        Args:
            prediction: Saída do modelo
            features: Features extraídas. Pode conter 'prediction_method' indicando
                      o método usado ('predict_proba', 'predict', 'predict_fallback').

        Returns:
            Dicionário com confidence_score, risk_score, calibrated (quando aplicável), etc.
        """
        confidence_score = 0.5
        risk_score = 0.5
        metadata = {}
        parsing_method = 'unknown'
        calibrated = False

        # Obter método de predição usado (passado por _predict_with_model)
        prediction_method = features.get('prediction_method', 'unknown')
        plan_id = features.get('plan_id', 'unknown')

        # Caso predict_proba: usar campo prediction_method para identificar explicitamente
        # Só processar como probabilidades se prediction_method indicar predict_proba
        if prediction_method == 'predict_proba':
            if isinstance(prediction, np.ndarray) and prediction.ndim == 2:
                if prediction.shape[0] == 1 and prediction.shape[1] >= 2:
                    num_classes = prediction.shape[1]

                    # Extrair probabilidade da classe positiva (índice 1)
                    # Para classificação binária ou multiclasse, índice 1 representa a classe positiva
                    raw_positive_prob = float(prediction[0][1])
                    raw_negative_prob = float(prediction[0][0])

                    # Normalizar probabilidades se necessário (classificação binária)
                    # Para multiclasse, não tentamos normalizar pois há mais de 2 classes
                    if num_classes == 2:
                        prob_sum = raw_positive_prob + raw_negative_prob
                        if prob_sum > 0 and abs(prob_sum - 1.0) > 0.01:
                            # Normalizar dividindo pela soma das duas classes
                            confidence_score = max(0.0, min(1.0, raw_positive_prob / prob_sum))
                            normalized_negative = max(0.0, min(1.0, raw_negative_prob / prob_sum))
                            logger.debug(
                                "Probabilidades binarias normalizadas",
                                plan_id=plan_id,
                                original_sum=prob_sum,
                                raw_positive=raw_positive_prob,
                                raw_negative=raw_negative_prob
                            )
                        else:
                            confidence_score = max(0.0, min(1.0, raw_positive_prob))
                            normalized_negative = max(0.0, min(1.0, raw_negative_prob))

                        metadata['negative_class_probability'] = normalized_negative
                    else:
                        # Multiclasse: usar P(classe_positiva) diretamente como confiança
                        # Não verificar se probabilidades somam 1.0 pois há mais classes
                        confidence_score = max(0.0, min(1.0, raw_positive_prob))
                        metadata['negative_class_probability'] = max(0.0, min(1.0, raw_negative_prob))
                        logger.info(
                            "Modelo multiclasse detectado, usando P(classe_positiva) como confianca",
                            plan_id=plan_id,
                            num_classes=num_classes,
                            positive_prob=confidence_score
                        )

                    # risk_score é sempre complementar a confidence_score
                    # Comportamento intencional: risk = 1 - confidence
                    risk_score = 1.0 - confidence_score

                    metadata['probabilities_used'] = True
                    metadata['positive_class_probability'] = confidence_score
                    metadata['num_classes'] = num_classes
                    metadata['calibrated'] = True
                    parsing_method = 'predict_proba'
                    calibrated = True

                    logger.info(
                        "Parsed predict_proba output",
                        plan_id=plan_id,
                        confidence_score=confidence_score,
                        risk_score=risk_score,
                        num_classes=num_classes,
                        parsing_method=parsing_method
                    )

                    metadata['parsing_method'] = parsing_method

                    return {
                        'confidence_score': confidence_score,
                        'risk_score': risk_score,
                        'calibrated': calibrated,
                        'recommendation': 'review_required',
                        'reasoning_summary': 'Avaliação baseada em modelo ML com probabilidades calibradas',
                        'reasoning_factors': [
                            {'factor': 'ml_confidence', 'score': confidence_score},
                            {'factor': 'ml_risk', 'score': risk_score}
                        ],
                        'metadata': metadata
                    }
                elif prediction.shape[0] != 1:
                    # Múltiplas amostras - inesperado para avaliação de plano único
                    logger.warning(
                        "predict_proba retornou multiplas amostras, formato inesperado",
                        shape=prediction.shape,
                        plan_id=plan_id,
                        prediction_method=prediction_method
                    )
            else:
                # prediction_method indica predict_proba mas formato não é reconhecido
                logger.warning(
                    "prediction_method indica predict_proba mas formato de saida nao reconhecido",
                    plan_id=plan_id,
                    prediction_method=prediction_method,
                    prediction_type=type(prediction).__name__,
                    prediction_shape=getattr(prediction, 'shape', None),
                    prediction_ndim=getattr(prediction, 'ndim', None)
                )

        try:
            # Caso 1: NumPy array (formato legado - coluna 0 = confidence, coluna 1 = risk)
            if isinstance(prediction, np.ndarray):
                if prediction.ndim == 2 and prediction.shape[1] >= 2:
                    confidence_score = float(prediction[0][0])
                    risk_score = float(prediction[0][1])
                    parsing_method = 'numpy_array_2d'
                elif prediction.ndim == 1 and len(prediction) >= 2:
                    confidence_score = float(prediction[0])
                    risk_score = float(prediction[1])
                    parsing_method = 'numpy_array_1d'
                else:
                    metadata['parse_warning'] = f'NumPy array shape não suportado: {prediction.shape}'
                    parsing_method = 'numpy_array_unsupported'
                    logger.warning("NumPy array com shape inesperado", shape=prediction.shape)

            # Caso 2: Pandas DataFrame
            elif hasattr(prediction, 'iloc'):  # Pandas DataFrame ou Series
                import pandas as pd
                if isinstance(prediction, pd.DataFrame):
                    if len(prediction.columns) >= 2:
                        confidence_score = float(prediction.iloc[0, 0])
                        risk_score = float(prediction.iloc[0, 1])
                        parsing_method = 'dataframe'
                    else:
                        metadata['parse_warning'] = f'DataFrame com colunas insuficientes: {len(prediction.columns)}'
                        parsing_method = 'dataframe_insufficient'
                elif isinstance(prediction, pd.Series):
                    if len(prediction) >= 2:
                        confidence_score = float(prediction.iloc[0])
                        risk_score = float(prediction.iloc[1])
                        parsing_method = 'series'
                    else:
                        metadata['parse_warning'] = f'Series com elementos insuficientes: {len(prediction)}'
                        parsing_method = 'series_insufficient'

            # Caso 3: Lista
            elif isinstance(prediction, list):
                if len(prediction) >= 2:
                    # Lista de listas
                    if isinstance(prediction[0], (list, tuple)):
                        confidence_score = float(prediction[0][0])
                        risk_score = float(prediction[0][1])
                        parsing_method = 'list_nested'
                    # Lista simples
                    else:
                        confidence_score = float(prediction[0])
                        risk_score = float(prediction[1])
                        parsing_method = 'list_flat'
                else:
                    metadata['parse_warning'] = f'Lista com elementos insuficientes: {len(prediction)}'
                    parsing_method = 'list_insufficient'

            # Caso 4: Dicionário
            elif isinstance(prediction, dict):
                confidence_score = float(prediction.get('confidence_score', prediction.get('confidence', 0.5)))
                risk_score = float(prediction.get('risk_score', prediction.get('risk', 0.5)))
                parsing_method = 'dict'

            # Caso 5: Formato desconhecido
            else:
                metadata['parse_warning'] = f'Formato de predição desconhecido: {type(prediction).__name__}'
                parsing_method = 'unknown'
                logger.warning(
                    "Formato de predição não reconhecido",
                    prediction_type=type(prediction).__name__
                )

        except Exception as e:
            prediction_shape = getattr(prediction, 'shape', None)
            logger.error(
                "Erro ao parsear predição do modelo",
                error=str(e),
                prediction_type=type(prediction).__name__,
                prediction_shape=prediction_shape
            )
            metadata['parse_error'] = str(e)
            parsing_method = 'error'

        # Garantir que scores estejam no range válido
        confidence_score = max(0.0, min(1.0, confidence_score))
        risk_score = max(0.0, min(1.0, risk_score))

        # Se houver mismatch de signature, logar nos metadados
        if 'parse_warning' in metadata:
            metadata['signature_mismatch'] = True

        metadata['parsing_method'] = parsing_method

        return {
            'confidence_score': confidence_score,
            'risk_score': risk_score,
            'calibrated': calibrated,
            'recommendation': 'review_required',
            'reasoning_summary': 'Avaliação baseada em modelo ML',
            'reasoning_factors': [
                {'factor': 'ml_confidence', 'score': confidence_score},
                {'factor': 'ml_risk', 'score': risk_score}
            ],
            'metadata': metadata
        }

    def _hash_plan(self, cognitive_plan: Dict[str, Any]) -> str:
        """
        Gera hash normalizado do plano cognitivo para cache.

        Remove campos voláteis (timestamps, IDs temporários) e ordena
        as chaves para garantir que planos semanticamente idênticos
        gerem o mesmo hash.

        Args:
            cognitive_plan: Plano cognitivo deserializado

        Returns:
            Hash SHA-256 hexadecimal do plano normalizado
        """
        # Criar cópia para não modificar original
        normalized_plan = cognitive_plan.copy()

        # Remover campos voláteis que não afetam a semântica do plano
        volatile_fields = ['plan_id', 'intent_id', 'created_at', 'updated_at', 'timestamp']
        for field in volatile_fields:
            normalized_plan.pop(field, None)

        # Normalizar tasks removendo campos voláteis
        if 'tasks' in normalized_plan:
            normalized_tasks = []
            for task in normalized_plan['tasks']:
                normalized_task = task.copy()
                # Remover campos voláteis de tasks
                task_volatile_fields = ['task_id', 'created_at', 'updated_at']
                for field in task_volatile_fields:
                    normalized_task.pop(field, None)
                normalized_tasks.append(normalized_task)
            normalized_plan['tasks'] = normalized_tasks

        # Serializar com chaves ordenadas para determinismo
        plan_json = json.dumps(normalized_plan, sort_keys=True, default=str)

        # Gerar hash SHA-256
        plan_hash = hashlib.sha256(plan_json.encode('utf-8')).hexdigest()

        return plan_hash

    def evaluate_plan(self, request) -> Dict[str, Any]:
        """
        Método público para avaliar plano (chamado pelo gRPC handler).

        Args:
            request: EvaluatePlanRequest protobuf message

        Returns:
            Dict representando EvaluatePlanResponse
        """
        start_time = time.time()
        plan_id = request.plan_id
        intent_id = request.intent_id

        # Criar root span usando context manager se tracing habilitado
        if self.tracer:
            return self._evaluate_plan_with_tracing(request, start_time)
        else:
            return self._evaluate_plan_impl(request, start_time, None)

    def _evaluate_plan_with_tracing(self, request, start_time: float) -> Dict[str, Any]:
        """Executa evaluate_plan com root span OpenTelemetry."""
        plan_id = request.plan_id
        intent_id = request.intent_id

        with self.tracer.start_as_current_span("specialist.evaluate_plan") as root_span:
            root_span.set_attribute("specialist.type", self.specialist_type)
            root_span.set_attribute("specialist.version", self.version)
            root_span.set_attribute("plan.id", plan_id)
            root_span.set_attribute("intent.id", intent_id)
            root_span.set_attribute("correlation.id", request.correlation_id)

            try:
                result = self._evaluate_plan_impl(request, start_time, root_span)

                # Adicionar atributos finais ao root span
                opinion = result.get('opinion', {})
                root_span.set_attribute("confidence.score", opinion.get('confidence_score', 0.0))
                root_span.set_attribute("risk.score", opinion.get('risk_score', 0.0))
                root_span.set_attribute("recommendation", opinion.get('recommendation', ''))
                root_span.set_attribute("opinion.id", result.get('opinion_id', ''))

                processing_time_ms = result.get('processing_time_ms', 0)
                root_span.set_attribute("processing.time_ms", processing_time_ms)

                # Adicionar model_version e explainability_method
                model_version = self._get_model_version()
                root_span.set_attribute("model.version", model_version)

                explainability_metadata = opinion.get('explainability', {})
                explain_method = explainability_metadata.get('method')
                if explain_method:
                    root_span.set_attribute("explainability.method", explain_method)

                root_span.set_status(Status(StatusCode.OK))
                return result

            except Exception as e:
                root_span.record_exception(e)
                root_span.set_status(Status(StatusCode.ERROR, str(e)))
                raise

    def _evaluate_plan_impl(self, request, start_time: float, root_span) -> Dict[str, Any]:
        """Implementação interna de evaluate_plan."""
        plan_id = request.plan_id
        intent_id = request.intent_id

        try:
            logger.info(
                "Starting plan evaluation",
                specialist_type=self.specialist_type,
                plan_id=plan_id,
                intent_id=intent_id,
                trace_id=request.trace_id
            )

            # Deserializar plano primeiro para poder normalizá-lo
            if self.tracer:
                with self.tracer.start_as_current_span("specialist.deserialize_plan") as span:
                    try:
                        cognitive_plan = self._deserialize_plan(request.cognitive_plan)
                        span.set_attribute("plan.version", cognitive_plan.get('version', 'unknown'))
                        tasks = cognitive_plan.get('tasks', [])
                        span.set_attribute("plan.tasks_count", len(tasks))
                        span.set_status(Status(StatusCode.OK))
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise
            else:
                cognitive_plan = self._deserialize_plan(request.cognitive_plan)

            # Sanitizar PII se compliance layer habilitado
            pii_metadata = {}
            if self.compliance_layer:
                try:
                    cognitive_plan, pii_metadata = self.compliance_layer.sanitize_cognitive_plan(cognitive_plan)
                    if pii_metadata.get('entities_detected'):
                        logger.info(
                            "PII detected and anonymized in cognitive plan",
                            plan_id=plan_id,
                            entities_count=len(pii_metadata['entities_detected'])
                        )
                except Exception as e:
                    logger.error("Failed to sanitize cognitive plan", error=str(e))
                    # Continuar com plano original

            # Verificar cache se habilitado
            cache_key = None
            if self.opinion_cache:
                try:
                    # Extrair tenant_id do context
                    context_dict = dict(request.context) if hasattr(request, 'context') else {}
                    tenant_id = context_dict.get('tenant_id', 'default')

                    # Serializar plano normalizado para bytes
                    plan_dict = cognitive_plan.copy()
                    plan_json = json.dumps(plan_dict, sort_keys=True, default=str)
                    plan_bytes = plan_json.encode('utf-8')

                    # Gerar cache key com tenant_id usando OpinionCache.generate_cache_key
                    cache_key = self.opinion_cache.generate_cache_key(
                        plan_bytes=plan_bytes,
                        specialist_type=self.specialist_type,
                        specialist_version=self.version,
                        tenant_id=tenant_id
                    )

                    if self.tracer:
                        with self.tracer.start_as_current_span("specialist.check_cache") as span:
                            try:
                                start_cache = time.time()
                                cached_opinion = self.opinion_cache.get_cached_opinion(cache_key)
                                cache_duration = time.time() - start_cache

                                self.metrics.observe_cache_operation_duration('get', cache_duration)

                                cache_hit = cached_opinion is not None
                                span.set_attribute("cache.hit", cache_hit)
                                span.set_attribute("cache.key", cache_key)
                                span.set_status(Status(StatusCode.OK))
                            except Exception as e:
                                span.record_exception(e)
                                span.set_status(Status(StatusCode.ERROR, str(e)))
                                raise
                    else:
                        start_cache = time.time()
                        cached_opinion = self.opinion_cache.get_cached_opinion(cache_key)
                        cache_duration = time.time() - start_cache

                        self.metrics.observe_cache_operation_duration('get', cache_duration)

                    if cached_opinion:
                        self.metrics.increment_cache_hit()
                        processing_time = time.time() - start_time

                        # Registrar métricas de avaliação para cache hit
                        self.metrics.observe_evaluation_duration(processing_time)
                        self.metrics.increment_evaluations(status='success')

                        # Extrair scores da opinião cacheada para métricas
                        opinion_data = cached_opinion.get('opinion', {})
                        if isinstance(opinion_data, dict):
                            confidence_score = opinion_data.get('confidence_score')
                            risk_score = opinion_data.get('risk_score')
                            recommendation = opinion_data.get('recommendation')

                            if confidence_score is not None:
                                self.metrics.observe_confidence_score(confidence_score)
                            if risk_score is not None:
                                self.metrics.observe_risk_score(risk_score)
                            if recommendation:
                                self.metrics.increment_recommendation(recommendation)

                        logger.info(
                            "Plan evaluation served from cache",
                            specialist_type=self.specialist_type,
                            plan_id=plan_id,
                            cache_key=cache_key,
                            processing_time_ms=int(processing_time * 1000)
                        )

                        # Retornar resposta cacheada com flag indicando cache hit
                        cached_opinion['cached'] = True
                        cached_opinion['cache_hit_at'] = datetime.utcnow().isoformat()

                        # Atualizar processing_time_ms para refletir tempo atual de cache hit
                        # Preservar tempo original em metadata
                        if 'processing_time_ms' in cached_opinion:
                            if 'opinion' not in cached_opinion:
                                cached_opinion['opinion'] = {}
                            if 'metadata' not in cached_opinion['opinion']:
                                cached_opinion['opinion']['metadata'] = {}

                            cached_opinion['opinion']['metadata']['original_processing_time_ms'] = cached_opinion['processing_time_ms']
                            cached_opinion['processing_time_ms'] = int(processing_time * 1000)

                        # Preservar evaluated_at original
                        if 'evaluated_at' in cached_opinion:
                            cached_opinion['opinion']['metadata']['evaluated_at_original'] = cached_opinion['evaluated_at']
                            cached_opinion['evaluated_at'] = datetime.utcnow().isoformat()

                        return cached_opinion
                    else:
                        self.metrics.increment_cache_miss()
                except Exception as e:
                    # Cache indisponível, continuar sem cache
                    logger.debug(
                        "Cache operation failed, continuing without cache",
                        error=str(e),
                        plan_id=plan_id
                    )
                    cache_key = None

            # Extrair contexto e tenant_id
            context = dict(request.context)
            tenant_id = context.get('tenant_id', 'default')

            # Extrair trace context do OpenTelemetry se disponível
            if self.tracer:
                current_span = trace.get_current_span()
                if current_span and current_span.get_span_context().is_valid:
                    context['trace_id'] = format(current_span.get_span_context().trace_id, "032x")
                    context['span_id'] = format(current_span.get_span_context().span_id, "016x")
                else:
                    # Fallback para valores do request
                    context['trace_id'] = request.trace_id
                    context['span_id'] = request.span_id
            else:
                # Sem tracing, usar valores do request
                context['trace_id'] = request.trace_id
                context['span_id'] = request.span_id

            context['correlation_id'] = request.correlation_id

            # Tentar inferência com modelo ML
            if self.tracer:
                with self.tracer.start_as_current_span("specialist.predict_with_model") as span:
                    try:
                        ml_result = self._predict_with_model(cognitive_plan)
                        if ml_result is not None:
                            span.set_attribute("inference.source", "ml_model")
                            span.set_attribute("confidence.score", ml_result.get('confidence_score', 0.0))
                            span.set_status(Status(StatusCode.OK))
                        else:
                            span.set_attribute("inference.source", "none")
                            span.set_status(Status(StatusCode.OK))
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        ml_result = None
            else:
                ml_result = self._predict_with_model(cognitive_plan)

            if ml_result is not None:
                # Usar resultado do modelo
                evaluation_result = ml_result
                logger.info(
                    "Using ML model prediction",
                    plan_id=plan_id,
                    confidence_score=evaluation_result['confidence_score']
                )
            else:
                # Registrar features para drift monitoring quando ML não executar
                if self.drift_detector:
                    try:
                        features = self.feature_extractor.extract_features(cognitive_plan)
                        self.drift_detector.log_evaluation_features(features['aggregated_features'])
                        logger.debug("Features logged for drift monitoring (fallback path)")
                    except Exception as e:
                        logger.warning("Failed to log features for drift monitoring on fallback", error=str(e))

                # Fallback baseado em feature flag
                if self.config.use_semantic_fallback:
                    # Fallback para semantic pipeline
                    logger.warning(
                        "Falling back to semantic pipeline",
                        plan_id=plan_id
                    )
                    if self.tracer:
                        with self.tracer.start_as_current_span("specialist.semantic_pipeline") as span:
                            try:
                                evaluation_result = self.semantic_pipeline.evaluate_plan(cognitive_plan, context)
                                span.set_attribute("inference.source", "semantic_pipeline")
                                span.set_attribute("confidence.score", evaluation_result.get('confidence_score', 0.0))
                                span.set_status(Status(StatusCode.OK))
                            except Exception as e:
                                span.record_exception(e)
                                span.set_status(Status(StatusCode.ERROR, str(e)))
                                raise
                    else:
                        evaluation_result = self.semantic_pipeline.evaluate_plan(cognitive_plan, context)

                    # Calibrar confiança (reduzir em 20% para sinalizar fallback de modelo ML)
                    evaluation_result['confidence_score'] *= 0.8
                    evaluation_result.setdefault('metadata', {})
                    evaluation_result['metadata']['model_source'] = 'semantic_pipeline'
                    evaluation_result['metadata']['fallback_reason'] = 'model_unavailable'
                else:
                    # Fallback para heurísticas internas do especialista
                    logger.warning(
                        "Falling back to specialist heuristics",
                        plan_id=plan_id
                    )
                    if self.tracer:
                        with self.tracer.start_as_current_span("specialist.heuristics") as span:
                            try:
                                evaluation_result = self._evaluate_plan_internal(cognitive_plan, context)
                                span.set_attribute("inference.source", "heuristics")
                                span.set_attribute("confidence.score", evaluation_result.get('confidence_score', 0.0))
                                span.set_status(Status(StatusCode.OK))
                            except Exception as e:
                                span.record_exception(e)
                                span.set_status(Status(StatusCode.ERROR, str(e)))
                                raise
                    else:
                        evaluation_result = self._evaluate_plan_internal(cognitive_plan, context)

                    # Calibrar confiança (reduzir em 20% para sinalizar fallback de modelo ML)
                    evaluation_result['confidence_score'] *= 0.8
                    evaluation_result.setdefault('metadata', {})
                    evaluation_result['metadata']['model_source'] = 'heuristics'
                    evaluation_result['metadata']['fallback_reason'] = 'model_unavailable'

            # Validar resultado
            if self.tracer:
                with self.tracer.start_as_current_span("specialist.validate_result") as span:
                    try:
                        self._validate_evaluation_result(evaluation_result)
                        span.set_status(Status(StatusCode.OK))
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise
            else:
                self._validate_evaluation_result(evaluation_result)

            # Gerar explicabilidade
            if self.tracer:
                with self.tracer.start_as_current_span("specialist.generate_explainability") as span:
                    try:
                        explainability_token, explainability_metadata = self.explainability_gen.generate(
                            evaluation_result,
                            cognitive_plan,
                            self.model
                        )
                        span.set_attribute("explainability.method", explainability_metadata.get('method', 'unknown'))
                        span.set_status(Status(StatusCode.OK))
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise
            else:
                explainability_token, explainability_metadata = self.explainability_gen.generate(
                    evaluation_result,
                    cognitive_plan,
                    self.model
                )

            # Construir parecer
            opinion = {
                'confidence_score': evaluation_result['confidence_score'],
                'risk_score': evaluation_result['risk_score'],
                'recommendation': evaluation_result['recommendation'],
                'reasoning_summary': evaluation_result['reasoning_summary'],
                'reasoning_factors': evaluation_result['reasoning_factors'],
                'explainability_token': explainability_token,
                'explainability': explainability_metadata,
                'mitigations': evaluation_result.get('mitigations', []),
                'metadata': evaluation_result.get('metadata', {})
            }

            # Calcular tempo de processamento real (antes de save_opinion)
            processing_time = time.time() - start_time
            processing_time_ms = int(processing_time * 1000)

            # Persistir no ledger com fallback (skip se flag definida no contexto)
            skip_ledger = context.get('skip_ledger', False)
            if skip_ledger:
                # Gerar opinion_id dummy para warmup/testes
                opinion_id = 'skip-ledger-' + str(uuid.uuid4())
                buffered = False
                logger.debug(
                    "Skipping ledger persistence per context flag",
                    plan_id=plan_id,
                    skip_ledger=True
                )
            else:
                # Passar processing_time_ms calculado para save_opinion com trace context
                if self.ledger_client is None:
                    logger.warning("Ledger unavailable - opinion not persisted", plan_id=plan_id)
                    opinion_id = 'ledger-unavailable-' + str(uuid.uuid4())
                    buffered = False
                elif self.tracer:
                    with self.tracer.start_as_current_span("specialist.persist_to_ledger") as span:
                        try:
                            opinion_id = self.ledger_client.save_opinion_with_fallback(
                                opinion,
                                plan_id,
                                intent_id,
                                self.specialist_type,
                                request.correlation_id,
                                specialist_version=self.version,
                                trace_id=context.get('trace_id'),
                                span_id=context.get('span_id'),
                                processing_time_ms=processing_time_ms,
                                tenant_id=tenant_id
                            )

                            # Check if opinion was buffered
                            buffered = self.ledger_client.was_last_save_buffered()
                            span.set_attribute("ledger.buffered", buffered)
                            span.set_attribute("opinion.id", opinion_id)
                            span.set_status(Status(StatusCode.OK))
                        except Exception as e:
                            span.record_exception(e)
                            span.set_status(Status(StatusCode.ERROR, str(e)))
                            raise
                else:
                    opinion_id = self.ledger_client.save_opinion_with_fallback(
                        opinion,
                        plan_id,
                        intent_id,
                        self.specialist_type,
                        request.correlation_id,
                        specialist_version=self.version,
                        trace_id=context.get('trace_id'),
                        span_id=context.get('span_id'),
                        processing_time_ms=processing_time_ms,
                        tenant_id=tenant_id
                    )

                    # Check if opinion was buffered
                    buffered = self.ledger_client.was_last_save_buffered()

                # Log se opinião foi bufferizada
                if buffered:
                    logger.warning(
                        "Opinion buffered due to ledger unavailability",
                        opinion_id=opinion_id,
                        plan_id=plan_id,
                        buffered=True
                    )
            skip_metrics = context.get('skip_metrics', False)
            if not skip_metrics:
                self.metrics.observe_evaluation_duration(processing_time)
                self.metrics.observe_confidence_score(opinion['confidence_score'])
                self.metrics.observe_risk_score(opinion['risk_score'])
                self.metrics.increment_recommendation(opinion['recommendation'])
                self.metrics.increment_evaluations(status='success')

            logger.info(
                "Plan evaluation completed successfully",
                specialist_type=self.specialist_type,
                plan_id=plan_id,
                opinion_id=opinion_id,
                confidence_score=opinion['confidence_score'],
                risk_score=opinion['risk_score'],
                recommendation=opinion['recommendation'],
                processing_time_ms=int(processing_time * 1000)
            )

            # Construir response
            response = {
                'opinion_id': opinion_id,
                'specialist_type': self.specialist_type,
                'specialist_version': self.version,
                'opinion': opinion,
                'processing_time_ms': int(processing_time * 1000),
                'evaluated_at': datetime.utcnow().isoformat(),
                'buffered': buffered
            }

            # Salvar no cache se habilitado
            if self.opinion_cache and cache_key:
                if self.tracer:
                    with self.tracer.start_as_current_span("specialist.cache_result") as span:
                        try:
                            start_cache = time.time()
                            cache_saved = self.opinion_cache.set_cached_opinion(cache_key, response)
                            cache_duration = time.time() - start_cache

                            self.metrics.observe_cache_operation_duration('set', cache_duration)

                            span.set_attribute("cache.saved", cache_saved)
                            span.set_attribute("cache.key", cache_key)
                            span.set_attribute("cache.ttl_seconds", self.config.opinion_cache_ttl_seconds)
                            span.set_status(Status(StatusCode.OK))

                            if cache_saved:
                                logger.debug(
                                    "Opinion cached for future requests",
                                    cache_key=cache_key,
                                    ttl_seconds=self.config.opinion_cache_ttl_seconds
                                )
                        except Exception as e:
                            span.record_exception(e)
                            span.set_status(Status(StatusCode.ERROR, str(e)))
                            # Não propagar erro de cache
                            logger.warning("Failed to cache opinion", error=str(e))
                else:
                    start_cache = time.time()
                    cache_saved = self.opinion_cache.set_cached_opinion(cache_key, response)
                    cache_duration = time.time() - start_cache

                    self.metrics.observe_cache_operation_duration('set', cache_duration)

                    if cache_saved:
                        logger.debug(
                            "Opinion cached for future requests",
                            cache_key=cache_key,
                            ttl_seconds=self.config.opinion_cache_ttl_seconds
                        )

            return response

        except Exception as e:
            processing_time = time.time() - start_time
            self.metrics.observe_evaluation_duration(processing_time)
            self.metrics.increment_evaluations(status='error')

            logger.error(
                "Plan evaluation failed",
                specialist_type=self.specialist_type,
                plan_id=plan_id,
                error=str(e),
                processing_time_ms=int(processing_time * 1000),
                exc_info=True
            )
            raise

    def _deserialize_plan(self, plan_bytes: bytes) -> Dict[str, Any]:
        """
        Deserializa e valida plano cognitivo.

        Valida o plano contra CognitivePlanSchema, incluindo verificação de
        compatibilidade de versão e dependências de tarefas.

        Raises:
            PlanValidationError: Se a validação do schema falhar
            PlanVersionIncompatibleError: Se a versão não for suportada
            ValueError: Para outros erros de formato
        """
        try:
            # Decodifica JSON
            plan_str = plan_bytes.decode('utf-8')
            plan_dict = json.loads(plan_str)

            # Extrai versão para verificação de compatibilidade
            plan_version = plan_dict.get('version')

            # Verifica compatibilidade de versão
            is_compatible, error_msg = is_version_compatible(
                plan_version,
                self.config.supported_plan_versions
            )

            if not is_compatible:
                logger.error(
                    "Versão do plano incompatível",
                    plan_version=plan_version,
                    supported_versions=self.config.supported_plan_versions,
                    error=error_msg
                )
                raise PlanVersionIncompatibleError(
                    f"Versão do plano {plan_version} não é suportada. "
                    f"Versões suportadas: {self.config.supported_plan_versions}. "
                    f"Detalhes: {error_msg}"
                )

            # Valida schema
            validated_plan = CognitivePlanSchema(**plan_dict)

            logger.debug(
                "Plano validado com sucesso",
                plan_id=validated_plan.plan_id,
                version=validated_plan.version,
                num_tasks=len(validated_plan.tasks)
            )

            return validated_plan.model_dump()

        except PlanVersionIncompatibleError:
            raise
        except ValidationError as e:
            logger.error(
                "Falha na validação Pydantic do plano",
                error=str(e),
                validation_errors=e.errors()
            )
            raise ValueError(f"Plano cognitivo com erros de validação: {e.errors()}")
        except PlanValidationError as e:
            logger.error(
                "Falha na validação do plano",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
        except json.JSONDecodeError as e:
            logger.error("Falha ao decodificar JSON", error=str(e))
            raise ValueError(f"Formato JSON inválido: {e}")
        except Exception as e:
            logger.error(
                "Falha ao deserializar plano cognitivo",
                error=str(e),
                error_type=type(e).__name__
            )
            raise ValueError(f"Formato de plano cognitivo inválido: {e}")

    def _validate_evaluation_result(self, result: Dict[str, Any]):
        """Valida estrutura do resultado de avaliação."""
        required_fields = [
            'confidence_score',
            'risk_score',
            'recommendation',
            'reasoning_summary',
            'reasoning_factors'
        ]

        for field in required_fields:
            if field not in result:
                raise ValueError(f"Missing required field in evaluation result: {field}")

        # Validar ranges
        if not (0.0 <= result['confidence_score'] <= 1.0):
            raise ValueError(f"Invalid confidence_score: {result['confidence_score']}")

        if not (0.0 <= result['risk_score'] <= 1.0):
            raise ValueError(f"Invalid risk_score: {result['risk_score']}")

        # Validar recomendação
        valid_recommendations = ['approve', 'reject', 'review_required', 'conditional']
        if result['recommendation'] not in valid_recommendations:
            raise ValueError(f"Invalid recommendation: {result['recommendation']}")

    async def evaluate_plans_batch(
        self,
        requests: list,
        max_concurrency: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Avalia múltiplos planos em paralelo com controle de concorrência.

        Args:
            requests: Lista de EvaluatePlanRequest protobuf messages
            max_concurrency: Concorrência máxima (usa config se None)

        Returns:
            Dict com resultados, estatísticas e erros
        """
        start_time = time.time()
        concurrency = max_concurrency or self.config.batch_max_concurrency

        logger.info(
            "Starting batch evaluation",
            specialist_type=self.specialist_type,
            batch_size=len(requests),
            max_concurrency=concurrency
        )

        # Criar semáforo para controlar concorrência
        semaphore = asyncio.Semaphore(concurrency)
        loop = asyncio.get_event_loop()

        async def evaluate_with_semaphore(request):
            async with semaphore:
                # Executar evaluate_plan em thread pool padrão (é síncrono)
                # Usando loop.run_in_executor(None, ...) para usar thread pool padrão
                try:
                    result = await loop.run_in_executor(
                        None,  # Usa thread pool padrão do loop
                        self.evaluate_plan,
                        request
                    )
                    return {'success': True, 'result': result, 'plan_id': request.plan_id}
                except Exception as e:
                    logger.error(
                        "Batch evaluation failed for plan",
                        plan_id=request.plan_id,
                        error=str(e)
                    )
                    return {'success': False, 'error': str(e), 'plan_id': request.plan_id}

        # Executar todas as avaliações em paralelo
        tasks = [evaluate_with_semaphore(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Separar sucessos e falhas
        successful = [r['result'] for r in results if isinstance(r, dict) and r.get('success')]
        failed = [r for r in results if isinstance(r, dict) and not r.get('success')]
        exceptions = [r for r in results if isinstance(r, Exception)]

        # Calcular estatísticas
        duration = time.time() - start_time
        success_rate = len(successful) / len(requests) if requests else 0

        # Registrar métricas
        self.metrics.observe_batch_evaluation(
            total=len(requests),
            successful=len(successful),
            failed=len(failed) + len(exceptions),
            duration=duration
        )

        logger.info(
            "Batch evaluation completed",
            specialist_type=self.specialist_type,
            total=len(requests),
            successful=len(successful),
            failed=len(failed) + len(exceptions),
            success_rate=success_rate,
            duration_seconds=duration
        )

        return {
            'successful': successful,
            'failed': failed,
            'exceptions': [str(e) for e in exceptions],
            'statistics': {
                'total': len(requests),
                'successful': len(successful),
                'failed': len(failed) + len(exceptions),
                'success_rate': success_rate,
                'duration_seconds': duration,
                'avg_duration_per_plan_ms': int((duration / len(requests)) * 1000) if requests else 0
            }
        }

    def warmup(self) -> Dict[str, Any]:
        """
        Pre-carrega modelo e executa inferência dummy para eliminar cold start.

        Returns:
            Dict com estatísticas de warmup
        """
        start_time = time.time()
        span_context = self.tracer.start_as_current_span("specialist.warmup") if self.tracer else nullcontext()

        logger.info(
            "Starting specialist warmup",
            specialist_type=self.specialist_type,
            version=self.version
        )

        dummy_plan = None
        with span_context as span:
            try:
                # 1. Garantir que modelo está carregado
                if self.model is None:
                    logger.info("Loading model during warmup")
                    self.model = self._load_model()

                # 2. Criar plano dummy
                dummy_plan = self._create_dummy_plan()

                # 3. Executar avaliação dummy (sem persistência no ledger e sem métricas)
                logger.info("Executing dummy evaluation for warmup")
                dummy_request = type('Request', (), {
                    'plan_id': 'warmup-dummy',
                    'intent_id': 'warmup-intent',
                    'cognitive_plan': json.dumps(dummy_plan).encode('utf-8'),
                    'trace_id': 'warmup-trace',
                    'span_id': 'warmup-span',
                    'correlation_id': 'warmup-correlation',
                    'context': {'skip_ledger': True, 'skip_metrics': True}
                })

                _ = self.evaluate_plan(dummy_request)

                # 4. Calcular duração
                duration = time.time() - start_time

                # 5. Registrar métricas
                self.metrics.observe_warmup_duration(duration, 'success')

                if span:
                    span.set_attribute("warmup.success", True)
                    span.set_attribute("warmup.time_ms", int(duration * 1000))
                    span.set_attribute("warmup.dummy_plan_id", dummy_plan.get('plan_id'))
                    span.set_status(Status(StatusCode.OK))

                logger.info(
                    "Specialist warmup completed successfully",
                    specialist_type=self.specialist_type,
                    duration_seconds=duration,
                    model_loaded=self.model is not None
                )

                return {
                    'status': 'success',
                    'duration_seconds': duration,
                    'model_loaded': self.model is not None,
                    'cache_ready': self.opinion_cache is not None and self.opinion_cache.is_connected()
                }

            except Exception as e:
                duration = time.time() - start_time
                self.metrics.observe_warmup_duration(duration, 'error')

                if span:
                    span.record_exception(e)
                    span.set_attribute("warmup.success", False)
                    span.set_attribute("warmup.time_ms", int(duration * 1000))
                    span.set_attribute(
                        "warmup.dummy_plan_id",
                        dummy_plan.get('plan_id') if dummy_plan else None
                    )
                    span.set_status(Status(StatusCode.ERROR, str(e)))

                logger.error(
                    "Specialist warmup failed",
                    specialist_type=self.specialist_type,
                    error=str(e),
                    duration_seconds=duration,
                    exc_info=True
                )

                return {
                    'status': 'error',
                    'error': str(e),
                    'duration_seconds': duration
                }

    def _create_dummy_plan(self) -> Dict[str, Any]:
        """
        Cria plano cognitivo dummy para warmup.

        Returns:
            Plano dummy válido
        """
        return {
            'version': '1.0.0',
            'plan_id': 'warmup-plan-dummy',
            'intent_id': 'warmup-intent-dummy',
            'original_domain': 'warmup',
            'original_priority': 'normal',
            'tasks': [
                {
                    'task_id': 'warmup-task-1',
                    'name': 'Warmup Task',
                    'task_type': 'warmup',
                    'description': 'Dummy task for warmup',
                    'estimated_duration_ms': 100,
                    'dependencies': []
                }
            ]
        }

    def health_check(self) -> Dict[str, Any]:
        """Verifica saúde do especialista."""
        details = {}
        degraded_reasons = []

        # Verificar modelo carregado
        details['model_loaded'] = str(self.model is not None)

        # Verificar MLflow
        if self.mlflow_client:
            details['mlflow_connected'] = str(self.mlflow_client.is_connected())
        else:
            details['mlflow_connected'] = 'N/A'

        # Verificar ledger
        if self.ledger_client is not None:
            try:
                details['ledger_connected'] = str(self.ledger_client.is_connected())
                if not self.ledger_client.is_connected():
                    degraded_reasons.append('ledger_unavailable')
            except Exception as e:
                logger.warning("Ledger health check failed", error=str(e))
                details['ledger'] = 'unavailable'
                details['ledger_connected'] = 'False'
                degraded_reasons.append('ledger_unavailable')
        else:
            details['ledger'] = 'disabled'
            details['ledger_connected'] = 'False'
            degraded_reasons.append('ledger_disabled')

        # Verificar opinion cache
        if self.opinion_cache:
            details['opinion_cache_connected'] = str(self.opinion_cache.is_connected())
        else:
            details['opinion_cache_connected'] = 'N/A'

        # Verificar compliance layer
        if hasattr(self, 'compliance_layer') and self.compliance_layer:
            details['compliance_layer'] = {
                'enabled': self.config.enable_compliance_layer,
                'pii_detection_enabled': bool(self.config.enable_pii_detection and self.compliance_layer),
                'encryption_enabled': bool(self.config.enable_field_encryption and self.compliance_layer),
                'audit_logging_enabled': bool(self.config.enable_audit_logging and self.compliance_layer)
            }
            # Incluir metadados adicionais se disponível
            if hasattr(self.compliance_layer, 'get_compliance_metadata'):
                details['compliance_layer'].update(self.compliance_layer.get_compliance_metadata())
        else:
            details['compliance_layer'] = {'enabled': False}

        # Verificar drift monitoring
        details['drift_monitoring_enabled'] = str(self.drift_detector is not None)
        if self.drift_detector:
            details['drift_monitoring_running'] = str(self.drift_detector._running)

        # Circuit breaker states
        circuit_breaker_states = {}
        if self.mlflow_client:
            circuit_breaker_states['mlflow'] = self.mlflow_client.get_circuit_breaker_state()
        if self.ledger_client:
            circuit_breaker_states['ledger'] = self.ledger_client.get_circuit_breaker_state()
        circuit_breaker_states['explainability'] = self.explainability_gen.get_circuit_breaker_state()

        details['circuit_breaker_states'] = circuit_breaker_states

        # Verificar se algum circuit breaker está aberto
        any_circuit_open = any(state == 'open' for state in circuit_breaker_states.values())

        # Buffer do ledger
        if self.ledger_client:
            ledger_buffer_size = self.ledger_client.get_buffer_size()
            details['ledger_buffer_size'] = str(ledger_buffer_size)
        else:
            ledger_buffer_size = 0
            details['ledger_buffer_size'] = 'N/A'

        # Check for degradation signals
        # Check ledger buffer
        if ledger_buffer_size > 0:
            degraded_reasons.append('ledger_buffer>0')

        # Check MLflow expired cache usage
        if self.mlflow_client and self.mlflow_client.used_expired_cache_recently:
            degraded_reasons.append('mlflow_expired_cache')

        # Set circuit breakers open flag and degraded reasons
        if any_circuit_open or degraded_reasons:
            details['circuit_breakers_open'] = 'True'

        if degraded_reasons:
            details['degraded_reasons'] = degraded_reasons

        # Determinar status considerando modo degradado opcional do ledger
        if self.config.ledger_required:
            # Se ledger é obrigatório, exigir conexão para SERVING
            critical_healthy = (
                details['model_loaded'] == 'True' and
                details['ledger_connected'] == 'True'
            )
        else:
            # Se ledger é opcional, não exigir conexão para SERVING
            # Marcar degraded_reasons adequadamente se ledger indisponível
            critical_healthy = details['model_loaded'] == 'True'

            # Verificar se ledger está indisponível (mas não desabilitado propositalmente)
            if self.config.enable_ledger and details.get('ledger_connected') == 'False':
                # Ledger está habilitado mas indisponível - modo degradado
                if 'ledger_unavailable' not in degraded_reasons:
                    degraded_reasons.append('ledger_unavailable')
                details['degraded_reasons'] = degraded_reasons

        status = 'SERVING' if critical_healthy else 'NOT_SERVING'

        logger.debug(
            "Health check performed",
            specialist_type=self.specialist_type,
            status=status,
            details=details
        )

        return {
            'status': status,
            'details': details
        }

    def get_capabilities(self) -> Dict[str, Any]:
        """Retorna capacidades do especialista."""
        metrics_summary = self.metrics.get_summary()

        capabilities = {
            'specialist_type': self.specialist_type,
            'version': self.version,
            'supported_domains': self.config.supported_domains,
            'supported_plan_versions': self.config.supported_plan_versions,
            'metrics': {
                'average_processing_time_ms': metrics_summary.get('avg_processing_time_ms', 0.0),
                'accuracy_score': metrics_summary.get('accuracy_score', 0.0),
                'total_evaluations': metrics_summary.get('total_evaluations', 0),
                'last_model_update': self.mlflow_client.get_last_model_update() if self.mlflow_client else None
            },
            'configuration': {
                'min_confidence_score': self.config.min_confidence_score,
                'high_risk_threshold': self.config.high_risk_threshold,
                'enable_explainability': self.config.enable_explainability,
                'enable_caching': self.config.enable_caching
            }
        }

        logger.debug(
            "Capabilities retrieved",
            specialist_type=self.specialist_type,
            capabilities=capabilities
        )

        return capabilities

    def close(self):
        """Fecha conexões e libera recursos."""
        try:
            if self.opinion_cache:
                self.opinion_cache.close()
            if self.feature_store:
                self.feature_store.close()
            logger.info("Specialist resources closed", specialist_type=self.specialist_type)
        except Exception as e:
            logger.warning(
                "Error closing specialist resources",
                specialist_type=self.specialist_type,
                error=str(e)
            )
