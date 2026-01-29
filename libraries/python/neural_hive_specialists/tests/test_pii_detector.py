"""
Testes unitários para PIIDetector.

Cobertura: inicialização, detecção de PII em pt/en, fallback de idioma não suportado,
estratégias de anonimização (replace, mask, redact, hash), metadados de detecção.
"""

import pytest
import sys
from unittest.mock import Mock, MagicMock, patch, create_autospec
from typing import List, Dict, Any

# Mock Presidio modules antes de qualquer import
presidio_analyzer_mock = MagicMock()
presidio_anonymizer_mock = MagicMock()
sys.modules["presidio_analyzer"] = presidio_analyzer_mock
sys.modules["presidio_analyzer.nlp_engine"] = MagicMock()
sys.modules["presidio_anonymizer"] = presidio_anonymizer_mock
sys.modules["presidio_anonymizer.entities"] = MagicMock()

from neural_hive_specialists.compliance.pii_detector import PIIDetector


@pytest.fixture
def mock_config():
    """Cria configuração mockada para testes."""
    config = Mock()
    config.enable_pii_detection = True
    config.pii_detection_languages = ["pt", "en"]
    config.pii_entities_to_detect = [
        "PERSON",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "LOCATION",
    ]
    config.pii_anonymization_strategy = "replace"
    return config


@pytest.fixture
def mock_analyzer_result():
    """Cria resultado mockado do Presidio Analyzer."""
    result = Mock()
    result.entity_type = "PERSON"
    result.start = 0
    result.end = 11
    result.score = 0.85
    return result


@pytest.fixture
def mock_anonymized_result():
    """Cria resultado mockado do Presidio Anonymizer."""
    result = Mock()
    result.text = "<PERSON> mora em <LOCATION>"
    return result


@pytest.mark.unit
class TestPIIDetectorInitialization:
    """Testes de inicialização do PIIDetector."""

    def test_initialization_disabled(self):
        """Testa inicialização quando PII detection está desabilitado."""
        config = Mock()
        config.enable_pii_detection = False

        detector = PIIDetector(config)

        assert detector.enabled is False
        assert not hasattr(detector, "analyzer")

    def test_initialization_success(self, mock_config):
        """Testa inicialização bem-sucedida com engines Presidio."""
        # Mock Presidio imports dentro do __init__
        with patch("presidio_analyzer.AnalyzerEngine") as mock_analyzer, patch(
            "presidio_analyzer.nlp_engine.NlpEngineProvider"
        ) as mock_nlp_provider, patch(
            "presidio_anonymizer.AnonymizerEngine"
        ) as mock_anonymizer, patch(
            "presidio_anonymizer.entities.OperatorConfig"
        ):
            mock_nlp_engine = Mock()
            mock_nlp_provider.return_value.create_engine.return_value = mock_nlp_engine

            detector = PIIDetector(mock_config)

            assert detector.enabled is True
            assert detector.supported_languages == ["pt", "en"]
            mock_analyzer.assert_called_once_with(
                nlp_engine=mock_nlp_engine, supported_languages=["pt", "en"]
            )
            mock_anonymizer.assert_called_once()

    def test_initialization_handles_unsupported_language(self, mock_config):
        """Testa que idiomas não suportados são ignorados."""
        mock_config.pii_detection_languages = ["pt", "fr", "en"]  # fr não suportado

        with patch("presidio_analyzer.AnalyzerEngine"), patch(
            "presidio_analyzer.nlp_engine.NlpEngineProvider"
        ) as mock_nlp_provider, patch("presidio_anonymizer.AnonymizerEngine"), patch(
            "presidio_anonymizer.entities.OperatorConfig"
        ):
            mock_nlp_engine = Mock()
            mock_nlp_provider.return_value.create_engine.return_value = mock_nlp_engine

            detector = PIIDetector(mock_config)

            # Apenas pt e en devem estar nos idiomas suportados
            assert "fr" not in detector.supported_languages
            assert "pt" in detector.supported_languages
            assert "en" in detector.supported_languages

    def test_initialization_handles_spacy_model_error(self, mock_config):
        """Testa que erro ao carregar modelo spaCy desabilita PII detection."""
        with patch(
            "presidio_analyzer.nlp_engine.NlpEngineProvider"
        ) as mock_nlp_provider:
            mock_nlp_provider.return_value.create_engine.side_effect = Exception(
                "spaCy model not found"
            )

            detector = PIIDetector(mock_config)

            assert detector.enabled is False

    def test_initialization_handles_presidio_import_error(self, mock_config):
        """Testa que erro ao importar Presidio desabilita PII detection."""
        # Simular falha de import mockando builtins.__import__
        original_import = __builtins__.__import__

        def mock_import(name, *args, **kwargs):
            if "presidio" in name:
                raise ImportError("presidio not installed")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            detector = PIIDetector(mock_config)
            assert detector.enabled is False


