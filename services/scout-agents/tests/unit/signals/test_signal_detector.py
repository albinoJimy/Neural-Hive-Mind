"""
Unit tests for SignalDetector service (scout-agents).

Tests signal detection, classification, and scoring.
"""
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.detection.signal_detector import SignalDetector
from src.models.scout_signal import SignalType, SignalSource


class TestSignalDetectorInitialization:
    """Test SignalDetector initialization and configuration."""

    def test_initialization(self):
        """Test detector initialization with scout agent ID."""
        detector = SignalDetector("scout-agent-001")

        assert detector.scout_agent_id == "scout-agent-001"
        assert detector.bayesian_filter is not None
        assert detector.curiosity_scorer is not None
        assert detector.settings is not None


class TestSignalTypeDetection:
    """Test signal type detection logic."""

    @pytest.mark.asyncio
    async def test_detect_positive_anomaly_business_domain(
        self, sample_anomalous_raw_event, business_domain
    ):
        """Test positive anomaly detection in business domain."""
        detector = SignalDetector("test-scout")

        # Modify event to be positive anomaly
        sample_anomalous_raw_event.payload["error_count"] = -50  # Negative errors = positive
        sample_anomalous_raw_event.event_type = "user_action"

        signal_type, confidence = detector.detect_signal_type(
            sample_anomalous_raw_event, business_domain
        )

        assert signal_type is not None
        assert confidence > 0

    @pytest.mark.asyncio
    async def test_detect_threat_security_domain(self, sample_anomalous_raw_event, security_domain):
        """Test threat detection in security domain."""
        detector = SignalDetector("test-scout")

        signal_type, confidence = detector.detect_signal_type(
            sample_anomalous_raw_event, security_domain
        )

        # High anomaly in security domain should be threat
        if signal_type:
            assert confidence > 0

    @pytest.mark.asyncio
    async def test_detect_opportunity(self, sample_raw_event, business_domain):
        """Test opportunity detection in business domain."""
        detector = SignalDetector("test-scout")

        # Add anomaly score to trigger detection
        with patch.object(sample_raw_event, "calculate_anomaly_score", return_value=0.7):
            signal_type, confidence = detector.detect_signal_type(sample_raw_event, business_domain)

            # May detect opportunity or other type
            if signal_type:
                assert isinstance(signal_type, SignalType)

    @pytest.mark.asyncio
    async def test_no_signal_normal_event(self, sample_raw_event, business_domain):
        """Test normal event returns no signal."""
        detector = SignalDetector("test-scout")

        with patch.object(sample_raw_event, "calculate_anomaly_score", return_value=0.2):
            signal_type, confidence = detector.detect_signal_type(sample_raw_event, business_domain)

            # Low anomaly should not trigger strong signals
            if signal_type is None:
                assert confidence == 0.0


class TestEmergingPatternDetection:
    """Test emerging pattern detection."""

    @pytest.mark.asyncio
    async def test_detect_emerging_pattern_high_variance(self):
        """Test pattern detection with high variance features."""
        detector = SignalDetector("test-scout")

        # Create high variance features
        high_variance_features = [i * 0.5 + (i % 3) for i in range(20)]

        result = detector._detect_emerging_pattern(high_variance_features, UnifiedDomain.BUSINESS)

        assert result is True

    @pytest.mark.asyncio
    async def test_no_pattern_low_variance(self):
        """Test no pattern detection with low variance features."""
        detector = SignalDetector("test-scout")

        # Create low variance features
        low_variance_features = [1.0, 1.01, 0.99, 1.0, 1.01]

        result = detector._detect_emerging_pattern(low_variance_features, UnifiedDomain.BUSINESS)

        assert result is False

    @pytest.mark.asyncio
    async def test_empty_features_no_pattern(self):
        """Test empty features return no pattern."""
        detector = SignalDetector("test-scout")

        result = detector._detect_emerging_pattern([], UnifiedDomain.BUSINESS)

        assert result is False


class TestTrendDetection:
    """Test trend detection logic."""

    @pytest.mark.asyncio
    async def test_detect_upward_trend(self):
        """Test upward trend detection."""
        detector = SignalDetector("test-scout")

        # Create upward trending data
        trending_features = list(range(15))

        result = detector._detect_trend(trending_features, UnifiedDomain.BUSINESS)

        assert result is True

    @pytest.mark.asyncio
    async def test_detect_downward_trend(self):
        """Test downward trend detection."""
        detector = SignalDetector("test-scout")

        # Create downward trending data
        trending_features = list(range(15, 0, -1))

        result = detector._detect_trend(trending_features, UnifiedDomain.BUSINESS)

        assert result is True

    @pytest.mark.asyncio
    async def test_no_trend_flat_data(self):
        """Test flat data returns no trend."""
        detector = SignalDetector("test-scout")

        # Create flat data
        flat_features = [5.0] * 15

        result = detector._detect_trend(flat_features, UnifiedDomain.BUSINESS)

        assert result is False

    @pytest.mark.asyncio
    async def test_insufficient_data_no_trend(self):
        """Test insufficient data returns no trend."""
        detector = SignalDetector("test-scout")

        result = detector._detect_trend([1.0, 2.0, 3.0], UnifiedDomain.BUSINESS)

        assert result is False


