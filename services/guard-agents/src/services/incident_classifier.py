"""Incident classification service for severity assessment (Fluxo E2)"""
from typing import Dict, Any, Optional, List
import structlog
from enum import Enum
from datetime import datetime, timezone

logger = structlog.get_logger()


class IncidentSeverity(str, Enum):
    """Níveis de severidade de incidentes"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IncidentImpact(str, Enum):
    """Tipos de impacto de incidentes"""
    SECURITY = "security"
    AVAILABILITY = "availability"
    PERFORMANCE = "performance"
    DATA_INTEGRITY = "data_integrity"
    COMPLIANCE = "compliance"


class IncidentClassifier:
    """Classifica severidade de incidentes seguindo Fluxo E2"""

    def __init__(self, mongodb_client=None):
        self.mongodb = mongodb_client
        self.classification_rules = self._initialize_classification_rules()
        self.severity_matrix = self._initialize_severity_matrix()

    def _initialize_classification_rules(self) -> Dict[str, Any]:
        """Carrega regras de classificação mapeadas a runbooks"""
        return {
            "threat_severity_mapping": {
                "unauthorized_access": IncidentSeverity.HIGH,
                "anomalous_behavior": IncidentSeverity.MEDIUM,
                "policy_violation": IncidentSeverity.MEDIUM,
                "resource_abuse": IncidentSeverity.MEDIUM,
                "data_exfiltration": IncidentSeverity.CRITICAL,
                "malicious_payload": IncidentSeverity.HIGH,
                "dos_attack": IncidentSeverity.CRITICAL,
            },
            "impact_weight": {
                IncidentImpact.SECURITY: 1.5,
                IncidentImpact.AVAILABILITY: 1.3,
                IncidentImpact.PERFORMANCE: 1.0,
                IncidentImpact.DATA_INTEGRITY: 1.4,
                IncidentImpact.COMPLIANCE: 1.2,
            },
            "confidence_threshold": 0.7,
        }

    def _initialize_severity_matrix(self) -> Dict[str, Dict[str, IncidentSeverity]]:
        """Matriz de severidade baseada em impacto e risco"""
        return {
            "security": {
                "critical": IncidentSeverity.CRITICAL,
                "high": IncidentSeverity.HIGH,
                "medium": IncidentSeverity.MEDIUM,
                "low": IncidentSeverity.LOW,
            },
            "availability": {
                "critical": IncidentSeverity.CRITICAL,
                "high": IncidentSeverity.HIGH,
                "medium": IncidentSeverity.MEDIUM,
                "low": IncidentSeverity.INFO,
            },
            "performance": {
                "critical": IncidentSeverity.HIGH,
                "high": IncidentSeverity.MEDIUM,
                "medium": IncidentSeverity.LOW,
                "low": IncidentSeverity.INFO,
            },
        }

    async def classify_incident(
        self, anomaly: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Classifica severidade de incidente (E2: Classificar severidade)

        Args:
            anomaly: Anomalia detectada pelo ThreatDetector
            context: Contexto adicional (histórico, recursos afetados, etc)

        Returns:
            Dict com classificação completa do incidente
        """
        try:
            threat_type = anomaly.get("threat_type", "unknown")
            base_severity = anomaly.get("severity", "medium")
            confidence = anomaly.get("confidence", 0.5)

            logger.info(
                "incident_classifier.classifying",
                threat_type=threat_type,
                base_severity=base_severity,
                confidence=confidence
            )

            # E2: Classificação mapeada a runbooks
            severity = await self._determine_severity(anomaly, context)
            impact = await self._assess_impact(anomaly, context)
            priority = await self._calculate_priority(severity, impact, confidence)
            runbook_id = await self._map_to_runbook(threat_type, severity)

            classification = {
                "incident_id": self._generate_incident_id(anomaly),
                "threat_type": threat_type,
                "severity": severity,
                "impact": impact,
                "priority": priority,
                "confidence": confidence,
                "runbook_id": runbook_id,
                "affected_resources": self._extract_affected_resources(anomaly, context),
                "business_impact": self._estimate_business_impact(severity, impact),
                "sla_breach_risk": self._assess_sla_risk(severity, impact),
                "requires_human_review": self._requires_human_review(confidence, severity),
                "classified_at": datetime.now(timezone.utc).isoformat(),
                "anomaly": anomaly,
                "context": context or {},
            }

            # Persistir classificação
            if self.mongodb and self.mongodb.incidents_collection:
                await self.mongodb.incidents_collection.insert_one(classification)

            logger.info(
                "incident_classifier.classified",
                incident_id=classification["incident_id"],
                severity=severity,
                runbook_id=runbook_id
            )

            return classification

        except Exception as e:
            logger.error(
                "incident_classifier.classification_failed",
                error=str(e),
                anomaly=anomaly
            )
            # E2: Severidade desconhecida → acionar duty engineer
            return self._create_fallback_classification(anomaly, str(e))

    async def _determine_severity(
        self, anomaly: Dict[str, Any], context: Optional[Dict[str, Any]]
    ) -> IncidentSeverity:
        """Determina severidade baseada em regras e contexto"""
        threat_type = anomaly.get("threat_type")
        base_severity = self.classification_rules["threat_severity_mapping"].get(
            threat_type, IncidentSeverity.MEDIUM
        )

        # Ajustar baseado em contexto
        if context:
            # Escalar se afeta produção
            if context.get("environment") == "production":
                severity_levels = list(IncidentSeverity)
                current_index = severity_levels.index(base_severity)
                if current_index > 0:
                    base_severity = severity_levels[current_index - 1]

            # Escalar se afeta recursos críticos
            if context.get("is_critical_resource"):
                severity_levels = list(IncidentSeverity)
                current_index = severity_levels.index(base_severity)
                if current_index > 0:
                    base_severity = severity_levels[current_index - 1]

        return base_severity

    async def _assess_impact(
        self, anomaly: Dict[str, Any], context: Optional[Dict[str, Any]]
    ) -> List[IncidentImpact]:
        """Avalia tipos de impacto do incidente"""
        impacts = []
        threat_type = anomaly.get("threat_type")

        # Mapeamento de ameaças para impactos
        impact_mapping = {
            "unauthorized_access": [IncidentImpact.SECURITY, IncidentImpact.COMPLIANCE],
            "anomalous_behavior": [IncidentImpact.SECURITY],
            "policy_violation": [IncidentImpact.COMPLIANCE, IncidentImpact.SECURITY],
            "resource_abuse": [IncidentImpact.PERFORMANCE, IncidentImpact.AVAILABILITY],
            "data_exfiltration": [
                IncidentImpact.SECURITY,
                IncidentImpact.DATA_INTEGRITY,
                IncidentImpact.COMPLIANCE
            ],
            "malicious_payload": [IncidentImpact.SECURITY, IncidentImpact.DATA_INTEGRITY],
            "dos_attack": [IncidentImpact.AVAILABILITY, IncidentImpact.PERFORMANCE],
        }

        impacts = impact_mapping.get(threat_type, [IncidentImpact.SECURITY])

        return impacts

    async def _calculate_priority(
        self, severity: IncidentSeverity, impact: List[IncidentImpact], confidence: float
    ) -> int:
        """Calcula prioridade numérica (1-5, menor = maior prioridade)"""
        # Base em severidade
        severity_score = {
            IncidentSeverity.CRITICAL: 1,
            IncidentSeverity.HIGH: 2,
            IncidentSeverity.MEDIUM: 3,
            IncidentSeverity.LOW: 4,
            IncidentSeverity.INFO: 5,
        }

        base_priority = severity_score.get(severity, 3)

        # Ajustar por impacto
        impact_weights = self.classification_rules["impact_weight"]
        max_impact_weight = max([impact_weights.get(i, 1.0) for i in impact], default=1.0)

        # Ajustar por confiança
        if confidence < self.classification_rules["confidence_threshold"]:
            base_priority += 1  # Menor confiança = menor prioridade

        # Aplicar peso de impacto
        final_priority = max(1, min(5, int(base_priority / max_impact_weight)))

        return final_priority

    async def _map_to_runbook(
        self, threat_type: str, severity: IncidentSeverity
    ) -> str:
        """Mapeia incidente para runbook específico (E2: mapeado a runbooks)"""
        runbook_mapping = {
            ("unauthorized_access", IncidentSeverity.CRITICAL): "RB-SEC-001-CRITICAL",
            ("unauthorized_access", IncidentSeverity.HIGH): "RB-SEC-001-HIGH",
            ("dos_attack", IncidentSeverity.CRITICAL): "RB-AVAIL-001-CRITICAL",
            ("data_exfiltration", IncidentSeverity.CRITICAL): "RB-SEC-002-CRITICAL",
            ("resource_abuse", IncidentSeverity.HIGH): "RB-PERF-001-HIGH",
            ("malicious_payload", IncidentSeverity.HIGH): "RB-SEC-003-HIGH",
            ("policy_violation", IncidentSeverity.MEDIUM): "RB-COMP-001-MEDIUM",
        }

        runbook_id = runbook_mapping.get(
            (threat_type, severity),
            f"RB-GENERIC-{severity.upper()}"
        )

        return runbook_id

    def _extract_affected_resources(
        self, anomaly: Dict[str, Any], context: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Extrai recursos afetados"""
        resources = []

        details = anomaly.get("details", {})
        if "resource" in details:
            resources.append(details["resource"])

        raw_event = anomaly.get("raw_event", {})
        if "resource_name" in raw_event:
            resources.append(raw_event["resource_name"])

        if context and "affected_resources" in context:
            resources.extend(context["affected_resources"])

        return list(set(resources))

    def _estimate_business_impact(
        self, severity: IncidentSeverity, impact: List[IncidentImpact]
    ) -> str:
        """Estima impacto no negócio"""
        if severity == IncidentSeverity.CRITICAL:
            return "HIGH - Potential service outage or data breach"
        elif severity == IncidentSeverity.HIGH:
            if IncidentImpact.SECURITY in impact:
                return "MEDIUM-HIGH - Security compromise possible"
            return "MEDIUM - Performance degradation likely"
        elif severity == IncidentSeverity.MEDIUM:
            return "MEDIUM - Limited impact on operations"
        else:
            return "LOW - Minimal business impact"

    def _assess_sla_risk(
        self, severity: IncidentSeverity, impact: List[IncidentImpact]
    ) -> bool:
        """Avalia risco de quebra de SLA"""
        if severity in [IncidentSeverity.CRITICAL, IncidentSeverity.HIGH]:
            return True
        if IncidentImpact.AVAILABILITY in impact:
            return True
        return False

    def _requires_human_review(
        self, confidence: float, severity: IncidentSeverity
    ) -> bool:
        """Determina se requer revisão humana"""
        # E2: Divergência > threshold → roteamento para validação manual
        if confidence < self.classification_rules["confidence_threshold"]:
            return True
        if severity == IncidentSeverity.CRITICAL:
            return True
        return False

    def _generate_incident_id(self, anomaly: Dict[str, Any]) -> str:
        """Gera ID único para incidente"""
        import hashlib
        from datetime import datetime

        timestamp = datetime.now(timezone.utc).isoformat()
        threat_type = anomaly.get("threat_type", "unknown")
        raw_str = f"{timestamp}:{threat_type}:{anomaly.get('detected_at', '')}"

        incident_hash = hashlib.sha256(raw_str.encode()).hexdigest()[:12]
        return f"INC-{threat_type.upper()[:4]}-{incident_hash}"

    def _create_fallback_classification(
        self, anomaly: Dict[str, Any], error: str
    ) -> Dict[str, Any]:
        """Cria classificação de fallback quando falha (E2: acionar duty engineer)"""
        return {
            "incident_id": self._generate_incident_id(anomaly),
            "threat_type": anomaly.get("threat_type", "unknown"),
            "severity": IncidentSeverity.MEDIUM,
            "impact": [IncidentImpact.SECURITY],
            "priority": 3,
            "confidence": 0.5,
            "runbook_id": "RB-FALLBACK-MANUAL",
            "affected_resources": [],
            "business_impact": "UNKNOWN - Requires manual review",
            "sla_breach_risk": True,
            "requires_human_review": True,
            "classification_error": error,
            "classified_at": datetime.now(timezone.utc).isoformat(),
            "anomaly": anomaly,
        }
