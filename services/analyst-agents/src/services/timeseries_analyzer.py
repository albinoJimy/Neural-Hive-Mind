"""
Time-Series Analysis Service.
Implementa detecção de anomalias, tendências e sazonalidade.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import stats
from scipy.signal import find_peaks

from ..models.insight_extended import (
    AnomalyDetectionQuery,
    AnomalyDetectionResponse,
    AnomalyPoint,
    TimeSeriesResponse,
)

logger = structlog.get_logger()


class TimeSeriesAnalyzer:
    """Analisador de séries temporais."""

    def __init__(
        self,
        anomaly_threshold: float = 2.5,
        min_data_points: int = 10,
        cache_ttl_seconds: int = 3600,
    ):
        self.anomaly_threshold = anomaly_threshold
        self.min_data_points = min_data_points
        self.cache_ttl_seconds = cache_ttl_seconds

    def analyze_trend(self, data: List[Tuple[datetime, float]]) -> Dict[str, Any]:
        """
        Analisar tendência da série temporal.

        Returns:
            Dict com 'trend' (increasing/decreasing/stable) e 'slope'
        """
        if len(data) < self.min_data_points:
            return {"trend": "stable", "slope": 0.0, "confidence": 0.0}

        timestamps = np.array([(t - data[0][0]).total_seconds() for t, _ in data])
        values = np.array([v for _, v in data])

        # Linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(timestamps, values)

        # Classify trend
        if abs(slope) < 0.001:
            trend = "stable"
        elif slope > 0:
            trend = "increasing"
        else:
            trend = "decreasing"

        return {
            "trend": trend,
            "slope": float(slope),
            "intercept": float(intercept),
            "r_squared": float(r_value**2),
            "p_value": float(p_value),
            "confidence": float(abs(r_value)),
        }

    def detect_anomalies_zscore(
        self, data: List[Tuple[datetime, float]], threshold: Optional[float] = None
    ) -> List[AnomalyPoint]:
        """
        Detectar anomalias usando Z-Score.

        Args:
            data: Lista de tuplas (timestamp, value)
            threshold: Limiar de z-score (default: self.anomaly_threshold)

        Returns:
            Lista de anomalias detectadas
        """
        if threshold is None:
            threshold = self.anomaly_threshold

        if len(data) < self.min_data_points:
            return []

        timestamps = [t for t, _ in data]
        values = np.array([v for _, v in data])

        mean = np.mean(values)
        std = np.std(values)

        if std == 0:
            return []

        z_scores = np.abs((values - mean) / std)
        anomaly_indices = np.where(z_scores > threshold)[0]

        anomalies = []
        for idx in anomaly_indices:
            score = z_scores[idx]
            if score > 3.0:
                severity = "high"
            elif score > 2.0:
                severity = "medium"
            else:
                severity = "low"

            anomalies.append(
                AnomalyPoint(
                    timestamp=timestamps[idx],
                    value=float(values[idx]),
                    score=float(score),
                    severity=severity,
                )
            )

        return anomalies

    def detect_anomalies_iqr(
        self, data: List[Tuple[datetime, float]], multiplier: float = 1.5
    ) -> List[AnomalyPoint]:
        """
        Detectar anomalias usando IQR (Interquartile Range).

        Args:
            data: Lista de tuplas (timestamp, value)
            multiplier: Multiplicador IQR (default: 1.5)

        Returns:
            Lista de anomalias detectadas
        """
        if len(data) < self.min_data_points:
            return []

        [t for t, _ in data]
        values = np.array([v for _, v in data])

        q1 = np.percentile(values, 25)
        q3 = np.percentile(values, 75)
        iqr = q3 - q1

        if iqr == 0:
            return []

        lower_bound = q1 - multiplier * iqr
        upper_bound = q3 + multiplier * iqr

        anomalies = []
        for i, (ts, val) in enumerate(data):
            if val < lower_bound or val > upper_bound:
                # Calculate severity based on distance from bounds
                if val < lower_bound:
                    distance = (lower_bound - val) / iqr
                else:
                    distance = (val - upper_bound) / iqr

                if distance > 2.0:
                    severity = "high"
                elif distance > 1.0:
                    severity = "medium"
                else:
                    severity = "low"

                anomalies.append(
                    AnomalyPoint(
                        timestamp=ts,
                        value=float(val),
                        score=float(distance),
                        severity=severity,
                    )
                )

        return anomalies

    def detect_anomalies_moving_avg(
        self, data: List[Tuple[datetime, float]], window: int = 5, std_multiplier: float = 2.0
    ) -> List[AnomalyPoint]:
        """
        Detectar anomalias usando média móvel.

        Args:
            data: Lista de tuplas (timestamp, value)
            window: Janela da média móvel
            std_multiplier: Multiplicador de desvio padrão

        Returns:
            Lista de anomalias detectadas
        """
        if len(data) < window + self.min_data_points:
            return []

        timestamps = [t for t, _ in data]
        values = np.array([v for _, v in data])

        anomalies = []

        for i in range(window, len(values)):
            window_values = values[i - window : i]
            window_mean = np.mean(window_values)
            window_std = np.std(window_values)

            if window_std == 0:
                continue

            current_value = values[i]
            z_score = abs((current_value - window_mean) / window_std)

            if z_score > std_multiplier:
                if z_score > 3.0:
                    severity = "high"
                elif z_score > 2.0:
                    severity = "medium"
                else:
                    severity = "low"

                anomalies.append(
                    AnomalyPoint(
                        timestamp=timestamps[i],
                        value=float(current_value),
                        score=float(z_score),
                        severity=severity,
                    )
                )

        return anomalies

    def detect_seasonality(
        self, data: List[Tuple[datetime, float]], period: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Detectar sazonalidade na série temporal.

        Args:
            data: Lista de tuplas (timestamp, value)
            period: Período esperado (None para auto-detectar)

        Returns:
            Dict com 'has_seasonality', 'period', 'strength'
        """
        if len(data) < 20:
            return {"has_seasonality": False, "period": None, "strength": 0.0}

        values = np.array([v for _, v in data])

        # Simple autocorrelation for seasonality detection
        max_lag = min(len(values) // 2, 50)
        autocorr = np.array(
            [1.0] + [np.corrcoef(values[:-i], values[i:])[0, 1] for i in range(1, max_lag)]
        )

        # Find peaks in autocorrelation
        peaks, properties = find_peaks(autocorr, height=0.2)

        if len(peaks) == 0:
            return {"has_seasonality": False, "period": None, "strength": 0.0}

        # Get the most significant period
        most_significant_peak = peaks[np.argmax(autocorr[peaks])]
        period_strength = autocorr[most_significant_peak]

        has_seasonality = period_strength > 0.3

        return {
            "has_seasonality": has_seasonality,
            "period": int(most_significant_peak) if has_seasonality else None,
            "strength": float(period_strength),
        }

    def calculate_statistics(self, data: List[Tuple[datetime, float]]) -> Dict[str, float]:
        """Calcular estatísticas básicas da série temporal."""
        if not data:
            return {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0, "count": 0}

        values = np.array([v for _, v in data])

        return {
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "median": float(np.median(values)),
            "count": len(values),
        }

    def generate_cache_key(
        self, metric_name: str, start: datetime, end: datetime, resolution: str
    ) -> str:
        """Gerar chave de cache para série temporal."""
        return f"{metric_name}:{start.isoformat()}:{end.isoformat()}:{resolution}"

    async def analyze_timeseries(
        self,
        metric_name: str,
        data: List[Tuple[datetime, float]],
        start: datetime,
        end: datetime,
        resolution: str,
        detect_anomalies: bool = True,
        anomaly_method: str = "zscore",
        anomaly_threshold: float = 2.5,
    ) -> TimeSeriesResponse:
        """
        Análise completa de série temporal.

        Args:
            metric_name: Nome da métrica
            data: Lista de tuplas (timestamp, value)
            start: Data inicial
            end: Data final
            resolution: Resolução dos dados
            detect_anomalies: Se deve detectar anomalias
            anomaly_method: Método de detecção (zscore, iqr, moving_avg)
            anomaly_threshold: Limiar para anomalias

        Returns:
            TimeSeriesResponse com dados completos
        """
        # Calculate statistics
        statistics = self.calculate_statistics(data)

        # Convert data to response format
        formatted_data = [{"timestamp": t.isoformat(), "value": float(v)} for t, v in data]

        response = TimeSeriesResponse(
            metric_name=metric_name,
            time_range={"start": start, "end": end},
            resolution=resolution,
            data=formatted_data,
            statistics=statistics,
        )

        return response

    async def detect_anomalies_async(
        self, query: AnomalyDetectionQuery, data: List[Tuple[datetime, float]]
    ) -> AnomalyDetectionResponse:
        """
        Detectar anomalias de forma assíncrona.

        Args:
            query: Query de detecção de anomalias
            data: Lista de tuplas (timestamp, value)

        Returns:
            AnomalyDetectionResponse com anomalias detectadas
        """
        if query.method == "zscore":
            anomalies = self.detect_anomalies_zscore(data, query.threshold)
        elif query.method == "iqr":
            anomalies = self.detect_anomalies_iqr(data, multiplier=query.threshold / 2.0)
        elif query.method == "moving_avg":
            anomalies = self.detect_anomalies_moving_avg(data, std_multiplier=query.threshold)
        else:
            anomalies = self.detect_anomalies_zscore(data, query.threshold)

        # Summary
        summary = {
            "total_anomalies": len(anomalies),
            "high_severity": sum(1 for a in anomalies if a.severity == "high"),
            "medium_severity": sum(1 for a in anomalies if a.severity == "medium"),
            "low_severity": sum(1 for a in anomalies if a.severity == "low"),
        }

        return AnomalyDetectionResponse(
            metric_name=query.metric_name,
            method=query.method,
            threshold=query.threshold,
            anomalies=anomalies,
            summary=summary,
        )