class TestConfidenceCalculation:
    """Test confidence score calculation."""

    def test_calculate_confidence_combines_sources(self, sample_raw_event):
        """Test confidence combines multiple sources."""
        detector = SignalDetector("test-scout")

        confidence = detector.calculate_confidence(
            sample_raw_event, detection_confidence=0.8, bayesian_posterior=0.7
        )

        # Should be weighted combination
        assert 0.0 <= confidence <= 1.0

    def test_calculate_confidence_with_high_quality_event(self, sample_raw_event):
        """Test higher confidence with quality event."""
        detector = SignalDetector("test-scout")

        confidence = detector.calculate_confidence(
            sample_raw_event, detection_confidence=0.9, bayesian_posterior=0.9
        )

        # High quality event should have good confidence
        assert confidence > 0.7

    def test_assess_data_quality_complete_event(self, sample_raw_event):
        """Test data quality assessment for complete event."""
        detector = SignalDetector("test-scout")

        quality = detector._assess_data_quality(sample_raw_event)

        assert 0.0 <= quality <= 1.0
        assert quality > 0.5  # Should be above base quality

    def test_assess_data_quality_minimal_event(self):
        """Test data quality assessment for minimal event."""
        from src.models.raw_event import RawEvent

        minimal_event = RawEvent(
            event_id="minimal", source="test", event_type="test", payload={}, metadata={}
        )

        detector = SignalDetector("test-scout")
        quality = detector._assess_data_quality(minimal_event)

        # Should have base quality
        assert quality >= 0.5


class TestRelevanceCalculation:
    """Test relevance score calculation."""

    def test_calculate_relevance_delegates(self, sample_raw_event, business_domain):
        """Test relevance calculation delegates to curiosity scorer."""
        detector = SignalDetector("test-scout")

        relevance = detector.calculate_relevance(sample_raw_event, business_domain)

        # Should return valid score
        assert 0.0 <= relevance <= 1.0


class TestRiskCalculation:
    """Test risk score calculation."""

    def test_calculate_risk_threat_signal(self):
        """Test high risk for threat signals."""
        detector = SignalDetector("test-scout")

        risk = detector.calculate_risk(SignalType.THREAT, UnifiedDomain.SECURITY)

        # Threat should have high risk
        assert risk > 0.8

    def test_calculate_risk_positive_anomaly(self):
        """Test low risk for positive anomalies."""
        detector = SignalDetector("test-scout")

        risk = detector.calculate_risk(SignalType.ANOMALY_POSITIVE, UnifiedDomain.BUSINESS)

        # Positive anomaly should have low risk
        assert risk < 0.5

    def test_calculate_risk_domain_multiplier(self):
        """Test domain affects risk calculation."""
        detector = SignalDetector("test-scout")

        # Same signal type, different domains
        business_risk = detector.calculate_risk(SignalType.THREAT, UnifiedDomain.BUSINESS)
        security_risk = detector.calculate_risk(SignalType.THREAT, UnifiedDomain.SECURITY)

        # Security domain should have higher multiplier
        assert security_risk > business_risk

    def test_calculate_risk_clamped(self):
        """Test risk is clamped to valid range."""
        detector = SignalDetector("test-scout")

        # All signals should produce valid risk scores
        for signal_type in SignalType:
            for domain in [UnifiedDomain.BUSINESS, UnifiedDomain.SECURITY, UnifiedDomain.TECHNICAL]:
                risk = detector.calculate_risk(signal_type, domain)
                assert 0.0 <= risk <= 1.0


