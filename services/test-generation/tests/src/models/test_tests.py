"""Tests para modelos de testes."""

from models.tests import (
    TestCase,
    TestCoverage,
    TestFramework,
    TestSuite,
    TestType,
)


class TestTestTypeEnum:
    """Testes para enum TestType."""

    def test_values(self):
        """Verifica valores do enum."""
        assert TestType.UNIT == "unit"
        assert TestType.INTEGRATION == "integration"
        assert TestType.E2E == "e2e"


class TestTestFrameworkEnum:
    """Testes para enum TestFramework."""

    def test_values(self):
        """Verifica valores do enum."""
        assert TestFramework.PYTEST == "pytest"
        assert TestFramework.JEST == "jest"


class TestTestCaseModel:
    """Testes para TestCase."""

    def test_create_minimal(self):
        """Cria caso de teste mínimo."""
        tc = TestCase(
            id="TC-001",
            name="Test Example",
            description="Example test",
            test_type=TestType.UNIT,
            framework=TestFramework.PYTEST,
            test_code="def test(): pass",
            file_path="tests/test_example.py",
            language="python",
        )

        assert tc.id == "TC-001"
        assert tc.test_type == TestType.UNIT
        assert tc.framework == TestFramework.PYTEST
        assert tc.language == "python"

    def test_create_with_tracking(self):
        """Cria caso com rastreabilidade."""
        tc = TestCase(
            id="TC-002",
            name="Test with Tracking",
            description="Test",
            test_type=TestType.INTEGRATION,
            framework=TestFramework.PYTEST,
            test_code="def test(): pass",
            file_path="tests/test_int.py",
            language="python",
            requirement_id="REQ-001",
            user_story_id="US-001",
        )

        assert tc.requirement_id == "REQ-001"
        assert tc.user_story_id == "US-001"


class TestTestSuiteModel:
    """Testes para TestSuite."""

    def test_create_suite(self):
        """Cria suíte de testes."""
        suite = TestSuite(
            id="TS-001",
            name="Example Suite",
            description="Example test suite",
            test_cases=[],
            framework=TestFramework.PYTEST,
            language="python",
        )

        assert suite.id == "TS-001"
        assert suite.total_tests == 0


class TestTestCoverageModel:
    """Testes para TestCoverage."""

    def test_coverage_calculation(self):
        """Testa cálculo de cobertura."""
        coverage = TestCoverage(
            total_requirements=10,
            requirements_with_tests=8,
            total_user_stories=5,
            user_stories_with_tests=4,
        )

        assert coverage.coverage_percentage() == 80.0

    def test_zero_coverage(self):
        """Testa cobertura zero."""
        coverage = TestCoverage()

        assert coverage.coverage_percentage() == 0.0
