"""
Testes unitários para TrivyClient.

Valida a execução de scans de vulnerabilidades com Trivy CLI.
"""

import pytest
import json
import shutil
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.clients.trivy_client import TrivyClient
from src.models.artifact import ValidationStatus


@pytest.fixture
def trivy_client_with_trivy():
    """Instância do TrivyClient com Trivy instalado."""
    with patch('shutil.which', return_value='/usr/bin/trivy'):
        client = TrivyClient(
            enabled=True,
            severity='CRITICAL,HIGH',
            timeout=300
        )
        # Forçar a detecção do Trivy
        client.trivy_path = '/usr/bin/trivy'
        client._trivy_available = True
        return client


@pytest.fixture
def trivy_client():
    """Instância do TrivyClient (sem Trivy instalado por padrão)."""
    return TrivyClient(
        enabled=True,
        severity='CRITICAL,HIGH',
        timeout=300
    )


class TestTrivyClientInitialization:
    """Testes de inicialização do cliente."""

    def test_init_with_defaults(self):
        """Testa inicialização com valores padrão."""
        client = TrivyClient()
        assert client.enabled is True
        assert client.severity == 'CRITICAL,HIGH'
        assert client.timeout == 600

    def test_init_with_custom_values(self):
        """Testa inicialização com valores customizados."""
        client = TrivyClient(
            enabled=False,
            severity='HIGH,MEDIUM',
            timeout=120
        )
        assert client.enabled is False
        assert client.severity == 'HIGH,MEDIUM'
        assert client.timeout == 120

    def test_trivy_version_constant(self):
        """Testa que versão do Trivy está definida."""
        assert TrivyClient.TRIVY_VERSION == '0.45.0'


class TestTrivyClientDisabled:
    """Testes de comportamento quando cliente está desabilitado."""

    @pytest.mark.asyncio
    async def test_scan_container_image_when_disabled(self):
        """Testa que scan retorna SKIPPED quando desabilitado."""
        client = TrivyClient(enabled=False)

        result = await client.scan_container_image('nginx:latest')

        assert result.status == ValidationStatus.SKIPPED
        assert result.issues_count == 0

    @pytest.mark.asyncio
    async def test_scan_filesystem_when_disabled(self):
        """Testa que scan de filesystem retorna SKIPPED quando desabilitado."""
        client = TrivyClient(enabled=False)

        result = await client.scan_filesystem('/tmp/app')

        assert result.status == ValidationStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_scan_iac_when_disabled(self):
        """Testa que scan de IaC retorna SKIPPED quando desabilitado."""
        client = TrivyClient(enabled=False)

        result = await client.scan_iac('/tmp/terraform')

        assert result.status == ValidationStatus.SKIPPED


class TestTrivyVulnerabilityParsing:
    """Testes de parse de vulnerabilidades."""

    def test_parse_critical_vulnerabilities(self, trivy_client):
        """Testa parse de vulnerabilidades críticas."""
        trivy_output = {
            'Results': [{
                'Vulnerabilities': [
                    {'Severity': 'CRITICAL', 'VulnerabilityID': 'CVE-2023-1234'},
                    {'Severity': 'CRITICAL', 'VulnerabilityID': 'CVE-2023-5678'},
                ]
            }]
        }

        counts = trivy_client._parse_vulnerabilities(trivy_output)

        assert counts['critical'] == 2
        assert counts['high'] == 0
        assert counts['medium'] == 0
        assert counts['low'] == 0

    def test_parse_all_severities(self, trivy_client):
        """Testa parse de todas as severidades."""
        trivy_output = {
            'Results': [{
                'Vulnerabilities': [
                    {'Severity': 'CRITICAL', 'VulnerabilityID': 'CVE-1'},
                    {'Severity': 'HIGH', 'VulnerabilityID': 'CVE-2'},
                    {'Severity': 'MEDIUM', 'VulnerabilityID': 'CVE-3'},
                    {'Severity': 'LOW', 'VulnerabilityID': 'CVE-4'},
                    # UNKNOWN não é contado no parse atual
                ]
            }]
        }

        counts = trivy_client._parse_vulnerabilities(trivy_output)

        assert counts['critical'] == 1
        assert counts['high'] == 1
        assert counts['medium'] == 1
        assert counts['low'] == 1

    def test_parse_misconfigurations(self, trivy_client):
        """Testa parse de misconfigurações."""
        trivy_output = {
            'Results': [{
                'Misconfigurations': [
                    {'Severity': 'CRITICAL', 'Title': 'Root user enabled'},
                    {'Severity': 'HIGH', 'Title': 'No healthcheck'},
                ]
            }]
        }

        counts = trivy_client._parse_vulnerabilities(trivy_output)

        assert counts['critical'] == 1
        assert counts['high'] == 1

    def test_parse_empty_results(self, trivy_client):
        """Testa parse de resultados vazios."""
        trivy_output = {'Results': []}

        counts = trivy_client._parse_vulnerabilities(trivy_output)

        assert counts['critical'] == 0
        assert counts['high'] == 0
        assert counts['medium'] == 0
        assert counts['low'] == 0

    def test_parse_no_vulnerabilities(self, trivy_client):
        """Testa parse quando não há vulnerabilidades."""
        trivy_output = {
            'Results': [{
                'Vulnerabilities': []
            }]
        }

        counts = trivy_client._parse_vulnerabilities(trivy_output)

        assert all(v == 0 for v in counts.values())