@pytest.mark.unit
class TestDetectPII:
    """Testes do método detect_pii."""

    @pytest.fixture
    def detector(self, mock_config):
        """Cria detector com Presidio mockado."""
        with patch("presidio_analyzer.AnalyzerEngine") as mock_analyzer, patch(
            "presidio_analyzer.nlp_engine.NlpEngineProvider"
        ) as mock_nlp_provider, patch("presidio_anonymizer.AnonymizerEngine"), patch(
            "presidio_anonymizer.entities.OperatorConfig"
        ):
            mock_nlp_engine = Mock()
            mock_nlp_provider.return_value.create_engine.return_value = mock_nlp_engine
            mock_analyzer_instance = Mock()
            mock_analyzer.return_value = mock_analyzer_instance

            detector = PIIDetector(mock_config)
            detector.analyzer = mock_analyzer_instance

            return detector

    def test_detect_pii_success_pt(self, detector, mock_analyzer_result):
        """Testa detecção bem-sucedida de PII em português."""
        detector.analyzer.analyze.return_value = [mock_analyzer_result]

        results = detector.detect_pii("João Silva mora em São Paulo", language="pt")

        assert len(results) == 1
        assert results[0].entity_type == "PERSON"
        detector.analyzer.analyze.assert_called_once_with(
            text="João Silva mora em São Paulo",
            language="pt",
            entities=detector.config.pii_entities_to_detect,
        )

    def test_detect_pii_success_en(self, detector, mock_analyzer_result):
        """Testa detecção bem-sucedida de PII em inglês."""
        detector.analyzer.analyze.return_value = [mock_analyzer_result]

        results = detector.detect_pii("John Smith lives in New York", language="en")

        assert len(results) == 1
        detector.analyzer.analyze.assert_called_once()

    def test_detect_pii_empty_text(self, detector):
        """Testa que texto vazio retorna lista vazia."""
        results = detector.detect_pii("", language="pt")

        assert results == []
        detector.analyzer.analyze.assert_not_called()

    def test_detect_pii_no_entities_found(self, detector):
        """Testa que nenhuma entidade detectada retorna lista vazia."""
        detector.analyzer.analyze.return_value = []

        results = detector.detect_pii("texto sem PII", language="pt")

        assert results == []

    def test_detect_pii_unsupported_language_fallback(
        self, detector, mock_analyzer_result
    ):
        """Testa fallback para inglês quando idioma não suportado."""
        detector.supported_languages = ["pt", "en"]
        detector.analyzer.analyze.return_value = [mock_analyzer_result]

        results = detector.detect_pii("Some text", language="fr")

        # Deve fazer fallback para 'en'
        detector.analyzer.analyze.assert_called_once()
        call_args = detector.analyzer.analyze.call_args
        assert call_args[1]["language"] == "en"

    def test_detect_pii_handles_analysis_error(self, detector):
        """Testa que erro na análise retorna lista vazia."""
        detector.analyzer.analyze.side_effect = Exception("Analysis error")

        results = detector.detect_pii("texto qualquer", language="pt")

        assert results == []

    def test_detect_pii_disabled(self, mock_config):
        """Testa que PII detection desabilitado retorna lista vazia."""
        mock_config.enable_pii_detection = False
        detector = PIIDetector(mock_config)

        results = detector.detect_pii("João Silva", language="pt")

        assert results == []


