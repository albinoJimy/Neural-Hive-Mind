"""Testes de integração para SonarQubeClient"""
import os
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.sonarqube_client import SonarQubeClient
from src.models.artifact import ValidationStatus


@pytest.fixture
def client():
    return SonarQubeClient(
        url='http://sonarqube:9000',
        token='test-token',
        enabled=True,
        scanner_timeout=900,
        poll_interval=1,
        poll_timeout=10
    )


@pytest.fixture
def disabled_client():
    return SonarQubeClient(
        url='http://sonarqube:9000',
        token='test-token',
        enabled=False
    )


@pytest.mark.asyncio
async def test_sonarqube_analysis_disabled(disabled_client):
    """Testa que análise retorna SKIPPED quando disabled"""
    result = await disabled_client.analyze_code('project-key', '/tmp/src')

    assert result.status == ValidationStatus.SKIPPED
    assert result.tool_name == 'SonarQube'
    assert result.duration_ms == 0


@pytest.mark.asyncio
async def test_sonarqube_analysis_scanner_failed(client):
    """Testa quando scanner falha"""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = 'ERROR: Scanner failed'
    mock_result.stderr = ''

    with patch('subprocess.run', return_value=mock_result):
        result = await client.analyze_code('project-key', '/tmp/src')

    assert result.status == ValidationStatus.FAILED
    assert result.report_uri == 'http://sonarqube:9000/dashboard?id=project-key'


@pytest.mark.asyncio
async def test_sonarqube_analysis_success_quality_gate_ok(client):
    """Testa análise completa com quality gate OK"""
    mock_scanner_result = MagicMock()
    mock_scanner_result.returncode = 0
    mock_scanner_result.stdout = 'INFO: EXECUTION SUCCESS\nINFO: ceTaskId=task-123'
    mock_scanner_result.stderr = ''

    mock_http_client = AsyncMock()

    task_response = MagicMock()
    task_response.raise_for_status = MagicMock()
    task_response.json.return_value = {'task': {'status': 'SUCCESS'}}

    issues_response = MagicMock()
    issues_response.raise_for_status = MagicMock()
    issues_response.json.return_value = {
        'issues': [
            {'severity': 'MAJOR'},
            {'severity': 'MINOR'},
            {'severity': 'INFO'}
        ]
    }

    qg_response = MagicMock()
    qg_response.raise_for_status = MagicMock()
    qg_response.json.return_value = {'projectStatus': {'status': 'OK'}}

    mock_http_client.get = AsyncMock(side_effect=[task_response, issues_response, qg_response])

    with patch('subprocess.run', return_value=mock_scanner_result):
        with patch.object(client, '_ensure_http_client', return_value=mock_http_client):
            result = await client.analyze_code('project-key', '/tmp/src')

    assert result.status == ValidationStatus.PASSED
    assert result.score == 0.9
    assert result.high_issues == 1
    assert result.medium_issues == 1
    assert result.low_issues == 1


@pytest.mark.asyncio
async def test_sonarqube_analysis_quality_gate_error(client):
    """Testa análise com quality gate ERROR"""
    mock_scanner_result = MagicMock()
    mock_scanner_result.returncode = 0
    mock_scanner_result.stdout = 'INFO: EXECUTION SUCCESS\nINFO: ceTaskId=task-123'
    mock_scanner_result.stderr = ''

    mock_http_client = AsyncMock()

    task_response = MagicMock()
    task_response.raise_for_status = MagicMock()
    task_response.json.return_value = {'task': {'status': 'SUCCESS'}}

    issues_response = MagicMock()
    issues_response.raise_for_status = MagicMock()
    issues_response.json.return_value = {
        'issues': [
            {'severity': 'BLOCKER'},
            {'severity': 'CRITICAL'}
        ]
    }

    qg_response = MagicMock()
    qg_response.raise_for_status = MagicMock()
    qg_response.json.return_value = {'projectStatus': {'status': 'ERROR'}}

    mock_http_client.get = AsyncMock(side_effect=[task_response, issues_response, qg_response])

    with patch('subprocess.run', return_value=mock_scanner_result):
        with patch.object(client, '_ensure_http_client', return_value=mock_http_client):
            result = await client.analyze_code('project-key', '/tmp/src')

    assert result.status == ValidationStatus.FAILED
    assert result.score == 0.4
    assert result.critical_issues == 2


