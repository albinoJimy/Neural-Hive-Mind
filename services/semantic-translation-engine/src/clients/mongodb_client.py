"""
MongoDB Client for operational context and cognitive ledger

Provides async interface to MongoDB for context storage and immutable ledger.
"""

import structlog
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from src.config.settings import Settings

logger = structlog.get_logger()


class MongoDBClient:
    """Async MongoDB client for context and ledger operations"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.context_collection = None
        self.ledger_collection = None

    async def initialize(self):
        """Initialize MongoDB client"""
        self.client = AsyncIOMotorClient(
            self.settings.mongodb_uri,
            maxPoolSize=self.settings.mongodb_max_pool_size,
            serverSelectionTimeoutMS=self.settings.mongodb_timeout_ms,
            retryWrites=True,
            w='majority'  # Write concern for durability
        )

        self.db = self.client[self.settings.mongodb_database]
        self.context_collection = self.db[self.settings.mongodb_context_collection]
        self.ledger_collection = self.db[self.settings.mongodb_ledger_collection]

        # Create indexes
        await self._create_indexes()

        # Verify connectivity
        await self.client.admin.command('ping')

        logger.info(
            'MongoDB client inicializado',
            uri=self.settings.mongodb_uri,
            database=self.settings.mongodb_database
        )

    async def _create_indexes(self):
        """Create necessary indexes"""
        # Indexes for operational context
        await self.context_collection.create_index('intent_id', unique=True)
        await self.context_collection.create_index('timestamp')
        await self.context_collection.create_index('domain')

        # Indexes for cognitive ledger
        await self.ledger_collection.create_index('plan_id', unique=True)
        await self.ledger_collection.create_index('intent_id')
        await self.ledger_collection.create_index('timestamp')
        await self.ledger_collection.create_index('hash')
        await self.ledger_collection.create_index('plan_data.saga_state')

        logger.debug('MongoDB indexes created')

    async def get_operational_context(self, intent_id: str) -> Optional[Dict]:
        """
        Retrieve operational context for an intent

        Args:
            intent_id: Intent identifier

        Returns:
            Context document or None
        """
        return await self.context_collection.find_one({'intent_id': intent_id})

    async def save_operational_context(self, intent_id: str, context: Dict):
        """
        Save operational context

        Args:
            intent_id: Intent identifier
            context: Context data
        """
        document = {
            'intent_id': intent_id,
            'context': context,
            'timestamp': datetime.utcnow(),
            'ttl_expires_at': datetime.utcnow() + timedelta(days=30)
        }

        await self.context_collection.update_one(
            {'intent_id': intent_id},
            {'$set': document},
            upsert=True
        )

        logger.debug('Operational context saved', intent_id=intent_id)

    async def append_to_ledger(self, cognitive_plan) -> str:
        """
        Append cognitive plan to immutable ledger

        Args:
            cognitive_plan: CognitivePlan instance

        Returns:
            Ledger entry hash

        Raises:
            DuplicateKeyError: If plan_id already exists
        """
        # Serialize plan
        plan_dict = cognitive_plan.dict()

        # Calculate hash for integrity
        plan_hash = self._calculate_hash(plan_dict)

        ledger_entry = {
            'plan_id': cognitive_plan.plan_id,
            'intent_id': cognitive_plan.intent_id,
            'version': cognitive_plan.version,
            'plan_data': plan_dict,
            'hash': plan_hash,
            'timestamp': datetime.utcnow(),
            'immutable': True
        }

        try:
            await self.ledger_collection.insert_one(ledger_entry)

            logger.info(
                'Plano registrado no ledger',
                plan_id=cognitive_plan.plan_id,
                hash=plan_hash
            )

            return plan_hash

        except DuplicateKeyError:
            logger.warning(
                'Plano já existe no ledger',
                plan_id=cognitive_plan.plan_id
            )
            raise

    def _calculate_hash(self, data: Dict) -> str:
        """
        Calculate SHA-256 hash for data integrity

        Args:
            data: Data to hash

        Returns:
            Hex-encoded hash
        """
        # Serialize deterministically
        json_str = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

    async def query_ledger(self, plan_id: str) -> Optional[Dict]:
        """
        Query ledger by plan_id

        Args:
            plan_id: Plan identifier

        Returns:
            Ledger entry or None
        """
        return await self.ledger_collection.find_one({'plan_id': plan_id})

    async def verify_ledger_integrity(self, plan_id: str) -> bool:
        """
        Verify integrity of ledger entry

        Args:
            plan_id: Plan identifier

        Returns:
            True if integrity check passes
        """
        entry = await self.query_ledger(plan_id)
        if not entry:
            return False

        # Recalculate hash
        calculated_hash = self._calculate_hash(entry['plan_data'])
        stored_hash = entry['hash']

        if calculated_hash != stored_hash:
            logger.error(
                'Ledger integrity check failed',
                plan_id=plan_id,
                calculated=calculated_hash,
                stored=stored_hash
            )
            return False

        return True

    async def update_plan_approval_status(
        self,
        plan_id: str,
        approval_status: str,
        approved_by: str,
        approved_at: datetime,
        rejection_reason: Optional[str] = None,
        saga_state: Optional[str] = None,
        saga_failure_reason: Optional[str] = None
    ) -> bool:
        """
        Atualiza status de aprovação de um plano no ledger.

        Args:
            plan_id: ID do plano
            approval_status: 'approved' ou 'rejected'
            approved_by: ID do aprovador
            approved_at: Timestamp da decisão
            rejection_reason: Motivo da rejeição (opcional)
            saga_state: Estado da saga ('executing', 'completed', 'compensated', 'failed')
            saga_failure_reason: Razão da falha da saga (quando saga_state='failed')

        Returns:
            True se atualizado com sucesso
        """
        update_fields = {
            'plan_data.approval_status': approval_status,
            'plan_data.approved_by': approved_by,
            'plan_data.approved_at': approved_at,
            'plan_data.status': approval_status,
            'updated_at': datetime.utcnow()
        }

        if rejection_reason:
            update_fields['plan_data.rejection_reason'] = rejection_reason

        if saga_state:
            update_fields['plan_data.saga_state'] = saga_state

        if saga_failure_reason:
            update_fields['plan_data.saga_failure_reason'] = saga_failure_reason

        try:
            result = await self.ledger_collection.update_one(
                {'plan_id': plan_id},
                {'$set': update_fields}
            )

            if result.modified_count > 0:
                logger.info(
                    'Status de aprovação atualizado no ledger',
                    plan_id=plan_id,
                    approval_status=approval_status,
                    approved_by=approved_by
                )
                return True
            else:
                logger.warning(
                    'Nenhum documento atualizado no ledger',
                    plan_id=plan_id,
                    matched_count=result.matched_count
                )
                return False

        except Exception as e:
            logger.error(
                'Erro ao atualizar status de aprovação no ledger',
                plan_id=plan_id,
                error=str(e)
            )
            raise

    async def revert_plan_approval_status(
        self,
        plan_id: str,
        saga_state: str,
        compensation_reason: str
    ) -> bool:
        """
        Reverte status de aprovação de um plano para 'pending'.

        Usado pela saga de aprovação quando a publicação no Kafka falha
        após retries e a compensação precisa ser executada.

        Args:
            plan_id: ID do plano
            saga_state: Estado da saga ('compensated' ou 'failed')
            compensation_reason: Razão da compensação

        Returns:
            True se revertido com sucesso
        """
        update_fields = {
            'plan_data.approval_status': 'pending',
            'plan_data.approved_by': None,
            'plan_data.approved_at': None,
            'plan_data.status': 'pending',
            'plan_data.saga_state': saga_state,
            'plan_data.compensation_metadata': {
                'compensated_at': datetime.utcnow(),
                'compensation_reason': compensation_reason
            },
            'updated_at': datetime.utcnow()
        }

        try:
            result = await self.ledger_collection.update_one(
                {'plan_id': plan_id},
                {'$set': update_fields}
            )

            if result.modified_count > 0:
                logger.info(
                    'Status de aprovação revertido (compensação)',
                    plan_id=plan_id,
                    saga_state=saga_state,
                    compensation_reason=compensation_reason[:100]
                )
                return True
            else:
                logger.warning(
                    'Nenhum documento atualizado na reversão',
                    plan_id=plan_id,
                    matched_count=result.matched_count
                )
                return False

        except Exception as e:
            logger.error(
                'Erro ao reverter status de aprovação',
                plan_id=plan_id,
                error=str(e)
            )
            raise

    async def update_plan_saga_state(
        self,
        plan_id: str,
        saga_state: str,
        saga_failure_reason: Optional[str] = None
    ) -> bool:
        """
        Atualiza apenas o saga_state de um plano no ledger.

        Usado para marcar saga como 'failed' quando compensação falha,
        sem modificar outros campos de aprovação.

        Args:
            plan_id: ID do plano
            saga_state: Novo estado da saga ('executing', 'completed', 'compensated', 'failed')
            saga_failure_reason: Razão da falha (quando saga_state='failed')

        Returns:
            True se atualizado com sucesso
        """
        update_fields = {
            'plan_data.saga_state': saga_state,
            'updated_at': datetime.utcnow()
        }

        if saga_failure_reason:
            update_fields['plan_data.saga_failure_reason'] = saga_failure_reason

        try:
            result = await self.ledger_collection.update_one(
                {'plan_id': plan_id},
                {'$set': update_fields}
            )

            if result.modified_count > 0:
                logger.info(
                    'Saga state atualizado no ledger',
                    plan_id=plan_id,
                    saga_state=saga_state
                )
                return True
            else:
                logger.warning(
                    'Nenhum documento atualizado (saga_state)',
                    plan_id=plan_id,
                    matched_count=result.matched_count
                )
                return False

        except Exception as e:
            logger.error(
                'Erro ao atualizar saga_state',
                plan_id=plan_id,
                error=str(e)
            )
            raise

    async def update_plan_dlq_status(
        self,
        plan_id: str,
        status: str,
        failure_reason: str,
        retry_count: int,
        last_failure_at: datetime
    ) -> bool:
        """
        Atualiza status de DLQ de um plano no ledger.

        Usado quando DLQ reprocessor marca um plano como permanentemente falhado.

        Args:
            plan_id: ID do plano
            status: Status DLQ ('permanently_failed')
            failure_reason: Razão da falha
            retry_count: Número de tentativas realizadas
            last_failure_at: Timestamp da última falha

        Returns:
            True se atualizado com sucesso
        """
        update_fields = {
            'plan_data.dlq_status': status,
            'plan_data.dlq_failure_reason': failure_reason,
            'plan_data.dlq_retry_count': retry_count,
            'plan_data.dlq_last_failure_at': last_failure_at,
            'updated_at': datetime.utcnow()
        }

        try:
            result = await self.ledger_collection.update_one(
                {'plan_id': plan_id},
                {'$set': update_fields}
            )

            if result.modified_count > 0:
                logger.info(
                    'DLQ status atualizado no ledger',
                    plan_id=plan_id,
                    dlq_status=status,
                    retry_count=retry_count
                )
                return True
            else:
                logger.warning(
                    'Nenhum documento atualizado (dlq_status)',
                    plan_id=plan_id,
                    matched_count=result.matched_count
                )
                return False

        except Exception as e:
            logger.error(
                'Erro ao atualizar DLQ status',
                plan_id=plan_id,
                error=str(e)
            )
            raise

    async def close(self):
        """Close MongoDB client"""
        if self.client:
            self.client.close()
            logger.info('MongoDB client fechado')
