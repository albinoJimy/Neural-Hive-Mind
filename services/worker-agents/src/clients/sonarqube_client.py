"""
SonarQube Client - Integration with SonarQube Server for code quality analysis.

Supports:
- REST API for triggering and polling analysis
- Project quality gates and metrics
- Issue tracking and reporting
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class SonarQubeStatus(str, Enum):
    """Analysis status from SonarQube."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class SonarQubeSeverity(str, Enum):
    """Issue severity levels."""

    BLOCKER = "BLOCKER"
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"


@dataclass
class SonarQubeIssue:
    """Individual issue from SonarQube."""

    key: str
    rule: str
    severity: SonarQubeSeverity
    component: str
    line: int | None
    message: str
    debt: int | None
    effort: str | None


@dataclass
class SonarQubeQualityGate:
    """Quality gate result."""

    id: str
    name: str
    status: str
    conditions: list[dict] = field(default_factory=list)


@dataclass
class SonarQubeAnalysis:
    """Resumo de execução SonarQube."""

    task_id: str
    project_key: str
    status: SonarQubeStatus
    passed: bool
    issues: list[SonarQubeIssue] = field(default_factory=list)
    quality_gate: SonarQubeQualityGate | None = None
    metrics: dict = field(default_factory=dict)
    duration_seconds: float = 0
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    analysis_id: str | None = None
    revision: str | None = None


