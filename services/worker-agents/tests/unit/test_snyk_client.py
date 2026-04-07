"""
Testes unitários para SnykClient.

Cobertura:
- Inicialização e configuracao
- Teste de dependencias via API REST
- Teste de container images
- Parsing de resultados com vulnerabilidades
- Error handling
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.clients.snyk_client import (
    SnykClient,
    SnykReport,
    SnykVulnerability,
    SnykSeverity,
    SnykClientError,
    SnykAPIError,
)


class TestSnykClientInitialization:
    """Testes de inicializacao."""

    def test_init_direct(self):
        """Deve inicializar com token e org_id."""
        client = SnykClient(token="test-token", org_id="org-123")

        assert client.token == "test-token"
        assert client.org_id == "org-123"
        assert client.timeout == 300

    def test_init_custom_timeout(self):
        """Deve aceitar timeout customizado."""
        client = SnykClient(token="test-token", timeout=600)

        assert client.timeout == 600

    def test_from_env_success(self):
        """Deve criar cliente via environment."""
        with patch.dict("os.environ", {"SNYK_TOKEN": "env-token", "SNYK_ORG_ID": "env-org"}):
            client = SnykClient.from_env()

        assert client.token == "env-token"
        assert client.org_id == "env-org"

    def test_from_env_with_config(self):
        """Deve usar config quando fornecido."""
        mock_config = MagicMock()
        mock_config.snyk_token = "config-token"
        mock_config.snyk_org_id = "config-org"
        mock_config.snyk_timeout_seconds = 600

        with patch.dict("os.environ", {}, clear=True):
            client = SnykClient.from_env(config=mock_config)

        assert client.token == "config-token"
        assert client.org_id == "config-org"
        assert client.timeout == 600

    def test_from_env_missing_token(self):
        """Deve levantar erro quando token ausente."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="SNYK_TOKEN not configured"):
                SnykClient.from_env()

    async def test_close(self):
        """Deve fechar HTTP client."""
        client = SnykClient(token="test-token")
        await client.close()

        # Verify client is closed (may raise on subsequent use)


class TestSnykVulnerability:
    """Testes do modelo SnykVulnerability."""

    def test_vulnerability_creation(self):
        """Deve criar vulnerabilidade com todos os campos."""
        vuln = SnykVulnerability(
            id="SNYK-JS-LODASH-1234",
            title="Prototype Pollution",
            severity=SnykSeverity.HIGH,
            cvss_score=7.5,
            cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            cve=["CVE-2021-23337"],
            package="lodash",
            version="4.17.19",
            fixed_in=["4.17.21", "5.0.0"],
            references=["https://snyk.io/vuln/SNYK-JS-LODASH-1234"],
        )

        assert vuln.id == "SNYK-JS-LODASH-1234"
        assert vuln.severity == SnykSeverity.HIGH
        assert vuln.cvss_score == 7.5
        assert len(vuln.cve) == 1

    def test_vulnerability_minimal(self):
        """Deve criar vulnerabilidade com campos minimos."""
        vuln = SnykVulnerability(
            id="test-id",
            title="Test",
            severity=SnykSeverity.LOW,
            cvss_score=None,
            cvss_vector=None,
            cve=None,
            package="test-pkg",
            version="1.0.0",
            fixed_in=None,
            references=None,
        )

        assert vuln.id == "test-id"
        assert vuln.severity == SnykSeverity.LOW
        assert vuln.cvss_score is None