class TestTrivyStatusAndScore:
    """Testes de determinação de status e score."""

    def test_critical_vulnerabilities_failed_status(self, trivy_client):
        """Testa que vulnerabilidades críticas resultam em status FAILED."""
        counts = {'critical': 1, 'high': 0, 'medium': 0, 'low': 0}
        status, score = trivy_client._determine_status_and_score(counts)

        assert status == ValidationStatus.FAILED
        assert score == 0.3

    def test_high_vulnerabilities_warning_status(self, trivy_client):
        """Testa que vulnerabilidades HIGH resultam em WARNING."""
        counts = {'critical': 0, 'high': 2, 'medium': 0, 'low': 0}
        status, score = trivy_client._determine_status_and_score(counts)

        assert status == ValidationStatus.WARNING
        assert score == 0.6

    def test_medium_vulnerabilities_warning_status(self, trivy_client):
        """Testa que vulnerabilidades MEDIUM resultam em WARNING."""
        counts = {'critical': 0, 'high': 0, 'medium': 5, 'low': 0}
        status, score = trivy_client._determine_status_and_score(counts)

        assert status == ValidationStatus.WARNING
        assert score == 0.8

    def test_low_vulnerabilities_passed_status(self, trivy_client):
        """Testa que vulnerabilidades LOW resultam em PASSED."""
        counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 3}
        status, score = trivy_client._determine_status_and_score(counts)

        assert status == ValidationStatus.PASSED
        assert score == 0.9

    def test_no_vulnerabilities_perfect_score(self, trivy_client):
        """Testa que sem vulnerabilidades resulta em score 1.0."""
        counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        status, score = trivy_client._determine_status_and_score(counts)

        assert status == ValidationStatus.PASSED
        assert score == 1.0


class TestTrivyResultCreation:
    """Testes de criação de resultados."""

    def test_create_result_with_vulnerabilities(self, trivy_client):
        """Testa criação de ValidationResult com vulnerabilidades."""
        counts = {'critical': 1, 'high': 2, 'medium': 3, 'low': 4}

        result = trivy_client._create_result(
            status=ValidationStatus.FAILED,
            score=0.3,
            counts=counts,
            duration_ms=5000
        )

        assert result.status == ValidationStatus.FAILED
        assert result.score == 0.3
        assert result.issues_count == 10
        assert result.critical_issues == 1
        assert result.high_issues == 2
        assert result.medium_issues == 3
        assert result.low_issues == 4
        assert result.duration_ms == 5000
        assert isinstance(result.executed_at, datetime)

    def test_create_skipped_result(self, trivy_client):
        """Testa criação de resultado SKIPPED."""
        result = trivy_client._create_skipped_result()

        assert result.status == ValidationStatus.SKIPPED
        assert result.score is None
        assert result.issues_count == 0

    def test_create_failed_result(self, trivy_client):
        """Testa criação de resultado FAILED."""
        result = trivy_client._create_failed_result(3000)

        assert result.status == ValidationStatus.FAILED
        assert result.score == 0.0
        assert result.duration_ms == 3000


