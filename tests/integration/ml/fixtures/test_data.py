# -*- coding: utf-8 -*-
"""
Datasets de teste para integração ML.

Fornece dados sintéticos para testes de predição, validação e promoção de modelos.
"""

import datetime
from typing import Dict, List, Any

import numpy as np
import pandas as pd
import pytest


def generate_features_dataset(
    n_samples: int = 1000,
    seed: int = 42
) -> pd.DataFrame:
    """
    Gera dataset sintético de features para predições.

    Args:
        n_samples: Número de amostras
        seed: Seed para reprodutibilidade

    Returns:
        DataFrame com features realistas
    """
    np.random.seed(seed)

    df = pd.DataFrame({
        'task_type_encoded': np.random.randint(0, 5, n_samples),
        'payload_size': np.random.randint(100, 10000, n_samples),
        'complexity_score': np.random.rand(n_samples),
        'priority': np.random.randint(1, 10, n_samples),
        'estimated_duration_ms': np.random.randint(1000, 60000, n_samples),
        'retry_count': np.random.randint(0, 3, n_samples),
        'queue_depth': np.random.randint(0, 100, n_samples),
        'hour_of_day': np.random.randint(0, 24, n_samples),
        'day_of_week': np.random.randint(0, 7, n_samples)
    })

    return df


def generate_prediction_history(
    n_predictions: int = 1000,
    model_name: str = 'duration_predictor',
    model_version: str = 'v1.0',
    mae_target: float = 10.0,
    seed: int = 42
) -> List[Dict[str, Any]]:
    """
    Gera histórico de predições para teste de validação.

    Args:
        n_predictions: Número de predições
        model_name: Nome do modelo
        model_version: Versão do modelo
        mae_target: MAE percentual alvo
        seed: Seed para reprodutibilidade

    Returns:
        Lista de dicts com predições
    """
    np.random.seed(seed)

    predictions = []
    base_time = datetime.datetime.utcnow() - datetime.timedelta(days=7)

    for i in range(n_predictions):
        actual = np.random.randint(1000, 60000)
        # Adiciona erro controlado para atingir MAE alvo
        error_factor = 1 + np.random.randn() * (mae_target / 100)
        predicted = actual * error_factor

        predictions.append({
            'model_name': model_name,
            'model_version': model_version,
            'actual_value': float(actual),
            'predicted_value': float(predicted),
            'error_percent': abs(actual - predicted) / actual * 100,
            'timestamp': base_time + datetime.timedelta(minutes=i),
            'task_type': f'type_{i % 5}',
            'latency_ms': np.random.randint(10, 500),
            'success': np.random.random() > 0.002  # ~0.2% taxa de erro
        })

    return predictions


def generate_shadow_comparisons(
    n_comparisons: int = 100,
    model_name: str = 'duration_predictor',
    prod_version: str = 'v1.0',
    shadow_version: str = 'v2.0',
    agreement_target: float = 0.95,
    seed: int = 42
) -> List[Dict[str, Any]]:
    """
    Gera comparações de shadow mode para testes.

    Args:
        n_comparisons: Número de comparações
        model_name: Nome do modelo
        prod_version: Versão de produção
        shadow_version: Versão shadow
        agreement_target: Taxa de acordo alvo
        seed: Seed para reprodutibilidade

    Returns:
        Lista de dicts com comparações
    """
    np.random.seed(seed)

    comparisons = []
    base_time = datetime.datetime.utcnow() - datetime.timedelta(hours=1)

    for i in range(n_comparisons):
        prod_pred = np.random.randint(1000, 60000)

        # Controla acordo baseado no target
        if np.random.random() < agreement_target:
            # Predição similar (dentro de 15% tolerância)
            diff = np.random.uniform(-0.1, 0.1)
            shadow_pred = prod_pred * (1 + diff)
        else:
            # Predição divergente
            diff = np.random.uniform(0.2, 0.5) * np.random.choice([-1, 1])
            shadow_pred = prod_pred * (1 + diff)

        diff_percent = abs(prod_pred - shadow_pred) / prod_pred * 100
        agreed = diff_percent < 15  # 15% tolerância

        comparisons.append({
            'model_name': model_name,
            'production_version': prod_version,
            'shadow_version': shadow_version,
            'production_prediction': float(prod_pred),
            'shadow_prediction': float(shadow_pred),
            'diff_percent': float(diff_percent),
            'agreed': bool(agreed),  # Convert numpy.bool_ to Python bool
            'created_at': base_time + datetime.timedelta(seconds=i * 10),
            'input_hash': f'hash_{i}',
            'latency_production_ms': int(np.random.randint(10, 100)),
            'latency_shadow_ms': int(np.random.randint(10, 100))
        })

    return comparisons


