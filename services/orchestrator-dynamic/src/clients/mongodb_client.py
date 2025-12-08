"""
Cliente MongoDB para persistência de Cognitive Plans e Execution Tickets.

NOTA: Motor 3.7+ requer parameter names em snake_case:
- maxPoolSize -> max_pool_size
- serverSelectionTimeoutMS -> server_selection_timeout_ms
"""
import hashlib
import json
from datetime import datetime
from typing import Optional, Dict, Any

from pymongo.errors import DuplicateKeyError, PyMongoError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import structlog

logger = structlog.get_logger()


class MongoDBClient:
    """Cliente MongoDB para ledger de planos cognitivos e tickets de execução."""

    def __init__(self, config, uri_override: Optional[str] = None):
        """
        Inicializa o cliente MongoDB.

        Args:
            config: Configurações da aplicação
            uri_override: URI MongoDB alternativa (para integração Vault)
        """
        self.config = config
        self.uri_override = uri_override
        self.client = None
        self.db = None
        self.cognitive_ledger = None
        self.execution_tickets = None
        self.workflows = None
        self.validation_audit = None
        self.workflow_results = None
        self.incidents = None
        self.telemetry_buffer = None

    async def initialize(self):
        """Inicializar cliente MongoDB e criar índices."""
        from motor.motor_asyncio import AsyncIOMotorClient

        mongodb_uri = self.uri_override if self.uri_override else self.config.mongodb_uri

        # Motor 3.7+ requer snake_case para parameter names
        self.client = AsyncIOMotorClient(
            mongodb_uri,
            maxPoolSize=100,                      # Motor aceita camelCase via pymongo
            serverSelectionTimeoutMS=5000,        # Motor aceita camelCase via pymongo
            retryWrites=True,
            w='majority'
        )

        self.db = self.client[self.config.mongodb_database]
        self.cognitive_ledger = self.db['cognitive_ledger']
        self.execution_tickets = self.db[self.config.mongodb_collection_tickets]
        self.workflows = self.db[self.config.mongodb_collection_workflows]
        self.validation_audit = self.db['validation_audit']
        self.workflow_results = self.db['workflow_results']
        self.incidents = self.db['incidents']
        self.telemetry_buffer = self.db['telemetry_buffer']

        # Criar índices
        await self._create_indexes()

        # Verificar conectividade
        await self.client.admin.command('ping')
        logger.info('MongoDB client inicializado')

    async def _create_indexes(self):
        """Criar índices necessários para performance e integridade."""
        # Índices para cognitive_ledger
        await self.cognitive_ledger.create_index('plan_id', unique=True)
        await self.cognitive_ledger.create_index('intent_id')
        await self.cognitive_ledger.create_index('created_at')
        await self.cognitive_ledger.create_index([('status', 1), ('created_at', -1)])

        # Índices para execution_tickets
        await self.execution_tickets.create_index('ticket_id', unique=True)
        await self.execution_tickets.create_index('plan_id')
        await self.execution_tickets.create_index('intent_id')
        await self.execution_tickets.create_index('decision_id')
        await self.execution_tickets.create_index('status')
        await self.execution_tickets.create_index([('plan_id', 1), ('created_at', -1)])

        # Índices para workflows
        await self.workflows.create_index('workflow_id', unique=True)
        await self.workflows.create_index('plan_id')
        await self.workflows.create_index('status')

        await self._create_indexes_extended()

    async def _create_indexes_extended(self):
        """Criar índices adicionais para coleções de auditoria e telemetria."""
        await self.validation_audit.create_index('plan_id')
        await self.validation_audit.create_index('workflow_id')
        await self.validation_audit.create_index('timestamp')
        await self.validation_audit.create_index([('plan_id', 1), ('timestamp', -1)])

        await self.workflow_results.create_index('workflow_id', unique=True)
        await self.workflow_results.create_index('plan_id')
        await self.workflow_results.create_index('status')
        await self.workflow_results.create_index('consolidated_at')
        await self.workflow_results.create_index([('status', 1), ('consolidated_at', -1)])

        await self.incidents.create_index('workflow_id')
        await self.incidents.create_index('type')
        await self.incidents.create_index('severity')
        await self.incidents.create_index('timestamp')
        await self.incidents.create_index([('severity', 1), ('timestamp', -1)])

        await self.telemetry_buffer.create_index('workflow_id')
        await self.telemetry_buffer.create_index('buffered_at')
        await self.telemetry_buffer.create_index('retry_count')
        await self.telemetry_buffer.create_index([('retry_count', 1), ('buffered_at', 1)])

    async def get_cognitive_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca um Cognitive Plan no ledger.

        Args:
            plan_id: ID do plano cognitivo

        Returns:
            Documento do plano ou None se não encontrado
        """
        return await self.cognitive_ledger.find_one({'plan_id': plan_id})

    async def save_execution_ticket(self, ticket: Dict[str, Any]):
        """
        Persiste um Execution Ticket no MongoDB para auditoria.

        Args:
            ticket: Ticket de execução a ser salvo
        """
        document = ticket.copy()
        document['_id'] = ticket['ticket_id']

        try:
            await self.execution_tickets.insert_one(document)
            logger.info(
                'Execution ticket salvo',
                ticket_id=ticket['ticket_id'],
                plan_id=ticket['plan_id']
            )
        except DuplicateKeyError:
            # Se já existe, atualizar
            await self.execution_tickets.replace_one(
                {'ticket_id': ticket['ticket_id']},
                document
            )
            logger.info(
                'Execution ticket atualizado',
                ticket_id=ticket['ticket_id']
            )

    async def update_ticket_status(self, ticket_id: str, status: str, **kwargs):
        """
        Atualiza o status de um ticket.

        Args:
            ticket_id: ID do ticket
            status: Novo status
            **kwargs: Campos adicionais a atualizar
        """
        update_fields = {'status': status, **kwargs}
        await self.execution_tickets.update_one(
            {'ticket_id': ticket_id},
            {'$set': update_fields}
        )

    async def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca um ticket por ID.

        Args:
            ticket_id: ID do ticket

        Returns:
            Documento do ticket ou None se não encontrado
        """
        return await self.execution_tickets.find_one({'ticket_id': ticket_id})

    def _get_retry_decorator(self):
        """Retorna decorator de retry configurado conforme settings."""
        return retry(
            stop=stop_after_attempt(self.config.retry_max_attempts),
            wait=wait_exponential(
                multiplier=self.config.retry_backoff_coefficient,
                min=self.config.retry_initial_interval_ms / 1000,
                max=self.config.retry_max_interval_ms / 1000
            ),
            retry=retry_if_exception_type(PyMongoError)
        )

    async def save_validation_audit(self, plan_id: str, validation_result: Dict[str, Any], workflow_id: str) -> None:
        """
        Persiste auditoria de validação de plano cognitivo.

        Fail-open: erros são logados mas não propagados.
        """
        retry_decorator = self._get_retry_decorator()
        document = {
            'plan_id': plan_id,
            'validation_result': validation_result,
            'workflow_id': workflow_id,
            'timestamp': datetime.now().isoformat(),
            'hash': hashlib.sha256(json.dumps(validation_result, sort_keys=True).encode()).hexdigest()
        }

        @retry_decorator
        async def _persist():
            await self.validation_audit.insert_one(document)

        try:
            await _persist()
            logger.info(
                'validation_audit_saved',
                plan_id=plan_id,
                workflow_id=workflow_id
            )
        except Exception as e:
            logger.error(
                'validation_audit_save_failed',
                plan_id=plan_id,
                workflow_id=workflow_id,
                error=str(e)
            )

    async def save_workflow_result(self, workflow_result: Dict[str, Any]) -> None:
        """
        Persiste resultado consolidado de workflow.

        Fail-open: erros são logados mas não propagados.
        """
        retry_decorator = self._get_retry_decorator()
        workflow_id = workflow_result.get('workflow_id')
        document = {**workflow_result}
        if workflow_id:
            document['_id'] = workflow_id

        @retry_decorator
        async def _persist():
            await self.workflow_results.replace_one(
                {'_id': document.get('_id')},
                document,
                upsert=True
            )

        try:
            await _persist()
            logger.info(
                'workflow_result_saved',
                workflow_id=workflow_id,
                status=workflow_result.get('status'),
                total_tickets=workflow_result.get('metrics', {}).get('total_tickets')
            )
        except Exception as e:
            logger.error(
                'workflow_result_save_failed',
                workflow_id=workflow_id,
                error=str(e)
            )

    async def save_incident(self, incident_event: Dict[str, Any]) -> None:
        """
        Persiste incidente de autocura.

        Fail-open: erros são logados mas não propagados.
        """
        retry_decorator = self._get_retry_decorator()

        @retry_decorator
        async def _persist():
            await self.incidents.insert_one(incident_event)

        try:
            await _persist()
            logger.warning(
                'incident_saved',
                workflow_id=incident_event.get('workflow_id'),
                incident_type=incident_event.get('type'),
                severity=incident_event.get('severity')
            )
        except Exception as e:
            logger.error(
                'incident_save_failed',
                workflow_id=incident_event.get('workflow_id'),
                error=str(e)
            )

    async def save_telemetry_buffer(self, telemetry_frame: Dict[str, Any]) -> None:
        """
        Persiste frame de telemetria em buffer para retry.

        Fail-open: erros são logados mas não propagados.
        """
        retry_decorator = self._get_retry_decorator()

        @retry_decorator
        async def _persist():
            await self.telemetry_buffer.insert_one(telemetry_frame)

        try:
            await _persist()
            logger.warning(
                'telemetry_buffered',
                workflow_id=telemetry_frame.get('correlation', {}).get('workflow_id'),
                source=telemetry_frame.get('source')
            )
        except Exception as e:
            logger.error(
                'telemetry_buffer_failed',
                workflow_id=telemetry_frame.get('correlation', {}).get('workflow_id'),
                error=str(e)
            )

    async def close(self):
        """Fechar cliente MongoDB."""
        if self.client:
            self.client.close()
            logger.info('MongoDB client fechado')
