"""Threat detection service for identifying security anomalies (Fluxo E1)"""
from typing import Dict, Any, Optional, List
import structlog
from datetime import datetime, timezone
from enum import Enum

logger = structlog.get_logger()


class ThreatType(str, Enum):
    """Types of threats detected"""
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"
    POLICY_VIOLATION = "policy_violation"
    RESOURCE_ABUSE = "resource_abuse"
    DATA_EXFILTRATION = "data_exfiltration"
    MALICIOUS_PAYLOAD = "malicious_payload"
    DOS_ATTACK = "dos_attack"


class ThreatDetector:
    """Detecta anomalias e ameaças seguindo Fluxo E1"""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.detection_rules = self._initialize_detection_rules()
        self.adaptive_thresholds = self._load_adaptive_thresholds()

    def _initialize_detection_rules(self) -> Dict[str, Any]:
        """Carrega regras de detecção (podem vir de config ou ML model)"""
        return {
            "failed_auth_threshold": 5,
            "request_rate_threshold": 1000,  # requests/min
            "suspicious_patterns": [
                r"(union|select|insert|drop|delete)\s+(from|into|table)",
                r"\.\.\/",
                r"<script",
            ],
            "known_malicious_ips": set(),
            "anomaly_score_threshold": 0.75,
        }

    def _load_adaptive_thresholds(self) -> Dict[str, float]:
        """Carrega limiares adaptativos conforme E1"""
        return {
            "cpu_usage": 0.85,
            "memory_usage": 0.90,
            "error_rate": 0.05,
            "latency_p95": 500.0,  # ms
        }

    async def detect_anomaly(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Detecta anomalias em eventos (E1: Detectar anomalia)

        Args:
            event: Evento de telemetria ou segurança

        Returns:
            Dict com detalhes da anomalia ou None se não detectada
        """
        try:
            event_type = event.get("type", "unknown")

            logger.debug(
                "threat_detector.analyzing_event",
                event_type=event_type,
                event_id=event.get("event_id")
            )

            # Múltiplos métodos de detecção
            anomaly = (
                await self._detect_authentication_anomaly(event)
                or await self._detect_rate_anomaly(event)
                or await self._detect_pattern_anomaly(event)
                or await self._detect_resource_anomaly(event)
                or await self._detect_behavioral_anomaly(event)
            )

            if anomaly:
                logger.info(
                    "threat_detector.anomaly_detected",
                    anomaly_type=anomaly.get("threat_type"),
                    severity=anomaly.get("severity"),
                    event_id=event.get("event_id")
                )

                # Cache para análise rápida
                if self.redis:
                    await self._cache_anomaly(anomaly)

            return anomaly

        except Exception as e:
            logger.error(
                "threat_detector.detection_failed",
                error=str(e),
                event_id=event.get("event_id")
            )
            raise

    async def _detect_authentication_anomaly(
        self, event: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Detecta falhas de autenticação anômalas"""
        if event.get("type") != "authentication":
            return None

        user_id = event.get("user_id")
        failed_count = event.get("failed_attempts", 0)

        if failed_count >= self.detection_rules["failed_auth_threshold"]:
            return {
                "threat_type": ThreatType.UNAUTHORIZED_ACCESS,
                "severity": "high",
                "confidence": min(0.5 + (failed_count * 0.1), 1.0),
                "details": {
                    "user_id": user_id,
                    "failed_attempts": failed_count,
                    "source_ip": event.get("source_ip"),
                },
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "raw_event": event,
            }

        return None

    async def _detect_rate_anomaly(
        self, event: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Detecta anomalias de taxa de requisições"""
        if event.get("type") != "request_metrics":
            return None

        request_rate = event.get("requests_per_minute", 0)

        if request_rate > self.detection_rules["request_rate_threshold"]:
            return {
                "threat_type": ThreatType.DOS_ATTACK,
                "severity": "critical",
                "confidence": 0.85,
                "details": {
                    "request_rate": request_rate,
                    "threshold": self.detection_rules["request_rate_threshold"],
                    "source": event.get("source"),
                },
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "raw_event": event,
            }

        return None

    async def _detect_pattern_anomaly(
        self, event: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Detecta padrões maliciosos no payload"""
        import re

        payload = event.get("payload", "")
        if not isinstance(payload, str):
            return None

        for pattern in self.detection_rules["suspicious_patterns"]:
            if re.search(pattern, payload, re.IGNORECASE):
                return {
                    "threat_type": ThreatType.MALICIOUS_PAYLOAD,
                    "severity": "high",
                    "confidence": 0.9,
                    "details": {
                        "matched_pattern": pattern,
                        "payload_snippet": payload[:200],
                    },
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "raw_event": event,
                }

        return None

    async def _detect_resource_anomaly(
        self, event: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Detecta anomalias de uso de recursos (thresholds adaptativos)"""
        if event.get("type") != "resource_metrics":
            return None

        metrics = event.get("metrics", {})

        # Verificar CPU
        cpu_usage = metrics.get("cpu_usage", 0)
        if cpu_usage > self.adaptive_thresholds["cpu_usage"]:
            return {
                "threat_type": ThreatType.RESOURCE_ABUSE,
                "severity": "medium",
                "confidence": 0.7,
                "details": {
                    "metric": "cpu_usage",
                    "value": cpu_usage,
                    "threshold": self.adaptive_thresholds["cpu_usage"],
                    "resource": event.get("resource_name"),
                },
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "raw_event": event,
            }

        # Verificar Memória
        memory_usage = metrics.get("memory_usage", 0)
        if memory_usage > self.adaptive_thresholds["memory_usage"]:
            return {
                "threat_type": ThreatType.RESOURCE_ABUSE,
                "severity": "high",
                "confidence": 0.75,
                "details": {
                    "metric": "memory_usage",
                    "value": memory_usage,
                    "threshold": self.adaptive_thresholds["memory_usage"],
                    "resource": event.get("resource_name"),
                },
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "raw_event": event,
            }

        return None

    async def _detect_behavioral_anomaly(
        self, event: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Detecta anomalias comportamentais usando ML (placeholder para modelo real)"""
        # TODO: Integrar com modelo ML real (autoencoder/isolationForest)
        anomaly_score = event.get("anomaly_score", 0)

        if anomaly_score > self.detection_rules["anomaly_score_threshold"]:
            return {
                "threat_type": ThreatType.ANOMALOUS_BEHAVIOR,
                "severity": "medium",
                "confidence": anomaly_score,
                "details": {
                    "anomaly_score": anomaly_score,
                    "threshold": self.detection_rules["anomaly_score_threshold"],
                    "features": event.get("features", {}),
                },
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "raw_event": event,
            }

        return None

    async def _cache_anomaly(self, anomaly: Dict[str, Any]):
        """Cacheia anomalia para acesso rápido"""
        if not self.redis:
            return

        try:
            import json
            anomaly_id = f"anomaly:{anomaly.get('threat_type')}:{datetime.now(timezone.utc).timestamp()}"
            await self.redis.set(
                anomaly_id,
                json.dumps(anomaly),
                ex=3600  # 1 hora
            )
        except Exception as e:
            logger.warning("threat_detector.cache_failed", error=str(e))

    async def recalibrate_thresholds(self, metrics: Dict[str, float]):
        """Recalibra thresholds adaptativos (E1: recalibrar modelo)"""
        try:
            logger.info("threat_detector.recalibrating_thresholds", metrics=metrics)

            # Ajustar baseado em feedback
            if "false_positive_rate" in metrics:
                fpr = metrics["false_positive_rate"]
                if fpr > 0.05:  # Se >5% falsos positivos
                    # Aumentar thresholds
                    for key in self.adaptive_thresholds:
                        self.adaptive_thresholds[key] *= 1.1
                    logger.info("threat_detector.thresholds_increased", fpr=fpr)

            # Salvar novos thresholds
            if self.redis:
                import json
                await self.redis.set(
                    "adaptive_thresholds",
                    json.dumps(self.adaptive_thresholds),
                    ex=86400  # 24 horas
                )

        except Exception as e:
            logger.error("threat_detector.recalibration_failed", error=str(e))
            raise
