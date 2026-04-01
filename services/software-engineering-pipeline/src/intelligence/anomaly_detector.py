from pydantic import BaseModel, ConfigDict, Field
from structlog import get_logger

from src.models.pipeline import Anomaly
from src.models.schemas import AnomalyType, Severity


class AnomalyDetectionConfig(BaseModel):
    """Configuração para detecção de anomalias."""

    model_config = ConfigDict(extra="forbid")

    flaky_test_threshold: int = Field(default=3, ge=1, description="Número de falhas consecutivas")
    failure_rate_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Taxa de falha (50%)"
    )
    duration_increase_threshold: float = Field(
        default=2.0, ge=1.0, description="Aumento de duração (2x mais lento)"
    )
    enable_performance_detection: bool = True
    enable_security_detection: bool = True


class AnomalyPattern(BaseModel):
    """Representa um padrão de anomalia detectado."""

    model_config = ConfigDict(extra="forbid")

    pattern_type: AnomalyType
    severity: Severity
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    affected_components: list[str]


class AnomalyDetector:
    """Detecta anomalias na execução de pipelines."""

    def __init__(self, config: AnomalyDetectionConfig | None = None):
        self.config = config or AnomalyDetectionConfig()
        self.logger = get_logger()

    async def analyze_run(
        self,
        run: dict,
        historical_runs: list[dict],
    ) -> list[Anomaly]:
        """Analisa uma execução de pipeline para anomalias."""
        self.logger.info("analyzing_run", run_id=run.get("run_id"))

        anomalies: list[Anomaly] = []

        # Check for flaky tests
        flaky_anomalies = await self._detect_flaky_tests(run, historical_runs)
        anomalies.extend(flaky_anomalies)

        # Check for performance degradation
        if self.config.enable_performance_detection:
            perf_anomalies = await self._detect_performance_degradation(run, historical_runs)
            anomalies.extend(perf_anomalies)

        # Check for security issues
        if self.config.enable_security_detection:
            security_anomalies = await self._detect_security_anomalies(run)
            anomalies.extend(security_anomalies)

        self.logger.info("anomaly_analysis_complete", count=len(anomalies))
        return anomalies

    async def _detect_flaky_tests(self, run: dict, historical_runs: list[dict]) -> list[Anomaly]:
        """Detecta testes flaky (que falham intermitentemente)."""
        anomalies: list[Anomaly] = []

        test_results = run.get("test_results", {})
        failed_tests = test_results.get("failed_tests", [])
        passed_tests = test_results.get("passed_tests", [])

        for test_name in failed_tests:
            # Check if this test has both passed AND failed in history
            has_ever_passed = test_name in passed_tests
            has_ever_failed = True  # Currently failing

            # Check historical runs for both pass and fail
            recent_passes = 0
            recent_failures = 0

            for historical_run in reversed(historical_runs[:10]):
                hist_test_results = historical_run.get("test_results", {})
                if test_name in hist_test_results.get("passed_tests", []):
                    recent_passes += 1
                    has_ever_passed = True
                if test_name in hist_test_results.get("failed_tests", []):
                    recent_failures += 1
                    has_ever_failed = True

            # Only flag as flaky if test has shown inconsistency
            # (has both passed and failed at some point)
            if has_ever_passed and has_ever_failed:
                anomalies.append(
                    Anomaly(
                        anomaly_id=f'flaky-{run.get("run_id")}-{test_name}',
                        repo_url=run.get("repo_url", ""),
                        run_id=run.get("run_id"),
                        type=AnomalyType.FLAKY_TEST,
                        severity=Severity.MEDIUM,
                        description=f'Test "{test_name}" has intermittent failures',
                        affected_component=test_name,
                        suggested_action="Review test for race conditions or external dependencies",
                    )
                )

        return anomalies

    async def _detect_performance_degradation(
        self, run: dict, historical_runs: list[dict]
    ) -> list[Anomaly]:
        """Detecta degradação de performance significativa."""
        anomalies: list[Anomaly] = []

        current_duration = run.get("duration_seconds", 0)
        if current_duration == 0:
            return anomalies

        # Calculate average duration from historical runs
        if not historical_runs:
            return anomalies

        durations = [
            r.get("duration_seconds", 0) for r in historical_runs if r.get("duration_seconds")
        ]
        if not durations:
            return anomalies

        avg_duration = sum(durations) / len(durations)

        if current_duration > avg_duration * self.config.duration_increase_threshold:
            anomalies.append(
                Anomaly(
                    anomaly_id=f'perf-{run.get("run_id")}',
                    repo_url=run.get("repo_url", ""),
                    run_id=run.get("run_id"),
                    type=AnomalyType.PERFORMANCE_DEGRADATION,
                    severity=Severity.HIGH
                    if current_duration > avg_duration * 3
                    else Severity.MEDIUM,
                    description=f"Pipeline duration increased from {avg_duration:.0f}s to {current_duration}s",
                    suggested_action="Review recent changes for performance issues",
                )
            )

        return anomalies

    async def _detect_security_anomalies(self, run: dict) -> list[Anomaly]:
        """Detecta anomalias relacionadas à segurança."""
        anomalies: list[Anomaly] = []

        security_results = run.get("security_scan", {})
        critical_vulns = security_results.get("critical", 0)
        high_vulns = security_results.get("high", 0)

        if critical_vulns > 0:
            anomalies.append(
                Anomaly(
                    anomaly_id=f'sec-critical-{run.get("run_id")}',
                    repo_url=run.get("repo_url", ""),
                    run_id=run.get("run_id"),
                    type=AnomalyType.SECURITY_VULNERABILITY,
                    severity=Severity.CRITICAL,
                    description=f"{critical_vulns} critical vulnerabilities detected",
                    suggested_action="Block deployment and address vulnerabilities immediately",
                )
            )

        if high_vulns > 5:
            anomalies.append(
                Anomaly(
                    anomaly_id=f'sec-high-{run.get("run_id")}',
                    repo_url=run.get("repo_url", ""),
                    run_id=run.get("run_id"),
                    type=AnomalyType.SECURITY_VULNERABILITY,
                    severity=Severity.HIGH,
                    description=f"{high_vulns} high-severity vulnerabilities detected",
                    suggested_action="Review and address high-severity vulnerabilities",
                )
            )

        return anomalies
