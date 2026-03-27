from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from structlog import get_logger

from src.models.pipeline import Insight, InsightsReport
from src.models.schemas import Severity, InsightType


class InsightConfig(BaseModel):
    """Configuração para geração de insights."""

    model_config = ConfigDict(extra="forbid")

    slow_test_threshold_seconds: int = Field(default=10, ge=1)
    cache_miss_threshold: int = Field(default=5, ge=1)
    parallelization_candidate_time: int = Field(default=30, ge=1)


class InsightsGenerator:
    """Gera insights a partir de dados de execução de pipeline."""

    def __init__(self, config: InsightConfig | None = None):
        self.config = config or InsightConfig()
        self.logger = get_logger()

    async def generate_insights(
        self,
        repo_url: str,
        runs: list[dict],
        timeframe_start: datetime,
        timeframe_end: datetime,
    ) -> InsightsReport:
        """Gera relatório de insights abrangente."""
        self.logger.info("generating_insights", repo_url=repo_url, runs_count=len(runs))

        if not runs:
            return InsightsReport(
                repo_url=repo_url,
                timeframe_start=timeframe_start,
                timeframe_end=timeframe_end,
                total_runs=0,
                success_rate=0.0,
                average_duration_seconds=0.0,
                flaky_tests=[],
                slow_tests=[],
                optimization_opportunities=[],
                security_issues=[],
            )

        # Calculate basic metrics
        successful_runs = [r for r in runs if r.get("status") == "success"]
        success_rate = len(successful_runs) / len(runs) if runs else 0.0

        durations = [
            r.get("duration_seconds", 0) for r in runs if r.get("duration_seconds")
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        # Generate insights
        flaky_tests = await self._find_flaky_tests(runs, repo_url)
        slow_tests = await self._find_slow_tests(runs, repo_url)
        optimization_opportunities = await self._find_optimization_opportunities(
            runs, repo_url
        )
        security_issues = await self._find_security_issues(runs, repo_url)

        return InsightsReport(
            repo_url=repo_url,
            timeframe_start=timeframe_start,
            timeframe_end=timeframe_end,
            total_runs=len(runs),
            success_rate=success_rate,
            average_duration_seconds=avg_duration,
            flaky_tests=flaky_tests,
            slow_tests=slow_tests,
            optimization_opportunities=optimization_opportunities,
            security_issues=security_issues,
        )

    async def _find_flaky_tests(self, runs: list[dict], repo_url: str) -> list[Insight]:
        """Encontra testes que falham intermitentemente."""
        test_results: dict[str, dict] = {}

        for run in runs:
            run_test_results = run.get("test_results", {})
            failed = run_test_results.get("failed_tests", [])
            passed = run_test_results.get("passed_tests", [])

            for test in failed:
                if test not in test_results:
                    test_results[test] = {"failures": 0, "passes": 0}
                test_results[test]["failures"] += 1

            for test in passed:
                if test not in test_results:
                    test_results[test] = {"failures": 0, "passes": 0}
                test_results[test]["passes"] += 1

        # Find tests with both failures and passes
        flaky = []
        for test_name, counts in test_results.items():
            if counts["failures"] > 0 and counts["passes"] > 0:
                flaky_score = counts["failures"] / (
                    counts["failures"] + counts["passes"]
                )
                if flaky_score > 0.1:  # At least 10% failure rate
                    flaky.append(
                        Insight(
                            insight_id=f"flaky-{test_name}",
                            repo_url=repo_url,
                            insight_type=InsightType.FLAKY_TEST,
                            title=f"Flaky test: {test_name}",
                            description=f'Test fails {counts["failures"]} times but passes {counts["passes"]} times',
                            impact=Severity.MEDIUM
                            if flaky_score < 0.3
                            else Severity.HIGH,
                            effort="M",
                        )
                    )

        return flaky

    async def _find_slow_tests(self, runs: list[dict], repo_url: str) -> list[Insight]:
        """Encontra testes que demoram muito para rodar."""
        test_times: dict[str, list[int]] = {}

        for run in runs:
            run_test_results = run.get("test_results", {})
            test_durations = run_test_results.get("test_durations", {})

            for test_name, duration in test_durations.items():
                if test_name not in test_times:
                    test_times[test_name] = []
                test_times[test_name].append(duration)

        slow_tests = []
        for test_name, durations in test_times.items():
            avg_duration = sum(durations) / len(durations)
            if avg_duration > self.config.slow_test_threshold_seconds:
                slow_tests.append(
                    Insight(
                        insight_id=f"slow-{test_name}",
                        repo_url=repo_url,
                        insight_type=InsightType.SLOW_TEST,
                        title=f"Slow test: {test_name}",
                        description=f"Test takes {avg_duration:.1f}s on average",
                        impact=Severity.MEDIUM,
                        effort="M",
                    )
                )

        return slow_tests

    async def _find_optimization_opportunities(
        self, runs: list[dict], repo_url: str
    ) -> list[Insight]:
        """Encontra oportunidades para otimizar performance do pipeline."""
        opportunities = []

        # Check for cache opportunities
        cache_misses = 0
        for run in runs:
            if run.get("cache_hit") is False:
                cache_misses += 1

        if cache_misses > self.config.cache_miss_threshold:
            opportunities.append(
                Insight(
                    insight_id="cache-miss",
                    repo_url=repo_url,
                    insight_type=InsightType.CACHE_OPPORTUNITY,
                    title="High cache miss rate",
                    description=f"{cache_misses} runs had cache misses",
                    impact=Severity.MEDIUM,
                    effort="S",
                )
            )

        # Check for parallelization opportunities
        avg_duration = (
            sum(r.get("duration_seconds", 0) for r in runs if r.get("duration_seconds"))
            / len(runs)
            if runs
            else 0
        )

        if avg_duration > self.config.parallelization_candidate_time:
            opportunities.append(
                Insight(
                    insight_id="parallelize",
                    repo_url=repo_url,
                    insight_type=InsightType.PARALLELIZATION_OPPORTUNITY,
                    title="Long pipeline duration",
                    description=f"Average pipeline takes {avg_duration:.0f}s - consider parallelizing stages",
                    impact=Severity.HIGH,
                    effort="M",
                )
            )

        return opportunities

    async def _find_security_issues(
        self, runs: list[dict], repo_url: str
    ) -> list[Insight]:
        """Encontra issues de segurança recorrentes."""
        security_issues = []

        vuln_count = 0
        critical_count = 0

        for run in runs:
            security_scan = run.get("security_scan", {})
            vuln_count += security_scan.get("total", 0)
            critical_count += security_scan.get("critical", 0)

        if critical_count > 0:
            security_issues.append(
                Insight(
                    insight_id="sec-critical",
                    repo_url=repo_url,
                    insight_type=InsightType.SECURITY_ISSUE,
                    title="Critical vulnerabilities recurring",
                    description=f"{critical_count} critical vulnerabilities found across {len(runs)} runs",
                    impact=Severity.CRITICAL,
                    effort="L",
                )
            )

        return security_issues