@pytest.mark.unit
class TestAnonymizeText:
    """Testes do método anonymize_text."""

    @pytest.fixture
    def detector(self, mock_config):
        """Cria detector com Presidio mockado."""
        with patch("presidio_analyzer.AnalyzerEngine") as mock_analyzer, patch(
            "presidio_analyzer.nlp_engine.NlpEngineProvider"
        ) as mock_nlp_provider, patch(
            "presidio_anonymizer.AnonymizerEngine"
        ) as mock_anonymizer, patch(
            "presidio_anonymizer.entities.OperatorConfig"
        ):
            mock_nlp_engine = Mock()
            mock_nlp_provider.return_value.create_engine.return_value = mock_nlp_engine
            mock_analyzer_instance = Mock()
            mock_anonymizer_instance = Mock()
            mock_analyzer.return_value = mock_analyzer_instance
            mock_anonymizer.return_value = mock_anonymizer_instance

            detector = PIIDetector(mock_config)
            detector.analyzer = mock_analyzer_instance
            detector.anonymizer = mock_anonymizer_instance

            return detector

    def test_anonymize_text_success(
        self, detector, mock_analyzer_result, mock_anonymized_result
    ):
        """Testa anonimização bem-sucedida de texto."""
        detector.analyzer.analyze.return_value = [mock_analyzer_result]
        detector.anonymizer.anonymize.return_value = mock_anonymized_result

        anonymized_text, metadata = detector.anonymize_text(
            "João Silva mora em São Paulo", language="pt"
        )

        assert anonymized_text == "<PERSON> mora em <LOCATION>"
        assert len(metadata) == 1
        assert metadata[0]["entity_type"] == "PERSON"
        assert metadata[0]["anonymized"] is True

    def test_anonymize_text_no_pii_detected(self, detector):
        """Testa que texto sem PII retorna original."""
        detector.analyzer.analyze.return_value = []

        anonymized_text, metadata = detector.anonymize_text(
            "texto sem PII", language="pt"
        )

        assert anonymized_text == "texto sem PII"
        assert metadata == []

    def test_anonymize_text_empty_text(self, detector):
        """Testa que texto vazio retorna vazio."""
        anonymized_text, metadata = detector.anonymize_text("", language="pt")

        assert anonymized_text == ""
        assert metadata == []

    def test_anonymize_text_metadata_shape(
        self, detector, mock_analyzer_result, mock_anonymized_result
    ):
        """Testa formato correto dos metadados."""
        detector.analyzer.analyze.return_value = [mock_analyzer_result]
        detector.anonymizer.anonymize.return_value = mock_anonymized_result

        _, metadata = detector.anonymize_text("João Silva", language="pt")

        assert len(metadata) == 1
        meta = metadata[0]
        assert "entity_type" in meta
        assert "start" in meta
        assert "end" in meta
        assert "score" in meta
        assert "anonymized" in meta

    def test_anonymize_text_handles_error(self, detector):
        """Testa que erro na anonimização retorna texto original."""
        detector.analyzer.analyze.side_effect = Exception("Anonymization error")

        anonymized_text, metadata = detector.anonymize_text("João Silva", language="pt")

        assert anonymized_text == "João Silva"
        assert metadata == []

    def test_anonymize_text_unsupported_language_fallback(
        self, detector, mock_analyzer_result, mock_anonymized_result
    ):
        """Testa fallback de idioma não suportado."""
        detector.supported_languages = ["pt", "en"]
        detector.analyzer.analyze.return_value = [mock_analyzer_result]
        detector.anonymizer.anonymize.return_value = mock_anonymized_result

        anonymized_text, metadata = detector.anonymize_text("Some text", language="de")

        # Deve fazer fallback para 'en'
        detector.analyzer.analyze.assert_called_once()
        call_args = detector.analyzer.analyze.call_args
        assert call_args[1]["language"] == "en"


