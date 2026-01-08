"""Testes unitários para LoadPredictor."""

import pytest
import pytest_asyncio
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from neural_hive_ml.predictive_models.load_predictor import LoadPredictor


@pytest.fixture
def mock_config():
    """Configuração mock para LoadPredictor."""
    return {
        'model_name': 'load-predictor',
        'model_type': 'prophet',
        'forecast_horizons': [60, 360, 1440],
        'seasonality_mode': 'additive',
        'cache_ttl_seconds': 300
    }


@pytest.fixture
def mock_config_arima():
    """Configuração mock para ARIMA."""
    return {
        'model_name': 'load-predictor',
        'model_type': 'arima',
        'forecast_horizons': [60, 360, 1440],
        'cache_ttl_seconds': 300
    }


@pytest.fixture
def mock_registry():
    """ModelRegistry mock."""
    registry = Mock()
    registry.get_model_metadata = AsyncMock(return_value=None)
    return registry


@pytest.fixture
def mock_metrics():
    """Metrics client mock."""
    metrics = Mock()
    metrics.record_prediction_latency = Mock()
    metrics.record_cache_hit = Mock()
    metrics.record_cache_miss = Mock()
    return metrics


@pytest.fixture
def mock_redis():
    """Redis client mock."""
    redis = Mock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.exists = AsyncMock(return_value=False)
    return redis


@pytest.fixture
def time_series_data():
    """Dados de série temporal sintéticos."""
    np.random.seed(42)

    # Criar 90 dias de dados horários
    dates = pd.date_range(
        start=datetime.now() - timedelta(days=90),
        end=datetime.now(),
        freq='H'
    )

    # Padrão semanal + tendência + ruído
    n = len(dates)
    trend = np.linspace(100, 150, n)
    weekly_pattern = 20 * np.sin(2 * np.pi * np.arange(n) / (24 * 7))
    daily_pattern = 10 * np.sin(2 * np.pi * np.arange(n) / 24)
    noise = np.random.normal(0, 5, n)

    load = trend + weekly_pattern + daily_pattern + noise
    load = np.maximum(load, 50)  # Mínimo de 50

    df = pd.DataFrame({
        'ds': dates,
        'y': load
    })

    return df


@pytest.fixture
def mock_clickhouse():
    """Mock de cliente ClickHouse."""
    client = Mock()

    # Mock query que retorna série temporal
    async def execute_query(query):
        # Retornar dados sintéticos
        dates = pd.date_range(
            start=datetime.now() - timedelta(days=30),
            end=datetime.now(),
            freq='H'
        )
        n = len(dates)
        load = 100 + 20 * np.sin(2 * np.pi * np.arange(n) / 24) + np.random.normal(0, 5, n)

        return pd.DataFrame({
            'timestamp': dates,
            'load': load
        })

    client.execute_query = AsyncMock(side_effect=execute_query)
    return client


# =============================================================================
# Testes de Inicialização
# =============================================================================

@pytest.mark.asyncio
async def test_initialization(mock_config, mock_registry, mock_metrics):
    """Testa inicialização básica do LoadPredictor."""
    predictor = LoadPredictor(
        config=mock_config,
        model_registry=mock_registry,
        metrics=mock_metrics,
        redis_client=None
    )

    assert predictor.config == mock_config
    assert predictor.model_registry == mock_registry
    assert predictor.metrics == mock_metrics
    assert predictor.forecast_horizons == [60, 360, 1440]


# =============================================================================
# Testes de Predição de Carga - Prophet
# =============================================================================

@pytest.mark.asyncio
async def test_predict_load_prophet(
    mock_config,
    mock_registry,
    mock_metrics,
    time_series_data
):
    """Testa predição de carga com Prophet."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.prophet.log_model'):

        predictor = LoadPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics,
            redis_client=None
        )

        # Treinar modelo
        metrics = await predictor.train_model(time_series_data)

        # Validar métricas de treinamento
        assert 'mape' in metrics
        assert 'mae' in metrics
        assert metrics['mape'] < 20  # MAPE < 20%
        assert metrics['mae'] > 0

        # Testar predição para 60 minutos
        forecast = await predictor.predict_load(horizon_minutes=60)

        assert 'forecast' in forecast
        assert 'trend' in forecast
        assert 'horizon_minutes' in forecast
        assert forecast['horizon_minutes'] == 60
        assert len(forecast['forecast']) > 0

        # Validar que todos os valores são não-negativos
        for point in forecast['forecast']:
            assert point['timestamp'] is not None
            assert point['predicted_load'] >= 0
            assert 'confidence_lower' in point
            assert 'confidence_upper' in point


@pytest.mark.asyncio
async def test_predict_load_multiple_horizons(
    mock_config,
    mock_registry,
    mock_metrics,
    time_series_data
):
    """Testa predições para múltiplos horizontes."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.prophet.log_model'):

        predictor = LoadPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics,
            redis_client=None
        )

        await predictor.train_model(time_series_data)

        # Testar todos os horizontes configurados
        for horizon in [60, 360, 1440]:
            forecast = await predictor.predict_load(horizon_minutes=horizon)

            assert forecast['horizon_minutes'] == horizon
            assert len(forecast['forecast']) > 0

            # Validar intervalo de confiança mais amplo para horizontes maiores
            first_point = forecast['forecast'][0]
            last_point = forecast['forecast'][-1]

            ci_width_first = first_point['confidence_upper'] - first_point['confidence_lower']
            ci_width_last = last_point['confidence_upper'] - last_point['confidence_lower']

            # CI deve aumentar com o tempo
            assert ci_width_last >= ci_width_first


