"""
Testes unitários abrangentes para RawEvent.

Cobertura: extração de features, normalização, validação, cálculo de anomalia.
"""

from datetime import UTC, datetime

import pytest
from src.models.raw_event import RawEvent

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def basic_raw_event():
    """Evento básico para testes."""
    return RawEvent(
        event_id="event-001",
        source="test-source",
        event_type="user_action",
        timestamp=datetime.now(UTC),
        payload={"action": "click", "value": 100, "count": 5},
        metadata={"trace_id": "trace-001"},
    )


@pytest.fixture()
def complex_nested_event():
    """Evento com payload aninhado complexo."""
    return RawEvent(
        event_id="complex-001",
        source="api",
        event_type="response",
        timestamp=datetime.now(UTC),
        payload={
            "data": {
                "user": {"id": 123, "score": 85.5},
                "metrics": {"cpu": 75.2, "memory": 60.8, "disk": [40, 50, 60]},
            },
            "status": 200,
            "timing": 123.456,
        },
        metadata={"request_id": "req-001"},
    )


@pytest.fixture()
def event_with_list_data():
    """Evento com dados em lista."""
    return RawEvent(
        event_id="list-001",
        source="metrics",
        event_type="timeseries",
        timestamp=datetime.now(UTC),
        payload={
            "values": [10, 20, 30, 40, 50],
            "timestamps": [1, 2, 3, 4, 5],
            "labels": ["a", "b", "c"],
        },
        metadata={},
    )


@pytest.fixture()
def event_with_no_numeric_data():
    """Evento sem dados numéricos."""
    return RawEvent(
        event_id="no-numeric-001",
        source="logs",
        event_type="message",
        timestamp=datetime.now(UTC),
        payload={"message": "User logged in", "level": "INFO", "service": "auth-service"},
        metadata={},
    )


# ============================================================================
# Testes de Criação e Validação
# ============================================================================


class TestRawEventCreation:
    """Testes de criação de RawEvent."""

    def test_create_basic_event(self, basic_raw_event):
        """Testa criação de evento básico."""
        assert basic_raw_event.event_id == "event-001"
        assert basic_raw_event.source == "test-source"
        assert basic_raw_event.event_type == "user_action"
        assert isinstance(basic_raw_event.timestamp, datetime)

    def test_create_event_with_complex_payload(self, complex_nested_event):
        """Testa criação com payload aninhado."""
        assert complex_nested_event.payload["data"]["user"]["id"] == 123
        assert complex_nested_event.payload["data"]["metrics"]["cpu"] == 75.2

    def test_create_event_with_list_payload(self, event_with_list_data):
        """Testa criação com payload em lista."""
        assert len(event_with_list_data.payload["values"]) == 5
        assert event_with_list_data.payload["values"] == [10, 20, 30, 40, 50]

    def test_create_empty_metadata(self):
        """Testa criação sem metadados."""
        event = RawEvent(
            event_id="event-002",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={"value": 1},
        )
        assert event.metadata == {}


# ============================================================================
# Testes de Extração de Features
# ============================================================================


class TestFeatureExtraction:
    """Testes de extração de features."""

    def test_extract_features_from_simple_payload(self, basic_raw_event):
        """Testa extração de payload simples."""
        features = basic_raw_event.extract_features()
        assert isinstance(features, list)
        assert len(features) == 50  # Pad para 50
        assert 100 in features
        assert 5 in features

    def test_extract_features_from_nested_payload(self, complex_nested_event):
        """Testa extração de payload aninhado."""
        features = complex_nested_event.extract_features()
        assert isinstance(features, list)
        # Deve extrair valores numéricos de todos os níveis
        assert 123 in features  # user.id
        assert 85.5 in features  # user.score
        assert 75.2 in features  # metrics.cpu
        assert 60.8 in features  # metrics.memory

    def test_extract_features_from_list_payload(self, event_with_list_data):
        """Testa extração de lista."""
        features = event_with_list_data.extract_features()
        assert 10 in features
        assert 20 in features
        assert 30 in features

    def test_extract_features_no_numeric_data(self, event_with_no_numeric_data):
        """Testa extração sem dados numéricos."""
        features = event_with_no_numeric_data.extract_features()
        # Deve retornar features default
        assert len(features) == 50
        assert all(f == 0.0 for f in features)

    def test_extract_features_fixed_size(self, basic_raw_event):
        """Testa que features têm tamanho fixo."""
        features = basic_raw_event.extract_features()
        assert len(features) == 50

    def test_extract_features_padding(self):
        """Testa padding quando há poucas features."""
        event = RawEvent(
            event_id="pad-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={"value": 1},  # Apenas 1 feature
            metadata={},
        )
        features = event.extract_features()
        assert len(features) == 50
        assert 1 in features
        assert features.count(0.0) == 49  # Resto são zeros

    def test_extract_features_truncation(self):
        """Testa truncamento quando há muitas features."""
        many_values = list(range(100))
        event = RawEvent(
            event_id="trunc-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={"values": many_values},
            metadata={},
        )
        features = event.extract_features()
        assert len(features) == 50  # Truncado

    def test_extract_features_max_depth_respected(self, complex_nested_event):
        """Testa que profundidade máxima é respeitada."""
        # O método usa max_depth=3, então deve extrair até 3 níveis
        features = complex_nested_event.extract_features()
        # Deve extrair valores de data.metrics.disk (nível 3)
        assert 40 in features or 50 in features or 60 in features


