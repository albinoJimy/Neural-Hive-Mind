"""
ClickHouse health checks for Neural Hive-Mind.

Validates ClickHouse schema integrity and connectivity for ML and analytics workloads.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from ..health import HealthCheck, HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


# Expected tables in the neural_hive database (from infrastructure/clickhouse/schema.sql)
DEFAULT_EXPECTED_TABLES = [
    'execution_logs',
    'telemetry_metrics',
    'worker_utilization',
    'queue_snapshots',
    'ml_model_performance',
    'scheduling_decisions',
]

# Expected materialized views
DEFAULT_EXPECTED_VIEWS = [
    'hourly_ticket_volume',
    'daily_worker_stats',
]


class ClickHouseSchemaHealthCheck(HealthCheck):
    """
    Health check for ClickHouse schema validation.

    Verifies that all expected tables and views exist in the ClickHouse database.
    """

    def __init__(
        self,
        clickhouse_client: Any,
        expected_tables: Optional[List[str]] = None,
        expected_views: Optional[List[str]] = None,
        database: str = 'neural_hive',
        name: str = 'clickhouse_schema',
        timeout_seconds: float = 10.0,
    ):
        """
        Initialize ClickHouse schema health check.

        Args:
            clickhouse_client: ClickHouse client instance (clickhouse-driver or aioch)
            expected_tables: List of expected table names
            expected_views: List of expected materialized view names
            database: Database name to check
            name: Name of this health check
            timeout_seconds: Timeout for health check operations
        """
        super().__init__(name=name, timeout_seconds=timeout_seconds)
        self.client = clickhouse_client
        self.expected_tables = expected_tables or DEFAULT_EXPECTED_TABLES
        self.expected_views = expected_views or DEFAULT_EXPECTED_VIEWS
        self.database = database

    async def check(self) -> HealthCheckResult:
        """
        Execute health check for ClickHouse schema.

        Verifies:
        1. Connection to ClickHouse is working
        2. Database exists
        3. All expected tables exist
        4. All expected materialized views exist

        Returns:
            HealthCheckResult with schema validation details
        """
        start_time = time.time()

        try:
            # Test connection
            connection_ok = await self._check_connection()
            if not connection_ok:
                return self._create_result(
                    HealthStatus.UNHEALTHY,
                    'Cannot connect to ClickHouse',
                    start_time=start_time
                )

            # Check database exists
            database_exists = await self._check_database_exists()
            if not database_exists:
                return self._create_result(
                    HealthStatus.UNHEALTHY,
                    f"Database '{self.database}' does not exist",
                    details={'database': self.database, 'exists': False},
                    start_time=start_time
                )

            # Get existing tables
            existing_tables = await self._get_existing_tables()
            existing_views = await self._get_existing_views()

            # Check for missing tables
            missing_tables = [t for t in self.expected_tables if t not in existing_tables]
            missing_views = [v for v in self.expected_views if v not in existing_views]

            details = {
                'database': self.database,
                'expected_tables': len(self.expected_tables),
                'found_tables': len(existing_tables),
                'missing_tables': missing_tables,
                'expected_views': len(self.expected_views),
                'found_views': len(existing_views),
                'missing_views': missing_views,
            }

            if missing_tables or missing_views:
                # Determine severity based on what's missing
                if len(missing_tables) == len(self.expected_tables):
                    # All tables missing - likely schema not initialized
                    return self._create_result(
                        HealthStatus.UNHEALTHY,
                        f"Schema not initialized: all {len(self.expected_tables)} tables missing",
                        details=details,
                        start_time=start_time
                    )
                elif len(missing_tables) > 0:
                    # Some tables missing - degraded
                    return self._create_result(
                        HealthStatus.DEGRADED,
                        f"Schema incomplete: {len(missing_tables)} tables and {len(missing_views)} views missing",
                        details=details,
                        start_time=start_time
                    )
                else:
                    # Only views missing - still degraded but less critical
                    return self._create_result(
                        HealthStatus.DEGRADED,
                        f"Materialized views missing: {missing_views}",
                        details=details,
                        start_time=start_time
                    )

            return self._create_result(
                HealthStatus.HEALTHY,
                f"Schema complete: {len(existing_tables)} tables, {len(existing_views)} views",
                details=details,
                start_time=start_time
            )

        except asyncio.TimeoutError:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Timeout checking ClickHouse schema ({self.timeout_seconds}s)",
                start_time=start_time
            )
        except Exception as e:
            logger.error(f"Error checking ClickHouse schema: {e}")
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Error checking schema: {str(e)}",
                start_time=start_time
            )

    async def _check_connection(self) -> bool:
        """Check if ClickHouse connection is working."""
        try:
            # Try different client interfaces
            if hasattr(self.client, 'execute'):
                # clickhouse-driver sync client
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, self.client.execute, 'SELECT 1'
                    ),
                    timeout=self.timeout_seconds
                )
                return result is not None
            elif hasattr(self.client, 'fetch'):
                # aioch async client
                result = await asyncio.wait_for(
                    self.client.fetch('SELECT 1'),
                    timeout=self.timeout_seconds
                )
                return result is not None
            elif hasattr(self.client, 'ping'):
                # Generic ping method
                return await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, self.client.ping
                    ),
                    timeout=self.timeout_seconds
                )
            else:
                logger.warning("Unknown ClickHouse client type, assuming connected")
                return True
        except Exception as e:
            logger.error(f"ClickHouse connection check failed: {e}")
            return False

    async def _check_database_exists(self) -> bool:
        """Check if the target database exists."""
        try:
            query = f"SELECT name FROM system.databases WHERE name = '{self.database}'"
            result = await self._execute_query(query)
            return len(result) > 0
        except Exception as e:
            logger.error(f"Error checking database existence: {e}")
            return False

    async def _get_existing_tables(self) -> List[str]:
        """Get list of existing tables in the database."""
        try:
            query = f"""
                SELECT name FROM system.tables
                WHERE database = '{self.database}'
                AND engine NOT LIKE '%View%'
            """
            result = await self._execute_query(query)
            return [row[0] for row in result] if result else []
        except Exception as e:
            logger.error(f"Error getting existing tables: {e}")
            return []

    async def _get_existing_views(self) -> List[str]:
        """Get list of existing materialized views in the database."""
        try:
            query = f"""
                SELECT name FROM system.tables
                WHERE database = '{self.database}'
                AND engine LIKE '%View%'
            """
            result = await self._execute_query(query)
            return [row[0] for row in result] if result else []
        except Exception as e:
            logger.error(f"Error getting existing views: {e}")
            return []

    async def _execute_query(self, query: str) -> List[tuple]:
        """Execute a query and return results."""
        if hasattr(self.client, 'execute'):
            # clickhouse-driver sync client
            return await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self.client.execute, query
                ),
                timeout=self.timeout_seconds
            )
        elif hasattr(self.client, 'fetch'):
            # aioch async client
            return await asyncio.wait_for(
                self.client.fetch(query),
                timeout=self.timeout_seconds
            )
        else:
            raise RuntimeError("Unknown ClickHouse client type")


class ClickHouseConnectionHealthCheck(HealthCheck):
    """
    Simple health check for ClickHouse connectivity.

    Useful for basic liveness checks without schema validation.
    """

    def __init__(
        self,
        clickhouse_client: Any,
        name: str = 'clickhouse_connection',
        timeout_seconds: float = 5.0,
    ):
        """
        Initialize ClickHouse connection health check.

        Args:
            clickhouse_client: ClickHouse client instance
            name: Name of this health check
            timeout_seconds: Timeout for health check operations
        """
        super().__init__(name=name, timeout_seconds=timeout_seconds)
        self.client = clickhouse_client

    async def check(self) -> HealthCheckResult:
        """Check ClickHouse connectivity."""
        start_time = time.time()

        try:
            if hasattr(self.client, 'execute'):
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, self.client.execute, 'SELECT 1'
                    ),
                    timeout=self.timeout_seconds
                )
                if result:
                    return self._create_result(
                        HealthStatus.HEALTHY,
                        'ClickHouse connection OK',
                        start_time=start_time
                    )

            return self._create_result(
                HealthStatus.UNHEALTHY,
                'ClickHouse connection failed',
                start_time=start_time
            )

        except asyncio.TimeoutError:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"ClickHouse connection timeout ({self.timeout_seconds}s)",
                start_time=start_time
            )
        except Exception as e:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"ClickHouse connection error: {str(e)}",
                start_time=start_time
            )
