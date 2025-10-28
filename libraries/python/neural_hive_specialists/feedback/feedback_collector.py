"""
Coletor de feedback humano para continuous learning de especialistas.

Este módulo gerencia a coleta, validação e persistência de feedback humano
sobre opiniões de especialistas, permitindo re-treinamento contínuo dos modelos.
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import structlog
from pydantic import BaseModel, Field, field_validator, ConfigDict
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError
import pybreaker

from ..config import SpecialistConfig
from ..compliance import AuditLogger

logger = structlog.get_logger()


class FeedbackStoreUnavailable(Exception):
    """
    Exceção levantada quando o armazenamento de feedback está indisponível.

    Pode ser causada por:
    - Circuit breaker aberto
    - Erros de conexão com MongoDB
    - Timeouts
    """
    pass


class FeedbackDocument(BaseModel):
    """
    Schema Pydantic para documento de feedback humano.

    Representa feedback de um revisor humano sobre uma opinião de especialista,
    usado para enriquecer dataset de treinamento.
    """

    feedback_id: str = Field(
        default_factory=lambda: f"feedback-{uuid.uuid4().hex[:12]}",
        description="ID único do feedback"
    )
    schema_version: str = Field(
        default='1.0.0',
        description="Versão do schema de feedback"
    )
    opinion_id: str = Field(
        ...,
        description="ID da opinião avaliada (FK para cognitive_ledger)"
    )
    plan_id: str = Field(
        ...,
        description="ID do plano cognitivo (denormalizado)"
    )
    specialist_type: str = Field(
        ...,
        description="Tipo do especialista (denormalizado)"
    )
    human_rating: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Rating de concordância (0.0-1.0)"
    )
    human_recommendation: str = Field(
        ...,
        description="Recomendação do revisor (approve, reject, review_required)"
    )
    feedback_notes: str = Field(
        default='',
        description="Notas textuais do revisor"
    )
    submitted_by: str = Field(
        ...,
        description="Identificador do revisor (email, user_id)"
    )
    submitted_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp de submissão"
    )
    feedback_source: str = Field(
        default='human_expert',
        description="Fonte do feedback"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados adicionais"
    )

    @field_validator('human_recommendation')
    @classmethod
    def validate_recommendation(cls, v):
        """Valida que recomendação é válida."""
        valid_recommendations = ['approve', 'reject', 'review_required']
        if v not in valid_recommendations:
            raise ValueError(
                f"human_recommendation deve ser um de {valid_recommendations}, recebido: {v}"
            )
        return v

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )


class FeedbackCollector:
    """
    Gerencia coleta, validação e persistência de feedback humano.

    Responsável por:
    - Validar e persistir feedback no MongoDB
    - Consultar feedbacks por opinion_id, specialist_type, período
    - Calcular estatísticas de feedback
    - Integrar com AuditLogger para rastreamento
    """

    def __init__(self, config: SpecialistConfig, audit_logger: Optional[AuditLogger] = None):
        """
        Inicializa FeedbackCollector.

        Args:
            config: Configuração do especialista
            audit_logger: Logger de auditoria (opcional)
        """
        self.config = config
        self.audit_logger = audit_logger
        self._client: Optional[MongoClient] = None
        self._db = None
        self._collection = None
        self._opinions_collection = None

        # Circuit breaker para MongoDB usando pybreaker
        self.breaker = pybreaker.CircuitBreaker(
            fail_max=5,
            reset_timeout=60,
            name="feedback_mongo"
        )

        # Inicializar conexão
        self._connect()
        self._create_indexes()

        logger.info(
            "FeedbackCollector initialized",
            collection=config.feedback_mongodb_collection,
            enabled=config.enable_feedback_collection
        )

    def _connect(self):
        """Estabelece conexão com MongoDB."""
        try:
            self._client = MongoClient(self.config.mongodb_uri)
            self._db = self._client[self.config.mongodb_database]
            self._collection = self._db[self.config.feedback_mongodb_collection]
            self._opinions_collection = self._db[self.config.mongodb_opinions_collection]

            # Test connection
            self._client.admin.command('ping')

            logger.info(
                "MongoDB connection established for feedback",
                database=self.config.mongodb_database,
                collection=self.config.feedback_mongodb_collection
            )
        except Exception as e:
            logger.error("Failed to connect to MongoDB", error=str(e))
            raise

    def _create_indexes(self):
        """Cria índices otimizados para queries de feedback."""
        try:
            # Índice para buscar feedback por opinião
            self._collection.create_index([('opinion_id', ASCENDING)])

            # Índice composto para contagem por especialista e período
            self._collection.create_index([
                ('specialist_type', ASCENDING),
                ('submitted_at', DESCENDING)
            ])

            # Índice para rating
            self._collection.create_index([('human_rating', ASCENDING)])

            # Índice único para feedback_id
            self._collection.create_index([('feedback_id', ASCENDING)], unique=True)

            logger.info("Feedback indexes created successfully")
        except Exception as e:
            logger.warning("Failed to create feedback indexes", error=str(e))

    def _with_breaker(self, fn):
        """
        Helper para executar operações MongoDB com circuit breaker.

        Args:
            fn: Função a executar

        Returns:
            Resultado da função

        Raises:
            pybreaker.CircuitBreakerError: Se circuit breaker estiver aberto
        """
        return self.breaker.call(fn)

    def validate_opinion_exists(self, opinion_id: str) -> bool:
        """
        Verifica se opinião existe no ledger cognitivo.

        Args:
            opinion_id: ID da opinião

        Returns:
            True se opinião existe, False caso contrário
        """
        try:
            result = self._opinions_collection.find_one(
                {'opinion_id': opinion_id},
                {'_id': 1}
            )
            return result is not None
        except Exception as e:
            logger.error(
                "Error validating opinion existence",
                opinion_id=opinion_id,
                error=str(e)
            )
            return False

    def get_opinion_metadata(self, opinion_id: str) -> Dict[str, Any]:
        """
        Obtém metadados de uma opinião do ledger cognitivo.

        Args:
            opinion_id: ID da opinião

        Returns:
            Dict com plan_id e specialist_type

        Raises:
            ValueError: Se opinião não for encontrada
        """
        try:
            result = self._opinions_collection.find_one(
                {'opinion_id': opinion_id},
                {'_id': 0, 'plan_id': 1, 'specialist_type': 1}
            )

            if result is None:
                raise ValueError(f"Opinião {opinion_id} não encontrada no ledger")

            return {
                'plan_id': result.get('plan_id', ''),
                'specialist_type': result.get('specialist_type', '')
            }

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "Error retrieving opinion metadata",
                opinion_id=opinion_id,
                error=str(e)
            )
            raise ValueError(f"Erro ao buscar metadados da opinião {opinion_id}: {str(e)}")

    def submit_feedback(self, feedback_data: Dict[str, Any]) -> str:
        """
        Valida, persiste e retorna ID de feedback.

        Args:
            feedback_data: Dados do feedback

        Returns:
            feedback_id: ID do feedback criado

        Raises:
            ValueError: Se validação falhar
            PyMongoError: Se persistência falhar
            pybreaker.CircuitBreakerError: Se circuit breaker estiver aberto
        """
        # Validar que opinião existe
        opinion_id = feedback_data.get('opinion_id')
        if not opinion_id:
            raise ValueError("opinion_id é obrigatório")

        if not self.validate_opinion_exists(opinion_id):
            raise ValueError(f"Opinião {opinion_id} não encontrada no ledger")

        # Validar com Pydantic
        try:
            feedback_doc = FeedbackDocument(**feedback_data)
        except Exception as e:
            logger.error(
                "Feedback validation failed",
                feedback_data=feedback_data,
                error=str(e)
            )
            raise ValueError(f"Validação de feedback falhou: {str(e)}")

        # Validar rating range
        if not self.config.feedback_rating_min <= feedback_doc.human_rating <= self.config.feedback_rating_max:
            raise ValueError(
                f"Rating deve estar entre {self.config.feedback_rating_min} e {self.config.feedback_rating_max}"
            )

        # Persistir no MongoDB com circuit breaker
        try:
            doc_dict = feedback_doc.model_dump()
            self.breaker.call(lambda: self._collection.insert_one(doc_dict))

            logger.info(
                "Feedback submitted successfully",
                feedback_id=feedback_doc.feedback_id,
                opinion_id=feedback_doc.opinion_id,
                specialist_type=feedback_doc.specialist_type,
                rating=feedback_doc.human_rating,
                recommendation=feedback_doc.human_recommendation
            )

            # Auditar submissão
            if self.audit_logger:
                self.audit_logger.log_data_access(
                    operation='feedback_submission',
                    resource_id=feedback_doc.feedback_id,
                    details={
                        'opinion_id': feedback_doc.opinion_id,
                        'specialist_type': feedback_doc.specialist_type,
                        'submitted_by': feedback_doc.submitted_by,
                        'rating': feedback_doc.human_rating
                    }
                )

            return feedback_doc.feedback_id

        except pybreaker.CircuitBreakerError as e:
            logger.error(
                "Circuit breaker open - MongoDB unavailable",
                feedback_id=feedback_doc.feedback_id,
                error=str(e)
            )
            raise
        except PyMongoError as e:
            logger.error(
                "Failed to persist feedback",
                feedback_id=feedback_doc.feedback_id,
                error=str(e)
            )
            raise

    def get_feedback_by_opinion(self, opinion_id: str) -> List[FeedbackDocument]:
        """
        Busca todos os feedbacks para uma opinião.

        Args:
            opinion_id: ID da opinião

        Returns:
            Lista de FeedbackDocuments

        Raises:
            FeedbackStoreUnavailable: Se store estiver indisponível
        """
        try:
            results = self._with_breaker(lambda: list(self._collection.find({'opinion_id': opinion_id})))
            feedbacks = []
            for doc in results:
                doc.pop('_id', None)  # Remove MongoDB _id
                feedbacks.append(FeedbackDocument(**doc))

            logger.debug(
                "Retrieved feedbacks for opinion",
                opinion_id=opinion_id,
                count=len(feedbacks)
            )

            return feedbacks

        except pybreaker.CircuitBreakerError as e:
            logger.error(
                "Circuit breaker open - cannot retrieve feedbacks",
                opinion_id=opinion_id,
                error=str(e)
            )
            raise FeedbackStoreUnavailable(
                f"Feedback store indisponível (circuit breaker aberto) para opinião {opinion_id}"
            ) from e
        except PyMongoError as e:
            logger.error(
                "MongoDB error retrieving feedbacks for opinion",
                opinion_id=opinion_id,
                error=str(e)
            )
            raise FeedbackStoreUnavailable(
                f"Erro ao acessar feedback store para opinião {opinion_id}: {str(e)}"
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected error retrieving feedbacks for opinion",
                opinion_id=opinion_id,
                error=str(e)
            )
            raise

    def get_feedback_by_specialist(
        self,
        specialist_type: str,
        window_days: int
    ) -> List[FeedbackDocument]:
        """
        Busca feedbacks recentes de um especialista.

        Args:
            specialist_type: Tipo do especialista
            window_days: Janela de tempo em dias

        Returns:
            Lista de FeedbackDocuments

        Raises:
            FeedbackStoreUnavailable: Se store estiver indisponível
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=window_days)

            results = self._with_breaker(lambda: list(self._collection.find({
                'specialist_type': specialist_type,
                'submitted_at': {'$gte': cutoff_date}
            }).sort('submitted_at', DESCENDING)))

            feedbacks = []
            for doc in results:
                doc.pop('_id', None)
                feedbacks.append(FeedbackDocument(**doc))

            logger.debug(
                "Retrieved feedbacks for specialist",
                specialist_type=specialist_type,
                window_days=window_days,
                count=len(feedbacks)
            )

            return feedbacks

        except pybreaker.CircuitBreakerError as e:
            logger.error(
                "Circuit breaker open - cannot retrieve feedbacks",
                specialist_type=specialist_type,
                error=str(e)
            )
            raise FeedbackStoreUnavailable(
                f"Feedback store indisponível (circuit breaker aberto) para {specialist_type}"
            ) from e
        except PyMongoError as e:
            logger.error(
                "MongoDB error retrieving feedbacks for specialist",
                specialist_type=specialist_type,
                error=str(e)
            )
            raise FeedbackStoreUnavailable(
                f"Erro ao acessar feedback store para {specialist_type}: {str(e)}"
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected error retrieving feedbacks for specialist",
                specialist_type=specialist_type,
                error=str(e)
            )
            raise

    def count_recent_feedback(
        self,
        specialist_type: str,
        window_days: int
    ) -> int:
        """
        Conta feedbacks recentes para verificar threshold.

        Args:
            specialist_type: Tipo do especialista
            window_days: Janela de tempo em dias

        Returns:
            Contagem de feedbacks

        Raises:
            FeedbackStoreUnavailable: Se store estiver indisponível
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=window_days)

            count = self._with_breaker(lambda: self._collection.count_documents({
                'specialist_type': specialist_type,
                'submitted_at': {'$gte': cutoff_date}
            }))

            logger.debug(
                "Counted recent feedbacks",
                specialist_type=specialist_type,
                window_days=window_days,
                count=count
            )

            return count

        except pybreaker.CircuitBreakerError as e:
            logger.error(
                "Circuit breaker open - cannot count feedbacks",
                specialist_type=specialist_type,
                error=str(e)
            )
            raise FeedbackStoreUnavailable(
                f"Feedback store indisponível (circuit breaker aberto) ao contar feedbacks de {specialist_type}"
            ) from e
        except PyMongoError as e:
            logger.error(
                "MongoDB error counting recent feedbacks",
                specialist_type=specialist_type,
                error=str(e)
            )
            raise FeedbackStoreUnavailable(
                f"Erro ao acessar feedback store ao contar feedbacks de {specialist_type}: {str(e)}"
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected error counting recent feedbacks",
                specialist_type=specialist_type,
                error=str(e)
            )
            raise

    def get_feedback_statistics(
        self,
        specialist_type: str,
        window_days: int
    ) -> Dict[str, Any]:
        """
        Calcula estatísticas de feedback.

        Args:
            specialist_type: Tipo do especialista
            window_days: Janela de tempo em dias

        Returns:
            Dict com estatísticas (rating médio, distribuição, etc.)

        Raises:
            FeedbackStoreUnavailable: Se store estiver indisponível
        """
        # Propagar exceções de FeedbackStoreUnavailable
        feedbacks = self.get_feedback_by_specialist(specialist_type, window_days)

        if not feedbacks:
            return {
                'count': 0,
                'avg_rating': 0.0,
                'distribution': {},
                'specialist_type': specialist_type,
                'window_days': window_days
            }

        # Calcular rating médio
        avg_rating = sum(f.human_rating for f in feedbacks) / len(feedbacks)

        # Calcular distribuição de recomendações
        distribution = {}
        for feedback in feedbacks:
            rec = feedback.human_recommendation
            distribution[rec] = distribution.get(rec, 0) + 1

        stats = {
            'count': len(feedbacks),
            'avg_rating': round(avg_rating, 3),
            'distribution': distribution,
            'specialist_type': specialist_type,
            'window_days': window_days,
            'min_rating': min(f.human_rating for f in feedbacks),
            'max_rating': max(f.human_rating for f in feedbacks)
        }

        logger.info(
            "Calculated feedback statistics",
            **stats
        )

        return stats

    def close(self):
        """Fecha conexão com MongoDB."""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed for feedback")
