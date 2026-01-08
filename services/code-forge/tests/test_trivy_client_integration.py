"""Testes de integração para TrivyClient"""
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.trivy_client import TrivyClient
from src.models.artifact import ValidationStatus


@pytest.fixture
def client():
    return TrivyClient(enabled=True, severity='CRITICAL,HIGH', timeout=600)


@pytest.fixture
def disabled_client():
    return TrivyClient(enabled=False)


@pytest.mark.asyncio
async def test_trivy_scan_disabled(disabled_client):
    """Testa que scan retorna SKIPPED quando disabled"""
    result = await disabled_client.scan_filesystem('/tmp/project')

    assert result.status == ValidationStatus.SKIPPED
    assert result.tool_name == 'Trivy'
    assert result.duration_ms == 0


@pytest.mark.asyncio
async def test_trivy_filesystem_scan_success_no_vulnerabilities(client):
    """Testa scan filesystem sem vulnerabilidades"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"Results": []}'
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_filesystem('/tmp/project')

    assert result.status == ValidationStatus.PASSED
    assert result.tool_name == 'Trivy'
    assert result.score == 1.0
    assert result.issues_count == 0


@pytest.mark.asyncio
async def test_trivy_filesystem_scan_with_vulnerabilities(client):
    """Testa scan filesystem com vulnerabilidades"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '''
    {
        "Results": [
            {
                "Target": "requirements.txt",
                "Vulnerabilities": [
                    {"VulnerabilityID": "CVE-2021-001", "Severity": "HIGH"},
                    {"VulnerabilityID": "CVE-2021-002", "Severity": "MEDIUM"},
                    {"VulnerabilityID": "CVE-2021-003", "Severity": "LOW"}
                ]
            }
        ]
    }
    '''
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_filesystem('/tmp/project')

    assert result.status == ValidationStatus.WARNING
    assert result.score == 0.6
    assert result.issues_count == 3
    assert result.high_issues == 1
    assert result.medium_issues == 1
    assert result.low_issues == 1


@pytest.mark.asyncio
async def test_trivy_container_scan_critical(client):
    """Testa scan de container com vulnerabilidade crítica"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '''
    {
        "Results": [
            {
                "Target": "alpine:3.14",
                "Vulnerabilities": [
                    {"VulnerabilityID": "CVE-2021-CRITICAL", "Severity": "CRITICAL"}
                ]
            }
        ]
    }
    '''
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_container_image('alpine:3.14')

    assert result.status == ValidationStatus.FAILED
    assert result.score == 0.3
    assert result.critical_issues == 1


@pytest.mark.asyncio
async def test_trivy_iac_scan_with_misconfigurations(client):
    """Testa scan IaC com misconfigurations"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '''
    {
        "Results": [
            {
                "Target": "main.tf",
                "Misconfigurations": [
                    {"ID": "AVD-AWS-001", "Severity": "HIGH"},
                    {"ID": "AVD-AWS-002", "Severity": "MEDIUM"}
                ]
            }
        ]
    }
    '''
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_iac('/tmp/terraform')

    assert result.status == ValidationStatus.WARNING
    assert result.high_issues == 1
    assert result.medium_issues == 1


@pytest.mark.asyncio
async def test_trivy_scan_timeout(client):
    """Testa timeout do Trivy"""
    with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('trivy', 600)):
        result = await client.scan_filesystem('/tmp/project')

    assert result.status == ValidationStatus.FAILED
    assert result.score == 0.0


@pytest.mark.asyncio
async def test_trivy_scan_cli_error(client):
    """Testa erro de CLI do Trivy"""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ''
    mock_result.stderr = 'Failed to scan'

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_filesystem('/tmp/project')

    assert result.status == ValidationStatus.FAILED


@pytest.mark.asyncio
async def test_trivy_scan_invalid_json(client):
    """Testa parsing de JSON inválido"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = 'not valid json'
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_filesystem('/tmp/project')

    assert result.status == ValidationStatus.FAILED


@pytest.mark.asyncio
async def test_trivy_scan_null_vulnerabilities(client):
    """Testa handling de Vulnerabilities null"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '''
    {
        "Results": [
            {
                "Target": "alpine:3.14",
                "Vulnerabilities": null
            }
        ]
    }
    '''
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result):
        result = await client.scan_container_image('alpine:3.14')

    assert result.status == ValidationStatus.PASSED
    assert result.issues_count == 0


@pytest.mark.asyncio
async def test_trivy_uses_correct_scan_type_for_image(client):
    """Testa que scan de imagem usa 'image' como tipo"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"Results": []}'
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result) as mock_run:
        await client.scan_container_image('nginx:latest')

    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert 'image' in cmd


@pytest.mark.asyncio
async def test_trivy_uses_correct_scan_type_for_fs(client):
    """Testa que scan filesystem usa 'fs' como tipo"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"Results": []}'
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result) as mock_run:
        await client.scan_filesystem('/tmp/project')

    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert 'fs' in cmd


@pytest.mark.asyncio
async def test_trivy_uses_correct_scan_type_for_config(client):
    """Testa que scan IaC usa 'config' como tipo"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"Results": []}'
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result) as mock_run:
        await client.scan_iac('/tmp/terraform')

    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert 'config' in cmd
