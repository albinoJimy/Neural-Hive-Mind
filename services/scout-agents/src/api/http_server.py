"""FastAPI HTTP server for health checks and API endpoints"""

from datetime import datetime, timezone
from typing import Dict, Optional

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest

from neural_hive_domain import UnifiedDomain

from ..config import get_settings
from ..engine.exploration_engine import ExplorationEngine
from ..models.raw_event import RawEvent
from ..models.scout_signal import ChannelType, SignalType

logger = structlog.get_logger()

# Global references (set by main.py)
app = FastAPI(
    title="Scout Agents API",
    description="Neural Hive-Mind Exploration Layer - Scout Agents",
    version="1.0.0",
)

_engine: Optional[ExplorationEngine] = None
_agent_start_time: datetime = datetime.now(timezone.utc)
_agent_id: str = ""


def init_app(engine: ExplorationEngine, agent_id: str):
    """Initialize app with engine reference"""
    global _engine, _agent_id
    _engine = engine
    _agent_id = agent_id


@app.get("/health/live")
async def liveness():
    """Liveness probe - checks if process is alive"""
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/health/ready")
async def readiness():
    """Readiness probe - checks if service is ready to accept traffic"""
    if not _engine or not _engine._is_running:
        raise HTTPException(status_code=503, detail="Engine not running")

    return {
        "status": "ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": _agent_id,
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()


@app.get("/api/v1/status")
async def get_status():
    """Get detailed Scout Agent status"""
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    settings = get_settings()
    uptime = (datetime.now(timezone.utc) - _agent_start_time).total_seconds()
    stats = _engine.get_stats()

    return {
        "agent_id": _agent_id,
        "version": settings.service.version,
        "environment": settings.service.environment,
        "uptime_seconds": uptime,
        "stats": stats,
        "configuration": {
            "max_signals_per_minute": settings.detection.max_signals_per_minute,
            "curiosity_threshold": settings.detection.curiosity_threshold,
            "confidence_threshold": settings.detection.confidence_threshold,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/signals")
async def list_signals(
    domain: Optional[UnifiedDomain] = None,
    signal_type: Optional[SignalType] = None,
    limit: int = Query(default=100, le=1000),
):
    """
    List recent signals (mock implementation for MVP)

    In production, this would query Memory Layer API
    """
    # For MVP, return mock data
    return {
        "signals": [],
        "total": 0,
        "limit": limit,
        "filters": {
            "domain": domain.value if domain else None,
            "signal_type": signal_type.value if signal_type else None,
        },
    }


@app.get("/api/v1/signals/{signal_id}")
async def get_signal(signal_id: str):
    """
    Get specific signal by ID (mock implementation for MVP)

    In production, this would query Memory Layer API
    """
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    # For MVP, return 404
    raise HTTPException(status_code=404, detail="Signal not found")


@app.post("/api/v1/signals/simulate")
async def simulate_signal(
    domain: UnifiedDomain = UnifiedDomain.TECHNICAL, channel: ChannelType = ChannelType.CORE
):
    """
    Simulate signal detection (for testing/development)

    This endpoint creates a synthetic raw event and processes it through
    the detection pipeline
    """
    if not _engine or not _engine._is_running:
        raise HTTPException(status_code=503, detail="Engine not running")

    try:
        # Create synthetic raw event
        raw_event = RawEvent(
            event_id=f"sim_{datetime.now(timezone.utc).timestamp()}",
            event_type="metric",
            source="simulation",
            timestamp=datetime.now(timezone.utc),
            payload={"value": 42.5, "metric_name": "test_metric", "anomaly_factor": 2.5},
            metadata={"simulation": "true", "domain": domain.value},
        )

        # Process through engine
        signal = await _engine.process_event(raw_event, domain, channel)

        if signal:
            return {
                "status": "signal_detected",
                "signal_id": signal.signal_id,
                "signal_type": signal.signal_type.value,
                "curiosity_score": signal.curiosity_score,
                "confidence": signal.confidence,
                "domain": domain.value,
                "channel": channel.value,
            }
        else:
            return {
                "status": "no_signal_detected",
                "domain": domain.value,
                "reason": "Signal did not meet thresholds or was filtered",
            }

    except Exception as e:
        logger.error("signal_simulation_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(
        "unhandled_exception", path=request.url.path, method=request.method, error=str(exc)
    )
    return HTTPException(status_code=500, detail="Internal server error")


# ========================================================================
# Exploration Endpoints
# ========================================================================

_explorations: Dict[str, Dict] = {}  # exploration_id -> exploration_data


@app.get("/api/v1/explorations")
async def list_explorations(
    status: str = Query(default="active"), limit: int = Query(default=50, le=100)
):
    """
    Lista explorações ativas ou recentes.

    Args:
        status: Filtrar por status (active, completed, failed)
        limit: Máximo de explorações a retornar

    Returns:
        Lista de explorações
    """
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    filtered = [
        (exp_id, exp) for exp_id, exp in _explorations.items() if exp.get("status") == status
    ]

    filtered.sort(key=lambda x: x[1].get("created_at", ""), reverse=True)

    return {
        "explorations": [
            {
                "exploration_id": exp_id,
                "target": exp.get("target"),
                "status": exp.get("status"),
                "created_at": exp.get("created_at"),
                "scouts_assigned": exp.get("scouts_assigned", 0),
                "files_scanned": exp.get("files_scanned", 0),
                "patterns_found": exp.get("patterns_found", 0),
            }
            for exp_id, exp in filtered[:limit]
        ],
        "total": len(filtered),
        "status_filter": status,
    }


@app.delete("/api/v1/explorations/{exploration_id}")
async def cancel_exploration(exploration_id: str):
    """
    Cancela uma exploração em andamento.

    Args:
        exploration_id: ID da exploração

    Returns:
        Resultado da operação
    """
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    if exploration_id not in _explorations:
        raise HTTPException(status_code=404, detail="Exploration not found")

    exploration = _explorations[exploration_id]

    if exploration.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Exploration already completed")

    # Marcar como cancelada
    exploration["status"] = "cancelled"
    exploration["cancelled_at"] = datetime.now(timezone.utc).isoformat()

    logger.info("exploration_cancelled", exploration_id=exploration_id)

    return {
        "exploration_id": exploration_id,
        "status": "cancelled",
        "message": "Exploration cancelled successfully",
    }


@app.post("/api/v1/explorations/{exploration_id}/scouts")
async def add_scout(exploration_id: str, scout_id: str = Query(...)):
    """
    Adiciona scout a uma exploração.

    Args:
        exploration_id: ID da exploração
        scout_id: ID do scout para adicionar

    Returns:
        Status da operação
    """
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    if exploration_id not in _explorations:
        raise HTTPException(status_code=404, detail="Exploration not found")

    exploration = _explorations[exploration_id]

    if exploration.get("status") not in ("pending", "active"):
        raise HTTPException(status_code=400, detail="Exploration is not accepting new scouts")

    # Adicionar scout
    if "scouts" not in exploration:
        exploration["scouts"] = []

    if scout_id in exploration["scouts"]:
        raise HTTPException(status_code=400, detail="Scout already assigned")

    exploration["scouts"].append(scout_id)
    exploration["scouts_assigned"] = len(exploration["scouts"])

    logger.info("scout_added_to_exploration", exploration_id=exploration_id, scout_id=scout_id)

    return {
        "exploration_id": exploration_id,
        "scout_id": scout_id,
        "total_scouts": len(exploration["scouts"]),
    }


# ========================================================================
# Pattern Detection Endpoints
# ========================================================================


@app.get("/api/v1/patterns")
async def list_patterns(
    category: Optional[str] = Query(default=None), limit: int = Query(default=100, le=500)
):
    """
    Lista padrões de design detectados.

    Args:
        category: Filtrar por categoria (creational, structural, behavioral)
        limit: Máximo de padrões

    Returns:
        Lista de padrões
    """
    from ..discovery.pattern_discovery import PatternDiscovery

    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        discovery = PatternDiscovery()

        # Obter categorias disponíveis da PatternDiscovery
        category_map = discovery.get_pattern_categories()

        # Criar lista de todos os padrões
        all_patterns = []
        for pattern_name in discovery.get_known_patterns():
            info = discovery.get_pattern_info(pattern_name)
            if info:
                all_patterns.append(
                    {
                        "name": pattern_name.capitalize(),
                        "category": info["category"],
                        "count": 0,
                        "keywords": info.get("keywords", []),
                        "common_methods": info.get("common_methods", []),
                        "naming_suffix": info.get("naming_suffix", []),
                    }
                )

        # Filtrar por categoria se especificado
        if category:
            all_patterns = [p for p in all_patterns if p["category"] == category]
            [category_map.get(category, [])]
        else:
            [list(patterns) for patterns in category_map.values()]

        return {
            "patterns": all_patterns[:limit],
            "total": len(all_patterns),
            "category_filter": category,
            "categories": category_map,
        }

    except Exception as e:
        logger.error("pattern_list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list patterns: {str(e)}")


# ========================================================================
# Signal Detection Endpoints
# ========================================================================


@app.post("/api/v1/signal-detect")
async def detect_signals(
    directory: str = Query(...),
    extensions: Optional[str] = Query(default=".py,.ts,.js,.yaml,.json"),
):
    """
    Detecta sinais de mudança em diretório.

    Args:
        directory: Diretório para escanear
        extensions: Extensões separadas por vírgula

    Returns:
        Sinais detectados
    """
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        ext_set = set(e.strip() for e in extensions.split(","))

        signals = await _engine.scan_codebase(directory, ext_set)

        return {"directory": directory, "signals_detected": len(signals), "signals": signals}

    except Exception as e:
        logger.error("signal_detection_failed", directory=directory, error=str(e))
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")


# ========================================================================
# Additional Utility Endpoints
# ========================================================================


@app.get("/api/v1/curiosity/{directory:path}")
async def get_curiosity_scores(directory: str, limit: int = Query(default=10, le=50)):
    """
    Retorna arquivos mais curiosos de um diretório.

    Args:
        directory: Diretório para analisar
        limit: Máximo de arquivos

    Returns:
        Lista de arquivos ordenados por curiosidade
    """
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        scores = await _engine.get_curiosity_scores(str(directory), limit)

        return {"directory": directory, "files": scores, "total": len(scores)}

    except Exception as e:
        logger.error("curiosity_calculation_failed", directory=directory, error=str(e))
        raise HTTPException(status_code=500, detail=f"Calculation failed: {str(e)}")


@app.get("/api/v1/exploration-summary/{directory:path}")
async def get_exploration_summary(directory: str):
    """
    Retorna resumo completo de exploração de diretório.

    Args:
        directory: Diretório para analisar

    Returns:
        Resumo com curiosidade, sinais, hotspots
    """
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        summary = await _engine.get_exploration_summary(str(directory))

        return summary

    except Exception as e:
        logger.error("exploration_summary_failed", directory=directory, error=str(e))
        raise HTTPException(status_code=500, detail=f"Summary failed: {str(e)}")


@app.post("/api/v1/explorations")
async def create_exploration(target: str = Query(...), task_type: str = Query(default="scan")):
    """
    Cria nova exploração.

    Args:
        target: Alvo da exploração (diretório ou arquivo)
        task_type: Tipo de tarefa

    Returns:
    ID da exploração criada
    """
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    exploration_id = f"exp_{datetime.now(timezone.utc).timestamp()}"

    _explorations[exploration_id] = {
        "target": target,
        "task_type": task_type,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scouts_assigned": 0,
        "files_scanned": 0,
        "patterns_found": 0,
    }

    logger.info(
        "exploration_created", exploration_id=exploration_id, target=target, task_type=task_type
    )

    return {
        "exploration_id": exploration_id,
        "target": target,
        "status": "pending",
        "message": "Exploration created successfully",
    }
