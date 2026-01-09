"""
Testes unitarios para SnykClient.

Cobertura:
- Teste de dependencias
- Configuracao via env
- Parsing de resultados
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSnykClientInitialization:
    """Testes de inicializacao."""

    def test_init_direct(self):
        """Deve inicializar com token direto."""
        from src.clients.snyk_client import SnykClient

        client = SnykClient(token='test-token')

        assert client.token == 'test-token'

    def test_from_env_success(self):
        """Deve criar cliente via environment."""
        from src.clients.snyk_client import SnykClient

        with patch.dict('os.environ', {'SNYK_TOKEN': 'env-token'}):
            client = SnykClient.from_env()

            assert client.token == 'env-token'

    def test_from_env_with_config(self):
        """Deve usar config quando fornecido."""
        from src.clients.snyk_client import SnykClient

        mock_config = MagicMock()
        mock_config.snyk_token = 'config-token'

        with patch.dict('os.environ', {}, clear=True):
            client = SnykClient.from_env(config=mock_config)

            assert client.token == 'config-token'

    def test_from_env_missing_token(self):
        """Deve levantar erro quando token ausente."""
        from src.clients.snyk_client import SnykClient

        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match='not configured'):
                SnykClient.from_env()


class TestSnykClientTest:
    """Testes de teste de dependencias."""

    @pytest.mark.asyncio
    async def test_test_dependencies_success(self):
        """Deve executar teste com sucesso."""
        from src.clients.snyk_client import SnykClient

        client = SnykClient(token='test-token')

        report = await client.test_dependencies('/tmp/package.json')

        assert report.passed is True
        assert isinstance(report.vulnerabilities, list)
        assert report.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_test_dependencies_logs(self):
        """Deve retornar logs de execucao."""
        from src.clients.snyk_client import SnykClient

        client = SnykClient(token='test-token')

        report = await client.test_dependencies('/tmp/requirements.txt')

        assert report.logs is not None
        assert len(report.logs) > 0


class TestSnykReport:
    """Testes do modelo SnykReport."""

    def test_snyk_report_creation(self):
        """Deve criar report corretamente."""
        from src.clients.snyk_client import SnykReport

        vulnerabilities = [
            {
                'id': 'SNYK-JS-LODASH-1234',
                'severity': 'high',
                'title': 'Prototype Pollution',
                'package': 'lodash',
                'version': '4.17.19'
            }
        ]

        report = SnykReport(
            passed=False,
            vulnerabilities=vulnerabilities,
            duration_seconds=30.5,
            logs=['Testing...', 'Found 1 vulnerability']
        )

        assert report.passed is False
        assert len(report.vulnerabilities) == 1
        assert report.vulnerabilities[0]['severity'] == 'high'
        assert report.duration_seconds == 30.5

    def test_snyk_report_no_vulnerabilities(self):
        """Deve criar report sem vulnerabilidades."""
        from src.clients.snyk_client import SnykReport

        report = SnykReport(
            passed=True,
            vulnerabilities=[],
            duration_seconds=15.0,
            logs=['No vulnerabilities found']
        )

        assert report.passed is True
        assert len(report.vulnerabilities) == 0

    def test_snyk_report_optional_fields(self):
        """Deve aceitar campos opcionais como None."""
        from src.clients.snyk_client import SnykReport

        report = SnykReport(
            passed=True,
            vulnerabilities=[],
            duration_seconds=None,
            logs=None
        )

        assert report.duration_seconds is None
        assert report.logs is None
