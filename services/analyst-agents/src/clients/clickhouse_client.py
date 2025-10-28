import structlog
from clickhouse_driver import Client
from typing import List, Dict, Optional

logger = structlog.get_logger()


class ClickHouseClient:
    def __init__(self, host: str, port: int, user: str, password: Optional[str], database: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.client = None

    def initialize(self):
        """Conectar ao ClickHouse"""
        try:
            self.client = Client(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password or '',
                database=self.database
            )
            self.client.execute('SELECT 1')
            logger.info('clickhouse_client_initialized', host=self.host)
        except Exception as e:
            logger.error('clickhouse_client_initialization_failed', error=str(e))
            raise

    def close(self):
        """Fechar conexão"""
        if self.client:
            self.client.disconnect()
            logger.info('clickhouse_client_closed')

    def query(self, sql: str, parameters: dict = None) -> List[tuple]:
        """Executar consulta SQL"""
        try:
            result = self.client.execute(sql, parameters or {})
            return result
        except Exception as e:
            logger.error('clickhouse_query_failed', error=str(e), sql=sql[:100])
            return []

    def get_telemetry_aggregates(self, start: int, end: int, metrics: List[str], group_by: List[str]) -> List[Dict]:
        """Agregar telemetria por janela temporal"""
        metrics_str = ', '.join([f'avg({m}) as avg_{m}, max({m}) as max_{m}' for m in metrics])
        group_by_str = ', '.join(group_by)

        sql = f"""
        SELECT {group_by_str}, {metrics_str}
        FROM telemetry_metrics
        WHERE timestamp >= %(start)s AND timestamp <= %(end)s
        GROUP BY {group_by_str}
        """

        result = self.query(sql, {'start': start, 'end': end})
        return [dict(zip(group_by + [f'avg_{m}' for m in metrics] + [f'max_{m}' for m in metrics], row)) for row in result]

    def get_execution_statistics(self, start: int, end: int) -> Dict:
        """Estatísticas de execução"""
        sql = """
        SELECT
            quantile(0.50)(latency_ms) as p50_latency,
            quantile(0.95)(latency_ms) as p95_latency,
            quantile(0.99)(latency_ms) as p99_latency,
            countIf(status = 'error') / count() as error_rate,
            count() as total_executions
        FROM execution_logs
        WHERE timestamp >= %(start)s AND timestamp <= %(end)s
        """

        result = self.query(sql, {'start': start, 'end': end})
        if result:
            return {
                'p50_latency': result[0][0],
                'p95_latency': result[0][1],
                'p99_latency': result[0][2],
                'error_rate': result[0][3],
                'total_executions': result[0][4]
            }
        return {}

    def detect_metric_anomalies(self, metric_name: str, start: int, end: int, threshold: float = 3.0) -> List[Dict]:
        """Detectar anomalias em métricas usando desvio padrão"""
        sql = f"""
        WITH stats AS (
            SELECT avg({metric_name}) as mean, stddevPop({metric_name}) as stddev
            FROM telemetry_metrics
            WHERE timestamp >= %(start)s AND timestamp <= %(end)s
        )
        SELECT timestamp, {metric_name},
               abs({metric_name} - stats.mean) / stats.stddev as zscore
        FROM telemetry_metrics, stats
        WHERE timestamp >= %(start)s AND timestamp <= %(end)s
          AND abs({metric_name} - stats.mean) / stats.stddev > %(threshold)s
        ORDER BY zscore DESC
        """

        result = self.query(sql, {'start': start, 'end': end, 'threshold': threshold})
        return [{'timestamp': r[0], 'value': r[1], 'zscore': r[2]} for r in result]
