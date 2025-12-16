"""
GuardrailEnforcer - Serviço para enforcement de guardrails éticos e de compliance.

Responsável por:
- Guardrails éticos de IA (bias, privacy, explainability)
- Guardrails de compliance (data residency, audit trail, encryption)
- Guardrails operacionais (blast radius, rollback plans, testing)
- Guardrails de custo (resource limits, cost thresholds)
"""

from typing import List, Dict, Optional
import structlog
from datetime import datetime

from neural_hive_observability import get_tracer

from src.models.security_validation import (
    GuardrailViolation,
    ViolationType,
    Severity
)

logger = structlog.get_logger(__name__)
tracer = get_tracer(__name__)


class GuardrailEnforcer:
    """
    Enforcer de guardrails de segurança, compliance e ética.
    """

    def __init__(
        self,
        opa_client,
        mongodb_client,
        redis_client,
        mode: str = "BLOCKING"
    ):
        """
        Inicializa o GuardrailEnforcer.

        Args:
            opa_client: Cliente OPA para políticas
            mongodb_client: Cliente MongoDB para persistência
            redis_client: Cliente Redis para cache
            mode: Modo de enforcement (BLOCKING ou ADVISORY)
        """
        self.opa_client = opa_client
        self.mongodb = mongodb_client
        self.redis_client = redis_client
        self.mode = mode  # BLOCKING ou ADVISORY

    async def enforce_guardrails(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Enforça todos os guardrails no ticket.

        Args:
            ticket: ExecutionTicket

        Returns:
            Lista de violações de guardrails
        """
        ticket_id = ticket.get("ticket_id", "unknown")
        logger.info(
            "guardrail_enforcer.enforcing",
            ticket_id=ticket_id,
            mode=self.mode
        )

        with tracer.start_as_current_span("enforce_guardrails") as span:
            span.set_attribute("neural.hive.ticket.id", ticket_id)
            violations: List[GuardrailViolation] = []

            # 1. Ethical AI Guardrails
            violations.extend(await self._check_bias_risk(ticket))
            violations.extend(await self._check_privacy_compliance(ticket))
            violations.extend(await self._check_explainability(ticket))

            # 2. Compliance Guardrails
            violations.extend(await self._check_data_residency(ticket))
            violations.extend(await self._check_audit_trail(ticket))
            violations.extend(await self._check_encryption(ticket))

            # 3. Operational Guardrails
            violations.extend(await self._check_blast_radius(ticket))
            violations.extend(await self._check_rollback_plan(ticket))
            violations.extend(await self._check_testing_coverage(ticket))

            # 4. Cost Guardrails
            violations.extend(await self._check_resource_limits(ticket))
            violations.extend(await self._check_cost_threshold(ticket))

            # Persistir violations para análise
            if violations:
                await self._persist_violations(ticket_id, violations)

            span.set_attribute("neural.hive.validation.result", "violations" if violations else "clean")
            span.set_attribute("neural.hive.validation.violations", len(violations))

            logger.info(
                "guardrail_enforcer.complete",
                ticket_id=ticket_id,
                violations_count=len(violations),
                mode=self.mode
            )

            return violations

    # ===== ETHICAL AI GUARDRAILS =====

    async def _check_bias_risk(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Verifica risco de bias em modelos ML.

        Args:
            ticket: ExecutionTicket

        Returns:
            Violações de bias risk
        """
        violations = []

        try:
            task_type = ticket.get("task_type", "")
            parameters = ticket.get("parameters", {})

            # Detectar uso de modelos ML
            uses_ml_model = (
                "model" in parameters or
                "ml_model" in parameters or
                task_type in ["ML_TRAINING", "ML_INFERENCE"]
            )

            if uses_ml_model:
                # Verificar se bias testing foi realizado
                has_bias_testing = parameters.get("bias_testing_completed", False)

                if not has_bias_testing:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.ETHICAL_CONCERN,
                            severity=Severity.HIGH,
                            description="Modelo ML sem bias testing",
                            remediation_suggestion="Executar bias testing antes de deploy",
                            detected_by="BiasRiskGuardrail",
                            evidence={
                                "task_type": task_type,
                                "model": parameters.get("model", "unknown")
                            }
                        )
                    )

        except Exception as e:
            logger.warning("guardrail_enforcer.bias_check_failed", error=str(e))

        return violations

    async def _check_privacy_compliance(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Valida compliance com GDPR/LGPD para dados pessoais.

        Args:
            ticket: ExecutionTicket

        Returns:
            Violações de privacy compliance
        """
        violations = []

        try:
            parameters = ticket.get("parameters", {})
            data_classification = parameters.get("data_classification", "")

            # Verificar se processa dados pessoais
            processes_personal_data = (
                data_classification in ["PII", "PERSONAL", "SENSITIVE"]
            )

            if processes_personal_data:
                # Verificar consentimento
                has_consent = parameters.get("user_consent", False)

                if not has_consent:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.COMPLIANCE_BREACH,
                            severity=Severity.CRITICAL,
                            description="Processamento de dados pessoais sem consentimento",
                            remediation_suggestion="Obter consentimento do usuário (GDPR/LGPD)",
                            detected_by="PrivacyComplianceGuardrail",
                            evidence={
                                "data_classification": data_classification
                            }
                        )
                    )

                # Verificar data retention policy
                has_retention_policy = parameters.get("data_retention_policy")

                if not has_retention_policy:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.COMPLIANCE_BREACH,
                            severity=Severity.MEDIUM,
                            description="Dados pessoais sem política de retenção",
                            remediation_suggestion="Definir data retention policy",
                            detected_by="PrivacyComplianceGuardrail",
                            evidence={
                                "data_classification": data_classification
                            }
                        )
                    )

        except Exception as e:
            logger.warning("guardrail_enforcer.privacy_check_failed", error=str(e))

        return violations

    async def _check_explainability(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Requer explicabilidade para decisões críticas.

        Args:
            ticket: ExecutionTicket

        Returns:
            Violações de explainability
        """
        violations = []

        try:
            task_type = ticket.get("task_type", "")
            parameters = ticket.get("parameters", {})
            is_critical_decision = parameters.get("is_critical_decision", False)

            # Decisões críticas requerem explicabilidade
            if is_critical_decision:
                has_explainability = parameters.get("explainability_enabled", False)

                if not has_explainability:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.ETHICAL_CONCERN,
                            severity=Severity.HIGH,
                            description="Decisão crítica sem explicabilidade",
                            remediation_suggestion="Habilitar explicabilidade (SHAP, LIME, etc)",
                            detected_by="ExplainabilityGuardrail",
                            evidence={
                                "task_type": task_type,
                                "is_critical_decision": str(is_critical_decision)
                            }
                        )
                    )

        except Exception as e:
            logger.warning("guardrail_enforcer.explainability_check_failed", error=str(e))

        return violations

    # ===== COMPLIANCE GUARDRAILS =====

    async def _check_data_residency(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Valida data residency requirements.

        Args:
            ticket: ExecutionTicket

        Returns:
            Violações de data residency
        """
        violations = []

        try:
            parameters = ticket.get("parameters", {})
            data_region = parameters.get("data_region", "")
            target_region = parameters.get("target_region", "")

            # Dados EU devem ficar na EU (GDPR)
            if data_region == "EU" and target_region not in ["EU", "eu-west-1", "eu-central-1"]:
                violations.append(
                    GuardrailViolation(
                        violation_type=ViolationType.COMPLIANCE_BREACH,
                        severity=Severity.CRITICAL,
                        description=f"Dados EU sendo transferidos para {target_region}",
                        remediation_suggestion="Manter dados EU na região EU (GDPR compliance)",
                        detected_by="DataResidencyGuardrail",
                        evidence={
                            "data_region": data_region,
                            "target_region": target_region
                        }
                    )
                )

        except Exception as e:
            logger.warning("guardrail_enforcer.data_residency_check_failed", error=str(e))

        return violations

    async def _check_audit_trail(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Garante auditabilidade de ações críticas.

        Args:
            ticket: ExecutionTicket

        Returns:
            Violações de audit trail
        """
        violations = []

        try:
            task_type = ticket.get("task_type", "")
            parameters = ticket.get("parameters", {})

            # Ações críticas requerem audit trail
            critical_actions = ["DEPLOY", "DELETE", "ROLLBACK", "SCALE"]

            if task_type in critical_actions:
                has_audit_trail = parameters.get("audit_trail_enabled", True)

                if not has_audit_trail:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.COMPLIANCE_BREACH,
                            severity=Severity.HIGH,
                            description=f"Ação crítica '{task_type}' sem audit trail",
                            remediation_suggestion="Habilitar audit trail para ações críticas",
                            detected_by="AuditTrailGuardrail",
                            evidence={
                                "task_type": task_type
                            }
                        )
                    )

        except Exception as e:
            logger.warning("guardrail_enforcer.audit_trail_check_failed", error=str(e))

        return violations

    async def _check_encryption(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Valida encryption at rest/in transit para dados sensíveis.

        Args:
            ticket: ExecutionTicket

        Returns:
            Violações de encryption
        """
        violations = []

        try:
            parameters = ticket.get("parameters", {})
            data_classification = parameters.get("data_classification", "")

            # Dados sensíveis requerem encryption
            requires_encryption = data_classification in [
                "CONFIDENTIAL", "RESTRICTED", "PII", "SENSITIVE"
            ]

            if requires_encryption:
                encryption_at_rest = parameters.get("encryption_at_rest", False)
                encryption_in_transit = parameters.get("encryption_in_transit", False)

                if not encryption_at_rest:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.COMPLIANCE_BREACH,
                            severity=Severity.CRITICAL,
                            description="Dados sensíveis sem encryption at rest",
                            remediation_suggestion="Habilitar encryption at rest",
                            detected_by="EncryptionGuardrail",
                            evidence={
                                "data_classification": data_classification
                            }
                        )
                    )

                if not encryption_in_transit:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.COMPLIANCE_BREACH,
                            severity=Severity.HIGH,
                            description="Dados sensíveis sem encryption in transit",
                            remediation_suggestion="Habilitar TLS/mTLS",
                            detected_by="EncryptionGuardrail",
                            evidence={
                                "data_classification": data_classification
                            }
                        )
                    )

        except Exception as e:
            logger.warning("guardrail_enforcer.encryption_check_failed", error=str(e))

        return violations

    # ===== OPERATIONAL GUARDRAILS =====

    async def _check_blast_radius(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Limita blast radius de mudanças.

        Args:
            ticket: ExecutionTicket

        Returns:
            Violações de blast radius
        """
        violations = []

        try:
            task_type = ticket.get("task_type", "")
            parameters = ticket.get("parameters", {})

            if task_type == "DEPLOY":
                affected_percentage = parameters.get("affected_percentage", 1.0)
                max_blast_radius = 0.1  # 10% max

                if affected_percentage > max_blast_radius:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.POLICY_VIOLATION,
                            severity=Severity.HIGH,
                            description=f"Blast radius muito grande: {affected_percentage * 100}%",
                            remediation_suggestion=f"Limitar blast radius a {max_blast_radius * 100}%",
                            detected_by="BlastRadiusGuardrail",
                            evidence={
                                "affected_percentage": str(affected_percentage),
                                "max_allowed": str(max_blast_radius)
                            }
                        )
                    )

        except Exception as e:
            logger.warning("guardrail_enforcer.blast_radius_check_failed", error=str(e))

        return violations

    async def _check_rollback_plan(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Requer rollback plan para mudanças de alto risco.

        Args:
            ticket: ExecutionTicket

        Returns:
            Violações de rollback plan
        """
        violations = []

        try:
            task_type = ticket.get("task_type", "")
            parameters = ticket.get("parameters", {})
            environment = ticket.get("environment", "development")

            # Mudanças em produção requerem rollback plan
            if task_type in ["DEPLOY", "SCALE", "MIGRATE"] and environment == "production":
                has_rollback_plan = parameters.get("rollback_plan", False)

                if not has_rollback_plan:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.POLICY_VIOLATION,
                            severity=Severity.HIGH,
                            description=f"Mudança em produção sem rollback plan",
                            remediation_suggestion="Definir rollback plan antes de executar",
                            detected_by="RollbackPlanGuardrail",
                            evidence={
                                "task_type": task_type,
                                "environment": environment
                            }
                        )
                    )

        except Exception as e:
            logger.warning("guardrail_enforcer.rollback_plan_check_failed", error=str(e))

        return violations

    async def _check_testing_coverage(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Valida que testes foram executados antes de deploy.

        Args:
            ticket: ExecutionTicket

        Returns:
            Violações de testing coverage
        """
        violations = []

        try:
            task_type = ticket.get("task_type", "")
            parameters = ticket.get("parameters", {})

            if task_type == "DEPLOY":
                tests_passed = parameters.get("tests_passed", False)
                test_coverage = parameters.get("test_coverage", 0)
                min_coverage = 80  # 80% mínimo

                if not tests_passed:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.POLICY_VIOLATION,
                            severity=Severity.HIGH,
                            description="Deploy sem testes passando",
                            remediation_suggestion="Executar e passar todos os testes",
                            detected_by="TestingCoverageGuardrail",
                            evidence={
                                "tests_passed": str(tests_passed)
                            }
                        )
                    )

                if test_coverage < min_coverage:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.POLICY_VIOLATION,
                            severity=Severity.MEDIUM,
                            description=f"Coverage baixo: {test_coverage}% (mínimo {min_coverage}%)",
                            remediation_suggestion="Aumentar test coverage",
                            detected_by="TestingCoverageGuardrail",
                            evidence={
                                "test_coverage": str(test_coverage),
                                "min_coverage": str(min_coverage)
                            }
                        )
                    )

        except Exception as e:
            logger.warning("guardrail_enforcer.testing_coverage_check_failed", error=str(e))

        return violations

    # ===== COST GUARDRAILS =====

    async def _check_resource_limits(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Valida resource requests/limits.

        Args:
            ticket: ExecutionTicket

        Returns:
            Violações de resource limits
        """
        violations = []

        try:
            parameters = ticket.get("parameters", {})
            resources = parameters.get("resources", {})

            # Verificar se recursos estão definidos
            if not resources:
                violations.append(
                    GuardrailViolation(
                        violation_type=ViolationType.POLICY_VIOLATION,
                        severity=Severity.MEDIUM,
                        description="Resource limits não definidos",
                        remediation_suggestion="Definir requests e limits de CPU/memória",
                        detected_by="ResourceLimitsGuardrail",
                        evidence={}
                    )
                )
            else:
                # Verificar se limits estão razoáveis
                cpu_limit = resources.get("cpu_limit", 0)
                memory_limit = resources.get("memory_limit", 0)

                # Limits muito altos
                if cpu_limit > 8:  # 8 cores
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.POLICY_VIOLATION,
                            severity=Severity.MEDIUM,
                            description=f"CPU limit muito alto: {cpu_limit} cores",
                            remediation_suggestion="Reduzir CPU limit ou justificar necessidade",
                            detected_by="ResourceLimitsGuardrail",
                            evidence={"cpu_limit": str(cpu_limit)}
                        )
                    )

                if memory_limit > 16384:  # 16GB
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.POLICY_VIOLATION,
                            severity=Severity.MEDIUM,
                            description=f"Memory limit muito alto: {memory_limit}Mi",
                            remediation_suggestion="Reduzir memory limit ou justificar necessidade",
                            detected_by="ResourceLimitsGuardrail",
                            evidence={"memory_limit": str(memory_limit)}
                        )
                    )

        except Exception as e:
            logger.warning("guardrail_enforcer.resource_limits_check_failed", error=str(e))

        return violations

    async def _check_cost_threshold(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Bloqueia mudanças que excedem budget threshold.

        Args:
            ticket: ExecutionTicket

        Returns:
            Violações de cost threshold
        """
        violations = []

        try:
            parameters = ticket.get("parameters", {})
            estimated_cost = parameters.get("estimated_cost_usd", 0)
            cost_threshold = 1000  # $1000 USD threshold

            if estimated_cost > cost_threshold:
                violations.append(
                    GuardrailViolation(
                        violation_type=ViolationType.POLICY_VIOLATION,
                        severity=Severity.HIGH,
                        description=f"Custo estimado (${estimated_cost}) excede threshold (${cost_threshold})",
                        remediation_suggestion="Obter aprovação de budget ou reduzir escopo",
                        detected_by="CostThresholdGuardrail",
                        evidence={
                            "estimated_cost_usd": str(estimated_cost),
                            "cost_threshold_usd": str(cost_threshold)
                        }
                    )
                )

        except Exception as e:
            logger.warning("guardrail_enforcer.cost_threshold_check_failed", error=str(e))

        return violations

    async def _persist_violations(
        self,
        ticket_id: str,
        violations: List[GuardrailViolation]
    ) -> None:
        """
        Persiste violations no MongoDB para análise de tendências.

        Args:
            ticket_id: ID do ticket
            violations: Lista de violações
        """
        try:
            collection = self.mongodb.guardrail_violations

            for violation in violations:
                document = violation.to_dict()
                document["ticket_id"] = ticket_id
                document["created_at"] = datetime.utcnow().isoformat()

                await collection.insert_one(document)

        except Exception as e:
            logger.error(
                "guardrail_enforcer.persist_violations_failed",
                ticket_id=ticket_id,
                error=str(e)
            )