@pytest.mark.unit
class TestAnonymizeDict:
    """Testes do método anonymize_dict."""

    @pytest.fixture
    def detector(self, mock_config):
        """Cria detector com Presidio mockado."""
        with patch("presidio_analyzer.AnalyzerEngine") as mock_analyzer, patch(
            "presidio_analyzer.nlp_engine.NlpEngineProvider"
        ) as mock_nlp_provider, patch(
            "presidio_anonymizer.AnonymizerEngine"
        ) as mock_anonymizer, patch(
            "presidio_anonymizer.entities.OperatorConfig"
        ):
            mock_nlp_engine = Mock()
            mock_nlp_provider.return_value.create_engine.return_value = mock_nlp_engine
            mock_analyzer_instance = Mock()
            mock_anonymizer_instance = Mock()
            mock_analyzer.return_value = mock_analyzer_instance
            mock_anonymizer.return_value = mock_anonymizer_instance

            detector = PIIDetector(mock_config)
            detector.analyzer = mock_analyzer_instance
            detector.anonymizer = mock_anonymizer_instance

            return detector

    def test_anonymize_dict_simple_field(
        self, detector, mock_analyzer_result, mock_anonymized_result
    ):
        """Testa anonimização de campo simples em dicionário."""
        detector.analyzer.analyze.return_value = [mock_analyzer_result]
        detector.anonymizer.anonymize.return_value = mock_anonymized_result

        data = {"description": "João Silva mora em São Paulo"}
        fields_to_scan = ["description"]

        anonymized_data, metadata = detector.anonymize_dict(
            data, fields_to_scan, language="pt"
        )

        assert anonymized_data["description"] == "<PERSON> mora em <LOCATION>"
        assert len(metadata) == 1
        assert metadata[0]["field"] == "description"

    def test_anonymize_dict_nested_field(
        self, detector, mock_analyzer_result, mock_anonymized_result
    ):
        """Testa anonimização de campo aninhado."""
        detector.analyzer.analyze.return_value = [mock_analyzer_result]
        detector.anonymizer.anonymize.return_value = mock_anonymized_result

        data = {"opinion": {"reasoning": "João Silva é o responsável"}}
        fields_to_scan = ["opinion.reasoning"]

        anonymized_data, metadata = detector.anonymize_dict(
            data, fields_to_scan, language="pt"
        )

        assert anonymized_data["opinion"]["reasoning"] == "<PERSON> mora em <LOCATION>"
        assert len(metadata) == 1
        assert metadata[0]["field"] == "opinion.reasoning"

    def test_anonymize_dict_no_pii_found(self, detector):
        """Testa que dicionário sem PII permanece inalterado."""
        detector.analyzer.analyze.return_value = []

        data = {"description": "texto sem PII"}
        fields_to_scan = ["description"]

        anonymized_data, metadata = detector.anonymize_dict(
            data, fields_to_scan, language="pt"
        )

        assert anonymized_data["description"] == "texto sem PII"
        assert metadata == []

    def test_anonymize_dict_disabled(self, mock_config):
        """Testa que detector desabilitado retorna dados originais."""
        mock_config.enable_pii_detection = False
        detector = PIIDetector(mock_config)

        data = {"description": "João Silva"}
        anonymized_data, metadata = detector.anonymize_dict(
            data, ["description"], language="pt"
        )

        assert anonymized_data == data
        assert metadata == []


