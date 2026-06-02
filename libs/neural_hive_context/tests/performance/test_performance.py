"""
Performance Tests for Context Layer.

Valida que componentes atendem targets de performance.
"""

import pytest
import time
import statistics
from datetime import datetime, timezone

from neural_hive_context.services import (
    MultiSignalWorkflowClassifier,
    RegexPIIDetector,
    ContextManagerService,
    StubActiveLearningService,
)
from neural_hive_context.models import (
    RichContext,
    IntentContext,
    SystemContext,
    TemporalContext,
    SecurityContext,
    ConversationContext,
)


@pytest.fixture
def performance_targets():
    """Targets de performance do Context Layer."""
    return {
        "workflow_classifier_p95": 0.020,  # 20ms
        "workflow_classifier_p99": 0.040,  # 40ms
        "pii_detector_p95": 0.015,  # 15ms
        "pii_detector_p99": 0.030,  # 30ms
        "context_builder_p95": 0.050,  # 50ms
        "context_builder_p99": 0.100,  # 100ms
    }


class TestWorkflowClassifierPerformance:
    """Performance tests para WorkflowClassifier."""

    @pytest.mark.asyncio
    async def test_classify_performance_p95(self, performance_targets):
        """Classificação deve ser <20ms p95."""
        classifier = MultiSignalWorkflowClassifier()
        context = self._create_test_context("gere um relatório de vendas")

        # Executar 100 vezes para medir p95
        times = []
        for _ in range(100):
            start = time.perf_counter()
            await classifier.classify(context)
            times.append(time.perf_counter() - start)

        p95 = statistics.quantiles(times, n=20)[18]  # 95th percentile
        p99 = statistics.quantiles(times, n=100)[98]  # 99th percentile

        print(f"WorkflowClassifier - p95: {p95*1000:.2f}ms, p99: {p99*1000:.2f}ms")

        assert (
            p95 < performance_targets["workflow_classifier_p95"]
        ), f"p95 {p95*1000:.2f}ms excede target {performance_targets['workflow_classifier_p95']*1000:.2f}ms"

    @pytest.mark.asyncio
    async def test_classify_performance_p99(self, performance_targets):
        """Classificação deve ser <40ms p99."""
        classifier = MultiSignalWorkflowClassifier()
        context = self._create_test_context("analise os dados")

        times = []
        for _ in range(100):
            start = time.perf_counter()
            await classifier.classify(context)
            times.append(time.perf_counter() - start)

        p99 = statistics.quantiles(times, n=100)[98]
        assert p99 < performance_targets["workflow_classifier_p99"]

    def _create_test_context(self, intent_text: str) -> RichContext:
        """Helper para criar contexto de teste."""
        return RichContext(
            intent=IntentContext(raw_text=intent_text, intent_id="test"),
            system=SystemContext(affected_services=[], active_workflows=0),
            temporal=TemporalContext(
                current_time=datetime.now(timezone.utc).isoformat(),
                time_of_day="morning",
                day_of_week="Monday",
                is_business_hours=True,
            ),
            security=SecurityContext(),
            conversation=ConversationContext(),
            context_id="test-ctx",
            created_at=datetime.now(timezone.utc).isoformat(),
        )


class TestPIIDetectorPerformance:
    """Performance tests para PII Detector."""

    def test_detect_performance_p95(self, performance_targets):
        """Detecção PII deve ser <15ms p95."""
        pii_detector = RegexPIIDetector()
        text = "Meu email é joao.silva@exemplo.com e telefone é (11) 98765-4321"

        times = []
        for _ in range(100):
            start = time.perf_counter()
            pii_detector.detect(text)
            times.append(time.perf_counter() - start)

        p95 = statistics.quantiles(times, n=20)[18]
        print(f"PIIDetector - p95: {p95*1000:.2f}ms")

        assert (
            p95 < performance_targets["pii_detector_p95"]
        ), f"p95 {p95*1000:.2f}ms excede target {performance_targets['pii_detector_p95']*1000:.2f}ms"

    def test_detect_performance_p99(self, performance_targets):
        """Detecção PII deve ser <30ms p99."""
        pii_detector = RegexPIIDetector()
        text = "CPF: 123.456.789-09, Cartão: 4539 1488 0343 6467"

        times = []
        for _ in range(100):
            start = time.perf_counter()
            pii_detector.detect(text)
            times.append(time.perf_counter() - start)

        p99 = statistics.quantiles(times, n=100)[98]
        assert p99 < performance_targets["pii_detector_p99"]

    def test_detect_performance_long_text(self, performance_targets):
        """Detecção em texto longo deve manter performance."""
        pii_detector = RegexPIIDetector()
        # Texto longo com múltiplas entidades
        text = (
            " ".join(
                [
                    "Contato: joao@exemplo.com, maria@teste.com",
                    "Telefones: (11) 98765-4321, (21) 99876-5432",
                    "CPF: 123.456.789-09, 987.654.321-00",
                    "Cartões: 4539 1488 0343 6467, 5421 1234 5678 9010",
                    "IPs: 192.168.1.1, 10.0.0.1, 172.16.0.1",
                    "URLs: https://exemplo.com, http://teste.com.br",
                ]
            )
            * 5
        )  # 5x repetição = ~1500 caracteres

        times = []
        for _ in range(50):
            start = time.perf_counter()
            pii_detector.detect(text)
            times.append(time.perf_counter() - start)

        p95 = statistics.quantiles(times, n=20)[18]
        assert (
            p95 < performance_targets["pii_detector_p99"]
        ), f"Texto longo p95 {p95*1000:.2f}ms excede target"


