"""
ExplainabilityLedgerV2: Ledger versionado de explicações com schema estruturado.

Persiste explicações completas com input_features, model_version, importance_vectors
e narrativa legível, garantindo reprodutibilidade e auditoria.
"""

import hashlib
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
import structlog
from pymongo import MongoClient, ASCENDING, IndexModel
from pydantic import BaseModel, Field, field_validator, model_validator

logger = structlog.get_logger(__name__)


class ExplainabilityRecordSchema(BaseModel):
    """Schema Pydantic para registro de explicabilidade v2."""

    explainability_token: str = Field(
        ...,
        description="Token único SHA-256 da explicação"
    )
    schema_version: str = Field(
        default="2.0.0",
        description="Versão do schema do ledger"
    )
    plan_id: str = Field(
        ...,
        description="ID do plano cognitivo"
    )
    specialist_type: str = Field(
        ...,
        description="Tipo do especialista (business, technical, etc.)"
    )
    explanation_method: str = Field(
        ...,
        description="Método de explicabilidade (shap, lime, heuristic)"
    )

    # Input features completas
    input_features: Dict[str, float] = Field(
        ...,
        description="Features estruturadas usadas na predição"
    )
    feature_names: List[str] = Field(
        ...,
        description="Nomes ordenados das features"
    )

    # Model metadata
    model_version: str = Field(
        ...,
        description="Versão do modelo MLflow"
    )
    model_type: str = Field(
        ...,
        description="Tipo do modelo (RandomForest, XGBoost, etc.)"
    )

    # Importance vectors (suporta ambos feature_importances e importance_vectors)
    feature_importances: List[Dict[str, Any]] = Field(
        ...,
        description="Lista de importâncias por feature com valores SHAP/LIME"
    )

    # Narrativa legível
    human_readable_summary: str = Field(
        ...,
        description="Resumo executivo em português"
    )
    detailed_narrative: str = Field(
        ...,
        description="Narrativa completa com top features"
    )

    # Metadata adicional
    prediction: Dict[str, float] = Field(
        ...,
        description="Predição do modelo (confidence_score, risk_score)"
    )
    computation_time_ms: int = Field(
        ...,
        description="Tempo de computação da explicação"
    )

    # Reprodutibilidade
    background_dataset_hash: Optional[str] = Field(
        None,
        description="Hash SHA-256 do background dataset (SHAP)"
    )
    random_seed: Optional[int] = Field(
        None,
        description="Seed para reprodutibilidade (LIME)"
    )
    num_samples: Optional[int] = Field(
        None,
        description="Número de amostras (LIME)"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp de criação"
    )
    correlation_id: Optional[str] = Field(
        None,
        description="ID de correlação para rastreamento distribuído"
    )

    @model_validator(mode='before')
    @classmethod
    def accept_importance_vectors_alias(cls, data: Any) -> Any:
        """
        Aceita tanto 'feature_importances' quanto 'importance_vectors' como nomes de campo.

        Se o dado de entrada usa 'importance_vectors', mapeia para 'feature_importances'.
        Isso garante compatibilidade com contratos externos que usam a terminologia antiga.
        """
        if isinstance(data, dict):
            # Se importance_vectors está presente mas feature_importances não
            if 'importance_vectors' in data and 'feature_importances' not in data:
                data['feature_importances'] = data.pop('importance_vectors')
        return data