@pytest.mark.asyncio
async def test_sonarqube_analysis_quality_gate_warn(client):
    """Testa análise com quality gate WARN"""
    mock_scanner_result = MagicMock()
    mock_scanner_result.returncode = 0
    mock_scanner_result.stdout = 'INFO: EXECUTION SUCCESS\nINFO: ceTaskId=task-123'
    mock_scanner_result.stderr = ''

    mock_http_client = AsyncMock()

    task_response = MagicMock()
    task_response.raise_for_status = MagicMock()
    task_response.json.return_value = {'task': {'status': 'SUCCESS'}}

    issues_response = MagicMock()
    issues_response.raise_for_status = MagicMock()
    issues_response.json.return_value = {'issues': []}

    qg_response = MagicMock()
    qg_response.raise_for_status = MagicMock()
    qg_response.json.return_value = {'projectStatus': {'status': 'WARN'}}

    mock_http_client.get = AsyncMock(side_effect=[task_response, issues_response, qg_response])

    with patch('subprocess.run', return_value=mock_scanner_result):
        with patch.object(client, '_ensure_http_client', return_value=mock_http_client):
            result = await client.analyze_code('project-key', '/tmp/src')

    assert result.status == ValidationStatus.WARNING
    assert result.score == 0.7


@pytest.mark.asyncio
async def test_sonarqube_scanner_timeout(client):
    """Testa timeout do scanner"""
    with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('sonar-scanner', 900)):
        result = await client.analyze_code('project-key', '/tmp/src')

    assert result.status == ValidationStatus.FAILED
    assert result.score == 0.0


@pytest.mark.asyncio
async def test_sonarqube_get_quality_gate_status(client):
    """Testa get_quality_gate_status"""
    mock_http_client = AsyncMock()

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {'projectStatus': {'status': 'OK'}}

    mock_http_client.get = AsyncMock(return_value=response)

    with patch.object(client, '_ensure_http_client', return_value=mock_http_client):
        status = await client.get_quality_gate_status('project-key')

    assert status is True


@pytest.mark.asyncio
async def test_sonarqube_get_issues(client):
    """Testa get_issues"""
    mock_http_client = AsyncMock()

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        'issues': [
            {'key': 'issue-1', 'severity': 'MAJOR'},
            {'key': 'issue-2', 'severity': 'MINOR'}
        ]
    }

    mock_http_client.get = AsyncMock(return_value=response)

    with patch.object(client, '_ensure_http_client', return_value=mock_http_client):
        issues = await client.get_issues('project-key')

    assert len(issues) == 2
    assert issues[0]['key'] == 'issue-1'


@pytest.mark.asyncio
async def test_sonarqube_get_metrics(client):
    """Testa get_metrics"""
    mock_http_client = AsyncMock()

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        'component': {
            'measures': [
                {'metric': 'bugs', 'value': '5'},
                {'metric': 'coverage', 'value': '85.0'}
            ]
        }
    }

    mock_http_client.get = AsyncMock(return_value=response)

    with patch.object(client, '_ensure_http_client', return_value=mock_http_client):
        metrics = await client.get_metrics('project-key')

    assert metrics['bugs'] == '5'
    assert metrics['coverage'] == '85.0'


@pytest.mark.asyncio
async def test_sonarqube_task_analysis_failed(client):
    """Testa quando task do SonarQube falha"""
    mock_scanner_result = MagicMock()
    mock_scanner_result.returncode = 0
    mock_scanner_result.stdout = 'INFO: EXECUTION SUCCESS\nINFO: ceTaskId=task-123'
    mock_scanner_result.stderr = ''

    mock_http_client = AsyncMock()

    task_response = MagicMock()
    task_response.raise_for_status = MagicMock()
    task_response.json.return_value = {'task': {'status': 'FAILED'}}

    mock_http_client.get = AsyncMock(return_value=task_response)

    with patch('subprocess.run', return_value=mock_scanner_result):
        with patch.object(client, '_ensure_http_client', return_value=mock_http_client):
            result = await client.analyze_code('project-key', '/tmp/src')

    assert result.status == ValidationStatus.FAILED


@pytest.mark.asyncio
async def test_sonarqube_severity_mapping(client):
    """Testa mapeamento correto de severidades"""
    counts = {
        'blocker': 2,
        'critical': 3,
        'major': 5,
        'minor': 8,
        'info': 10
    }

    mapped = client._map_severity_counts(counts)

    assert mapped['critical'] == 5
    assert mapped['high'] == 5
    assert mapped['medium'] == 8
    assert mapped['low'] == 10
