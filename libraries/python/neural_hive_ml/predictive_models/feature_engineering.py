"""Utilitários de engenharia de features compartilhados."""

from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def extract_ticket_features(
    ticket: Dict[str, Any],
    historical_stats: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Extrai features de um ticket para ML.

    Args:
        ticket: Dados do ticket
        historical_stats: Estatísticas históricas agregadas

    Returns:
        Dicionário com features extraídas
    """
    historical_stats = historical_stats or {}
    features = {}

    # Features do ticket
    features['risk_weight'] = ticket.get('risk_weight', 0.0)
    features['capabilities_count'] = len(ticket.get('capabilities', []))
    features['parameters_size'] = len(str(ticket.get('parameters', {})))

    # QoS scores
    qos = ticket.get('qos', {})
    features['qos_priority'] = _qos_to_score(qos.get('priority', 'MEDIUM'))
    features['qos_consistency'] = _consistency_to_score(qos.get('consistency', 'AT_LEAST_ONCE'))
    features['qos_durability'] = _durability_to_score(qos.get('durability', 'TRANSIENT'))

    # Task type encoding
    task_type = ticket.get('type', 'UNKNOWN')
    features['task_type_encoded'] = _encode_task_type(task_type)

    # Temporal features
    timestamp = ticket.get('timestamp', datetime.now().isoformat())
    temporal_features = _extract_temporal_features(timestamp)
    features.update(temporal_features)

    # Resource features
    features['estimated_duration_ms'] = ticket.get('estimated_duration_ms', 0)
    features['sla_timeout_ms'] = ticket.get('sla_timeout_ms', 300000)
    features['retry_count'] = ticket.get('retry_count', 0)

    # Historical features
    if historical_stats:
        task_stats = historical_stats.get(task_type, {})
        features['avg_duration_by_task'] = task_stats.get('avg_duration', 0)
        features['std_duration_by_task'] = task_stats.get('std_duration', 0)
        features['success_rate_by_task'] = task_stats.get('success_rate', 1.0)

        risk_band = _risk_to_band(features['risk_weight'])
        risk_stats = historical_stats.get(f'risk_{risk_band}', {})
        features['avg_duration_by_risk'] = risk_stats.get('avg_duration', 0)

    # Derived features
    features['risk_to_capabilities_ratio'] = (
        features['risk_weight'] / max(features['capabilities_count'], 1)
    )
    features['estimated_to_sla_ratio'] = (
        features['estimated_duration_ms'] / max(features['sla_timeout_ms'], 1)
    )

    return features


def normalize_features(features_dict: Dict[str, Any]) -> np.ndarray:
    """
    Normaliza features para range [0, 1].

    Args:
        features_dict: Dicionário de features

    Returns:
        Array numpy normalizado
    """
    feature_names = sorted(features_dict.keys())
    values = np.array([features_dict[name] for name in feature_names])

    # Min-max normalization
    min_vals = np.zeros_like(values)
    max_vals = np.ones_like(values)

    # Define ranges conhecidos para features específicas
    known_ranges = {
        'risk_weight': (0, 100),
        'capabilities_count': (0, 20),
        'qos_priority': (0, 1),
        'qos_consistency': (0, 1),
        'qos_durability': (0, 1),
        'success_rate_by_task': (0, 1),
    }

    for i, name in enumerate(feature_names):
        if name in known_ranges:
            min_vals[i], max_vals[i] = known_ranges[name]

    range_vals = max_vals - min_vals
    range_vals[range_vals == 0] = 1

    normalized = (values - min_vals) / range_vals
    return np.clip(normalized, 0, 1)


def create_feature_vector(
    features: Dict[str, Any],
    feature_names: List[str]
) -> np.ndarray:
    """
    Cria vetor de features ordenado.

    Args:
        features: Dicionário de features
        feature_names: Lista ordenada de nomes de features

    Returns:
        Array numpy com features na ordem especificada
    """
    return np.array([features.get(name, 0.0) for name in feature_names])


async def compute_historical_stats(
    mongodb_client: Any,
    window_days: int = 30
) -> Dict[str, Dict[str, float]]:
    """
    Calcula estatísticas históricas agregadas.

    Args:
        mongodb_client: Cliente MongoDB
        window_days: Janela de tempo em dias

    Returns:
        Dicionário com estatísticas por task_type e risk_band
    """
    try:
        cutoff_date = datetime.now().timestamp() - (window_days * 24 * 3600)

        # Agrega por task_type
        pipeline_task = [
            {"$match": {
                "status": "COMPLETED",
                "completed_at": {"$gte": cutoff_date}
            }},
            {"$group": {
                "_id": "$type",
                "avg_duration": {"$avg": "$actual_duration_ms"},
                "std_duration": {"$stdDevPop": "$actual_duration_ms"},
                "total_count": {"$sum": 1},
                "success_count": {"$sum": {"$cond": [{"$eq": ["$status", "COMPLETED"]}, 1, 0]}}
            }}
        ]

        task_stats = {}
        async for doc in mongodb_client.execution_tickets.aggregate(pipeline_task):
            task_type = doc['_id']
            task_stats[task_type] = {
                'avg_duration': doc.get('avg_duration', 0),
                'std_duration': doc.get('std_duration', 0),
                'success_rate': doc.get('success_count', 0) / max(doc.get('total_count', 1), 1)
            }

        # Agrega por risk_band
        for band in ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']:
            pipeline_risk = [
                {"$match": {
                    "status": "COMPLETED",
                    "completed_at": {"$gte": cutoff_date},
                    "risk_band": band
                }},
                {"$group": {
                    "_id": None,
                    "avg_duration": {"$avg": "$actual_duration_ms"}
                }}
            ]

            async for doc in mongodb_client.execution_tickets.aggregate(pipeline_risk):
                task_stats[f'risk_{band}'] = {
                    'avg_duration': doc.get('avg_duration', 0)
                }

        return task_stats

    except Exception as e:
        logger.error(f"Erro ao calcular estatísticas históricas: {e}")
        return {}


def get_feature_importance(
    model: Any,
    feature_names: List[str]
) -> Dict[str, float]:
    """
    Extrai importância de features de modelos baseados em árvore.

    Args:
        model: Modelo treinado
        feature_names: Lista de nomes das features

    Returns:
        Dicionário com importância de cada feature
    """
    if not hasattr(model, 'feature_importances_'):
        return {}

    importances = model.feature_importances_
    return {
        name: float(imp)
        for name, imp in zip(feature_names, importances)
    }


# Funções auxiliares privadas

def _qos_to_score(priority: str) -> float:
    """Converte prioridade QoS para score numérico."""
    priority_map = {
        'LOW': 0.25,
        'MEDIUM': 0.50,
        'HIGH': 0.75,
        'CRITICAL': 1.0
    }
    return priority_map.get(priority, 0.5)


def _consistency_to_score(consistency: str) -> float:
    """Converte nível de consistência para score numérico."""
    consistency_map = {
        'AT_MOST_ONCE': 0.33,
        'AT_LEAST_ONCE': 0.67,
        'EXACTLY_ONCE': 1.0
    }
    return consistency_map.get(consistency, 0.67)


def _durability_to_score(durability: str) -> float:
    """Converte nível de durabilidade para score numérico."""
    durability_map = {
        'TRANSIENT': 0.5,
        'PERSISTENT': 1.0
    }
    return durability_map.get(durability, 0.5)


def _encode_task_type(task_type: str) -> int:
    """Codifica task_type como inteiro."""
    task_type_map = {
        'ANALYSIS': 1,
        'OPTIMIZATION': 2,
        'VALIDATION': 3,
        'EXECUTION': 4,
        'MONITORING': 5,
        'UNKNOWN': 0
    }
    return task_type_map.get(task_type, 0)


def _extract_temporal_features(timestamp: str) -> Dict[str, float]:
    """Extrai features temporais de timestamp."""
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except Exception:
        dt = datetime.now()

    return {
        'hour_of_day': dt.hour / 24.0,
        'day_of_week': dt.weekday() / 7.0,
        'is_weekend': 1.0 if dt.weekday() >= 5 else 0.0,
        'is_business_hours': 1.0 if 9 <= dt.hour <= 18 else 0.0
    }


def _risk_to_band(risk_weight: float) -> str:
    """Converte risk_weight para banda de risco."""
    if risk_weight < 25:
        return 'LOW'
    elif risk_weight < 50:
        return 'MEDIUM'
    elif risk_weight < 75:
        return 'HIGH'
    else:
        return 'CRITICAL'
