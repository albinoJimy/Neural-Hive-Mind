"""
Snyk Client - Integration with Snyk API for vulnerability scanning.

Supports:
- REST API v1 for testing dependencies and container images
- Organization-level test results
- Dependency scanning (pip, npm, maven, gradle, etc.)
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class SnykSeverity(str, Enum):
    """Vulnerability severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SnykVulnerability:
    """Individual vulnerability details."""

    id: str
    title: str
    severity: SnykSeverity
    cvss_score: float | None
    cvss_vector: str | None
    cve: list[str] | None
    package: str
    version: str
    fixed_in: list[str] | None
    references: list[str] | None


@dataclass
class SnykReport:
    """Resultado resumido do Snyk scan."""

    passed: bool
    vulnerabilities: list[SnykVulnerability]
    duration_seconds: float
    logs: list[str]
    test_id: str | None = None
    error: str | None = None


class SnykClientError(Exception):
    """Base exception for Snyk client errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


class SnykAPIError(SnykClientError):
    """API request errors."""

    pass


class SnykClient:
    """
    Snyk REST API Client for vulnerability scanning.

    API Docs: https://snyk.docs.apiary.io/#reference
    """

    API_BASE = "https://api.snyk.io/api/v1"
    TEST_ENDPOINT = "/test/org"

    def __init__(self, token: str, org_id: str | None = None, timeout: int = 300):
        """
        Initialize Snyk client.

        Args:
            token: Snyk API token
            org_id: Organization ID (optional, uses default if not provided)
            timeout: Request timeout in seconds
        """
        self.token = token
        self.org_id = org_id
        self.timeout = timeout
        self.logger = logger.bind(service="snyk_client")

        self._client = httpx.AsyncClient(
            base_url=self.API_BASE,
            headers={"Authorization": f"token {self.token}"},
            timeout=timeout,
        )

    @classmethod
    def from_env(cls, config=None) -> "SnykClient":
        """Create client from environment variables."""
        token = os.getenv("SNYK_TOKEN") or getattr(config, "snyk_token", None)
        if not token:
            raise ValueError("SNYK_TOKEN not configured")
        org_id = os.getenv("SNYK_ORG_ID") or getattr(config, "snyk_org_id", None)
        timeout = getattr(config, "snyk_timeout_seconds", 300)
        return cls(token=token, org_id=org_id, timeout=timeout)

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()

    async def _get_org_id(self) -> str:
        """Get organization ID if not set."""
        if self.org_id:
            return self.org_id

        # Fetch default org from user profile
        try:
            response = await self._client.get("/orgs")
            response.raise_for_status()
            data = response.json()
            if data.get("orgs") and len(data["orgs"]) > 0:
                self.org_id = data["orgs"][0]["id"]
                self.logger.debug("snyk_org_resolved", org_id=self.org_id)
                return self.org_id
        except httpx.HTTPStatusError as e:
            raise SnykAPIError(f"Failed to fetch organization: {e.response.status_code}") from e

        raise SnykClientError("No Snyk organization found")

    async def test_dependencies(
        self,
        manifest_path: str,
        severity_threshold: SnykSeverity = SnykSeverity.MEDIUM,
    ) -> SnykReport:
        """
        Test dependencies for vulnerabilities using Snyk API.

        Args:
            manifest_path: Path to dependency manifest (package.json, requirements.txt, etc.)
            severity_threshold: Minimum severity to fail the test

        Returns:
            SnykReport with scan results
        """
        start_time = datetime.now(timezone.utc)
        logs = []

        try:
            org_id = await self._get_org_id()
            self.logger.info("snyk_test_started", manifest=manifest_path, org=org_id)

            # Read manifest file
            try:
                with open(manifest_path, "rb") as f:
                    files = {
                        "file": (os.path.basename(manifest_path), f, "application/octet-stream")
                    }
            except FileNotFoundError:
                return SnykReport(
                    passed=False,
                    vulnerabilities=[],
                    duration_seconds=0,
                    logs=[f"Manifest not found: {manifest_path}"],
                    error=f"File not found: {manifest_path}",
                )

            # API request to test dependencies
            endpoint = f"/org/{org_id}/test"
            params = {
                "severityThreshold": severity_threshold.value,
                "docker": "false",  # Not testing Docker images
            }

            response = await self._client.post(
                endpoint,
                files=files,
                params=params,
            )
            response.raise_for_status()
            result = response.json()

            # Parse vulnerabilities
            vulnerabilities = []
            for issue in result.get("issues", []):
                vuln = SnykVulnerability(
                    id=issue.get("id", ""),
                    title=issue.get("title", "Unknown vulnerability"),
                    severity=SnykSeverity(issue.get("severity", "low")),
                    cvss_score=issue.get("cvssScore"),
                    cvss_vector=issue.get("cvssVector"),
                    cve=issue.get("identifiers", {}).get("CVE", []),
                    package=issue.get("package", ""),
                    version=issue.get("version", ""),
                    fixed_in=issue.get("fixInfo", {}).get("versions", []),
                    references=issue.get("references", []),
                )
                vulnerabilities.append(vuln)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            passed = len(vulnerabilities) == 0

            logs.append(f"Scanned {len(vulnerabilities)} vulnerabilities")
            logs.append(f"Test duration: {duration:.2f}s")

            self.logger.info(
                "snyk_test_completed",
                manifest=manifest_path,
                passed=passed,
                vuln_count=len(vulnerabilities),
            )

            return SnykReport(
                passed=passed,
                vulnerabilities=vulnerabilities,
                duration_seconds=duration,
                logs=logs,
                test_id=result.get("id"),
            )

        except httpx.HTTPStatusError as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            error_msg = f"Snyk API error: {e.response.status_code}"
            try:
                error_detail = e.response.json()
                error_msg = f"Snyk API error: {error_detail}"
            except Exception:
                pass

            self.logger.error("snyk_test_failed", error=error_msg)
            return SnykReport(
                passed=False,
                vulnerabilities=[],
                duration_seconds=duration,
                logs=logs + [error_msg],
                error=error_msg,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.exception("snyk_test_exception")
            return SnykReport(
                passed=False,
                vulnerabilities=[],
                duration_seconds=duration,
                logs=logs + [f"Exception: {str(e)}"],
                error=str(e),
            )

    async def test_container_image(
        self,
        image: str,
        severity_threshold: SnykSeverity = SnykSeverity.MEDIUM,
    ) -> SnykReport:
        """
        Test a container image for vulnerabilities.

        Args:
            image: Container image reference (e.g., "nginx:latest")
            severity_threshold: Minimum severity to fail the test

        Returns:
            SnykReport with scan results
        """
        start_time = datetime.now(timezone.utc)
        logs = []

        try:
            org_id = await self._get_org_id()
            self.logger.info("snyk_container_test_started", image=image, org=org_id)

            endpoint = f"/org/{org_id}/container"
            payload = {
                "image": image,
                "severityThreshold": severity_threshold.value,
            }

            response = await self._client.post(endpoint, json=payload)
            response.raise_for_status()
            result = response.json()

            # Parse vulnerabilities
            vulnerabilities = []
            for layer_data in result.get("layers", []):
                for issue in layer_data.get("vulnerabilities", []):
                    vuln = SnykVulnerability(
                        id=issue.get("id", ""),
                        title=issue.get("title", "Unknown"),
                        severity=SnykSeverity(issue.get("severity", "low")),
                        cvss_score=issue.get("cvssScore"),
                        cvss_vector=issue.get("cvssVector"),
                        cve=issue.get("identifiers", {}).get("CVE", []),
                        package=issue.get("package", ""),
                        version=issue.get("version", ""),
                        fixed_in=issue.get("fixInfo", {}).get("versions", []),
                        references=issue.get("references", []),
                    )
                    vulnerabilities.append(vuln)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            passed = len(vulnerabilities) == 0

            logs.append(f"Scanned image {image}")
            logs.append(f"Found {len(vulnerabilities)} vulnerabilities")
            logs.append(f"Test duration: {duration:.2f}s")

            self.logger.info(
                "snyk_container_test_completed",
                image=image,
                passed=passed,
                vuln_count=len(vulnerabilities),
            )

            return SnykReport(
                passed=passed,
                vulnerabilities=vulnerabilities,
                duration_seconds=duration,
                logs=logs,
                test_id=result.get("imageId"),
            )

        except httpx.HTTPStatusError as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            error_msg = f"Snyk API error: {e.response.status_code}"
            self.logger.error("snyk_container_test_failed", error=error_msg)
            return SnykReport(
                passed=False,
                vulnerabilities=[],
                duration_seconds=duration,
                logs=logs + [error_msg],
                error=error_msg,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.exception("snyk_container_test_exception")
            return SnykReport(
                passed=False,
                vulnerabilities=[],
                duration_seconds=duration,
                logs=logs + [f"Exception: {str(e)}"],
                error=str(e),
            )

    async def get_organization_health(self) -> dict:
        """Get organization health metrics."""
        org_id = await self._get_org_id()
        endpoint = f"/org/{org_id}/health-metrics"

        response = await self._client.get(endpoint)
        response.raise_for_status()
        return response.json()


# Factory function for easy instantiation
async def create_snyk_client(config=None) -> SnykClient:
    """Factory to create and initialize Snyk client."""
    client = SnykClient.from_env(config)
    return client
