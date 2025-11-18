"""
Testes unitários para LoadPredictor (Prophet/ARIMA forecasting).

Cobertura:
- Inicialização (carregamento de modelos do MLflow)
- predict_load (previsões com confiança e bottlenecks)
- train_model (treinamento com dados sintéticos e insuficientes)
- Cache hit/miss
- Fallback Prophet -> ARIMA
- Interpolação e cálculo de MAPE
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import numpy as np

from src.ml.load_predictor import LoadPredictor


@pytest.fixture
def config():
    """Configuração para LoadPredictor."""
    return {
        'ml_prophet_seasonality_mode': 'additive',
        'ml_prophet_changepoint_prior_scale': 0.05,
        'ml_load_forecast_horizons': [60, 360, 1440],
        'ml_forecast_cache_ttl_seconds': 300,
        'ml_training_window_days': 540,
        'ml_min_samples_prophet': 1000,
        'ml_min_samples_arima': 100,
    }


@pytest.fixture
def mock_clickhouse_client():
    """Mock ClickHouseClient."""
    client = AsyncMock()
    client.query_historical_loads = AsyncMock(return_value=pd.DataFrame({
        'timestamp': pd.date_range(start='2024-01-01', periods=1500, freq='H'),
        'ticket_count': np.random.randint(10, 100, 1500),
        'task_type': ['processing'] * 1500,
        'risk_band': ['medium'] * 1500,
        'cpu_usage': np.random.uniform(0.3, 0.8, 1500),
        'memory_usage': np.random.uniform(0.4, 0.7, 1500),
    }))
    return client


@pytest.fixture
def mock_redis_client():
    """Mock Redis para cache."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)  # Cache miss por padrão
    client.set = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def mock_model_registry():
    """Mock de ModelRegistry."""
    registry = AsyncMock()
    registry.load_load_model = AsyncMock(return_value=None)
    registry.save_load_model = AsyncMock()
    return registry


@pytest.fixture
def mock_metrics():
    """Mock de métricas."""
    metrics = Mock()
    metrics.record_ml_model_load = Mock()
    metrics.record_load_prediction = Mock()
    metrics.increment_cache_hit = Mock()
    metrics.increment_cache_miss = Mock()
    metrics.record_ml_training = Mock()
    return metrics


@pytest.fixture
def sample_historical_data():
    """Dados históricos de exemplo."""
    base_time = datetime.utcnow() - timedelta(days=7)
    data = []
    for i in range(1000):  # 1000 pontos
        data.append({
            'timestamp': base_time + timedelta(minutes=i),
            'ticket_count': 50 + np.random.randint(-10, 10),
            'avg_duration_ms': 60000,
            'resource_cpu_avg': 0.5,
            'resource_memory_avg': 512,
            'task_type': 'BUILD',
            'risk_band': 'medium'
        })
    return data


# Tests - Inicialização

