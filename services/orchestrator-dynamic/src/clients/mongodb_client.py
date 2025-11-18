"""
Cliente MongoDB para persistência de Cognitive Plans e Execution Tickets.
"""
from typing import Optional, Dict, Any
from pymongo.errors import DuplicateKeyError
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

    async def initialize(self):
        """Inicializar cliente MongoDB e criar índices."""
        from motor.motor_asyncio import AsyncIOMotorClient

        mongodb_uri = self.uri_override if self.uri_override else self.config.mongodb_uri

        self.client = AsyncIOMotorClient(
            mongodb_uri,
            maxPoolSize=100,
            serverSelectionTimeoutMS=5000,
            retryWrites=True,
            w='majority'
        )

        self.db = self.client[self.config.mongodb_database]
        self.cognitive_ledger = self.db['cognitive_ledger']
        self.execution_tickets = self.db[self.config.mongodb_collection_tickets]
        self.workflows = self.db[self.config.mongodb_collection_workflows]

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

    async def close(self):
        """Fechar cliente MongoDB."""
        if self.client:
            self.client.close()
            logger.info('MongoDB client fechado')
