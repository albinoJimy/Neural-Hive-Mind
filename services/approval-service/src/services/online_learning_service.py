"""
Online Learning Service - Wrapper para IncrementalLearner

Integra o IncrementalLearner do ml_pipelines com o approval service,
permitindo aprendizado incremental contínuo a partir de feedbacks.
"""

import asyncio
import os
from typing import Any, Optional

import numpy as np
import structlog

from src.config.settings import Settings

logger = structlog.get_logger()

# Import opcional do IncrementalLearner
try:
    from ml_pipelines.online_learning.config import OnlineLearningConfig
    from ml_pipelines.online_learning.incremental_learner import (
        CheckpointError,
        IncrementalLearner,
        IncrementalLearnerError,
        ModelNotInitializedError,
    )

    HAS_INCREMENTAL_LEARNER = True
except ImportError:
    HAS_INCREMENTAL_LEARNER = False
    IncrementalLearner = None
    OnlineLearningConfig = None
    IncrementalLearnerError = Exception
    ModelNotInitializedError = Exception
    CheckpointError = Exception


class OnlineLearningServiceError(Exception):
    """Exceção base para erros do OnlineLearningService."""



class OnlineLearningNotEnabledError(OnlineLearningServiceError):
    """Exceção quando online learning não está habilitado."""



class FeatureExtractionError(OnlineLearningServiceError):
    """Exceção para erros na extração de features."""



