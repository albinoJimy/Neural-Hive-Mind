"""
Router FastAPI para endpoints de SLOs.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from ..models.slo_definition import SLODefinition
from ..services.slo_manager import SLOManager


router = APIRouter(prefix="/api/v1/slos", tags=["SLOs"])


# Response models
class SLOCreateResponse(BaseModel):
    slo_id: str
    message: str


class SLOListResponse(BaseModel):
    slos: List[SLODefinition]
    total: int


class SLOTestResponse(BaseModel):
    success: bool
    sli_value: Optional[float] = None
    message: str


class SLOImportResponse(BaseModel):
    imported_slos: List[str]
    total: int


# Dependency injection (será configurado no main.py)
def get_slo_manager() -> SLOManager:
    """Dependency para injetar SLOManager."""
    # Será sobrescrito no main.py
    raise NotImplementedError


@router.post("", response_model=SLOCreateResponse, status_code=201)
async def create_slo(
    slo: SLODefinition,
    manager: SLOManager = Depends(get_slo_manager)
):
    """Cria novo SLO."""
    try:
        slo_id = await manager.create_slo(slo)
        return SLOCreateResponse(
            slo_id=slo_id,
            message="SLO created successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/{slo_id}", response_model=SLODefinition)
async def get_slo(
    slo_id: str,
    manager: SLOManager = Depends(get_slo_manager)
):
    """Busca SLO por ID."""
    slo = await manager.get_slo(slo_id)
    if not slo:
        raise HTTPException(status_code=404, detail="SLO not found")
    return slo


@router.get("", response_model=SLOListResponse)
async def list_slos(
    service_name: Optional[str] = Query(None),
    layer: Optional[str] = Query(None),
    slo_type: Optional[str] = Query(None),
    enabled: bool = Query(True),
    manager: SLOManager = Depends(get_slo_manager)
):
    """Lista SLOs com filtros opcionais."""
    filters = {}
    if service_name:
        filters["service_name"] = service_name
    if layer:
        filters["layer"] = layer
    if slo_type:
        filters["slo_type"] = slo_type
    filters["enabled"] = enabled

    slos = await manager.list_slos(filters if filters else None)
    return SLOListResponse(slos=slos, total=len(slos))


@router.put("/{slo_id}", response_model=SLODefinition)
async def update_slo(
    slo_id: str,
    updates: dict,
    manager: SLOManager = Depends(get_slo_manager)
):
    """Atualiza campos do SLO."""
    try:
        slo = await manager.update_slo(slo_id, updates)
        if not slo:
            raise HTTPException(status_code=404, detail="SLO not found")
        return slo
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.delete("/{slo_id}")
async def delete_slo(
    slo_id: str,
    manager: SLOManager = Depends(get_slo_manager)
):
    """Deleta SLO (soft delete)."""
    success = await manager.delete_slo(slo_id)
    if not success:
        raise HTTPException(status_code=404, detail="SLO not found")
    return {"message": "SLO deleted successfully"}


@router.post("/{slo_id}/test", response_model=SLOTestResponse)
async def test_slo(
    slo_id: str,
    manager: SLOManager = Depends(get_slo_manager)
):
    """Testa query do SLO contra Prometheus."""
    slo = await manager.get_slo(slo_id)
    if not slo:
        raise HTTPException(status_code=404, detail="SLO not found")

    success, sli_value, error = await manager.test_slo_query(slo)

    if success:
        return SLOTestResponse(
            success=True,
            sli_value=sli_value,
            message="Query executed successfully"
        )
    else:
        return SLOTestResponse(
            success=False,
            message=f"Query failed: {error}"
        )


class ImportAlertsRequest(BaseModel):
    alert_rules_path: str


@router.post("/import/alerts", response_model=SLOImportResponse)
async def import_from_alerts(
    request: ImportAlertsRequest,
    manager: SLOManager = Depends(get_slo_manager)
):
    """Importa SLOs de arquivo de alertas Prometheus."""
    try:
        imported_slos = await manager.import_from_alerts(request.alert_rules_path)
        return SLOImportResponse(
            imported_slos=imported_slos,
            total=len(imported_slos)
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Alert rules file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