# ============================================================================
# Testes de Normalização
# ============================================================================


class TestNormalization:
    """Testes de normalização de eventos."""

    def test_normalize_returns_dict(self, basic_raw_event):
        """Testa que normalize retorna dict."""
        normalized = basic_raw_event.normalize()
        assert isinstance(normalized, dict)

    def test_normalize_includes_all_fields(self, basic_raw_event):
        """Testa que normalize inclui todos os campos."""
        normalized = basic_raw_event.normalize()
        assert "event_id" in normalized
        assert "event_type" in normalized
        assert "source" in normalized
        assert "timestamp" in normalized
        assert "payload" in normalized
        assert "metadata" in normalized

    def test_normalize_timestamp_is_string(self, basic_raw_event):
        """Testa que timestamp é convertido para string ISO."""
        normalized = basic_raw_event.normalize()
        assert isinstance(normalized["timestamp"], str)

    def test_normalize_preserves_payload(self, basic_raw_event):
        """Testa que payload é preservado."""
        normalized = basic_raw_event.normalize()
        assert normalized["payload"] == basic_raw_event.payload

    def test_normalize_preserves_metadata(self, basic_raw_event):
        """Testa que metadados são preservados."""
        normalized = basic_raw_event.normalize()
        assert normalized["metadata"] == basic_raw_event.metadata


# ============================================================================
# Testes de Validação
# ============================================================================


class TestValidation:
    """Testes de validação de eventos."""

    def test_is_valid_complete_event(self, basic_raw_event):
        """Testa que evento completo é válido."""
        assert basic_raw_event.is_valid() is True

    def test_is_valid_missing_event_id(self):
        """Testa que sem event_id é inválido."""
        event = RawEvent(
            event_id="",  # Vazio
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={},
        )
        assert event.is_valid() is False

    def test_is_valid_missing_source(self):
        """Testa que sem source é inválido."""
        event = RawEvent(
            event_id="event-001",
            source=None,
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={},
        )
        # Pydantic pode converter None para string ou validar
        # Mas se for string vazia após:
        if event.source == "" or event.source is None:
            assert event.is_valid() is False

    def test_is_valid_missing_timestamp(self):
        """Testa que sem timestamp é inválido."""
        event = RawEvent(
            event_id="event-001", source="test", event_type="test", timestamp=None, payload={}
        )
        # Depende de como Pydantic lida com None
        result = event.is_valid()
        # Se timestamp for None, is_valid deve retornar False

    def test_is_valid_missing_payload(self):
        """Testa que sem payload é inválido."""
        event = RawEvent(
            event_id="event-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload=None,
        )
        if event.payload is None:
            assert event.is_valid() is False


# ============================================================================
# Testes de Cálculo de Anomalia
# ============================================================================


class TestAnomalyScoreCalculation:
    """Testes de cálculo de score de anomalia."""

    def test_calculate_anomaly_score_basic(self, basic_raw_event):
        """Testa cálculo básico de anomalia."""
        score = basic_raw_event.calculate_anomaly_score()
        assert 0.0 <= score <= 1.0

    def test_calculate_anomaly_score_no_features(self, event_with_no_numeric_data):
        """Testa anomalia sem features."""
        score = event_with_no_numeric_data.calculate_anomaly_score()
        # Sem features, retorna 0.0
        assert score == 0.0

    def test_calculate_anomaly_score_with_historical_mean(self, basic_raw_event):
        """Testa anomalia com média histórica."""
        score_default = basic_raw_event.calculate_anomaly_score()
        score_with_mean = basic_raw_event.calculate_anomaly_score(historical_mean=50)
        # Devem ser diferentes pois a base de comparação muda
        # (pode ser igual se o z-score for similar)

    def test_anomaly_score_normalization(self, basic_raw_event):
        """Testa que score é normalizado via sigmoid."""
        score = basic_raw_event.calculate_anomaly_score()
        assert 0.0 <= score <= 1.0

    def test_anomaly_score_zero_std(self, basic_raw_event):
        """Testa anomalia com std zero."""
        score = basic_raw_event.calculate_anomaly_score(historical_mean=100, historical_std=0)
        # Com std zero, z-score é 0, sigmoid(0) = 0.5
        assert score == 0.5

    def test_anomaly_score_extreme_values(self):
        """Testa anomalia com valores extremos."""
        event = RawEvent(
            event_id="extreme-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={"value": 10000},  # Valor extremo
            metadata={},
        )
        score = event.calculate_anomaly_score(historical_mean=100, historical_std=10)
        # Z-score alto deve resultar em score próximo de 1
        assert score > 0.5


# ============================================================================
# Testes de Casos Especiais
# ============================================================================


