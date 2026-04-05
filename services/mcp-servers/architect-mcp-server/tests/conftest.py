"""Architect MCP Server - Tests configuration."""
import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def mcp():
    """Fixture para servidor MCP."""
    # Será criado após implementação
    return None


@pytest.fixture
def mock_feature_request():
    """Fixture de requisição de feature para planejamento."""
    return {
        "feature_id": "feat-001",
        "feature_name": "User Authentication",
        "feature_description": "Implement OAuth2 authentication with JWT tokens",
        "requirements": [
            "Support Google and GitHub OAuth providers",
            "JWT token expiration of 24 hours",
            "Refresh token rotation",
            "Session management",
        ],
        "constraints": {
            "max_development_time_days": 14,
            "team_size": 3,
            "max_complexity": "medium",
        },
        "priority": "high",
        "ticket_id": "ARCH-001",
    }


@pytest.fixture
def mock_design_document():
    """Fixture de documento de design."""
    return {
        "design_id": "design-001",
        "ticket_id": "ARCH-001",
        "design_name": "Microservices Authentication Architecture",
        "components": [
            {
                "name": "auth-service",
                "type": "service",
                "responsibility": "Handle authentication logic",
                "dependencies": ["user-service", "token-service"],
            },
            {
                "name": "token-service",
                "type": "service",
                "responsibility": "Generate and validate JWT tokens",
                "dependencies": [],
            },
        ],
        "dataflows": [
            {
                "from": "api-gateway",
                "to": "auth-service",
                "protocol": "REST",
                "authentication": "required",
            }
        ],
        "patterns": ["Gateway Pattern", "Token Pattern"],
    }


@pytest.fixture
def mock_architecture_state():
    """Fixture do estado atual da arquitetura."""
    return {
        "architecture_id": "arch-state-v1",
        "version": "1.2.0",
        "last_updated": "2026-04-03T10:00:00Z",
        "services": [
            {
                "name": "api-gateway",
                "version": "2.0.0",
                "status": "healthy",
                "dependencies": [],
            },
            {
                "name": "user-service",
                "version": "1.5.0",
                "status": "healthy",
                "dependencies": ["mongodb"],
            },
        ],
        "patterns": ["API Gateway", "Repository Pattern"],
        "evolution_history": [
            {
                "version": "1.0.0",
                "date": "2026-01-01T00:00:00Z",
                "changes": ["Initial architecture"],
            }
        ],
    }


@pytest.fixture
def mock_pattern_analysis_result():
    """Fixture de resultado de análise de padrões."""
    return {
        "analysis_id": "pattern-analysis-001",
        "patterns_detected": [
            {
                "name": "Repository Pattern",
                "occurrences": 15,
                "locations": ["user-service", "order-service"],
                "health": "good",
            },
            {
                "name": "Circuit Breaker",
                "occurrences": 5,
                "locations": ["payment-service", "notification-service"],
                "health": "excellent",
            },
        ],
        "anti_patterns_detected": [
            {
                "name": "God Object",
                "occurrences": 2,
                "locations": ["legacy-service"],
                "severity": "high",
                "recommendation": "Refactor into smaller services",
            }
        ],
        "metrics": {
            "pattern_coverage": 0.75,
            "code_reusability": 0.82,
            "maintainability_index": 0.68,
        },
    }


@pytest.fixture
def mock_documentation_config():
    """Fixture de configuração para geração de documentação."""
    return {
        "doc_id": "doc-001",
        "ticket_id": "ARCH-001",
        "doc_type": "architecture_decision_record",
        "format": "markdown",
        "include_diagrams": True,
        "include_api_docs": True,
        "include_data_models": True,
        "output_path": "/docs/architecture/adr-001-authentication.md",
        "sections": [
            "context",
            "decision",
            "alternatives",
            "consequences",
            "references",
        ],
    }
