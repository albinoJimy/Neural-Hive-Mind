"""
Testes para API endpoints estendidos.
Nova funcionalidade de exploração e detecção de sinais.
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime, timezone
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from enum import Enum


# Criar mock de UnifiedDomain como Enum válido
class MockUnifiedDomain(str, Enum):
    """Mock de UnifiedDomain para testes"""

    TECHNICAL = "TECHNICAL"
    BUSINESS = "BUSINESS"
    ARCHITECTURE = "ARCHITECTURE"
    BEHAVIORAL = "BEHAVIORAL"
    EVOLUTION = "EVOLUTION"


# Mock de dependências externas antes de importar
mock_domain = MagicMock()
mock_domain.UnifiedDomain = MockUnifiedDomain

mock_obs = MagicMock()
mock_obs.get_tracer = MagicMock(return_value=MagicMock())

sys.modules["neural_hive_domain"] = mock_domain
sys.modules["neural_hive_observability"] = mock_obs

# Agora pode importar
from src.api.http_server import app, _engine, init_app


@pytest.fixture
def mock_engine():
    """Mock do ExplorationEngine."""
    engine = AsyncMock()
    engine._is_running = True
    engine.get_stats.return_value = {
        "processed": 10,
        "detected": 5,
        "published": 5,
        "queue_size": 2,
    }
    engine.scan_codebase = AsyncMock(
        return_value=[{"filepath": "/test.py", "signal_type": "modified", "intensity": 0.7}]
    )
    engine.get_curiosity_scores = AsyncMock(
        return_value=[{"filepath": "/test.py", "curiosity_score": 85.0}]
    )
    engine.get_exploration_summary = AsyncMock(
        return_value={
            "directory_curiosity": 75.0,
            "signal_summary": {"total_signals": 5},
            "hotspots": [],
        }
    )
    return engine


@pytest.fixture
def client(mock_engine):
    """Cliente de teste com engine mockado."""
    import src.api.http_server as http_server_module

    original_engine = http_server_module._engine

    # Set the mock engine directly
    http_server_module._engine = mock_engine

    yield TestClient(app)

    # Restore original
    http_server_module._engine = original_engine


class TestExplorationsEndpoints:
    """Testes de endpoints de exploração."""

    def test_list_explorations_empty(self, client):
        """Testa listar explorações quando vazio."""
        from src.api.http_server import _explorations

        _explorations.clear()

        response = client.get("/api/v1/explorations")

        assert response.status_code == 200
        data = response.json()
        assert data["explorations"] == []
        assert data["total"] == 0

    def test_list_explorations_with_items(self, client):
        """Testa listar explorações com itens."""
        from src.api.http_server import _explorations

        _explorations["exp_1"] = {
            "target": "/src",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scouts_assigned": 2,
            "files_scanned": 10,
            "patterns_found": 3,
        }

        response = client.get("/api/v1/explorations?status=active")

        assert response.status_code == 200
        data = response.json()
        assert len(data["explorations"]) == 1
        assert data["explorations"][0]["exploration_id"] == "exp_1"

    def test_cancel_exploration(self, client):
        """Testa cancelar exploração."""
        from src.api.http_server import _explorations

        _explorations["exp_1"] = {
            "target": "/src",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scouts_assigned": 1,
        }

        response = client.delete("/api/v1/explorations/exp_1")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert _explorations["exp_1"]["status"] == "cancelled"

    def test_cancel_not_found(self, client):
        """Testa cancelar exploração inexistente."""
        response = client.delete("/api/v1/explorations/nonexistent")

        assert response.status_code == 404

    def test_cancel_already_completed(self, client):
        """Testa cancelar exploração já completada."""
        from src.api.http_server import _explorations

        _explorations["exp_1"] = {
            "target": "/src",
            "status": "completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        response = client.delete("/api/v1/explorations/exp_1")

        assert response.status_code == 400
        assert "already completed" in response.json()["detail"].lower()

    def test_add_scout(self, client):
        """Testa adicionar scout à exploração."""
        from src.api.http_server import _explorations

        _explorations["exp_1"] = {
            "target": "/src",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scouts_assigned": 1,
            "scouts": ["scout_1"],
        }

        response = client.post("/api/v1/explorations/exp_1/scouts?scout_id=scout_2")

        assert response.status_code == 200
        data = response.json()
        assert data["total_scouts"] == 2
        assert "scout_2" in _explorations["exp_1"]["scouts"]

    def test_add_scout_duplicate(self, client):
        """Testa adicionar scout duplicado."""
        from src.api.http_server import _explorations

        _explorations["exp_1"] = {"target": "/src", "status": "active", "scouts": ["scout_1"]}

        response = client.post("/api/v1/explorations/exp_1/scouts?scout_id=scout_1")

        assert response.status_code == 400
        assert "already assigned" in response.json()["detail"].lower()

    def test_create_exploration(self, client):
        """Testa criar nova exploração."""
        from src.api.http_server import _explorations

        response = client.post("/api/v1/explorations?target=/src&task_type=scan")

        assert response.status_code == 200
        data = response.json()
        assert "exploration_id" in data
        assert data["target"] == "/src"
        assert data["status"] == "pending"


class TestPatternEndpoints:
    """Testes de endpoints de padrões."""

    def test_list_patterns_all(self, client):
        """Testa listar todos os padrões."""
        response = client.get("/api/v1/patterns")

        assert response.status_code == 200
        data = response.json()
        assert "patterns" in data
        assert "categories" in data
        assert len(data["patterns"]) > 0

    def test_list_patterns_filtered(self, client):
        """Testa listar padrões por categoria."""
        response = client.get("/api/v1/patterns?category=creational")

        assert response.status_code == 200
        data = response.json()
        assert data["category_filter"] == "creational"
        # Todos os padrões retornados devem ser da categoria
        for pattern in data["patterns"]:
            assert pattern["category"] == "creational"


class TestSignalDetectionEndpoints:
    """Testes de endpoints de detecção de sinais."""

    def test_detect_signals(self, client):
        """Testa detecção de sinais."""
        response = client.post("/api/v1/signal-detect?directory=/src&extensions=.py,.ts")

        assert response.status_code == 200
        data = response.json()
        assert "directory" in data
        assert "signals_detected" in data
        assert "signals" in data

    def test_detect_signals_engine_down(self, client):
        """Testa detecção com engine desligado."""
        import src.api.http_server as http_server_module

        # Temporariamente setar engine como None
        original_engine = http_server_module._engine
        http_server_module._engine = None

        try:
            response = client.post("/api/v1/signal-detect?directory=/src")
            assert response.status_code == 503
        finally:
            http_server_module._engine = original_engine


class TestCuriosityEndpoints:
    """Testes de endpoints de curiosidade."""

    def test_get_curiosity_scores(self, client):
        """Testa obter scores de curiosidade."""
        response = client.get("/api/v1/curiosity/src")

        assert response.status_code == 200
        data = response.json()
        assert "directory" in data
        assert "files" in data

    def test_get_exploration_summary(self, client):
        """Testa obter resumo de exploração."""
        response = client.get("/api/v1/exploration-summary/src")

        assert response.status_code == 200
        data = response.json()
        assert "directory_curiosity" in data
        assert "signal_summary" in data
        assert "hotspots" in data


class TestErrorHandling:
    """Testes de tratamento de erros."""

    def test_engine_not_initialized(self, client):
        """Testa comportamento quando engine não está inicializado."""
        import src.api.http_server as http_server_module

        # Temporariamente setar engine como None
        original_engine = http_server_module._engine
        http_server_module._engine = None

        try:
            response = client.get("/api/v1/curiosity/src")
            assert response.status_code == 503
            assert "not initialized" in response.json()["detail"].lower()
        finally:
            http_server_module._engine = original_engine

    def test_invalid_exploration_id(self, client):
        """Testa ID de exploração inválido."""
        response = client.delete("/api/v1/explorations/invalid_id")

        assert response.status_code == 404


@pytest.mark.asyncio
class TestAsyncEndpoints:
    """Testes para endpoints async."""

    async def test_scan_codebase_async(self, mock_engine):
        """Testa scan de codebase de forma assíncrona."""
        # Chamar diretamente o método do engine
        signals = await mock_engine.scan_codebase("/src", {".py"})

        assert signals is not None
        mock_engine.scan_codebase.assert_called_once_with("/src", {".py"})

    async def test_get_curiosity_async(self, mock_engine):
        """Testa obtenção de curiosidade de forma assíncrona."""
        scores = await mock_engine.get_curiosity_scores("/src", 10)

        assert scores is not None
        mock_engine.get_curiosity_scores.assert_called_once_with("/src", 10)
