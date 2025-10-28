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

    async def close(self):
        """Close ClickHouse connection"""
        if self.client:
            self.client.close()
            logger.info("ClickHouse client closed")
