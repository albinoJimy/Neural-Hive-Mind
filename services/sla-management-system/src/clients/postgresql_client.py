"""
Cliente para PostgreSQL usando asyncpg.
"""

from typing import Optional, List, Dict, Any
import asyncpg
import structlog

from ..config.settings import PostgreSQLSettings
from ..models.slo_definition import SLODefinition
from ..models.error_budget import ErrorBudget
from ..models.freeze_policy import FreezePolicy, FreezeEvent
from ..observability.metrics import sla_metrics


class PostgreSQLClient:
    """Cliente para PostgreSQL."""

    def __init__(self, settings: PostgreSQLSettings):
        self.settings = settings
        self.pool: Optional[asyncpg.Pool] = None
        self.logger = structlog.get_logger(__name__)

    async def connect(self) -> None:
        """Cria connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                host=self.settings.host,
                port=self.settings.port,
                database=self.settings.database,
                user=self.settings.user,
                password=self.settings.password,
                min_size=self.settings.pool_min_size,
                max_size=self.settings.pool_max_size,
                timeout=self.settings.connection_timeout
            )
            self.logger.info(
                "postgresql_connected",
                host=self.settings.host,
                database=self.settings.database
            )
            await self._create_tables()
        except Exception as e:
            self.logger.error("postgresql_connection_failed", error=str(e))
            sla_metrics.record_postgresql_error()
            raise

    async def disconnect(self) -> None:
        """Fecha pool gracefully."""
        if self.pool:
            await self.pool.close()
            self.logger.info("postgresql_disconnected")

    def _handle_connection_error(self, error: Exception) -> None:
        """Trata erros de conexão e incrementa métrica."""
        if isinstance(error, (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, ConnectionError)):
            sla_metrics.record_postgresql_error()
            self.logger.error("postgresql_connection_error", error=str(error))
        raise error

    def _parse_slo_row(self, row) -> Dict[str, Any]:
        """Parse row from slo_definitions, converting JSON fields."""
        import json
        data = dict(row)

        # Parse sli_query from JSON string to dict
        if 'sli_query' in data and isinstance(data['sli_query'], str):
            data['sli_query'] = json.loads(data['sli_query'])

        # Parse metadata if it's a JSON string
        if 'metadata' in data and isinstance(data['metadata'], str):
            data['metadata'] = json.loads(data['metadata'])

        return data

    async def _create_tables(self) -> None:
        """Cria tabelas se não existirem."""
        async with self.pool.acquire() as conn:
            # Tabela slo_definitions
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS slo_definitions (
                    slo_id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    slo_type VARCHAR(50) NOT NULL,
                    service_name VARCHAR(255) NOT NULL,
                    component VARCHAR(255),
                    layer VARCHAR(50),
                    target FLOAT NOT NULL,
                    window_days INTEGER NOT NULL,
                    sli_query JSONB NOT NULL,
                    error_budget_percent FLOAT,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    metadata JSONB
                )
            ''')

            # Tabela error_budgets
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS error_budgets (
                    budget_id VARCHAR(255) PRIMARY KEY,
                    slo_id VARCHAR(255) NOT NULL REFERENCES slo_definitions(slo_id),
                    service_name VARCHAR(255) NOT NULL,
                    calculated_at TIMESTAMP NOT NULL,
                    window_start TIMESTAMP NOT NULL,
                    window_end TIMESTAMP NOT NULL,
                    sli_value FLOAT NOT NULL,
                    slo_target FLOAT NOT NULL,
                    error_budget_total FLOAT NOT NULL,
                    error_budget_consumed FLOAT NOT NULL,
                    error_budget_remaining FLOAT NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    burn_rates JSONB,
                    violations_count INTEGER DEFAULT 0,
                    last_violation_at TIMESTAMP,
                    metadata JSONB
                )
            ''')

            # Tabela freeze_policies
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS freeze_policies (
                    policy_id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    scope VARCHAR(50) NOT NULL,
                    target VARCHAR(255) NOT NULL,
                    actions TEXT[],
                    trigger_threshold_percent FLOAT NOT NULL,
                    auto_unfreeze BOOLEAN DEFAULT TRUE,
                    unfreeze_threshold_percent FLOAT,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL,
                    metadata JSONB
                )
            ''')

            # Tabela freeze_events
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS freeze_events (
                    event_id VARCHAR(255) PRIMARY KEY,
                    policy_id VARCHAR(255) NOT NULL REFERENCES freeze_policies(policy_id),
                    slo_id VARCHAR(255) NOT NULL REFERENCES slo_definitions(slo_id),
                    service_name VARCHAR(255) NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    triggered_at TIMESTAMP NOT NULL,
                    resolved_at TIMESTAMP,
                    trigger_reason TEXT,
                    budget_remaining_percent FLOAT,
                    burn_rate FLOAT,
                    active BOOLEAN DEFAULT TRUE,
                    metadata JSONB
                )
            ''')

            # Criar índices
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_error_budgets_slo_id_calculated_at
                ON error_budgets(slo_id, calculated_at DESC)
            ''')
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_slo_definitions_service_enabled
                ON slo_definitions(service_name, enabled)
            ''')
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_freeze_events_active_triggered
                ON freeze_events(active, triggered_at DESC)
            ''')

    # Métodos de SLO Definitions
    async def create_slo(self, slo: SLODefinition) -> str:
        """Insere SLO na tabela."""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO slo_definitions
                (slo_id, name, description, slo_type, service_name, component, layer,
                 target, window_days, sli_query, error_budget_percent, enabled,
                 created_at, updated_at, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ''',
                slo.slo_id, slo.name, slo.description, slo.slo_type.value,
                slo.service_name, slo.component, slo.layer, slo.target,
                slo.window_days, slo.sli_query.model_dump_json(),
                slo.error_budget_percent, slo.enabled,
                slo.created_at, slo.updated_at, slo.metadata
            )
            return slo.slo_id

    async def get_slo(self, slo_id: str) -> Optional[SLODefinition]:
        """Busca SLO por ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM slo_definitions WHERE slo_id = $1',
                slo_id
            )
            if row:
                return SLODefinition(**self._parse_slo_row(row))
            return None

    async def list_slos(
        self,
        service_name: Optional[str] = None,
        enabled_only: bool = True
    ) -> List[SLODefinition]:
        """Lista SLOs com filtros opcionais."""
        query = 'SELECT * FROM slo_definitions WHERE 1=1'
        params = []

        if service_name:
            params.append(service_name)
            query += f' AND service_name = ${len(params)}'

        if enabled_only:
            query += ' AND enabled = TRUE'

        query += ' ORDER BY created_at DESC'

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [SLODefinition(**self._parse_slo_row(row)) for row in rows]

    async def find_slo_by_name(
        self,
        name: str,
        namespace: Optional[str] = None
    ) -> Optional[SLODefinition]:
        """Busca SLO por nome e namespace."""
        query = 'SELECT * FROM slo_definitions WHERE name = $1'
        params = [name]

        # Se namespace for fornecido, usar metadata para filtrar
        if namespace:
            query += " AND metadata->>'namespace' = $2"
            params.append(namespace)

        query += ' ORDER BY created_at DESC LIMIT 1'

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
            if row:
                return SLODefinition(**self._parse_slo_row(row))
            return None

    async def update_slo(self, slo_id: str, updates: Dict[str, Any]) -> bool:
        """Atualiza campos permitidos de um SLO."""
        import json
        from datetime import datetime

        if not updates:
            return False

        # Sempre atualizar updated_at
        updates = updates.copy()
        updates['updated_at'] = datetime.utcnow()

        set_clauses = []
        params = []
        param_idx = 1

        for field, value in updates.items():
            if field == 'sli_query':
                # Serialize SLIQuery to JSON
                if hasattr(value, 'model_dump_json'):
                    value = value.model_dump_json()
                elif isinstance(value, dict):
                    value = json.dumps(value)
            elif field == 'metadata' and isinstance(value, dict):
                value = json.dumps(value)

            params.append(value)
            set_clauses.append(f'{field} = ${param_idx}')
            param_idx += 1

        params.append(slo_id)
        query = f'''
            UPDATE slo_definitions
            SET {', '.join(set_clauses)}
            WHERE slo_id = ${param_idx}
        '''

        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(query, *params)
                success = result == 'UPDATE 1'
                if success:
                    self.logger.info("slo_updated_in_db", slo_id=slo_id, fields=list(updates.keys()))
                else:
                    self.logger.warning("slo_update_no_rows_affected", slo_id=slo_id)
                return success
        except Exception as e:
            self.logger.error("slo_update_failed", slo_id=slo_id, error=str(e))
            raise

    async def delete_slo(self, slo_id: str) -> bool:
        """Soft delete de SLO (marca como disabled)."""
        from datetime import datetime

        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute('''
                    UPDATE slo_definitions
                    SET enabled = FALSE, updated_at = $2
                    WHERE slo_id = $1
                ''', slo_id, datetime.utcnow())
                success = result == 'UPDATE 1'
                if success:
                    self.logger.info("slo_soft_deleted", slo_id=slo_id)
                else:
                    self.logger.warning("slo_delete_no_rows_affected", slo_id=slo_id)
                return success
        except Exception as e:
            self.logger.error("slo_delete_failed", slo_id=slo_id, error=str(e))
            raise

    # Métodos de Error Budgets
    async def save_budget(self, budget: ErrorBudget) -> str:
        """Insere budget calculado."""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO error_budgets
                (budget_id, slo_id, service_name, calculated_at, window_start, window_end,
                 sli_value, slo_target, error_budget_total, error_budget_consumed,
                 error_budget_remaining, status, burn_rates, violations_count,
                 last_violation_at, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            ''',
                budget.budget_id, budget.slo_id, budget.service_name,
                budget.calculated_at, budget.window_start, budget.window_end,
                budget.sli_value, budget.slo_target, budget.error_budget_total,
                budget.error_budget_consumed, budget.error_budget_remaining,
                budget.status.value,
                [br.model_dump() for br in budget.burn_rates],
                budget.violations_count, budget.last_violation_at, budget.metadata
            )
            return budget.budget_id

    async def get_latest_budget(self, slo_id: str) -> Optional[ErrorBudget]:
        """Busca budget mais recente para um SLO."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT * FROM error_budgets
                WHERE slo_id = $1
                ORDER BY calculated_at DESC
                LIMIT 1
            ''', slo_id)
            if row:
                return ErrorBudget(**dict(row))
            return None

    # Métodos de Freeze Policies
    async def create_policy(self, policy: FreezePolicy) -> str:
        """Cria política de freeze."""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO freeze_policies
                (policy_id, name, description, scope, target, actions,
                 trigger_threshold_percent, auto_unfreeze, unfreeze_threshold_percent,
                 enabled, created_at, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ''',
                policy.policy_id, policy.name, policy.description,
                policy.scope.value, policy.target,
                [a.value for a in policy.actions],
                policy.trigger_threshold_percent, policy.auto_unfreeze,
                policy.unfreeze_threshold_percent, policy.enabled,
                policy.created_at, policy.metadata
            )
            return policy.policy_id

    async def get_policy(self, policy_id: str) -> Optional[FreezePolicy]:
        """Busca política por ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM freeze_policies WHERE policy_id = $1',
                policy_id
            )
            if row:
                return FreezePolicy(**dict(row))
            return None

    async def list_policies(self, enabled_only: bool = True) -> List[FreezePolicy]:
        """Lista políticas."""
        query = 'SELECT * FROM freeze_policies'
        if enabled_only:
            query += ' WHERE enabled = TRUE'

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [FreezePolicy(**dict(row)) for row in rows]

    async def find_policy_by_name(
        self,
        name: str,
        namespace: Optional[str] = None
    ) -> Optional[FreezePolicy]:
        """Busca política por nome e namespace."""
        query = 'SELECT * FROM freeze_policies WHERE name = $1'
        params = [name]

        # Se namespace for fornecido, usar metadata para filtrar
        if namespace:
            query += " AND metadata->>'namespace' = $2"
            params.append(namespace)

        query += ' ORDER BY created_at DESC LIMIT 1'

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
            if row:
                return FreezePolicy(**dict(row))
            return None

    async def update_policy(self, policy_id: str, updates: Dict[str, Any]) -> bool:
        """Atualiza campos permitidos de uma política."""
        import json
        from datetime import datetime

        if not updates:
            return False

        set_clauses = []
        params = []
        param_idx = 1

        for field, value in updates.items():
            if field == 'metadata' and isinstance(value, dict):
                value = json.dumps(value)
            elif field == 'actions' and isinstance(value, list):
                # Convert PolicyAction enums to strings
                value = [a.value if hasattr(a, 'value') else a for a in value]

            params.append(value)
            set_clauses.append(f'{field} = ${param_idx}')
            param_idx += 1

        params.append(policy_id)
        query = f'''
            UPDATE freeze_policies
            SET {', '.join(set_clauses)}
            WHERE policy_id = ${param_idx}
        '''

        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(query, *params)
                success = result == 'UPDATE 1'
                if success:
                    self.logger.info("policy_updated_in_db", policy_id=policy_id, fields=list(updates.keys()))
                else:
                    self.logger.warning("policy_update_no_rows_affected", policy_id=policy_id)
                return success
        except Exception as e:
            self.logger.error("policy_update_failed", policy_id=policy_id, error=str(e))
            raise

    # Métodos de Freeze Events
    async def create_freeze_event(self, event: FreezeEvent) -> str:
        """Cria evento de freeze."""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO freeze_events
                (event_id, policy_id, slo_id, service_name, action, triggered_at,
                 trigger_reason, budget_remaining_percent, burn_rate, active, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ''',
                event.event_id, event.policy_id, event.slo_id, event.service_name,
                event.action.value, event.triggered_at, event.trigger_reason,
                event.budget_remaining_percent, event.burn_rate, event.active,
                event.metadata
            )
            return event.event_id

    async def get_active_freezes(
        self,
        service_name: Optional[str] = None
    ) -> List[FreezeEvent]:
        """Busca freezes ativos."""
        query = 'SELECT * FROM freeze_events WHERE active = TRUE'
        params = []

        if service_name:
            params.append(service_name)
            query += f' AND service_name = ${len(params)}'

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [FreezeEvent(**dict(row)) for row in rows]

    async def resolve_freeze_event(self, event_id: str) -> bool:
        """Resolve evento de freeze."""
        async with self.pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE freeze_events
                SET active = FALSE, resolved_at = NOW()
                WHERE event_id = $1
            ''', event_id)
            return result == "UPDATE 1"
