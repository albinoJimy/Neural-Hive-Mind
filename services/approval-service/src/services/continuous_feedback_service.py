"""
Continuous Feedback Service (EPIC 3.3 - FASE 0 IA/ML Integration)

Coordena a coleta de feedback continuo, enriquecimento com features NLP,
e publicacao no Kafka para treinamento ML.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

from src.clients.mongodb_client import MongoDBClient
from src.config.settings import Settings
from src.models.continuous_feedback import (
    ContinuousFeedbackRequest,
    ContinuousFeedbackResponse,
    ContinuousFeedbackStats,
    TrainingDataKafkaMessage,
)
from src.producers.training_data_producer import TrainingDataProducer

# Import opcional do NLPFeatureExtractor
try:
    from neural_hive_specialists.feature_extraction.nlp_feature_extractor import (
        NLPFeatureExtractor,
        get_nlp_extractor,
    )

    HAS_NLP_EXTRACTOR = True
except ImportError:
    NLPFeatureExtractor = None
    get_nlp_extractor = None
    HAS_NLP_EXTRACTOR = False

logger = structlog.get_logger()


class ContinuousFeedbackService:
    """
    Servico para processamento de feedback continuo para ML.

    Orquestra:
    1. Recebimento de feedback via API
    2. Extracao de features NLP do texto da intent
    3. Persistencia no MongoDB (continuous_feedback collection)
    4. Publicacao no Kafka (ml.training_data topic)
    """

    def __init__(
        self,
        settings: Settings,
        mongodb_client: MongoDBClient,
        training_data_producer: TrainingDataProducer,
    ):
        self.settings = settings
        self.mongodb_client = mongodb_client
        self.training_data_producer = training_data_producer

        # Inicializa colecao de continuous feedback
        self.collection = None

        # Cache do NLP extractor (singleton)
        self._nlp_extractor: Optional[NLPFeatureExtractor] = None
        if HAS_NLP_EXTRACTOR:
            try:
                self._nlp_extractor = get_nlp_extractor()
                logger.info("NLPFeatureExtractor inicializado para continuous feedback")
            except Exception as e:
                logger.warning("NLP extractor init falhou", error=str(e))

    async def initialize(self):
        """Inicializa colecao MongoDB e indices"""
        self.collection = self.mongodb_client.db[
            self.settings.mongodb_collection + "_continuous_feedback"
        ]
        await self._create_indexes()
        logger.info(
            "ContinuousFeedbackService inicializado",
            collection=self.collection.name,
        )

    async def _create_indexes(self):
        """Cria indices para a colecao de continuous feedback"""
        await self.collection.create_index("prediction_id", unique=True)
        await self.collection.create_index("timestamp")
        await self.collection.create_index("prediction")
        await self.collection.create_index("actual_result")
        await self.collection.create_index([("prediction", 1), ("actual_result", 1)])
        await self.collection.create_index("plan_id", sparse=True)
        await self.collection.create_index("nlp_features_enriched")

        logger.debug("Indices criados para continuous_feedback")

    async def submit_feedback(
        self, feedback: ContinuousFeedbackRequest
    ) -> ContinuousFeedbackResponse:
        """
        Processa feedback continuo de predicao ML.

        Args:
            feedback: ContinuousFeedbackRequest com dados do feedback

        Returns:
            ContinuousFeedbackResponse com resultado do processamento
        """
        feedback_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc)

        # 1. Extrair features NLP se texto da intencao fornecido
        nlp_features = None
        nlp_features_enriched = False

        if feedback.intent_text and self._nlp_extractor:
            try:
                nlp_features = self._nlp_extractor.extract_features(feedback.intent_text)
                nlp_features_enriched = True
                logger.info(
                    "Features NLP extraidas para feedback continuo",
                    feedback_id=feedback_id,
                    prediction_id=feedback.prediction_id,
                    primary_domain=nlp_features.get("primary_domain", "unknown"),
                )
            except Exception as e:
                logger.warning(
                    "Falha ao extrair features NLP",
                    feedback_id=feedback_id,
                    error=str(e),
                )

        # 2. Criar mensagem Kafka com dados enriquecidos
        kafka_message = TrainingDataKafkaMessage(
            prediction_id=feedback.prediction_id,
            prediction=feedback.prediction,
            actual_result=feedback.actual_result,
            timestamp=feedback.timestamp,
            intent_text=feedback.intent_text,
            nlp_features=nlp_features,
            plan_id=feedback.plan_id,
            user_id=feedback.user_id,
            confidence=feedback.confidence,
            model_version=feedback.model_version,
            features=feedback.features,
        )

        # 3. Persistir no MongoDB
        document = {
            "feedback_id": feedback_id,
            "prediction_id": feedback.prediction_id,
            "prediction": feedback.prediction,
            "actual_result": feedback.actual_result,
            "timestamp": feedback.timestamp,
            "intent_text": feedback.intent_text,
            "plan_id": feedback.plan_id,
            "user_id": feedback.user_id,
            "confidence": feedback.confidence,
            "model_version": feedback.model_version,
            "features": feedback.features,
            "nlp_features": nlp_features,
            "nlp_features_enriched": nlp_features_enriched,
            "created_at": timestamp,
        }

        try:
            await self.collection.insert_one(document)
            logger.info(
                "Continuous feedback salvo no MongoDB",
                feedback_id=feedback_id,
                prediction_id=feedback.prediction_id,
            )
        except Exception as e:
            logger.error(
                "Erro ao salvar feedback no MongoDB",
                feedback_id=feedback_id,
                error=str(e),
            )
            # Continua processamento mesmo se MongoDB falhar

        # 4. Publicar no Kafka
        kafka_published = False
        try:
            await self.training_data_producer.send_training_data(kafka_message)
            kafka_published = True
        except Exception as e:
            logger.error(
                "Erro ao publicar no Kafka",
                feedback_id=feedback_id,
                prediction_id=feedback.prediction_id,
                error=str(e),
            )
            # Nao falha o request mesmo se Kafka falhar

        # 5. Retornar resposta
        return ContinuousFeedbackResponse(
            feedback_id=feedback_id,
            prediction_id=feedback.prediction_id,
            enrolled=True,
            nlp_features_enriched=nlp_features_enriched,
            kafka_published=kafka_published,
            created_at=timestamp,
        )

    async def get_feedback_by_prediction_id(
        self, prediction_id: str
    ) -> Optional[dict[str, Any]]:
        """
        Busca feedback por prediction_id.

        Args:
            prediction_id: ID da predicao

        Returns:
            Dict com dados do feedback ou None
        """
        document = await self.collection.find_one({"prediction_id": prediction_id})
        if document:
            document.pop("_id", None)
            return document
        return None

    async def get_stats(self) -> ContinuousFeedbackStats:
        """
        Retorna estatisticas de feedback continuo.

        Returns:
            ContinuousFeedbackStats com metricas agregadas
        """
        pipeline = [
            {
                "$facet": {
                    "total_count": [{"$count": "count"}],
                    "prediction_matches": [
                        {
                            "$group": {
                                "_id": {
                                    "prediction": "$prediction",
                                    "actual": "$actual_result",
                                },
                                "count": {"$sum": 1},
                            }
                        }
                    ],
                    "avg_confidence": [
                        {
                            "$match": {"confidence": {"$ne": None, "$ne": 0}}  # type: ignore
                        },
                        {
                            "$group": {
                                "_id": None,
                                "avg": {"$avg": "$confidence"},
                            }
                        },
                    ],
                    "nlp_enriched": [
                        {"$match": {"nlp_features_enriched": True}},
                        {"$count": "count"},
                    ],
                }
            }
        ]

        result = await self.collection.aggregate(pipeline).to_list(length=1)

        if not result or not result[0]:
            return ContinuousFeedbackStats(
                total_feedbacks=0,
                approvals_correct=0,
                approvals_incorrect=0,
                rejections_correct=0,
                rejections_incorrect=0,
                accuracy=0.0,
                avg_confidence=None,
                with_nlp_features=0,
            )

        data = result[0]

        # Total
        total = data.get("total_count", [{}])[0].get("count", 0)

        # Contagens por combinacao prediction/actual
        matches = {item["_id"]: item["count"] for item in data.get("prediction_matches", [])}

        approvals_correct = matches.get(("approve", "approve"), 0)
        approvals_incorrect = matches.get(("approve", "reject"), 0)
        rejections_correct = matches.get(("reject", "reject"), 0)
        rejections_incorrect = matches.get(("reject", "approve"), 0)

        # Acuracia
        correct = approvals_correct + rejections_correct
        accuracy = correct / total if total > 0 else 0.0

        # Confianca media
        avg_conf = None
        if data.get("avg_confidence") and data["avg_confidence"]:
            avg_conf = data["avg_confidence"][0].get("avg")

        # Com features NLP
        with_nlp = data.get("nlp_enriched", [{}])[0].get("count", 0)

        return ContinuousFeedbackStats(
            total_feedbacks=total,
            approvals_correct=approvals_correct,
            approvals_incorrect=approvals_incorrect,
            rejections_correct=rejections_correct,
            rejections_incorrect=rejections_incorrect,
            accuracy=round(accuracy, 4),
            avg_confidence=round(avg_conf, 4) if avg_conf else None,
            with_nlp_features=with_nlp,
        )

    async def get_recent_feedbacks(
        self, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """
        Lista feedbacks recentes.

        Args:
            limit: Limite de resultados
            offset: Offset para paginacao

        Returns:
            Lista de feedbacks ordenados por timestamp DESC
        """
        cursor = (
            self.collection.find({})
            .sort("timestamp", -1)
            .skip(offset)
            .limit(limit)
        )

        results = []
        async for document in cursor:
            document.pop("_id", None)
            results.append(document)

        return results
