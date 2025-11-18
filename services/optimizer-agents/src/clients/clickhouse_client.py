"""
Cliente ClickHouse para queries de dados históricos.

Integração com ClickHouse para análise de telemetria e execution logs
de 18 meses para treinamento de modelos ML.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from clickhouse_driver import Client as SyncClickHouseClient

logger = logging.getLogger(__name__)


class ClickHouseClient:
    """
    Cliente assíncrono para ClickHouse.

    Fornece queries otimizadas para:
    - Séries temporais de execução de tickets
    - Utilização de recursos (CPU, memória)
    - Compliance de SLA
    - Eventos de bottleneck
    """

    def __init__(self, redis_client, config: Dict):
        """
        Args:
            redis_client: Cliente Redis para caching
            config: Configuração (host, port, user, password, database)
        """
        self.redis = redis_client
        self.config = config

        # Configurações de conexão
        self.host = config.get('clickhouse_host', 'clickhouse.clickhouse.svc.cluster.local')
        self.port = config.get('clickhouse_port', 9000)
        self.user = config.get('clickhouse_user', 'default')
        self.password = config.get('clickhouse_password', '')
        self.database = config.get('clickhouse_database', 'neural_hive')

        # Cliente síncrono (wrappado em async)
        self.client: Optional[SyncClickHouseClient] = None

        # Cache TTL
        self.cache_ttl = 300  # 5 minutos

        # Query timeout
        self.query_timeout = 30  # 30 segundos

        self._initialized = False

    async def initialize(self) -> None:
        """Estabelece conexão com ClickHouse com retry logic."""
        if self._initialized:
            return

        logger.info(f"Conectando ao ClickHouse: {self.host}:{self.port}")

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

                logger.info("ClickHouse conectado com sucesso")
                self._initialized = True
                return

            except Exception as e:
                logger.error(f"Falha na conexão (tentativa {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Backoff exponencial
                else:
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

    async def query_execution_timeseries(
        self,
        start_timestamp: datetime,
        end_timestamp: datetime,
        aggregation_interval: str = '1h'
    ) -> List[Dict]:
        """
        Query série temporal de execuções de tickets.

        Args:
            start_timestamp: Início da janela
            end_timestamp: Fim da janela
            aggregation_interval: Intervalo de agregação ('1m', '1h', '1d')

        Returns:
            Lista de dicts com:
                - timestamp: DateTime
                - ticket_count: Total de tickets
                - avg_duration_ms: Duração média
                - task_type: Tipo de tarefa (se agrupado)
                - risk_band: Banda de risco (se agrupado)
        """
        # Verificar cache
        cache_key = f"exec_ts:{start_timestamp.isoformat()}:{end_timestamp.isoformat()}:{aggregation_interval}"
        cached = await self._get_cached_result(cache_key)
        if cached:
            return cached

        # Mapear intervalo para função ClickHouse
        interval_map = {
            '1m': 'toStartOfMinute',
            '1h': 'toStartOfHour',
            '1d': 'toStartOfDay',
        }
        interval_func = interval_map.get(aggregation_interval, 'toStartOfHour')

        query = f"""
        SELECT
            {interval_func}(timestamp) as timestamp,
            count(*) as ticket_count,
            avg(actual_duration_ms) as avg_duration_ms,
            avg(resource_cpu) as resource_cpu_avg,
            avg(resource_memory) as resource_memory_avg,
            task_type,
            risk_band
        FROM execution_logs
        WHERE timestamp >= %(start_time)s AND timestamp <= %(end_time)s
        GROUP BY timestamp, task_type, risk_band
        ORDER BY timestamp
        """

        params = {
            'start_time': start_timestamp,
            'end_time': end_timestamp,
        }

        try:
            results = await self._execute_query(query, params)

            # Converter para lista de dicts
            data = [
                {
                    'timestamp': row[0],
                    'ticket_count': row[1],
                    'avg_duration_ms': row[2],
                    'resource_cpu_avg': row[3],
                    'resource_memory_avg': row[4],
                    'task_type': row[5],
                    'risk_band': row[6],
                }
                for row in results
            ]

            # Cachear
            await self._cache_result(cache_key, data, ttl=self.cache_ttl)

            logger.info(f"Query execution_timeseries retornou {len(data)} registros")
            return data

        except Exception as e:
            logger.error(f"Erro em query_execution_timeseries: {e}")
            return []

    async def query_resource_utilization(
        self,
        start_timestamp: datetime,
        end_timestamp: datetime
    ) -> List[Dict]:
        """
        Query utilização de recursos (CPU, memória, workers ativos).

        Args:
            start_timestamp: Início da janela
            end_timestamp: Fim da janela

        Returns:
            Lista de dicts com métricas de utilização
        """
        cache_key = f"resource_util:{start_timestamp.isoformat()}:{end_timestamp.isoformat()}"
        cached = await self._get_cached_result(cache_key)
        if cached:
            return cached

        query = """
        SELECT
            toStartOfHour(timestamp) as timestamp,
            avg(metric_value) as avg_value,
            max(metric_value) as max_value,
            metric_name,
            labels['service'] as service
        FROM telemetry_metrics
        WHERE timestamp >= %(start_time)s AND timestamp <= %(end_time)s
          AND metric_name IN ('worker_cpu_usage', 'worker_memory_usage', 'active_workers')
        GROUP BY timestamp, metric_name, service
        ORDER BY timestamp
        """

        params = {
            'start_time': start_timestamp,
            'end_time': end_timestamp,
        }

        try:
            results = await self._execute_query(query, params)

            data = [
                {
                    'timestamp': row[0],
                    'avg_value': row[1],
                    'max_value': row[2],
                    'metric_name': row[3],
                    'service': row[4],
                }
                for row in results
            ]

            await self._cache_result(cache_key, data, ttl=self.cache_ttl)

            logger.info(f"Query resource_utilization retornou {len(data)} registros")
            return data

        except Exception as e:
            logger.error(f"Erro em query_resource_utilization: {e}")
            return []

    async def query_sla_compliance(
        self,
        start_timestamp: datetime,
        end_timestamp: datetime
    ) -> List[Dict]:
        """
        Query compliance de SLA por serviço.

        Args:
            start_timestamp: Início da janela
            end_timestamp: Fim da janela

        Returns:
            Lista de dicts com percentagens de compliance
        """
        cache_key = f"sla_compliance:{start_timestamp.isoformat()}:{end_timestamp.isoformat()}"
        cached = await self._get_cached_result(cache_key)
        if cached:
            return cached

        query = """
        SELECT
            toStartOfDay(timestamp) as date,
            service,
            countIf(status = 'SUCCESS' AND actual_duration_ms <= sla_threshold_ms) * 100.0 / count(*) as compliance_percentage,
            count(*) as total_tickets
        FROM execution_logs
        WHERE timestamp >= %(start_time)s AND timestamp <= %(end_time)s
        GROUP BY date, service
        ORDER BY date
        """

        params = {
            'start_time': start_timestamp,
            'end_time': end_timestamp,
        }

        try:
            results = await self._execute_query(query, params)

            data = [
                {
                    'date': row[0],
                    'service': row[1],
                    'compliance_percentage': row[2],
                    'total_tickets': row[3],
                }
                for row in results
            ]

            await self._cache_result(cache_key, data, ttl=self.cache_ttl)

            logger.info(f"Query sla_compliance retornou {len(data)} registros")
            return data

        except Exception as e:
            logger.error(f"Erro em query_sla_compliance: {e}")
            return []

    async def query_bottleneck_events(
        self,
        start_timestamp: datetime,
        end_timestamp: datetime
    ) -> List[Dict]:
        """
        Query eventos de bottleneck (saturação de workers, filas longas).

        Args:
            start_timestamp: Início da janela
            end_timestamp: Fim da janela

        Returns:
            Lista de eventos de bottleneck
        """
        cache_key = f"bottlenecks:{start_timestamp.isoformat()}:{end_timestamp.isoformat()}"
        cached = await self._get_cached_result(cache_key)
        if cached:
            return cached

        # Detectar bottlenecks quando queue_depth > 100 ou worker_utilization > 90%
        query = """
        SELECT
            timestamp,
            metric_name,
            metric_value,
            labels['service'] as service
        FROM telemetry_metrics
        WHERE timestamp >= %(start_time)s AND timestamp <= %(end_time)s
          AND (
              (metric_name = 'queue_depth' AND metric_value > 100)
              OR
              (metric_name = 'worker_utilization' AND metric_value > 0.9)
          )
        ORDER BY timestamp
        """

        params = {
            'start_time': start_timestamp,
            'end_time': end_timestamp,
        }

        try:
            results = await self._execute_query(query, params)

            data = [
                {
                    'timestamp': row[0],
                    'metric_name': row[1],
                    'metric_value': row[2],
                    'service': row[3],
                    'bottleneck_type': 'queue_saturation' if row[1] == 'queue_depth' else 'worker_saturation',
                }
                for row in results
            ]

            await self._cache_result(cache_key, data, ttl=self.cache_ttl)

            logger.info(f"Query bottleneck_events retornou {len(data)} eventos")
            return data

        except Exception as e:
            logger.error(f"Erro em query_bottleneck_events: {e}")
            return []

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
            logger.error(f"Erro ao executar query: {e}")
            logger.debug(f"Query: {query}")
            raise

    async def _get_cached_result(self, cache_key: str) -> Optional[List[Dict]]:
        """Recupera resultado do cache Redis."""
        try:
            import json
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(f"Cache hit: {cache_key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Erro ao ler cache: {e}")
        return None

    async def _cache_result(self, cache_key: str, data: List[Dict], ttl: int) -> None:
        """Armazena resultado no cache Redis."""
        try:
            import json
            # Converter datetimes para strings
            serializable_data = []
            for item in data:
                serializable = {}
                for key, value in item.items():
                    if isinstance(value, datetime):
                        serializable[key] = value.isoformat()
                    else:
                        serializable[key] = value
                serializable_data.append(serializable)

            await self.redis.setex(cache_key, ttl, json.dumps(serializable_data))
            logger.debug(f"Cache armazenado: {cache_key}")

        except Exception as e:
            logger.warning(f"Erro ao cachear: {e}")

    async def close(self) -> None:
        """Fecha conexão com ClickHouse."""
        if self.client:
            try:
                # Driver não tem close assíncrono, só desconectar
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.client.disconnect)
                logger.info("ClickHouse desconectado")
            except Exception as e:
                logger.error(f"Erro ao desconectar ClickHouse: {e}")

            self.client = None
            self._initialized = False
