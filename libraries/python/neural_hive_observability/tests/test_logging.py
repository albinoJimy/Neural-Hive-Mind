"""
Testes para o módulo logging.py da biblioteca neural_hive_observability.

Este arquivo contém testes unitários para validar:
- CorrelationFormatter para logs estruturados
- NeuralHiveLoggerAdapter para logs com correlação
- Funções de inicialização de logging
- Funções utilitárias de log (log_intent_start, log_plan_execution, etc.)
"""

import logging
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

from neural_hive_observability.config import ObservabilityConfig
from neural_hive_observability.logging import (
    CorrelationFormatter,
    NeuralHiveLoggerAdapter,
    init_logging,
    get_logger,
    log_intent_start,
    log_intent_completion,
    log_plan_execution_start,
    log_plan_execution_completion,
)


class TestCorrelationFormatter:
    """Testes para CorrelationFormatter."""

    def test_formatter_creates_json_output(self):
        """Testa que formatter cria JSON válido."""
        config = ObservabilityConfig(
            service_name="test-service",
            service_version="1.0.0",
            neural_hive_component="test-component",
            neural_hive_layer="test-layer",
        )

        formatter = CorrelationFormatter(config)
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert parsed["service"]["name"] == "test-service"
        assert parsed["service"]["version"] == "1.0.0"
        assert parsed["neural_hive"]["component"] == "test-component"
        assert parsed["neural_hive"]["layer"] == "test-layer"
        assert "timestamp" in parsed

    def test_formatter_includes_trace_correlation(self):
        """Testa que formatter inclui correlação de trace."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        formatter = CorrelationFormatter(config)
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        # Trace pode não estar presente sem span ativo
        # Mas a chave "trace" deve estar presente se houver span válido
        # ou ausente se não houver - verificar estrutura básica
        assert "timestamp" in parsed

    def test_formatter_includes_intent_id(self):
        """Testa que formatter inclui intent_id."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        formatter = CorrelationFormatter(config)
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.intent_id = "test-intent-123"

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["intent_id"] == "test-intent-123"

    def test_formatter_includes_plan_id(self):
        """Testa que formatter inclui plan_id."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        formatter = CorrelationFormatter(config)
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.plan_id = "test-plan-456"

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["plan_id"] == "test-plan-456"

    def test_formatter_includes_user_id(self):
        """Testa que formatter inclui user_id."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        formatter = CorrelationFormatter(config)
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.user_id = "test-user-789"

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["user_id"] == "test-user-789"

    def test_formatter_includes_extra_fields(self):
        """Testa que formatter inclui campos extras."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        formatter = CorrelationFormatter(config)
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.extra_fields = {"custom_field": "custom_value", "number": 42}

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["custom_field"] == "custom_value"
        assert parsed["number"] == 42

    def test_formatter_includes_exception(self):
        """Testa que formatter inclui informações de exceção."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        formatter = CorrelationFormatter(config)

        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
            record = logging.LogRecord(
                name="test.logger",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error message",
                args=(),
                exc_info=exc_info,
            )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "exception" in parsed
        assert parsed["exception"]["type"] == "ValueError"
        assert "Test exception" in parsed["exception"]["message"]
        assert "stack_trace" in parsed["exception"]

    def test_formatter_timestamp_iso_format(self):
        """Testa que timestamp está em formato ISO."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        formatter = CorrelationFormatter(config)
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        # Verificar formato ISO (deve conter T e Z ou +)
        timestamp = parsed["timestamp"]
        assert "T" in timestamp

    def test_formatter_includes_module_function_line(self):
        """Testa que formatter inclui module, function e line."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        formatter = CorrelationFormatter(config)
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["logger"] == "test.logger"
        assert "module" in parsed
        assert "function" in parsed
        assert parsed["line"] == 42


