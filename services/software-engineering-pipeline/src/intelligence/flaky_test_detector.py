from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from structlog import get_logger

from src.models.pipeline import Anomaly
from src.models.schemas import Severity


class TestHistory(BaseModel):
    """Rastreia histórico de um teste específico."""

    model_config = ConfigDict(extra="forbid")

    test_name: str
    total_runs: int = Field(default=0, ge=0)
    passed_runs: int = Field(default=0, ge=0)
    failed_runs: int = Field(default=0, ge=0)
    flaky_score: float = Field(default=0.0, ge=0.0, le=1.0)
    last_failure: datetime | None = None
    last_pass: datetime | None = None


class FlakyTestDetector:
    """Detecta e rastreia testes flaky."""

    def __init__(self, flaky_threshold: float = 0.3):
        self.flaky_threshold = flaky_threshold
        self.logger = get_logger()
        self.test_histories: dict[str, TestHistory] = {}

    async def analyze_test_results(
        self,
        test_results: dict,
        repo_url: str,
        run_id: str,
    ) -> list[Anomaly]:
        """Analisa resultados de testes para flakiness."""
        self.logger.info("analyzing_test_results", run_id=run_id)

        anomalies: list[Anomaly] = []

        # Update test histories
        self._update_histories(test_results, run_id)

        # Check for flaky tests
        for test_name, history in self.test_histories.items():
            if history.flaky_score >= self.flaky_threshold:
                anomalies.append(
                    Anomaly(
                        anomaly_id=f"flaky-{run_id}-{test_name}",
                        repo_url=repo_url,
                        run_id=run_id,
                        type="flaky_test",
                        severity=Severity.MEDIUM,
                        description=f'Test "{test_name}" has flaky score of {history.flaky_score:.2f}',
                        affected_component=test_name,
                        suggested_action="Add retry logic or fix race condition",
                    )
                )

        return anomalies

    def _update_histories(self, test_results: dict, run_id: str) -> None:
        """Atualiza históricos de testes com novos resultados."""
        now = datetime.now(timezone.utc)

        passed_tests = test_results.get("passed_tests", [])
        failed_tests = test_results.get("failed_tests", [])

        # Update passed tests
        for test_name in passed_tests:
            if test_name not in self.test_histories:
                self.test_histories[test_name] = TestHistory(test_name=test_name)

            history = self.test_histories[test_name]
            history.total_runs += 1
            history.passed_runs += 1
            history.last_pass = now
            history.flaky_score = self._calculate_flaky_score(history)

        # Update failed tests
        for test_name in failed_tests:
            if test_name not in self.test_histories:
                self.test_histories[test_name] = TestHistory(test_name=test_name)

            history = self.test_histories[test_name]
            history.total_runs += 1
            history.failed_runs += 1
            history.last_failure = now
            history.flaky_score = self._calculate_flaky_score(history)

    def _calculate_flaky_score(self, history: TestHistory) -> float:
        """Calcula score de flakiness baseado no padrão pass/fail."""
        if history.total_runs < 2:
            return 0.0

        # For flaky tests, we want high score when test has both passes AND failures
        # Simple metric: failure rate weighted by recency
        base_score = history.failed_runs / history.total_runs

        # Boost score if test has both recent passes and failures (true flakiness)
        if history.last_pass and history.last_failure:
            time_diff = abs((history.last_pass - history.last_failure).total_seconds())
            if time_diff < 3600:  # Within an hour
                base_score *= 1.5

            # If has both pass and fail, boost score significantly
            if history.passed_runs > 0 and history.failed_runs > 0:
                base_score = max(base_score, 0.4)

        return min(base_score, 1.0)

    def get_flaky_tests(self) -> list[TestHistory]:
        """Retorna todos os testes considerados flaky."""
        return [
            h
            for h in self.test_histories.values()
            if h.flaky_score >= self.flaky_threshold
        ]

    def get_test_history(self, test_name: str) -> TestHistory | None:
        """Retorna histórico de um teste específico."""
        return self.test_histories.get(test_name)
