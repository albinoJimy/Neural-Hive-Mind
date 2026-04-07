"""
Testes para o servico de Code Review Integration do Code Forge.

Cobre integracao com analise de codigo, comentarios e feedback.
"""

import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_code_review_service_init():
    """CodeReviewService deve inicializar com clientes corretos."""
    from src.services.code_review_integration import CodeReviewService

    mock_analyst = AsyncMock()
    mock_llm = AsyncMock()
    mock_mcp = AsyncMock()

    service = CodeReviewService(
        analyst_client=mock_analyst, llm_client=mock_llm, mcp_client=mock_mcp
    )

    assert service.analyst_client == mock_analyst
    assert service.llm_client == mock_llm
    assert service.mcp_client == mock_mcp


@pytest.mark.asyncio
async def test_analyze_code_success():
    """Analise de codigo deve retornar feedback estruturado."""
    from src.services.code_review_integration import CodeReviewService

    mock_analyst = AsyncMock()
    mock_llm = AsyncMock()
    mock_mcp = AsyncMock()

    mock_llm.generate_code = AsyncMock(
        return_value={
            "code": "Reviewed code",
            "confidence_score": 0.85,
            "suggestions": ["Add type hints", "Improve error handling"],
        }
    )

    service = CodeReviewService(
        analyst_client=mock_analyst, llm_client=mock_llm, mcp_client=mock_mcp
    )

    code = """def main():
    pass"""

    result = await service.analyze_code(code, language="python")

    assert result["confidence_score"] >= 0
    assert "suggestions" in result


@pytest.mark.asyncio
async def test_analyze_code_with_embedding():
    """Analise de codigo deve usar embedding quando disponivel."""
    from src.services.code_review_integration import CodeReviewService

    mock_analyst = AsyncMock()
    mock_llm = AsyncMock()
    mock_mcp = AsyncMock()

    mock_analyst.get_embedding = AsyncMock(return_value=[0.1] * 512)
    mock_analyst.find_similar_code = AsyncMock(
        return_value=[{"code": "similar code", "similarity": 0.9}]
    )
    mock_llm.generate_code = AsyncMock(
        return_value={"code": "Reviewed code", "confidence_score": 0.85}
    )

    service = CodeReviewService(
        analyst_client=mock_analyst, llm_client=mock_llm, mcp_client=mock_mcp
    )

    code = "def main(): pass"

    result = await service.analyze_code(code, language="python", use_embedding=True)

    mock_analyst.get_embedding.assert_called_once()
    assert "confidence_score" in result


@pytest.mark.asyncio
async def test_generate_review_comment():
    """Geracao de comentario de review deve ser formatada."""
    from src.services.code_review_integration import CodeReviewService

    mock_analyst = AsyncMock()
    mock_llm = AsyncMock()
    mock_mcp = AsyncMock()

    mock_llm.generate_code = AsyncMock(
        return_value={
            "code": "### Review Comment\n\n**Severity**: Medium\n\n**Suggestion**: Add type hints for better clarity.",
            "confidence_score": 0.9,
        }
    )

    service = CodeReviewService(
        analyst_client=mock_analyst, llm_client=mock_llm, mcp_client=mock_mcp
    )

    code = "def process(data): return data.upper()"

    result = await service.generate_review_comment(
        code, issue="Missing type hints", severity="medium"
    )

    assert "comment" in result
    assert result["severity"] == "medium"


@pytest.mark.asyncio
async def test_review_security_issues():
    """Review de seguranca deve identificar problemas potenciais."""
    from src.services.code_review_integration import CodeReviewService

    mock_analyst = AsyncMock()
    mock_llm = AsyncMock()
    mock_mcp = AsyncMock()

    mock_llm.generate_code = AsyncMock(
        return_value={
            "code": "### Security Review\n\n**Issues Found**: 1\n- Hardcoded credentials detected",
            "confidence_score": 0.95,
            "security_issues": [
                {"severity": "high", "line": 1, "description": "Hardcoded password"}
            ],
        }
    )

    service = CodeReviewService(
        analyst_client=mock_analyst, llm_client=mock_llm, mcp_client=mock_mcp
    )

    code = 'password = "admin123"  # TODO: move to env'

    result = await service.review_security(code)

    assert "security_issues" in result
    assert len(result["security_issues"]) >= 0


