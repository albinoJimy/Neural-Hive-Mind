"""
API REST para gestão de incidentes de segurança.
"""

from datetime import UTC, datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

router = APIRouter()


class IncidentResponse(BaseModel):
    """Response de incidente."""

    incident_id: str
    threat_type: str
    severity: str
    status: str
    created_at: str
    affected_resources: list[str]
    enforcement_actions: list[str]
    remediation_actions: list[str]


class IncidentListResponse(BaseModel):
    """Response paginado de incidentes."""

    incidents: list[IncidentResponse]
    total_count: int
    page: int
    page_size: int


class IncidentStatistics(BaseModel):
    """Estatísticas de incidentes."""

    total_incidents: int
    by_severity: dict
    by_threat_type: dict
    by_status: dict
    avg_resolution_time_seconds: float


@router.get("/incidents", response_model=IncidentListResponse)
async def list_incidents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    severity: Optional[str] = Query(None),
    threat_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    fastapi_request: Request = None,
):
    """
    Lista incidentes com filtros e paginação.

    Args:
        page: Número da página
        page_size: Tamanho da página
        severity: Filtrar por severidade
        threat_type: Filtrar por tipo de ameaça
        status: Filtrar por status
        fastapi_request: FastAPI Request

    Returns:
        Lista paginada de incidentes
    """
    try:
        logger.info(
            "incidents_api.list_incidents",
            page=page,
            page_size=page_size,
            severity=severity,
            threat_type=threat_type,
            status=status,
        )

        mongodb = fastapi_request.app.state.mongodb

        # Construir filtro
        query_filter = {}
        if severity:
            query_filter["severity"] = severity
        if threat_type:
            query_filter["threat_type"] = threat_type
        if status:
            query_filter["status"] = status

        # Contar total
        total_count = await mongodb.incidents_collection.count_documents(query_filter)

        # Buscar incidentes
        skip = (page - 1) * page_size
        cursor = (
            mongodb.incidents_collection.find(query_filter)
            .sort("created_at", -1)
            .skip(skip)
            .limit(page_size)
        )

        incidents = []
        async for doc in cursor:
            incidents.append(
                IncidentResponse(
                    incident_id=doc.get("incident_id", ""),
                    threat_type=doc.get("threat_type", "unknown"),
                    severity=doc.get("severity", "unknown"),
                    status=doc.get("status", "open"),
                    created_at=doc.get("created_at", datetime.now(UTC).isoformat()),
                    affected_resources=doc.get("affected_resources", []),
                    enforcement_actions=doc.get("enforcement_actions", []),
                    remediation_actions=doc.get("remediation_actions", []),
                )
            )

        return IncidentListResponse(
            incidents=incidents, total_count=total_count, page=page, page_size=page_size
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("incidents_api.list_incidents_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str, fastapi_request: Request):
    """
    Obtém detalhes de um incidente.

    Args:
        incident_id: ID do incidente
        fastapi_request: FastAPI Request

    Returns:
        Detalhes do incidente
    """
    try:
        logger.info("incidents_api.get_incident", incident_id=incident_id)

        mongodb = fastapi_request.app.state.mongodb

        doc = await mongodb.incidents_collection.find_one({"incident_id": incident_id})

        if not doc:
            raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

        return IncidentResponse(
            incident_id=doc.get("incident_id", ""),
            threat_type=doc.get("threat_type", "unknown"),
            severity=doc.get("severity", "unknown"),
            status=doc.get("status", "open"),
            created_at=doc.get("created_at", datetime.now(UTC).isoformat()),
            affected_resources=doc.get("affected_resources", []),
            enforcement_actions=doc.get("enforcement_actions", []),
            remediation_actions=doc.get("remediation_actions", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("incidents_api.get_incident_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/incidents/statistics", response_model=IncidentStatistics)
async def get_incident_statistics(fastapi_request: Request):
    """
    Obtém estatísticas agregadas de incidentes.

    Args:
        fastapi_request: FastAPI Request

    Returns:
        Estatísticas de incidentes
    """
    try:
        logger.info("incidents_api.get_statistics")

        mongodb = fastapi_request.app.state.mongodb

        # Total de incidentes
        total_incidents = await mongodb.incidents_collection.count_documents({})

        # Agregação por severidade
        severity_pipeline = [{"$group": {"_id": "$severity", "count": {"$sum": 1}}}]
        by_severity = {}
        async for doc in mongodb.incidents_collection.aggregate(severity_pipeline):
            by_severity[doc["_id"]] = doc["count"]

        # Agregação por tipo de ameaça
        threat_pipeline = [{"$group": {"_id": "$threat_type", "count": {"$sum": 1}}}]
        by_threat_type = {}
        async for doc in mongodb.incidents_collection.aggregate(threat_pipeline):
            by_threat_type[doc["_id"]] = doc["count"]

        # Agregação por status
        status_pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        by_status = {}
        async for doc in mongodb.incidents_collection.aggregate(status_pipeline):
            by_status[doc["_id"]] = doc["count"]

        # Tempo médio de resolução
        resolution_pipeline = [
            {"$match": {"status": "resolved", "resolved_at": {"$exists": True}}},
            {
                "$project": {
                    "resolution_time": {
                        "$divide": [
                            {"$subtract": ["$resolved_at", "$created_at"]},
                            1000,  # Converter para segundos
                        ]
                    }
                }
            },
            {"$group": {"_id": None, "avg_time": {"$avg": "$resolution_time"}}},
        ]
        avg_resolution_time = 0
        async for doc in mongodb.incidents_collection.aggregate(resolution_pipeline):
            avg_resolution_time = doc.get("avg_time", 0)

        return IncidentStatistics(
            total_incidents=total_incidents,
            by_severity=by_severity,
            by_threat_type=by_threat_type,
            by_status=by_status,
            avg_resolution_time_seconds=avg_resolution_time,
        )

    except Exception as e:
        logger.error("incidents_api.get_statistics_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
