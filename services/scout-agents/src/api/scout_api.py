"""
ScoutAPI - API REST para interação com Scout Agents.

Responsável por:
- Endpoint de health check
- Criar novas explorações
- Recuperar status de explorações
- Listar explorações
- Obter estatísticas
- Deletar explorações
"""

from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

logger = structlog.get_logger()


# Request/Response Models
class ExplorationRequest(BaseModel):
    """Modelo de requisição para criar exploração."""

    plan_id: str = Field(..., description="ID do plano cognitivo")
    intent_text: str = Field(..., description="Texto da intenção do usuário")
    scouts: Optional[list[str]] = Field(None, description="Scouts específicos para deployar")
    timeout_ms: Optional[int] = Field(None, description="Timeout em ms")


class ExplorationResponse(BaseModel):
    """Modelo de resposta de exploração."""

    exploration_id: str
    status: str
    created_at: Optional[str] = None


class ErrorDetail(BaseModel):
    """Modelo de detalhe de erro."""

    detail: str


class ScoutAPI:
    """API REST para Scout Agents."""

    def __init__(self, scout_orchestrator, scout_ledger):
        """
        Inicializa a API.

        Args:
            scout_orchestrator: Instância do ScoutOrchestrator
            scout_ledger: Instância do ScoutLedger
        """
        self.scout_orchestrator = scout_orchestrator
        self.scout_ledger = scout_ledger
        self.app = FastAPI(
            title="Scout Agents API",
            description="API para exploração e descoberta autónoma de código",
            version="1.0.0",
        )
        self._setup_routes()

    def _setup_routes(self):
        """Configura as rotas da API."""

        @self.app.get("/health")
        async def health():
            """Health check endpoint."""
            return {"status": "healthy"}

        @self.app.post("/explorations", response_model=ExplorationResponse, status_code=200)
        async def start_exploration(request: ExplorationRequest):
            """
            Inicia uma nova exploração.

            - **plan_id**: ID do plano cognitivo
            - **intent_text**: Intenção do usuário em linguagem natural
            - **scouts**: Scouts específicos (opcional)
            """
            logger.info(
                "start_exploration_requested",
                plan_id=request.plan_id,
                intent_text=request.intent_text,
            )

            # Iniciar exploração via orchestrator
            exploration = await self.scout_orchestrator.coordinate_exploration(
                plan_id=request.plan_id,
                intent_text=request.intent_text,
                scouts=request.scouts,
                timeout_ms=request.timeout_ms,
            )

            # Salvar no ledger
            await self.scout_ledger.save_exploration(exploration)

            logger.info("exploration_started", exploration_id=exploration["exploration_id"])

            return ExplorationResponse(**exploration)

        @self.app.get("/explorations/{exploration_id}", response_model=dict)
        async def get_exploration(exploration_id: str):
            """Recupera uma exploração por ID."""
            exploration = await self.scout_ledger.get_exploration(exploration_id)

            if not exploration:
                raise HTTPException(status_code=404, detail="Exploration not found")

            return exploration

        @self.app.get("/explorations")
        async def list_explorations(
            plan_id: Optional[str] = Query(None),
            status: Optional[str] = Query(None),
            limit: int = Query(100, le=1000),
        ):
            """Lista explorações com filtros opcionais."""
            explorations = await self.scout_ledger.list_explorations(
                plan_id=plan_id, status=status, limit=limit
            )

            return explorations

        @self.app.get("/stats")
        async def get_stats(plan_id: Optional[str] = Query(None)):
            """Retorna estatísticas de explorações."""
            stats = await self.scout_ledger.get_exploration_stats(plan_id=plan_id)
            return stats

        @self.app.delete("/explorations/{exploration_id}", status_code=204)
        async def delete_exploration(exploration_id: str):
            """Deleta uma exploração."""
            deleted = await self.scout_ledger.delete_exploration(exploration_id)

            if not deleted:
                raise HTTPException(status_code=404, detail="Exploration not found")

            return None