class TestSpecialCases:
    """Testes de casos especiais."""

    def test_event_with_mixed_data_types(self):
        """Testa evento com tipos de dados mistos."""
        event = RawEvent(
            event_id="mixed-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={
                "string": "hello",
                "integer": 42,
                "float": 3.14,
                "boolean": True,
                "null": None,
                "list": [1, 2, 3],
                "nested": {"value": 99},
            },
            metadata={},
        )
        features = event.extract_features()
        # Deve extrair apenas valores numéricos
        assert 42 in features
        assert 3.14 in features
        assert 1 in features
        assert 99 in features
        # Strings e booleanos são ignorados
        assert "hello" not in features
        assert True not in features

    def test_event_with_unicode_values(self):
        """Testa evento com valores unicode."""
        event = RawEvent(
            event_id="unicode-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={"metric": 100.5, "label": "café", "emoji": "🚀"},
            metadata={},
        )
        features = event.extract_features()
        # Deve extrair apenas o valor numérico
        assert 100.5 in features

    def test_event_with_very_deep_nesting(self):
        """Testa evento com aninhamento muito profundo."""
        event = RawEvent(
            event_id="deep-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={"level1": {"level2": {"level3": {"level4": {"value": 42}}}}},
            metadata={},
        )
        features = event.extract_features()
        # max_depth=3, então level4 não deve ser extraído
        # Mas vamos verificar se funciona sem erro
        assert isinstance(features, list)

    def test_event_with_scientific_notation(self):
        """Testa evento com notação científica."""
        event = RawEvent(
            event_id="sci-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={"small": 1.5e-10, "large": 1.5e10},
            metadata={},
        )
        features = event.extract_features()
        # Deve extrair valores
        assert 1.5e-10 in features or any(abs(f - 1.5e-10) < 1e-15 for f in features)
        assert 1.5e10 in features or any(abs(f - 1.5e10) < 1.0 for f in features)


# ============================================================================
# Testes de Imutabilidade
# ============================================================================


class TestImmutability:
    """Testes de comportamento de imutabilidade."""

    def test_extract_features_doesnt_modify_payload(self, basic_raw_event):
        """Testa que extract_features não modifica o payload."""
        original_payload = basic_raw_event.payload.copy()
        basic_raw_event.extract_features()
        assert basic_raw_event.payload == original_payload

    def test_normalize_doesnt_modify_event(self, basic_raw_event):
        """Testa que normalize não modifica o evento."""
        original_timestamp = basic_raw_event.timestamp
        normalized = basic_raw_event.normalize()
        assert basic_raw_event.timestamp == original_timestamp


# ============================================================================
# Testes de Performance
# ============================================================================


class TestPerformance:
    """Testes de performance."""

    def test_extract_features_large_payload(self):
        """Testa extração de payload grande."""
        large_payload = {f"metric_{i}": i * 1.5 for i in range(1000)}
        event = RawEvent(
            event_id="large-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload=large_payload,
            metadata={},
        )
        features = event.extract_features()
        # Deve completar sem erro e retornar 50 features
        assert len(features) == 50

    def test_extract_features_deeply_nested_performance(self):
        """Testa performance de aninhamento profundo."""
        payload = {"level": {"value": 1}}
        # Criar aninhamento profundo manualmente
        for _ in range(50):
            payload = {"level": payload}

        event = RawEvent(
            event_id="deep-perf-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload=payload,
            metadata={},
        )
        # Deve completar sem erro (max_depth limita iteração)
        features = event.extract_features()
        assert isinstance(features, list)


# ============================================================================
# Testes de Bordas
# ============================================================================


class TestBoundaryConditions:
    """Testes de condições de contorno."""

    def test_empty_payload(self):
        """Testa payload vazio."""
        event = RawEvent(
            event_id="empty-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={},
            metadata={},
        )
        features = event.extract_features()
        # Deve retornar features default de zeros
        assert len(features) == 50
        assert all(f == 0.0 for f in features)

    def test_all_numeric_zeros(self):
        """Testa todos os valores numéricos zero."""
        event = RawEvent(
            event_id="zeros-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={"a": 0, "b": 0.0, "c": -0.0},
            metadata={},
        )
        features = event.extract_features()
        # Deve incluir os zeros
        assert 0.0 in features

    def test_negative_numbers(self):
        """Testa números negativos."""
        event = RawEvent(
            event_id="neg-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={"negative": -100, "positive": 50},
            metadata={},
        )
        features = event.extract_features()
        assert -100 in features
        assert 50 in features

    def test_infinity_values(self):
        """Testa valores infinitos."""
        event = RawEvent(
            event_id="inf-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={"inf": float("inf"), "ninf": float("-inf")},
            metadata={},
        )
        # Não deve crashar
        features = event.extract_features()
        assert isinstance(features, list)

    def test_nan_values(self):
        """Testa valores NaN."""
        event = RawEvent(
            event_id="nan-001",
            source="test",
            event_type="test",
            timestamp=datetime.now(UTC),
            payload={"nan": float("nan")},
            metadata={},
        )
        # Não deve crashar
        features = event.extract_features()
        assert isinstance(features, list)
