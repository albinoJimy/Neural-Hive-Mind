"""
Load Predictor usando Prophet e ARIMA para forecasting de séries temporais.

Prevê volumes de tickets futuros, demanda de recursos e bottlenecks potenciais
baseado em dados históricos de 18 meses do ClickHouse.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from prophet import Prophet
from statsmodels.tsa.arima.model import ARIMA
import holidays

logger = logging.getLogger(__name__)


class LoadPredictor:
    """
    Preditor de carga usando Prophet para forecasting com ARIMA como fallback.

    Gera previsões de:
    - Volumes de tickets por horizonte temporal (1h, 6h, 24h)
    - Demanda de recursos (CPU, memória) por task_type/risk_band
    - Bottlenecks potenciais (saturação de workers, depth de fila)
    """

    def __init__(
        self,
        clickhouse_client,
        redis_client,
        model_registry,
        metrics,
        config: Dict
    ):
        """
        Args:
            clickhouse_client: Cliente para queries históricos
            redis_client: Cliente Redis para caching de previsões
            model_registry: Registro MLflow para modelos
            metrics: Instância de métricas Prometheus
            config: Configuração (horizons, Prophet params, cache TTLs)
        """
        self.clickhouse = clickhouse_client
        self.redis = redis_client
        self.model_registry = model_registry
        self.metrics = metrics
        self.config = config

        # Modelos carregados (Prophet por horizonte)
        self.models: Dict[int, Prophet] = {}
        self.arima_models: Dict[int, ARIMA] = {}

        # Feriados brasileiros para Prophet
        self.br_holidays = holidays.Brazil()

        # Configurações Prophet
        self.seasonality_mode = config.get('ml_prophet_seasonality_mode', 'additive')
        self.changepoint_prior_scale = config.get('ml_prophet_changepoint_prior_scale', 0.05)

        # Horizontes de previsão (minutos)
        self.forecast_horizons = config.get('ml_load_forecast_horizons', [60, 360, 1440])

        # Cache TTL
        self.cache_ttl = config.get('ml_forecast_cache_ttl_seconds', 300)

        self._initialized = False

    async def initialize(self) -> None:
        """Carrega modelos Prophet/ARIMA do MLflow para cada horizonte."""
        if self._initialized:
            return

        logger.info("Inicializando LoadPredictor...")
        start_time = datetime.utcnow()

        try:
            for horizon in self.forecast_horizons:
                model_name = f"load_predictor_{horizon}m"

                try:
                    # Tentar carregar modelo do MLflow
                    model_data = await self.model_registry.load_load_model(
                        model_name=model_name,
                        stage='Production'
                    )

                    if model_data:
                        loaded_model = model_data['model']
                        # Verificar se é Prophet nativo ou PyFuncModel
                        if hasattr(loaded_model, 'make_future_dataframe'):
                            # Modelo Prophet nativo
                            self.models[horizon] = loaded_model
                        elif hasattr(loaded_model, 'predict'):
                            # PyFuncModel - armazenar para uso posterior
                            self.models[horizon] = loaded_model
                        else:
                            logger.warning(f"Modelo carregado não é compatível para {horizon}m")
                            self.models[horizon] = self._create_default_prophet_model()
                        logger.info(f"Modelo Prophet carregado para horizonte {horizon}m")
                    else:
                        # Criar modelo padrão se não existir
                        logger.warning(f"Modelo não encontrado para {horizon}m, criando padrão")
                        self.models[horizon] = self._create_default_prophet_model()

                except Exception as e:
                    logger.error(f"Erro ao carregar modelo {horizon}m: {e}")
                    self.models[horizon] = self._create_default_prophet_model()

            duration = (datetime.utcnow() - start_time).total_seconds()
            self.metrics.record_ml_model_load('load_predictor', 'success', duration)

            self._initialized = True
            logger.info(f"LoadPredictor inicializado em {duration:.2f}s")

        except Exception as e:
            logger.error(f"Erro ao inicializar LoadPredictor: {e}")
            self.metrics.record_ml_model_load('load_predictor', 'error', 0)
            raise

    def _create_default_prophet_model(self) -> Prophet:
        """Cria modelo Prophet padrão com configurações otimizadas."""
        # Criar DataFrame de feriados
        holidays_df = pd.DataFrame({
            'ds': pd.to_datetime([str(date) for date in self.br_holidays.keys()]),
            'holiday': 'brazil_holiday'
        })

        model = Prophet(
            seasonality_mode=self.seasonality_mode,
            changepoint_prior_scale=self.changepoint_prior_scale,
            holidays=holidays_df,
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=True,
            interval_width=0.95  # 95% confidence interval
        )

        # Adicionar sazonalidade horária
        model.add_seasonality(name='hourly', period=1, fourier_order=8)

        return model

    async def predict_load(
        self,
        horizon_minutes: int,
        include_confidence_intervals: bool = True
    ) -> Dict:
        """
        Gera previsão de carga para horizonte especificado.

        Args:
            horizon_minutes: Horizonte de previsão em minutos
            include_confidence_intervals: Incluir intervalos de confiança

        Returns:
            Dict com:
                - forecast: Lista de pontos de previsão (timestamp, ticket_count, resource_demand)
                - confidence_intervals: Intervalos de confiança (80%, 95%) se solicitado
                - metadata: Info sobre modelo, MAPE, última atualização
        """
        start_time = datetime.utcnow()

        try:
            # Verificar cache
            cache_key = f"load_forecast:{horizon_minutes}m"
            cached = await self._get_cached_forecast(cache_key)
            if cached:
                self.metrics.increment_cache_hit('load_forecast')
                return cached

            # Selecionar modelo mais próximo
            model_horizon = min(self.forecast_horizons, key=lambda x: abs(x - horizon_minutes))
            model = self.models.get(model_horizon)

            if not model:
                raise ValueError(f"Modelo não encontrado para horizonte {model_horizon}m")

            # Buscar dados históricos recentes para contexto
            historical_data = await self._fetch_recent_historical_data(days=30)

            if len(historical_data) < 100:
                logger.warning(f"Dados insuficientes para previsão: {len(historical_data)} amostras")
                # Fallback para ARIMA
                return await self._predict_with_arima(horizon_minutes, historical_data)

            # Preparar dados no formato Prophet (ds, y)
            df = self._prepare_timeseries_data(historical_data)

            # Fazer previsão baseado no tipo de modelo
            if hasattr(model, 'make_future_dataframe'):
                # Modelo Prophet nativo
                future = model.make_future_dataframe(periods=horizon_minutes, freq='T')  # T = minuto
                forecast = model.predict(future)
            elif hasattr(model, 'predict'):
                # PyFuncModel - criar DataFrame apenas com coluna ds
                import pandas as pd
                from datetime import timedelta
                last_timestamp = df['ds'].max()
                future_timestamps = pd.date_range(
                    start=last_timestamp + timedelta(minutes=1),
                    periods=horizon_minutes,
                    freq='T'
                )
                future = pd.DataFrame({'ds': future_timestamps})
                forecast = model.predict(future)
                # Converter saída do PyFunc para formato esperado
                if isinstance(forecast, pd.DataFrame):
                    # Já está em formato de DataFrame
                    pass
                else:
                    # Criar DataFrame com previsões
                    forecast = pd.DataFrame({
                        'ds': future_timestamps,
                        'yhat': forecast,
                        'yhat_lower': forecast * 0.9,  # Aproximação
                        'yhat_upper': forecast * 1.1,
                    })
            else:
                raise ValueError(f"Modelo não suportado para horizonte {model_horizon}m")

            # Extrair apenas previsões futuras
            future_forecast = forecast.tail(horizon_minutes)

            # Construir resultado
            result = {
                'forecast': [
                    {
                        'timestamp': row['ds'].isoformat(),
                        'ticket_count': max(0, int(row['yhat'])),  # Não negativo
                        'resource_demand': self._estimate_resource_demand(row['yhat']),
                        'confidence_lower': max(0, int(row['yhat_lower'])) if include_confidence_intervals else None,
                        'confidence_upper': max(0, int(row['yhat_upper'])) if include_confidence_intervals else None,
                    }
                    for _, row in future_forecast.iterrows()
                ],
                'metadata': {
                    'model_horizon': model_horizon,
                    'horizon_requested': horizon_minutes,
                    'forecast_generated_at': datetime.utcnow().isoformat(),
                    'data_points_used': len(historical_data),
                    'confidence_level': 0.95 if include_confidence_intervals else None,
                }
            }

            # Cachear resultado
            await self._cache_forecast(cache_key, result, ttl=self.cache_ttl)

            duration = (datetime.utcnow() - start_time).total_seconds()
            self.metrics.record_load_prediction(horizon_minutes, 'success', duration, None)

            logger.info(f"Previsão gerada para {horizon_minutes}m em {duration:.3f}s")
            return result

        except Exception as e:
            logger.error(f"Erro ao prever carga: {e}")
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.metrics.record_load_prediction(horizon_minutes, 'error', duration, None)
            raise

    async def predict_bottlenecks(self, horizon_minutes: int = 60) -> List[Dict]:
        """
        Identifica bottlenecks potenciais no horizonte especificado.

        Args:
            horizon_minutes: Horizonte de análise

        Returns:
            Lista de bottlenecks preditos com timestamp, tipo, severidade
        """
        try:
            # Obter forecast de carga
            load_forecast = await self.predict_load(horizon_minutes, include_confidence_intervals=True)

            # Buscar capacidade atual de workers
            current_capacity = await self._get_current_worker_capacity()

            bottlenecks = []

            for point in load_forecast['forecast']:
                predicted_load = point['ticket_count']
                timestamp = point['timestamp']

                # Detectar saturação de workers (>90% capacidade)
                utilization = predicted_load / max(current_capacity, 1)
                if utilization > 0.9:
                    bottlenecks.append({
                        'timestamp': timestamp,
                        'type': 'worker_saturation',
                        'severity': 'high' if utilization > 0.95 else 'medium',
                        'predicted_utilization': utilization,
                        'recommendation': 'INCREASE_WORKER_POOL'
                    })

                # Detectar picos de demanda (>2x média)
                if point.get('confidence_upper'):
                    avg_load = np.mean([p['ticket_count'] for p in load_forecast['forecast']])
                    if point['confidence_upper'] > 2 * avg_load:
                        bottlenecks.append({
                            'timestamp': timestamp,
                            'type': 'demand_spike',
                            'severity': 'medium',
                            'predicted_peak': point['confidence_upper'],
                            'recommendation': 'PREEMPTIVE_SCALING'
                        })

            logger.info(f"Detectados {len(bottlenecks)} bottlenecks potenciais em {horizon_minutes}m")
            return bottlenecks

        except Exception as e:
            logger.error(f"Erro ao prever bottlenecks: {e}")
            return []

    async def train_model(self, training_window_days: int = 540) -> Dict:
        """
        Treina modelos Prophet para todos os horizontes usando dados históricos.

        Args:
            training_window_days: Janela de dados históricos (default 18 meses)

        Returns:
            Dict com métricas de treinamento (MAE, MAPE, RMSE) por horizonte
        """
        logger.info(f"Iniciando treinamento com janela de {training_window_days} dias")
        start_time = datetime.utcnow()

        training_results = {}

        try:
            # Buscar dados históricos do ClickHouse
            historical_data = await self._fetch_historical_training_data(training_window_days)

            # Validar qualidade dos dados
            validation_result = self._validate_data_quality(historical_data)
            if not validation_result['is_valid']:
                raise ValueError(f"Dados insuficientes: {validation_result['issues']}")

            # Preparar DataFrame Prophet
            df = self._prepare_timeseries_data(historical_data)

            # Preencher gaps
            df = self._backfill_missing_data(df)

            # Treinar modelo para cada horizonte
            for horizon in self.forecast_horizons:
                logger.info(f"Treinando modelo para horizonte {horizon}m")

                # Criar modelo
                model = self._create_default_prophet_model()

                # Split train/test (últimos 7 dias para validação)
                split_date = df['ds'].max() - timedelta(days=7)
                train_df = df[df['ds'] <= split_date]
                test_df = df[df['ds'] > split_date]

                # Treinar
                model.fit(train_df)

                # Avaliar no conjunto de teste
                test_forecast = model.predict(test_df[['ds']])
                metrics = self._calculate_forecast_accuracy(
                    test_df['y'].values,
                    test_forecast['yhat'].values
                )

                # Salvar modelo se MAPE < 20%
                if metrics['mape'] < 20.0:
                    model_name = f"load_predictor_{horizon}m"
                    await self.model_registry.save_load_model(
                        model=model,
                        model_name=model_name,
                        metrics=metrics,
                        params={
                            'horizon_minutes': horizon,
                            'seasonality_mode': self.seasonality_mode,
                            'changepoint_prior_scale': self.changepoint_prior_scale,
                            'training_window_days': training_window_days,
                        }
                    )

                    # Atualizar modelo em memória
                    self.models[horizon] = model

                    logger.info(f"Modelo {horizon}m salvo com MAPE={metrics['mape']:.2f}%")
                else:
                    logger.warning(f"Modelo {horizon}m não promovido (MAPE={metrics['mape']:.2f}%)")

                training_results[horizon] = metrics

            duration = (datetime.utcnow() - start_time).total_seconds()
            self.metrics.record_ml_training('load_predictor', duration, training_results)

            logger.info(f"Treinamento concluído em {duration:.2f}s")
            return training_results

        except Exception as e:
            logger.error(f"Erro no treinamento: {e}")
            raise

    def _prepare_timeseries_data(self, historical_data: List[Dict]) -> pd.DataFrame:
        """
        Converte dados históricos para formato Prophet (ds, y).

        Args:
            historical_data: Lista de dicts com timestamp e ticket_count

        Returns:
            DataFrame com colunas ds (datetime) e y (valor)
        """
        df = pd.DataFrame(historical_data)

        # Renomear colunas para formato Prophet
        df = df.rename(columns={'timestamp': 'ds', 'ticket_count': 'y'})

        # Converter timestamp para datetime
        df['ds'] = pd.to_datetime(df['ds'])

        # Garantir ordenação temporal
        df = df.sort_values('ds').reset_index(drop=True)

        # Agregar por minuto (se houver duplicatas)
        df = df.groupby('ds', as_index=False).agg({'y': 'sum'})

        return df[['ds', 'y']]

    def _backfill_missing_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Preenche gaps em série temporal usando interpolação linear.

        Args:
            df: DataFrame Prophet com ds e y

        Returns:
            DataFrame com gaps preenchidos
        """
        # Criar range completo de timestamps (intervalo de 1 minuto)
        full_range = pd.date_range(
            start=df['ds'].min(),
            end=df['ds'].max(),
            freq='T'
        )

        # Reindexar para incluir todos os timestamps
        df = df.set_index('ds').reindex(full_range)

        # Interpolação linear para preencher NaNs
        df['y'] = df['y'].interpolate(method='linear', limit_direction='both')

        # Reset index
        df = df.reset_index()
        df = df.rename(columns={'index': 'ds'})

        return df

    def _validate_data_quality(self, data: List[Dict]) -> Dict:
        """
        Valida qualidade dos dados históricos.

        Returns:
            Dict com is_valid (bool) e issues (lista de problemas)
        """
        issues = []

        # Verificar quantidade mínima
        min_samples = self.config.get('ml_min_training_samples', 1000)
        if len(data) < min_samples:
            issues.append(f"Amostras insuficientes: {len(data)} < {min_samples}")

        # Verificar campos obrigatórios
        if data:
            required_fields = {'timestamp', 'ticket_count'}
            if not required_fields.issubset(data[0].keys()):
                issues.append(f"Campos faltando: {required_fields - set(data[0].keys())}")

        # Verificar outliers extremos (> 10x mediana)
        if data:
            counts = [d['ticket_count'] for d in data]
            median = np.median(counts)
            outliers = sum(1 for c in counts if c > 10 * median)
            if outliers > len(data) * 0.05:  # >5% outliers
                issues.append(f"Muitos outliers: {outliers} ({100*outliers/len(data):.1f}%)")

        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'data_points': len(data)
        }

    def _calculate_forecast_accuracy(
        self,
        actual: np.ndarray,
        predicted: np.ndarray
    ) -> Dict:
        """Calcula métricas de acurácia (MAE, MAPE, RMSE)."""
        mae = np.mean(np.abs(actual - predicted))
        mape = np.mean(np.abs((actual - predicted) / np.maximum(actual, 1))) * 100
        rmse = np.sqrt(np.mean((actual - predicted) ** 2))

        return {
            'mae': float(mae),
            'mape': float(mape),
            'rmse': float(rmse)
        }

    def _estimate_resource_demand(self, ticket_count: float) -> Dict:
        """
        Estima demanda de recursos (CPU, memória) baseado em ticket count.

        Heurística: 0.1 CPU e 100MB por ticket em média.
        """
        cpu_per_ticket = 0.1
        memory_per_ticket_mb = 100

        return {
            'cpu_cores': round(ticket_count * cpu_per_ticket, 2),
            'memory_mb': int(ticket_count * memory_per_ticket_mb)
        }

    async def _fetch_recent_historical_data(self, days: int) -> List[Dict]:
        """Busca dados históricos recentes do ClickHouse."""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        try:
            data = await self.clickhouse.query_execution_timeseries(
                start_timestamp=start_time,
                end_timestamp=end_time,
                aggregation_interval='1m'  # 1 minuto
            )
            return data
        except Exception as e:
            logger.error(f"Erro ao buscar dados históricos: {e}")
            return []

    async def _fetch_historical_training_data(self, days: int) -> List[Dict]:
        """Busca janela completa de dados para treinamento."""
        return await self._fetch_recent_historical_data(days)

    async def _get_current_worker_capacity(self) -> int:
        """
        Obtém capacidade atual de workers baseado em métricas de utilização.

        Calcula a capacidade aproximada consultando utilização de recursos
        e throughput recente.
        """
        try:
            # Consultar métricas de utilização recente (última hora)
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)

            resource_metrics = await self.clickhouse.query_resource_utilization(
                start_timestamp=start_time,
                end_timestamp=end_time
            )

            if not resource_metrics:
                # Fallback para valor configurável se não houver métricas
                default_capacity = self.config.get('ml_default_worker_capacity', 1000)
                logger.warning(f"Sem métricas de utilização, usando capacidade padrão: {default_capacity}")
                return default_capacity

            # Calcular capacidade baseado em workers ativos e utilização média
            active_workers_metrics = [m for m in resource_metrics if m['metric_name'] == 'active_workers']

            if active_workers_metrics:
                # Média de workers ativos na última hora
                avg_active_workers = np.mean([m['avg_value'] for m in active_workers_metrics])
                # Capacidade heurística: 100 tickets por worker
                tickets_per_worker = self.config.get('ml_tickets_per_worker', 100)
                estimated_capacity = int(avg_active_workers * tickets_per_worker)

                logger.debug(f"Capacidade calculada: {estimated_capacity} tickets ({avg_active_workers:.1f} workers × {tickets_per_worker})")
                return max(100, estimated_capacity)  # Mínimo de 100
            else:
                # Fallback para valor configurável
                default_capacity = self.config.get('ml_default_worker_capacity', 1000)
                logger.debug(f"Sem dados de workers ativos, usando capacidade padrão: {default_capacity}")
                return default_capacity

        except Exception as e:
            logger.error(f"Erro ao calcular capacidade de workers: {e}")
            # Fallback seguro
            default_capacity = self.config.get('ml_default_worker_capacity', 1000)
            return default_capacity

    async def _get_cached_forecast(self, cache_key: str) -> Optional[Dict]:
        """Recupera previsão do cache Redis."""
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                import json
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Erro ao ler cache: {e}")
        return None

    async def _cache_forecast(self, cache_key: str, forecast: Dict, ttl: int) -> None:
        """Armazena previsão no cache Redis."""
        try:
            import json
            await self.redis.setex(cache_key, ttl, json.dumps(forecast))
        except Exception as e:
            logger.warning(f"Erro ao cachear: {e}")

    async def _predict_with_arima(
        self,
        horizon_minutes: int,
        historical_data: List[Dict]
    ) -> Dict:
        """Fallback ARIMA quando Prophet falha ou dados insuficientes."""
        logger.info(f"Usando fallback ARIMA para horizonte {horizon_minutes}m")

        try:
            # Preparar série temporal
            df = self._prepare_timeseries_data(historical_data)

            # Auto-ARIMA para selecionar melhor ordem (p,d,q)
            from pmdarima import auto_arima
            model = auto_arima(
                df['y'],
                start_p=1, start_q=1,
                max_p=3, max_q=3,
                seasonal=False,
                stepwise=True,
                suppress_warnings=True,
                error_action='ignore'
            )

            # Fazer previsão
            forecast, conf_int = model.predict(n_periods=horizon_minutes, return_conf_int=True)

            # Construir resultado
            future_timestamps = pd.date_range(
                start=df['ds'].max() + timedelta(minutes=1),
                periods=horizon_minutes,
                freq='T'
            )

            result = {
                'forecast': [
                    {
                        'timestamp': ts.isoformat(),
                        'ticket_count': max(0, int(val)),
                        'resource_demand': self._estimate_resource_demand(val),
                        'confidence_lower': max(0, int(conf_int[i, 0])),
                        'confidence_upper': max(0, int(conf_int[i, 1])),
                    }
                    for i, (ts, val) in enumerate(zip(future_timestamps, forecast))
                ],
                'metadata': {
                    'model_type': 'ARIMA',
                    'model_order': str(model.order),
                    'horizon_requested': horizon_minutes,
                    'forecast_generated_at': datetime.utcnow().isoformat(),
                }
            }

            return result

        except Exception as e:
            logger.error(f"Erro no fallback ARIMA: {e}")
            raise
