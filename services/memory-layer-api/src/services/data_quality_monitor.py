"""
Data Quality Monitor
"""
import statistics
import structlog
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional

from prometheus_client import Counter, Gauge

logger = structlog.get_logger(__name__)

# Métricas Prometheus
ANOMALIES_DETECTED = Counter(
    'memory_data_quality_anomalies_detected_total',
    'Total de anomalias detectadas em métricas de qualidade',
    ['data_type', 'metric', 'severity']
)

QUALITY_SCORE_GAUGE = Gauge(
    'neural_hive_data_quality_score',
    'Score geral de qualidade de dados (0-1)',
    ['data_type']
)


class DataQualityMonitor:
    """Monitor data quality across memory layers"""

    def __init__(self, mongodb_client, settings, clickhouse_client=None):
        self.mongodb = mongodb_client
        self.settings = settings
        self.clickhouse = clickhouse_client

    async def validate_data(
        self,
        data: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate data against schema

        Returns: (is_valid, violations)
        """
        violations = []

        # Completeness check
        required_fields = schema.get('required', [])
        for field in required_fields:
            if field not in data or data[field] is None:
                violations.append(f"Missing required field: {field}")

        # Type validation
        field_types = schema.get('types', {})
        for field, expected_type in field_types.items():
            if field in data and not isinstance(data[field], expected_type):
                violations.append(f"Invalid type for {field}: expected {expected_type}")

        # Range validation
        field_ranges = schema.get('ranges', {})
        for field, (min_val, max_val) in field_ranges.items():
            if field in data:
                value = data[field]
                if not (min_val <= value <= max_val):
                    violations.append(f"Value out of range for {field}: {value}")

        # Timestamp validation
        if 'created_at' in data:
            try:
                if isinstance(data['created_at'], str):
                    datetime.fromisoformat(data['created_at'])
            except ValueError:
                violations.append("Invalid timestamp format for created_at")

        is_valid = len(violations) == 0
        return is_valid, violations

    async def calculate_quality_score(
        self,
        data_type: str,
        sample_size: int = 1000
    ) -> Dict[str, float]:
        """
        Calculate quality scores by dimension

        Returns scores: completeness, accuracy, timeliness, uniqueness, consistency
        """
        try:
            # Sample data from MongoDB
            collection = self.settings.mongodb_context_collection
            sample = await self.mongodb.find(
                collection=collection,
                filter={'data_type': data_type} if data_type else {},
                limit=sample_size
            )

            if not sample:
                logger.warning("No data found for quality check", data_type=data_type)
                return self._empty_scores()

            # Calculate scores
            completeness = self._calculate_completeness(sample)
            accuracy = self._calculate_accuracy(sample)
            timeliness = self._calculate_timeliness(sample)
            uniqueness = self._calculate_uniqueness(sample)
            consistency = self._calculate_consistency(sample)

            # Overall score (weighted average)
            overall = (
                completeness * 0.25 +
                accuracy * 0.25 +
                timeliness * 0.20 +
                uniqueness * 0.15 +
                consistency * 0.15
            )

            scores = {
                'completeness_score': completeness,
                'accuracy_score': accuracy,
                'timeliness_score': timeliness,
                'uniqueness_score': uniqueness,
                'consistency_score': consistency,
                'overall_score': overall
            }

            logger.info("Quality scores calculated", data_type=data_type, overall=overall)
            return scores

        except Exception as e:
            logger.error("Quality score calculation failed", error=str(e))
            return self._empty_scores()

    def _calculate_completeness(self, sample: List[Dict]) -> float:
        """Calculate completeness score (% of non-null fields)"""
        if not sample:
            return 0.0

        total_fields = 0
        non_null_fields = 0

        for doc in sample:
            for key, value in doc.items():
                if key not in ['_id', 'created_at']:  # Exclude system fields
                    total_fields += 1
                    if value is not None and value != '':
                        non_null_fields += 1

        return (non_null_fields / total_fields * 100) if total_fields > 0 else 0.0

    def _calculate_accuracy(self, sample: List[Dict]) -> float:
        """Calculate accuracy score (% of valid records)"""
        if not sample:
            return 0.0

        valid_records = 0
        for doc in sample:
            # Basic validation checks
            is_valid = True

            # Check for required fields
            if not doc.get('entity_id'):
                is_valid = False

            # Check timestamp format
            if 'created_at' in doc:
                try:
                    if isinstance(doc['created_at'], str):
                        datetime.fromisoformat(doc['created_at'])
                except (ValueError, TypeError):
                    is_valid = False

            if is_valid:
                valid_records += 1

        return (valid_records / len(sample) * 100) if sample else 0.0

    def _calculate_timeliness(self, sample: List[Dict]) -> float:
        """Calculate timeliness score (% of fresh records)"""
        if not sample:
            return 0.0

        threshold = datetime.utcnow() - timedelta(hours=self.settings.freshness_threshold_hours)
        fresh_records = 0

        for doc in sample:
            created_at = doc.get('created_at')
            if created_at:
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at)
                    except ValueError:
                        continue
                if created_at >= threshold:
                    fresh_records += 1

        return (fresh_records / len(sample) * 100) if sample else 0.0

    def _calculate_uniqueness(self, sample: List[Dict]) -> float:
        """Calculate uniqueness score (% of unique entity_ids)"""
        if not sample:
            return 0.0

        entity_ids = [doc.get('entity_id') for doc in sample if doc.get('entity_id')]
        unique_ids = set(entity_ids)

        return (len(unique_ids) / len(entity_ids) * 100) if entity_ids else 0.0

    def _calculate_consistency(self, sample: List[Dict]) -> float:
        """Calculate consistency score"""
        # For now, simple heuristic - can be enhanced
        # Check for consistent schema across records
        if not sample:
            return 0.0

        field_sets = [set(doc.keys()) for doc in sample]
        if not field_sets:
            return 0.0

        # Find common fields
        common_fields = set.intersection(*field_sets) if field_sets else set()
        all_fields = set.union(*field_sets) if field_sets else set()

        return (len(common_fields) / len(all_fields) * 100) if all_fields else 0.0

    def _empty_scores(self) -> Dict[str, float]:
        """Return empty scores"""
        return {
            'completeness_score': 0.0,
            'accuracy_score': 0.0,
            'timeliness_score': 0.0,
            'uniqueness_score': 0.0,
            'consistency_score': 0.0,
            'overall_score': 0.0
        }

    async def detect_anomalies(
        self,
        data_type: str,
        metric: str,
        window_hours: int = 24,
        baseline_days: int = 7
    ) -> List[Dict]:
        """
        Detecta anomalias usando método estatístico (mean ± 3*std)

        Utiliza ClickHouse como fonte primária para estatísticas agregadas,
        com fallback para MongoDB se ClickHouse estiver indisponível.

        Args:
            data_type: Tipo de dado (context, plan, decision)
            metric: Métrica a analisar (completeness_score, freshness_score, consistency_score)
            window_hours: Janela de análise atual (padrão 24h)
            baseline_days: Dias para calcular baseline (padrão 7 dias)

        Returns:
            Lista de anomalias detectadas com timestamp, valor, z_score e severidade
        """
        try:
            now = datetime.utcnow()
            baseline_start = now - timedelta(days=baseline_days)
            window_start = now - timedelta(hours=window_hours)

            # Tenta usar ClickHouse como fonte primária
            baseline_stats = await self._get_baseline_from_clickhouse(
                data_type, metric, baseline_start, window_start
            )

            # Fallback para MongoDB se ClickHouse falhar ou não estiver disponível
            if baseline_stats is None:
                baseline_stats = await self._get_baseline_from_mongodb(
                    data_type, metric, baseline_start, window_start
                )

            if baseline_stats is None:
                logger.info(
                    "Dados de baseline insuficientes para detecção de anomalias",
                    data_type=data_type,
                    metric=metric
                )
                return []

            mean_val, std_val, count = baseline_stats

            if std_val == 0:
                logger.info(
                    "Desvio padrão zero, não é possível calcular Z-score",
                    data_type=data_type,
                    metric=metric
                )
                return []

            # Query dados da janela atual do MongoDB
            current_data = await self.mongodb.find(
                collection=self.settings.mongodb_quality_collection,
                filter={
                    'collection': data_type,
                    'timestamp': {'$gte': window_start}
                },
                sort=[('timestamp', 1)],
                limit=1000
            )

            anomalies = []
            for doc in current_data:
                metrics = doc.get('metrics', {})
                metric_category = metric.replace('_score', '')
                if metric_category in metrics:
                    score = metrics[metric_category].get(metric, 0.0)
                    if score > 0:
                        # Calcula Z-score
                        z_score = (score - mean_val) / std_val

                        # Identifica anomalias (|z| > 3)
                        if abs(z_score) > 3:
                            # Classifica severidade
                            if abs(z_score) > 5:
                                severity = 'high'
                            elif abs(z_score) > 4:
                                severity = 'medium'
                            else:
                                severity = 'low'

                            anomaly = {
                                'timestamp': doc.get('timestamp'),
                                'value': score,
                                'z_score': round(z_score, 3),
                                'severity': severity,
                                'metric': metric,
                                'data_type': data_type,
                                'baseline_mean': round(mean_val, 3),
                                'baseline_std': round(std_val, 3)
                            }
                            anomalies.append(anomaly)

                            # Incrementa métrica Prometheus
                            ANOMALIES_DETECTED.labels(
                                data_type=data_type,
                                metric=metric,
                                severity=severity
                            ).inc()

                            logger.warning(
                                "Anomalia detectada",
                                data_type=data_type,
                                metric=metric,
                                z_score=z_score,
                                severity=severity,
                                value=score,
                                baseline_mean=mean_val
                            )

            logger.info(
                "Detecção de anomalias concluída",
                data_type=data_type,
                metric=metric,
                anomalies_found=len(anomalies)
            )

            return anomalies

        except Exception as e:
            logger.error(
                "Erro na detecção de anomalias",
                error=str(e),
                data_type=data_type,
                metric=metric
            )
            return []

    async def _get_baseline_from_clickhouse(
        self,
        data_type: str,
        metric: str,
        baseline_start: datetime,
        window_start: datetime
    ) -> Optional[tuple]:
        """
        Busca estatísticas de baseline do ClickHouse.

        Returns:
            Tuple (mean, std, count) ou None se falhar
        """
        if not self.clickhouse or not hasattr(self.clickhouse, 'client') or not self.clickhouse.client:
            logger.debug("ClickHouse não disponível, usando fallback MongoDB")
            return None

        try:
            metric_column = self._map_metric_to_column(metric)

            # Query agregada para calcular mean e std diretamente no ClickHouse
            query = f"""
                SELECT
                    avg({metric_column}) as mean_val,
                    stddevPop({metric_column}) as std_val,
                    count() as cnt
                FROM {self.clickhouse.database}.data_quality_metrics
                WHERE data_type = %(data_type)s
                  AND timestamp >= %(baseline_start)s
                  AND timestamp < %(window_start)s
                  AND {metric_column} > 0
            """

            result = self.clickhouse.client.query(
                query,
                parameters={
                    'data_type': data_type,
                    'baseline_start': baseline_start,
                    'window_start': window_start
                }
            )

            if result.result_rows and len(result.result_rows) > 0:
                row = result.result_rows[0]
                mean_val, std_val, count = row[0], row[1], row[2]

                if count >= 10 and mean_val is not None:
                    logger.info(
                        "Baseline obtido do ClickHouse",
                        data_type=data_type,
                        metric=metric,
                        mean=mean_val,
                        std=std_val,
                        count=count
                    )
                    return (float(mean_val), float(std_val or 0), int(count))

            logger.info(
                "Dados insuficientes no ClickHouse",
                data_type=data_type,
                metric=metric
            )
            return None

        except Exception as e:
            logger.warning(
                "Falha ao buscar baseline do ClickHouse, usando fallback MongoDB",
                error=str(e),
                data_type=data_type,
                metric=metric
            )
            return None

    async def _get_baseline_from_mongodb(
        self,
        data_type: str,
        metric: str,
        baseline_start: datetime,
        window_start: datetime
    ) -> Optional[tuple]:
        """
        Busca estatísticas de baseline do MongoDB (fallback).

        Returns:
            Tuple (mean, std, count) ou None se falhar
        """
        try:
            historical_data = await self.mongodb.find(
                collection=self.settings.mongodb_quality_collection,
                filter={
                    'collection': data_type,
                    'timestamp': {'$gte': baseline_start, '$lt': window_start}
                },
                sort=[('timestamp', 1)],
                limit=10000
            )

            if len(historical_data) < 10:
                logger.info(
                    "Dados históricos insuficientes no MongoDB",
                    data_type=data_type,
                    metric=metric,
                    count=len(historical_data)
                )
                return None

            # Extrai valores da métrica do histórico
            baseline_values = []
            for doc in historical_data:
                metrics = doc.get('metrics', {})
                metric_category = metric.replace('_score', '')
                if metric_category in metrics:
                    score = metrics[metric_category].get(metric, 0.0)
                    if score > 0:
                        baseline_values.append(score)

            if len(baseline_values) < 5:
                logger.info(
                    "Valores de baseline insuficientes no MongoDB",
                    data_type=data_type,
                    metric=metric,
                    count=len(baseline_values)
                )
                return None

            mean_val = statistics.mean(baseline_values)
            std_val = statistics.stdev(baseline_values) if len(baseline_values) > 1 else 0.0

            logger.info(
                "Baseline obtido do MongoDB (fallback)",
                data_type=data_type,
                metric=metric,
                mean=mean_val,
                std=std_val,
                count=len(baseline_values)
            )

            return (mean_val, std_val, len(baseline_values))

        except Exception as e:
            logger.error(
                "Falha ao buscar baseline do MongoDB",
                error=str(e),
                data_type=data_type,
                metric=metric
            )
            return None

    def _map_metric_to_column(self, metric: str) -> str:
        """Mapeia nome da métrica para coluna do ClickHouse"""
        metric_mapping = {
            'completeness_score': 'completeness_score',
            'accuracy_score': 'accuracy_score',
            'freshness_score': 'freshness_score',
            'timeliness_score': 'timeliness_score',
            'uniqueness_score': 'uniqueness_score',
            'consistency_score': 'consistency_score',
            'overall_score': 'overall_score'
        }
        return metric_mapping.get(metric, 'overall_score')

    async def check_freshness(self, data_type: str) -> Dict[str, Any]:
        """Check data freshness"""
        try:
            # Find most recent record
            collection = self.settings.mongodb_context_collection
            latest = await self.mongodb.find_one(
                collection=collection,
                filter={'data_type': data_type} if data_type else {},
                sort=[('created_at', -1)]
            )

            if not latest:
                return {'status': 'no_data', 'age_hours': None}

            created_at = latest.get('created_at')
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)

            age = datetime.utcnow() - created_at
            age_hours = age.total_seconds() / 3600

            status = 'fresh'
            if age_hours > self.settings.freshness_threshold_hours:
                status = 'stale'

            return {
                'status': status,
                'age_hours': age_hours,
                'latest_timestamp': created_at.isoformat()
            }

        except Exception as e:
            logger.error("Freshness check failed", error=str(e))
            return {'status': 'error', 'age_hours': None}

    async def persist_quality_metrics(
        self,
        data_type: str,
        quality_scores: Dict[str, float],
        anomalies: List[Dict],
        freshness: Dict[str, Any]
    ):
        """Persist quality metrics to MongoDB"""
        try:
            document = {
                'data_type': data_type,
                'timestamp': datetime.utcnow(),
                'quality_scores': quality_scores,
                'anomalies': anomalies,
                'freshness': freshness,
                'overall_score': quality_scores.get('overall_score', 0.0)
            }

            await self.mongodb.insert_one(
                collection=self.settings.mongodb_quality_collection,
                document=document
            )

            logger.info("Quality metrics persisted", data_type=data_type,
                       overall_score=quality_scores.get('overall_score'))

        except Exception as e:
            logger.error("Failed to persist quality metrics", error=str(e))

    async def get_quality_trends(
        self,
        data_type: str,
        days: int = 7
    ) -> List[Dict]:
        """Get quality trends over time"""
        try:
            start_date = datetime.utcnow() - timedelta(days=days)

            trends = await self.mongodb.find(
                collection=self.settings.mongodb_quality_collection,
                filter={
                    'data_type': data_type,
                    'timestamp': {'$gte': start_date}
                },
                sort=[('timestamp', 1)],
                limit=1000
            )

            return trends

        except Exception as e:
            logger.error("Failed to get quality trends", error=str(e))
            return []
