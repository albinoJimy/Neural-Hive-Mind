from fastapi import APIRouter, HTTPException, Query, Request
from typing import List, Dict, Any, Optional

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


@router.get("/{decision_id}")
async def get_decision(decision_id: str, request: Request) -> Dict[str, Any]:
    """Buscar decisão estratégica por ID"""
    mongodb_client = request.app.state.app_state.mongodb_client

    decision = await mongodb_client.get_strategic_decision(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

    # Remover _id do MongoDB antes de retornar
    decision.pop('_id', None)
    return decision


@router.get("")
async def list_decisions(
    request: Request,
    decision_type: Optional[str] = Query(None),
    start_date: Optional[int] = Query(None),
    end_date: Optional[int] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0)
) -> Dict[str, Any]:
    """Listar decisões com filtros"""
    mongodb_client = request.app.state.app_state.mongodb_client

    # Construir filtros
    filters = {}
    if decision_type:
        filters['decision_type'] = decision_type
    if start_date or end_date:
        filters['created_at'] = {}
        if start_date:
            filters['created_at']['$gte'] = start_date
        if end_date:
            filters['created_at']['$lte'] = end_date

    decisions = await mongodb_client.list_strategic_decisions(filters, limit=limit, skip=offset)

    # Remover _id do MongoDB
    for decision in decisions:
        decision.pop('_id', None)

    return {
        "decisions": decisions,
        "total": len(decisions),
        "limit": limit,
        "offset": offset
    }


@router.get("/recent")
async def get_recent_decisions(request: Request, hours: int = Query(24)) -> List[Dict[str, Any]]:
    """Buscar decisões recentes"""
    mongodb_client = request.app.state.app_state.mongodb_client

    decisions = await mongodb_client.get_recent_decisions(hours=hours)

    # Remover _id do MongoDB
    for decision in decisions:
        decision.pop('_id', None)

    return decisions


@router.get("/stats")
async def get_decision_stats(request: Request) -> Dict[str, Any]:
    """Estatísticas de decisões"""
    mongodb_client = request.app.state.app_state.mongodb_client

    # Buscar últimas 100 decisões para estatísticas
    recent_decisions = await mongodb_client.list_strategic_decisions({}, limit=100)

    if not recent_decisions:
        return {
            "total": 0,
            "by_type": {},
            "avg_confidence": 0.0,
            "avg_risk": 0.0
        }

    # Calcular estatísticas
    by_type = {}
    total_confidence = 0.0
    total_risk = 0.0

    for decision in recent_decisions:
        decision_type = decision.get('decision_type', 'unknown')
        by_type[decision_type] = by_type.get(decision_type, 0) + 1
        total_confidence += decision.get('confidence_score', 0.0)
        total_risk += decision.get('risk_assessment', {}).get('risk_score', 0.0)

    count = len(recent_decisions)

    return {
        "total": count,
        "by_type": by_type,
        "avg_confidence": total_confidence / count,
        "avg_risk": total_risk / count
    }
