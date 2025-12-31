"""
SecurityValidator - Serviço para validação proativa de segurança de ExecutionTickets.

Responsável por:
- Validar políticas OPA
- Validar RBAC e permissões
- Escanear secrets expostos
- Validar compliance organizacional
- Calcular risk assessment
"""

from typing import List, Dict, Optional, Any
import structlog
from datetime import datetime
import json

from neural_hive_observability import get_tracer

from src.models.security_validation import (
    SecurityValidation,
    GuardrailViolation,
    ViolationType,
    ValidationStatus,
    ValidatorType,
    Severity,
    RiskAssessment
)

logger = structlog.get_logger(__name__)
tracer = get_tracer()


class SecurityValidator:
    """
    Validador proativo de segurança para ExecutionTickets.
    """

    def __init__(
        self,
        opa_client,
        k8s_client,
        vault_client,
        trivy_client,
        redis_client,
        mongodb_client,
        settings
    ):
        """
        Inicializa o SecurityValidator.

        Args:
            opa_client: Cliente OPA para validação de políticas
            k8s_client: Cliente Kubernetes para validação RBAC
            vault_client: Cliente Vault para validação de secrets
            trivy_client: Cliente Trivy para scanning de secrets
            redis_client: Cliente Redis para cache
            mongodb_client: Cliente MongoDB para persistência
            settings: Instância de Settings com configurações
        """
        self.opa_client = opa_client
        self.k8s_client = k8s_client
        self.vault_client = vault_client
        self.trivy_client = trivy_client
        self.redis_client = redis_client
        self.mongodb = mongodb_client
        self.settings = settings
        self._cache_ttl = 300  # 5 minutos

        # Thresholds de risco configuráveis
        self.risk_score_threshold_auto_approve = settings.risk_score_threshold_auto_approve
        self.risk_score_threshold_auto_reject = settings.risk_score_threshold_auto_reject
        self.require_approval_for_production = settings.require_approval_for_production
        self.require_approval_for_critical_risk = settings.require_approval_for_critical_risk

    async def validate_ticket(self, ticket: dict) -> SecurityValidation:
        """
        Valida um ExecutionTicket completamente.

        Args:
            ticket: Dicionário com dados do ExecutionTicket

        Returns:
            SecurityValidation com resultado da validação
        """
        ticket_id = ticket.get("ticket_id", "unknown")
        logger.info(
            "security_validator.validating_ticket",
            ticket_id=ticket_id,
            task_type=ticket.get("task_type")
        )

        with tracer.start_as_current_span("validate_security") as span:
            span.set_attribute("neural.hive.ticket.id", ticket_id)
            if ticket.get("plan_id"):
                span.set_attribute("neural.hive.plan.id", ticket.get("plan_id"))

            # Verificar cache
            cached = await self._get_cached_validation(ticket_id)
            if cached:
                span.set_attribute("neural.hive.validation.result", cached.validation_status.value)
                span.set_attribute("neural.hive.risk.score", cached.risk_assessment.risk_score)
                logger.info("security_validator.cache_hit", ticket_id=ticket_id)
                return cached

            violations: List[GuardrailViolation] = []

            # Executar validações em paralelo quando possível
            try:
                # 1. Validar políticas OPA
                opa_violations = await self._validate_opa_policies(ticket)
                violations.extend(opa_violations)

                # 2. Validar RBAC
                rbac_violations = await self._validate_rbac(ticket)
                violations.extend(rbac_violations)

                # 3. Escanear secrets (se Trivy disponível)
                if self.trivy_client:
                    secret_violations = await self._scan_secrets(ticket)
                    violations.extend(secret_violations)

                # 4. Validar compliance
                compliance_violations = await self._validate_compliance(ticket)
                violations.extend(compliance_violations)

            except Exception as e:
                logger.error(
                    "security_validator.validation_error",
                    ticket_id=ticket_id,
                    error=str(e)
                )
                # Criar violação de erro interno
                violations.append(
                    GuardrailViolation(
                        violation_type=ViolationType.POLICY_VIOLATION,
                        severity=Severity.HIGH,
                        description=f"Erro durante validação: {str(e)}",
                        remediation_suggestion="Verificar logs do Guard Agent",
                        detected_by="SecurityValidator",
                        evidence={"error": str(e)}
                    )
                )

            # 5. Calcular risk assessment
            risk_assessment = await self._calculate_risk_assessment(violations, ticket)
            span.set_attribute("neural.hive.risk.score", risk_assessment.risk_score)

            # Determinar status da validação
            validation_status = self._determine_validation_status(
                risk_assessment, violations
            )
            span.set_attribute("neural.hive.validation.result", validation_status.value)

            # Criar SecurityValidation
            validation = SecurityValidation(
                ticket_id=ticket_id,
                plan_id=ticket.get("plan_id", "unknown"),
                intent_id=ticket.get("intent_id", "unknown"),
                correlation_id=ticket.get("correlation_id", "unknown"),
                trace_id=ticket.get("trace_id"),
                span_id=ticket.get("span_id"),
                validation_status=validation_status,
                validator_type=ValidatorType.GUARDRAIL,  # Validação completa
                violations=violations,
                risk_assessment=risk_assessment,
                approval_required=validation_status == ValidationStatus.REQUIRES_APPROVAL,
                approval_reason=self._get_approval_reason(risk_assessment, violations),
                metadata={
                    "validator_version": "1.0.0",
                    "ticket_type": ticket.get("task_type", "unknown"),
                    "security_level": ticket.get("security_level", "unknown")
                }
            )

            # Recalcular hash após construção completa
            validation.refresh_hash()

            # Cachear validação
            await self._cache_validation(validation)

            # Persistir no MongoDB
            await self._persist_validation(validation)

            logger.info(
                "security_validator.validation_complete",
                ticket_id=ticket_id,
                status=validation_status.value,
                violations_count=len(violations),
                risk_score=risk_assessment.risk_score
            )

            return validation

    async def _validate_opa_policies(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Valida ticket contra políticas OPA.

        Args:
            ticket: ExecutionTicket

        Returns:
            Lista de violações detectadas
        """
        violations = []

        try:
            # Consultar OPA com policy path para execution tickets
            policy_input = {
                "ticket": ticket,
                "metadata": {
                    "security_level": ticket.get("security_level"),
                    "required_capabilities": ticket.get("required_capabilities", []),
                    "parameters": ticket.get("parameters", {})
                }
            }

            result = await self.opa_client.evaluate_policy(
                "data.guard.execution_ticket",
                policy_input
            )

            if not result.get("allowed", True):
                violations.append(
                    GuardrailViolation(
                        violation_type=ViolationType.POLICY_VIOLATION,
                        severity=Severity.HIGH,
                        description=result.get("reason", "Ticket viola políticas OPA"),
                        remediation_suggestion=result.get(
                            "remediation",
                            "Ajustar ticket para cumprir políticas de segurança"
                        ),
                        detected_by="OPAValidator",
                        evidence={
                            "policy_path": "data.guard.execution_ticket",
                            "opa_response": json.dumps(result)
                        }
                    )
                )

        except Exception as e:
            logger.warning(
                "security_validator.opa_validation_failed",
                error=str(e),
                ticket_id=ticket.get("ticket_id")
            )

        return violations

    async def _validate_rbac(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Valida permissões RBAC para o ticket.

        Args:
            ticket: ExecutionTicket

        Returns:
            Lista de violações RBAC
        """
        violations = []

        try:
            service_account = ticket.get("service_account", "default")
            namespace = ticket.get("namespace", "default")
            required_capabilities = ticket.get("required_capabilities", [])

            # Verificar se service account existe
            sa_exists = await self._check_service_account_exists(
                service_account, namespace
            )

            if not sa_exists:
                violations.append(
                    GuardrailViolation(
                        violation_type=ViolationType.RBAC_VIOLATION,
                        severity=Severity.HIGH,
                        description=f"Service account '{service_account}' não existe no namespace '{namespace}'",
                        remediation_suggestion="Criar service account ou usar um existente",
                        detected_by="RBACValidator",
                        evidence={
                            "service_account": service_account,
                            "namespace": namespace
                        }
                    )
                )

            # Verificar permissões necessárias
            for capability in required_capabilities:
                has_permission = await self._check_rbac_permission(
                    service_account, namespace, capability
                )

                if not has_permission:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.RBAC_VIOLATION,
                            severity=Severity.HIGH,
                            description=f"Service account sem permissão para '{capability}'",
                            remediation_suggestion=f"Adicionar permissão '{capability}' ao service account",
                            detected_by="RBACValidator",
                            evidence={
                                "service_account": service_account,
                                "capability": capability
                            }
                        )
                    )

            # Detectar privilege escalation
            if self._is_privilege_escalation_attempt(ticket):
                violations.append(
                    GuardrailViolation(
                        violation_type=ViolationType.RBAC_VIOLATION,
                        severity=Severity.CRITICAL,
                        description="Tentativa de escalação de privilégios detectada",
                        remediation_suggestion="Remover capacidades privilegiadas desnecessárias",
                        detected_by="RBACValidator",
                        evidence={"capabilities": required_capabilities}
                    )
                )

        except Exception as e:
            logger.warning(
                "security_validator.rbac_validation_failed",
                error=str(e),
                ticket_id=ticket.get("ticket_id")
            )

        return violations

    async def _scan_secrets(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Escaneia ticket em busca de secrets expostos.

        Args:
            ticket: ExecutionTicket

        Returns:
            Lista de violações de secrets
        """
        violations = []

        try:
            parameters = ticket.get("parameters", {})
            ticket_id = ticket.get("ticket_id", "unknown")

            # Escanear parameters com Trivy
            secrets_found = await self.trivy_client.scan_parameters(parameters)

            for secret in secrets_found:
                violations.append(
                    GuardrailViolation(
                        violation_type=ViolationType.SECRET_EXPOSED,
                        severity=Severity.CRITICAL,
                        description=f"Secret exposto: {secret.get('type', 'unknown')}",
                        remediation_suggestion="Remover credenciais hardcoded e usar Vault",
                        detected_by="TrivyScanner",
                        evidence={
                            "secret_type": secret.get("type"),
                            "location": secret.get("match", ""),
                            "line": str(secret.get("line", 0))
                        }
                    )
                )

            # Validar acesso a Vault se parâmetros contiverem caminhos de secrets
            if self.vault_client:
                vault_paths = parameters.get("vault_secret_paths", [])
                for vault_path in vault_paths:
                    try:
                        has_access = await self.vault_client.validate_secret_access(
                            ticket_id=ticket_id,
                            secret_path=vault_path
                        )

                        if not has_access:
                            violations.append(
                                GuardrailViolation(
                                    violation_type=ViolationType.RBAC_VIOLATION,
                                    severity=Severity.HIGH,
                                    description=f"Sem permissão para acessar secret em '{vault_path}'",
                                    remediation_suggestion="Verificar políticas Vault para este service account",
                                    detected_by="VaultValidator",
                                    evidence={
                                        "vault_path": vault_path,
                                        "ticket_id": ticket_id
                                    }
                                )
                            )

                        # Auditar tentativa de acesso
                        await self.vault_client.audit_secret_access(
                            ticket_id=ticket_id,
                            secret_path=vault_path,
                            action="read"
                        )

                    except Exception as e:
                        logger.warning(
                            "security_validator.vault_validation_failed",
                            error=str(e),
                            vault_path=vault_path,
                            ticket_id=ticket_id
                        )

        except Exception as e:
            logger.warning(
                "security_validator.secrets_scan_failed",
                error=str(e),
                ticket_id=ticket.get("ticket_id")
            )

        return violations

    async def _validate_compliance(self, ticket: dict) -> List[GuardrailViolation]:
        """
        Valida compliance organizacional do ticket.

        Args:
            ticket: ExecutionTicket

        Returns:
            Lista de violações de compliance
        """
        violations = []

        try:
            security_level = ticket.get("security_level", "INTERNAL")
            task_type = ticket.get("task_type", "unknown")
            environment = ticket.get("environment", "development")

            # Verificar se security_level é apropriado para o tipo de tarefa
            if task_type == "DEPLOY" and environment == "production":
                if security_level not in ["CONFIDENTIAL", "RESTRICTED"]:
                    violations.append(
                        GuardrailViolation(
                            violation_type=ViolationType.COMPLIANCE_BREACH,
                            severity=Severity.HIGH,
                            description="Deploy em produção requer security_level CONFIDENTIAL ou RESTRICTED",
                            remediation_suggestion="Aumentar security_level do ticket",
                            detected_by="ComplianceValidator",
                            evidence={
                                "current_security_level": security_level,
                                "required_security_level": "CONFIDENTIAL ou RESTRICTED"
                            }
                        )
                    )

            # Verificar se tarefa requer aprovação manual
            requires_manual_approval = (
                task_type == "DEPLOY" and environment == "production"
            ) or (
                task_type in ["DELETE", "ROLLBACK"]
            )

            if requires_manual_approval:
                violations.append(
                    GuardrailViolation(
                        violation_type=ViolationType.COMPLIANCE_BREACH,
                        severity=Severity.MEDIUM,
                        description=f"Tarefa '{task_type}' em '{environment}' requer aprovação manual",
                        remediation_suggestion="Solicitar aprovação antes de executar",
                        detected_by="ComplianceValidator",
                        evidence={
                            "task_type": task_type,
                            "environment": environment
                        }
                    )
                )

        except Exception as e:
            logger.warning(
                "security_validator.compliance_validation_failed",
                error=str(e),
                ticket_id=ticket.get("ticket_id")
            )

        return violations

    async def _calculate_risk_assessment(
        self,
        violations: List[GuardrailViolation],
        ticket: dict
    ) -> RiskAssessment:
        """
        Calcula avaliação de risco com base nas violações.

        Args:
            violations: Lista de violações detectadas
            ticket: ExecutionTicket

        Returns:
            RiskAssessment calculado
        """
        # Pesos por severidade
        severity_weights = {
            Severity.CRITICAL: 1.0,
            Severity.HIGH: 0.7,
            Severity.MEDIUM: 0.4,
            Severity.LOW: 0.1
        }

        # Calcular risk_score baseado em violações
        if not violations:
            risk_score = 0.0
            severity = Severity.LOW
            impact = "Nenhuma violação detectada"
        else:
            # Soma ponderada de violações
            total_weight = sum(
                severity_weights[v.severity] for v in violations
            )
            # Normalizar para 0-1
            risk_score = min(1.0, total_weight / len(violations))

            # Severidade máxima
            severity = max(violations, key=lambda v: severity_weights[v.severity]).severity

            # Análise de impacto
            critical_count = len([v for v in violations if v.severity == Severity.CRITICAL])
            high_count = len([v for v in violations if v.severity == Severity.HIGH])

            if critical_count > 0:
                impact = f"{critical_count} violação(ões) CRITICAL detectada(s)"
            elif high_count > 0:
                impact = f"{high_count} violação(ões) HIGH detectada(s)"
            else:
                impact = f"{len(violations)} violação(ões) detectada(s)"

        return RiskAssessment(
            risk_score=risk_score,
            severity=severity,
            impact=impact
        )

    def _determine_validation_status(
        self,
        risk_assessment: RiskAssessment,
        violations: List[GuardrailViolation]
    ) -> ValidationStatus:
        """
        Determina status da validação baseado no risco.

        Args:
            risk_assessment: Avaliação de risco
            violations: Violações detectadas

        Returns:
            ValidationStatus apropriado
        """
        # Auto-reject se risk_score > threshold ou há violações CRITICAL
        critical_violations = [
            v for v in violations if v.severity == Severity.CRITICAL
        ]
        if risk_assessment.risk_score > self.risk_score_threshold_auto_reject or critical_violations:
            return ValidationStatus.REJECTED

        # Requer aprovação se threshold_approve < risk_score < threshold_reject
        if self.risk_score_threshold_auto_approve < risk_assessment.risk_score < self.risk_score_threshold_auto_reject:
            return ValidationStatus.REQUIRES_APPROVAL

        # Auto-approve se risk_score < threshold_approve
        if risk_assessment.risk_score < self.risk_score_threshold_auto_approve:
            return ValidationStatus.APPROVED

        # Default: requer aprovação
        return ValidationStatus.REQUIRES_APPROVAL

    def _get_approval_reason(
        self,
        risk_assessment: RiskAssessment,
        violations: List[GuardrailViolation]
    ) -> Optional[str]:
        """
        Gera razão para aprovação manual se necessário.

        Args:
            risk_assessment: Avaliação de risco
            violations: Violações detectadas

        Returns:
            Razão para aprovação ou None
        """
        # Usar threshold configurável ao invés de valor hardcoded
        approval_threshold = self.risk_score_threshold_auto_reject * 0.89  # ~80% do threshold de rejeição

        if risk_assessment.risk_score > approval_threshold:
            return f"Risk score alto ({risk_assessment.risk_score:.2f})"

        critical_violations = [
            v for v in violations if v.severity == Severity.CRITICAL
        ]
        if critical_violations:
            return f"{len(critical_violations)} violação(ões) CRITICAL detectada(s)"

        if violations:
            return f"{len(violations)} violação(ões) detectada(s)"

        return None

    async def _check_service_account_exists(
        self,
        service_account: str,
        namespace: str
    ) -> bool:
        """
        Verifica se service account existe no namespace.

        Args:
            service_account: Nome do service account
            namespace: Namespace do Kubernetes

        Returns:
            True se service account existe
        """
        try:
            # Simplified check - would use K8s API in production
            return True
        except Exception:
            return False

    async def _check_rbac_permission(
        self,
        service_account: str,
        namespace: str,
        capability: str
    ) -> bool:
        """
        Verifica se service account tem permissão específica.

        Args:
            service_account: Nome do service account
            namespace: Namespace
            capability: Capacidade necessária

        Returns:
            True se tem permissão
        """
        try:
            # Simplified check - would use K8s RBAC API in production
            return True
        except Exception:
            return False

    def _is_privilege_escalation_attempt(self, ticket: dict) -> bool:
        """
        Detecta tentativas de escalação de privilégios.

        Args:
            ticket: ExecutionTicket

        Returns:
            True se detectar tentativa de escalação
        """
        required_capabilities = ticket.get("required_capabilities", [])

        # Capacidades privilegiadas
        privileged_caps = [
            "SYS_ADMIN",
            "NET_ADMIN",
            "SYS_PTRACE",
            "DAC_OVERRIDE"
        ]

        # Detectar se há capacidades privilegiadas desnecessárias
        has_privileged = any(cap in privileged_caps for cap in required_capabilities)

        return has_privileged

    async def _get_cached_validation(
        self,
        ticket_id: str
    ) -> Optional[SecurityValidation]:
        """
        Obtém validação do cache Redis.

        Args:
            ticket_id: ID do ticket

        Returns:
            SecurityValidation cacheada ou None
        """
        try:
            cache_key = f"security_validation:{ticket_id}"
            cached_data = await self.redis_client.get(cache_key)

            if cached_data:
                return SecurityValidation.from_avro_dict(json.loads(cached_data))

        except Exception as e:
            logger.warning("security_validator.cache_get_failed", error=str(e))

        return None

    async def _cache_validation(self, validation: SecurityValidation) -> None:
        """
        Cacheia validação no Redis.

        Args:
            validation: SecurityValidation para cachear
        """
        try:
            cache_key = f"security_validation:{validation.ticket_id}"
            cache_value = json.dumps(validation.to_avro_dict())

            await self.redis_client.setex(
                cache_key,
                self._cache_ttl,
                cache_value
            )

        except Exception as e:
            logger.warning("security_validator.cache_set_failed", error=str(e))

    async def _persist_validation(self, validation: SecurityValidation) -> None:
        """
        Persiste validação no MongoDB.

        Args:
            validation: SecurityValidation para persistir
        """
        try:
            collection = self.mongodb.security_validations

            await collection.insert_one(validation.to_avro_dict())

            logger.info(
                "security_validator.validation_persisted",
                validation_id=validation.validation_id,
                ticket_id=validation.ticket_id
            )

        except Exception as e:
            logger.error(
                "security_validator.persist_failed",
                validation_id=validation.validation_id,
                error=str(e)
            )
