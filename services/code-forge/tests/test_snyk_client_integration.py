"""Testes de integração para SnykClient"""
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.snyk_client import SnykClient
from src.models.artifact import ValidationStatus


@pytest.fixture
def client():
    return SnykClient(token='test-token', enabled=True, timeout=300)


@pytest.fixture
def disabled_client():
    return SnykClient(token='test-token', enabled=False)


@pytest.mark.asyncio
async def test_snyk_scan_disabled(disabled_client):
    """Testa que scan retorna SKIPPED quando disabled"""
    result = await disabled_client.scan_dependencies('/tmp/project', 'python')

    assert result.status == ValidationStatus.SKIPPED
    assert result.tool_name == 'Snyk'
    assert result.duration_ms == 0


@pytest.mark.asyncio
async def test_snyk_scan_success_no_vulnerabilities(client):
    """Testa scan Snyk com resultado sem vulnerabilidades"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"vulnerabilities": [], "ok": true}'
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_dependencies('/tmp/project', 'python')

    assert result.status == ValidationStatus.PASSED
    assert result.tool_name == 'Snyk'
    assert result.score == 1.0
    assert result.issues_count == 0
    assert result.critical_issues == 0
    assert result.high_issues == 0


@pytest.mark.asyncio
async def test_snyk_scan_success_with_vulnerabilities(client):
    """Testa scan Snyk com vulnerabilidades encontradas"""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = '''
    {
        "vulnerabilities": [
            {"severity": "high", "id": "SNYK-001"},
            {"severity": "medium", "id": "SNYK-002"},
            {"severity": "low", "id": "SNYK-003"},
            {"severity": "low", "id": "SNYK-004"}
        ],
        "ok": false
    }
    '''
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_dependencies('/tmp/project', 'python')

    assert result.status == ValidationStatus.WARNING
    assert result.tool_name == 'Snyk'
    assert result.score == 0.6
    assert result.issues_count == 4
    assert result.high_issues == 1
    assert result.medium_issues == 1
    assert result.low_issues == 2


@pytest.mark.asyncio
async def test_snyk_scan_critical_vulnerability(client):
    """Testa scan Snyk com vulnerabilidade crítica"""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = '''
    {
        "vulnerabilities": [
            {"severity": "critical", "id": "SNYK-CRITICAL"}
        ],
        "ok": false
    }
    '''
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_dependencies('/tmp/project', 'python')

    assert result.status == ValidationStatus.FAILED
    assert result.score == 0.3
    assert result.critical_issues == 1


@pytest.mark.asyncio
async def test_snyk_scan_timeout(client):
    """Testa timeout do Snyk"""
    with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('snyk', 300)):
        result = await client.scan_dependencies('/tmp/project', 'python')

    assert result.status == ValidationStatus.FAILED
    assert result.score == 0.0


@pytest.mark.asyncio
async def test_snyk_scan_cli_error(client):
    """Testa erro de CLI do Snyk"""
    mock_result = MagicMock()
    mock_result.returncode = 2
    mock_result.stdout = ''
    mock_result.stderr = 'Authentication failed'

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_dependencies('/tmp/project', 'python')

    assert result.status == ValidationStatus.FAILED


@pytest.mark.asyncio
async def test_snyk_scan_invalid_json(client):
    """Testa parsing de JSON inválido"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = 'not valid json {'
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_dependencies('/tmp/project', 'python')

    assert result.status == ValidationStatus.FAILED


@pytest.mark.asyncio
async def test_snyk_scan_python_language(client):
    """Testa que Python usa requirements.txt"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"vulnerabilities": []}'
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result) as mock_run:
        await client.scan_dependencies('/tmp/project', 'python')

    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert '--file=requirements.txt' in cmd


@pytest.mark.asyncio
async def test_snyk_scan_javascript_language(client):
    """Testa que JavaScript usa package.json"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"vulnerabilities": []}'
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result) as mock_run:
        await client.scan_dependencies('/tmp/project', 'javascript')

    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert '--file=package.json' in cmd


@pytest.mark.asyncio
async def test_snyk_scan_go_language(client):
    """Testa que Go usa go.mod"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"vulnerabilities": []}'
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result) as mock_run:
        await client.scan_dependencies('/tmp/project', 'go')

    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert '--file=go.mod' in cmd