class TestSnykClientTest:
    """Testes de teste de dependencias via API."""

    @pytest.mark.asyncio
    async def test_test_dependencies_success(self):
        """Deve executar teste com sucesso via API."""
        client = SnykClient(token="test-token", org_id="org-123")

        # Mock HTTP client response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "test-123", "issues": []}

        with patch.object(client._client, "post", return_value=mock_response):
            report = await client.test_dependencies("/tmp/package.json")

        assert report.passed is True
        assert len(report.vulnerabilities) == 0
        assert report.test_id == "test-123"

    @pytest.mark.asyncio
    async def test_test_dependencies_with_vulnerabilities(self):
        """Deve parser vulnerabilidades da resposta da API."""
        client = SnykClient(token="test-token", org_id="org-123")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "test-456",
            "issues": [
                {
                    "id": "SNYK-JS-LODASH-1234",
                    "title": "Prototype Pollution",
                    "severity": "high",
                    "package": "lodash",
                    "version": "4.17.19",
                    "cvssScore": 7.5,
                    "identifiers": {"CVE": ["CVE-2021-23337"]},
                    "fixInfo": {"versions": ["4.17.21"]},
                }
            ],
        }

        with patch.object(client._client, "post", return_value=mock_response):
            with patch.object(client, "_get_org_id", return_value="org-123"):
                report = await client.test_dependencies("/tmp/package.json")

        assert report.passed is False
        assert len(report.vulnerabilities) == 1
        assert report.vulnerabilities[0].package == "lodash"
        assert report.vulnerabilities[0].severity == SnykSeverity.HIGH

    @pytest.mark.asyncio
    async def test_test_dependencies_file_not_found(self):
        """Deve retornar erro quando ficheiro nao existe."""
        client = SnykClient(token="test-token", org_id="org-123")

        report = await client.test_dependencies("/nonexistent/package.json")

        assert report.passed is False
        assert report.error is not None
        assert "File not found" in report.error

    @pytest.mark.asyncio
    async def test_test_dependencies_api_error(self):
        """Deve handle erros da API."""
        client = SnykClient(token="test-token", org_id="org-123")

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "Unauthorized"}

        with patch.object(client, "_get_org_id", return_value="org-123"):
            with patch.object(
                client._client,
                "post",
                side_effect=httpx.HTTPStatusError(
                    "Unauthorized", request=MagicMock(), response=mock_response
                ),
            ):
                report = await client.test_dependencies("/tmp/package.json")

        assert report.passed is False
        assert report.error is not None

    @pytest.mark.asyncio
    async def test_get_organization_health(self):
        """Deve obter metricas de saude da organizacao."""
        client = SnykClient(token="test-token", org_id="org-123")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "health": "good",
            "severity_counts": {"critical": 0, "high": 5, "medium": 20},
        }

        with patch.object(client._client, "get", return_value=mock_response):
            health = await client.get_organization_health()

        assert health["health"] == "good"
        assert health["severity_counts"]["high"] == 5


class TestSnykClientContainer:
    """Testes de scan de imagens de container."""

    @pytest.mark.asyncio
    async def test_container_scan_success(self):
        """Deve escanear imagem de container com sucesso."""
        client = SnykClient(token="test-token", org_id="org-123")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "imageId": "sha256:abc123",
            "layers": [
                {
                    "vulnerabilities": [
                        {
                            "id": "SNYK-DOCKER-ALPINE-1234",
                            "title": "Alpine vulnerability",
                            "severity": "medium",
                            "package": "alpine",
                            "version": "3.14.0",
                        }
                    ]
                }
            ],
        }

        with patch.object(client, "_get_org_id", return_value="org-123"):
            with patch.object(client._client, "post", return_value=mock_response):
                report = await client.test_container_image("nginx:latest")

        assert report.passed is False
        assert len(report.vulnerabilities) == 1
        assert report.test_id == "sha256:abc123"

    @pytest.mark.asyncio
    async def test_container_scan_passed(self):
        """Deve retornar passed true para imagem limpa."""
        client = SnykClient(token="test-token", org_id="org-123")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"imageId": "sha256:def456", "layers": []}

        with patch.object(client, "_get_org_id", return_value="org-123"):
            with patch.object(client._client, "post", return_value=mock_response):
                report = await client.test_container_image("myapp:1.0.0")

        assert report.passed is True
        assert len(report.vulnerabilities) == 0


class TestSnykReport:
    """Testes do modelo SnykReport."""

    def test_snyk_report_creation(self):
        """Deve criar report corretamente."""
        vulns = [
            SnykVulnerability(
                id="SNYK-JS-LODASH-1234",
                title="Prototype Pollution",
                severity=SnykSeverity.HIGH,
                cvss_score=7.5,
                cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                cve=["CVE-2021-23337"],
                package="lodash",
                version="4.17.19",
                fixed_in=["4.17.21"],
                references=["https://snyk.io/vuln/SNYK-JS-LODASH-1234"],
            )
        ]

        report = SnykReport(
            passed=False,
            vulnerabilities=vulns,
            duration_seconds=30.5,
            logs=["Testing...", "Found 1 vulnerability"],
            test_id="test-123",
        )

        assert report.passed is False
        assert len(report.vulnerabilities) == 1
        assert report.vulnerabilities[0].severity == SnykSeverity.HIGH
        assert report.duration_seconds == 30.5
        assert report.test_id == "test-123"

    def test_snyk_report_no_vulnerabilities(self):
        """Deve criar report sem vulnerabilidades."""
        report = SnykReport(
            passed=True,
            vulnerabilities=[],
            duration_seconds=15.0,
            logs=["No vulnerabilities found"],
            test_id="test-456",
        )

        assert report.passed is True
        assert len(report.vulnerabilities) == 0
        assert report.test_id == "test-456"

    def test_snyk_report_with_error(self):
        """Deve incluir informacao de erro."""
        report = SnykReport(
            passed=False,
            vulnerabilities=[],
            duration_seconds=0,
            logs=["API error"],
            error="Connection timeout",
        )

        assert report.passed is False
        assert report.error == "Connection timeout"
