"""Guard MCP Server - Tests configuration."""

import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture()
def mcp():
    """Fixture para servidor MCP."""
    # Será criado após implementação
    return


@pytest.fixture()
def mock_ticket():
    """Fixture de ticket para testes."""
    return {
        "ticket_id": "ticket-123",
        "task_type": "DEPLOY",
        "environment": "production",
        "service_account": "default",
        "namespace": "production",
        "required_capabilities": ["READ", "WRITE"],
        "parameters": {"image": "nginx:latest"},
        "security_level": "CONFIDENTIAL",
    }


@pytest.fixture()
def mock_event():
    """Fixture de evento de segurança para testes."""
    return {
        "event_id": "event-456",
        "type": "authentication",
        "user_id": "user-123",
        "failed_attempts": 7,
        "source_ip": "192.168.1.100",
        "timestamp": 1712123456.789,
    }


@pytest.fixture()
def mock_vulnerability_report():
    """Fixture de relatório de vulnerabilidades."""
    return {
        "target": "nginx:latest",
        "vulnerabilities": [
            {
                "vulnerability_id": "CVE-2024-1234",
                "severity": "HIGH",
                "package": "openssl",
                "installed_version": "1.1.1",
                "fixed_version": "1.1.1k",
            },
            {
                "vulnerability_id": "CVE-2024-5678",
                "severity": "MEDIUM",
                "package": "pcre3",
                "installed_version": "2.8.6",
                "fixed_version": "2.8.7",
            },
        ],
    }
