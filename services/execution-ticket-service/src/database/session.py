"""Dependency injection for FastAPI database sessions."""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from .postgres_client import get_postgres_client


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency para injetar sessão PostgreSQL em routes FastAPI.

    Yields:
        AsyncSession: Sessão do SQLAlchemy

    Usage:
        @router.get('/tickets/{ticket_id}')
        async def get_ticket(
            ticket_id: str,
            db: AsyncSession = Depends(get_db_session)
        ):
            ...
    """
    postgres_client = await get_postgres_client()
    async with postgres_client.session_maker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
