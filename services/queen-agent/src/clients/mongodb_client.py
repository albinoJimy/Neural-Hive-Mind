import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from neural_hive_resilience.circuit_breaker import MonitoredCircuitBreaker, CircuitBreakerError
from ..config import Settings
from ..models import StrategicDecision, ExceptionApproval, ApprovalStatus


logger = structlog.get_logger()


class MongoDBClient:
    """Cliente MongoDB assíncrono para persistência de decisões e exceções"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.ledger_collection: Optional[AsyncIOMotorCollection] = None
        self.exceptions_collection: Optional[AsyncIOMotorCollection] = None
        self.ledger_breaker: Optional[MonitoredCircuitBreaker] = None
        self.exceptions_breaker: Optional[MonitoredCircuitBreaker] = None
        self.circuit_breaker_enabled: bool = getattr(settings, "CIRCUIT_BREAKER_ENABLED", False)

    async def initialize(self) -> None:
        """Conectar ao MongoDB e criar índices"""
        try:
            self.client = AsyncIOMotorClient(
                self.settings.MONGODB_URI,
                maxPoolSize=self.settings.MONGODB_MAX_POOL_SIZE,
                minPoolSize=self.settings.MONGODB_MIN_POOL_SIZE
            )
            self.db = self.client[self.settings.MONGODB_DATABASE]
            self.ledger_collection = self.db[self.settings.MONGODB_COLLECTION_LEDGER]
            self.exceptions_collection = self.db[self.settings.MONGODB_COLLECTION_EXCEPTIONS]

            if self.circuit_breaker_enabled:
                self.ledger_breaker = MonitoredCircuitBreaker(
                    service_name=self.settings.SERVICE_NAME,
                    circuit_name="strategic_decision_persistence",
                    fail_max=self.settings.CIRCUIT_BREAKER_FAIL_MAX,
                    timeout_duration=self.settings.CIRCUIT_BREAKER_TIMEOUT,
                    recovery_timeout=self.settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
                    expected_exception=Exception
                )
                self.exceptions_breaker = MonitoredCircuitBreaker(
                    service_name=self.settings.SERVICE_NAME,
                    circuit_name="exception_approval_persistence",
                    fail_max=self.settings.CIRCUIT_BREAKER_FAIL_MAX,
                    timeout_duration=self.settings.CIRCUIT_BREAKER_TIMEOUT,
                    recovery_timeout=self.settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
                    expected_exception=Exception
                )

            # Criar índices para ledger
            await self.ledger_collection.create_index("decision_id", unique=True)
            await self.ledger_collection.create_index("decision_type")
            await self.ledger_collection.create_index([("created_at", -1)])
            await self.ledger_collection.create_index("triggered_by.source_id")
            await self.ledger_collection.create_index([("decision_type", 1), ("created_at", -1)])

            # Criar índices para exceptions
            await self.exceptions_collection.create_index("exception_id", unique=True)
            await self.exceptions_collection.create_index("approval_status")
            await self.exceptions_collection.create_index("plan_id")
            await self.exceptions_collection.create_index([("created_at", -1)])

            logger.info("mongodb_initialized", database=self.settings.MONGODB_DATABASE)

        except Exception as e:
            logger.error("mongodb_initialization_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Fechar conexão MongoDB"""
        if self.client:
            self.client.close()
            logger.info("mongodb_closed")

    async def save_strategic_decision(self, decision: StrategicDecision) -> None:
        """Persistir decisão estratégica no ledger com hash"""
        try:
            # Calcular hash se não existir
            if not decision.hash:
                decision.hash = decision.calculate_hash()

            # Converter para dict e salvar
            decision_dict = decision.to_avro_dict()
            await self._execute_with_breaker(
                self.ledger_breaker,
                self.ledger_collection.insert_one,
                decision_dict
            )

            logger.info(
                "strategic_decision_saved",
                decision_id=decision.decision_id,
                decision_type=decision.decision_type.value
            )

        except Exception as e:
            logger.error(
                "strategic_decision_save_failed",
                decision_id=decision.decision_id,
                error=str(e)
            )
            raise
        except CircuitBreakerError:
            logger.warning(
                "strategic_decision_circuit_open",
                decision_id=decision.decision_id
            )
            raise

    async def get_strategic_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Buscar decisão por ID"""
        try:
            decision = await self.ledger_collection.find_one({"decision_id": decision_id})
            return decision

        except Exception as e:
            logger.error("strategic_decision_get_failed", decision_id=decision_id, error=str(e))
            return None

    async def list_strategic_decisions(
        self,
        filters: Dict[str, Any],
        limit: int = 50,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """Listar decisões com filtros"""
        try:
            cursor = self.ledger_collection.find(filters).sort("created_at", -1).skip(skip).limit(limit)
            decisions = await cursor.to_list(length=limit)
            return decisions

        except Exception as e:
            logger.error("strategic_decisions_list_failed", error=str(e))
            return []

    async def get_recent_decisions(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Buscar decisões recentes"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        cutoff_ts = int(cutoff_time.timestamp() * 1000)

        return await self.list_strategic_decisions(
            filters={"created_at": {"$gte": cutoff_ts}},
            limit=100
        )

    async def save_exception_approval(self, approval: ExceptionApproval) -> None:
        """Persistir aprovação de exceção"""
        try:
            approval_dict = approval.to_dict()
            await self._execute_with_breaker(
                self.exceptions_breaker,
                self.exceptions_collection.insert_one,
                approval_dict
            )

            logger.info(
                "exception_approval_saved",
                exception_id=approval.exception_id,
                exception_type=approval.exception_type.value
            )

        except Exception as e:
            logger.error(
                "exception_approval_save_failed",
                exception_id=approval.exception_id,
                error=str(e)
            )
            raise
        except CircuitBreakerError:
            logger.warning(
                "exception_approval_circuit_open",
                exception_id=approval.exception_id
            )
            raise

    async def get_exception_approval(self, exception_id: str) -> Optional[Dict[str, Any]]:
        """Buscar aprovação de exceção"""
        try:
            exception = await self.exceptions_collection.find_one({"exception_id": exception_id})
            return exception

        except Exception as e:
            logger.error("exception_approval_get_failed", exception_id=exception_id, error=str(e))
            return None

    async def update_exception_status(self, exception_id: str, status: ApprovalStatus) -> bool:
        """Atualizar status de exceção"""
        try:
            result = await self.exceptions_collection.update_one(
                {"exception_id": exception_id},
                {"$set": {
                    "approval_status": status.value,
                    "updated_at": datetime.now().isoformat()
                }}
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(
                "exception_status_update_failed",
                exception_id=exception_id,
                error=str(e)
            )
            return False

    async def list_exception_approvals(
        self,
        filters: Dict[str, Any],
        limit: int = 50,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """Listar aprovações de exceções com filtros"""
        try:
            cursor = self.exceptions_collection.find(filters).sort("created_at", -1).skip(skip).limit(limit)
            exceptions = await cursor.to_list(length=limit)
            return exceptions

        except Exception as e:
            logger.error("exception_approvals_list_failed", error=str(e))
            return []

    async def _execute_with_breaker(self, breaker: Optional[MonitoredCircuitBreaker], func, *args, **kwargs):
        """Executa operação MongoDB protegida por circuit breaker quando habilitado."""
        if not self.circuit_breaker_enabled or breaker is None:
            return await func(*args, **kwargs)

        return await breaker.call_async(func, *args, **kwargs)
