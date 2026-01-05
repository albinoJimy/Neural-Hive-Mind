#!/usr/bin/env python3
"""Script para testar acurácia de modelos em produção."""

import asyncio
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
import numpy as np
from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_anomaly_detector_accuracy(
    mongo_uri: str = 'mongodb://localhost:27017',
    mlflow_uri: str = 'http://localhost:5000',
    model_type: str = 'isolation_forest',
    days_back: int = 7,
    max_samples: int = 1000
) -> Dict[str, Any]:
    """
    Testa acurácia do AnomalyDetector em produção.

    Args:
        mongo_uri: URI do MongoDB
        mlflow_uri: URI do MLflow
        model_type: Tipo do modelo (isolation_forest ou autoencoder)
        days_back: Dias de histórico para testar
        max_samples: Máximo de amostras para teste

    Returns:
        Dict com métricas de acurácia
    """
    from motor.motor_asyncio import AsyncIOMotorClient
    from neural_hive_ml.predictive_models import AnomalyDetector
    from neural_hive_ml.predictive_models.model_registry import ModelRegistry

    # Conectar ao MongoDB
    mongo_client = AsyncIOMotorClient(mongo_uri)
    db = mongo_client.neural_hive

    # Carregar modelo de produção
    model_registry = ModelRegistry(
        tracking_uri=mlflow_uri,
        experiment_prefix='neural-hive-ml'
    )

    detector = AnomalyDetector(
        config={
            'model_name': 'anomaly-detector',
            'model_type': model_type,
            'contamination': 0.05
        },
        model_registry=model_registry
    )

    await detector.initialize()

    if not detector.model:
        logger.error("Modelo não carregado")
        return {'error': 'Modelo não carregado'}

    # Buscar tickets recentes
    cutoff_date = datetime.now() - timedelta(days=days_back)
    cutoff_timestamp = cutoff_date.timestamp()

    cursor = db.execution_tickets.find({
        'status': 'COMPLETED',
        'completed_at': {'$gte': cutoff_timestamp}
    }).limit(max_samples)

    tickets = await cursor.to_list(length=max_samples)

    if len(tickets) < 10:
        logger.warning(f"Poucos tickets para teste: {len(tickets)}")
        return {'error': f'Poucos tickets: {len(tickets)}', 'min_required': 10}

    logger.info(f"Testando com {len(tickets)} tickets")

    # Gerar labels verdadeiros (heurísticas) e predições
    true_labels = []
    predictions = []
    scores = []

    for ticket in tickets:
        # Label verdadeiro (heurística)
        is_anomaly_true = _is_anomaly_heuristic(ticket)
        true_labels.append(-1 if is_anomaly_true else 1)

        # Predição do modelo
        result = await detector.detect_anomaly(ticket)
        is_anomaly_pred = result.get('is_anomaly', False)
        predictions.append(-1 if is_anomaly_pred else 1)
        scores.append(result.get('anomaly_score', 0))

    # Calcular métricas
    precision = precision_score(true_labels, predictions, pos_label=-1, zero_division=0)
    recall = recall_score(true_labels, predictions, pos_label=-1, zero_division=0)
    f1 = f1_score(true_labels, predictions, pos_label=-1, zero_division=0)
    cm = confusion_matrix(true_labels, predictions, labels=[1, -1])

    metrics = {
        'precision': float(precision),
        'recall': float(recall),
        'f1_score': float(f1),
        'total_samples': len(tickets),
        'true_anomalies': sum(1 for l in true_labels if l == -1),
        'predicted_anomalies': sum(1 for p in predictions if p == -1),
        'confusion_matrix': {
            'true_negatives': int(cm[0][0]),
            'false_positives': int(cm[0][1]),
            'false_negatives': int(cm[1][0]),
            'true_positives': int(cm[1][1])
        },
        'model_type': model_type,
        'days_back': days_back
    }

    # Fechar conexões
    mongo_client.close()

    return metrics