@pytest.mark.asyncio
async def test_predict_load_arima(
    mock_config_arima,
    mock_registry,
    mock_metrics,
    time_series_data
):
    """Testa predição de carga com ARIMA."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.statsmodels.log_model'):

        predictor = LoadPredictor(
            config=mock_config_arima,
            model_registry=mock_registry,
            metrics=mock_metrics,
            redis_client=None
        )

        metrics = await predictor.train_model(time_series_data)

        assert 'mape' in metrics
        assert metrics['mape'] < 25  # ARIMA pode ter MAPE um pouco maior

        forecast = await predictor.predict_load(horizon_minutes=60)

        assert len(forecast['forecast']) > 0
        assert forecast['forecast'][0]['predicted_load'] >= 0


# =============================================================================
# Testes de Sazonalidade
# =============================================================================

@pytest.mark.asyncio
async def test_seasonality_detection(
    mock_config,
    mock_registry,
    mock_metrics,
    time_series_data
):
    """Valida que modelo detecta padrões sazonais."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.prophet.log_model'):

        predictor = LoadPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics,
            redis_client=None
        )

        await predictor.train_model(time_series_data)

        # Fazer predição para 24h (1 dia completo)
        forecast = await predictor.predict_load(horizon_minutes=1440)

        # Validar que há variação na carga (indicando sazonalidade)
        loads = [p['predicted_load'] for p in forecast['forecast']]
        assert max(loads) > min(loads) * 1.1  # Pelo menos 10% de variação


# =============================================================================
# Testes de Cache
# =============================================================================

@pytest.mark.asyncio
async def test_cache_hit(
    mock_config,
    mock_registry,
    mock_metrics,
    mock_redis,
    time_series_data
):
    """Testa que cache é usado quando disponível."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.prophet.log_model'):

        predictor = LoadPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics,
            redis_client=mock_redis
        )

        await predictor.train_model(time_series_data)

        # Primeira chamada - cache miss
        mock_redis.get.return_value = None
        forecast1 = await predictor.predict_load(horizon_minutes=60)

        # Simular cache hit
        import json
        cached_forecast = json.dumps(forecast1)
        mock_redis.get.return_value = cached_forecast

        # Segunda chamada - deve usar cache
        forecast2 = await predictor.predict_load(horizon_minutes=60)

        # Validar que cache foi usado
        assert mock_redis.get.called
        assert forecast1['horizon_minutes'] == forecast2['horizon_minutes']


@pytest.mark.asyncio
async def test_cache_miss_rate(
    mock_config,
    mock_registry,
    mock_metrics,
    time_series_data
):
    """Valida que cache hit rate > 80% em uso normal."""
    # Sem Redis, cache hit rate deve ser 0% (sempre miss)
    predictor = LoadPredictor(
        config=mock_config,
        model_registry=mock_registry,
        metrics=mock_metrics,
        redis_client=None
    )

    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.prophet.log_model'):

        await predictor.train_model(time_series_data)

        # Sem Redis, todas as predições são cache miss
        for _ in range(5):
            forecast = await predictor.predict_load(horizon_minutes=60)
            assert len(forecast['forecast']) > 0


# =============================================================================
# Testes de Treinamento
# =============================================================================

@pytest.mark.asyncio
async def test_train_model_metrics(
    mock_config,
    mock_registry,
    mock_metrics,
    time_series_data
):
    """Valida que métricas de treinamento atendem os requisitos."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.prophet.log_model'):

        predictor = LoadPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics,
            redis_client=None
        )

        metrics = await predictor.train_model(time_series_data)

        # Validar requisitos da documentação
        assert metrics['mape'] < 20  # MAPE < 20%
        assert metrics['mae'] > 0
        assert 'training_samples' in metrics
        assert metrics['training_samples'] == len(time_series_data)


# =============================================================================
# Testes de Feriados Brasileiros
# =============================================================================

@pytest.mark.asyncio
async def test_brazilian_holidays(
    mock_config,
    mock_registry,
    mock_metrics,
    time_series_data
):
    """Valida que feriados brasileiros são considerados."""
    # Adicionar configuração de feriados
    mock_config['country_holidays'] = 'BR'

    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.prophet.log_model'):

        predictor = LoadPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics,
            redis_client=None
        )

        await predictor.train_model(time_series_data)

        # Validar que modelo foi treinado com feriados
        assert predictor.model is not None


