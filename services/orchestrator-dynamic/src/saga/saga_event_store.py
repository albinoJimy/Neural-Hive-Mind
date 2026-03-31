"""
Event Store para eventos de Saga.

Persiste eventos de Saga no MongoDB para auditoria e reconstrucao
do historico de transaccoes.
"""
from typing import List, Optional, Dict, Any
from uuid import uuid4
import asyncio

import structlog
from motor.motor_asyncio import AsyncIOMotorClientSession

from .saga_state import SagaEvent, SagaEventType


logger = structlog.get_logger()


class SagaEventStore:
    """
    Event Store para eventos de Saga com MongoDB.

    Responsavel por gravar e recuperar eventos de Saga para
    auditoria e tracing de transaccoes distribuidas.
    """

    # Nome da colecao no MongoDB
    COLLECTION_NAME = 'saga_events'

    # Tipos de evento que geram logs de warning
    WARNING_EVENT_TYPES = {
        SagaEventType.saga_step_failed,
        SagaEventType.saga_compensating,
        SagaEventType.saga_failed
    }

    def __init__(self, mongodb_client):
        """
        Inicializa o event store.

        Args:
            mongodb_client: MongoDBClient inicializado
        """
        self._client = mongodb_client
        self._collection = None

    async def initialize(self) -> None:
        """
        Inicializa a colecao e cria indices.

        Deve ser chamado apos o MongoDBClient estar conectado.
        """
        db = self._client.db
        self._collection = db[self.COLLECTION_NAME]

        # Criar indices
        await self._create_indexes()

        logger.info(
            'saga_event_store_initialized',
            collection=self.COLLECTION_NAME
        )

    async def _create_indexes(self) -> None:
        """Cria indices na colecao de eventos."""
        if self._collection is None:
            return

        indexes = [
            # Index primario para consultas por saga_id
            {'keys': [('saga_id', 1)], 'name': 'saga_id_1'},
            # Index para queries temporais
            {'keys': [('timestamp', -1)], 'name': 'timestamp_-1'},
            # Index composto para filtros por tipo e saga
            {'keys': [('saga_id', 1), ('event_type', 1)], 'name': 'saga_id_1_event_type_1'},
            # Index para queries por tipo (monitoramento)
            {'keys': [('event_type', 1), ('timestamp', -1)], 'name': 'event_type_1_timestamp_-1'},
        ]

        for index_def in indexes:
            try:
                await self._collection.create_index(
                    index_def['keys'],
                    name=index_def['name'],
                    background=True
                )
            except Exception as e:
                logger.warning(
                    'saga_event_store_index_creation_failed',
                    index=index_def['name'],
                    error=str(e)
                )

    async def record_event(
        self,
        event: SagaEvent,
        timeout_ms: int = 5000
    ) -> bool:
        """
        Grava um evento de Saga.

        Args:
            event: Evento a gravar
            timeout_ms: Timeout em milissegundos (default 5000ms)

        Returns:
            True se gravado com sucesso
        """
        if self._collection is None:
            logger.warning(
                'saga_event_store_not_initialized',
                event_id=event.event_id
            )
            return False

        try:
            doc = event.model_dump()

            await asyncio.wait_for(
                self._collection.insert_one(doc),
                timeout=timeout_ms / 1000.0
            )

            # Log baseado no tipo de evento
            log_method = logger.warning if event.event_type in self.WARNING_EVENT_TYPES else logger.info

            log_method(
                'saga_event_recorded',
                event_id=event.event_id,
                saga_id=event.saga_id,
                event_type=event.event_type.value
            )

            return True

        except asyncio.TimeoutError:
            logger.error(
                'saga_event_record_timeout',
                event_id=event.event_id,
                saga_id=event.saga_id,
                timeout_ms=timeout_ms
            )
            return False
        except Exception as e:
            logger.error(
                'saga_event_record_failed',
                event_id=event.event_id,
                saga_id=event.saga_id,
                error=str(e)
            )
            return False

    async def record_event_raw(
        self,
        saga_id: str,
        event_type: SagaEventType,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Cria e grava um evento de Saga.

        Args:
            saga_id: ID da Saga
            event_type: Tipo do evento
            data: Dados adicionais do evento

        Returns:
            True se gravado com sucesso
        """
        event = SagaEvent.create(
            saga_id=saga_id,
            event_type=event_type,
            data=data or {}
        )
        return await self.record_event(event)

    async def get_saga_events(
        self,
        saga_id: str,
        limit: Optional[int] = None,
        timeout_ms: int = 5000
    ) -> List[SagaEvent]:
        """
        Recupera todos os eventos de uma Saga.

        Args:
            saga_id: ID da Saga
            limit: Numero maximo de eventos (mais recentes)
            timeout_ms: Timeout em milissegundos (default 5000ms)

        Returns:
            Lista de eventos em ordem cronologica
        """
        if self._collection is None:
            logger.warning('saga_event_store_not_initialized')
            return []

        try:
            query = {'saga_id': saga_id}
            cursor = self._collection.find(query).sort('timestamp', 1)

            if limit:
                cursor = cursor.limit(limit)

            docs = await asyncio.wait_for(
                cursor.to_list(length=limit or 1000),
                timeout=timeout_ms / 1000.0
            )

            events = [
                SagaEvent(**doc) for doc in docs
            ]

            logger.debug(
                'saga_events_retrieved',
                saga_id=saga_id,
                count=len(events)
            )

            return events

        except asyncio.TimeoutError:
            logger.error(
                'saga_events_retrieval_timeout',
                saga_id=saga_id,
                timeout_ms=timeout_ms
            )
            return []
        except Exception as e:
            logger.error(
                'saga_events_retrieval_failed',
                saga_id=saga_id,
                error=str(e)
            )
            return []

    async def get_events_by_type(
        self,
        event_type: SagaEventType,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100
    ) -> List[SagaEvent]:
        """
        Recupera eventos por tipo para monitoramento.

        Args:
            event_type: Tipo de evento a filtrar
            start_time: Timestamp inicial (millis)
            end_time: Timestamp final (millis)
            limit: Numero maximo de eventos

        Returns:
            Lista de eventos
        """
        if self._collection is None:
            logger.warning('saga_event_store_not_initialized')
            return []

        try:
            query = {'event_type': event_type.value}

            if start_time or end_time:
                query['timestamp'] = {}
                if start_time:
                    query['timestamp']['$gte'] = start_time
                if end_time:
                    query['timestamp']['$lte'] = end_time

            cursor = self._collection.find(query).sort('timestamp', -1).limit(limit)

            docs = await cursor.to_list(length=limit)

            events = [
                SagaEvent(**doc) for doc in docs
            ]

            logger.debug(
                'saga_events_by_type_retrieved',
                event_type=event_type.value,
                count=len(events)
            )

            return events

        except Exception as e:
            logger.error(
                'saga_events_by_type_retrieval_failed',
                event_type=event_type.value,
                error=str(e)
            )
            return []

    async def get_latest_saga_status(
        self,
        saga_id: str
    ) -> Optional[str]:
        """
        Determina o status atual da Saga baseado no ultimo evento.

        Args:
            saga_id: ID da Saga

        Returns:
            Status da Saga ou None se sem eventos
        """
        events = await self.get_saga_events(saga_id, limit=1)
        if not events:
            return None

        # Mapear tipo de evento para status
        event_to_status = {
            SagaEventType.saga_created: 'PENDING',
            SagaEventType.saga_started: 'STARTED',
            SagaEventType.saga_step_completed: 'IN_PROGRESS',
            SagaEventType.saga_step_failed: 'FAILED',
            SagaEventType.saga_compensating: 'COMPENSATING',
            SagaEventType.saga_step_compensated: 'COMPENSATING',
            SagaEventType.saga_compensated: 'COMPENSATED',
            SagaEventType.saga_completed: 'COMPLETED',
            SagaEventType.saga_failed: 'FAILED'
        }

        last_event = events[-1]
        return event_to_status.get(last_event.event_type)

    async def delete_saga_events(
        self,
        saga_id: str
    ) -> int:
        """
        Remove todos os eventos de uma Saga.

        Usado para limpeza de sagas antigas.

        Args:
            saga_id: ID da Saga

        Returns:
            Numero de eventos removidos
        """
        if self._collection is None:
            return 0

        try:
            result = await self._collection.delete_many({'saga_id': saga_id})

            logger.info(
                'saga_events_deleted',
                saga_id=saga_id,
                count=result.deleted_count
            )

            return result.deleted_count

        except Exception as e:
            logger.error(
                'saga_events_deletion_failed',
                saga_id=saga_id,
                error=str(e)
            )
            return 0
