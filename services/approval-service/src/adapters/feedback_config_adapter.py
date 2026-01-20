"""
Adaptador de configuracao para FeedbackCollector.

Converte Settings do approval-service para SpecialistConfig
esperado pela biblioteca neural_hive_specialists.
"""

from neural_hive_specialists.config import SpecialistConfig
from src.config.settings import Settings


def create_feedback_collector_config(settings: Settings) -> SpecialistConfig:
    """
    Cria SpecialistConfig a partir de Settings do approval service.

    O FeedbackCollector usa SpecialistConfig para acessar MongoDB e validar
    opinioes do ledger cognitivo. Esta funcao mapeia campos do Settings do
    approval service para os campos necessarios do SpecialistConfig.

    Args:
        settings: Settings do approval service

    Returns:
        SpecialistConfig configurado para feedback collection
    """
    # Criar config com campos necessarios para FeedbackCollector
    # Campos nao usados pelo FeedbackCollector recebem placeholders
    config_dict = {
        # Identificacao
        'specialist_type': 'approval_service',
        'service_name': settings.service_name,
        'specialist_version': settings.service_version,
        'environment': settings.environment,
        'log_level': settings.log_level,

        # MLflow (placeholders - nao usado pelo FeedbackCollector)
        'mlflow_tracking_uri': 'http://mlflow:5000',
        'mlflow_experiment_name': 'approval_feedback',
        'mlflow_model_name': 'approval_feedback',

        # MongoDB (usado pelo FeedbackCollector)
        'mongodb_uri': settings.mongodb_uri,
        'mongodb_database': settings.mongodb_database,
        'mongodb_opinions_collection': settings.mongodb_opinions_collection,
        'feedback_mongodb_collection': settings.feedback_mongodb_collection,

        # Feedback configuration (usado pelo FeedbackCollector)
        'enable_feedback_collection': settings.enable_feedback_collection,
        'feedback_rating_min': settings.feedback_rating_min,
        'feedback_rating_max': settings.feedback_rating_max,

        # Redis (placeholder - nao usado pelo FeedbackCollector)
        'redis_cluster_nodes': 'redis:6379',

        # Neo4j (placeholders - nao usado pelo FeedbackCollector)
        'neo4j_uri': 'bolt://neo4j:7687',
        'neo4j_password': 'placeholder',

        # Desabilitar features nao necessarias
        'enable_jwt_auth': False,
        'enable_digital_signature': False,
        'enable_field_encryption': False,
        'enable_pii_detection': False,
        'enable_audit_logging': False,
        'enable_tracing': False,
    }

    return SpecialistConfig(**config_dict)