class TestTrivyScanExecution:
    """Testes de execução de scans."""

    @pytest.mark.asyncio
    async def test_scan_container_image_success(self, trivy_client_with_trivy):
        """Testa scan de imagem com sucesso."""
        trivy_output = {
            'Results': [{
                'Target': 'nginx:latest',
                'Vulnerabilities': [
                    {'Severity': 'HIGH', 'VulnerabilityID': 'CVE-2023-1234'}
                ]
            }]
        }

        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = json.dumps(trivy_output)
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            result = await trivy_client_with_trivy.scan_container_image('nginx:latest')

            assert result.status == ValidationStatus.WARNING
            assert result.high_issues == 1
            assert result.issues_count == 1

    @pytest.mark.asyncio
    async def test_scan_container_image_no_vulnerabilities(self, trivy_client_with_trivy):
        """Testa scan de imagem sem vulnerabilidades."""
        trivy_output = {'Results': []}

        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = json.dumps(trivy_output)
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            result = await trivy_client_with_trivy.scan_container_image('alpine:latest')

            assert result.status == ValidationStatus.PASSED
            assert result.score == 1.0
            assert result.issues_count == 0

    @pytest.mark.asyncio
    async def test_scan_container_image_trivy_error(self, trivy_client_with_trivy):
        """Testa scan quando Trivy retorna erro."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = ''
            mock_result.stderr = 'Error: unable to pull image'
            mock_result.returncode = 1
            mock_run.return_value = mock_result

            result = await trivy_client_with_trivy.scan_container_image('invalid:tag')

            assert result.status == ValidationStatus.FAILED
            assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_scan_container_image_timeout(self, trivy_client_with_trivy):
        """Testa scan com timeout."""
        import subprocess

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired('trivy', 300)

            result = await trivy_client_with_trivy.scan_container_image('huge:image')

            assert result.status == ValidationStatus.FAILED
            assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_scan_filesystem_success(self, trivy_client_with_trivy):
        """Testa scan de filesystem com sucesso."""
        trivy_output = {
            'Results': [{
                'Target': '/tmp/app',
                'Vulnerabilities': [
                    {'Severity': 'MEDIUM', 'VulnerabilityID': 'CVE-2023-0001'}
                ]
            }]
        }

        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = json.dumps(trivy_output)
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            result = await trivy_client_with_trivy.scan_filesystem('/tmp/app')

            assert result.status == ValidationStatus.WARNING
            assert result.medium_issues == 1

    @pytest.mark.asyncio
    async def test_scan_iac_success(self, trivy_client_with_trivy):
        """Testa scan de IaC com sucesso."""
        trivy_output = {
            'Results': [{
                'Target': 'main.tf',
                'Misconfigurations': [
                    {'Severity': 'LOW', 'Title': 'Missing encryption'}
                ]
            }]
        }

        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = json.dumps(trivy_output)
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            result = await trivy_client_with_trivy.scan_iac('/tmp/terraform')

            assert result.status == ValidationStatus.PASSED
            assert result.low_issues == 1


class TestTrivyCLICommand:
    """Testes de comando CLI do Trivy."""

    def test_run_trivy_cli_command_image(self, trivy_client_with_trivy):
        """Testa construção do comando para scan de imagem."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = '{"Results": []}'
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            trivy_client_with_trivy._run_trivy_cli('image', 'nginx:latest')

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == '/usr/bin/trivy'
            assert cmd[1] == 'image'
            assert '--format' in cmd
            assert '--severity' in cmd
            assert 'nginx:latest' in cmd

    def test_run_trivy_cli_custom_severity(self):
        """Testa comando com severidade customizada."""
        with patch('shutil.which', return_value='/usr/bin/trivy'):
            client = TrivyClient(severity='CRITICAL,HIGH,MEDIUM')
            client.trivy_path = '/usr/bin/trivy'
            client._trivy_available = True

        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = '{"Results": []}'
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            client._run_trivy_cli('fs', '/tmp/app')

            cmd = mock_run.call_args[0][0]
            severity_idx = cmd.index('--severity')
            assert cmd[severity_idx + 1] == 'CRITICAL,HIGH,MEDIUM'

    def test_run_trivy_cli_timeout(self):
        """Testa que timeout é respeitado."""
        with patch('shutil.which', return_value='/usr/bin/trivy'):
            client = TrivyClient(timeout=120)
            client.trivy_path = '/usr/bin/trivy'
            client._trivy_available = True

        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = '{"Results": []}'
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            client._run_trivy_cli('image', 'nginx:latest')

            mock_run.assert_called_once()
            assert mock_run.call_args[1]['timeout'] == 120


