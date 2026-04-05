"""Healer MCP Server - Tests configuration."""
import sys
from pathlib import Path

import pytest

# Add src to path
sys.session: pytest.Session
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def mcp():
    """Fixture para servidor MCP."""
    # Será criado após implementação
    return None


@pytest.fixture
def mock_incident():
    """Fixture de incidente para testes."""
    return {
        "incident_id": "incident-123",
        "service": "gateway-intencoes",
        "severity": "HIGH",
        "incident_type": "pod_crash_loop",
        "description": "Pod em crash loop_back_off",
        "affected_resources": ["gateway-intencoes-7d9f4c8b-xk2lp"],
        "detected_at": "2026-04-03T12:34:56Z",
        "metrics": {
            "error_rate": 0.85,
            "latency_p99_ms": 5000,
            "request_count": 100,
        },
    }


@pytest.fixture
def mock_playbook():
    """Fixture de playbook para testes."""
    return {
        "playbook_id": "playbook-restart-pod",
        "name": "Restart Pod",
        "description": "Reinicia pod em crash loop",
        "steps": [
            {"order": 1, "action": "delete_pod", "resource": "$.affected_resources[0]"},
            {"order": 2, "action": "wait_ready", "timeout_seconds": 60},
            {"order": 3, "action": "verify_health", "endpoint": "/health"},
        ],
        "estimated_duration_seconds": 90,
        "rollback_actions": [
            {"action": "rollback_deployment", "version": "previous"}
        ],
    }


@pytest.fixture
def mock_health_check():
    """Fixture de health check para testes."""
    return {
        "service": "gateway-intencoes",
        "endpoint": "http://gateway-intencoes:8000/health",
        "expected_status_code": 200,
        "timeout_seconds": 5,
        "checks": ["liveness", "readiness", "startup"],
    }


@pytest.fixture
def mock_recovery_validation():
    """Fixture de validação de recuperação para testes."""
    return {
        "incident_id": "incident-123",
        "playbook_id": "playbook-restart-pod",
        "validation_checks": [
            {"check": "pod_running", "expected": True, "actual": True},
            {"check": "error_rate", "expected": "< 0.05", "actual": 0.02},
            {"check": "latency_p99_ms", "expected": "< 1000", "actual": 350},
        ],
        "recovery_status": "SUCCESS",
    }


@pytest.fixture
def mock_escalation_data():
    """Fixture de dados de escalamento para testes."""
    return {
        "incident_id": "incident-456",
        "reason": "Playbook executado mas serviço não recuperou",
        "attempts": 3,
        "last_attempt_at": "2026-04-03T14:30:00Z",
        "target_team": "platform_team",
        "urgency": "critical",
        "context": {
            "service": "orchestrator-dynamic",
            "error_logs": ["Connection timeout", "Database unreachable"],
        },
    }