@pytest.mark.asyncio
class TestLoadPredictorInitialization:
    """Testes de inicialização."""

    async def test_initialize_without_models(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa inicialização sem modelos pré-treinados."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        await predictor.initialize()

        assert predictor._initialized
        assert len(predictor.models) == 3  # 3 horizontes
        # Modelos padrão criados
        for horizon in [60, 360, 1440]:
            assert horizon in predictor.models

    async def test_initialize_with_mlflow_models(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa inicialização carregando modelos do MLflow."""
        # Mock modelo Prophet do MLflow
        mock_prophet_model = Mock()
        mock_prophet_model.make_future_dataframe = Mock()
        mock_prophet_model.predict = Mock(return_value=pd.DataFrame({
            'ds': [datetime.utcnow()],
            'yhat': [100],
            'yhat_lower': [90],
            'yhat_upper': [110]
        }))

        mock_model_registry.load_load_model = AsyncMock(return_value={
            'model': mock_prophet_model,
            'metadata': {'mape': 12.5}
        })

        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        await predictor.initialize()

        assert predictor._initialized
        # Modelos carregados do MLflow
        for horizon in [60, 360, 1440]:
            assert horizon in predictor.models
            assert predictor.models[horizon] == mock_prophet_model


# Tests - Previsão de Carga

@pytest.mark.asyncio
class TestLoadPrediction:
    """Testes de previsão de carga."""

    async def test_predict_load_with_prophet(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics, sample_historical_data):
        """Testa previsão usando Prophet."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        # Mock modelo Prophet
        mock_prophet = Mock()
        future_df = pd.DataFrame({
            'ds': pd.date_range(start=datetime.utcnow(), periods=60, freq='T')
        })
        forecast_df = pd.DataFrame({
            'ds': future_df['ds'],
            'yhat': [100 + i for i in range(60)],
            'yhat_lower': [90 + i for i in range(60)],
            'yhat_upper': [110 + i for i in range(60)]
        })
        mock_prophet.make_future_dataframe = Mock(return_value=future_df)
        mock_prophet.predict = Mock(return_value=forecast_df)

        predictor.models[60] = mock_prophet
        predictor._initialized = True

        # Mock dados históricos
        mock_clickhouse.query_execution_timeseries = AsyncMock(return_value=sample_historical_data)

        result = await predictor.predict_load(horizon_minutes=60, include_confidence_intervals=True)

        assert 'forecast' in result
        assert 'metadata' in result
        assert len(result['forecast']) == 60
        assert result['forecast'][0]['ticket_count'] >= 0
        assert result['forecast'][0]['confidence_lower'] is not None
        assert result['forecast'][0]['confidence_upper'] is not None
        assert 'resource_demand' in result['forecast'][0]

    async def test_predict_load_cache_hit(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa cache hit em previsões."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        predictor._initialized = True

        # Mock cache retornando previsão
        cached_forecast = {
            'forecast': [
                {'timestamp': datetime.utcnow().isoformat(), 'ticket_count': 100, 'resource_demand': {'cpu_cores': 10, 'memory_mb': 1000}}
            ],
            'metadata': {}
        }
        import json
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_forecast))

        result = await predictor.predict_load(horizon_minutes=60)

        assert result == cached_forecast
        mock_metrics.increment_cache_hit.assert_called_once_with('load_forecast')

    async def test_predict_load_insufficient_data_fallback_arima(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa fallback para ARIMA com dados insuficientes."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        predictor.models[60] = Mock()
        predictor._initialized = True

        # Mock dados históricos insuficientes (< 100)
        minimal_data = [
            {'timestamp': datetime.utcnow() - timedelta(minutes=i), 'ticket_count': 50 + i}
            for i in range(50)
        ]
        mock_clickhouse.query_execution_timeseries = AsyncMock(return_value=minimal_data)

        with patch('src.ml.load_predictor.auto_arima') as mock_auto_arima:
            mock_arima_model = Mock()
            mock_arima_model.predict = Mock(return_value=(
                np.array([100] * 60),
                np.array([[90, 110]] * 60)
            ))
            mock_arima_model.order = (1, 1, 1)
            mock_auto_arima.return_value = mock_arima_model

            result = await predictor.predict_load(horizon_minutes=60)

            assert 'forecast' in result
            assert result['metadata']['model_type'] == 'ARIMA'
            assert len(result['forecast']) == 60

    async def test_predict_load_missing_data_handling(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa tratamento de dados faltando."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        # Mock ClickHouse retornando vazio
        mock_clickhouse.query_execution_timeseries = AsyncMock(return_value=[])

        with pytest.raises(Exception):
            await predictor.predict_load(horizon_minutes=60)

        mock_metrics.record_load_prediction.assert_called()


# Tests - Detecção de Bottlenecks

@pytest.mark.asyncio
class TestBottleneckPrediction:
    """Testes de detecção de bottlenecks."""

    async def test_predict_bottlenecks_worker_saturation(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa detecção de saturação de workers."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        predictor._initialized = True

        # Mock forecast com carga alta
        mock_forecast = {
            'forecast': [
                {
                    'timestamp': (datetime.utcnow() + timedelta(minutes=i)).isoformat(),
                    'ticket_count': 950,  # > 90% de 1000 (capacidade)
                    'resource_demand': {'cpu_cores': 95, 'memory_mb': 95000},
                    'confidence_lower': 900,
                    'confidence_upper': 1000
                }
                for i in range(10)
            ],
            'metadata': {}
        }

        with patch.object(predictor, 'predict_load', return_value=mock_forecast):
            with patch.object(predictor, '_get_current_worker_capacity', return_value=1000):
                bottlenecks = await predictor.predict_bottlenecks(horizon_minutes=60)

                assert len(bottlenecks) > 0
                assert any(b['type'] == 'worker_saturation' for b in bottlenecks)
                assert any(b['recommendation'] == 'INCREASE_WORKER_POOL' for b in bottlenecks)

    async def test_predict_bottlenecks_demand_spike(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa detecção de picos de demanda."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        predictor._initialized = True

        # Mock forecast com pico
        mock_forecast = {
            'forecast': [
                {
                    'timestamp': (datetime.utcnow() + timedelta(minutes=i)).isoformat(),
                    'ticket_count': 50 if i < 5 else 150,  # Pico em i >= 5
                    'resource_demand': {'cpu_cores': 5, 'memory_mb': 5000},
                    'confidence_lower': 40,
                    'confidence_upper': 50 if i < 5 else 200  # Upper bound > 2x média
                }
                for i in range(10)
            ],
            'metadata': {}
        }

        with patch.object(predictor, 'predict_load', return_value=mock_forecast):
            with patch.object(predictor, '_get_current_worker_capacity', return_value=1000):
                bottlenecks = await predictor.predict_bottlenecks(horizon_minutes=60)

                assert len(bottlenecks) > 0
                assert any(b['type'] == 'demand_spike' for b in bottlenecks)
                assert any(b['recommendation'] == 'PREEMPTIVE_SCALING' for b in bottlenecks)


# Tests - Treinamento

@pytest.mark.asyncio
class TestTraining:
    """Testes de treinamento de modelos."""

    async def test_train_model_success(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics, sample_historical_data):
        """Testa treinamento bem-sucedido."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        predictor._initialized = True

        # Mock dados históricos suficientes
        mock_clickhouse.query_execution_timeseries = AsyncMock(return_value=sample_historical_data)

        result = await predictor.train_model(training_window_days=7)

        assert 60 in result
        assert 360 in result
        assert 1440 in result
        assert result[60]['mape'] < 100  # MAPE razoável
        mock_metrics.record_ml_training.assert_called_once()

    async def test_train_model_insufficient_data(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa treinamento com dados insuficientes."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        predictor._initialized = True

        # Mock dados insuficientes
        minimal_data = [
            {'timestamp': datetime.utcnow() - timedelta(minutes=i), 'ticket_count': 50}
            for i in range(50)  # < 100 (min_training_samples)
        ]
        mock_clickhouse.query_execution_timeseries = AsyncMock(return_value=minimal_data)

        with pytest.raises(ValueError, match="Dados insuficientes"):
            await predictor.train_model(training_window_days=7)

    async def test_calculate_forecast_accuracy(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa cálculo de acurácia."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        actual = np.array([100, 110, 90, 105, 95])
        predicted = np.array([105, 108, 92, 100, 98])

        metrics = predictor._calculate_forecast_accuracy(actual, predicted)

        assert 'mae' in metrics
        assert 'mape' in metrics
        assert 'rmse' in metrics
        assert metrics['mae'] > 0
        assert metrics['mape'] > 0
        assert metrics['rmse'] > 0


# Tests - Helpers

@pytest.mark.asyncio
class TestHelpers:
    """Testes de métodos auxiliares."""

    def test_prepare_timeseries_data(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics, sample_historical_data):
        """Testa preparação de dados para Prophet."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        df = predictor._prepare_timeseries_data(sample_historical_data)

        assert isinstance(df, pd.DataFrame)
        assert 'ds' in df.columns
        assert 'y' in df.columns
        assert len(df) == len(sample_historical_data)
        assert df['ds'].dtype == 'datetime64[ns]'

    def test_backfill_missing_data(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa preenchimento de gaps."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        # DataFrame com gaps
        df_with_gaps = pd.DataFrame({
            'ds': pd.date_range(start='2024-01-01', periods=100, freq='10T'),  # A cada 10 min (com gaps)
            'y': np.random.randint(50, 150, 100)
        })

        df_filled = predictor._backfill_missing_data(df_with_gaps)

        # Deve ter preenchido para 1 minuto de intervalo
        assert len(df_filled) > len(df_with_gaps)
        assert not df_filled['y'].isna().any()

    def test_validate_data_quality_valid(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics, sample_historical_data):
        """Testa validação de dados com dados válidos."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        result = predictor._validate_data_quality(sample_historical_data)

        assert result['is_valid']
        assert len(result['issues']) == 0

    def test_validate_data_quality_invalid(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa validação de dados com dados inválidos."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        # Dados insuficientes
        invalid_data = [
            {'timestamp': datetime.utcnow(), 'ticket_count': 50}
            for _ in range(10)
        ]

        result = predictor._validate_data_quality(invalid_data)

        assert not result['is_valid']
        assert len(result['issues']) > 0

    def test_estimate_resource_demand(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa estimativa de recursos."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        resources = predictor._estimate_resource_demand(ticket_count=100)

        assert 'cpu_cores' in resources
        assert 'memory_mb' in resources
        assert resources['cpu_cores'] == 10.0  # 100 * 0.1
        assert resources['memory_mb'] == 10000  # 100 * 100

    async def test_get_current_worker_capacity(self, mock_config, mock_clickhouse, mock_redis, mock_model_registry, mock_metrics):
        """Testa cálculo de capacidade de workers."""
        predictor = LoadPredictor(
            mock_clickhouse,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        # Mock métricas de utilização
        mock_clickhouse.query_resource_utilization = AsyncMock(return_value=[
            {'timestamp': datetime.utcnow(), 'metric_name': 'active_workers', 'avg_value': 10, 'max_value': 12}
        ])

        capacity = await predictor._get_current_worker_capacity()

        assert capacity > 0
        assert capacity == 1000  # 10 workers * 100 tickets/worker


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
