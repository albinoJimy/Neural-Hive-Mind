"""
Feature Engineering para ML Predictions.

Utilitários compartilhados para extração e normalização de features de tickets
para modelos de predição de duração e detecção de anomalias.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


def encode_risk_band(risk_band: str) -> float:
    """
    Codifica risk_band como valor numérico.

    Args:
        risk_band: String representando banda de risco

    Returns:
        Peso numérico: critical=1.0, high=0.7, medium=0.5, low=0.3
    """
    risk_weights = {
        'critical': 1.0,
        'high': 0.7,
        'medium': 0.5,
        'low': 0.3
    }
    return risk_weights.get(risk_band.lower() if risk_band else 'medium', 0.5)


def encode_qos(qos: Dict[str, Any]) -> Dict[str, float]:
    """
    Codifica campos de QoS como scores numéricos.

    Args:
        qos: Dicionário com campos delivery_mode, consistency, durability
             (ou delivery_guarantee/consistency_level para compatibilidade)

    Returns:
        Dict com delivery_score (0.5-1.0), consistency_score (0.85-1.0), durability_score (0.9-1.0)
    """
    delivery_map = {
        'at_least_once': 0.5,
        'at_most_once': 0.6,
        'exactly_once': 1.0
    }

    consistency_map = {
        'eventual': 0.85,
        'strong': 1.0,
        'causal': 0.95
    }

    durability_map = {
        'ephemeral': 0.9,
        'transient': 0.9,
        'persistent': 1.0
    }

    # Suporta tanto formato novo (delivery_mode, consistency) quanto antigo (delivery_guarantee, consistency_level)
    if qos:
        delivery = qos.get('delivery_mode') or qos.get('delivery_guarantee', 'at_least_once')
        consistency = qos.get('consistency') or qos.get('consistency_level', 'eventual')
        durability = qos.get('durability', 'persistent')
    else:
        delivery = 'at_least_once'
        consistency = 'eventual'
        durability = 'persistent'

    # Normaliza para minúsculas
    delivery = delivery.lower() if isinstance(delivery, str) else 'at_least_once'
    consistency = consistency.lower() if isinstance(consistency, str) else 'eventual'
    durability = durability.lower() if isinstance(durability, str) else 'persistent'

    return {
        'delivery_score': delivery_map.get(delivery, 0.5),
        'consistency_score': consistency_map.get(consistency, 0.85),
        'durability_score': durability_map.get(durability, 1.0)
    }


def encode_task_type(task_type: str) -> int:
    """
    Codifica task_type como valor numérico.

    Args:
        task_type: String representando tipo de tarefa

    Returns:
        Código numérico: BUILD=0, DEPLOY=1, TEST=2, VALIDATE=3, EXECUTE=4
    """
    task_type_map = {
        'BUILD': 0,
        'DEPLOY': 1,
        'TEST': 2,
        'VALIDATE': 3,
        'EXECUTE': 4,
        'PLAN': 5,
        'CONSOLIDATE': 6
    }
    return task_type_map.get(task_type.upper() if task_type else 'EXECUTE', 4)


def extract_ticket_features(
    ticket: Dict[str, Any],
    historical_stats: Optional[Dict] = None
) -> Dict[str, float]:
    """
    Extrai features de um ticket para modelos de ML.

    Features extraídas (15+):
    - risk_weight: Peso numérico da banda de risco (0.3-1.0)
    - qos_delivery_score: Score de garantia de entrega (0.5-1.0)
    - qos_consistency_score: Score de consistência (0.85-1.0)
    - qos_durability_score: Score de durabilidade (0.9-1.0)
    - capabilities_count: Número de capabilities requeridas
    - task_type_encoded: Tipo de tarefa codificado (0-6)
    - parameters_size: Tamanho do dict de parâmetros
    - estimated_duration_ms: Duração estimada do ticket
    - sla_timeout_ms: Timeout de SLA
    - avg_duration_by_task: Duração média histórica por task_type
    - avg_duration_by_risk: Duração média histórica por risk_band
    - success_rate_by_task: Taxa de sucesso histórica por task_type
    - std_duration_by_task: Desvio padrão da duração por task_type
    - retry_count: Número de retries do ticket
    - hour_of_day: Hora do dia da criação (0-23)

    Args:
        ticket: Dicionário com dados do ticket
        historical_stats: Estatísticas históricas agregadas (opcional)

    Returns:
        Dicionário com features extraídas
    """
    try:
        # Features básicas do ticket
        risk_band = ticket.get('risk_band', 'medium')
        task_type = ticket.get('task_type', 'EXECUTE')
        qos = ticket.get('qos', {})

        # Codificações
        risk_weight = encode_risk_band(risk_band)
        qos_scores = encode_qos(qos)
        task_type_code = encode_task_type(task_type)

        # Contagens e tamanhos
        capabilities = ticket.get('required_capabilities', [])
        capabilities_count = len(capabilities) if isinstance(capabilities, list) else 0

        parameters = ticket.get('parameters', {})
        parameters_size = len(str(parameters)) if parameters else 0

        # Duração e SLA
        estimated_duration_ms = float(ticket.get('estimated_duration_ms', 60000))
        sla = ticket.get('sla', {})
        sla_timeout_ms = float(sla.get('timeout_ms', 300000)) if isinstance(sla, dict) else 300000.0

        # Retry count
        retry_count = int(ticket.get('retry_count', 0))

        # Hora do dia (para capturar padrões temporais)
        created_at = ticket.get('created_at')
        hour_of_day = 12  # default
        if created_at:
            if isinstance(created_at, str):
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    hour_of_day = dt.hour
                except:
                    pass
            elif isinstance(created_at, datetime):
                hour_of_day = created_at.hour
            elif isinstance(created_at, (int, float)):
                try:
                    # Converte timestamp em milissegundos para datetime
                    dt = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc)
                    hour_of_day = dt.hour
                except:
                    pass

        # Features históricas (se disponíveis)
        avg_duration_by_task = 60000.0
        avg_duration_by_risk = 60000.0
        success_rate_by_task = 0.95
        std_duration_by_task = 15000.0

        if historical_stats:
            task_stats = historical_stats.get(task_type, {})
            risk_stats = task_stats.get(risk_band, {})

            avg_duration_by_task = float(risk_stats.get('avg_duration_ms', 60000.0))
            avg_duration_by_risk = avg_duration_by_task  # mesmo valor para simplificar
            success_rate_by_task = float(risk_stats.get('success_rate', 0.95))
            std_duration_by_task = float(risk_stats.get('std_duration_ms', 15000.0))

        features = {
            'risk_weight': risk_weight,
            'qos_delivery_score': qos_scores['delivery_score'],
            'qos_consistency_score': qos_scores['consistency_score'],
            'qos_durability_score': qos_scores['durability_score'],
            'capabilities_count': float(capabilities_count),
            'task_type_encoded': float(task_type_code),
            'parameters_size': float(parameters_size),
            'estimated_duration_ms': estimated_duration_ms,
            'sla_timeout_ms': sla_timeout_ms,
            'avg_duration_by_task': avg_duration_by_task,
            'avg_duration_by_risk': avg_duration_by_risk,
            'success_rate_by_task': success_rate_by_task,
            'std_duration_by_task': std_duration_by_task,
            'retry_count': float(retry_count),
            'hour_of_day': float(hour_of_day)
        }

        return features

    except Exception as e:
        logger.warning("feature_extraction_failed", error=str(e), ticket_id=ticket.get('ticket_id'))
        # Retorna features default em caso de erro
        return {
            'risk_weight': 0.5,
            'qos_delivery_score': 0.5,
            'qos_consistency_score': 0.85,
            'qos_durability_score': 1.0,
            'capabilities_count': 1.0,
            'task_type_encoded': 4.0,
            'parameters_size': 100.0,
            'estimated_duration_ms': 60000.0,
            'sla_timeout_ms': 300000.0,
            'avg_duration_by_task': 60000.0,
            'avg_duration_by_risk': 60000.0,
            'success_rate_by_task': 0.95,
            'std_duration_by_task': 15000.0,
            'retry_count': 0.0,
            'hour_of_day': 12.0
        }


def normalize_features(features: Dict[str, float]) -> np.ndarray:
    """
    Converte dict de features para array numpy com ordenação consistente.

    Args:
        features: Dicionário com features extraídas

    Returns:
        Array numpy com features na ordem definida
    """
    # Ordem consistente de features
    feature_order = [
        'risk_weight',
        'qos_delivery_score',
        'qos_consistency_score',
        'qos_durability_score',
        'capabilities_count',
        'task_type_encoded',
        'parameters_size',
        'estimated_duration_ms',
        'sla_timeout_ms',
        'avg_duration_by_task',
        'avg_duration_by_risk',
        'success_rate_by_task',
        'std_duration_by_task',
        'retry_count',
        'hour_of_day'
    ]

    # Extrai valores na ordem definida
    values = [features.get(f, 0.0) for f in feature_order]

    return np.array(values, dtype=np.float64).reshape(1, -1)


async def compute_historical_stats(
    mongodb_client,
    window_days: int = 30,
    clickhouse_client=None
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Computa estatísticas históricas agregadas por task_type e risk_band.

    Prioriza ClickHouse se disponível (10x mais rápido para agregações).
    Fallback para MongoDB se ClickHouse não disponível.

    Agrega:
    - avg_duration_ms: Duração média
    - success_rate: Taxa de sucesso (status=COMPLETED)
    - std_duration_ms: Desvio padrão da duração
    - p50/p95/p99_duration_ms: Percentis (apenas ClickHouse)

    Args:
        mongodb_client: Cliente MongoDB configurado
        window_days: Janela de dados em dias (default: 30)
        clickhouse_client: Cliente ClickHouse opcional (preferido se disponível)

    Returns:
        Dict aninhado: {task_type: {risk_band: {avg_duration_ms, success_rate, std_duration_ms, ...}}}
    """
    # Tenta ClickHouse primeiro (mais rápido para agregações)
    if clickhouse_client is not None:
        try:
            stats = await clickhouse_client.query_duration_stats_by_task_type(window_days)
            if stats:
                logger.info(
                    "historical_stats_computed_from_clickhouse",
                    window_days=window_days,
                    task_types=len(stats)
                )
                return stats
        except Exception as e:
            logger.warning(
                "clickhouse_stats_failed_fallback_mongodb",
                error=str(e)
            )

    # Fallback para MongoDB
    try:
        # Calcula data limite
        cutoff_date = datetime.utcnow() - timedelta(days=window_days)

        # Pipeline de agregação MongoDB
        pipeline = [
            {
                '$match': {
                    'completed_at': {'$gte': cutoff_date},
                    'actual_duration_ms': {'$exists': True, '$ne': None}
                }
            },
            {
                '$group': {
                    '_id': {
                        'task_type': '$task_type',
                        'risk_band': '$risk_band'
                    },
                    'avg_duration_ms': {'$avg': '$actual_duration_ms'},
                    'std_duration_ms': {'$stdDevPop': '$actual_duration_ms'},
                    'total_count': {'$sum': 1},
                    'success_count': {
                        '$sum': {
                            '$cond': [
                                {'$eq': ['$status', 'COMPLETED']},
                                1,
                                0
                            ]
                        }
                    }
                }
            }
        ]

        # Executa agregação
        results = await mongodb_client.db['execution_tickets'].aggregate(pipeline).to_list(None)

        # Constrói dict aninhado
        stats = {}
        for result in results:
            task_type = result['_id']['task_type']
            risk_band = result['_id']['risk_band']

            if task_type not in stats:
                stats[task_type] = {}

            success_rate = result['success_count'] / result['total_count'] if result['total_count'] > 0 else 0.0

            stats[task_type][risk_band] = {
                'avg_duration_ms': float(result.get('avg_duration_ms', 60000.0)),
                'std_duration_ms': float(result.get('std_duration_ms', 15000.0)),
                'success_rate': float(success_rate),
                'sample_count': int(result['total_count'])
            }

        logger.info(
            "historical_stats_computed",
            window_days=window_days,
            task_types=len(stats),
            total_groups=len(results)
        )

        return stats

    except Exception as e:
        logger.error("historical_stats_computation_failed", error=str(e))
        # Retorna dict vazio em caso de erro (features usarão defaults)
        return {}


async def compute_historical_stats_from_clickhouse(
    clickhouse_client,
    window_days: int = 30
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Computa estatísticas históricas usando exclusivamente ClickHouse.

    Features adicionais disponíveis via ClickHouse:
    - p50/p95/p99_duration_ms: Percentis de duração
    - min/max_duration_ms: Valores extremos

    Args:
        clickhouse_client: Cliente ClickHouse configurado
        window_days: Janela de dados em dias (default: 30)

    Returns:
        Dict aninhado com estatísticas enriquecidas
    """
    try:
        stats = await clickhouse_client.query_duration_stats_by_task_type(window_days)

        logger.info(
            "historical_stats_from_clickhouse",
            window_days=window_days,
            task_types=len(stats)
        )

        return stats

    except Exception as e:
        logger.error("clickhouse_historical_stats_failed", error=str(e))
        return {}