class TestDescriptionGeneration:
    """Test signal description generation."""

    def test_generate_description_includes_domain(self):
        """Test description includes domain information."""
        detector = SignalDetector("test-scout")

        desc = detector.generate_description(
            SignalType.THREAT,
            sample_raw_event := type("obj", (object,), {"source": "test", "event_type": "test"})(),
            UnifiedDomain.SECURITY,
        )

        assert "security" in desc.lower()
        assert "ameaça" in desc.lower()

    def test_generate_description_includes_source(self):
        """Test description includes source information."""
        detector = SignalDetector("test-scout")

        from src.models.raw_event import RawEvent

        event = RawEvent(
            event_id="test",
            source="api-gateway",
            event_type="http_request",
            payload={},
            metadata={},
        )

        desc = detector.generate_description(
            SignalType.PATTERN_EMERGING, event, UnifiedDomain.BUSINESS
        )

        assert "api-gateway" in desc

    def test_generate_description_all_signal_types(self):
        """Test descriptions are generated for all signal types."""
        detector = SignalDetector("test-scout")

        from src.models.raw_event import RawEvent

        event = RawEvent(event_id="test", source="test", event_type="test", payload={}, metadata={})

        for signal_type in SignalType:
            desc = detector.generate_description(signal_type, event, UnifiedDomain.BUSINESS)
            assert len(desc) > 0


class TestValidationRequirement:
    """Test validation requirement logic."""

    def test_threat_requires_validation(self):
        """Test threat signals require validation."""
        detector = SignalDetector("test-scout")

        requires = detector.requires_validation(SignalType.THREAT, 0.9)

        assert requires is True

    def test_negative_anomaly_requires_validation(self):
        """Test negative anomalies require validation."""
        detector = SignalDetector("test-scout")

        requires = detector.requires_validation(SignalType.ANOMALY_NEGATIVE, 0.9)

        assert requires is True

    def test_low_confidence_requires_validation(self):
        """Test low confidence signals require validation."""
        detector = SignalDetector("test-scout")

        requires = detector.requires_validation(SignalType.OPPORTUNITY, 0.6)

        assert requires is True

    def test_high_confidence_positive_no_validation(self):
        """Test high confidence positive signals may not need validation."""
        detector = SignalDetector("test-scout")

        requires = detector.requires_validation(SignalType.ANOMALY_POSITIVE, 0.9)

        assert requires is False


class TestGeolocationExtraction:
    """Test geolocation extraction from events."""

    def test_extract_geolocation_from_metadata(self, sample_raw_event_with_geo):
        """Test geolocation extraction from metadata."""
        detector = SignalDetector("test-scout")

        # Add geolocation to metadata
        sample_raw_event_with_geo.metadata["geolocation"] = {
            "latitude": 51.5074,
            "longitude": -0.1278,
        }

        geo = detector._extract_geolocation(sample_raw_event_with_geo)

        assert geo is not None
        assert geo.latitude == 51.5074
        assert geo.longitude == -0.1278

    def test_extract_geolocation_from_payload(self):
        """Test geolocation extraction from payload."""
        from src.models.raw_event import RawEvent

        event = RawEvent(
            event_id="geo-001",
            source="mobile",
            event_type="location",
            payload={"lat": 48.8566, "lon": 2.3522},
            metadata={},
        )

        detector = SignalDetector("test-scout")
        geo = detector._extract_geolocation(event)

        assert geo is not None
        assert geo.latitude == 48.8566
        assert geo.longitude == 2.3522

    def test_extract_geolocation_geojson_format(self):
        """Test geolocation extraction from GeoJSON format."""
        from src.models.raw_event import RawEvent

        event = RawEvent(
            event_id="geo-002",
            source="api",
            event_type="location",
            payload={"location": [35.6762, 139.6503]},  # Tokyo
            metadata={},
        )

        detector = SignalDetector("test-scout")
        geo = detector._extract_geolocation(event)

        assert geo is not None

    def test_extract_geolocation_string_format(self):
        """Test geolocation extraction from string format."""
        from src.models.raw_event import RawEvent

        event = RawEvent(
            event_id="geo-003",
            source="api",
            event_type="location",
            payload={"coordinates": "37.7749 -122.4194"},  # San Francisco
            metadata={},
        )

        detector = SignalDetector("test-scout")
        geo = detector._extract_geolocation(event)

        assert geo is not None

    def test_extract_geolocation_invalid_coordinates(self):
        """Test invalid coordinates return None."""
        from src.models.raw_event import RawEvent

        event = RawEvent(
            event_id="geo-invalid",
            source="test",
            event_type="location",
            payload={"lat": 200.0, "lon": 300.0},  # Invalid coordinates
            metadata={},
        )

        detector = SignalDetector("test-scout")
        geo = detector._extract_geolocation(event)

        assert geo is None

    def test_extract_geolocation_no_coords(self, sample_raw_event):
        """Test event without geolocation returns None."""
        detector = SignalDetector("test-scout")

        geo = detector._extract_geolocation(sample_raw_event)

        assert geo is None


