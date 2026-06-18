from typing import Optional

import structlog
from pymongo.errors import DuplicateKeyError
from src.models.consolidated_decision import ConsolidatedDecision

logger = structlog.get_logger()


class MongoDBClient:
    """Cliente MongoDB para ledger de decisões consolidadas com suporte a cache-aside"""

    def __init__(self, config):
        self.config = config
        self.client = None
        self.db = None
        self.consensus_collection = None
        self.explainability_collection = None
        self.cache_service = None  # Será injetado após inicialização

    def set_cache_service(self, cache_service):
        """
        Injeta serviço de cache para cache-aside pattern.

        Args:
            cache_service: Instância de CacheAsideService
        """
        self.cache_service = cache_service
        logger.info("Cache service injetado no MongoDB client")

    async def initialize(self):
        """Inicializar cliente MongoDB"""
        from motor.motor_asyncio import AsyncIOMotorClient

        self.client = AsyncIOMotorClient(
            self.config.mongodb_uri,
            maxPoolSize=50,  # Reduzido de 100 para evitar sobrecarga
            serverSelectionTimeoutMS=30000,  # Aumentado de 5s para 30s
            connectTimeoutMS=30000,  # Timeout de conexão aumentado
            socketTimeoutMS=30000,  # Timeout de socket aumentado
            retryWrites=True,
            w="majority",
            # Devolve datetimes timezone-aware (UTC) em vez de naive. Evita
            # "can't compare offset-naive and offset-aware datetimes" ao comparar
            # campos como expires_at (lidos do BSON) com datetime.now(timezone.utc).
            tz_aware=True,
        )

        self.db = self.client[self.config.mongodb_database]
        self.consensus_collection = self.db[self.config.mongodb_consensus_collection]
        self.explainability_collection = self.db["consensus_explainability"]

        # Criar índices
        await self._create_indexes()

        # Verificar conectividade
        await self.client.admin.command("ping")
        logger.info("MongoDB client inicializado")

    async def _create_indexes(self):
        """Criar índices necessários (idempotente - ignora se já existem)"""
        try:
            # Índices para decisões consolidadas
            await self.consensus_collection.create_index("decision_id", unique=True)
            # plan_id NÃO é único: um plano pode legitimamente ter mais do que uma
            # decisão histórica (reavaliações). A eliminação do duplo processamento é
            # feita na origem — o STE deixou de republicar o plano aprovado em
            # plans.ready (passou a plans.approved). Um índice único aqui falharia em
            # colecções com duplicados existentes e saltaria os índices seguintes.
            await self.consensus_collection.create_index("plan_id")
            await self.consensus_collection.create_index("intent_id")
            await self.consensus_collection.create_index("created_at")
            await self.consensus_collection.create_index("hash")
            await self.consensus_collection.create_index(
                [("final_decision", 1), ("created_at", -1)]
            )
            # P3-trace: índices para correlação distribuída por trace context
            await self.consensus_collection.create_index("trace_id")
            await self.consensus_collection.create_index("span_id")

            # Índices para explicabilidade
            await self.explainability_collection.create_index("token", unique=True)
            await self.explainability_collection.create_index("timestamp")

            logger.info("Índices MongoDB criados/verificados com sucesso")
        except Exception as e:
            # Índices podem já existir, especialmente em ambiente multi-worker
            logger.warning(
                "Aviso ao criar índices MongoDB (podem já existir)", error=str(e)
            )

    async def save_consensus_decision(self, decision: ConsolidatedDecision):
        """
        Salva decisão consolidada no ledger.

        Após salvar com sucesso, invalida caches relacionados.
        """
        # Usar model_dump com mode='json' para garantir serialização correta de enums
        # Isso converte DecisionType.APPROVE para "approve" automaticamente
        document = decision.model_dump(mode="json")
        document["_id"] = decision.decision_id
        document["immutable"] = True

        try:
            await self.consensus_collection.insert_one(document)
            logger.info(
                "Decisão consolidada salva",
                decision_id=decision.decision_id,
                hash=decision.hash,
            )

            # Invalidar caches relacionados (cache-aside pattern)
            if self.cache_service and self.config.enable_cache:
                await self.cache_service.invalidate_consensus_decision(
                    decision.decision_id
                )
                await self.cache_service.invalidate_plan_approval(decision.plan_id)

        except DuplicateKeyError:
            logger.warning(
                "Decisão já existe no ledger", decision_id=decision.decision_id
            )
            raise

    async def get_decision(self, decision_id: str) -> Optional[dict]:
        """
        Consulta decisão por ID com cache-aside.

        Cache-aside workflow:
        1. Check cache
        2. Cache miss → fetch from MongoDB
        3. Write to cache
        """
        # Se cache service disponível, usar cache-aside
        if self.cache_service and self.config.enable_cache:
            return await self.cache_service.get_consensus_decision(
                decision_id,
                db_fetcher=lambda: self._fetch_decision_from_db(decision_id),
            )

        # Fallback para MongoDB direto
        return await self._fetch_decision_from_db(decision_id)

    async def _fetch_decision_from_db(self, decision_id: str) -> Optional[dict]:
        """Busca decisão diretamente do MongoDB (sem cache)"""
        return await self.consensus_collection.find_one({"decision_id": decision_id})

    async def get_decision_by_plan(self, plan_id: str) -> Optional[dict]:
        """
        Consulta decisão por plan_id com cache-aside.

        Cache-aside workflow:
        1. Check cache
        2. Cache miss → fetch from MongoDB
        3. Write to cache
        """
        # Se cache service disponível, usar cache-aside
        if self.cache_service and self.config.enable_cache:
            return await self.cache_service.get_plan_approval(
                plan_id,
                db_fetcher=lambda: self._fetch_decision_by_plan_from_db(plan_id),
            )

        # Fallback para MongoDB direto
        return await self._fetch_decision_by_plan_from_db(plan_id)

    async def _fetch_decision_by_plan_from_db(self, plan_id: str) -> Optional[dict]:
        """Busca decisão por plan diretamente do MongoDB (sem cache)"""
        return await self.consensus_collection.find_one({"plan_id": plan_id})

    async def verify_integrity(self, decision_id: str) -> bool:
        """Verifica integridade de decisão"""
        decision = await self.get_decision(decision_id)
        if not decision:
            return False

        # Reconstruir ConsolidatedDecision e recalcular hash
        stored_hash = decision.pop("hash", None)
        decision_obj = ConsolidatedDecision(**decision)
        calculated_hash = decision_obj.calculate_hash()

        return calculated_hash == stored_hash

    async def close(self):
        """Fechar cliente"""
        if self.client:
            self.client.close()
            logger.info("MongoDB client fechado")
