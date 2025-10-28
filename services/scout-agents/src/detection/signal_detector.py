"""Main signal detector orchestrating detection pipeline"""
from typing import Optional, Dict, Any
import numpy as np
from datetime import datetime, timedelta
import structlog

from ..models.raw_event import RawEvent
from ..models.scout_signal import (
    ScoutSignal,
    SignalType,
    ExplorationDomain,
    SignalSource,
    ChannelType
)
from ..config import get_settings
from .bayesian_filter import BayesianFilter
from .curiosity_scorer import CuriosityScorer

logger = structlog.get_logger()


class SignalDetector:
    """Detects and classifies signals from raw events"""

    def __init__(self, scout_agent_id: str):
        self.scout_agent_id = scout_agent_id
        self.settings = get_settings()
        self.bayesian_filter = BayesianFilter()
        self.curiosity_scorer = CuriosityScorer()

    async def detect(
        self,
        event: RawEvent,
        domain: ExplorationDomain,
        channel: ChannelType = ChannelType.CORE
    ) -> Optional[ScoutSignal]:
        """
        Main detection pipeline

        Args:
            event: Raw event to analyze
            domain: Exploration domain
            channel: Channel type

        Returns:
            ScoutSignal if detected, None otherwise
        """
        try:
            # Step 1: Apply Bayesian filter
            should_process, posterior_prob = self.bayesian_filter.filter(event, domain)

            if not should_process:
                logger.debug(
                    "event_filtered_out",
                    event_id=event.event_id,
                    domain=domain.value,
                    posterior=posterior_prob
                )
                return None

            # Step 2: Detect anomaly or pattern
            signal_type, confidence = self.detect_signal_type(event, domain)

            if not signal_type:
                return None

            # Step 3: Calculate scores
            curiosity_score = self.curiosity_scorer.calculate_score(event, domain)
            confidence_score = self.calculate_confidence(event, confidence, posterior_prob)
            relevance_score = self.calculate_relevance(event, domain)
            risk_score = self.calculate_risk(signal_type, domain)

            # Step 4: Create ScoutSignal
            signal = ScoutSignal(
                scout_agent_id=self.scout_agent_id,
                correlation_id=event.event_id,
                trace_id=event.metadata.get('trace_id', event.event_id),
                span_id=event.metadata.get('span_id', event.event_id),
                signal_type=signal_type,
                exploration_domain=domain,
                source=SignalSource(
                    channel=channel,
                    device_id=event.metadata.get('device_id'),
                    geolocation=None  # TODO: Extract from event if available
                ),
                curiosity_score=curiosity_score,
                confidence=confidence_score,
                relevance_score=relevance_score,
                risk_score=risk_score,
                description=self.generate_description(signal_type, event, domain),
                raw_data={k: str(v) for k, v in event.payload.items()},
                features=event.extract_features(),
                metadata={
                    'event_type': event.event_type,
                    'source': event.source,
                    'detection_timestamp': datetime.utcnow().isoformat()
                },
                requires_validation=self.requires_validation(signal_type, confidence_score)
            )

            # Step 5: Check if should publish
            if signal.should_publish(
                self.settings.detection.curiosity_threshold,
                self.settings.detection.confidence_threshold,
                self.settings.detection.relevance_threshold,
                self.settings.detection.risk_threshold
            ):
                logger.info(
                    "signal_detected",
                    signal_id=signal.signal_id,
                    signal_type=signal_type.value,
                    domain=domain.value,
                    curiosity=curiosity_score,
                    confidence=confidence_score
                )
                return signal

            logger.debug(
                "signal_below_thresholds",
                signal_type=signal_type.value,
                curiosity=curiosity_score,
                confidence=confidence_score
            )
            return None

        except Exception as e:
            logger.error(
                "signal_detection_failed",
                event_id=event.event_id,
                error=str(e)
            )
            return None

    def detect_signal_type(
        self,
        event: RawEvent,
        domain: ExplorationDomain
    ) -> tuple[Optional[SignalType], float]:
        """
        Detect signal type using heuristics

        Returns:
            Tuple of (SignalType, confidence) or (None, 0.0)
        """
        features = event.extract_features()

        # Anomaly detection using z-score
        anomaly_score = event.calculate_anomaly_score()

        if anomaly_score > 0.8:
            # High anomaly - determine if positive or negative
            if self._is_positive_anomaly(event, domain):
                return SignalType.ANOMALY_POSITIVE, 0.85
            else:
                return SignalType.ANOMALY_NEGATIVE, 0.85

        # Pattern detection
        if self._detect_emerging_pattern(features, domain):
            return SignalType.PATTERN_EMERGING, 0.75

        # Opportunity detection
        if domain == ExplorationDomain.BUSINESS and anomaly_score > 0.6:
            return SignalType.OPPORTUNITY, 0.70

        # Threat detection
        if domain == ExplorationDomain.SECURITY and anomaly_score > 0.7:
            return SignalType.THREAT, 0.80

        # Trend detection
        if self._detect_trend(features, domain):
            return SignalType.TREND, 0.65

        return None, 0.0

    def _is_positive_anomaly(self, event: RawEvent, domain: ExplorationDomain) -> bool:
        """Determine if anomaly is positive based on domain and event type"""
        # Heuristic: user_action events in BUSINESS domain tend to be positive
        if domain == ExplorationDomain.BUSINESS and event.event_type == 'user_action':
            return True

        # Metrics above threshold could be positive
        if event.event_type == 'metric':
            values = [v for v in event.payload.values() if isinstance(v, (int, float))]
            if values and np.mean(values) > 0:
                return True

        return False

    def _detect_emerging_pattern(
        self,
        features: list[float],
        domain: ExplorationDomain
    ) -> bool:
        """Detect emerging patterns - MVP heuristic"""
        # Simple pattern: high variance in features
        if not features:
            return False

        variance = np.var(features)
        return variance > 0.5  # Threshold for pattern detection

    def _detect_trend(self, features: list[float], domain: ExplorationDomain) -> bool:
        """Detect trends - MVP heuristic"""
        if not features or len(features) < 10:
            return False

        # Calculate simple linear trend
        x = np.arange(len(features))
        slope = np.polyfit(x, features, 1)[0]

        # Significant trend if slope is substantial
        return abs(slope) > 0.1

    def calculate_confidence(
        self,
        event: RawEvent,
        detection_confidence: float,
        bayesian_posterior: float
    ) -> float:
        """
        Calculate overall confidence in detection

        Args:
            event: Raw event
            detection_confidence: Confidence from signal type detection
            bayesian_posterior: Posterior probability from Bayesian filter

        Returns:
            float: Confidence score (0-1)
        """
        # Combine multiple confidence sources
        data_quality = self._assess_data_quality(event)

        confidence = (
            detection_confidence * 0.5 +
            bayesian_posterior * 0.3 +
            data_quality * 0.2
        )

        return min(max(confidence, 0.0), 1.0)

    def _assess_data_quality(self, event: RawEvent) -> float:
        """Assess quality of event data"""
        quality_score = 0.5  # Base quality

        # Check payload completeness
        if event.payload:
            quality_score += 0.2

        # Check metadata
        if event.metadata:
            quality_score += 0.1

        # Check feature extractability
        features = event.extract_features()
        if features and len(features) > 10:
            quality_score += 0.2

        return min(quality_score, 1.0)

    def calculate_relevance(self, event: RawEvent, domain: ExplorationDomain) -> float:
        """Calculate relevance score for the system"""
        # Delegate to curiosity scorer's relevance calculation
        return self.curiosity_scorer.calculate_relevance(event, domain)

    def calculate_risk(self, signal_type: SignalType, domain: ExplorationDomain) -> float:
        """
        Calculate risk score based on signal type and domain

        Args:
            signal_type: Type of signal
            domain: Exploration domain

        Returns:
            float: Risk score (0-1)
        """
        # Base risk by signal type
        type_risk = {
            SignalType.THREAT: 0.9,
            SignalType.ANOMALY_NEGATIVE: 0.7,
            SignalType.OPPORTUNITY: 0.3,
            SignalType.ANOMALY_POSITIVE: 0.2,
            SignalType.PATTERN_EMERGING: 0.5,
            SignalType.TREND: 0.4
        }

        base_risk = type_risk.get(signal_type, 0.5)

        # Domain risk multiplier
        domain_multiplier = {
            ExplorationDomain.SECURITY: 1.2,
            ExplorationDomain.INFRASTRUCTURE: 1.1,
            ExplorationDomain.BUSINESS: 0.9,
            ExplorationDomain.TECHNICAL: 1.0,
            ExplorationDomain.BEHAVIOR: 0.95
        }

        risk = base_risk * domain_multiplier.get(domain, 1.0)

        return min(max(risk, 0.0), 1.0)

    def generate_description(
        self,
        signal_type: SignalType,
        event: RawEvent,
        domain: ExplorationDomain
    ) -> str:
        """Generate human-readable description of signal"""
        descriptions = {
            SignalType.ANOMALY_POSITIVE: f"Anomalia positiva detectada em {domain.value}",
            SignalType.ANOMALY_NEGATIVE: f"Anomalia negativa detectada em {domain.value}",
            SignalType.PATTERN_EMERGING: f"Padrão emergente identificado em {domain.value}",
            SignalType.OPPORTUNITY: f"Oportunidade detectada em {domain.value}",
            SignalType.THREAT: f"Ameaça potencial identificada em {domain.value}",
            SignalType.TREND: f"Tendência detectada em {domain.value}"
        }

        base_desc = descriptions.get(signal_type, f"Sinal detectado em {domain.value}")

        # Add event source info
        return f"{base_desc} (fonte: {event.source}, tipo: {event.event_type})"

    def requires_validation(self, signal_type: SignalType, confidence: float) -> bool:
        """Determine if signal requires validation by Analyst Agents"""
        # High-risk signals always require validation
        if signal_type in [SignalType.THREAT, SignalType.ANOMALY_NEGATIVE]:
            return True

        # Low confidence signals require validation
        if confidence < 0.8:
            return True

        return False