class TestTrivyCache:
    """Testes de cache de resultados."""

    def test_cache_key_generation(self, trivy_client):
        """Testa geração de chave de cache."""
        key1 = trivy_client._get_cache_key('image', 'nginx:latest')
        key2 = trivy_client._get_cache_key('image', 'nginx:latest')
        key3 = trivy_client._get_cache_key('fs', '/tmp/app')

        assert key1 == key2
        assert key1 != key3
        assert key1 == 'image:nginx:latest'

    def test_cache_save_and_retrieve(self, trivy_client):
        """Testa salvar e recuperar do cache."""
        from datetime import timedelta

        result = MagicMock()
        cache_key = 'test:key'

        trivy_client._save_to_cache(cache_key, result)

        assert cache_key in trivy_client._cache
        cached_result, timestamp = trivy_client._cache[cache_key]
        assert cached_result == result

    def test_cache_expiration(self, trivy_client):
        """Testa expiração de cache."""
        from datetime import datetime, timedelta

        # Cache com timestamp antigo
        old_timestamp = datetime.now() - timedelta(seconds=3700)
        result = MagicMock()
        trivy_client._cache['old_key'] = (result, old_timestamp)

        # Deve retornar None para cache expirado
        cached = trivy_client._get_from_cache('old_key')
        assert cached is None
        assert 'old_key' not in trivy_client._cache

    def test_cache_clear(self, trivy_client):
        """Testa limpar cache."""
        result = MagicMock()
        trivy_client._save_to_cache('key1', result)
        trivy_client._save_to_cache('key2', result)

        assert len(trivy_client._cache) == 2

        trivy_client._clear_cache()

        assert len(trivy_client._cache) == 0

    def test_get_cache_stats(self, trivy_client):
        """Testa obter estatísticas do cache."""
        result = MagicMock()
        trivy_client._save_to_cache('key1', result)

        stats = trivy_client.get_cache_stats()

        assert stats['cache_size'] == 1
        assert stats['cache_ttl_seconds'] == 3600
        assert 'key1' in stats['cached_keys']


class TestTrivyHealthCheck:
    """Testes de verificação de saúde."""

    def test_is_available_with_trivy(self):
        """Testa is_available quando Trivy está instalado."""
        with patch('shutil.which', return_value='/usr/bin/trivy'):
            client = TrivyClient(enabled=True)
            client.trivy_path = '/usr/bin/trivy'
            client._trivy_available = True

        assert client.is_available() is True

    def test_is_available_without_trivy(self):
        """Testa is_available quando Trivy não está instalado."""
        with patch('shutil.which', return_value=None):
            client = TrivyClient(enabled=True)

        assert client.is_available() is False

    @pytest.mark.asyncio
    async def test_health_check_enabled_with_trivy(self):
        """Testa health_check quando habilitado com Trivy."""
        with patch('shutil.which', return_value='/usr/bin/trivy'):
            client = TrivyClient(enabled=True)
            client.trivy_path = '/usr/bin/trivy'
            client._trivy_available = True

        result = await client.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_enabled_without_trivy(self):
        """Testa health_check quando habilitado sem Trivy."""
        with patch('shutil.which', return_value=None):
            client = TrivyClient(enabled=True)

        result = await client.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_disabled(self):
        """Testa health_check quando desabilitado."""
        client = TrivyClient(enabled=False)

        result = await client.health_check()
        assert result is True


class TestTrivyThreshold:
    """Testes de threshold configurável."""

    def test_status_with_threshold_zero(self, trivy_client):
        """Testa status com threshold zero (padrão)."""
        counts = {'critical': 0, 'high': 5, 'medium': 0, 'low': 0}
        status, score = trivy_client._determine_status_and_score(counts)

        assert status == ValidationStatus.WARNING  # HIGH sempre WARNING com threshold 0

    def test_status_with_threshold_exceeded(self):
        """Testa status quando threshold é excedido."""
        with patch('shutil.which', return_value='/usr/bin/trivy'):
            client = TrivyClient(fail_on_threshold=3)
            client.trivy_path = '/usr/bin/trivy'
            client._trivy_available = True

        counts = {'critical': 0, 'high': 0, 'medium': 3, 'low': 0}
        status, score = client._determine_status_and_score(counts)

        assert status == ValidationStatus.FAILED  # 3 >= threshold

    def test_status_with_threshold_not_exceeded(self):
        """Testa status quando threshold não é excedido."""
        with patch('shutil.which', return_value='/usr/bin/trivy'):
            client = TrivyClient(fail_on_threshold=10)
            client.trivy_path = '/usr/bin/trivy'
            client._trivy_available = True

        counts = {'critical': 0, 'high': 0, 'medium': 5, 'low': 0}
        status, score = client._determine_status_and_score(counts)

        assert status == ValidationStatus.WARNING  # 5 < threshold, MEDIUM = WARNING

    def test_critical_always_fails(self):
        """Testa que vulnerabilidades críticas sempre falham."""
        with patch('shutil.which', return_value='/usr/bin/trivy'):
            client = TrivyClient(fail_on_threshold=100)
            client.trivy_path = '/usr/bin/trivy'
            client._trivy_available = True

        counts = {'critical': 1, 'high': 0, 'medium': 0, 'low': 0}
        status, score = client._determine_status_and_score(counts)

        assert status == ValidationStatus.FAILED  # CRITICAL sempre falha