@pytest.mark.unit
class TestAnonymizationStrategies:
    """Testes das estratégias de anonimização."""

    def test_strategy_replace(self, mock_config):
        """Testa estratégia replace (padrão)."""
        mock_config.pii_anonymization_strategy = "replace"

        with patch("presidio_analyzer.AnalyzerEngine"), patch(
            "presidio_analyzer.nlp_engine.NlpEngineProvider"
        ) as mock_nlp_provider, patch("presidio_anonymizer.AnonymizerEngine"), patch(
            "presidio_anonymizer.entities.OperatorConfig"
        ):
            mock_nlp_engine = Mock()
            mock_nlp_provider.return_value.create_engine.return_value = mock_nlp_engine

            detector = PIIDetector(mock_config)
            operators = detector._get_anonymization_operators()

            # Replace usa None (padrão Presidio)
            assert operators is None

    def test_strategy_mask(self, mock_config):
        """Testa estratégia mask."""
        mock_config.pii_anonymization_strategy = "mask"

        with patch("presidio_analyzer.AnalyzerEngine"), patch(
            "presidio_analyzer.nlp_engine.NlpEngineProvider"
        ) as mock_nlp_provider, patch("presidio_anonymizer.AnonymizerEngine"), patch(
            "presidio_anonymizer.entities.OperatorConfig"
        ) as mock_op:
            mock_nlp_engine = Mock()
            mock_nlp_provider.return_value.create_engine.return_value = mock_nlp_engine

            detector = PIIDetector(mock_config)
            detector.OperatorConfig = mock_op
            operators = detector._get_anonymization_operators()

            # Mask deve criar operadores para cada entidade
            assert operators is not None
            assert "PERSON" in operators

    def test_strategy_redact(self, mock_config):
        """Testa estratégia redact."""
        mock_config.pii_anonymization_strategy = "redact"

        with patch("presidio_analyzer.AnalyzerEngine"), patch(
            "presidio_analyzer.nlp_engine.NlpEngineProvider"
        ) as mock_nlp_provider, patch("presidio_anonymizer.AnonymizerEngine"), patch(
            "presidio_anonymizer.entities.OperatorConfig"
        ) as mock_op:
            mock_nlp_engine = Mock()
            mock_nlp_provider.return_value.create_engine.return_value = mock_nlp_engine

            detector = PIIDetector(mock_config)
            detector.OperatorConfig = mock_op
            operators = detector._get_anonymization_operators()

            assert operators is not None
            assert "PERSON" in operators

    def test_strategy_hash(self, mock_config):
        """Testa estratégia hash."""
        mock_config.pii_anonymization_strategy = "hash"

        with patch("presidio_analyzer.AnalyzerEngine"), patch(
            "presidio_analyzer.nlp_engine.NlpEngineProvider"
        ) as mock_nlp_provider, patch("presidio_anonymizer.AnonymizerEngine"), patch(
            "presidio_anonymizer.entities.OperatorConfig"
        ) as mock_op:
            mock_nlp_engine = Mock()
            mock_nlp_provider.return_value.create_engine.return_value = mock_nlp_engine

            detector = PIIDetector(mock_config)
            detector.OperatorConfig = mock_op
            operators = detector._get_anonymization_operators()

            assert operators is not None
            assert "PERSON" in operators

    def test_strategy_unknown_fallback(self, mock_config):
        """Testa que estratégia desconhecida usa replace como fallback."""
        mock_config.pii_anonymization_strategy = "unknown_strategy"

        with patch("presidio_analyzer.AnalyzerEngine"), patch(
            "presidio_analyzer.nlp_engine.NlpEngineProvider"
        ) as mock_nlp_provider, patch("presidio_anonymizer.AnonymizerEngine"), patch(
            "presidio_anonymizer.entities.OperatorConfig"
        ):
            mock_nlp_engine = Mock()
            mock_nlp_provider.return_value.create_engine.return_value = mock_nlp_engine

            detector = PIIDetector(mock_config)
            operators = detector._get_anonymization_operators()

            # Deve usar None (replace padrão)
            assert operators is None


@pytest.mark.unit
class TestNestedValueHelpers:
    """Testes dos métodos auxiliares de valores aninhados."""

    def test_get_nested_value_simple(self):
        """Testa obtenção de valor simples."""
        data = {"field": "value"}
        value = PIIDetector._get_nested_value(data, "field")
        assert value == "value"

    def test_get_nested_value_nested(self):
        """Testa obtenção de valor aninhado."""
        data = {"level1": {"level2": {"level3": "deep_value"}}}
        value = PIIDetector._get_nested_value(data, "level1.level2.level3")
        assert value == "deep_value"

    def test_get_nested_value_not_found(self):
        """Testa que None é retornado para path inexistente."""
        data = {"field": "value"}
        value = PIIDetector._get_nested_value(data, "nonexistent")
        assert value is None

    def test_set_nested_value_simple(self):
        """Testa definição de valor simples."""
        data = {}
        PIIDetector._set_nested_value(data, "field", "new_value")
        assert data["field"] == "new_value"

    def test_set_nested_value_nested(self):
        """Testa definição de valor aninhado."""
        data = {}
        PIIDetector._set_nested_value(data, "level1.level2.level3", "deep_value")
        assert data["level1"]["level2"]["level3"] == "deep_value"

    def test_set_nested_value_partial_path_exists(self):
        """Testa definição quando path parcial já existe."""
        data = {"level1": {"existing": "value"}}
        PIIDetector._set_nested_value(data, "level1.level2", "new_value")
        assert data["level1"]["level2"] == "new_value"
        assert data["level1"]["existing"] == "value"
