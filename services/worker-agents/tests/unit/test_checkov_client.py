"""
Testes unitários para CheckovClient.

Cobertura:
- Inicializacao e configuracao
- Scan de IaC via CLI
- Parsing de resultados JSON
- Timeout handling
- Error handling
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.clients.checkov_client import (
    CheckovClient,
    CheckovFinding,
    CheckovNotFoundError,
    CheckovReport,
    CheckovSeverity,
    CheckovSummary,
)


class TestCheckovClientInitialization:
    """Testes de inicializacao."""

    def test_init_direct(self):
        """Deve inicializar com defaults."""
        client = CheckovClient()

        assert client.timeout == 300
        assert self.framework == "all"
        assert client.output_format == "json"

    def test_init_with_config(self):
        """Deve aceitar configuracao customizada."""
        mock_config = MagicMock()
        mock_config.checkov_timeout_seconds = 600
        mock_config.checkov_framework = "terraform"
        mock_config.checkov_compact = True

        client = CheckovClient(config=mock_config)

        assert client.timeout == 600
        assert client.framework == "terraform"
        assert client.compact is True

    def test_from_env(self):
        """Deve criar cliente via from_env."""
        client = CheckovClient.from_env()

        assert client.timeout == 300


class TestCheckovClientScan:
    """Testes de scan IaC via CLI."""

    @pytest.mark.asyncio()
    async def test_scan_iac_success(self):
        """Deve executar scan com sucesso."""
        client = CheckovClient()

        # Create temporary directory with test file
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a dummy Terraform file
            tf_file = Path(tmpdir) / "main.tf"
            tf_file.write_text("""
resource "aws_s3_bucket" "example" {
  bucket = "my-test-bucket"
}

