"""Cliente PostgreSQL para persistência de tickets usando SQLAlchemy async."""
import logging
from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine
from sqlalchemy import select, update, func
from sqlalchemy.exc import SQLAlchemyError

from ..config.settings import TicketServiceSettings
from ..models.ticket_orm import TicketORM, Base
from ..models import ExecutionTicket, TicketStatus

logger = logging.getLogger(__name__)


class PostgresClient:
    """Cliente PostgreSQL async para gerenciar tickets."""

    def __init__(self, settings: TicketServiceSettings):
        """Inicializa cliente PostgreSQL."""
        self.settings = settings
        self._engine: Optional[AsyncEngine] = None
        self._session_maker: Optional[async_sessionmaker] = None

    async def connect(self):
        """Estabelece conexão com PostgreSQL."""
        connection_string = (
            f"postgresql+asyncpg://{self.settings.postgres_user}:{self.settings.postgres_password}"
            f"@{self.settings.postgres_host}:{self.settings.postgres_port}/{self.settings.postgres_database}"
        )

        self._engine = create_async_engine(
            connection_string,
            pool_size=self.settings.postgres_pool_size,
            max_overflow=self.settings.postgres_max_overflow,
            echo=False
        )

        self._session_maker = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        logger.info("PostgreSQL client connected", host=self.settings.postgres_host)

    async def disconnect(self):
        """Fecha conexão com PostgreSQL."""
        if self._engine:
            await self._engine.dispose()
            logger.info("PostgreSQL client disconnected")

    def session_maker(self):
        """Retorna session maker."""
        return self._session_maker

    async def health_check(self) -> bool:
        """Verifica saúde da conexão."""
        try:
            async with self._session_maker() as session:
                result = await session.execute(select(func.count()).select_from(TicketORM))
                return True
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return False

    async def create_ticket(self, ticket: ExecutionTicket) -> TicketORM:
        """Cria novo ticket."""
        async with self._session_maker() as session:
            orm_ticket = TicketORM.from_pydantic(ticket)
            session.add(orm_ticket)
            await session.commit()
            await session.refresh(orm_ticket)
            logger.info(f"Ticket created", ticket_id=ticket.ticket_id)
            return orm_ticket

    async def get_ticket_by_id(self, ticket_id: str) -> Optional[TicketORM]:
        """Busca ticket por ID."""
        async with self._session_maker() as session:
            result = await session.execute(
                select(TicketORM).where(TicketORM.ticket_id == ticket_id)
            )
            return result.scalar_one_or_none()

    async def get_tickets_by_plan_id(self, plan_id: str) -> List[TicketORM]:
        """Busca tickets por plan_id."""
        async with self._session_maker() as session:
            result = await session.execute(
                select(TicketORM).where(TicketORM.plan_id == plan_id)
            )
            return list(result.scalars().all())

    async def get_tickets_by_status(self, status: TicketStatus, limit: int = 100) -> List[TicketORM]:
        """Busca tickets por status."""
        async with self._session_maker() as session:
            result = await session.execute(
                select(TicketORM)
                .where(TicketORM.status == status.value)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def update_ticket_status(
        self,
        ticket_id: str,
        status: TicketStatus,
        error_message: Optional[str] = None
    ) -> Optional[TicketORM]:
        """Atualiza status do ticket."""
        async with self._session_maker() as session:
            stmt = (
                update(TicketORM)
                .where(TicketORM.ticket_id == ticket_id)
                .values(status=status.value, error_message=error_message)
                .returning(TicketORM)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.scalar_one_or_none()

    async def list_tickets(self, filters: dict, offset: int = 0, limit: int = 100) -> List[TicketORM]:
        """Lista tickets com filtros."""
        async with self._session_maker() as session:
            query = select(TicketORM)

            if 'plan_id' in filters:
                query = query.where(TicketORM.plan_id == filters['plan_id'])
            if 'status' in filters:
                query = query.where(TicketORM.status == filters['status'])
            if 'priority' in filters:
                query = query.where(TicketORM.priority == filters['priority'])

            query = query.offset(offset).limit(limit).order_by(TicketORM.created_at.desc())

            result = await session.execute(query)
            return list(result.scalars().all())

    async def count_tickets(self, filters: dict) -> int:
        """Conta tickets com filtros."""
        async with self._session_maker() as session:
            query = select(func.count()).select_from(TicketORM)

            if 'plan_id' in filters:
                query = query.where(TicketORM.plan_id == filters['plan_id'])
            if 'status' in filters:
                query = query.where(TicketORM.status == filters['status'])

            result = await session.execute(query)
            return result.scalar()


# Singleton instance
_postgres_client: Optional[PostgresClient] = None


async def get_postgres_client() -> PostgresClient:
    """Retorna singleton do PostgreSQL client."""
    global _postgres_client
    if _postgres_client is None:
        from ..config import get_settings
        settings = get_settings()
        _postgres_client = PostgresClient(settings)
        await _postgres_client.connect()
    return _postgres_client