def generate_validation_metrics(
    model_name: str = 'duration_predictor',
    model_version: str = 'v1.0',
    n_checkpoints: int = 10,
    seed: int = 42
) -> List[Dict[str, Any]]:
    """
    Gera métricas de validação contínua.

    Args:
        model_name: Nome do modelo
        model_version: Versão do modelo
        n_checkpoints: Número de checkpoints
        seed: Seed para reprodutibilidade

    Returns:
        Lista de métricas por checkpoint
    """
    np.random.seed(seed)

    metrics = []
    base_time = datetime.datetime.utcnow() - datetime.timedelta(hours=n_checkpoints)

    for i in range(n_checkpoints):
        metrics.append({
            'model_name': model_name,
            'model_version': model_version,
            'checkpoint_time': base_time + datetime.timedelta(hours=i),
            'mae_percentage': 10.0 + np.random.randn() * 0.5,  # ~10% MAE
            'precision': 0.80 + np.random.randn() * 0.02,
            'error_rate': 0.002 + np.random.random() * 0.001,
            'prediction_count': np.random.randint(900, 1100),
            'p50_latency_ms': np.random.randint(20, 50),
            'p99_latency_ms': np.random.randint(100, 300)
        })

    return metrics


def generate_audit_log_entries(
    request_id: str,
    model_name: str = 'duration_predictor',
    stages: List[str] = None
) -> List[Dict[str, Any]]:
    """
    Gera entradas de log de auditoria para promoção.

    Args:
        request_id: ID da requisição de promoção
        model_name: Nome do modelo
        stages: Lista de estágios a incluir

    Returns:
        Lista de entradas de log
    """
    if stages is None:
        stages = [
            'promotion_initiated',
            'shadow_mode_started',
            'shadow_mode_completed',
            'canary_deployed',
            'canary_validated',
            'rollout_stage_25',
            'rollout_stage_50',
            'rollout_stage_75',
            'rollout_completed'
        ]

    entries = []
    base_time = datetime.datetime.utcnow() - datetime.timedelta(minutes=len(stages))

    for i, stage in enumerate(stages):
        entries.append({
            'request_id': request_id,
            'model_name': model_name,
            'event_type': stage,
            'timestamp': base_time + datetime.timedelta(minutes=i),
            'details': {
                'stage_index': i,
                'status': 'completed'
            }
        })

    return entries


# =============================================================================
# Fixtures Pytest
# =============================================================================

@pytest.fixture
def test_features_dataset() -> pd.DataFrame:
    """
    Fixture: Dataset sintético de features.
    """
    return generate_features_dataset()


@pytest.fixture
def test_features_small() -> pd.DataFrame:
    """
    Fixture: Dataset pequeno para testes rápidos.
    """
    return generate_features_dataset(n_samples=100)


@pytest.fixture
def test_prediction_history() -> List[Dict[str, Any]]:
    """
    Fixture: Histórico de predições para validação.
    """
    return generate_prediction_history()


@pytest.fixture
def test_prediction_history_degraded() -> List[Dict[str, Any]]:
    """
    Fixture: Histórico com performance degradada (MAE alto).
    """
    return generate_prediction_history(mae_target=25.0, seed=99)


@pytest.fixture
def test_shadow_comparisons() -> List[Dict[str, Any]]:
    """
    Fixture: Comparações de shadow mode com alto acordo.
    """
    return generate_shadow_comparisons()


@pytest.fixture
def test_shadow_comparisons_low_agreement() -> List[Dict[str, Any]]:
    """
    Fixture: Comparações de shadow mode com baixo acordo.
    """
    return generate_shadow_comparisons(agreement_target=0.70, seed=99)


@pytest.fixture
def test_validation_metrics() -> List[Dict[str, Any]]:
    """
    Fixture: Métricas de validação contínua.
    """
    return generate_validation_metrics()


@pytest.fixture
def test_audit_log_complete() -> List[Dict[str, Any]]:
    """
    Fixture: Log de auditoria completo de promoção bem-sucedida.
    """
    return generate_audit_log_entries(request_id='test_promotion_complete')


@pytest.fixture
def test_audit_log_rollback() -> List[Dict[str, Any]]:
    """
    Fixture: Log de auditoria com rollback.
    """
    return generate_audit_log_entries(
        request_id='test_promotion_rollback',
        stages=[
            'promotion_initiated',
            'shadow_mode_started',
            'shadow_mode_completed',
            'canary_deployed',
            'degradation_detected',
            'rollback_initiated',
            'rollback_completed'
        ]
    )