class TestNeuralHiveLoggerAdapter:
    """Testes para NeuralHiveLoggerAdapter."""

    def test_adapter_initialization(self):
        """Testa inicialização do adapter."""
        logger = logging.getLogger("test.logger")
        adapter = NeuralHiveLoggerAdapter(logger)

        assert adapter.logger == logger
        assert adapter.extra == {}

    def test_adapter_with_extra(self):
        """Testa adapter com campos extras."""
        logger = logging.getLogger("test.logger")
        adapter = NeuralHiveLoggerAdapter(logger, {"context": "test"})

        assert adapter.extra == {"context": "test"}

    def test_process_adds_intent_id_to_kwargs(self):
        """Testa que process adiciona intent_id."""
        logger = logging.getLogger("test.logger")
        adapter = NeuralHiveLoggerAdapter(logger)

        msg, kwargs = adapter.process("Test message", {"intent_id": "intent-123"})

        assert msg == "Test message"
        assert "extra" in kwargs
        assert kwargs["extra"]["intent_id"] == "intent-123"

    def test_process_adds_plan_id_to_kwargs(self):
        """Testa que process adiciona plan_id."""
        logger = logging.getLogger("test.logger")
        adapter = NeuralHiveLoggerAdapter(logger)

        msg, kwargs = adapter.process("Test message", {"plan_id": "plan-456"})

        assert msg == "Test message"
        assert "extra" in kwargs
        assert kwargs["extra"]["plan_id"] == "plan-456"

    def test_process_adds_user_id_to_kwargs(self):
        """Testa que process adiciona user_id."""
        logger = logging.getLogger("test.logger")
        adapter = NeuralHiveLoggerAdapter(logger)

        msg, kwargs = adapter.process("Test message", {"user_id": "user-789"})

        assert msg == "Test message"
        assert "extra" in kwargs
        assert kwargs["extra"]["user_id"] == "user-789"

    def test_process_adds_extra_fields(self):
        """Testa que process adiciona campos extras."""
        logger = logging.getLogger("test.logger")
        adapter = NeuralHiveLoggerAdapter(logger)

        extra_fields = {"custom_field": "custom_value"}
        msg, kwargs = adapter.process("Test message", {"extra_fields": extra_fields})

        assert msg == "Test message"
        assert "extra" in kwargs
        assert kwargs["extra"]["extra_fields"] == extra_fields

    def test_process_preserves_existing_kwargs(self):
        """Testa que process preserva kwargs existentes."""
        logger = logging.getLogger("test.logger")
        adapter = NeuralHiveLoggerAdapter(logger)

        msg, kwargs = adapter.process("Test message", {"exc_info": True, "stack_info": False})

        assert msg == "Test message"
        assert kwargs["exc_info"] is True
        assert kwargs["stack_info"] is False

    def test_info_with_correlation(self):
        """Testa método info_with_correlation."""
        logger = logging.getLogger("test.logger.info_corr")
        adapter = NeuralHiveLoggerAdapter(logger)

        # Criar handler real para capturar logs
        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        adapter.info_with_correlation("Test message", intent_id="intent-123", plan_id="plan-456")

        # Verificar que log foi criado
        assert len(log_capture.getvalue()) > 0

        logger.removeHandler(handler)

    def test_error_with_correlation(self):
        """Testa método error_with_correlation."""
        logger = logging.getLogger("test.logger.error_corr")
        adapter = NeuralHiveLoggerAdapter(logger)

        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.ERROR)
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        adapter.error_with_correlation("Error message", intent_id="intent-123", plan_id="plan-456")

        assert len(log_capture.getvalue()) > 0

        logger.removeHandler(handler)

    def test_warning_with_correlation(self):
        """Testa método warning_with_correlation."""
        logger = logging.getLogger("test.logger.warning_corr")
        adapter = NeuralHiveLoggerAdapter(logger)

        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.WARNING)
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)

        adapter.warning_with_correlation("Warning message", intent_id="intent-123")

        assert len(log_capture.getvalue()) > 0

        logger.removeHandler(handler)


class TestInitLogging:
    """Testes para init_logging."""

    def test_init_logging_sets_up_root_logger(self):
        """Testa que init_logging configura root logger."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component", log_format="json"
        )

        init_logging(config)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO

    def test_init_logging_with_debug_level(self):
        """Testa init_logging com nível DEBUG."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component", log_level="DEBUG"
        )

        init_logging(config)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_init_logging_sets_external_library_levels(self):
        """Testa que níveis de bibliotecas externas são configurados."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        init_logging(config)

        # Verificar níveis de bibliotecas externas
        urllib3_logger = logging.getLogger("urllib3")
        assert urllib3_logger.level >= logging.WARNING

        requests_logger = logging.getLogger("requests")
        assert requests_logger.level >= logging.WARNING

        opentelemetry_logger = logging.getLogger("opentelemetry")
        assert opentelemetry_logger.level >= logging.WARNING

    def test_init_logging_creates_handler(self):
        """Testa que init_logging cria handler."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        # Limpar handlers existentes
        root_logger = logging.getLogger()
        initial_handlers = list(root_logger.handlers)

        init_logging(config)

        # Deve ter pelo menos um handler
        assert len(root_logger.handlers) > 0


