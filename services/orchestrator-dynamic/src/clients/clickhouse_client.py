"""
Cliente ClickHouse para o Orchestrator Dynamic.

Integração com ClickHouse para analytics de dados históricos de execução,
usado para feature engineering e treinamento de modelos ML.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from clickhouse_driver import Client as SyncClickHouseClient
import structlog

logger = structlog.get_logger(__name__)


class ClickHouseClient:
    """
    Cliente assíncrono para ClickHouse.

    Fornece queries otimizadas para:
    - Estatísticas históricas de duração por task_type/risk_band
    - Percentis de duração (P50/P95/P99)
    - Taxas de sucesso por hora do dia
    - Padrões de utilização de recursos
    """

    def __init__(self, config, redis_client=None):
        """
        Args:
            config: OrchestratorSettings com configurações ClickHouse
            redis_client: Cliente Redis para caching (opcional)
        """
        self.config = config
        self.redis = redis_client

        # Configurações de conexão
        self.host = getattr(config, 'clickhouse_host', 'clickhouse.clickhouse.svc.cluster.local')
        self.port = getattr(config, 'clickhouse_port', 9000)
        self.user = getattr(config, 'clickhouse_user', 'default')
        self.password = getattr(config, 'clickhouse_password', '')
        self.database = getattr(config, 'clickhouse_database', 'neural_hive_analytics')

        # Cliente síncrono (wrappado em async)
        self.client: Optional[SyncClickHouseClient] = None

        # Cache TTL (1 hora para estatísticas)
        self.cache_ttl = 3600

        # Query timeout
        self.query_timeout = 30

        self._initialized = False
        self.logger = logger.bind(component="clickhouse_client")

    async def initialize(self) -> None:
        """Estabelece conexão com ClickHouse com retry logic."""
        if self._initialized:
            return

        self.logger.info(
            "clickhouse_connecting",
            host=self.host,
            port=self.port,
            database=self.database
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Executar em thread pool (driver é síncrono)
                loop = asyncio.get_event_loop()
                self.client = await loop.run_in_executor(
                    None,
                    self._create_sync_client
                )

                # Testar conexão
                await self._execute_query("SELECT 1")

                self.logger.info("clickhouse_connected")
                self._initialized = True
                return

            except Exception as e:
                self.logger.warning(
                    "clickhouse_connection_failed",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e)
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    self.logger.error("clickhouse_connection_exhausted", error=str(e))
                    raise

    def _create_sync_client(self) -> SyncClickHouseClient:
        """Cria cliente síncrono."""
        return SyncClickHouseClient(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            connect_timeout=10,
            send_receive_timeout=self.query_timeout,
        )

    async def query_duration_stats_by_task_type(
        self,
        window_days: int = 30
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Query estatísticas de duração agrupadas por task_type e risk_band.

        Args:
            window_days: Janela de dados em dias

        Returns:
            Dict aninhado: {task_type: {risk_band: {avg_duration_ms, std_duration_ms, success_rate, ...}}}
        """
        cache_key = f"ch:duration_stats:{window_days}"
        cached = await self._get_cached_result(cache_key)
        if cached:
            return cached

        query = """
        SELECT
            task_type,
            risk_band,
            count(*) as sample_count,
            avg(actual_duration_ms) as avg_duration_ms,
            stddevPop(actual_duration_ms) as std_duration_ms,
            quantile(0.5)(actual_duration_ms) as p50_duration_ms,
            quantile(0.95)(actual_duration_ms) as p95_duration_ms,
            quantile(0.99)(actual_duration_ms) as p99_duration_ms,
            countIf(status = 'COMPLETED') * 100.0 / count(*) as success_rate,
            min(actual_duration_ms) as min_duration_ms,
            max(actual_duration_ms) as max_duration_ms
        FROM execution_logs
        WHERE timestamp >= now() - INTERVAL %(window_days)s DAY
          AND actual_duration_ms > 0
        GROUP BY task_type, risk_band
        HAVING count(*) >= 10
        ORDER BY task_type, risk_band
        """

        try:
            results = await self._execute_query(query, {'window_days': window_days})

            stats = {}
            for row in results:
                task_type = row[0] or 'UNKNOWN'
                risk_band = row[1] or 'medium'

                if task_type not in stats:
                    stats[task_type] = {}

                stats[task_type][risk_band] = {
                    'sample_count': int(row[2]),
                    'avg_duration_ms': float(row[3] or 60000.0),
                    'std_duration_ms': float(row[4] or 15000.0),
                    'p50_duration_ms': float(row[5] or 60000.0),
                    'p95_duration_ms': float(row[6] or 120000.0),
                    'p99_duration_ms': float(row[7] or 180000.0),
                    'success_rate': float(row[8] or 0.95),
                    'min_duration_ms': float(row[9] or 1000.0),
                    'max_duration_ms': float(row[10] or 300000.0)
                }

            await self._cache_result(cache_key, stats, ttl=self.cache_ttl)

            self.logger.info(
                "duration_stats_queried",
                task_types=len(stats),
                window_days=window_days
            )

            return stats

        except Exception as e:
            self.logger.error("duration_stats_query_failed", error=str(e))
            return {}

    async def query_success_rate_by_hour(
        self,
        window_days: int = 30
    ) -> Dict[int, Dict[str, float]]:
        """
        Query taxa de sucesso por hora do dia.

        Args:
            window_days: Janela de dados em dias

        Returns:
            Dict: {hour: {success_rate, avg_duration_ms, ticket_count}}
        """
        cache_key = f"ch:success_by_hour:{window_days}"
        cached = await self._get_cached_result(cache_key)
        if cached:
            return cached

        query = """
        SELECT
            toHour(timestamp) as hour_of_day,
            count(*) as ticket_count,
            avg(actual_duration_ms) as avg_duration_ms,
            countIf(status = 'COMPLETED') * 100.0 / count(*) as success_rate
        FROM execution_logs
        WHERE timestamp >= now() - INTERVAL %(window_days)s DAY
          AND actual_duration_ms > 0
        GROUP BY hour_of_day
        ORDER BY hour_of_day
        """

        try:
            results = await self._execute_query(query, {'window_days': window_days})

            hourly_stats = {}
            for row in results:
                hour = int(row[0])
                hourly_stats[hour] = {
                    'ticket_count': int(row[1]),
                    'avg_duration_ms': float(row[2] or 60000.0),
                    'success_rate': float(row[3] or 0.95)
                }

            await self._cache_result(cache_key, hourly_stats, ttl=self.cache_ttl)

            self.logger.debug(
                "success_by_hour_queried",
                hours=len(hourly_stats),
                window_days=window_days
            )

            return hourly_stats

        except Exception as e:
            self.logger.error("success_by_hour_query_failed", error=str(e))
            return {}

    async def query_resource_utilization_patterns(
        self,
        window_days: int = 7
    ) -> Dict[str, List[Dict]]:
        """
        Query padrões de utilização de recursos.

        Args:
            window_days: Janela de dados em dias

        Returns:
            Dict com séries temporais de utilização
        """
        cache_key = f"ch:resource_util:{window_days}"
        cached = await self._get_cached_result(cache_key)
        if cached:
            return cached

        query = """
        SELECT
            toStartOfHour(timestamp) as timestamp,
            avg(resource_cpu) as avg_cpu,
            avg(resource_memory) as avg_memory,
            count(*) as concurrent_tickets,
            countIf(status = 'RUNNING') as running_tickets
        FROM execution_logs
        WHERE timestamp >= now() - INTERVAL %(window_days)s DAY
        GROUP BY timestamp
        ORDER BY timestamp
        """

        try:
            results = await self._execute_query(query, {'window_days': window_days})

            data = []
            for row in results:
                data.append({
                    'timestamp': row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
                    'avg_cpu': float(row[1] or 0.0),
                    'avg_memory': float(row[2] or 0.0),
                    'concurrent_tickets': int(row[3]),
                    'running_tickets': int(row[4])
                })

            result = {'timeseries': data}
            await self._cache_result(cache_key, result, ttl=self.cache_ttl // 4)  # 15 min TTL

            self.logger.debug(
                "resource_utilization_queried",
                datapoints=len(data),
                window_days=window_days
            )

            return result

        except Exception as e:
            self.logger.error("resource_utilization_query_failed", error=str(e))
            return {'timeseries': []}

    async def query_ticket_metrics_for_training(
        self,
        window_days: int = 540,
        limit: int = 100000
    ) -> List[Dict[str, Any]]:
        """
        Query métricas de tickets para treinamento de modelos ML.

        Args:
            window_days: Janela de dados em dias (default: 18 meses)
            limit: Limite de registros

        Returns:
            Lista de dicts com features e target
        """
        query = """
        SELECT
            ticket_id,
            task_type,
            risk_band,
            toHour(timestamp) as hour_of_day,
            toDayOfWeek(timestamp) as day_of_week,
            actual_duration_ms,
            estimated_duration_ms,
            status,
            retry_count,
            resource_cpu,
            resource_memory,
            capabilities_count,
            parameters_size,
            sla_timeout_ms,
            queue_wait_ms
        FROM execution_logs
        WHERE timestamp >= now() - INTERVAL %(window_days)s DAY
          AND actual_duration_ms > 0
          AND status IN ('COMPLETED', 'FAILED')
        ORDER BY timestamp DESC
        LIMIT %(limit)s
        """

        try:
            results = await self._execute_query(query, {
                'window_days': window_days,
                'limit': limit
            })

            data = []
            for row in results:
                data.append({
                    'ticket_id': row[0],
                    'task_type': row[1],
                    'risk_band': row[2],
                    'hour_of_day': int(row[3]),
                    'day_of_week': int(row[4]),
                    'actual_duration_ms': float(row[5]),
                    'estimated_duration_ms': float(row[6] or 60000.0),
                    'status': row[7],
                    'retry_count': int(row[8] or 0),
                    'resource_cpu': float(row[9] or 0.0),
                    'resource_memory': float(row[10] or 0.0),
                    'capabilities_count': int(row[11] or 1),
                    'parameters_size': int(row[12] or 0),
                    'sla_timeout_ms': float(row[13] or 300000.0),
                    'queue_wait_ms': float(row[14] or 0.0)
                })

            self.logger.info(
                "training_data_queried_from_clickhouse",
                records=len(data),
                window_days=window_days
            )

            return data

        except Exception as e:
            self.logger.error("training_data_query_failed", error=str(e))
            return []

    async def query_duration_percentiles(
        self,
        task_type: str,
        risk_band: str,
        window_days: int = 30
    ) -> Dict[str, float]:
        """
        Query percentis de duração para um task_type/risk_band específico.

        Args:
            task_type: Tipo de tarefa
            risk_band: Banda de risco
            window_days: Janela de dados em dias

        Returns:
            Dict com percentis (p50, p75, p90, p95, p99)
        """
        cache_key = f"ch:percentiles:{task_type}:{risk_band}:{window_days}"
        cached = await self._get_cached_result(cache_key)
        if cached:
            return cached

        query = """
        SELECT
            quantile(0.50)(actual_duration_ms) as p50,
            quantile(0.75)(actual_duration_ms) as p75,
            quantile(0.90)(actual_duration_ms) as p90,
            quantile(0.95)(actual_duration_ms) as p95,
            quantile(0.99)(actual_duration_ms) as p99,
            count(*) as sample_count
        FROM execution_logs
        WHERE timestamp >= now() - INTERVAL %(window_days)s DAY
          AND task_type = %(task_type)s
          AND risk_band = %(risk_band)s
          AND actual_duration_ms > 0
        """

        try:
            results = await self._execute_query(query, {
                'window_days': window_days,
                'task_type': task_type,
                'risk_band': risk_band
            })

            if results and results[0][5] > 0:
                row = results[0]
                percentiles = {
                    'p50': float(row[0] or 60000.0),
                    'p75': float(row[1] or 90000.0),
                    'p90': float(row[2] or 120000.0),
                    'p95': float(row[3] or 150000.0),
                    'p99': float(row[4] or 200000.0),
                    'sample_count': int(row[5])
                }
            else:
                # Defaults se não houver dados
                percentiles = {
                    'p50': 60000.0,
                    'p75': 90000.0,
                    'p90': 120000.0,
                    'p95': 150000.0,
                    'p99': 200000.0,
                    'sample_count': 0
                }

            await self._cache_result(cache_key, percentiles, ttl=self.cache_ttl)

            return percentiles

        except Exception as e:
            self.logger.error(
                "percentiles_query_failed",
                task_type=task_type,
                risk_band=risk_band,
                error=str(e)
            )
            return {
                'p50': 60000.0,
                'p75': 90000.0,
                'p90': 120000.0,
                'p95': 150000.0,
                'p99': 200000.0,
                'sample_count': 0
            }

    async def _execute_query(self, query: str, params: Optional[Dict] = None) -> List:
        """
        Executa query ClickHouse de forma assíncrona.

        Args:
            query: SQL query
            params: Parâmetros parametrizados

        Returns:
            Lista de tuplas com resultados
        """
        if not self.client:
            await self.initialize()

        if not self.client:
            raise RuntimeError("ClickHouse client não inicializado")

        # Executar em thread pool (driver é síncrono)
        loop = asyncio.get_event_loop()

        try:
            results = await loop.run_in_executor(
                None,
                lambda: self.client.execute(query, params or {})
            )

            return results

        except Exception as e:
            self.logger.error("clickhouse_query_failed", error=str(e))
            raise

    async def _get_cached_result(self, cache_key: str) -> Optional[Any]:
        """Recupera resultado do cache Redis."""
        if not self.redis:
            return None

        try:
            cached = await self.redis.get(cache_key)
            if cached:
                self.logger.debug("clickhouse_cache_hit", key=cache_key)
                return json.loads(cached)
        except Exception as e:
            self.logger.warning("clickhouse_cache_read_failed", error=str(e))

        return None

    async def _cache_result(self, cache_key: str, data: Any, ttl: int) -> None:
        """Armazena resultado no cache Redis."""
        if not self.redis:
            return

        try:
            await self.redis.setex(cache_key, ttl, json.dumps(data, default=str))
            self.logger.debug("clickhouse_cache_stored", key=cache_key, ttl=ttl)
        except Exception as e:
            self.logger.warning("clickhouse_cache_write_failed", error=str(e))

    async def health_check(self) -> bool:
        """Verifica saúde da conexão ClickHouse."""
        try:
            await self._execute_query("SELECT 1")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Fecha conexão com ClickHouse."""
        if self.client:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.client.disconnect)
                self.logger.info("clickhouse_disconnected")
            except Exception as e:
                self.logger.error("clickhouse_disconnect_failed", error=str(e))

            self.client = None
            self._initialized = False
