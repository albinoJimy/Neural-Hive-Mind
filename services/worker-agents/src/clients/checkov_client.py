"""
Checkov Client - Integration with Checkov for Infrastructure-as-Code security scanning.

Supports:
- CLI execution for scanning IaC files (Terraform, CloudFormation, Kubernetes, etc.)
- Output parsing (JSON, SARIF, JUnit)
- Docker container support
"""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class CheckovSeverity(str, Enum):
    """Checkov severity levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


@dataclass
class CheckovFinding:
    """Individual security/compliance finding."""

    check_id: str
    check_name: str
    severity: CheckovSeverity
    category: str
    resource: str
    file_path: str
    file_line_range: tuple[int, int] | None
    description: str
    pass_or_fail: str
    code: str | None


@dataclass
class CheckovSummary:
    """Summary of Checkov scan results."""

    passed: bool
    failed: int
    skipped: int
    parsing_errors: int
    total: int
    severity_counts: dict[str, int]


@dataclass
class CheckovReport:
    """Resultado de um scan Checkov."""

    passed: bool
    findings: list[CheckovFinding]
    summary: CheckovSummary
    duration_seconds: float
    logs: list[str]
    exit_code: int
    output_format: str = "json"
    error: str | None = None


class CheckovError(Exception):
    """Base exception for Checkov client errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


class CheckovNotFoundError(CheckovError):
    """Checkov CLI not found."""

    pass


class CheckovExecutionError(CheckovError):
    """Error executing Checkov scan."""

    pass


