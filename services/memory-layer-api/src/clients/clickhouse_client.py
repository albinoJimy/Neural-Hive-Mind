"""
ClickHouse Client for historical analytics
"""
import structlog
import clickhouse_connect
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class ClickHouseClient:
    """ClickHouse client for cold storage (18 months retention)"""

    def __init__(self, settings):
        self.settings = settings
        self.client = None
        self.database = settings.clickhouse_database

    async def initialize(self):
        """Initialize ClickHouse connection and create schemas"""
        try:
            self.client = clickhouse_connect.get_client(
                host=self.settings.clickhouse_host,
                port=self.settings.clickhouse_port,
                username=self.settings.clickhouse_user,
                password=self.settings.clickhouse_password,
                database=self.database
            )

            logger.info("ClickHouse client connected", host=self.settings.clickhouse_host)

            # Create schemas
            await self._create_schemas()

            logger.info("ClickHouse schemas initialized")
        except Exception as e:
            logger.error("Failed to initialize ClickHouse", error=str(e))
            raise

    async def _create_schemas(self):
        """Create database and tables if they don't exist"""
        # Create database
        self.client.command(f"CREATE DATABASE IF NOT EXISTS {self.database}")

        # cognitive_plans_history table
        self.client.command(f"""
            CREATE TABLE IF NOT EXISTS {self.database}.cognitive_plans_history (
                plan_id String,
                intent_id String,
                domain String,
                created_at DateTime,
                risk_score Float32,
                complexity_score Float32,
                plan_data String,
                metadata String,
                partition_month Date DEFAULT toDate(created_at)
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(created_at)
            ORDER BY (created_at, plan_id)
            TTL created_at + INTERVAL {self.settings.clickhouse_retention_months} MONTH
            SETTINGS index_granularity = 8192
        """)

        # consensus_decisions_history table
        self.client.command(f"""
            CREATE TABLE IF NOT EXISTS {self.database}.consensus_decisions_history (
                decision_id String,
                plan_id String,
                aggregated_confidence Float32,
                consensus_type String,
                created_at DateTime,
                decision_data String,
                metadata String,
                partition_month Date DEFAULT toDate(created_at)
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(created_at)
            ORDER BY (created_at, decision_id)
            TTL created_at + INTERVAL {self.settings.clickhouse_retention_months} MONTH
            SETTINGS index_granularity = 8192
        """)

        # specialist_opinions_history table
        self.client.command(f"""
            CREATE TABLE IF NOT EXISTS {self.database}.specialist_opinions_history (
                opinion_id String,
                specialist_type String,
                plan_id String,
                confidence_score Float32,
                created_at DateTime,
                opinion_data String,
                metadata String,
                partition_month Date DEFAULT toDate(created_at)
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(created_at)
            ORDER BY (created_at, opinion_id)
            TTL created_at + INTERVAL {self.settings.clickhouse_retention_months} MONTH
            SETTINGS index_granularity = 8192
        """)

        # telemetry_events table
        self.client.command(f"""
            CREATE TABLE IF NOT EXISTS {self.database}.telemetry_events (
                event_id String,
                event_type String,
                timestamp DateTime,
                service_name String,
                trace_id String,
                metadata String,
                partition_month Date DEFAULT toDate(timestamp)
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (timestamp, event_id)
            TTL timestamp + INTERVAL 12 MONTH
            SETTINGS index_granularity = 8192
        """)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_cognitive_plan(self, plan: Dict) -> bool:
        """Insert cognitive plan into history"""
        try:
            self.client.insert(
                f"{self.database}.cognitive_plans_history",
                [[
                    plan.get('plan_id'),
                    plan.get('intent_id'),
                    plan.get('domain'),
                    plan.get('created_at', datetime.utcnow()),
                    plan.get('risk_score', 0.0),
                    plan.get('complexity_score', 0.0),
                    str(plan.get('plan_data', {})),
                    str(plan.get('metadata', {}))
                ]],
                column_names=['plan_id', 'intent_id', 'domain', 'created_at',
                             'risk_score', 'complexity_score', 'plan_data', 'metadata']
            )
            logger.info("Cognitive plan inserted", plan_id=plan.get('plan_id'))
            return True
        except Exception as e:
            logger.error("Failed to insert cognitive plan", error=str(e), plan_id=plan.get('plan_id'))
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_consensus_decision(self, decision: Dict) -> bool:
        """Insert consensus decision into history"""
        try:
            self.client.insert(
                f"{self.database}.consensus_decisions_history",
                [[
                    decision.get('decision_id'),
                    decision.get('plan_id'),
                    decision.get('aggregated_confidence', 0.0),
                    decision.get('consensus_type'),
                    decision.get('created_at', datetime.utcnow()),
                    str(decision.get('decision_data', {})),
                    str(decision.get('metadata', {}))
                ]],
                column_names=['decision_id', 'plan_id', 'aggregated_confidence',
                             'consensus_type', 'created_at', 'decision_data', 'metadata']
            )
            logger.info("Consensus decision inserted", decision_id=decision.get('decision_id'))
            return True
        except Exception as e:
            logger.error("Failed to insert decision", error=str(e), decision_id=decision.get('decision_id'))
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_batch(self, table: str, rows: List[List[Any]], column_names: List[str]) -> bool:
        """
        Insere batch de linhas em uma tabela.

        Args:
            table: Nome da tabela (sem prefixo do database)
            rows: Lista de linhas (cada linha é uma lista de valores)
            column_names: Nomes das colunas correspondentes

        Returns:
            True se inserido com sucesso
        """
        if not rows:
            return True

        try:
            self.client.insert(
                f"{self.database}.{table}",
                rows,
                column_names=column_names
            )
            logger.info("Batch inserido", table=table, row_count=len(rows))
            return True
        except Exception as e:
            logger.error("Falha ao inserir batch", error=str(e), table=table, row_count=len(rows))
            raise

    async def query_historical_plans(
        self,
        start_date: datetime,
        end_date: datetime,
        domain: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Query historical plans with time range"""
        query = f"""
            SELECT *
            FROM {self.database}.cognitive_plans_history
            WHERE created_at BETWEEN %(start_date)s AND %(end_date)s
        """

        params = {'start_date': start_date, 'end_date': end_date}

        if domain:
            query += " AND domain = %(domain)s"
            params['domain'] = domain

        query += f" ORDER BY created_at DESC LIMIT {limit}"

        try:
            result = self.client.query(query, parameters=params)
            return result.result_rows
        except Exception as e:
            logger.error("Historical plans query failed", error=str(e))
            raise

    async def get_aggregated_metrics(
        self,
        metric_type: str,
        granularity: str = 'hour',
        start_date: datetime = None,
        end_date: datetime = None
    ) -> List[Dict]:
        """Get aggregated metrics with specified granularity"""
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=7)
        if not end_date:
            end_date = datetime.utcnow()

        interval_func = {
            'hour': 'toStartOfHour',
            'day': 'toStartOfDay',
            'week': 'toMonday',
            'month': 'toStartOfMonth'
        }.get(granularity, 'toStartOfHour')

        query = f"""
            SELECT
                {interval_func}(created_at) as time_bucket,
                count() as total_count,
                avg(risk_score) as avg_risk,
                avg(complexity_score) as avg_complexity
            FROM {self.database}.cognitive_plans_history
            WHERE created_at BETWEEN %(start_date)s AND %(end_date)s
            GROUP BY time_bucket
            ORDER BY time_bucket
        """

        try:
            result = self.client.query(query, parameters={
                'start_date': start_date,
                'end_date': end_date
            })
            return result.result_rows
        except Exception as e:
            logger.error("Aggregated metrics query failed", error=str(e))
            raise

    async def cleanup_old_data(self, retention_months: int = 18) -> int:
        """Delete data older than retention period"""
        cutoff_date = datetime.utcnow() - timedelta(days=retention_months * 30)

        try:
            # ClickHouse TTL handles automatic cleanup, but we can manually trigger
            for table in ['cognitive_plans_history', 'consensus_decisions_history',
                         'specialist_opinions_history', 'telemetry_events']:
                self.client.command(f"""
                    ALTER TABLE {self.database}.{table}
                    DELETE WHERE created_at < %(cutoff_date)s
                """, parameters={'cutoff_date': cutoff_date})

            logger.info("Old data cleanup completed", cutoff_date=cutoff_date)
            return 0  # ClickHouse doesn't return affected rows for DELETE
        except Exception as e:
            logger.error("Cleanup failed", error=str(e))
            raise

    # ========================================
    # Métodos para tabelas ML Predictive Scheduling
    # ========================================

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_execution_log(self, log: Dict) -> bool:
        """
        Insere log de execução de ticket para forecasting de carga.

        Args:
            log: Dicionário com dados do log de execução

        Returns:
            True se inserido com sucesso
        """
        try:
            self.client.insert(
                f"{self.database}.execution_logs",
                [[
                    log.get('timestamp', datetime.utcnow()),
                    log.get('ticket_id', ''),
                    log.get('task_type', ''),
                    log.get('risk_band', 'medium'),
                    log.get('actual_duration_ms', 0),
                    log.get('latency_ms', 0),
                    log.get('status', 'success'),
                    log.get('worker_id', ''),
                    log.get('service', ''),
                    log.get('sla_threshold_ms', 0),
                    log.get('resource_cpu', 0.0),
                    log.get('resource_memory', 0.0),
                    1 if log.get('sla_met', True) else 0,
                    log.get('queue_depth_at_start', 0),
                    log.get('specialist_type', ''),
                    log.get('priority', 5),
                    log.get('retry_count', 0)
                ]],
                column_names=[
                    'timestamp', 'ticket_id', 'task_type', 'risk_band',
                    'actual_duration_ms', 'latency_ms', 'status', 'worker_id',
                    'service', 'sla_threshold_ms', 'resource_cpu', 'resource_memory',
                    'sla_met', 'queue_depth_at_start', 'specialist_type', 'priority', 'retry_count'
                ]
            )
            logger.debug("Execution log inserido", ticket_id=log.get('ticket_id'))
            return True
        except Exception as e:
            logger.error("Falha ao inserir execution log", error=str(e), ticket_id=log.get('ticket_id'))
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_execution_logs_batch(self, logs: List[Dict]) -> bool:
        """
        Insere batch de logs de execução.

        Args:
            logs: Lista de dicionários com dados dos logs

        Returns:
            True se inserido com sucesso
        """
        if not logs:
            return True

        rows = []
        for log in logs:
            rows.append([
                log.get('timestamp', datetime.utcnow()),
                log.get('ticket_id', ''),
                log.get('task_type', ''),
                log.get('risk_band', 'medium'),
                log.get('actual_duration_ms', 0),
                log.get('latency_ms', 0),
                log.get('status', 'success'),
                log.get('worker_id', ''),
                log.get('service', ''),
                log.get('sla_threshold_ms', 0),
                log.get('resource_cpu', 0.0),
                log.get('resource_memory', 0.0),
                1 if log.get('sla_met', True) else 0,
                log.get('queue_depth_at_start', 0),
                log.get('specialist_type', ''),
                log.get('priority', 5),
                log.get('retry_count', 0)
            ])

        return await self.insert_batch(
            'execution_logs',
            rows,
            [
                'timestamp', 'ticket_id', 'task_type', 'risk_band',
                'actual_duration_ms', 'latency_ms', 'status', 'worker_id',
                'service', 'sla_threshold_ms', 'resource_cpu', 'resource_memory',
                'sla_met', 'queue_depth_at_start', 'specialist_type', 'priority', 'retry_count'
            ]
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_telemetry_metric(self, metric: Dict) -> bool:
        """
        Insere métrica de telemetria para análise de tendências.

        Args:
            metric: Dicionário com dados da métrica

        Returns:
            True se inserido com sucesso
        """
        import json
        try:
            labels = metric.get('labels', {})
            if isinstance(labels, str):
                labels = json.loads(labels)

            self.client.insert(
                f"{self.database}.telemetry_metrics",
                [[
                    metric.get('timestamp', datetime.utcnow()),
                    metric.get('service', ''),
                    metric.get('metric_name', ''),
                    float(metric.get('metric_value', 0.0)),
                    labels,
                    metric.get('aggregation_window_seconds', 60)
                ]],
                column_names=[
                    'timestamp', 'service', 'metric_name', 'metric_value',
                    'labels', 'aggregation_window_seconds'
                ]
            )
            logger.debug("Telemetry metric inserido", metric_name=metric.get('metric_name'))
            return True
        except Exception as e:
            logger.error("Falha ao inserir telemetry metric", error=str(e))
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_telemetry_metrics_batch(self, metrics: List[Dict]) -> bool:
        """
        Insere batch de métricas de telemetria.

        Args:
            metrics: Lista de dicionários com dados das métricas

        Returns:
            True se inserido com sucesso
        """
        import json
        if not metrics:
            return True

        rows = []
        for metric in metrics:
            labels = metric.get('labels', {})
            if isinstance(labels, str):
                labels = json.loads(labels)

            rows.append([
                metric.get('timestamp', datetime.utcnow()),
                metric.get('service', ''),
                metric.get('metric_name', ''),
                float(metric.get('metric_value', 0.0)),
                labels,
                metric.get('aggregation_window_seconds', 60)
            ])

        return await self.insert_batch(
            'telemetry_metrics',
            rows,
            ['timestamp', 'service', 'metric_name', 'metric_value', 'labels', 'aggregation_window_seconds']
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_worker_utilization(self, util: Dict) -> bool:
        """
        Insere dados de utilização de worker.

        Args:
            util: Dicionário com dados de utilização

        Returns:
            True se inserido com sucesso
        """
        try:
            self.client.insert(
                f"{self.database}.worker_utilization",
                [[
                    util.get('timestamp', datetime.utcnow()),
                    util.get('worker_id', ''),
                    util.get('active_tasks', 0),
                    float(util.get('cpu_usage', 0.0)),
                    float(util.get('memory_usage_mb', 0.0)),
                    float(util.get('network_rx_mbps', 0.0)),
                    float(util.get('network_tx_mbps', 0.0)),
                    1 if util.get('is_available', True) else 0,
                    util.get('specialist_type', '')
                ]],
                column_names=[
                    'timestamp', 'worker_id', 'active_tasks', 'cpu_usage',
                    'memory_usage_mb', 'network_rx_mbps', 'network_tx_mbps',
                    'is_available', 'specialist_type'
                ]
            )
            logger.debug("Worker utilization inserido", worker_id=util.get('worker_id'))
            return True
        except Exception as e:
            logger.error("Falha ao inserir worker utilization", error=str(e))
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_worker_utilization_batch(self, utils: List[Dict]) -> bool:
        """
        Insere batch de dados de utilização de workers.

        Args:
            utils: Lista de dicionários com dados de utilização

        Returns:
            True se inserido com sucesso
        """
        if not utils:
            return True

        rows = []
        for util in utils:
            rows.append([
                util.get('timestamp', datetime.utcnow()),
                util.get('worker_id', ''),
                util.get('active_tasks', 0),
                float(util.get('cpu_usage', 0.0)),
                float(util.get('memory_usage_mb', 0.0)),
                float(util.get('network_rx_mbps', 0.0)),
                float(util.get('network_tx_mbps', 0.0)),
                1 if util.get('is_available', True) else 0,
                util.get('specialist_type', '')
            ])

        return await self.insert_batch(
            'worker_utilization',
            rows,
            [
                'timestamp', 'worker_id', 'active_tasks', 'cpu_usage',
                'memory_usage_mb', 'network_rx_mbps', 'network_tx_mbps',
                'is_available', 'specialist_type'
            ]
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_queue_snapshot(self, snapshot: Dict) -> bool:
        """
        Insere snapshot da fila de tickets.

        Args:
            snapshot: Dicionário com dados do snapshot

        Returns:
            True se inserido com sucesso
        """
        try:
            self.client.insert(
                f"{self.database}.queue_snapshots",
                [[
                    snapshot.get('timestamp', datetime.utcnow()),
                    snapshot.get('queue_depth', 0),
                    snapshot.get('avg_wait_time_ms', 0),
                    snapshot.get('tickets_by_priority', {}),
                    snapshot.get('tickets_by_task_type', {}),
                    snapshot.get('tickets_by_risk_band', {}),
                    snapshot.get('active_workers', 0),
                    float(snapshot.get('available_capacity', 0.0))
                ]],
                column_names=[
                    'timestamp', 'queue_depth', 'avg_wait_time_ms',
                    'tickets_by_priority', 'tickets_by_task_type', 'tickets_by_risk_band',
                    'active_workers', 'available_capacity'
                ]
            )
            logger.debug("Queue snapshot inserido")
            return True
        except Exception as e:
            logger.error("Falha ao inserir queue snapshot", error=str(e))
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_ml_model_performance(self, perf: Dict) -> bool:
        """
        Insere dados de performance de modelo ML.

        Args:
            perf: Dicionário com dados de performance

        Returns:
            True se inserido com sucesso
        """
        try:
            self.client.insert(
                f"{self.database}.ml_model_performance",
                [[
                    perf.get('timestamp', datetime.utcnow()),
                    perf.get('model_name', ''),
                    perf.get('model_version', ''),
                    perf.get('metric_name', ''),
                    float(perf.get('metric_value', 0.0)),
                    perf.get('evaluation_samples', 0),
                    perf.get('horizon_minutes', 0),
                    perf.get('task_type', ''),
                    perf.get('risk_band', '')
                ]],
                column_names=[
                    'timestamp', 'model_name', 'model_version', 'metric_name',
                    'metric_value', 'evaluation_samples', 'horizon_minutes',
                    'task_type', 'risk_band'
                ]
            )
            logger.debug("ML model performance inserido", model_name=perf.get('model_name'))
            return True
        except Exception as e:
            logger.error("Falha ao inserir ml model performance", error=str(e))
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def insert_scheduling_decision(self, decision: Dict) -> bool:
        """
        Insere decisão de agendamento para análise de política RL.

        Args:
            decision: Dicionário com dados da decisão

        Returns:
            True se inserido com sucesso
        """
        try:
            self.client.insert(
                f"{self.database}.scheduling_decisions",
                [[
                    decision.get('timestamp', datetime.utcnow()),
                    decision.get('decision_id', ''),
                    decision.get('state_hash', ''),
                    decision.get('action', ''),
                    float(decision.get('confidence', 0.0)),
                    float(decision.get('reward', 0.0)),
                    float(decision.get('sla_compliance_before', 0.0)),
                    float(decision.get('sla_compliance_after', 0.0)),
                    float(decision.get('throughput_before', 0.0)),
                    float(decision.get('throughput_after', 0.0)),
                    1 if decision.get('was_applied', False) else 0,
                    decision.get('rejection_reason', ''),
                    decision.get('source', 'ml_model')
                ]],
                column_names=[
                    'timestamp', 'decision_id', 'state_hash', 'action',
                    'confidence', 'reward', 'sla_compliance_before', 'sla_compliance_after',
                    'throughput_before', 'throughput_after', 'was_applied',
                    'rejection_reason', 'source'
                ]
            )
            logger.debug("Scheduling decision inserido", decision_id=decision.get('decision_id'))
            return True
        except Exception as e:
            logger.error("Falha ao inserir scheduling decision", error=str(e))
            raise

    async def close(self):
        """Close ClickHouse connection"""
        if self.client:
            self.client.close()
            logger.info("ClickHouse client closed")
