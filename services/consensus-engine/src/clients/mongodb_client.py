from typing import Optional, Dict
from pymongo.errors import DuplicateKeyError
import structlog
from src.models.consolidated_decision import ConsolidatedDecision

logger = structlog.get_logger()


class MongoDBClient:
    '''Cliente MongoDB para ledger de decisões consolidadas'''

    def __init__(self, config):
        self.config = config
        self.client = None
        self.db = None
        self.consensus_collection = None
        self.explainability_collection = None

    async def initialize(self):
        '''Inicializar cliente MongoDB'''
        from motor.motor_asyncio import AsyncIOMotorClient

        self.client = AsyncIOMotorClient(
            self.config.mongodb_uri,
            maxPoolSize=50,  # Reduzido de 100 para evitar sobrecarga
            serverSelectionTimeoutMS=30000,  # Aumentado de 5s para 30s
            connectTimeoutMS=30000,  # Timeout de conexão aumentado
            socketTimeoutMS=30000,  # Timeout de socket aumentado
            retryWrites=True,
            w='majority'
        )

        self.db = self.client[self.config.mongodb_database]
        self.consensus_collection = self.db[self.config.mongodb_consensus_collection]
        self.explainability_collection = self.db['consensus_explainability']

        # Criar índices
        await self._create_indexes()

        # Verificar conectividade
        await self.client.admin.command('ping')
        logger.info('MongoDB client inicializado')

    async def _create_indexes(self):
        '''Criar índices necessários (idempotente - ignora se já existem)'''
        try:
            # Índices para decisões consolidadas
            await self.consensus_collection.create_index('decision_id', unique=True)
            await self.consensus_collection.create_index('plan_id')
            await self.consensus_collection.create_index('intent_id')
            await self.consensus_collection.create_index('created_at')
            await self.consensus_collection.create_index('hash')
            await self.consensus_collection.create_index(
                [('final_decision', 1), ('created_at', -1)]
            )

            # Índices para explicabilidade
            await self.explainability_collection.create_index('token', unique=True)
            await self.explainability_collection.create_index('timestamp')

            logger.info('Índices MongoDB criados/verificados com sucesso')
        except Exception as e:
            # Índices podem já existir, especialmente em ambiente multi-worker
            logger.warning('Aviso ao criar índices MongoDB (podem já existir)', error=str(e))

    async def save_consensus_decision(self, decision: ConsolidatedDecision):
        '''Salva decisão consolidada no ledger'''
        # Usar model_dump com mode='json' para garantir serialização correta de enums
        # Isso converte DecisionType.APPROVE para "approve" automaticamente
        document = decision.model_dump(mode='json')
        document['_id'] = decision.decision_id
        document['immutable'] = True

        try:
            await self.consensus_collection.insert_one(document)
            logger.info(
                'Decisão consolidada salva',
                decision_id=decision.decision_id,
                hash=decision.hash
            )
        except DuplicateKeyError:
            logger.warning(
                'Decisão já existe no ledger',
                decision_id=decision.decision_id
            )
            raise

    async def get_decision(self, decision_id: str) -> Optional[Dict]:
        '''Consulta decisão por ID'''
        return await self.consensus_collection.find_one({'decision_id': decision_id})

    async def get_decision_by_plan(self, plan_id: str) -> Optional[Dict]:
        '''Consulta decisão por plan_id'''
        return await self.consensus_collection.find_one({'plan_id': plan_id})

    async def verify_integrity(self, decision_id: str) -> bool:
        '''Verifica integridade de decisão'''
        decision = await self.get_decision(decision_id)
        if not decision:
            return False

        # Reconstruir ConsolidatedDecision e recalcular hash
        stored_hash = decision.pop('hash', None)
        decision_obj = ConsolidatedDecision(**decision)
        calculated_hash = decision_obj.calculate_hash()

        return calculated_hash == stored_hash

    async def close(self):
        '''Fechar cliente'''
        if self.client:
            self.client.close()
            logger.info('MongoDB client fechado')
