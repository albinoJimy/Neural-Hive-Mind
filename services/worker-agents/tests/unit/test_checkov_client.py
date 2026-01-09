"""
Testes unitarios para CheckovClient.

Cobertura:
- Scan de IaC
- Parsing de resultados
- Timeout handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCheckovClientScan:
    """Testes de scan IaC."""

    @pytest.mark.asyncio
    async def test_scan_iac_success(self):
        """Deve executar scan com sucesso."""
        from src.clients.checkov_client import CheckovClient

        client = CheckovClient()

        report = await client.scan_iac('/tmp/terraform')

        assert report.passed is True
        assert isinstance(report.findings, list)
        assert report.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_scan_iac_with_config(self):
        """Deve usar timeout do config."""
        mock_config = MagicMock()
        mock_config.checkov_timeout_seconds = 600

        from src.clients.checkov_client import CheckovClient

        client = CheckovClient(config=mock_config)

        assert client.timeout == 600

    @pytest.mark.asyncio
    async def test_scan_iac_default_timeout(self):
        """Deve usar timeout padrao."""
        from src.clients.checkov_client import CheckovClient

        client = CheckovClient()

        assert client.timeout == 300


class TestCheckovReport:
    """Testes do modelo CheckovReport."""

    def test_checkov_report_creation(self):
        """Deve criar report corretamente."""
        from src.clients.checkov_client import CheckovReport

        findings = [
            {'check_id': 'CKV_AWS_1', 'severity': 'HIGH', 'message': 'S3 bucket not encrypted'}
        ]

        report = CheckovReport(
            passed=False,
            findings=findings,
            duration_seconds=45.5,
            logs=['Scanning...', 'Complete']
        )

        assert report.passed is False
        assert len(report.findings) == 1
        assert report.findings[0]['check_id'] == 'CKV_AWS_1'
        assert report.duration_seconds == 45.5
        assert len(report.logs) == 2

    def test_checkov_report_empty_findings(self):
        """Deve criar report sem findings."""
        from src.clients.checkov_client import CheckovReport

        report = CheckovReport(
            passed=True,
            findings=[],
            duration_seconds=10.0,
            logs=['No issues found']
        )

        assert report.passed is True
        assert len(report.findings) == 0
