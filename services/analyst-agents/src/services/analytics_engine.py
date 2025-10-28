import structlog
import numpy as np
from typing import List, Dict, Optional, Tuple
from scipy import stats
from sklearn.ensemble import IsolationForest
from ..models.insight import AnalystInsight, InsightType, Priority, TimeWindow

logger = structlog.get_logger()


class AnalyticsEngine:
    def __init__(self, min_confidence: float = 0.7):
        self.min_confidence = min_confidence

    async def analyze_telemetry_window(self, telemetry_data: List[dict], window: TimeWindow) -> Optional[AnalystInsight]:
        """Analisar janela de telemetria"""
        try:
            if not telemetry_data:
                return None

            # Extrair métricas
            metrics = self._extract_metrics(telemetry_data)

            # Detectar anomalias
            anomalies = self.detect_anomalies('latency_ms', metrics.get('latency_values', []), method='zscore')

            if anomalies:
                logger.info('anomalies_detected', count=len(anomalies))
                # Gerar insight de anomalia
                # (será implementado completamente com InsightGenerator)

            return None
        except Exception as e:
            logger.error('analyze_telemetry_window_failed', error=str(e))
            return None

    def detect_anomalies(self, metric_name: str, values: List[float], method: str = 'zscore', threshold: float = 3.0) -> List[dict]:
        """Detectar anomalias"""
        try:
            if not values or len(values) < 3:
                return []

            arr = np.array(values)

            if method == 'zscore':
                z_scores = np.abs(stats.zscore(arr))
                anomaly_indices = np.where(z_scores > threshold)[0]
                return [{'index': int(i), 'value': float(arr[i]), 'zscore': float(z_scores[i])} for i in anomaly_indices]

            elif method == 'iqr':
                q1, q3 = np.percentile(arr, [25, 75])
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                anomaly_indices = np.where((arr < lower_bound) | (arr > upper_bound))[0]
                return [{'index': int(i), 'value': float(arr[i]), 'bounds': [float(lower_bound), float(upper_bound)]} for i in anomaly_indices]

            elif method == 'isolation_forest':
                if len(arr) < 10:
                    return []
                clf = IsolationForest(contamination=0.1, random_state=42)
                predictions = clf.fit_predict(arr.reshape(-1, 1))
                anomaly_indices = np.where(predictions == -1)[0]
                return [{'index': int(i), 'value': float(arr[i])} for i in anomaly_indices]

            return []
        except Exception as e:
            logger.error('detect_anomalies_failed', error=str(e))
            return []

    def calculate_trend(self, metric_name: str, time_series: List[Tuple[int, float]]) -> Dict:
        """Calcular tendência"""
        try:
            if not time_series or len(time_series) < 2:
                return {'trend': 'insufficient_data'}

            times = np.array([t[0] for t in time_series])
            values = np.array([t[1] for t in time_series])

            # Regressão linear
            slope, intercept, r_value, p_value, std_err = stats.linregress(times, values)

            trend_direction = 'increasing' if slope > 0 else 'decreasing' if slope < 0 else 'stable'

            return {
                'trend': trend_direction,
                'slope': float(slope),
                'r_squared': float(r_value ** 2),
                'p_value': float(p_value),
                'significant': p_value < 0.05
            }
        except Exception as e:
            logger.error('calculate_trend_failed', error=str(e))
            return {'trend': 'error'}

    def calculate_correlation(self, metric1: List[float], metric2: List[float]) -> float:
        """Calcular correlação de Pearson"""
        try:
            if len(metric1) != len(metric2) or len(metric1) < 2:
                return 0.0

            correlation, _ = stats.pearsonr(metric1, metric2)
            return float(correlation)
        except Exception as e:
            logger.error('calculate_correlation_failed', error=str(e))
            return 0.0

    def aggregate_by_dimension(self, data: List[dict], dimensions: List[str], metrics: List[str]) -> Dict:
        """Agregar por dimensões"""
        try:
            aggregated = {}

            for item in data:
                key = tuple(item.get(dim) for dim in dimensions)

                if key not in aggregated:
                    aggregated[key] = {m: [] for m in metrics}

                for metric in metrics:
                    if metric in item:
                        aggregated[key][metric].append(item[metric])

            # Calcular estatísticas
            result = {}
            for key, metric_values in aggregated.items():
                result[key] = {}
                for metric, values in metric_values.items():
                    if values:
                        result[key][metric] = {
                            'avg': float(np.mean(values)),
                            'max': float(np.max(values)),
                            'min': float(np.min(values)),
                            'count': len(values)
                        }

            return result
        except Exception as e:
            logger.error('aggregate_by_dimension_failed', error=str(e))
            return {}

    def _extract_metrics(self, telemetry_data: List[dict]) -> Dict[str, List[float]]:
        """Extrair métricas de telemetria"""
        metrics = {'latency_values': [], 'error_rate_values': [], 'throughput_values': []}

        for item in telemetry_data:
            if 'latency_ms' in item:
                metrics['latency_values'].append(float(item['latency_ms']))
            if 'error_rate' in item:
                metrics['error_rate_values'].append(float(item['error_rate']))
            if 'throughput' in item:
                metrics['throughput_values'].append(float(item['throughput']))

        return metrics
