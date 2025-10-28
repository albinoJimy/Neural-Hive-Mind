"""
API REST endpoints para seleção síncrona de ferramentas.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import structlog

from ..models.tool_selection import (
    ToolSelectionRequest,
    ToolSelectionResponse,
    SelectionMethod,
    ArtifactType,
    SelectionConstraints
)
from ..services.genetic_tool_selector import GeneticToolSelector

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/selections", tags=["selections"])


# ===== Request/Response Models =====

class ToolSelectionAPIRequest(BaseModel):
    """Request para seleção de ferramentas via API."""
    request_id: str = Field(..., description="ID único da requisição")
    ticket_id: Optional[str] = Field(None, description="ID do execution ticket")
    plan_id: Optional[str] = Field(None, description="ID do cognitive plan")
    intent_id: Optional[str] = Field(None, description="ID do intent envelope")
    correlation_id: str = Field(..., description="ID de correlação")

    artifact_type: str = Field(..., description="Tipo do artefato (CODE, CONFIG, etc)")
    language: Optional[str] = Field(None, description="Linguagem do artefato")
    complexity_score: float = Field(..., ge=0.0, le=1.0, description="Score de complexidade")

    required_categories: List[str] = Field(
        ...,
        description="Categorias obrigatórias (GENERATION, VALIDATION, etc)"
    )

    constraints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Constraints da seleção"
    )

    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Contexto adicional"
    )


class SelectedToolInfo(BaseModel):
    """Informações de uma ferramenta selecionada."""
    tool_id: str
    tool_name: str
    category: str
    execution_order: int
    fitness_score: float
    reasoning: str


class ToolSelectionAPIResponse(BaseModel):
    """Response da seleção de ferramentas via API."""
    request_id: str
    selection_method: str
    selected_tools: List[SelectedToolInfo]
    total_fitness_score: float
    convergence_time_ms: int
    cached: bool


# ===== Dependency Injection =====

genetic_selector: Optional[GeneticToolSelector] = None


def set_genetic_selector(selector: GeneticToolSelector):
    """Injeta selector no router."""
    global genetic_selector
    genetic_selector = selector


# ===== Endpoints =====

@router.post("", response_model=ToolSelectionAPIResponse)
async def select_tools(request: ToolSelectionAPIRequest):
    """
    Executa seleção de ferramentas de forma síncrona.

    Este endpoint fornece alternativa síncrona ao fluxo Kafka.
    Útil para integrações diretas via REST API.

    Args:
        request: Requisição de seleção

    Returns:
        Resposta com ferramentas selecionadas
    """
    if not genetic_selector:
        raise HTTPException(
            status_code=500,
            detail="Genetic selector not initialized"
        )

    try:
        # Converter API request para ToolSelectionRequest interno
        # Coerce artifact_type to enum
        try:
            artifact_type_enum = ArtifactType(request.artifact_type.upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid artifact_type: {request.artifact_type}. Valid: {[t.value for t in ArtifactType]}"
            )

        # Convert constraints dict to SelectionConstraints
        constraints = SelectionConstraints(**request.constraints) if request.constraints else SelectionConstraints()

        selection_request = ToolSelectionRequest(
            request_id=request.request_id,
            ticket_id=request.ticket_id or "api-direct",
            plan_id=request.plan_id,
            intent_id=request.intent_id,
            decision_id=None,  # Não usado em API direta
            correlation_id=request.correlation_id,
            artifact_type=artifact_type_enum,
            language=request.language or "unknown",
            complexity_score=request.complexity_score,
            required_categories=request.required_categories,
            constraints=constraints,
            context=request.context
        )

        # Executar seleção
        logger.info(
            "api_tool_selection_started",
            request_id=request.request_id,
            complexity=request.complexity_score,
            categories=request.required_categories
        )

        response = await genetic_selector.select_tools(selection_request)

        # Converter para API response
        selected_tools_info = [
            SelectedToolInfo(
                tool_id=tool.tool_id,
                tool_name=tool.tool_name,
                category=tool.category,
                execution_order=tool.execution_order,
                fitness_score=tool.fitness_score,
                reasoning=tool.reasoning
            )
            for tool in response.selected_tools
        ]

        api_response = ToolSelectionAPIResponse(
            request_id=response.request_id,
            selection_method=response.selection_method.value,
            selected_tools=selected_tools_info,
            total_fitness_score=response.total_fitness_score,
            convergence_time_ms=response.convergence_time_ms,
            cached=response.cached
        )

        logger.info(
            "api_tool_selection_completed",
            request_id=request.request_id,
            method=response.selection_method.value,
            tools_count=len(selected_tools_info),
            fitness=response.total_fitness_score
        )

        return api_response

    except Exception as e:
        logger.error(
            "api_tool_selection_failed",
            request_id=request.request_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Tool selection failed: {str(e)}"
        )


@router.get("/{request_id}/status")
async def get_selection_status(request_id: str):
    """
    Obtém status de uma seleção (placeholder para implementação futura).

    Args:
        request_id: ID da requisição

    Returns:
        Status da seleção
    """
    # TODO: Implementar consulta ao MongoDB de histórico
    raise HTTPException(
        status_code=501,
        detail="Selection status endpoint not yet implemented"
    )
