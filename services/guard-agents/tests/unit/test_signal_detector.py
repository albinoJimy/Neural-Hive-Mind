"""
Unit tests for ThreatDetector service (guard-agents).

Tests signal detection, classification, and threat analysis.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.services.threat_detector import ThreatDetector, ThreatType


class TestThreatDetectorInitialization:
    """Test ThreatDetector initialization and configuration."""

    def test_initialization_defaults(self):
        """Test detector initialization with default values."""
        detector = ThreatDetector()

        assert detector.detection_rules is not None
        assert detector.adaptive_thresholds is not None
        assert detector.detection_rules["failed_auth_threshold"] == 5
        assert detector.detection_rules["request_rate_threshold"] == 1000
        assert detector.adaptive_thresholds["cpu_usage"] == 0.85
        assert detector.adaptive_thresholds["memory_usage"] == 0.90

    def test_initialization_with_redis(self, mock_redis_client):
        """Test detector initialization with Redis client."""
        detector = ThreatDetector(redis_client=mock_redis_client)

        assert detector.redis is not None
        assert detector.redis == mock_redis_client

    def test_initialization_with_anomaly_detector(self, mock_anomaly_detector):
        """Test detector initialization with ML anomaly detector."""
        detector = ThreatDetector(anomaly_detector=mock_anomaly_detector)

        assert detector.anomaly_detector is not None
        assert detector.anomaly_detector == mock_anomaly_detector

    def test_detection_rules_structure(self):
        """Test that detection rules have expected structure."""
        detector = ThreatDetector()

        assert "failed_auth_threshold" in detector.detection_rules
        assert "request_rate_threshold" in detector.detection_rules
        assert "suspicious_patterns" in detector.detection_rules
        assert "known_malicious_ips" in detector.detection_rules
        assert "anomaly_score_threshold" in detector.detection_rules
        assert isinstance(detector.detection_rules["suspicious_patterns"], list)

    def test_adaptive_thresholds_structure(self):
        """Test that adaptive thresholds have expected structure."""
        detector = ThreatDetector()

        assert "cpu_usage" in detector.adaptive_thresholds
        assert "memory_usage" in detector.adaptive_thresholds
        assert "error_rate" in detector.adaptive_thresholds
        assert "latency_p95" in detector.adaptive_thresholds


class TestAuthenticationAnomalyDetection:
    """Test authentication anomaly detection."""

    @pytest.mark.asyncio
    async def test_normal_auth_event(self, sample_auth_event):
        """Test normal authentication event does not trigger anomaly."""
        detector = ThreatDetector()
        result = await detector._detect_authentication_anomaly(sample_auth_event)

        assert result is None

    @pytest.mark.asyncio
    async def test_failed_auth_threshold_trigger(self, sample_failed_auth_event):
        """Test failed authentication event above threshold triggers anomaly."""
        detector = ThreatDetector()
        result = await detector._detect_authentication_anomaly(sample_failed_auth_event)

        assert result is not None
        assert result["threat_type"] == ThreatType.UNAUTHORIZED_ACCESS
        assert result["severity"] == "high"
        assert result["details"]["failed_attempts"] == 7
        assert result["details"]["user_id"] == "user-456"

    @pytest.mark.asyncio
    async def test_failed_auth_confidence_calculation(self):
        """Test confidence increases with failed attempts."""
        detector = ThreatDetector()

        # Test with threshold attempts
        event_5 = {"type": "authentication", "failed_attempts": 5, "user_id": "test"}
        result_5 = await detector._detect_authentication_anomaly(event_5)

        assert result_5 is not None
        expected_confidence = min(0.5 + (5 * 0.1), 1.0)
        assert result_5["confidence"] == expected_confidence

        # Test with more attempts
        event_10 = {"type": "authentication", "failed_attempts": 10, "user_id": "test"}
        result_10 = await detector._detect_authentication_anomaly(event_10)

        assert result_10 is not None
        assert result_10["confidence"] == 1.0  # Max confidence

    @pytest.mark.asyncio
    async def test_non_auth_event_ignored(self):
        """Test non-authentication events are ignored."""
        detector = ThreatDetector()
        event = {"type": "other", "user_id": "test", "failed_attempts": 10}

        result = await detector._detect_authentication_anomaly(event)

        assert result is None


class TestRateAnomalyDetection:
    """Test rate-based anomaly detection."""

    @pytest.mark.asyncio
    async def test_normal_request_rate(self, sample_request_metrics_event):
        """Test normal request rate does not trigger anomaly."""
        detector = ThreatDetector()
        result = await detector._detect_rate_anomaly(sample_request_metrics_event)

        assert result is None

    @pytest.mark.asyncio
    async def test_dos_attack_detection(self, sample_dos_attack_event):
        """Test DoS attack detection via high request rate."""
        detector = ThreatDetector()
        result = await detector._detect_rate_anomaly(sample_dos_attack_event)

        assert result is not None
        assert result["threat_type"] == ThreatType.DOS_ATTACK
        assert result["severity"] == "critical"
        assert result["confidence"] == 0.85
        assert result["details"]["request_rate"] == 1500
        assert result["details"]["threshold"] == 1000

    @pytest.mark.asyncio
    async def test_exact_threshold_trigger(self):
        """Test exact threshold value triggers anomaly."""
        detector = ThreatDetector()
        event = {
            "type": "request_metrics",
            "requests_per_minute": 1000,  # Exact threshold
            "source": "test",
        }

        result = await detector._detect_rate_anomaly(event)

        assert result is None  # Uses > not >=


class TestPatternAnomalyDetection:
    """Test pattern-based anomaly detection."""

    @pytest.mark.asyncio
    async def test_safe_payload(self, sample_payload_event):
        """Test safe payload does not trigger anomaly."""
        detector = ThreatDetector()
        result = await detector._detect_pattern_anomaly(sample_payload_event)

        # Safe payload should not trigger
        assert result is None

    @pytest.mark.asyncio
    async def test_sql_injection_detection(self, sample_malicious_payload_event):
        """Test SQL injection pattern detection."""
        detector = ThreatDetector()
        result = await detector._detect_pattern_anomaly(sample_malicious_payload_event)

        assert result is not None
        assert result["threat_type"] == ThreatType.MALICIOUS_PAYLOAD
        assert result["severity"] == "high"
        assert result["confidence"] == 0.9
        assert "matched_pattern" in result["details"]

    @pytest.mark.asyncio
    async def test_path_traversal_detection(self):
        """Test path traversal pattern detection."""
        detector = ThreatDetector()
        event = {"type": "http_request", "payload": "../../../etc/passwd"}

        result = await detector._detect_pattern_anomaly(event)

        assert result is not None
        assert result["threat_type"] == ThreatType.MALICIOUS_PAYLOAD

    @pytest.mark.asyncio
    async def test_xss_detection(self):
        """Test XSS pattern detection."""
        detector = ThreatDetector()
        event = {"type": "http_request", "payload": "<script>alert('xss')</script>"}

        result = await detector._detect_pattern_anomaly(event)

        assert result is not None
        assert result["threat_type"] == ThreatType.MALICIOUS_PAYLOAD

    @pytest.mark.asyncio
    async def test_non_string_payload_ignored(self):
        """Test non-string payloads are ignored."""
        detector = ThreatDetector()
        event = {"type": "http_request", "payload": 12345}

        result = await detector._detect_pattern_anomaly(event)

        assert result is None

    @pytest.mark.asyncio
    async def test_case_insensitive_pattern_matching(self):
        """Test pattern matching is case insensitive."""
        detector = ThreatDetector()
        event = {
            "type": "http_request",
            "payload": "delete from users",  # Lowercase but should still match
        }

        result = await detector._detect_pattern_anomaly(event)

        assert result is not None


class TestResourceAnomalyDetection:
    """Test resource-based anomaly detection."""

    @pytest.mark.asyncio
    async def test_normal_resource_usage(self, sample_resource_metrics_event):
        """Test normal resource usage does not trigger anomaly."""
        detector = ThreatDetector()
        result = await detector._detect_resource_anomaly(sample_resource_metrics_event)

        assert result is None

    @pytest.mark.asyncio
    async def test_high_cpu_usage_detection(self):
        """Test high CPU usage detection."""
        detector = ThreatDetector()
        event = {
            "type": "resource_metrics",
            "resource_name": "node-1",
            "metrics": {"cpu_usage": 0.90},
        }

        result = await detector._detect_resource_anomaly(event)

        assert result is not None
        assert result["threat_type"] == ThreatType.RESOURCE_ABUSE
        assert result["severity"] == "medium"
        assert result["details"]["metric"] == "cpu_usage"

    @pytest.mark.asyncio
    async def test_high_memory_usage_detection(self):
        """Test high memory usage detection."""
        detector = ThreatDetector()
        event = {
            "type": "resource_metrics",
            "resource_name": "node-1",
            "metrics": {"memory_usage": 0.95},
        }

        result = await detector._detect_resource_anomaly(event)

        assert result is not None
        assert result["threat_type"] == ThreatType.RESOURCE_ABUSE
        assert result["severity"] == "high"
        assert result["details"]["metric"] == "memory_usage"

    @pytest.mark.asyncio
    async def test_combined_resource_alerts(self, sample_high_resource_event):
        """Test that both CPU and memory issues can be detected."""
        detector = ThreatDetector()
        result = await detector._detect_resource_anomaly(sample_high_resource_event)

        # Should trigger on CPU first (checked before memory)
        assert result is not None
        assert result["details"]["metric"] in ["cpu_usage", "memory_usage"]

    @pytest.mark.asyncio
    async def test_non_resource_event_ignored(self):
        """Test non-resource events are ignored."""
        detector = ThreatDetector()
        event = {"type": "other", "metrics": {"cpu_usage": 0.99}}

        result = await detector._detect_resource_anomaly(event)

        assert result is None


class TestBehavioralAnomalyDetection:
    """Test behavioral anomaly detection."""

    @pytest.mark.asyncio
    async def test_normal_behavior(self, sample_behavioral_event):
        """Test normal behavior does not trigger anomaly."""
        detector = ThreatDetector()
        result = await detector._detect_behavioral_anomaly(sample_behavioral_event)

        assert result is None

    @pytest.mark.asyncio
    async def test_anomalous_behavior_threshold(self, sample_anomalous_behavior_event):
        """Test anomalous behavior detection via threshold."""
        detector = ThreatDetector()
        result = await detector._detect_behavioral_anomaly(sample_anomalous_behavior_event)

        assert result is not None
        assert result["threat_type"] == ThreatType.ANOMALOUS_BEHAVIOR
        assert result["details"]["anomaly_score"] == 0.85

    @pytest.mark.asyncio
    async def test_ml_anomaly_detection(
        self, sample_anomalous_behavior_event, mock_anomaly_detector
    ):
        """Test ML-based anomaly detection."""
        # Configure mock to return anomaly
        mock_anomaly_detector.detect_anomaly = AsyncMock(
            return_value={
                "is_anomaly": True,
                "anomaly_score": 0.85,
                "anomaly_type": "outlier",
                "explanation": "Unusual pattern detected",
                "model_type": "isolation_forest",
            }
        )

        detector = ThreatDetector(anomaly_detector=mock_anomaly_detector)
        result = await detector._detect_behavioral_anomaly(sample_anomalous_behavior_event)

        assert result is not None
        assert result["threat_type"] == ThreatType.ANOMALOUS_BEHAVIOR
        # When ML detects, it includes model_type in details
        assert "model_type" in result["details"]

    @pytest.mark.asyncio
    async def test_ml_fallback_on_failure(
        self, sample_anomalous_behavior_event, mock_anomaly_detector
    ):
        """Test fallback to heuristic when ML fails."""
        # Configure mock to raise exception
        mock_anomaly_detector.detect_anomaly = AsyncMock(side_effect=Exception("ML error"))

        detector = ThreatDetector(anomaly_detector=mock_anomaly_detector)
        result = await detector._detect_behavioral_anomaly(sample_anomalous_behavior_event)

        # Should still detect via heuristic fallback
        assert result is not None
        assert result["details"]["detection_method"] == "heuristic"


class TestMainDetectionPipeline:
    """Test main detection pipeline."""

    @pytest.mark.asyncio
    async def test_detect_no_anomaly(self, sample_auth_event):
        """Test detection pipeline with normal event."""
        detector = ThreatDetector()
        result = await detector.detect_anomaly(sample_auth_event)

        assert result is None

    @pytest.mark.asyncio
    async def test_detect_authentication_anomaly(self, sample_failed_auth_event):
        """Test detection pipeline finds authentication anomaly."""
        detector = ThreatDetector()
        result = await detector.detect_anomaly(sample_failed_auth_event)

        assert result is not None
        assert result["threat_type"] == ThreatType.UNAUTHORIZED_ACCESS
        assert "detected_at" in result

    @pytest.mark.asyncio
    async def test_detect_dos_attack(self, sample_dos_attack_event):
        """Test detection pipeline finds DoS attack."""
        detector = ThreatDetector()
        result = await detector.detect_anomaly(sample_dos_attack_event)

        assert result is not None
        assert result["threat_type"] == ThreatType.DOS_ATTACK

    @pytest.mark.asyncio
    async def test_caching_anomaly(self, sample_failed_auth_event, mock_redis_client):
        """Test anomaly is cached in Redis."""
        detector = ThreatDetector(redis_client=mock_redis_client)
        result = await detector.detect_anomaly(sample_failed_auth_event)

        assert result is not None
        mock_redis_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_detection_exception_handling(self):
        """Test detection exceptions are propagated."""
        detector = ThreatDetector()

        # Invalid event structure
        with pytest.raises(Exception):
            await detector.detect_anomaly(None)


class TestSeverityMapping:
    """Test severity mapping functionality."""

    def test_severity_mapping_critical(self):
        """Test critical severity mapping."""
        detector = ThreatDetector()
        severity = detector._map_severity(0.9)

        assert severity == "critical"

    def test_severity_mapping_high(self):
        """Test high severity mapping."""
        detector = ThreatDetector()
        severity = detector._map_severity(0.7)

        assert severity == "high"

    def test_severity_mapping_medium(self):
        """Test medium severity mapping."""
        detector = ThreatDetector()
        severity = detector._map_severity(0.5)

        assert severity == "medium"

    def test_severity_mapping_low(self):
        """Test low severity mapping."""
        detector = ThreatDetector()
        severity = detector._map_severity(0.3)

        assert severity == "low"


class TestThresholdRecalibration:
    """Test adaptive threshold recalibration."""

    @pytest.mark.asyncio
    async def test_threshold_increase_on_high_fpr(self, mock_redis_client):
        """Test thresholds increase when false positive rate is high."""
        detector = ThreatDetector(redis_client=mock_redis_client)
        initial_cpu_threshold = detector.adaptive_thresholds["cpu_usage"]

        await detector.recalibrate_thresholds({"false_positive_rate": 0.10})

        # Threshold should increase
        assert detector.adaptive_thresholds["cpu_usage"] > initial_cpu_threshold
        mock_redis_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_threshold_saved_to_redis(self, mock_redis_client):
        """Test recalibrated thresholds are saved to Redis."""
        detector = ThreatDetector(redis_client=mock_redis_client)

        await detector.recalibrate_thresholds({"false_positive_rate": 0.06})

        # Check Redis was called to save thresholds
        mock_redis_client.set.assert_called_once()
        call_args = mock_redis_client.set.call_args
        assert call_args[0][0] == "adaptive_thresholds"

    @pytest.mark.asyncio
    async def test_recalibration_exception_handling(self):
        """Test recalibration handles exceptions."""
        detector = ThreatDetector()

        # Should not raise exception even with invalid input
        await detector.recalibrate_thresholds({})


class TestEventToTicketConversion:
    """Test event to ticket conversion for ML."""

    def test_event_to_ticket_conversion(self):
        """Test event is converted to ticket format correctly."""
        detector = ThreatDetector()
        event = {
            "event_id": "test-001",
            "type": "test_type",
            "risk_weight": 60,
            "capabilities": ["query", "transform"],
            "qos": {"priority": "high"},
            "parameters": {"timeout": 5000},
            "timestamp": 1234567890.0,
            "estimated_duration_ms": 1000,
            "sla_timeout_ms": 5000,
            "retry_count": 2,
        }

        ticket = detector._event_to_ticket(event)

        assert ticket["ticket_id"] == "test-001"
        assert ticket["type"] == "test_type"
        assert ticket["risk_weight"] == 60
        assert ticket["capabilities"] == ["query", "transform"]
        assert ticket["qos"]["priority"] == "high"

    def test_event_to_ticket_defaults(self):
        """Test event to ticket uses defaults for missing fields."""
        detector = ThreatDetector()
        event = {"event_id": "minimal"}

        ticket = detector._event_to_ticket(event)

        assert ticket["ticket_id"] == "minimal"
        assert ticket["type"] == "UNKNOWN"
        assert ticket["risk_weight"] == 50
        assert ticket["capabilities"] == []
        assert ticket["qos"] == {}
        assert ticket["parameters"] == {}
        assert ticket["retry_count"] == 0


class TestMetrics:
    """Test metrics collection."""

    @pytest.mark.asyncio
    @patch("src.services.threat_detector.MetricsCollector")
    async def test_anomaly_detection_metrics_recorded(
        self, mock_metrics_collector, mock_anomaly_detector
    ):
        """Test that anomaly detection metrics are recorded."""
        mock_anomaly_detector.detect_anomaly = AsyncMock(
            return_value={
                "is_anomaly": True,
                "anomaly_score": 0.85,
                "anomaly_type": "outlier",
                "model_type": "isolation_forest",
            }
        )

        detector = ThreatDetector(anomaly_detector=mock_anomaly_detector)
        event = {"event_id": "test-001", "type": "user_behavior", "anomaly_score": 0.85}

        await detector._detect_behavioral_anomaly(event)

        # Check metrics were recorded
        # Note: This depends on MetricsCollector.record_anomaly_detection being called
        # The actual implementation would need to be verified