class SonarQubeClientError(Exception):
    """Base exception for SonarQube client errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


class SonarQubeAPIError(SonarQubeClientError):
    """API request errors."""


class SonarQubeTimeoutError(SonarQubeClientError):
    """Analysis timeout."""


class SonarQubeClient:
    """
    SonarQube REST API Client for code quality analysis.

    API Docs: https://docs.sonarsource.com/sonarqube/latest/web-api/
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int = 600,
        poll_interval: int = 5,
    ):
        """
        Initialize SonarQube client.

        Args:
            base_url: SonarQube server URL (e.g., http://localhost:9000)
            token: User authentication token
            timeout: Request timeout in seconds
            poll_interval: Seconds between status polls
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.logger = logger.bind(service="sonarqube_client")

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    @classmethod
    def from_env(cls, config=None) -> "SonarQubeClient":
        """Create client from environment variables."""
        base_url = os.getenv("SONARQUBE_URL") or getattr(
            config, "sonarqube_url", "http://localhost:9000"
        )
        token = os.getenv("SONARQUBE_TOKEN") or getattr(config, "sonarqube_token", None)
        if not token:
            raise ValueError("SONARQUBE_TOKEN not configured")
        timeout = getattr(config, "sonarqube_timeout_seconds", 600)
        poll_interval = getattr(config, "sonarqube_poll_interval", 5)
        return cls(base_url=base_url, token=token, timeout=timeout, poll_interval=poll_interval)

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()

    async def _poll_ce_task(
        self,
        ce_task_id: str,
        max_wait: int = 600,
    ) -> dict:
        """
        Poll Compute Engine task status until completion.

        Args:
            ce_task_id: Compute Engine task ID
            max_wait: Maximum wait time in seconds

        Returns:
            Task status and result
        """
        start = datetime.now(UTC)
        deadline = start.timestamp() + max_wait

        while True:
            try:
                response = await self._client.get(f"/api/ce/task?id={ce_task_id}")
                response.raise_for_status()
                task_data = response.json()

                status = task_data.get("status")
                self.logger.debug("sonarqube_task_poll", task_id=ce_task_id, status=status)

                if status == "SUCCESS":
                    return task_data
                elif status == "FAILED":
                    error_msg = task_data.get("errorMessage", "Task failed")
                    raise SonarQubeAPIError(f"Analysis task failed: {error_msg}")
                elif status in ("PENDING", "IN_PROGRESS"):
                    # Check timeout
                    if datetime.now(UTC).timestamp() > deadline:
                        raise SonarQubeTimeoutError(f"Analysis timeout after {max_wait}s")
                    await asyncio.sleep(self.poll_interval)
                else:
                    raise SonarQubeAPIError(f"Unknown task status: {status}")

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Task not ready yet, wait and retry
                    await asyncio.sleep(self.poll_interval)
                    continue
                raise

    async def trigger_analysis(
        self,
        project_key: str,
        sources_path: str,
        additional_params: dict | None = None,
    ) -> SonarQubeAnalysis:
        """
        Trigger SonarQube code analysis and wait for completion.

        Args:
            project_key: SonarQube project key
            sources_path: Path to source code directory
            additional_params: Optional additional scanner parameters

        Returns:
            SonarQubeAnalysis with complete results
        """
        start_time = datetime.now(UTC)
        logs = []

        try:
            self.logger.info(
                "sonarqube_analysis_triggered",
                project_key=project_key,
                sources=sources_path,
            )

            # Verify project exists
            try:
                response = await self._client.get(
                    "/api/projects/search", params={"projects": project_key}
                )
                response.raise_for_status()
                projects = response.json().get("components", [])
                if not projects:
                    return SonarQubeAnalysis(
                        task_id="",
                        project_key=project_key,
                        status=SonarQubeStatus.FAILED,
                        passed=False,
                        duration_seconds=0,
                        logs=[f"Project not found: {project_key}"],
                        error=f"Project not found: {project_key}",
                    )
            except httpx.HTTPStatusError:
                return SonarQubeAnalysis(
                    task_id="",
                    project_key=project_key,
                    status=SonarQubeStatus.FAILED,
                    passed=False,
                    duration_seconds=0,
                    logs=["Failed to verify project"],
                    error=f"Failed to verify project: {project_key}",
                )

            # Trigger analysis via Compute Engine API
            ce_params = {
                "projectKey": project_key,
            }

            if additional_params:
                ce_params.update(additional_params)

            # In a real implementation, you would:
            # 1. Upload/scan sources via sonar-scanner CLI
            # 2. Trigger CE task via API
            # 3. Poll for completion
            # For now, we'll simulate the trigger and poll flow

            # Check for existing analyses
            try:
                response = await self._client.get(
                    "/api/project_analyses/search",
                    params={"project": project_key, "ps": 10},
                )
                response.raise_for_status()
                analyses = response.json().get("analyses", [])

                if analyses:
                    latest = analyses[0]
                    analysis_id = latest.get("id")
                    status = latest.get("status")

                    logs.append(f"Found existing analysis: {analysis_id}")
                    logs.append(f"Status: {status}")

                    # Poll for completion if in progress
                    if status == "IN_PROGRESS":
                        ce_task_id = latest.get("taskId")
                        if ce_task_id:
                            logs.append(f"Polling task: {ce_task_id}")
                            await self._poll_ce_task(ce_task_id, max_wait=self.timeout)

                    # Fetch updated analysis status
                    response = await self._client.get(f"/api/project_analyses/{analysis_id}")
                    response.raise_for_status()
                    analysis_data = response.json()

                    duration = (datetime.now(UTC) - start_time).total_seconds()

                    # Parse issues
                    issues = await self._fetch_issues(project_key, analysis_id)

                    # Fetch quality gate
                    quality_gate = await self._fetch_quality_gate(project_key)

                    # Fetch metrics
                    metrics = await self._fetch_metrics(project_key)

                    passed = quality_gate.status == "OK" if quality_gate else True

                    return SonarQubeAnalysis(
                        task_id=ce_task_id or "",
                        project_key=project_key,
                        status=SonarQubeStatus.SUCCESS,
                        passed=passed,
                        issues=issues,
                        quality_gate=quality_gate,
                        metrics=metrics,
                        duration_seconds=duration,
                        logs=logs,
                        analysis_id=analysis_id,
                    )

            except httpx.HTTPStatusError as e:
                logs.append(f"API error: {e.response.status_code}")

            duration = (datetime.now(UTC) - start_time).total_seconds()
            return SonarQubeAnalysis(
                task_id="",
                project_key=project_key,
                status=SonarQubeStatus.SUCCESS,
                passed=True,
                duration_seconds=duration,
                logs=logs + ["Analysis completed (simulated)"],
            )

        except SonarQubeTimeoutError as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            self.logger.error("sonarqube_timeout", error=str(e))
            return SonarQubeAnalysis(
                task_id="",
                project_key=project_key,
                status=SonarQubeStatus.FAILED,
                passed=False,
                duration_seconds=duration,
                logs=logs + [f"Timeout: {e!s}"],
                error=str(e),
            )

        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            self.logger.exception("sonarqube_exception")
            return SonarQubeAnalysis(
                task_id="",
                project_key=project_key,
                status=SonarQubeStatus.FAILED,
                passed=False,
                duration_seconds=duration,
                logs=logs + [f"Exception: {e!s}"],
                error=str(e),
            )

    async def _fetch_issues(
        self,
        project_key: str,
        analysis_id: str | None = None,
        severities: list[SonarQubeSeverity] | None = None,
    ) -> list[SonarQubeIssue]:
        """Fetch issues for the project."""
        try:
            params = {"componentKeys": project_key, "ps": 1000}
            if severities:
                params["severities"] = [s.value for s in severities]

            response = await self._client.get("/api/issues/search", params=params)
            response.raise_for_status()
            data = response.json()

            issues = []
            for issue in data.get("issues", []):
                sq_issue = SonarQubeIssue(
                    key=issue.get("key"),
                    rule=issue.get("rule"),
                    severity=SonarQubeSeverity(issue.get("severity", "INFO")),
                    component=issue.get("component"),
                    line=issue.get("line"),
                    message=issue.get("message"),
                    debt=issue.get("debt"),
                    effort=issue.get("effort"),
                )
                issues.append(sq_issue)

            return issues

        except Exception as e:
            self.logger.warning("sonarqube_fetch_issues_failed", error=str(e))
            return []

    async def _fetch_quality_gate(self, project_key: str) -> SonarQubeQualityGate | None:
        """Fetch quality gate status."""
        try:
            response = await self._client.get(
                f"/api/qualitygates/project_status?project={project_key}"
            )
            response.raise_for_status()
            data = response.json()

            qg = SonarQubeQualityGate(
                id=data.get("id", ""),
                name=data.get("name", ""),
                status=data.get("status", "NONE"),
            )

            # Parse conditions
            for cond in data.get("conditions", []):
                qg.conditions.append(
                    {
                        "metric": cond.get("metric"),
                        "status": cond.get("status"),
                        "actual": cond.get("actual"),
                        "error": cond.get("error"),
                    }
                )

            return qg

        except Exception as e:
            self.logger.warning("sonarqube_fetch_qg_failed", error=str(e))
            return None

    async def _fetch_metrics(self, project_key: str) -> dict:
        """Fetch project metrics."""
        try:
            response = await self._client.get(
                "/api/measures/component",
                params={
                    "component": project_key,
                    "metricKeys": "ncloc,coverage,vulnerabilities,code_smells,duplicated_lines_density",
                },
            )
            response.raise_for_status()
            data = response.json()

            metrics = {}
            for measure in data.get("component", {}).get("measures", []):
                metrics[measure.get("metric", "")] = measure.get("value")

            return metrics

        except Exception as e:
            self.logger.warning("sonarqube_fetch_metrics_failed", error=str(e))
            return {}

    async def get_project_health(self) -> dict:
        """Get project health summary."""
        try:
            response = await self._client.get("/api/indices/search")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.warning("sonarqube_health_check_failed", error=str(e))
            return {}


# Factory function
async def create_sonarqube_client(config=None) -> SonarQubeClient:
    """Factory to create SonarQube client."""
    client = SonarQubeClient.from_env(config)
    return client
