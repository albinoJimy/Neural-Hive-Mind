"""
Feature Engineering para modelos de ML de otimização de agendamento.

Extração e transformação de features de dados históricos do ClickHouse
e métricas em tempo real para alimentar LoadPredictor e SchedulingOptimizer.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, StandardScaler

logger = logging.getLogger(__name__)


class FeatureEngineering:
    """
    Utilitários de engenharia de features para ML de agendamento.

    Processa dados brutos do ClickHouse e métricas em features estruturadas
    para modelos Prophet, ARIMA e Q-learning.
    """

    def __init__(self, redis_client, config: Dict):
        """
        Args:
            redis_client: Cliente Redis para caching de agregações
            config: Configuração
        """
        self.redis = redis_client
        self.config = config

        # Scalers para normalização
        self.minmax_scaler = MinMaxScaler()
        self.standard_scaler = StandardScaler()

        # Cache TTL para agregações
        self.cache_ttl = 3600  # 1 hora

    async def extract_load_features(
        self,
        clickhouse_data: List[Dict]
    ) -> pd.DataFrame:
        """
        Extrai features de séries temporais de dados históricos.

        Args:
            clickhouse_data: Dados brutos do ClickHouse (execution_logs)

        Returns:
            DataFrame com features agregadas:
                - timestamp
                - ticket_count (total por hora)
                - avg_duration (média de duração)
                - resource_cpu_avg, resource_memory_avg
                - lag_1h, lag_6h, lag_24h (valores defasados)
                - hour_of_day, day_of_week (features cíclicas)
                - is_weekend, is_holiday
        """
        if not clickhouse_data:
            return pd.DataFrame()

        # Converter para DataFrame
        df = pd.DataFrame(clickhouse_data)

        # Converter timestamp
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Agregar por hora
        # Verificar se colunas já estão agregadas ou precisam ser agregadas
        if 'resource_cpu_avg' in df.columns:
            # Dados já vêm agregados do ClickHouse
            hourly = df.groupby(pd.Grouper(key='timestamp', freq='H')).agg({
                'ticket_count': 'sum',  # Somar tickets já agregados
                'avg_duration_ms': 'mean',
                'resource_cpu_avg': 'mean',
                'resource_memory_avg': 'mean',
            }).reset_index()
            hourly.rename(columns={'avg_duration_ms': 'avg_duration'}, inplace=True)
        else:
            # Dados brutos precisam ser agregados
            hourly = df.groupby(pd.Grouper(key='timestamp', freq='H')).agg({
                'ticket_id': 'count',  # Contar tickets
                'actual_duration_ms': 'mean',
                'resource_cpu': 'mean',
                'resource_memory': 'mean',
            }).reset_index()
            hourly.rename(columns={
                'ticket_id': 'ticket_count',
                'actual_duration_ms': 'avg_duration',
                'resource_cpu': 'resource_cpu_avg',
                'resource_memory': 'resource_memory_avg',
            }, inplace=True)

        # Features de lag (valores passados)
        hourly['lag_1h'] = hourly['ticket_count'].shift(1)
        hourly['lag_6h'] = hourly['ticket_count'].shift(6)
        hourly['lag_24h'] = hourly['ticket_count'].shift(24)

        # Features cíclicas (hora do dia e dia da semana)
        hourly['hour_of_day'] = hourly['timestamp'].dt.hour
        hourly['day_of_week'] = hourly['timestamp'].dt.dayofweek

        # Encoding cíclico (sin/cos) para hora
        hourly['hour_sin'] = np.sin(2 * np.pi * hourly['hour_of_day'] / 24)
        hourly['hour_cos'] = np.cos(2 * np.pi * hourly['hour_of_day'] / 24)

        # Encoding cíclico para dia da semana
        hourly['day_sin'] = np.sin(2 * np.pi * hourly['day_of_week'] / 7)
        hourly['day_cos'] = np.cos(2 * np.pi * hourly['day_of_week'] / 7)

        # Flags de final de semana e feriado
        hourly['is_weekend'] = (hourly['day_of_week'] >= 5).astype(int)
        hourly['is_holiday'] = hourly['timestamp'].apply(self._is_brazilian_holiday).astype(int)

        # Preencher NaNs de lag com 0
        hourly.fillna(0, inplace=True)

        logger.info(f"Features extraídas: {len(hourly)} pontos, {len(hourly.columns)} features")
        return hourly

    async def extract_scheduling_state_features(
        self,
        current_metrics: Dict
    ) -> np.ndarray:
        """
        Extrai features de estado atual para RL de agendamento.

        Args:
            current_metrics: Métricas atuais (load, utilization, queue_depth, sla_compliance)

        Returns:
            Vetor numpy normalizado com features:
                [load_normalized, utilization, queue_depth_normalized,
                 sla_compliance, recent_optimization_count, hour_sin, hour_cos]
        """
        # Extrair valores
        load = current_metrics.get('current_load', 0)
        utilization = current_metrics.get('worker_utilization', 0)
        queue_depth = current_metrics.get('queue_depth', 0)
        sla_compliance = current_metrics.get('sla_compliance', 1.0)
        recent_optimizations = current_metrics.get('recent_optimization_count', 0)

        # Normalizar valores
        load_norm = min(1.0, load / 1000.0)  # Assumir 1000 como carga máxima
        queue_norm = min(1.0, queue_depth / 100.0)  # 100 como fila máxima
        optimizations_norm = min(1.0, recent_optimizations / 10.0)

        # Features temporais cíclicas
        now = datetime.utcnow()
        hour = now.hour
        hour_sin = np.sin(2 * np.pi * hour / 24)
        hour_cos = np.cos(2 * np.pi * hour / 24)

        # Construir vetor de features
        features = np.array([
            load_norm,
            utilization,
            queue_norm,
            sla_compliance,
            optimizations_norm,
            hour_sin,
            hour_cos,
        ])

        return features

    async def compute_historical_aggregates(
        self,
        clickhouse_client,
        window_days: int = 30
    ) -> Dict:
        """
        Calcula agregações estatísticas de dados históricos.

        Args:
            clickhouse_client: Cliente ClickHouse
            window_days: Janela de dados para agregação

        Returns:
            Dict com estatísticas:
                - por task_type: {mean, std, p50, p95, p99}
                - por risk_band: {mean, std, ...}
                - por hour_of_day: {mean, std, ...}
        """
        # Verificar cache
        cache_key = f"historical_aggregates:{window_days}d"
        cached = await self._get_cached_aggregates(cache_key)
        if cached:
            return cached

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=window_days)

        try:
            # Buscar dados históricos
            data = await clickhouse_client.query_execution_timeseries(
                start_timestamp=start_time,
                end_timestamp=end_time,
                aggregation_interval='1h'
            )

            if not data:
                return {}

            df = pd.DataFrame(data)

            # Agregar por task_type
            aggregates = {'by_task_type': {}, 'by_risk_band': {}, 'by_hour_of_day': {}}

            if 'task_type' in df.columns:
                for task_type in df['task_type'].unique():
                    subset = df[df['task_type'] == task_type]['ticket_count']
                    aggregates['by_task_type'][task_type] = {
                        'mean': float(subset.mean()),
                        'std': float(subset.std()),
                        'p50': float(subset.quantile(0.5)),
                        'p95': float(subset.quantile(0.95)),
                        'p99': float(subset.quantile(0.99)),
                    }

            if 'risk_band' in df.columns:
                for risk_band in df['risk_band'].unique():
                    subset = df[df['risk_band'] == risk_band]['ticket_count']
                    aggregates['by_risk_band'][risk_band] = {
                        'mean': float(subset.mean()),
                        'std': float(subset.std()),
                        'p50': float(subset.quantile(0.5)),
                        'p95': float(subset.quantile(0.95)),
                        'p99': float(subset.quantile(0.99)),
                    }

            # Agregar por hora do dia
            df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
            for hour in range(24):
                subset = df[df['hour'] == hour]['ticket_count']
                if len(subset) > 0:
                    aggregates['by_hour_of_day'][hour] = {
                        'mean': float(subset.mean()),
                        'std': float(subset.std()),
                    }

            # Cachear
            await self._cache_aggregates(cache_key, aggregates, ttl=self.cache_ttl)

            logger.info(f"Agregações computadas para {window_days} dias")
            return aggregates

        except Exception as e:
            logger.error(f"Erro ao computar agregações: {e}")
            return {}

    def normalize_timeseries(
        self,
        data: pd.DataFrame,
        method: str = 'minmax',
        columns: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Normaliza séries temporais.

        Args:
            data: DataFrame com séries temporais
            method: 'minmax' (0-1) ou 'standard' (z-score)
            columns: Colunas a normalizar (None = todas numéricas)

        Returns:
            DataFrame normalizado
        """
        df = data.copy()

        # Selecionar colunas numéricas se não especificado
        if columns is None:
            columns = df.select_dtypes(include=[np.number]).columns.tolist()

        # Aplicar normalização
        if method == 'minmax':
            df[columns] = self.minmax_scaler.fit_transform(df[columns])
        elif method == 'standard':
            df[columns] = self.standard_scaler.fit_transform(df[columns])
        else:
            raise ValueError(f"Método inválido: {method}")

        logger.debug(f"Normalizadas {len(columns)} colunas usando {method}")
        return df

    def encode_risk_band(self, risk_band: str) -> int:
        """
        Codifica risk_band em valor numérico.

        Args:
            risk_band: 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'

        Returns:
            Valor numérico (0-3)
        """
        encoding = {
            'LOW': 0,
            'MEDIUM': 1,
            'HIGH': 2,
            'CRITICAL': 3,
        }
        return encoding.get(risk_band.upper(), 1)

    def compute_qos_score(self, metrics: Dict) -> float:
        """
        Calcula QoS score agregado baseado em múltiplas métricas.

        Args:
            metrics: Dict com sla_compliance, avg_duration, error_rate

        Returns:
            Score normalizado 0-1 (1=melhor)
        """
        sla = metrics.get('sla_compliance', 0)
        duration_penalty = min(1.0, metrics.get('avg_duration_ms', 0) / 10000.0)  # 10s como referência
        error_rate = metrics.get('error_rate', 0)

        # Combinar com pesos
        qos = (sla * 0.6) - (duration_penalty * 0.2) - (error_rate * 0.2)

        return max(0.0, min(1.0, qos))

    def decompose_trend_seasonality(
        self,
        timeseries: pd.Series,
        period: int = 24
    ) -> Dict:
        """
        Decompõe série temporal em tendência e sazonalidade.

        Args:
            timeseries: Série temporal (ex: ticket counts)
            period: Período de sazonalidade (24 para diário)

        Returns:
            Dict com trend, seasonal, residual
        """
        from statsmodels.tsa.seasonal import seasonal_decompose

        try:
            decomposition = seasonal_decompose(
                timeseries,
                model='additive',
                period=period,
                extrapolate_trend='freq'
            )

            return {
                'trend': decomposition.trend.fillna(0).tolist(),
                'seasonal': decomposition.seasonal.fillna(0).tolist(),
                'residual': decomposition.resid.fillna(0).tolist(),
            }

        except Exception as e:
            logger.error(f"Erro na decomposição: {e}")
            return {
                'trend': [0] * len(timeseries),
                'seasonal': [0] * len(timeseries),
                'residual': [0] * len(timeseries),
            }

    def _is_brazilian_holiday(self, date: datetime) -> bool:
        """Verifica se data é feriado brasileiro."""
        import holidays
        br_holidays = holidays.Brazil()
        return date.date() in br_holidays

    async def _get_cached_aggregates(self, cache_key: str) -> Optional[Dict]:
        """Recupera agregações do cache Redis."""
        try:
            import json
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Erro ao ler cache: {e}")
        return None

    async def _cache_aggregates(self, cache_key: str, aggregates: Dict, ttl: int) -> None:
        """Armazena agregações no cache Redis."""
        try:
            import json
            await self.redis.setex(cache_key, ttl, json.dumps(aggregates))
        except Exception as e:
            logger.warning(f"Erro ao cachear: {e}")
