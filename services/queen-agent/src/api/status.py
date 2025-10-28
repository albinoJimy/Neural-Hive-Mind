from fastapi import APIRouter, Request
from typing import Dict, Any, List
import structlog

router = APIRouter(prefix="/api/v1/status", tags=["status"])
logger = structlog.get_logger()


@router.get("/system")
async def get_system_status(request: Request) -> Dict[str, Any]:
    """Status geral do sistema"""
    telemetry_aggregator = request.app.state.app_state.telemetry_aggregator

    try:
        health = await telemetry_aggregator.aggregate_system_health()
        return health if health else {
            "system_score": 0.0,
            "sla_compliance": 0.0,
            "error_rate": 0.0,
            "resource_saturation": 0.0,
            "active_incidents": 0,
            "timestamp": 0
        }

    except Exception as e:
        logger.error("get_system_status_failed", error=str(e))
        return {
            "system_score": 0.0,
            "sla_compliance": 0.0,
            "error_rate": 0.0,
            "resource_saturation": 0.0,
            "active_incidents": 0,
            "timestamp": 0,
            "error": str(e)
        }


@router.get("/conflicts")
async def get_active_conflicts(request: Request) -> List[Dict[str, Any]]:
    """Conflitos ativos"""
    neo4j_client = request.app.state.app_state.neo4j_client

    try:
        conflicts = await neo4j_client.list_active_conflicts()
        return conflicts

    except Exception as e:
        logger.error("get_active_conflicts_failed", error=str(e))
        return []


@router.get("/replanning")
async def get_replanning_status(request: Request) -> Dict[str, Any]:
    """Status de replanejamentos"""
    replanning_coordinator = request.app.state.app_state.replanning_coordinator

    try:
        stats = await replanning_coordinator.get_replanning_stats()
        return stats

    except Exception as e:
        logger.error("get_replanning_status_failed", error=str(e))
        return {
            "total_replannings": 0,
            "active_replannings": 0,
            "cooldown_plans": [],
            "error": str(e)
        }


@router.get("/pheromones")
async def get_pheromone_status(request: Request) -> List[Dict[str, Any]]:
    """Status de feromônios"""
    pheromone_client = request.app.state.app_state.pheromone_client

    try:
        # Buscar principais domínios de feromônios
        # Placeholder: em produção, manteríamos lista de domínios ativos
        domains = []  # Lista de domínios seria obtida dinamicamente

        pheromone_data = []
        for domain in domains[:10]:  # Limitar a 10
            signals = await pheromone_client.get_domain_signals(domain)
            pheromone_data.append({
                "domain": domain,
                "signals": signals
            })

        return pheromone_data

    except Exception as e:
        logger.error("get_pheromone_status_failed", error=str(e))
        return []