resource "aws_s3_bucket" "example2" {
  bucket = "another-test-bucket"
}
""")

            with patch.object(client, "_verify_checkov_installed", return_value="Checkov v2.3.0"):
                with patch(
                    "asyncio.create_subprocess_exec",
                    return_value=AsyncMock(
                        communicate=lambda timeout: (b'{"summary": {"passed": true}}', b"")
                    ),
                ):
                    report = await client.scan_iac(str(tf_file))

        assert report.passed is True
        assert isinstance(report.findings, list)
        assert report.duration_seconds >= 0

    @pytest.mark.asyncio()
    async def test_scan_iac_directory_not_found(self):
        """Deve retornar erro quando diretorio nao existe."""
        client = CheckovClient()

        report = await client.scan_iac("/nonexistent/directory")

        assert report.passed is False
        assert report.error is not None
        assert "not found" in report.error.lower()

    @pytest.mark.asyncio()
    async def test_scan_iac_timeout(self):
        """Deve lidar com timeout do scan."""
        client = CheckovClient(timeout=1)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(client, "_verify_checkov_installed", return_value="Checkov v2.3.0"):
                # Mock timeout
                async def mock_sleep(*args, **kwargs):
                    await asyncio.sleep(2)

                with patch("asyncio.sleep", side_effect=mock_sleep):
                    report = await client.scan_iac(tmpdir)

        assert report.passed is False
        assert "timeout" in report.error.lower()

    @pytest.mark.asyncio()
    async def test_scan_iac_with_framework(self):
        """Deve aceitar parametro de framework."""
        client = CheckovClient()

        with tempfile.TemporaryDirectory() as tmpdir:
            tf_file = Path(tmpdir) / "main.tf"
            tf_file.write_text('resource "aws_s3_bucket" "example" {}')

            with patch.object(client, "_verify_checkov_installed", return_value="Checkov v2.3.0"):
                with patch(
                    "asyncio.create_subprocess_exec",
                    return_value=AsyncMock(
                        communicate=lambda timeout: (b'{"summary": {"passed": true}}', b"")
                    ),
                ):
                    report = await client.scan_iac(tmpdir, framework="terraform")

        assert report.passed is True


class TestCheckovClientVersion:
    """Testes de verificacao de instalacao."""

    @pytest.mark.asyncio()
    async def test_verify_checkov_installed_success(self):
        """Deve retornar versao quando Checkov instalado."""
        client = CheckovClient()

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=AsyncMock(communicate=lambda timeout: (b"Checkov v2.3.45\n", b"")),
        ):
            version = await client._verify_checkov_installed()

        assert "Checkov" in version
        assert "2.3" in version

    @pytest.mark.asyncio()
    async def test_verify_checkov_not_installed(self):
        """Deve levantar erro quando Checkov nao instalado."""
        client = CheckovClient()

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            with pytest.raises(CheckovNotFoundError):
                await client._verify_checkov_installed()


class TestCheckovReport:
    """Testes do modelo CheckovReport."""

    def test_checkov_report_creation(self):
        """Deve criar report corretamente."""
        findings = [
            CheckovFinding(
                check_id="CKV_AWS_1",
                check_name="S3 Bucket Encryption",
                severity=CheckovSeverity.HIGH,
                category="aws",
                resource="aws_s3_bucket.example",
                file_path="main.tf",
                file_line_range=(5, 8),
                description="S3 bucket not encrypted",
                pass_or_fail="fail",
                code='resource "aws_s3_bucket" "example" { ... }',
            )
        ]

        summary = CheckovSummary(
            passed=False,
            failed=1,
            skipped=0,
            parsing_errors=0,
            total=1,
            severity_counts={"HIGH": 1},
        )

        report = CheckovReport(
            passed=False,
            findings=findings,
            summary=summary,
            duration_seconds=45.5,
            logs=["Scanning...", "Complete"],
            exit_code=1,
        )

        assert report.passed is False
        assert len(report.findings) == 1
        assert report.summary.total == 1
        assert report.summary.severity_counts["HIGH"] == 1

    def test_checkov_report_passed(self):
        """Deve criar report passed."""
        report = CheckovReport(
            passed=True,
            findings=[],
            summary=CheckovSummary(
                passed=True,
                failed=0,
                skipped=0,
                parsing_errors=0,
                total=0,
                severity_counts={},
            ),
            duration_seconds=10.0,
            logs=["No issues found"],
            exit_code=0,
        )

        assert report.passed is True
        assert len(report.findings) == 0
        assert report.summary.passed is True

    def test_checkov_report_with_error(self):
        """Deve incluir informacao de erro."""
        report = CheckovReport(
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
            logs=["Scan error"],
            exit_code=1,
            error="Checkov timeout",
        )

        assert report.error == "Checkov timeout"


class TestCheckovFinding:
    """Testes do modelo CheckovFinding."""

    def test_finding_creation(self):
        """Deve criar finding com todos os campos."""
        finding = CheckovFinding(
            check_id="CKV_AWS_1",
            check_name="S3 Bucket Server-Side Encryption",
            severity=CheckovSeverity.CRITICAL,
            category="aws_security",
            resource="aws_s3_bucket.my_bucket",
            file_path="terraform/s3.tf",
            file_line_range=(10, 15),
            description="S3 bucket lacks server-side encryption",
            pass_or_fail="fail",
            code='resource "aws_s3_bucket" "my_bucket" {}',
        )

        assert finding.check_id == "CKV_AWS_1"
        assert finding.severity == CheckovSeverity.CRITICAL
        assert finding.file_path == "terraform/s3.tf"
        assert finding.file_line_range == (10, 15)

    def test_finding_minimal(self):
        """Deve criar finding com campos minimos."""
        finding = CheckovFinding(
            check_id="CKV2_AWS_1",
            check_name="Some Check",
            severity=CheckovSeverity.MEDIUM,
            category="general",
            resource="unknown",
            file_path="unknown.tf",
            file_line_range=None,
            description="A finding",
            pass_or_fail="warn",
            code=None,
        )

        assert finding.check_id == "CKV2_AWS_1"
        assert finding.file_line_range is None


class TestCheckovSummary:
    """Testes do modelo CheckovSummary."""

    def test_summary_creation(self):
        """Deve criar summary corretamente."""
        summary = CheckovSummary(
            passed=False,
            failed=5,
            skipped=2,
            parsing_errors=1,
            total=8,
            severity_counts={
                CheckovSeverity.CRITICAL: 1,
                CheckovSeverity.HIGH: 2,
                CheckovSeverity.MEDIUM: 5,
            },
        )

        assert summary.total == 8
        assert summary.failed == 5
        assert summary.skipped == 2
        assert summary.parsing_errors == 1
        assert summary.severity_counts[CheckovSeverity.MEDIUM] == 5

    def test_summary_all_zero(self):
        """Deve criar summary com todos zeros."""
        summary = CheckovSummary(
            passed=True,
            failed=0,
            skipped=0,
            parsing_errors=0,
            total=0,
            severity_counts={},
        )

        assert summary.total == 0
        assert summary.passed is True


# Factory test
@pytest.mark.asyncio()
async def test_create_checkov_client():
    """Test factory function."""
    client = await create_checkov_client()

    assert client.timeout == 300
