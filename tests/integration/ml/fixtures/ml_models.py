# -*- coding: utf-8 -*-
"""
Modelos ML mock para testes de integração.

Fornece modelos treinados para predição de duração e detecção de anomalias.
"""

import numpy as np
import pytest
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.preprocessing import StandardScaler
from typing import Tuple, Any


def create_duration_predictor(seed: int = 42, n_estimators: int = 10) -> RandomForestRegressor:
    """
    Cria um RandomForestRegressor treinado para predição de duração.

    Args:
        seed: Seed para reprodutibilidade
        n_estimators: Número de árvores

    Returns:
        Modelo treinado

    Features esperadas:
        - task_type_encoded (int): Tipo de tarefa codificado (0-4)
        - payload_size (int): Tamanho do payload em bytes
        - complexity_score (float): Score de complexidade (0-1)

    Target:
        - duration_ms (float): Duração esperada em milissegundos
    """
    np.random.seed(seed)
    n_samples = 1000

    # Gera features sintéticas
    X_train = np.random.rand(n_samples, 3)

    # Gera target com relação conhecida com features
    # duration = f(task_type, payload, complexity) + ruído
    y_train = (
        X_train[:, 0] * 5000 +      # task_type contribui até 5s
        X_train[:, 1] * 2000 +      # payload contribui até 2s
        X_train[:, 2] * 3000 +      # complexity contribui até 3s
        np.random.randn(n_samples) * 500  # ruído ~500ms
    )

    # Treina modelo
    model = RandomForestRegressor(n_estimators=n_estimators, random_state=seed)
    model.fit(X_train, y_train)

    return model


def create_anomaly_detector(seed: int = 42, contamination: float = 0.1) -> IsolationForest:
    """
    Cria um IsolationForest treinado para detecção de anomalias.

    Args:
        seed: Seed para reprodutibilidade
        contamination: Fração esperada de anomalias

    Returns:
        Modelo treinado

    Features esperadas:
        - latency_ms (float): Latência da requisição
        - error_count (int): Contagem de erros
        - payload_size (int): Tamanho do payload
        - complexity_score (float): Score de complexidade
        - resource_usage (float): Uso de recursos (0-1)
    """
    np.random.seed(seed)
    n_samples = 1000

    # Gera dados normais
    X_train = np.random.randn(n_samples, 5)

    # Treina modelo
    model = IsolationForest(contamination=contamination, random_state=seed)
    model.fit(X_train)

    return model


def create_model_pair(seed_v1: int = 42, seed_v2: int = 43) -> Tuple[RandomForestRegressor, RandomForestRegressor]:
    """
    Cria par de modelos para teste de shadow mode.

    Os modelos são similares mas não idênticos, permitindo testar
    taxa de acordo entre versões.

    Args:
        seed_v1: Seed para versão 1 (produção)
        seed_v2: Seed para versão 2 (candidato)

    Returns:
        Tupla (model_v1, model_v2)
    """
    model_v1 = create_duration_predictor(seed=seed_v1)
    model_v2 = create_duration_predictor(seed=seed_v2)

    return model_v1, model_v2


def create_divergent_model(seed: int = 999) -> RandomForestRegressor:
    """
    Cria modelo que produz predições muito diferentes.

    Usado para testar cenário de baixa taxa de acordo no shadow mode.

    Args:
        seed: Seed para reprodutibilidade

    Returns:
        Modelo treinado com distribuição diferente
    """
    np.random.seed(seed)
    n_samples = 1000

    # Gera features com distribuição diferente
    X_train = np.random.rand(n_samples, 3) * 2  # Escala diferente

    # Relação diferente com target
    y_train = (
        X_train[:, 0] * 10000 +     # Peso diferente
        X_train[:, 1] * 500 +
        X_train[:, 2] * 8000 +
        np.random.randn(n_samples) * 2000  # Mais ruído
    )

    model = RandomForestRegressor(n_estimators=5, random_state=seed)
    model.fit(X_train, y_train)

    return model


# =============================================================================
# Fixtures Pytest
# =============================================================================

@pytest.fixture
def mock_duration_predictor() -> RandomForestRegressor:
    """
    Fixture: RandomForestRegressor treinado para predição de duração.
    """
    return create_duration_predictor()


@pytest.fixture
def mock_duration_predictor_v2() -> RandomForestRegressor:
    """
    Fixture: Versão 2 do modelo de duração (similar à v1).
    """
    return create_duration_predictor(seed=43)


@pytest.fixture
def mock_anomaly_detector() -> IsolationForest:
    """
    Fixture: IsolationForest para detecção de anomalias.
    """
    return create_anomaly_detector()


@pytest.fixture
def mock_model_pair() -> Tuple[RandomForestRegressor, RandomForestRegressor]:
    """
    Fixture: Par de modelos para teste de shadow mode.
    """
    return create_model_pair()


@pytest.fixture
def mock_divergent_model() -> RandomForestRegressor:
    """
    Fixture: Modelo divergente para teste de baixa taxa de acordo.
    """
    return create_divergent_model()


@pytest.fixture
def model_with_scaler() -> Tuple[RandomForestRegressor, StandardScaler]:
    """
    Fixture: Modelo com scaler associado para normalização de features.
    """
    np.random.seed(42)
    n_samples = 1000

    X_raw = np.column_stack([
        np.random.randint(0, 5, n_samples),           # task_type
        np.random.randint(100, 10000, n_samples),     # payload_size
        np.random.rand(n_samples)                      # complexity
    ])

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_raw)

    y = (
        X_scaled[:, 0] * 1000 +
        X_scaled[:, 1] * 500 +
        X_scaled[:, 2] * 800 +
        np.random.randn(n_samples) * 200
    )

    model = RandomForestRegressor(n_estimators=10, random_state=42)
    model.fit(X_scaled, y)

    return model, scaler