def _is_anomaly_heuristic(ticket: Dict[str, Any]) -> bool:
    """
    Heurística para determinar se ticket é anômalo.

    Regras baseadas em padrões conhecidos de anomalias.

    Args:
        ticket: Dados do ticket

    Returns:
        True se é anomalia, False caso contrário
    """
    capabilities_count = len(ticket.get('capabilities', []))
    risk_weight = ticket.get('risk_weight', 0)
    actual_duration = ticket.get('actual_duration_ms', 0)
    estimated_duration = ticket.get('estimated_duration_ms', 1)

    # Regra 1: Capabilities excessivas
    if capabilities_count > 12:
        return True

    # Regra 2: Duração muito diferente da estimada
    if estimated_duration > 0:
        ratio = actual_duration / estimated_duration
        if ratio > 3 or ratio < 0.3:
            return True

    # Regra 3: Alto risco sem retries (suspeito)
    if risk_weight > 75 and ticket.get('retry_count', 0) == 0:
        return True

    # Regra 4: QoS inconsistente com risco
    qos = ticket.get('qos', {})
    if qos.get('consistency') == 'EXACTLY_ONCE' and risk_weight < 30:
        return True

    # Regra 5: Timeout muito próximo da duração
    sla_timeout = ticket.get('sla_timeout_ms', 300000)
    if sla_timeout > 0 and estimated_duration > 0:
        if estimated_duration / sla_timeout > 0.95:
            return True

    return False


def print_metrics(metrics: Dict[str, Any]) -> None:
    """Imprime métricas de forma formatada."""
    print("\n" + "=" * 50)
    print("MÉTRICAS DE ACURÁCIA - ANOMALY DETECTOR")
    print("=" * 50)
    print(f"Modelo: {metrics.get('model_type', 'N/A')}")
    print(f"Período: últimos {metrics.get('days_back', 'N/A')} dias")
    print(f"Total de amostras: {metrics.get('total_samples', 'N/A')}")
    print("-" * 50)
    print(f"Precision: {metrics.get('precision', 0):.3f}")
    print(f"Recall: {metrics.get('recall', 0):.3f}")
    print(f"F1-Score: {metrics.get('f1_score', 0):.3f}")
    print("-" * 50)
    print("Confusion Matrix:")
    cm = metrics.get('confusion_matrix', {})
    print(f"  True Negatives:  {cm.get('true_negatives', 0)}")
    print(f"  False Positives: {cm.get('false_positives', 0)}")
    print(f"  False Negatives: {cm.get('false_negatives', 0)}")
    print(f"  True Positives:  {cm.get('true_positives', 0)}")
    print("-" * 50)
    print(f"Anomalias reais: {metrics.get('true_anomalies', 0)}")
    print(f"Anomalias preditas: {metrics.get('predicted_anomalies', 0)}")
    print("=" * 50 + "\n")

    # Avaliação
    f1 = metrics.get('f1_score', 0)
    if f1 >= 0.80:
        print("✅ EXCELENTE: F1-Score >= 0.80")
    elif f1 >= 0.70:
        print("✓ BOM: F1-Score >= 0.70")
    elif f1 >= 0.60:
        print("⚠ ACEITÁVEL: F1-Score >= 0.60, considere retreinar")
    else:
        print("❌ INSUFICIENTE: F1-Score < 0.60, retreinamento necessário")


async def main():
    parser = argparse.ArgumentParser(description='Testar acurácia de modelos ML')
    parser.add_argument(
        '--mongo-uri',
        default='mongodb://localhost:27017',
        help='URI do MongoDB'
    )
    parser.add_argument(
        '--mlflow-uri',
        default='http://localhost:5000',
        help='URI do MLflow'
    )
    parser.add_argument(
        '--model-type',
        choices=['isolation_forest', 'autoencoder'],
        default='isolation_forest',
        help='Tipo do modelo'
    )
    parser.add_argument(
        '--days-back',
        type=int,
        default=7,
        help='Dias de histórico para teste'
    )
    parser.add_argument(
        '--max-samples',
        type=int,
        default=1000,
        help='Máximo de amostras'
    )

    args = parser.parse_args()

    metrics = await test_anomaly_detector_accuracy(
        mongo_uri=args.mongo_uri,
        mlflow_uri=args.mlflow_uri,
        model_type=args.model_type,
        days_back=args.days_back,
        max_samples=args.max_samples
    )

    if 'error' in metrics:
        logger.error(f"Erro: {metrics['error']}")
        return 1

    print_metrics(metrics)
    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    exit(exit_code)