class OnlineLearningService:
    """
    Serviço de gerenciamento de online learning para o approval service.

    Funcionalidades:
    - Wrapper para IncrementalLearner
    - Extração de features de feedbacks
    - Execução de partial_fit periódico
    - Model checkpoint para MLflow
    - Métricas de aprendizado
    """

    # Classes de decisão para classificação
    DECISION_CLASSES = ["approve", "reject", "review_required"]

    # Features esperadas pelo modelo
    FEATURE_NAMES = [
        "confidence",
        "risk",
        "sentiment_score",
        "urgency_score",
        "complexity_score",
        "business_domain_confidence",
        "technical_domain_confidence",
        "architecture_domain_confidence",
        "behavior_domain_confidence",
        "evolution_domain_confidence",
    ]

    def __init__(self, settings: Settings):
        """
        Inicializa Online Learning Service.

        Args:
            settings: Configurações do Approval Service
        """
        self.settings = settings
        self._enabled = settings.enable_online_learning and HAS_INCREMENTAL_LEARNER

        if not self._enabled:
            logger.warning(
                "online_learning_disabled",
                has_incremental_learner=HAS_INCREMENTAL_LEARNER,
                setting_enabled=settings.enable_online_learning,
            )
            return

        # Criar configuração do ml_pipelines a partir das settings do approval service
        self._ml_config = OnlineLearningConfig(
            online_learning_enabled=True,
            incremental_algorithm=settings.online_learning_algorithm,
            mini_batch_size=settings.online_learning_buffer_size,
            learning_rate=settings.online_learning_learning_rate,
            checkpoint_interval_updates=settings.online_learning_checkpoint_interval_updates,
            checkpoint_storage_path=settings.online_learning_checkpoint_path,
            mongodb_uri=settings.mongodb_uri,
            mongodb_database=settings.mongodb_database,
        )

        # Criar learner para cada specialist type
        self._learners: dict[str, IncrementalLearner] = {}
        self._learner_lock = asyncio.Lock()

        # Tentar carregar checkpoint existente
        self._checkpoints_loaded = False

        logger.info(
            "online_learning_service_initialized",
            algorithm=self._ml_config.incremental_algorithm,
            buffer_size=self._ml_config.mini_batch_size,
            checkpoint_path=self._ml_config.checkpoint_storage_path,
        )

    @property
    def is_enabled(self) -> bool:
        """Retorna se online learning está habilitado."""
        return self._enabled

    async def initialize(self):
        """Inicializa o serviço, carregando checkpoints existentes."""
        if not self._enabled:
            return

        await self._load_existing_checkpoints()

    async def _load_existing_checkpoints(self):
        """Carrega checkpoints existentes do armazenamento."""
        if not os.path.exists(self._ml_config.checkpoint_storage_path):
            logger.info("checkpoint_path_nao_existe", path=self._ml_config.checkpoint_storage_path)
            return

        try:
            # Listar arquivos de checkpoint
            checkpoint_files = [
                f for f in os.listdir(self._ml_config.checkpoint_storage_path) if f.endswith(".pkl")
            ]

            if not checkpoint_files:
                logger.info("nenhum_checkpoint_encontrado")
                return

            # Carregar o checkpoint mais recente para cada specialist
            for specialist_type in self._get_supported_specialist_types():
                specialist_checkpoints = [
                    f for f in checkpoint_files if f.startswith(f"{specialist_type}_")
                ]

                if not specialist_checkpoints:
                    continue

                # Ordenar por timestamp (nome do arquivo)
                specialist_checkpoints.sort(reverse=True)
                latest_checkpoint = os.path.join(
                    self._ml_config.checkpoint_storage_path, specialist_checkpoints[0]
                )

                try:
                    learner = IncrementalLearner(
                        config=self._ml_config,
                        specialist_type=specialist_type,
                        classes=self.DECISION_CLASSES,
                        feature_names=self.FEATURE_NAMES,
                    )
                    learner.load_checkpoint(latest_checkpoint)
                    self._learners[specialist_type] = learner

                    logger.info(
                        "checkpoint_carregado",
                        specialist_type=specialist_type,
                        checkpoint=latest_checkpoint,
                        update_count=learner.updates_count,
                    )

                except CheckpointError as e:
                    logger.warning(
                        "falha_ao_carregar_checkpoint",
                        specialist_type=specialist_type,
                        checkpoint=latest_checkpoint,
                        error=str(e),
                    )
                    continue

            self._checkpoints_loaded = True

        except Exception as e:
            logger.error("erro_ao_carregar_checkpoints", error=str(e))

    async def process_feedback_batch(self, feedbacks: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Processa lote de feedbacks para aprendizado incremental.

        Args:
            feedbacks: Lista de feedbacks do specialist_feedback topic

        Returns:
            Dicionário com métricas do processamento

        Raises:
            OnlineLearningNotEnabledError: Se serviço não habilitado
            FeatureExtractionError: Se falhar extração de features
        """
        if not self._enabled:
            raise OnlineLearningNotEnabledError("Online learning não está habilitado")

        if not feedbacks:
            return {"processed": 0, "errors": 0}

        # Agrupar feedbacks por specialist_type
        feedbacks_by_specialist = self._group_feedbacks_by_specialist(feedbacks)

        results = {"processed": 0, "errors": 0, "specialist_results": {}}

        # Processar cada specialist type
        for specialist_type, specialist_feedbacks in feedbacks_by_specialist.items():
            try:
                result = await self._process_specialist_feedbacks(
                    specialist_type, specialist_feedbacks
                )
                results["specialist_results"][specialist_type] = result
                results["processed"] += result.get("processed", 0)
                results["errors"] += result.get("errors", 0)

            except Exception as e:
                logger.error(
                    "erro_ao_processar_feedbacks_specialist",
                    specialist_type=specialist_type,
                    feedback_count=len(specialist_feedbacks),
                    error=str(e),
                )
                results["errors"] += len(specialist_feedbacks)

        logger.info("feedback_batch_processado", **results)

        return results

    def _group_feedbacks_by_specialist(
        self, feedbacks: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Agrupa feedbacks por specialist_type.

        Args:
            feedbacks: Lista de feedbacks

        Returns:
            Dicionário specialist_type -> lista de feedbacks
        """
        grouped = {}
        for feedback in feedbacks:
            specialist_type = feedback.get("specialist_type", "unknown")
            if specialist_type not in grouped:
                grouped[specialist_type] = []
            grouped[specialist_type].append(feedback)
        return grouped

    async def _process_specialist_feedbacks(
        self, specialist_type: str, feedbacks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Processa feedbacks de um specialist específico.

        Args:
            specialist_type: Tipo do especialista
            feedbacks: Lista de feedbacks

        Returns:
            Métricas do processamento
        """
        # Obter ou criar learner
        learner = await self._get_or_create_learner(specialist_type)

        # Extrair features e labels
        features_list = []
        labels_list = []
        errors = 0

        for feedback in feedbacks:
            try:
                features, label = self._extract_features_and_label(feedback)
                if features is not None and label is not None:
                    features_list.append(features)
                    labels_list.append(label)
                else:
                    errors += 1
            except FeatureExtractionError as e:
                logger.debug(
                    "feature_extraction_failed",
                    feedback_id=feedback.get("feedback_id"),
                    error=str(e),
                )
                errors += 1

        if not features_list:
            return {"specialist_type": specialist_type, "processed": 0, "errors": errors}

        # Converter para numpy arrays
        X = np.array(features_list)
        y = np.array(labels_list)

        # Executar partial_fit
        try:
            fit_result = learner.partial_fit(X, y)
            return {
                "specialist_type": specialist_type,
                "processed": len(features_list),
                "errors": errors,
                "update_metrics": fit_result,
            }
        except IncrementalLearnerError as e:
            logger.error("partial_fit_failed", specialist_type=specialist_type, error=str(e))
            return {
                "specialist_type": specialist_type,
                "processed": 0,
                "errors": len(features_list),
            }

    async def _get_or_create_learner(self, specialist_type: str) -> IncrementalLearner:
        """
        Obtém learner existente ou cria novo.

        Args:
            specialist_type: Tipo do especialista

        Returns:
            IncrementalLearner
        """
        async with self._learner_lock:
            if specialist_type not in self._learners:
                learner = IncrementalLearner(
                    config=self._ml_config,
                    specialist_type=specialist_type,
                    classes=self.DECISION_CLASSES,
                    feature_names=self.FEATURE_NAMES,
                )
                self._learners[specialist_type] = learner
                logger.info("learner_criado", specialist_type=specialist_type)
            return self._learners[specialist_type]

    def _extract_features_and_label(
        self, feedback: dict[str, Any]
    ) -> tuple[Optional[np.ndarray], Optional[str]]:
        """
        Extrai features e label de um feedback.

        Args:
            feedback: Dados do feedback

        Returns:
            Tuple (features_array, label) ou (None, None) se falhar
        """
        try:
            # Extrair label (human_recommendation ou mapear rating)
            label = self._extract_label(feedback)
            if label is None:
                return None, None

            # Extrair features
            features = self._extract_features(feedback)
            if features is None:
                return None, None

            return features, label

        except Exception as e:
            raise FeatureExtractionError(f"Falha na extração: {e!s}") from e

    def _extract_label(self, feedback: dict[str, Any]) -> Optional[str]:
        """
        Extrai label de decisão do feedback.

        Args:
            feedback: Dados do feedback

        Returns:
            Label ('approve', 'reject', 'review_required') ou None
        """
        # Tentar human_recommendation primeiro
        human_rec = feedback.get("human_recommendation")
        if human_rec:
            if isinstance(human_rec, str):
                human_rec = human_rec.lower()
                if human_rec in ["approve", "approved"]:
                    return "approve"
                elif human_rec in ["reject", "rejected"]:
                    return "reject"
                elif human_rec in ["review", "review_required"]:
                    return "review_required"

        # Mapear rating para decisão
        rating = feedback.get("human_rating")
        if rating is not None:
            try:
                rating_val = float(rating)
                if rating_val >= 0.7:
                    return "approve"
                elif rating_val <= 0.3:
                    return "reject"
                else:
                    return "review_required"
            except (ValueError, TypeError):
                pass

        return None

    def _extract_features(self, feedback: dict[str, Any]) -> Optional[np.ndarray]:
        """
        Extrai vetor de features do feedback.

        Args:
            feedback: Dados do feedback

        Returns:
            Array numpy com features ou None
        """
        features = []

        # 1. Confidence (specialist ou default 0.5)
        confidence = feedback.get("specialist_confidence", 0.5)
        if confidence is None:
            confidence = 0.5
        features.append(float(confidence))

        # 2. Risk (extrair de metadata ou default 0.5)
        risk = 0.5
        if "metadata" in feedback and isinstance(feedback["metadata"], dict):
            risk = feedback["metadata"].get("risk_score", 0.5)
        features.append(float(risk))

        # 3-5. NLP Features (sentiment, urgency, complexity)
        nlp_features = feedback.get("nlp_features", {})
        if isinstance(nlp_features, dict):
            sentiment = nlp_features.get("sentiment_score", 0.5)
            urgency = nlp_features.get("urgency_score", 0.5)
            complexity = nlp_features.get("complexity_score", 0.5)
        else:
            sentiment = urgency = complexity = 0.5

        features.extend([float(sentiment), float(urgency), float(complexity)])

        # 6-10. Domain confidences (business, technical, architecture, behavior, evolution)
        domain = (
            nlp_features.get("primary_domain", "unknown")
            if isinstance(nlp_features, dict)
            else "unknown"
        )

        for d in ["business", "technical", "architecture", "behavior", "evolution"]:
            if domain == d:
                features.append(1.0)  # Alta confiança para domínio primário
            else:
                features.append(0.3)  # Baixa confiança para outros domínios

        return np.array(features)

    async def get_model_state(self, specialist_type: str) -> Optional[dict[str, Any]]:
        """
        Retorna estado atual do modelo para um specialist.

        Args:
            specialist_type: Tipo do especialista

        Returns:
            Dicionário com estado do modelo ou None
        """
        if not self._enabled:
            return None

        learner = self._learners.get(specialist_type)
        if not learner:
            return None

        return learner.get_model_state()

    async def get_convergence_metrics(self, specialist_type: str) -> Optional[dict[str, Any]]:
        """
        Retorna métricas de convergência do modelo.

        Args:
            specialist_type: Tipo do especialista

        Returns:
            Dicionário com métricas de convergência
        """
        if not self._enabled:
            return None

        learner = self._learners.get(specialist_type)
        if not learner or not learner.is_fitted:
            return None

        return learner.get_convergence_metrics()

    async def get_all_learner_states(self) -> dict[str, Any]:
        """
        Retorna estado de todos os learners.

        Returns:
            Dicionário com estados de todos os specialists
        """
        if not self._enabled:
            return {"enabled": False}

        states = {}
        for specialist_type, learner in self._learners.items():
            try:
                states[specialist_type] = {
                    "model_state": learner.get_model_state(),
                    "convergence": learner.get_convergence_metrics() if learner.is_fitted else None,
                }
            except Exception as e:
                states[specialist_type] = {"error": str(e)}

        return {"enabled": True, "total_learners": len(self._learners), "learners": states}

    async def save_all_checkpoints(self) -> dict[str, Any]:
        """
        Salva checkpoints de todos os learners.

        Returns:
            Dicionário com resultados
        """
        if not self._enabled:
            return {"enabled": False}

        results = {}
        for specialist_type, learner in self._learners.items():
            try:
                if learner.is_fitted:
                    path = learner.save_checkpoint()
                    results[specialist_type] = {"success": True, "checkpoint_path": path}
                else:
                    results[specialist_type] = {"success": False, "reason": "model_not_fitted"}
            except Exception as e:
                results[specialist_type] = {"success": False, "error": str(e)}

        return {"enabled": True, "results": results}

    def _get_supported_specialist_types(self) -> list[str]:
        """Retorna lista de specialist types suportados."""
        return [
            "text_analysis",
            "code_analysis",
            "data_analysis",
            "security",
            "business",
            "technical",
            "architecture",
            "behavior",
            "evolution",
        ]

    async def predict(self, specialist_type: str, features: np.ndarray) -> Optional[np.ndarray]:
        """
        Executa predição com modelo online.

        Args:
            specialist_type: Tipo do especialista
            features: Array de features

        Returns:
            Predições ou None
        """
        if not self._enabled:
            return None

        learner = self._learners.get(specialist_type)
        if not learner or not learner.is_fitted:
            return None

        try:
            return learner.predict(features)
        except ModelNotInitializedError:
            return None

    async def predict_proba(
        self, specialist_type: str, features: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        Executa predição de probabilidades.

        Args:
            specialist_type: Tipo do especialista
            features: Array de features

        Returns:
            Probabilidades ou None
        """
        if not self._enabled:
            return None

        learner = self._learners.get(specialist_type)
        if not learner or not learner.is_fitted:
            return None

        try:
            return learner.predict_proba(features)
        except ModelNotInitializedError:
            return None

    async def reset_learner(self, specialist_type: str) -> bool:
        """
        Reinicia learner para estado inicial.

        Args:
            specialist_type: Tipo do especialista

        Returns:
            True se sucesso
        """
        if not self._enabled:
            return False

        learner = self._learners.get(specialist_type)
        if not learner:
            return False

        try:
            learner.reset()
            logger.info("learner_resetado", specialist_type=specialist_type)
            return True
        except Exception as e:
            logger.error("erro_ao_resetar_learner", specialist_type=specialist_type, error=str(e))
            return False