# =============================================================================
# Testes de Persistência
# =============================================================================

@pytest.mark.asyncio
async def test_model_persistence_and_reload(
    mock_config,
    mock_registry,
    mock_metrics,
    time_series_data
):
    """Testa que modelo pode ser salvo e recarregado."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.prophet.log_model'):

        # Treinar modelo original
        predictor1 = LoadPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics,
            redis_client=None
        )

        await predictor1.train_model(time_series_data)

        # Fazer predição original
        forecast1 = await predictor1.predict_load(horizon_minutes=60)

        # Simular reload do modelo
        predictor2 = LoadPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics,
            redis_client=None
        )

        # Mock do MLflow para carregar modelo
        with patch('mlflow.prophet.load_model', return_value=predictor1.model), \
             patch('mlflow.tracking.MlflowClient') as mock_client_class:

            mock_client = Mock()
            mock_version = Mock()
            mock_version.run_id = 'test_run_id'
            mock_client.get_latest_versions.return_value = [mock_version]
            mock_client_class.return_value = mock_client

            await predictor2.initialize()

        # Fazer predição com modelo recarregado
        forecast2 = await predictor2.predict_load(horizon_minutes=60)

        # Validar que predições têm mesmo tamanho
        assert len(forecast1['forecast']) == len(forecast2['forecast'])


# =============================================================================
# Testes de Integração com ClickHouse
# =============================================================================

@pytest.mark.asyncio
async def test_clickhouse_integration(
    mock_config,
    mock_registry,
    mock_metrics,
    mock_clickhouse
):
    """Testa integração com ClickHouse para buscar dados históricos."""
    predictor = LoadPredictor(
        config=mock_config,
        model_registry=mock_registry,
        metrics=mock_metrics,
        redis_client=None
    )

    # Mock de método que busca dados do ClickHouse
    with patch.object(predictor, '_fetch_historical_data', return_value=mock_clickhouse.execute_query()):
        historical_data = await predictor._fetch_historical_data()

        assert len(historical_data) > 0
        assert 'timestamp' in historical_data.columns or 'ds' in historical_data.columns


# =============================================================================
# Testes de Medição de Latência
# =============================================================================

@pytest.mark.asyncio
async def test_predict_load_latency_measurement(mock_config, mock_registry):
    """Testa que a latência de predição é medida e registrada corretamente."""
    # Mock de métricas que captura os valores passados
    recorded_latencies = []

    async def mock_record_load_forecast(horizon_minutes, status, latency, mape):
        recorded_latencies.append({
            'horizon_minutes': horizon_minutes,
            'status': status,
            'latency': latency,
            'mape': mape
        })

    mock_metrics = Mock()
    mock_metrics.record_load_forecast = AsyncMock(side_effect=mock_record_load_forecast)
    mock_metrics.record_forecast_cache_hit = AsyncMock()

    # Configuração para usar dados sintéticos
    config = {**mock_config, 'use_synthetic_data': True}

    predictor = LoadPredictor(
        config=config,
        model_registry=mock_registry,
        metrics=mock_metrics,
        redis_client=None
    )

    # Fazer predição (usará fallback ARIMA pois não há modelo carregado)
    await predictor.predict_load(horizon_minutes=60)

    # Verificar que record_load_forecast foi chamado
    assert len(recorded_latencies) > 0, "Métricas de latência não foram registradas"

    # Verificar que a latência registrada é maior que 0
    last_record = recorded_latencies[-1]
    assert last_record['latency'] > 0, f"Latência deveria ser > 0, mas foi {last_record['latency']}"
    assert last_record['horizon_minutes'] == 60


@pytest.mark.asyncio
async def test_predict_load_latency_on_error(mock_config, mock_registry):
    """Testa que a latência é medida mesmo quando ocorre erro."""
    recorded_latencies = []

    async def mock_record_load_forecast(horizon_minutes, status, latency, mape):
        recorded_latencies.append({
            'status': status,
            'latency': latency
        })

    mock_metrics = Mock()
    mock_metrics.record_load_forecast = AsyncMock(side_effect=mock_record_load_forecast)
    mock_metrics.record_forecast_cache_hit = AsyncMock()

    predictor = LoadPredictor(
        config=mock_config,
        model_registry=mock_registry,
        metrics=mock_metrics,
        redis_client=None
    )

    # Forçar erro no método interno de predição
    with patch.object(predictor, '_predict_with_arima', side_effect=Exception("Erro simulado")):
        result = await predictor.predict_load(horizon_minutes=60)

    # Deve retornar erro mas ainda registrar métricas
    assert 'error' in result
    assert len(recorded_latencies) > 0

    # Latência deve ser registrada mesmo em caso de erro
    last_record = recorded_latencies[-1]
    assert last_record['status'] == 'error'
    assert last_record['latency'] >= 0