class TestContextManagerPerformance:
    """Performance tests para Context Manager."""

    @pytest.mark.asyncio
    async def test_create_context_performance_p95(self, performance_targets):
        """Criação de contexto deve ser <50ms p95."""
        classifier = MultiSignalWorkflowClassifier()
        context_manager = ContextManagerService(
            workflow_classifier=classifier,
        )

        times = []
        for _ in range(100):
            start = time.perf_counter()
            await context_manager.create_context(
                intent_text="gere um relatório",
                intent_id="test-intent",
            )
            times.append(time.perf_counter() - start)

        p95 = statistics.quantiles(times, n=20)[18]
        print(f"ContextManager.create_context - p95: {p95*1000:.2f}ms")

        assert (
            p95 < performance_targets["context_builder_p95"]
        ), f"p95 {p95*1000:.2f}ms excede target {performance_targets['context_builder_p95']*1000:.2f}ms"

    @pytest.mark.asyncio
    async def test_classify_workflow_performance(self, performance_targets):
        """Classificação completa deve ser rápida."""
        classifier = MultiSignalWorkflowClassifier()
        context_manager = ContextManagerService(
            workflow_classifier=classifier,
        )

        times = []
        for _ in range(100):
            start = time.perf_counter()
            await context_manager.create_and_classify(
                intent_text="gere um dashboard",
                intent_id="test-intent",
            )
            times.append(time.perf_counter() - start)

        p95 = statistics.quantiles(times, n=20)[18]
        print(f"ContextManager.create_and_classify - p95: {p95*1000:.2f}ms")

        # Deve ser rápido, mas pode ser maior que classify sozinho
        assert p95 < 0.100  # 100ms máximo


class TestActiveLearningPerformance:
    """Performance tests para Active Learning."""

    @pytest.mark.asyncio
    async def test_extract_signal_performance(self):
        """Extração de sinal deve ser rápida."""
        al_service = StubActiveLearningService()

        times = []
        for _ in range(100):
            start = time.perf_counter()
            await al_service.extract_signal(
                intent_text="gere um relatório complexo",
                confidence=0.5,
                workflow_type="generation",
            )
            times.append(time.perf_counter() - start)

        p95 = statistics.quantiles(times, n=20)[18]
        print(f"ActiveLearning.extract_signal - p95: {p95*1000:.2f}ms")

        # Deve ser muito rápido (<5ms)
        assert p95 < 0.005, f"p95 {p95*1000:.2f}ms excede target 5ms"


@pytest.mark.performance
class TestPerformanceSummary:
    """Testes consolidados de performance."""

    @pytest.mark.asyncio
    async def test_all_components_performance(self, performance_targets):
        """Testa performance de todos os componentes."""
        classifier = MultiSignalWorkflowClassifier()
        pii_detector = RegexPIIDetector()
        al_service = StubActiveLearningService()

        results = {}

        # WorkflowClassifier
        context = RichContext(
            intent=IntentContext(raw_text="teste", intent_id="test"),
            system=SystemContext(affected_services=[], active_workflows=0),
            temporal=TemporalContext(
                current_time="2024-01-01T00:00:00Z",
                time_of_day="morning",
                day_of_week="Monday",
                is_business_hours=True,
            ),
            security=SecurityContext(),
            conversation=ConversationContext(),
            context_id="test",
            created_at="2024-01-01T00:00:00Z",
        )

        times = []
        for _ in range(100):
            start = time.perf_counter()
            await classifier.classify(context)
            times.append(time.perf_counter() - start)
        results["workflow_classifier"] = statistics.quantiles(times, n=20)[18]

        # PII Detector
        times = []
        for _ in range(100):
            start = time.perf_counter()
            pii_detector.detect("email: teste@exemplo.com")
            times.append(time.perf_counter() - start)
        results["pii_detector"] = statistics.quantiles(times, n=20)[18]

        # Active Learning
        times = []
        for _ in range(100):
            start = time.perf_counter()
            await al_service.extract_signal("teste", 0.5, "generation")
            times.append(time.perf_counter() - start)
        results["active_learning"] = statistics.quantiles(times, n=20)[18]

        # Print summary
        print("\n=== Performance Summary ===")
        for name, p95 in results.items():
            print(f"{name}: {p95*1000:.2f}ms")

        # Asserts
        assert results["workflow_classifier"] < performance_targets["workflow_classifier_p95"]
        assert results["pii_detector"] < performance_targets["pii_detector_p95"]
        assert results["active_learning"] < 0.005  # 5ms
