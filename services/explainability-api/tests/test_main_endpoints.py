"""
Testes para os endpoints principais do Explainability API.

Cobre health, ready, metrics, explainability e shap.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime


@pytest.mark.asyncio
async def test_health_endpoint():
    """Health check deve retornar status healthy."""
    from src.main import health_check

    response = await health_check()

    assert response["status"] == "healthy"
    assert response["service"] == "explainability-api"
    assert "timestamp" in response
    assert "version" in response


@pytest.mark.asyncio
async def test_readiness_endpoint_mongodb_connected():
    """Readiness check deve retornar ready quando MongoDB conectado."""
    from src.main import readiness_check, mongo_client

    # Configurar mock MongoDB
    mock_mongo = MagicMock()
    mock_mongo.admin.command = AsyncMock(return_value={"ok": 1})

    # Simular MongoDB conectado
    import src.main

    src.main.mongo_client = mock_mongo
    src.main.explanation_producer = None

    response = await readiness_check()

    # Parse JSONResponse body
    import json

    body = json.loads(response.body.decode())
    assert body["status"] == "ready"
    assert body["checks"]["mongodb"] is True
    assert body["checks"]["api"] is True


@pytest.mark.asyncio
async def test_readiness_endpoint_mongodb_disconnected():
    """Readiness check deve retornar not_ready quando MongoDB desconectado."""
    from src.main import readiness_check

    # Simular MongoDB desconectado
    import src.main

    src.main.mongo_client = None
    src.main.explanation_producer = None

    response = await readiness_check()

    # Parse JSONResponse body
    import json

    body = json.loads(response.body.decode())
    assert body["status"] == "not_ready"
    assert body["checks"]["mongodb"] is False


@pytest.mark.asyncio
async def test_readiness_endpoint_with_kafka():
    """Readiness check deve verificar Kafka producer."""
    from src.main import readiness_check

    mock_mongo = MagicMock()
    mock_mongo.admin.command = AsyncMock(return_value={"ok": 1})

    mock_producer = MagicMock()
    mock_producer.producer = MagicMock()

    import src.main

    src.main.mongo_client = mock_mongo
    src.main.explanation_producer = mock_producer

    response = await readiness_check()

    # Parse JSONResponse body
    import json

    body = json.loads(response.body.decode())
    assert body["status"] == "ready"
    assert body["checks"]["kafka_producer"] is True


@pytest.mark.asyncio
async def test_metrics_endpoint():
    """Metrics endpoint deve retornar metricas Prometheus."""
    from src.main import metrics

    response = await metrics()

    assert "content-type" in response.headers
    assert "text/plain" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_get_explainability_by_token_success():
    """Buscar explicação por token deve retornar dados."""
    from src.main import get_explainability_by_token, db

    mock_db = MagicMock()
    mock_db.explainability_ledger.find_one = AsyncMock(
        return_value={
            "explainability_token": "token-123",
            "decision_id": "decision-123",
            "method": "shap",
            "generated_at": datetime.now(),
        }
    )

    import src.main

    src.main.db = mock_db

    response = await get_explainability_by_token("token-123")

    assert response["explainability_token"] == "token-123"
    assert response["decision_id"] == "decision-123"


@pytest.mark.asyncio
async def test_get_explainability_by_token_not_found():
    """Buscar explicação por token inexistente deve retornar 404."""
    from src.main import get_explainability_by_token
    from fastapi import HTTPException

    mock_db = MagicMock()
    mock_db.explainability_ledger.find_one = AsyncMock(return_value=None)

    import src.main

    src.main.db = mock_db

    with pytest.raises(HTTPException) as exc_info:
        await get_explainability_by_token("nonexistent")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_explanation_extended():
    """Buscar explicação extendida por decision_id."""
    from src.main import get_explanation_extended, api_extensions

    mock_extensions = AsyncMock()
    mock_extensions.get_explainability_by_decision_id = AsyncMock(
        return_value={
            "decision_id": "decision-123",
            "method": "hierarchical",
            "hierarchical_data": {"seniority_weights": [0.3, 0.5, 0.2]},
        }
    )

    import src.main

    src.main.api_extensions = mock_extensions

    response = await get_explanation_extended("decision-123")

    assert response["decision_id"] == "decision-123"
    assert "hierarchical_data" in response


@pytest.mark.asyncio
async def test_generate_explanation():
    """Gerar explicação sob demanda."""
    from src.main import generate_explanation_endpoint, GenerateExplanationRequest, api_extensions

    mock_extensions = AsyncMock()
    mock_extensions.generate_explanation = AsyncMock(
        return_value={
            "decision_id": "decision-123",
            "explainability_token": "token-456",
            "explanation": "Generated explanation",
        }
    )

    import src.main

    src.main.api_extensions = mock_extensions

    request = GenerateExplanationRequest(
        decision_id="decision-123", format="json", include_shap=True
    )

    response = await generate_explanation_endpoint(request)

    assert response["decision_id"] == "decision-123"
    assert "explainability_token" in response


@pytest.mark.asyncio
async def test_get_explanation_formatted():
    """Buscar explicação em formato especifico."""
    from src.main import get_explanation_formatted, api_extensions

    mock_extensions = AsyncMock()
    mock_extensions.get_explainability_by_decision_id = AsyncMock(
        return_value={"decision_id": "decision-123", "explanation": "Test explanation"}
    )
    mock_extensions.format_explanation = MagicMock(return_value="<html>Formatted</html>")

    import src.main

    src.main.api_extensions = mock_extensions

    response = await get_explanation_formatted("decision-123", "html")

    assert "<html>" in str(response)


@pytest.mark.asyncio
async def test_get_explanation_formatted_invalid_format():
    """Formato invalido deve retornar 400."""
    from src.main import get_explanation_formatted
    from fastapi import HTTPException

    mock_extensions = AsyncMock()
    mock_extensions.get_explainability_by_decision_id = AsyncMock(
        return_value={"decision_id": "decision-123"}
    )

    import src.main

    src.main.api_extensions = mock_extensions

    with pytest.raises(HTTPException) as exc_info:
        await get_explanation_formatted("decision-123", "invalid")

    assert exc_info.value.status_code == 400
    assert "Invalid format" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_explainability_stats():
    """Buscar estatisticas de explicabilidade."""
    from src.main import get_explainability_stats, db

    mock_db = MagicMock()
    # aggregate() retorna um cursor com método to_list
    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(
        return_value=[{"_id": "shap", "count": 150}, {"_id": "hierarchical", "count": 80}]
    )
    mock_db.explainability_ledger.aggregate = Mock(return_value=mock_cursor)
    mock_db.explainability_ledger.count_documents = AsyncMock(return_value=230)

    import src.main

    src.main.db = mock_db

    response = await get_explainability_stats()

    assert response["total_explanations"] == 230
    assert response["by_method"]["shap"] == 150
    assert response["by_method"]["hierarchical"] == 80


@pytest.mark.asyncio
async def test_get_explainability_stats_with_date_filter():
    """Estatisticas com filtro de data."""
    from src.main import get_explainability_stats, db

    mock_db = MagicMock()
    # aggregate() retorna um cursor com método to_list
    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=[{"_id": "shap", "count": 50}])
    mock_db.explainability_ledger.aggregate = Mock(return_value=mock_cursor)
    mock_db.explainability_ledger.count_documents = AsyncMock(return_value=50)

    import src.main

    src.main.db = mock_db

    response = await get_explainability_stats(start_date="2026-03-01", end_date="2026-03-30")

    assert response["total_explanations"] == 50


@pytest.mark.asyncio
async def test_global_exception_handler():
    """Handler global de excecao deve retornar 500."""
    from src.main import global_exception_handler
    from fastapi import Request

    request = MagicMock(spec=Request)
    request.url.path = "/api/v1/explainability/123"

    exc = Exception("Test error")

    response = await global_exception_handler(request, exc)

    assert response.status_code == 500
    assert "Internal server error" in response.body.decode()
