import uuid
from typing import Optional

import numpy as np
import structlog
from scipy import stats
from sklearn.ensemble import IsolationForest

from ..models.insight import (
    AnalystInsight,
    InsightType,
    Priority,
    Recommendation,
    TimeWindow,
)

logger = structlog.get_logger()


class AnalyticsEngine:
    def __init__(self, min_confidence: float = 0.7, insight_generator=None):
        self.min_confidence = min_confidence
        self.insight_generator = insight_generator

    async def analyze_telemetry_window(
        self, telemetry_data: list[dict], window: TimeWindow
    ) -> Optional[AnalystInsight]:
        """Analisar janela de telemetria e gerar insight se houver anomalias."""
        try:
            if not telemetry_data:
                return None

            # Extrair métricas
            metrics = self._extract_metrics(telemetry_data)

            # Detectar anomalias em todas as métricas
            all_anomalies = []

            # Latência
            latency_anomalies = self._detect_metric_anomalies(
                "latency_ms", metrics.get("latency_values", [])
            )
            all_anomalies.extend([{**a, "metric": "latency_ms"} for a in latency_anomalies])

            # Error Rate
            error_rate_anomalies = self._detect_metric_anomalies(
                "error_rate", metrics.get("error_rate_values", [])
            )
            all_anomalies.extend([{**a, "metric": "error_rate"} for a in error_rate_anomalies])

            # Throughput
            throughput_anomalies = self._detect_metric_anomalies(
                "throughput", metrics.get("throughput_values", [])
            )
            all_anomalies.extend([{**a, "metric": "throughput"} for a in throughput_anomalies])

            # Se não há anomalias, retornar None
            if not all_anomalies:
                return None

            logger.info("anomalies_detected", count=len(all_anomalies))

            # Calcular prioridade baseada na severidade das anomalias
            max_zscore = max((a.get("zscore", 0) for a in all_anomalies), default=0)
            priority = Priority.CRITICAL if max_zscore >= 5 else Priority.HIGH

            # Calcular confidence score
            confidence_score = min(max_zscore / 5.0, 1.0)
            confidence_score = max(confidence_score, self.min_confidence)

            # Calcular impact score baseado no número de anomalias
            impact_score = min(len(all_anomalies) / len(telemetry_data), 1.0)

            # Encontrar anomalia crítica (maior zscore)
            critical_anomaly = max(all_anomalies, key=lambda a: a.get("zscore", 0))

            # Gerar recomendações
            recommendations = self._generate_recommendations(all_anomalies, metrics)

            # Criar AnalystInsight
            insight = AnalystInsight(
                insight_id=str(uuid.uuid4()),
                correlation_id=str(uuid.uuid4()),
                trace_id=str(uuid.uuid4()),
                span_id=str(uuid.uuid4()),
                insight_type=InsightType.OPERATIONAL,
                priority=priority,
                title=f"Anomalia de {critical_anomaly.get('metric', 'latência')} detectada",
                summary=f"Detectada(s) {len(all_anomalies)} anomalia(s) na janela analisada",
                detailed_analysis=(
                    f"Valor crítico: {critical_anomaly['value']:.2f} "
                    f"({critical_anomaly.get('metric', 'latency_ms')}) "
                    f"(Z-Score: {critical_anomaly.get('zscore', 0):.2f})"
                ),
                data_sources=["telemetry", "kafka"],
                metrics={
                    "anomaly_count": len(all_anomalies),
                    "max_latency": (
                        critical_anomaly["value"]
                        if critical_anomaly.get("metric") == "latency_ms"
                        else 0
                    ),
                    "max_value": critical_anomaly["value"],
                    "max_zscore": critical_anomaly.get("zscore", 0),
                },
                confidence_score=confidence_score,
                impact_score=impact_score,
                recommendations=recommendations,
                related_entities=[],
                time_window=window,
                tags=["anomaly", "telemetry"],
            )

            return insight
        except Exception as e:
            logger.error("analyze_telemetry_window_failed", error=str(e))
            return None

    def _detect_metric_anomalies(self, metric_name: str, values: list[float]) -> list[dict]:
        """Detectar anomalias em uma métrica específica."""
        anomalies = []

        if not values or len(values) < 1:
            return anomalies

        # Detecção simples para poucos dados (2-3 valores)
        if len(values) == 2:
            val1, val2 = values[0], values[1]
            # Se um valor é > 3x o outro, é anomalia
            if val1 > val2 * 3 or val2 > val1 * 3:
                larger_idx = 0 if val1 > val2 else 1
                is_critical = (
                    values[larger_idx] > 5000
                    if metric_name == "latency_ms"
                    else values[larger_idx] > 1.0
                )
                anomalies.append(
                    {
                        "index": larger_idx,
                        "value": float(values[larger_idx]),
                        "zscore": 5.0 if is_critical else 3.0,
                        "method": "simple_ratio",
                    }
                )
                return anomalies

        # Detecção de valores absolutos extremos (para qualquer número de valores)
        critical_threshold = (
            5000 if metric_name == "latency_ms" else 1.0 if metric_name == "error_rate" else 0
        )
        absolute_threshold = (
            1000 if metric_name == "latency_ms" else 0.1 if metric_name == "error_rate" else 0
        )

        for i, val in enumerate(values):
            if val > critical_threshold:
                if not any(a["index"] == i for a in anomalies):
                    anomalies.append(
                        {
                            "index": i,
                            "value": float(val),
                            "zscore": 5.0,
                            "method": "absolute_critical",
                        }
                    )
            elif val > absolute_threshold:
                # Verificar se é significativamente maior que os outros valores
                if len(values) >= 3:
                    avg_val = np.mean(values)
                    if val > avg_val * 3:
                        if not any(a["index"] == i for a in anomalies):
                            anomalies.append(
                                {
                                    "index": i,
                                    "value": float(val),
                                    "zscore": 3.0,
                                    "method": "relative_ratio",
                                }
                            )

        # Método Z-Score (para 3+ valores)
        if len(values) >= 3:
            try:
                arr = np.array(values)
                z_scores = np.abs(stats.zscore(arr))
                threshold = 1.95 if len(arr) >= 5 else 1.5

                anomaly_indices = np.where(z_scores > threshold)[0]
                for i in anomaly_indices:
                    if not any(a["index"] == i for a in anomalies):
                        anomalies.append(
                            {
                                "index": i,
                                "value": float(arr[i]),
                                "zscore": float(z_scores[i]),
                                "method": "zscore",
                            }
                        )
            except Exception:
                pass

        # Método IQR para valores extremos
        try:
            if len(values) >= 4:
                q75 = np.percentile(values, 75)
                q25 = np.percentile(values, 25)
                iqr = q75 - q25
                upper_bound = q75 + 1.5 * iqr

                for i, val in enumerate(values):
                    if val > upper_bound and val > absolute_threshold:
                        if not any(a["index"] == i for a in anomalies):
                            is_critical = val > critical_threshold
                            anomalies.append(
                                {
                                    "index": i,
                                    "value": float(val),
                                    "zscore": 5.0 if is_critical else 3.0,
                                    "method": "extreme_value",
                                }
                            )
        except Exception:
            pass

        return anomalies

    def _generate_recommendations(
        self, anomalies: list[dict], metrics: dict[str, list[float]]
    ) -> list[Recommendation]:
        """Gerar recomendações baseadas nas anomalias detectadas."""
        recommendations = []

        # Sempre adicionar pelo menos uma recomendação
        if len(anomalies) >= 1:
            recommendations.append(
                Recommendation(
                    action="Investigar anomalia detectada",
                    priority="HIGH",
                    estimated_impact=0.7,
                )
            )

        if len(anomalies) > 1:
            recommendations.append(
                Recommendation(
                    action="Investigar padrão de múltiplas anomalias",
                    priority="HIGH",
                    estimated_impact=0.8,
                )
            )

        max_anomaly = max(anomalies, key=lambda a: a.get("zscore", 0))
        if max_anomaly.get("zscore", 0) >= 5:
            recommendations.append(
                Recommendation(
                    action="Ação imediata: valor crítico detectado",
                    priority="CRITICAL",
                    estimated_impact=0.95,
                )
            )

        return recommendations

    def detect_anomalies(
        self, metric_name: str, values: list[float], method: str = "zscore", threshold: float = 3.0
    ) -> list[dict]:
        """Detectar anomalias"""
        try:
            if not values or len(values) < 3:
                return []

            arr = np.array(values)

            if method == "zscore":
                z_scores = np.abs(stats.zscore(arr))
                anomaly_indices = np.where(z_scores > threshold)[0]
                return [
                    {"index": int(i), "value": float(arr[i]), "zscore": float(z_scores[i])}
                    for i in anomaly_indices
                ]

            elif method == "iqr":
                q1, q3 = np.percentile(arr, [25, 75])
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                anomaly_indices = np.where((arr < lower_bound) | (arr > upper_bound))[0]
                return [
                    {
                        "index": int(i),
                        "value": float(arr[i]),
                        "bounds": [float(lower_bound), float(upper_bound)],
                    }
                    for i in anomaly_indices
                ]

            elif method == "isolation_forest":
                if len(arr) < 10:
                    return []
                clf = IsolationForest(contamination=0.1, random_state=42)
                predictions = clf.fit_predict(arr.reshape(-1, 1))
                anomaly_indices = np.where(predictions == -1)[0]
                return [{"index": int(i), "value": float(arr[i])} for i in anomaly_indices]

            return []
        except Exception as e:
            logger.error("detect_anomalies_failed", error=str(e))
            return []

    def calculate_trend(self, metric_name: str, time_series: list[tuple[int, float]]) -> dict:
        """Calcular tendência"""
        try:
            if not time_series or len(time_series) < 2:
                return {"trend": "insufficient_data"}

            times = np.array([t[0] for t in time_series])
            values = np.array([t[1] for t in time_series])

            # Regressão linear
            slope, intercept, r_value, p_value, std_err = stats.linregress(times, values)

            trend_direction = "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable"

            return {
                "trend": trend_direction,
                "slope": float(slope),
                "r_squared": float(r_value**2),
                "p_value": float(p_value),
                "significant": p_value < 0.05,
            }
        except Exception as e:
            logger.error("calculate_trend_failed", error=str(e))
            return {"trend": "error"}

    def calculate_correlation(self, metric1: list[float], metric2: list[float]) -> float:
        """Calcular correlação de Pearson"""
        try:
            if len(metric1) != len(metric2) or len(metric1) < 2:
                return 0.0

            correlation, _ = stats.pearsonr(metric1, metric2)
            return float(correlation)
        except Exception as e:
            logger.error("calculate_correlation_failed", error=str(e))
            return 0.0

    def aggregate_by_dimension(
        self, data: list[dict], dimensions: list[str], metrics: list[str]
    ) -> dict:
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
                            "avg": float(np.mean(values)),
                            "max": float(np.max(values)),
                            "min": float(np.min(values)),
                            "count": len(values),
                        }

            return result
        except Exception as e:
            logger.error("aggregate_by_dimension_failed", error=str(e))
            return {}

    def _extract_metrics(self, telemetry_data: list[dict]) -> dict[str, list[float]]:
        """Extrair métricas de telemetria"""
        metrics = {"latency_values": [], "error_rate_values": [], "throughput_values": []}

        for item in telemetry_data:
            # Suporte a dois formatos: {"metric": "latency_ms", "value": 50.0}
            # e {"latency_ms": 50.0}
            metric_name = item.get("metric")
            value = item.get("value")

            if metric_name and value is not None:
                # Formato: {"metric": "latency_ms", "value": 50.0}
                if metric_name == "latency_ms":
                    metrics["latency_values"].append(float(value))
                elif metric_name == "error_rate":
                    metrics["error_rate_values"].append(float(value))
                elif metric_name == "throughput":
                    metrics["throughput_values"].append(float(value))
            else:
                # Formato: {"latency_ms": 50.0}
                if "latency_ms" in item:
                    metrics["latency_values"].append(float(item["latency_ms"]))
                if "error_rate" in item:
                    metrics["error_rate_values"].append(float(item["error_rate"]))
                if "throughput" in item:
                    metrics["throughput_values"].append(float(item["throughput"]))

        return metrics