class ExplainabilityLedgerV2:
    """Ledger versionado para explicações com schema estruturado."""

    def __init__(self, config: Any):
        """
        Inicializa ledger v2.

        Args:
            config: SpecialistConfig com mongodb_uri, etc.
        """
        self.config = config
        self._mongo_client: Optional[MongoClient] = None
        self._ensure_indexes()

        logger.info("ExplainabilityLedgerV2 initialized")

    @property
    def mongo_client(self) -> MongoClient:
        """Lazy initialization do cliente MongoDB."""
        if self._mongo_client is None:
            self._mongo_client = MongoClient(
                self.config.mongodb_uri,
                serverSelectionTimeoutMS=5000
            )
        return self._mongo_client

    def _ensure_indexes(self):
        """Cria índices otimizados na collection."""
        try:
            db = self.mongo_client[self.config.mongodb_database]
            collection = db['explainability_ledger_v2']

            # Índices
            indexes = [
                IndexModel([("explainability_token", ASCENDING)], unique=True),
                IndexModel([("plan_id", ASCENDING)]),
                IndexModel([("specialist_type", ASCENDING)]),
                IndexModel([("model_version", ASCENDING)]),
                IndexModel([("explanation_method", ASCENDING)]),
                IndexModel([("created_at", ASCENDING)]),
                IndexModel([("correlation_id", ASCENDING)])
            ]

            collection.create_indexes(indexes)

            logger.info("Explainability ledger v2 indexes created")

        except Exception as e:
            logger.warning(
                "Failed to create indexes for explainability ledger v2",
                error=str(e)
            )

    def persist(
        self,
        explainability_data: Dict[str, Any],
        specialist_type: str,
        correlation_id: Optional[str] = None
    ) -> str:
        """
        Persiste explicação completa no ledger.

        Args:
            explainability_data: Dicionário com todos os dados da explicação
            specialist_type: Tipo do especialista
            correlation_id: ID de correlação

        Returns:
            Token único da explicação
        """
        try:
            # Gerar token baseado em hash dos inputs
            token = self._generate_token(explainability_data)

            # Criar registro versionado
            record = ExplainabilityRecordSchema(
                explainability_token=token,
                plan_id=explainability_data['plan_id'],
                specialist_type=specialist_type,
                explanation_method=explainability_data['explanation_method'],
                input_features=explainability_data['input_features'],
                feature_names=explainability_data['feature_names'],
                model_version=explainability_data['model_version'],
                model_type=explainability_data['model_type'],
                feature_importances=explainability_data['feature_importances'],
                human_readable_summary=explainability_data['human_readable_summary'],
                detailed_narrative=explainability_data['detailed_narrative'],
                prediction=explainability_data['prediction'],
                computation_time_ms=explainability_data['computation_time_ms'],
                background_dataset_hash=explainability_data.get('background_dataset_hash'),
                random_seed=explainability_data.get('random_seed'),
                num_samples=explainability_data.get('num_samples'),
                correlation_id=correlation_id
            )

            # Persistir
            db = self.mongo_client[self.config.mongodb_database]
            collection = db['explainability_ledger_v2']

            collection.insert_one(record.model_dump(by_alias=True))

            logger.info(
                "Explainability record persisted",
                token=token,
                method=explainability_data['explanation_method']
            )

            return token

        except Exception as e:
            logger.error(
                "Failed to persist explainability record",
                error=str(e),
                exc_info=True
            )
            raise

    def _generate_token(self, explainability_data: Dict[str, Any]) -> str:
        """
        Gera token único baseado em hash dos inputs.

        Args:
            explainability_data: Dados da explicação

        Returns:
            Token SHA-256
        """
        # Criar string determinística dos inputs
        input_str = json.dumps({
            'plan_id': explainability_data['plan_id'],
            'input_features': explainability_data['input_features'],
            'model_version': explainability_data['model_version'],
            'timestamp': datetime.utcnow().isoformat()
        }, sort_keys=True)

        # Gerar hash SHA-256
        token = hashlib.sha256(input_str.encode('utf-8')).hexdigest()

        return token

    def retrieve(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Recupera explicação completa por token.

        Args:
            token: Token da explicação

        Returns:
            Documento de explicação ou None
        """
        try:
            db = self.mongo_client[self.config.mongodb_database]
            collection = db['explainability_ledger_v2']

            document = collection.find_one({'explainability_token': token})

            if document:
                document.pop('_id', None)
                return document

            return None

        except Exception as e:
            logger.error(
                "Failed to retrieve explainability record",
                token=token,
                error=str(e)
            )
            return None

    def query_by_plan(self, plan_id: str) -> List[Dict[str, Any]]:
        """
        Recupera todas as explicações de um plano.

        Args:
            plan_id: ID do plano cognitivo

        Returns:
            Lista de explicações
        """
        try:
            db = self.mongo_client[self.config.mongodb_database]
            collection = db['explainability_ledger_v2']

            cursor = collection.find({'plan_id': plan_id}).sort('created_at', -1)
            documents = list(cursor)

            # Remover _id
            for doc in documents:
                doc.pop('_id', None)

            return documents

        except Exception as e:
            logger.error(
                "Failed to query explanations by plan",
                plan_id=plan_id,
                error=str(e)
            )
            return []

    def query_by_specialist(
        self,
        specialist_type: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Recupera explicações por tipo de especialista.

        Args:
            specialist_type: Tipo do especialista
            limit: Limite de resultados

        Returns:
            Lista de explicações
        """
        try:
            db = self.mongo_client[self.config.mongodb_database]
            collection = db['explainability_ledger_v2']

            cursor = collection.find({'specialist_type': specialist_type}) \
                               .sort('created_at', -1) \
                               .limit(limit)

            documents = list(cursor)

            for doc in documents:
                doc.pop('_id', None)

            return documents

        except Exception as e:
            logger.error(
                "Failed to query explanations by specialist",
                specialist_type=specialist_type,
                error=str(e)
            )
            return []

    def validate_schema(self, document: Dict[str, Any]) -> bool:
        """
        Valida documento contra schema v2.

        Args:
            document: Documento a validar

        Returns:
            True se válido, False caso contrário
        """
        try:
            ExplainabilityRecordSchema(**document)
            return True
        except Exception as e:
            logger.warning("Schema validation failed", error=str(e))
            return False
