"""Preditor de carga do sistema usando Prophet/ARIMA."""

from typing import Dict, Any, List, Optional
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from prophet import Prophet
from statsmodels.tsa.arima.model import ARIMA
import pmdarima as pm

from neural_hive_ml.predictive_models.base_predictor import BasePredictor

logger = logging.getLogger(__name__)


class LoadPredictor(BasePredictor):
    """Preditor de carga usando Prophet/ARIMA para time-series forecasting."""

    def __init__(
        self,
        config: Dict[str, Any],
        model_registry: Optional[Any] = None,
        metrics: Optional[Any] = None,
        redis_client: Optional[Any] = None,
        data_source: Optional[Any] = None
    ):
        """
        Inicializa o preditor de carga.

        Args:
            config: Configuração do modelo
                - forecast_horizons: [60, 360, 1440] minutos
                - seasonality_mode: 'additive' ou 'multiplicative'
                - cache_ttl_seconds: TTL do cache Redis
                - use_synthetic_data: flag para usar dados sintéticos (dev/test)
            model_registry: Registry MLflow
            metrics: Cliente de métricas Prometheus
            redis_client: Cliente Redis para cache
            data_source: Cliente de banco (ClickHouse, MongoDB) para dados históricos
        """
        super().__init__(config, model_registry, metrics)

        self.forecast_horizons = config.get('forecast_horizons', [60, 360, 1440])
        self.seasonality_mode = config.get('seasonality_mode', 'additive')
        self.cache_ttl = config.get('cache_ttl_seconds', 300)
        self.use_synthetic_data = config.get('use_synthetic_data', False)
        self.redis_client = redis_client
        self.data_source = data_source

        # Um modelo Prophet por horizonte
        self.prophet_models = {}
        self.arima_model = None

    async def initialize(self) -> None:
        """Carrega modelos Prophet para cada horizonte."""
        try:
            for horizon in self.forecast_horizons:
                model_name = f"load-predictor-{horizon}m"
                model = self._load_from_registry(model_name, stage="Production")

                if model:
                    self.prophet_models[horizon] = model
                    logger.info(f"Modelo Prophet carregado para horizonte {horizon}m")
                else:
                    logger.warning(f"Modelo não encontrado para horizonte {horizon}m")

            if not self.prophet_models:
                logger.warning("Nenhum modelo Prophet carregado")

        except Exception as e:
            logger.error(f"Erro ao inicializar LoadPredictor: {e}")

    async def predict_load(
        self,
        horizon_minutes: int,
        include_confidence: bool = True
    ) -> Dict[str, Any]:
        """
        Gera previsão de carga para horizonte especificado.

        Args:
            horizon_minutes: Horizonte de previsão (60, 360 ou 1440)
            include_confidence: Se True, inclui intervalos de confiança

        Returns:
            Dict com forecast, timestamps, e opcionalmente confidence intervals
        """
        try:
            # Verifica cache
            if self.redis_client:
                cache_key = f"load_forecast:{horizon_minutes}m"
                cached = await self._get_from_cache(cache_key)
                if cached:
                    logger.debug(f"Forecast carregado do cache: {cache_key}")
                    if self.metrics:
                        await self.metrics.record_forecast_cache_hit(True)
                    return cached

            # Seleciona modelo apropriado
            if horizon_minutes not in self.prophet_models:
                # Fallback para ARIMA
                logger.warning(
                    f"Modelo Prophet não disponível para {horizon_minutes}m, "
                    "usando ARIMA"
                )
                result = await self._predict_with_arima(horizon_minutes)
            else:
                result = await self._predict_with_prophet(
                    horizon_minutes,
                    include_confidence
                )

            # Salva no cache
            if self.redis_client:
                await self._save_to_cache(cache_key, result)
                if self.metrics:
                    await self.metrics.record_forecast_cache_hit(False)

            # Registra métricas
            if self.metrics:
                await self.metrics.record_load_forecast(
                    horizon_minutes=horizon_minutes,
                    status="success",
                    latency=0.0,  # TODO: medir
                    mape=result.get('mape', 0.0)
                )

            return result

        except Exception as e:
            logger.error(f"Erro ao prever carga: {e}")
            if self.metrics:
                await self.metrics.record_load_forecast(
                    horizon_minutes=horizon_minutes,
                    status="error",
                    latency=0.0,
                    mape=100.0
                )
            return {
                "forecast": [],
                "timestamps": [],
                "error": str(e)
            }

    async def predict_bottlenecks(
        self,
        horizon_minutes: int = 360
    ) -> List[Dict[str, Any]]:
        """
        Identifica potenciais bottlenecks futuros.

        Args:
            horizon_minutes: Horizonte de análise

        Returns:
            Lista de bottlenecks previstos com timestamp e severidade
        """
        try:
            forecast = await self.predict_load(horizon_minutes)

            if 'error' in forecast:
                return []

            bottlenecks = []
            load_values = forecast.get('forecast', [])
            timestamps = forecast.get('timestamps', [])

            # Define threshold para bottleneck (80% da capacidade)
            capacity_threshold = 0.8

            for i, (load, ts) in enumerate(zip(load_values, timestamps)):
                if load > capacity_threshold:
                    severity = 'HIGH' if load > 0.9 else 'MEDIUM'

                    bottleneck = {
                        'timestamp': ts,
                        'predicted_load': load,
                        'severity': severity,
                        'type': 'worker_saturation',
                        'minutes_ahead': int((i / len(load_values)) * horizon_minutes)
                    }
                    bottlenecks.append(bottleneck)

                    # Registra métrica
                    if self.metrics:
                        await self.metrics.record_bottleneck_prediction(
                            bottleneck_type='worker_saturation',
                            severity=severity,
                            timestamp=ts
                        )

            logger.info(f"Identificados {len(bottlenecks)} bottlenecks potenciais")
            return bottlenecks

        except Exception as e:
            logger.error(f"Erro ao prever bottlenecks: {e}")
            return []

    async def train_model(
        self,
        training_window_days: int = 540
    ) -> Dict[str, Any]:
        """
        Treina modelos Prophet para todos os horizontes.

        Args:
            training_window_days: Janela de dados históricos (540 = 18 meses)

        Returns:
            Dict com métricas de treinamento
        """
        try:
            # Carrega dados históricos (deve ser implementado pelo serviço)
            historical_data = await self._load_historical_data(training_window_days)

            if len(historical_data) < 1000:
                raise ValueError(
                    f"Dados insuficientes para treinamento: {len(historical_data)} amostras"
                )

            # Prepara time series
            df = self._prepare_timeseries_data(historical_data)
            df = self._backfill_missing_data(df)

            all_metrics = {}

            # Treina um modelo para cada horizonte
            for horizon in self.forecast_horizons:
                logger.info(f"Treinando modelo para horizonte {horizon}m")

                # Configura Prophet
                model = Prophet(
                    seasonality_mode=self.seasonality_mode,
                    daily_seasonality=True,
                    weekly_seasonality=True,
                    yearly_seasonality=True,
                    changepoint_prior_scale=0.05,
                    interval_width=0.95
                )

                # Adiciona sazonalidade horária
                model.add_seasonality(
                    name='hourly',
                    period=1/24,
                    fourier_order=8
                )

                # Treina
                model.fit(df)

                # Avalia
                metrics = self._evaluate_forecast(model, df, horizon)
                all_metrics[f'{horizon}m'] = metrics

                # Salva no registry
                model_name = f"load-predictor-{horizon}m"
                self._save_to_registry(
                    model=model,
                    model_name=model_name,
                    metrics=metrics,
                    params={
                        'seasonality_mode': self.seasonality_mode,
                        'training_window_days': training_window_days,
                        'horizon_minutes': horizon
                    },
                    tags={'horizon': f'{horizon}m'}
                )

                self.prophet_models[horizon] = model

            logger.info(f"Treinamento concluído para {len(self.forecast_horizons)} horizontes")
            return all_metrics

        except Exception as e:
            logger.error(f"Erro ao treinar modelo: {e}")
            raise

    def _extract_features(self, data: Dict[str, Any]) -> np.ndarray:
        """
        Extrai features de dados de time series.

        Para Prophet, não usamos features adicionais.
        """
        return np.array([])

    def _prepare_timeseries_data(
        self,
        historical_data: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        """
        Converte dados históricos para formato Prophet (ds, y).

        Args:
            historical_data: Lista de dicts com timestamp e load

        Returns:
            DataFrame com colunas 'ds' e 'y'
        """
        records = []
        for record in historical_data:
            records.append({
                'ds': pd.to_datetime(record['timestamp']),
                'y': float(record['load'])
            })

        df = pd.DataFrame(records)
        df = df.sort_values('ds')
        return df

    def _backfill_missing_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Interpola gaps em time series.

        Args:
            df: DataFrame com colunas 'ds' e 'y'

        Returns:
            DataFrame com gaps preenchidos
        """
        df = df.set_index('ds')
        df = df.asfreq('5T')  # 5 minutos
        df['y'] = df['y'].interpolate(method='linear')
        df = df.reset_index()
        return df

    async def _predict_with_prophet(
        self,
        horizon_minutes: int,
        include_confidence: bool
    ) -> Dict[str, Any]:
        """Gera forecast usando Prophet."""
        model = self.prophet_models[horizon_minutes]

        # Cria dataframe de datas futuras
        future = model.make_future_dataframe(
            periods=horizon_minutes,
            freq='T'  # Minutely
        )

        # Gera forecast
        forecast = model.predict(future)

        # Extrai apenas previsões futuras
        forecast = forecast.tail(horizon_minutes)

        result = {
            'forecast': forecast['yhat'].tolist(),
            'timestamps': forecast['ds'].dt.isoformat().tolist(),
            'model_type': 'prophet',
            'horizon_minutes': horizon_minutes
        }

        if include_confidence:
            result['confidence_lower'] = forecast['yhat_lower'].tolist()
            result['confidence_upper'] = forecast['yhat_upper'].tolist()

        return result

    async def _predict_with_arima(
        self,
        horizon_minutes: int
    ) -> Dict[str, Any]:
        """Fallback usando ARIMA."""
        try:
            # Carrega dados recentes
            recent_data = await self._load_historical_data(days=7)
            df = self._prepare_timeseries_data(recent_data)

            # Auto ARIMA
            model = pm.auto_arima(
                df['y'],
                start_p=1, start_q=1,
                max_p=3, max_q=3,
                seasonal=False,
                stepwise=True,
                suppress_warnings=True,
                error_action='ignore'
            )

            # Previsão
            forecast_values, conf_int = model.predict(
                n_periods=horizon_minutes,
                return_conf_int=True
            )

            # Gera timestamps futuros
            last_timestamp = df['ds'].max()
            timestamps = [
                (last_timestamp + timedelta(minutes=i)).isoformat()
                for i in range(1, horizon_minutes + 1)
            ]

            return {
                'forecast': forecast_values.tolist(),
                'timestamps': timestamps,
                'model_type': 'arima',
                'horizon_minutes': horizon_minutes,
                'confidence_lower': conf_int[:, 0].tolist(),
                'confidence_upper': conf_int[:, 1].tolist()
            }

        except Exception as e:
            logger.error(f"Erro em ARIMA fallback: {e}")
            return {
                'forecast': [],
                'timestamps': [],
                'error': str(e)
            }

    def _evaluate_forecast(
        self,
        model: Prophet,
        df: pd.DataFrame,
        horizon_minutes: int
    ) -> Dict[str, float]:
        """
        Avalia acurácia do forecast usando validação cruzada.

        Args:
            model: Modelo Prophet treinado
            df: Dados de treinamento
            horizon_minutes: Horizonte de previsão

        Returns:
            Métricas MAE, MAPE, RMSE
        """
        from prophet.diagnostics import cross_validation, performance_metrics

        # Cross-validation
        df_cv = cross_validation(
            model,
            initial=f'{len(df) // 2} days',
            period='30 days',
            horizon=f'{horizon_minutes} minutes'
        )

        # Calcula métricas
        df_p = performance_metrics(df_cv)

        return {
            'mae': float(df_p['mae'].mean()),
            'mape': float(df_p['mape'].mean()),
            'rmse': float(df_p['rmse'].mean())
        }

    async def _load_historical_data(
        self,
        days: int
    ) -> List[Dict[str, Any]]:
        """
        Carrega dados históricos de carga de banco de dados ou gera dados sintéticos.

        Args:
            days: Número de dias a carregar

        Returns:
            Lista de registros com timestamp e load
        """
        # Se flag de dados sintéticos está ativa ou não há data_source, usar sintético
        if self.use_synthetic_data or not self.data_source:
            if not self.use_synthetic_data:
                logger.warning(
                    "Data source não disponível, usando dados sintéticos. "
                    "Configure use_synthetic_data=True para suprimir este aviso."
                )
            return self._generate_synthetic_data(days)

        # Carregar dados reais do data_source
        try:
            # Calcular janela de tempo
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)

            # Query dados - Suporta ClickHouse ou MongoDB
            if hasattr(self.data_source, 'query'):  # ClickHouse client
                query = f"""
                    SELECT
                        toStartOfInterval(timestamp, INTERVAL 5 MINUTE) as time_bucket,
                        COUNT(*) as ticket_count,
                        AVG(actual_duration_ms) as avg_duration
                    FROM tickets
                    WHERE
                        timestamp >= %(start_time)s
                        AND timestamp < %(end_time)s
                        AND status = 'COMPLETED'
                    GROUP BY time_bucket
                    ORDER BY time_bucket
                """

                result = await self.data_source.query(
                    query,
                    parameters={'start_time': start_time, 'end_time': end_time}
                )

                data = [
                    {
                        'timestamp': row['time_bucket'].isoformat(),
                        'load': float(row['ticket_count'])  # Carga = nº de tickets
                    }
                    for row in result
                ]

            elif hasattr(self.data_source, 'find'):  # MongoDB client
                # Agregar tickets por janelas de 5 minutos
                pipeline = [
                    {
                        '$match': {
                            'completed_at': {
                                '$gte': start_time.timestamp(),
                                '$lt': end_time.timestamp()
                            },
                            'status': 'COMPLETED'
                        }
                    },
                    {
                        '$group': {
                            '_id': {
                                '$subtract': [
                                    {'$toLong': {'$multiply': ['$completed_at', 1000]}},
                                    {'$mod': [
                                        {'$toLong': {'$multiply': ['$completed_at', 1000]}},
                                        300000  # 5 minutos em ms
                                    ]}
                                ]
                            },
                            'count': {'$sum': 1},
                            'avg_duration': {'$avg': '$actual_duration_ms'}
                        }
                    },
                    {'$sort': {'_id': 1}}
                ]

                cursor = self.data_source.execution_tickets.aggregate(pipeline)
                data = []
                async for doc in cursor:
                    timestamp = datetime.fromtimestamp(doc['_id'] / 1000)
                    data.append({
                        'timestamp': timestamp.isoformat(),
                        'load': float(doc['count'])
                    })

            else:
                logger.error(
                    f"Data source não suportado: {type(self.data_source)}. "
                    "Esperado: ClickHouse client (com .query) ou MongoDB client (com .find)"
                )
                return self._generate_synthetic_data(days)

            if not data:
                logger.warning(f"Nenhum dado encontrado para os últimos {days} dias, usando sintético")
                return self._generate_synthetic_data(days)

            logger.info(f"Carregados {len(data)} registros de carga dos últimos {days} dias")
            return data

        except Exception as e:
            logger.error(f"Erro ao carregar dados históricos: {e}, usando sintético")
            return self._generate_synthetic_data(days)

    def _generate_synthetic_data(self, days: int) -> List[Dict[str, Any]]:
        """
        Gera dados sintéticos de carga para desenvolvimento/teste.

        Args:
            days: Número de dias a gerar

        Returns:
            Lista de registros sintéticos com timestamp e load
        """
        now = datetime.now()
        data = []

        for i in range(days * 24 * 12):  # 5-min intervals
            timestamp = now - timedelta(minutes=i * 5)
            # Carga sintética com padrão diário
            hour = timestamp.hour
            base_load = 50
            daily_pattern = 30 * np.sin((hour - 6) * np.pi / 12)
            noise = np.random.normal(0, 5)

            data.append({
                'timestamp': timestamp.isoformat(),
                'load': max(0, base_load + daily_pattern + noise)
            })

        return data

    async def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Recupera forecast do cache Redis."""
        if not self.redis_client:
            return None

        try:
            import json
            cached = await self.redis_client.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.error(f"Erro ao ler cache: {e}")

        return None

    async def _save_to_cache(
        self,
        key: str,
        data: Dict[str, Any]
    ) -> None:
        """Salva forecast no cache Redis."""
        if not self.redis_client:
            return

        try:
            import json
            await self.redis_client.setex(
                key,
                self.cache_ttl,
                json.dumps(data)
            )
        except Exception as e:
            logger.error(f"Erro ao salvar cache: {e}")
