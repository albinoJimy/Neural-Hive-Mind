"""
MongoDB Client para Approval Service

Fornece interface async para MongoDB para persistencia de aprovacoes.
"""

import structlog
from datetime import datetime
from typing import Dict, List, Optional, Any
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from src.config.settings import Settings
from src.models.approval import ApprovalRequest, ApprovalDecision, ApprovalStatus, ApprovalStats

logger = structlog.get_logger()


class MongoDBClient:
    """Cliente async MongoDB para operacoes de aprovacao"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.collection = None

    async def initialize(self):
        """Inicializa cliente MongoDB"""
        self.client = AsyncIOMotorClient(
            self.settings.mongodb_uri,
            maxPoolSize=self.settings.mongodb_max_pool_size,
            serverSelectionTimeoutMS=self.settings.mongodb_timeout_ms,
            retryWrites=True,
            w='majority'
        )

        self.db = self.client[self.settings.mongodb_database]
        self.collection = self.db[self.settings.mongodb_collection]

        # Cria indices
        await self._create_indexes()

        # Verifica conectividade
        await self.client.admin.command('ping')

        logger.info(
            'MongoDB client inicializado',
            uri=self.settings.mongodb_uri,
            database=self.settings.mongodb_database,
            collection=self.settings.mongodb_collection
        )

    async def _create_indexes(self):
        """Cria indices necessarios"""
        # Index unico por plan_id
        await self.collection.create_index('plan_id', unique=True)
        # Indices para queries
        await self.collection.create_index('status')
        await self.collection.create_index('requested_at')
        await self.collection.create_index('risk_band')
        await self.collection.create_index('is_destructive')
        # Index composto para queries de pendentes
        await self.collection.create_index([('status', 1), ('requested_at', -1)])
        # Index para intent_id
        await self.collection.create_index('intent_id')

        logger.debug('MongoDB indexes criados')

    async def save_approval_request(self, approval: ApprovalRequest) -> str:
        """
        Salva request de aprovacao no MongoDB

        Args:
            approval: Instancia de ApprovalRequest

        Returns:
            approval_id do documento inserido

        Raises:
            DuplicateKeyError: Se plan_id ja existe
        """
        document = {
            'approval_id': approval.approval_id,
            'plan_id': approval.plan_id,
            'intent_id': approval.intent_id,
            'risk_score': approval.risk_score,
            'risk_band': approval.risk_band.value if hasattr(approval.risk_band, 'value') else approval.risk_band,
            'is_destructive': approval.is_destructive,
            'destructive_tasks': approval.destructive_tasks,
            'risk_matrix': approval.risk_matrix,
            'status': approval.status.value if hasattr(approval.status, 'value') else approval.status,
            'requested_at': approval.requested_at,
            'approved_by': approval.approved_by,
            'approved_at': approval.approved_at,
            'rejection_reason': approval.rejection_reason,
            'comments': approval.comments,
            'cognitive_plan': approval.cognitive_plan
        }

        try:
            await self.collection.insert_one(document)
            logger.info(
                'Approval request salvo',
                plan_id=approval.plan_id,
                approval_id=approval.approval_id,
                risk_band=approval.risk_band
            )
            return approval.approval_id
        except DuplicateKeyError:
            logger.warning(
                'Plan_id ja existe no MongoDB',
                plan_id=approval.plan_id
            )
            raise

    async def get_approval_by_plan_id(self, plan_id: str) -> Optional[ApprovalRequest]:
        """
        Busca aprovacao por plan_id

        Args:
            plan_id: ID do plano

        Returns:
            ApprovalRequest ou None
        """
        document = await self.collection.find_one({'plan_id': plan_id})
        if document:
            document.pop('_id', None)
            return ApprovalRequest(**document)
        return None

    async def get_pending_approvals(
        self,
        limit: int = 50,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ApprovalRequest]:
        """
        Busca aprovacoes pendentes com filtros

        Args:
            limit: Limite de resultados
            offset: Offset para paginacao
            filters: Filtros adicionais (risk_band, is_destructive)

        Returns:
            Lista de ApprovalRequest
        """
        query = {'status': 'pending'}

        if filters:
            if filters.get('risk_band'):
                query['risk_band'] = filters['risk_band']
            if filters.get('is_destructive') is not None:
                query['is_destructive'] = filters['is_destructive']

        cursor = self.collection.find(query).sort(
            'requested_at', -1
        ).skip(offset).limit(limit)

        results = []
        async for document in cursor:
            document.pop('_id', None)
            results.append(ApprovalRequest(**document))

        logger.debug(
            'Query de aprovacoes pendentes executada',
            count=len(results),
            limit=limit,
            offset=offset
        )

        return results

    async def update_approval_decision(
        self,
        plan_id: str,
        decision: ApprovalDecision
    ) -> bool:
        """
        Atualiza decisao de aprovacao

        Args:
            plan_id: ID do plano
            decision: Decisao de aprovacao

        Returns:
            True se atualizado com sucesso
        """
        update_data = {
            'status': decision.decision,
            'approved_by': decision.approved_by,
            'approved_at': decision.approved_at,
            'comments': decision.comments
        }

        if decision.rejection_reason:
            update_data['rejection_reason'] = decision.rejection_reason

        result = await self.collection.update_one(
            {'plan_id': plan_id, 'status': 'pending'},
            {'$set': update_data}
        )

        if result.modified_count > 0:
            logger.info(
                'Decisao de aprovacao atualizada',
                plan_id=plan_id,
                decision=decision.decision,
                approved_by=decision.approved_by
            )
            return True

        logger.warning(
            'Nenhum documento atualizado',
            plan_id=plan_id,
            decision=decision.decision
        )
        return False

    async def get_approval_stats(self) -> ApprovalStats:
        """
        Retorna estatisticas de aprovacao

        Returns:
            ApprovalStats com contagens e metricas
        """
        pipeline = [
            {
                '$facet': {
                    'status_counts': [
                        {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
                    ],
                    'risk_band_pending': [
                        {'$match': {'status': 'pending'}},
                        {'$group': {'_id': '$risk_band', 'count': {'$sum': 1}}}
                    ],
                    'avg_approval_time': [
                        {'$match': {'status': 'approved', 'approved_at': {'$ne': None}}},
                        {
                            '$project': {
                                'approval_time': {
                                    '$subtract': ['$approved_at', '$requested_at']
                                }
                            }
                        },
                        {'$group': {'_id': None, 'avg': {'$avg': '$approval_time'}}}
                    ]
                }
            }
        ]

        result = await self.collection.aggregate(pipeline).to_list(length=1)

        if not result:
            return ApprovalStats(
                pending_count=0,
                approved_count=0,
                rejected_count=0,
                avg_approval_time_seconds=None,
                by_risk_band={}
            )

        data = result[0]

        # Processa contagens por status
        status_map = {item['_id']: item['count'] for item in data.get('status_counts', [])}

        # Processa contagens por risk_band para pendentes
        risk_band_map = {item['_id']: item['count'] for item in data.get('risk_band_pending', [])}

        # Processa tempo medio de aprovacao
        avg_time = None
        if data.get('avg_approval_time') and data['avg_approval_time']:
            avg_ms = data['avg_approval_time'][0].get('avg')
            if avg_ms:
                avg_time = avg_ms / 1000  # Converte ms para segundos

        return ApprovalStats(
            pending_count=status_map.get('pending', 0),
            approved_count=status_map.get('approved', 0),
            rejected_count=status_map.get('rejected', 0),
            avg_approval_time_seconds=avg_time,
            by_risk_band=risk_band_map
        )

    async def close(self):
        """Fecha cliente MongoDB"""
        if self.client:
            self.client.close()
            logger.info('MongoDB client fechado')
