"""FastAPI HTTP server for health checks and API endpoints"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import structlog

from ..models.scout_signal import ScoutSignal, SignalType, ChannelType
from neural_hive_domain import UnifiedDomain
from ..models.raw_event import RawEvent
from ..engine.exploration_engine import ExplorationEngine
from ..config import get_settings

logger = structlog.get_logger()

# Global references (set by main.py)
app = FastAPI(
    title="Scout Agents API",
    description="Neural Hive-Mind Exploration Layer - Scout Agents",
    version="1.0.0"
)

_engine: Optional[ExplorationEngine] = None
_agent_start_time: datetime = datetime.utcnow()
_agent_id: str = ""


def init_app(engine: ExplorationEngine, agent_id: str):
    """Initialize app with engine reference"""
    global _engine, _agent_id
    _engine = engine
    _agent_id = agent_id


@app.get("/health/live")
async def liveness():
    """Liveness probe - checks if process is alive"""
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}


@app.get("/health/ready")
async def readiness():
    """Readiness probe - checks if service is ready to accept traffic"""
    if not _engine or not _engine._is_running:
        raise HTTPException(status_code=503, detail="Engine not running")

    return {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat(),
        "agent_id": _agent_id
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
    uptime = (datetime.utcnow() - _agent_start_time).total_seconds()
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
            "confidence_threshold": settings.detection.confidence_threshold
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/v1/signals")
async def list_signals(
    domain: Optional[UnifiedDomain] = None,
    signal_type: Optional[SignalType] = None,
    limit: int = Query(default=100, le=1000)
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
            "signal_type": signal_type.value if signal_type else None
        }
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
    domain: UnifiedDomain = UnifiedDomain.TECHNICAL,
    channel: ChannelType = ChannelType.CORE
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
            event_id=f"sim_{datetime.utcnow().timestamp()}",
            event_type="metric",
            source="simulation",
            timestamp=datetime.utcnow(),
            payload={
                "value": 42.5,
                "metric_name": "test_metric",
                "anomaly_factor": 2.5
            },
            metadata={
                "simulation": "true",
                "domain": domain.value
            }
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
                "channel": channel.value
            }
        else:
            return {
                "status": "no_signal_detected",
                "domain": domain.value,
                "reason": "Signal did not meet thresholds or was filtered"
            }

    except Exception as e:
        logger.error("signal_simulation_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc)
    )
    return HTTPException(status_code=500, detail="Internal server error")
