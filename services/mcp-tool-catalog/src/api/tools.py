"""
API REST endpoints para operações com ferramentas MCP.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field
import structlog

from ..models.tool_descriptor import ToolDescriptor, ToolCategory
from ..services.tool_registry import ToolRegistry

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


# ===== Request/Response Models =====

class ToolResponse(BaseModel):
    """Resposta com dados de uma ferramenta."""
    tool_id: str
    tool_name: str
    category: str
    version: str
    reputation_score: float
    cost_score: float
    average_execution_time_ms: float
    integration_type: str
    capabilities: List[str]
    metadata: dict


class ToolListResponse(BaseModel):
    """Resposta com lista de ferramentas."""
    total: int
    tools: List[ToolResponse]


class ToolHealthResponse(BaseModel):
    """Resposta de health check de ferramenta."""
    tool_id: str
    tool_name: str
    is_healthy: bool
    last_check: Optional[str] = None
    error: Optional[str] = None


class ToolFeedbackRequest(BaseModel):
    selection_id: str
    tool_id: str
    success: bool
    execution_time_ms: int = Field(ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ===== Dependency Injection =====

tool_registry: Optional[ToolRegistry] = None


def set_tool_registry(registry: ToolRegistry):
    """Injeta registry no router."""
    global tool_registry
    tool_registry = registry


# ===== Endpoints =====

@router.get("", response_model=ToolListResponse)
async def list_tools(
    category: Optional[str] = Query(None, description="Filtrar por categoria"),
    min_reputation: Optional[float] = Query(
        None, ge=0.0, le=1.0, description="Reputation score mínimo"
    ),
    max_cost: Optional[float] = Query(
        None, ge=0.0, le=1.0, description="Cost score máximo"
    ),
    limit: int = Query(100, ge=1, le=500, description="Número máximo de resultados")
):
    """
    Lista todas as ferramentas do catálogo com filtros opcionais.

    Args:
        category: Filtrar por categoria (ANALYSIS, GENERATION, etc)
        min_reputation: Filtrar por reputation score mínimo
        max_cost: Filtrar por cost score máximo
        limit: Número máximo de resultados

    Returns:
        Lista de ferramentas
    """
    if not tool_registry:
        raise HTTPException(status_code=500, detail="Tool registry not initialized")

    try:
        # Buscar todas as ferramentas
        tools = await tool_registry.get_all_tools()

        # Aplicar filtros
        if category:
            try:
                cat = ToolCategory(category.upper())
                tools = [t for t in tools if t.category == cat]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid category: {category}"
                )

        if min_reputation is not None:
            tools = [t for t in tools if t.reputation_score >= min_reputation]

        if max_cost is not None:
            tools = [t for t in tools if t.cost_score <= max_cost]

        # Limitar resultados
        tools = tools[:limit]

        # Converter para response model
        tool_responses = [
            ToolResponse(
                tool_id=t.tool_id,
                tool_name=t.tool_name,
                category=t.category.value,
                version=t.version,
                reputation_score=t.reputation_score,
                cost_score=t.cost_score,
                average_execution_time_ms=t.average_execution_time_ms,
                integration_type=t.integration_type.value,
                capabilities=t.capabilities,
                metadata=t.metadata or {}
            )
            for t in tools
        ]

        return ToolListResponse(
            total=len(tool_responses),
            tools=tool_responses
        )

    except Exception as e:
        logger.error("list_tools_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(
    tool_id: str = Path(..., description="ID da ferramenta")
):
    """
    Obtém detalhes de uma ferramenta específica.

    Args:
        tool_id: ID único da ferramenta

    Returns:
        Detalhes da ferramenta
    """
    if not tool_registry:
        raise HTTPException(status_code=500, detail="Tool registry not initialized")

    try:
        tool = await tool_registry.get_tool_by_id(tool_id)

        if not tool:
            raise HTTPException(
                status_code=404,
                detail=f"Tool {tool_id} not found"
            )

        return ToolResponse(
            tool_id=tool.tool_id,
            tool_name=tool.tool_name,
            category=tool.category.value,
            version=tool.version,
            reputation_score=tool.reputation_score,
            cost_score=tool.cost_score,
            average_execution_time_ms=tool.average_execution_time_ms,
            integration_type=tool.integration_type.value,
            capabilities=tool.capabilities,
            metadata=tool.metadata or {}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_tool_failed", tool_id=tool_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/category/{category}", response_model=ToolListResponse)
async def get_tools_by_category(
    category: str = Path(..., description="Categoria da ferramenta")
):
    """
    Lista ferramentas por categoria.

    Args:
        category: ANALYSIS, GENERATION, TRANSFORMATION, VALIDATION, AUTOMATION, INTEGRATION

    Returns:
        Lista de ferramentas da categoria
    """
    if not tool_registry:
        raise HTTPException(status_code=500, detail="Tool registry not initialized")

    try:
        cat = ToolCategory(category.upper())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category: {category}. Valid: {[c.value for c in ToolCategory]}"
        )

    try:
        tools = await tool_registry.get_tools_by_category(cat)

        tool_responses = [
            ToolResponse(
                tool_id=t.tool_id,
                tool_name=t.tool_name,
                category=t.category.value,
                version=t.version,
                reputation_score=t.reputation_score,
                cost_score=t.cost_score,
                average_execution_time_ms=t.average_execution_time_ms,
                integration_type=t.integration_type.value,
                capabilities=t.capabilities,
                metadata=t.metadata or {}
            )
            for t in tools
        ]

        return ToolListResponse(
            total=len(tool_responses),
            tools=tool_responses
        )

    except Exception as e:
        logger.error(
            "get_tools_by_category_failed",
            category=category,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health/{tool_id}", response_model=ToolHealthResponse)
async def check_tool_health(
    tool_id: str = Path(..., description="ID da ferramenta")
):
    """
    Verifica health status de uma ferramenta.

    Args:
        tool_id: ID da ferramenta

    Returns:
        Status de saúde
    """
    if not tool_registry:
        raise HTTPException(status_code=500, detail="Tool registry not initialized")

    try:
        tool = await tool_registry.get_tool_by_id(tool_id)

        if not tool:
            raise HTTPException(
                status_code=404,
                detail=f"Tool {tool_id} not found"
            )

        # Verificar health no Redis (fallback para True se não tiver info)
        health_status = await tool_registry.redis_client.get_tool_health(tool.tool_id)
        is_healthy = health_status if health_status is not None else True

        return ToolHealthResponse(
            tool_id=tool.tool_id,
            tool_name=tool.tool_name,
            is_healthy=is_healthy,
            last_check=None,  # TODO: implementar last_check_timestamp
            error=None if is_healthy else "Tool marked as unhealthy"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("check_tool_health_failed", tool_id=tool_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{tool_id}/feedback", status_code=204)
async def submit_tool_feedback(
    tool_id: str = Path(..., description="ID da ferramenta"),
    feedback: ToolFeedbackRequest
):
    """Recebe feedback de execução de ferramenta."""
    if not tool_registry:
        raise HTTPException(status_code=500, detail="Tool registry not initialized")

    if feedback and feedback.tool_id != tool_id:
        raise HTTPException(
            status_code=400,
            detail="tool_id in path and body must match"
        )

    try:
        tool = await tool_registry.get_tool_by_id(tool_id)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool {tool_id} not found")

        await tool_registry.update_tool_metrics(
            tool_id=tool_id,
            category=tool.category.value,
            success=feedback.success,
            execution_time_ms=feedback.execution_time_ms,
            metadata=feedback.metadata
        )

        logger.info(
            "tool_feedback_processed",
            tool_id=tool_id,
            selection_id=feedback.selection_id,
            success=feedback.success
        )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("submit_tool_feedback_failed", tool_id=tool_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