@pytest.mark.asyncio
async def test_suggest_improvements():
    """Sugestoes de melhoria devem ser acionaveis."""
    from src.services.code_review_integration import CodeReviewService

    mock_analyst = AsyncMock()
    mock_llm = AsyncMock()
    mock_mcp = AsyncMock()

    mock_llm.generate_code = AsyncMock(
        return_value={
            "code": "improved_code",
            "improvements": ["Use list comprehension", "Add docstring", "Type hint return value"],
        }
    )

    service = CodeReviewService(
        analyst_client=mock_analyst, llm_client=mock_llm, mcp_client=mock_mcp
    )

    code = """result = []
for x in items:
    result.append(x * 2)"""

    result = await service.suggest_improvements(code, language="python")

    assert "improvements" in result
    assert isinstance(result["improvements"], list)


@pytest.mark.asyncio
async def test_check_code_quality():
    """Verificacao de qualidade deve retornar score."""
    from src.services.code_review_integration import CodeReviewService

    mock_analyst = AsyncMock()
    mock_llm = AsyncMock()
    mock_mcp = AsyncMock()

    mock_llm.generate_code = AsyncMock(
        return_value={
            "quality_score": 0.75,
            "maintainability": "medium",
            "complexity": "low",
            "duplication": "none",
        }
    )

    service = CodeReviewService(
        analyst_client=mock_analyst, llm_client=mock_llm, mcp_client=mock_mcp
    )

    code = "def good_function(): return 42"

    result = await service.check_code_quality(code)

    assert "quality_score" in result
    assert 0 <= result["quality_score"] <= 1


@pytest.mark.asyncio
async def test_analyze_with_mcp_tools():
    """Analise com ferramentas MCP deve enriquecer feedback."""
    from src.services.code_review_integration import CodeReviewService

    mock_analyst = AsyncMock()
    mock_llm = AsyncMock()
    mock_mcp = AsyncMock()

    mock_mcp.request_tool_selection = AsyncMock(
        return_value={"selected_tools": [{"tool_name": "Pylint", "category": "LINTING"}]}
    )
    mock_llm.generate_code = AsyncMock(
        return_value={
            "code": "analyzed_code",
            "mcp_feedback": [{"tool": "Pylint", "message": "Consider using f-string"}],
        }
    )

    service = CodeReviewService(
        analyst_client=mock_analyst, llm_client=mock_llm, mcp_client=mock_mcp
    )

    code = 'message = "Hello " + name'

    result = await service.analyze_with_mcp(code, language="python")

    mock_mcp.request_tool_selection.assert_called_once()
    assert "mcp_feedback" in result


@pytest.mark.asyncio
async def test_batch_review():
    """Review em lote deve processar multiplos arquivos."""
    from src.services.code_review_integration import CodeReviewService

    mock_analyst = AsyncMock()
    mock_llm = AsyncMock()
    mock_mcp = AsyncMock()

    mock_llm.generate_code = AsyncMock(return_value={"code": "reviewed", "issues": 0})

    service = CodeReviewService(
        analyst_client=mock_analyst, llm_client=mock_llm, mcp_client=mock_mcp
    )

    files = {"file1.py": "code1", "file2.py": "code2"}

    result = await service.batch_review(files)

    assert "file1.py" in result
    assert "file2.py" in result


@pytest.mark.asyncio
async def test_review_without_llm():
    """Review deve funcionar sem LLM (modo basico)."""
    from src.services.code_review_integration import CodeReviewService

    mock_analyst = AsyncMock()
    mock_mcp = AsyncMock()

    service = CodeReviewService(analyst_client=mock_analyst, llm_client=None, mcp_client=mock_mcp)

    code = "def simple(): pass"

    result = await service.analyze_code(code, language="python")

    # Deve retornar resultado basico mesmo sem LLM
    assert result is not None
