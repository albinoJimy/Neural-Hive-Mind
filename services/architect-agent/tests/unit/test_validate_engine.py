"""Testes unitários para ValidateEngine."""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.validators.validate_engine import ValidateEngine
from src.models.validation import Severity, ViolationType


@pytest.fixture
def mock_scout_responses():
    """Respostas mock do Scout Agents."""
    return {
        "patterns": [
            {
                "type": "class",
                "name": "BigClass",
                "file": "big_class.py",
                "methods": list(range(20)),  # 20 methods - SRP violation
                "if_statements": 12,
                "switch_statements": 0,
            }
        ],
        "insights": {
            "commit_sha": "abc123",
            "complexity": 75,
            "test_coverage": 65,
            "inheritance": [
                {
                    "file": "child.py",
                    "method": "process",
                    "overrides_method_without_calling_super": True,
                }
            ],
            "interfaces": [{"name": "HugeInterface", "file": "huge.py", "method_count": 15}],
            "dependencies": [
                {
                    "name": "ConcreteClass",
                    "file": "dep.py",
                    "is_concrete": True,
                    "is_interface": False,
                }
            ],
        },
        "duplication": {"percentage": 15.5, "duplicated_lines": 450},
    }


@pytest.fixture
def mock_opa_responses():
    """Respostas mock do OPA."""
    return [
        {
            "type": "architecture",
            "severity": "medium",
            "location": "app.py",
            "description": "Diretório src/ não segue estrutura padrão",
        }
    ]


@pytest.fixture
def engine(mock_scout_responses, mock_opa_responses):
    """Engine com clientes mockados."""
    engine_instance = ValidateEngine()
    # Mock dos métodos do cliente Scout
    engine_instance.scout_client.get_patterns = AsyncMock(
        return_value=mock_scout_responses["patterns"]
    )
    engine_instance.scout_client.get_insights = AsyncMock(
        return_value=mock_scout_responses["insights"]
    )
    engine_instance.scout_client.check_duplication = AsyncMock(
        return_value=mock_scout_responses["duplication"]
    )
    # Mock do cliente OPA
    engine_instance.opa_client.check_architecture_rules = AsyncMock(return_value=mock_opa_responses)
    return engine_instance


@pytest.mark.asyncio
async def test_validate_returns_report(engine):
    target = {"repo_url": "github.com/org/repo", "branch": "main"}
    report = await engine.validate(target)

    assert report.report_id.startswith("val-")
    assert report.repo_url == "github.com/org/repo"
    assert report.branch == "main"
    assert report.commit_sha == "abc123"
    assert 0 <= report.health_score <= 100


@pytest.mark.asyncio
async def test_validate_detects_srp_violation(engine):
    target = {"repo_url": "github.com/org/repo"}
    report = await engine.validate(target)

    srp_violations = [v for v in report.violations if v.type == ViolationType.SRP]
    assert len(srp_violations) > 0
    assert "BigClass" in srp_violations[0].description


@pytest.mark.asyncio
async def test_validate_detects_duplication(engine):
    target = {"repo_url": "github.com/org/repo"}
    report = await engine.validate(target)

    dup_violations = [v for v in report.violations if v.type == ViolationType.DUPLICATION]
    assert len(dup_violations) > 0
    assert "15.5%" in dup_violations[0].description


@pytest.mark.asyncio
async def test_validate_generates_suggestions(engine):
    target = {"repo_url": "github.com/org/repo"}
    report = await engine.validate(target)

    assert len(report.suggestions) > 0
    # Sugestão para baixa cobertura de testes
    test_suggestions = [s for s in report.suggestions if "cobertura" in s.description.lower()]
    assert len(test_suggestions) > 0


@pytest.mark.asyncio
async def test_validate_handles_scout_errors(engine):
    with patch("src.validators.validate_engine.ScoutAgentsClient") as mock:
        client = Mock()
        client.get_patterns = AsyncMock(side_effect=Exception("Scout unavailable"))
        client.get_insights = AsyncMock(side_effect=Exception("Scout unavailable"))
        client.check_duplication = AsyncMock(side_effect=Exception("Scout unavailable"))
        mock.return_value = client

    target = {"repo_url": "github.com/org/repo"}
    report = await engine.validate(target)

    # Deve retornar relatório mesmo com erros
    assert report.report_id.startswith("val-")
    assert report.health_score >= 0


@pytest.mark.asyncio
async def test_health_score_calculation(engine):
    target = {"repo_url": "github.com/org/repo"}
    report = await engine.validate(target)

    # Score deve ser penalizado por violações e duplicação
    assert report.health_score < 100


@pytest.mark.asyncio
async def test_validate_without_branch_uses_default(engine):
    target = {"repo_url": "github.com/org/repo"}
    await engine.validate(target)

    # Deve chamar com branch padrão "main"
    engine.scout_client.get_patterns.assert_called_with("github.com/org/repo", "main")