class CheckovClient:
    """
    Checkov Client for IaC security scanning.

    Executes Checkov CLI and parses JSON output.
    """

    CHECKOV_CMD = "checkov"

    # Default directories to scan
    DEFAULT_FRAMEWORKS = [
        "terraform",
        "cloudformation",
        "kubernetes",
        "helm",
        "dockerfile",
        "github_configuration",
    ]

    def __init__(self, config=None):
        """
        Initialize Checkov client.

        Args:
            config: Optional configuration object with timeout, frameworks, etc.
        """
        self.logger = logger.bind(service="checkov_client")
        self.timeout = getattr(config, "checkov_timeout_seconds", 300)
        self.framework = getattr(config, "checkov_framework", "all")
        self.output_format = getattr(config, "checkov_output_format", "json")
        self.directory = getattr(config, "checkov_directory", ".")
        self.soft_fail = getattr(config, "checkov_soft_fail", False)
        self.compact = getattr(config, "checkov_compact", False)
        self.quiet = getattr(config, "checkov_quiet", True)

    @classmethod
    def from_env(cls, config=None) -> "CheckovClient":
        """Create client from environment variables."""
        return cls(config)

    async def _verify_checkov_installed(self) -> str:
        """Verify Checkov is installed and return version."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.CHECKOV_CMD,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            return stdout.decode().strip()
        except FileNotFoundError:
            raise CheckovNotFoundError(
                f"{self.CHECKOV_CMD} not found. Install via: pip install checkov"
            )
        except asyncio.TimeoutError:
            raise CheckovError("Checkov version check timed out")

    def _build_command(
        self,
        directory: str,
        framework: str = "all",
        compact: bool = False,
    ) -> list[str]:
        """Build Checkov command arguments."""
        cmd = [
            self.CHECKOV_CMD,
            "-d",
            directory,
            "--framework",
            framework,
            "--output",
            self.output_format,
            "--quiet",
            "true",
        ]

        if self.soft_fail:
            cmd.extend(["--soft-fail"])

        if compact:
            cmd.append("--compact")

        return cmd

    async def scan_iac(
        self,
        directory: str,
        framework: str = "all",
    ) -> CheckovReport:
        """
        Execute IaC scan using Checkov CLI.

        Args:
            directory: Path to IaC directory to scan
            framework: Checkov framework (all, terraform, kubernetes, etc.)

        Returns:
            CheckovReport with scan findings
        """
        start_time = datetime.now(timezone.utc)
        logs = []

        try:
            # Verify Checkov installation
            version = await self._verify_checkov_installed()
            logs.append(f"Checkov version: {version}")

            if not os.path.isdir(directory):
                return CheckovReport(
                    passed=False,
                    findings=[],
                    summary=CheckovSummary(
                        passed=False,
                        failed=0,
                        skipped=0,
                        parsing_errors=0,
                        total=0,
                        severity_counts={},
                    ),
                    duration_seconds=0,
                    logs=[f"Directory not found: {directory}"],
                    exit_code=1,
                    error=f"Directory not found: {directory}",
                )

            self.logger.info(
                "checkov_scan_started",
                directory=directory,
                framework=framework,
            )

            # Build command
            cmd = self._build_command(directory, framework, self.compact)

            logs.append(f"Executing: {' '.join(cmd[:4])}...")

            # Execute Checkov
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout,
                )
                exit_code = proc.returncode

            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                return CheckovReport(
                    passed=False,
                    findings=[],
                    summary=CheckovSummary(
                        passed=False,
                        failed=0,
                        skipped=0,
                        parsing_errors=0,
                        total=0,
                        severity_counts={},
                    ),
                    duration_seconds=duration,
                    logs=[f"Scan timeout after {self.timeout}s"],
                    exit_code=-1,
                    error="Scan timeout",
                )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Parse output
            findings = []
            summary = None

            if self.output_format == "json":
                try:
                    data = json.loads(stdout)
                    results = self._parse_json_results(data, directory)
                    findings = results.get("findings", [])
                    summary = results.get("summary")

                except json.JSONDecodeError:
                    logs.append("Failed to parse JSON output")
                    self.logger.warning("checkov_json_parse_failed", stderr=stderr.decode())

            # Log stderr if any
            if stderr:
                stderr_str = stderr.decode().strip()
                if stderr_str:
                    logs.append(f"Checkov warnings: {stderr_str[:200]}")

            # Build summary from exit code if not parsed
            if not summary:
                if exit_code == 0:
                    summary = CheckovSummary(
                        passed=True,
                        failed=0,
                        skipped=0,
                        parsing_errors=0,
                        total=0,
                        severity_counts={},
                    )
                else:
                    # Estimate from findings
                    failed = len([f for f in findings if f.pass_or_fail == "fail"])
                    summary = CheckovSummary(
                        passed=failed == 0,
                        failed=failed,
                        skipped=0,
                        parsing_errors=0,
                        total=len(findings),
                        severity_counts=self._count_severities(findings),
                    )

            passed = summary.passed if summary else exit_code == 0
            logs.append(f"Exit code: {exit_code}")
            logs.append(f"Findings: {summary.total if summary else len(findings)}")

            self.logger.info(
                "checkov_scan_completed",
                directory=directory,
                passed=passed,
                total_findings=summary.total if summary else len(findings),
                duration=duration,
            )

            return CheckovReport(
                passed=passed,
                findings=findings,
                summary=summary
                or CheckovSummary(
                    passed=False,
                    failed=0,
                    skipped=0,
                    parsing_errors=0,
                    total=0,
                    severity_counts={},
                ),
                duration_seconds=duration,
                logs=logs,
                exit_code=exit_code,
            )

        except CheckovNotFoundError as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return CheckovReport(
                passed=False,
                findings=[],
                summary=CheckovSummary(
                    passed=False,
                    failed=0,
                    skipped=0,
                    parsing_errors=0,
                    total=0,
                    severity_counts={},
                ),
                duration_seconds=duration,
                logs=[str(e)],
                exit_code=1,
                error=str(e),
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.exception("checkov_scan_exception")
            return CheckovReport(
                passed=False,
                findings=[],
                summary=CheckovSummary(
                    passed=False,
                    failed=0,
                    skipped=0,
                    parsing_errors=0,
                    total=0,
                    severity_counts={},
                ),
                duration_seconds=duration,
                logs=[f"Exception: {str(e)}"],
                exit_code=1,
                error=str(e),
            )

    def _parse_json_results(self, data: dict, scan_dir: str) -> dict:
        """Parse Checkov JSON output."""
        findings = []
        summary_data = {}

        # Parse results.checks if available (Checkov v1 format)
        for check in data.get("results", {}).get("failed_checks", []):
            finding = CheckovFinding(
                check_id=check.get("check_id", ""),
                check_name=check.get("check_name", ""),
                severity=CheckovSeverity(check.get("severity", "UNKNOWN")),
                category=check.get("check_class", ""),
                resource=check.get("resource", ""),
                file_path=check.get("file_path", ""),
                file_line_range=(
                    tuple(check.get("file_line_range", [0, 0]))
                    if "file_line_range" in check
                    else None
                ),
                description=check.get("check", {}).get("name", ""),
                pass_or_fail="fail",
                code=check.get("code", ""),
            )
            findings.append(finding)

        # Parse summary
        for summary in data.get("summary", []):
            if summary.get("check_type") == "checkov":
                summary_data = CheckovSummary(
                    passed=summary.get("passed", False),
                    failed=summary.get("failed", 0),
                    skipped=summary.get("skipped", 0),
                    parsing_errors=summary.get("parsing_errors", 0),
                    total=summary.get("total", 0),
                    severity_counts=summary.get("severity_counts", {}),
                )

        return {
            "findings": findings,
            "summary": summary_data,
        }

    def _count_severities(self, findings: list[CheckovFinding]) -> dict[str, int]:
        """Count findings by severity."""
        counts = {}
        for finding in findings:
            sev = finding.severity.value
            counts[sev] = counts.get(sev, 0) + 1
        return counts


# Factory function
async def create_checkov_client(config=None) -> CheckovClient:
    """Factory to create Checkov client."""
    client = CheckovClient.from_env(config)
    return client