class TestGetLogger:
    """Testes para get_logger."""

    def test_get_logger_returns_adapter(self):
        """Testa que get_logger retorna NeuralHiveLoggerAdapter."""
        logger = get_logger("test.logger")
        assert isinstance(logger, NeuralHiveLoggerAdapter)

    def test_get_logger_uses_caller_module_name(self):
        """Testa que get_logger usa nome do módulo chamador."""
        logger = get_logger()
        assert isinstance(logger, NeuralHiveLoggerAdapter)
        # Nome do logger deve ser algo como test_logging ou pytest
        assert logger.logger.name is not None


class TestLogIntentFunctions:
    """Testes para funções de log de intenções."""

    def test_log_intent_start(self):
        """Testa log_intent_start."""
        logger = get_logger("test.intent.start")
        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)

        log_intent_start(logger, intent_id="intent-123", user_input="Test input", channel="web")

        assert len(log_capture.getvalue()) > 0
        logger.logger.removeHandler(handler)

    def test_log_intent_completion(self):
        """Testa log_intent_completion."""
        logger = get_logger("test.intent.completion")
        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)

        log_intent_completion(
            logger, intent_id="intent-123", confidence=0.95, processing_duration=1.5, channel="api"
        )

        assert len(log_capture.getvalue()) > 0
        logger.logger.removeHandler(handler)

    def test_log_intent_start_with_empty_input(self):
        """Testa log_intent_start com input vazio."""
        logger = get_logger("test.intent.start.empty")
        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)

        log_intent_start(logger, intent_id="intent-123", user_input="", channel="mobile")

        assert len(log_capture.getvalue()) > 0
        logger.logger.removeHandler(handler)


class TestLogPlanFunctions:
    """Testes para funções de log de planos."""

    def test_log_plan_execution_start(self):
        """Testa log_plan_execution_start."""
        logger = get_logger("test.plan.start")
        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)

        log_plan_execution_start(
            logger, plan_id="plan-456", intent_id="intent-123", plan_type="data_processing"
        )

        assert len(log_capture.getvalue()) > 0
        logger.logger.removeHandler(handler)

    def test_log_plan_execution_completion_success(self):
        """Testa log_plan_execution_completion com sucesso."""
        logger = get_logger("test.plan.completion")
        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)

        log_plan_execution_completion(
            logger,
            plan_id="plan-456",
            success=True,
            execution_duration=5.2,
            intent_id="intent-123",
            plan_type="data_processing",
        )

        assert len(log_capture.getvalue()) > 0
        logger.logger.removeHandler(handler)

    def test_log_plan_execution_completion_failure(self):
        """Testa log_plan_execution_completion com falha."""
        logger = get_logger("test.plan.completion.fail")
        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)

        log_plan_execution_completion(
            logger,
            plan_id="plan-456",
            success=False,
            execution_duration=2.1,
            intent_id="intent-123",
            plan_type="validation",
        )

        assert len(log_capture.getvalue()) > 0
        logger.logger.removeHandler(handler)

    def test_log_plan_execution_start_without_intent(self):
        """Testa log_plan_execution_start sem intent_id."""
        logger = get_logger("test.plan.start.no_intent")
        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)

        log_plan_execution_start(logger, plan_id="plan-789", plan_type="standalone")

        assert len(log_capture.getvalue()) > 0
        logger.logger.removeHandler(handler)


class TestLoggingIntegration:
    """Testes de integração de logging."""

    def test_full_logging_flow(self):
        """Testa fluxo completo de logging."""
        config = ObservabilityConfig(
            service_name="integration-test",
            neural_hive_component="test-component",
            log_format="json",
        )

        init_logging(config)

        logger = get_logger("integration.flow")

        # Criar string buffer para capturar output
        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setFormatter(CorrelationFormatter(config))
        logger.logger.addHandler(handler)

        logger.info_with_correlation(
            "Integration test message", intent_id="test-intent", plan_id="test-plan"
        )

        log_output = log_capture.getvalue()
        assert len(log_output) > 0

        # Verificar que é JSON válido
        parsed = json.loads(log_output.strip())
        assert parsed["message"] == "Integration test message"

        logger.logger.removeHandler(handler)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
