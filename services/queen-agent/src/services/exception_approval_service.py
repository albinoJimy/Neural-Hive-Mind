import structlog
from datetime import datetime
from typing import List, Optional

from ..config import Settings
from ..models import ExceptionApproval, ExceptionType, ApprovalStatus
from ..clients import MongoDBClient
from neural_hive_resilience.circuit_breaker import CircuitBreakerError


logger = structlog.get_logger()


class ExceptionApprovalService:
    """Serviço de gestão de exceções a guardrails éticos"""

    # Pesos de risco por tipo de exceção
    EXCEPTION_RISK_WEIGHTS = {
        ExceptionType.SECURITY_OVERRIDE: 0.9,
        ExceptionType.COMPLIANCE_WAIVER: 0.7,
        ExceptionType.SLA_EXTENSION: 0.4,
        ExceptionType.RESOURCE_LIMIT_BYPASS: 0.5
    }

    def __init__(self, mongodb_client: MongoDBClient, settings: Settings):
        self.mongodb_client = mongodb_client
        self.settings = settings

    async def request_exception(self, exception: ExceptionApproval) -> str:
        """Criar solicitação de exceção"""
        try:
            # Avaliar risco automaticamente
            exception.risk_assessment = await self.evaluate_exception_risk(exception)

            # Salvar no MongoDB
            try:
                await self.mongodb_client.save_exception_approval(exception)
            except CircuitBreakerError:
                logger.warning(
                    "exception_approval_circuit_open",
                    exception_id=exception.exception_id
                )
                raise

            logger.info(
                "exception_requested",
                exception_id=exception.exception_id,
                exception_type=exception.exception_type.value,
                risk_score=exception.risk_assessment.risk_score
            )

            return exception.exception_id

        except Exception as e:
            logger.error("request_exception_failed", error=str(e))
            raise

    async def approve_exception(
        self,
        exception_id: str,
        decision_id: str,
        conditions: List[str]
    ) -> ExceptionApproval:
        """Aprovar exceção"""
        try:
            # Buscar exceção
            exception_data = await self.mongodb_client.get_exception_approval(exception_id)
            if not exception_data:
                raise ValueError(f"Exception {exception_id} not found")

            exception = ExceptionApproval(**exception_data)

            # Verificar se pode ser aprovada
            if exception.approval_status != ApprovalStatus.PENDING:
                raise ValueError(f"Exception already {exception.approval_status.value}")

            if exception.is_expired():
                raise ValueError("Exception has expired")

            # Aprovar
            exception.approve(decision_id, conditions)

            # Atualizar no MongoDB
            try:
                await self.mongodb_client.update_exception_status(exception_id, ApprovalStatus.APPROVED)
            except CircuitBreakerError:
                logger.warning(
                    "exception_status_update_circuit_open",
                    exception_id=exception_id,
                    decision_id=decision_id
                )
                raise

            logger.info(
                "exception_approved",
                exception_id=exception_id,
                decision_id=decision_id,
                conditions_count=len(conditions)
            )

            return exception

        except Exception as e:
            logger.error("approve_exception_failed", exception_id=exception_id, error=str(e))
            raise

    async def reject_exception(self, exception_id: str, reason: str) -> ExceptionApproval:
        """Rejeitar exceção"""
        try:
            exception_data = await self.mongodb_client.get_exception_approval(exception_id)
            if not exception_data:
                raise ValueError(f"Exception {exception_id} not found")

            exception = ExceptionApproval(**exception_data)

            # Rejeitar
            exception.reject(reason)

            # Atualizar no MongoDB
            try:
                await self.mongodb_client.update_exception_status(exception_id, ApprovalStatus.REJECTED)
            except CircuitBreakerError:
                logger.warning(
                    "exception_status_update_circuit_open",
                    exception_id=exception_id,
                    reason=reason
                )
                raise

            logger.info("exception_rejected", exception_id=exception_id, reason=reason)

            return exception

        except Exception as e:
            logger.error("reject_exception_failed", exception_id=exception_id, error=str(e))
            raise

    async def get_pending_exceptions(self) -> List[ExceptionApproval]:
        """Listar exceções pendentes"""
        try:
            # Buscar do MongoDB
            pending_data = await self.mongodb_client.list_exception_approvals(
                filters={'approval_status': ApprovalStatus.PENDING.value},
                limit=50
            )

            exceptions = [ExceptionApproval(**data) for data in pending_data]
            return exceptions

        except Exception as e:
            logger.error("get_pending_exceptions_failed", error=str(e))
            return []

    async def evaluate_exception_risk(self, exception: ExceptionApproval) -> 'RiskAssessment':
        """Avaliar risco de uma exceção"""
        from ..models import RiskAssessment

        try:
            risk_factors = []
            risk_score = 0.0

            # Fator 1: Tipo de exceção
            type_weight = self.EXCEPTION_RISK_WEIGHTS.get(exception.exception_type, 0.5)
            risk_score += type_weight * 0.4

            # Fator 2: Número de guardrails afetados
            guardrails_count = len(exception.guardrails_affected)
            if guardrails_count > 0:
                risk_factors.append(f'{guardrails_count}_guardrails_affected')
                risk_score += min(0.3, guardrails_count * 0.1)

            # Fator 3: Avaliação existente (se fornecida)
            if exception.risk_assessment and exception.risk_assessment.risk_score > 0:
                risk_score += exception.risk_assessment.risk_score * 0.3

            risk_score = min(1.0, risk_score)

            # Mitigações baseadas em risco
            mitigations = []
            if risk_score > 0.7:
                mitigations.append('require_additional_human_approval')
                mitigations.append('implement_enhanced_monitoring')
                mitigations.append('set_short_expiration_time')
            elif risk_score > 0.5:
                mitigations.append('implement_monitoring')
                mitigations.append('require_justification_review')

            return RiskAssessment(
                risk_score=risk_score,
                risk_factors=risk_factors,
                mitigations=mitigations
            )

        except Exception as e:
            logger.error("evaluate_exception_risk_failed", error=str(e))
            return RiskAssessment(risk_score=0.5, risk_factors=[], mitigations=[])

    async def check_exception_validity(self, exception_id: str) -> bool:
        """Verificar se exceção ainda é válida"""
        try:
            exception_data = await self.mongodb_client.get_exception_approval(exception_id)
            if not exception_data:
                return False

            exception = ExceptionApproval(**exception_data)

            return (
                exception.approval_status == ApprovalStatus.APPROVED and
                not exception.is_expired()
            )

        except Exception as e:
            logger.error("check_exception_validity_failed", error=str(e))
            return False

    async def revoke_exception(self, exception_id: str, reason: str) -> bool:
        """Revogar exceção aprovada"""
        try:
            exception_data = await self.mongodb_client.get_exception_approval(exception_id)
            if not exception_data:
                return False

            exception = ExceptionApproval(**exception_data)

            if exception.approval_status != ApprovalStatus.APPROVED:
                logger.warning("revoke_exception_invalid_status", exception_id=exception_id)
                return False

            # Atualizar status para REJECTED com razão de revogação
            exception.reject(f"Revoked: {reason}")
            await self.mongodb_client.update_exception_status(exception_id, ApprovalStatus.REJECTED)

            logger.info("exception_revoked", exception_id=exception_id, reason=reason)
            return True

        except Exception as e:
            logger.error("revoke_exception_failed", error=str(e))
            return False