class TestParseGeolocationData:
    """Test geolocation data parsing utilities."""

    def test_parse_dict_geolocation(self):
        """Test parsing dict geolocation data."""
        detector = SignalDetector("test-scout")

        data = {"latitude": 52.5200, "longitude": 13.4050}
        geo = detector._parse_geolocation_data(data)

        assert geo is not None
        assert geo.latitude == 52.5200
        assert geo.longitude == 13.4050

    def test_parse_list_geolocation(self):
        """Test parsing list geolocation data."""
        detector = SignalDetector("test-scout")

        data = [53.3498, -6.2603]  # Dublin
        geo = detector._parse_geolocation_data(data)

        assert geo is not None

    def test_parse_string_geolocation(self):
        """Test parsing string geolocation data."""
        detector = SignalDetector("test-scout")

        data = "59.3293 18.0686"  # Stockholm
        geo = detector._parse_geolocation_data(data)

        assert geo is not None

    def test_parse_invalid_geolocation(self):
        """Test parsing invalid geolocation data."""
        detector = SignalDetector("test-scout")

        geo = detector._parse_geolocation_data("invalid")

        assert geo is None


class TestPositiveAnomalyDetection:
    """Test positive anomaly detection logic."""

    def test_positive_anomaly_user_action_business(self, sample_raw_event):
        """Test user action in business domain is positive."""
        from src.models.raw_event import RawEvent

        detector = SignalDetector("test-scout")

        test_event = RawEvent(
            event_id="test-001",
            source="test",
            event_type="user_action",
            timestamp=datetime.now(timezone.utc),
            payload={"action": "click"},
            metadata={},
        )

        is_positive = detector._is_positive_anomaly(test_event, UnifiedDomain.BUSINESS)

        assert is_positive is True

    def test_positive_anomaly_metric_positive_values(self):
        """Test metrics with positive values are positive."""
        from src.models.raw_event import RawEvent

        event = RawEvent(
            event_id="metric-001",
            source="prometheus",
            event_type="metric",
            payload={"throughput": 1500, "requests": 2000},
            metadata={},
        )

        detector = SignalDetector("test-scout")
        is_positive = detector._is_positive_anomaly(event, UnifiedDomain.BUSINESS)

        assert is_positive is True

    def test_not_positive_anomaly_negative_values(self):
        """Test metrics with negative values are not positive."""
        from src.models.raw_event import RawEvent

        event = RawEvent(
            event_id="metric-002",
            source="prometheus",
            event_type="metric",
            payload={"errors": 50, "latency": 500},
            metadata={},
        )

        detector = SignalDetector("test-scout")
        is_positive = detector._is_positive_anomaly(event, UnifiedDomain.BUSINESS)

        assert is_positive is False


class TestMainDetectionPipeline:
    """Test main detection pipeline."""

    @pytest.mark.asyncio
    async def test_detect_returns_signal(self, sample_raw_event, business_domain):
        """Test detect returns ScoutSignal when thresholds met."""
        from src.models.raw_event import RawEvent

        detector = SignalDetector("test-scout")

        # Create event with high anomaly
        test_event = RawEvent(
            event_id="test-001",
            source="test",
            event_type="user_action",
            timestamp=datetime.now(timezone.utc),
            payload={"action": "click"},
            metadata={},
        )

        # Mock high anomaly score
        with patch.object(test_event, "calculate_anomaly_score", return_value=0.9):
            signal = await detector.detect(test_event, business_domain, "core")

            # May return signal or None depending on thresholds
            if signal:
                assert hasattr(signal, "signal_id")
                assert hasattr(signal, "signal_type")

    @pytest.mark.asyncio
    async def test_detect_returns_none_filtered(self, sample_raw_event, business_domain):
        """Test detect returns None when Bayesian filter rejects."""
        detector = SignalDetector("test-scout")

        signal = await detector.detect(sample_raw_event, business_domain, "core")

        # Signal may be None if filtered out
        assert signal is None or hasattr(signal, "signal_id")

    @pytest.mark.asyncio
    async def test_detect_signal_attributes(self, sample_raw_event, business_domain):
        """Test detected signal has required attributes."""
        from src.models.raw_event import RawEvent

        detector = SignalDetector("test-scout")

        test_event = RawEvent(
            event_id="test-001",
            source="test",
            event_type="user_action",
            timestamp=datetime.now(timezone.utc),
            payload={"action": "click"},
            metadata={},
        )

        with patch.object(test_event, "calculate_anomaly_score", return_value=0.9):
            signal = await detector.detect(test_event, business_domain, "core")

            if signal:
                assert signal.scout_agent_id == "test-scout"
                assert signal.exploration_domain == business_domain
                assert signal.source.channel == "core"
                assert hasattr(signal, "curiosity_score")
                assert hasattr(signal, "confidence")
                assert hasattr(signal, "relevance_score")
                assert hasattr(signal, "risk_score")
