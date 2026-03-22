"""
V3 API Routes - Hierarchical Explanation Endpoints.

REST API para explicações hierárquicas de decisões.

Explainability API v3 - Task 6
"""

import os
import structlog
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.services.hierarchical_explainer import HierarchicalExplainer
from src.services.counterfactual_analyzer import CounterfactualAnalyzer
from src.services.temporal_tracker import TemporalTracker

logger = structlog.get_logger(__name__)

# Feature flag para v3
ENABLE_V3_API = os.getenv('ENABLE_V3_API', 'false').lower() == 'true'

# Router
router = APIRouter(prefix="/api/v3", tags=["v3"])


# ========== PYDANTIC MODELS ==========

class HierarchicalBreakdownResponse(BaseModel):
    """Response para breakdown hierárquico."""

    decision_id: str = Field(..., description="ID da decisão")
    hierarchical_breakdown: Dict[str, Any] = Field(
        ...,
        description={
            "by_level": "Estatísticas por nível de senioridade",
            "dominant_level": "Nível hierárquico dominante",
            "consensus_strength": "Força do consenso (0.0 a 1.0)",
        },
    )
    explanation_quality: Optional[Dict[str, float]] = Field(
        None, description="Métricas de qualidade da explicação"
    )


class IndividualContributionsResponse(BaseModel):
    """Response para contribuições individuais."""

    decision_id: str = Field(..., description="ID da decisão")
    individual_contributions: List[Dict[str, Any]] = Field(
        ...,
        description=[
            "Lista de contribuições individuais ordenadas por rank",
            "Cada item contém: specialist_id, seniority_level, rank, contribution_score",
        ],
    )
    total_specialists: int = Field(..., description="Número total de especialistas")


class CounterfactualsResponse(BaseModel):
    """Response para análise contrafactual."""

    decision_id: str = Field(..., description="ID da decisão")
    counterfactuals: List[Dict[str, Any]] = Field(
        ...,
        description=[
            "Lista de cenários contrafactuais",
            "Cada item contém: scenario, flipped_decision, confidence_change",
        ],
    )
    sensitivity_score: float = Field(
        ...,
        description="Score de sensibilidade (0.0 a 1.0), maior = mais sensível a mudanças",
    )


class TemporalAnalysisResponse(BaseModel):
    """Response para análise temporal."""

    decision_id: str = Field(..., description="ID da decisão")
    temporal_analysis: Dict[str, Any] = Field(
        ...,
        description={
            "current_seniority": "Nível de senioridade atual",
            "history": "Lista de mudanças de senioridade",
            "trend": "Tendência (stable, upward, downward)",
            "volatility": "Volatilidade da senioridade (0.0 a 1.0)",
        },
    )


class FullExplanationResponse(BaseModel):
    """Response para explicação completa (todos os componentes)."""

    decision_id: str = Field(..., description="ID da decisão")
    hierarchical_breakdown: Dict[str, Any] = Field(
        ..., description="Breakdown hierárquico completo"
    )
    individual_contributions: List[Dict[str, Any]] = Field(
        ..., description="Contribuições individuais ordenadas"
    )
    counterfactuals: Optional[List[Dict[str, Any]]] = Field(
        None, description="Análise contrafactual (se disponível)"
    )
    temporal_analysis: Optional[Dict[str, Any]] = Field(
        None, description="Análise temporal (se disponível)"
    )
    explanation_quality: Optional[Dict[str, float]] = Field(
        None, description="Métricas de qualidade"
    )


class BatchExplanationRequest(BaseModel):
    """Request para explicação em lote."""

    decision_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Lista de IDs de decisão (máximo 10)",
    )
    include_counterfactuals: bool = Field(
        False, description="Incluir análise contrafactual"
    )
    include_temporal: bool = Field(False, description="Incluir análise temporal")


class BatchExplanationResponse(BaseModel):
    """Response para explicação em lote."""

    explanations: List[Dict[str, Any]] = Field(
        ..., description="Lista de explicações (mesma ordem da request)"
    )
    failed_ids: List[str] = Field(
        ..., description="IDs que falharam (não encontrados ou erro)"
    )
    summary: Dict[str, Any] = Field(
        ..., description="Resumo: total_requested, successful, failed"
    )


class ExplanationComparison(BaseModel):
    """Model para comparação entre decisões."""

    decision_ids: List[str] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="IDs das decisões para comparar (2 a 5)",
    )
    comparison_dimensions: List[str] = Field(
        default=["hierarchical", "individual"],
        description="Dimensões para comparar: hierarchical, individual, counterfactuals, temporal",
    )


# ========== SERVICE CLASSES ==========

class V3ExplanationService:
    """
    Serviço para geração de explicações v3.

    Integra HierarchicalExplainer, CounterfactualAnalyzer e TemporalTracker.
    """

    def __init__(self, mongodb_client):
        """
        Inicializa o serviço v3.

        Args:
            mongodb_client: Cliente MongoDB para buscar dados de decisões
        """
        self.db = mongodb_client
        self.hierarchical_explainer = HierarchicalExplainer()
        self.counterfactual_analyzer = CounterfactualAnalyzer()
        self.temporal_tracker = TemporalTracker(mongo_client=mongodb_client)
        self.logger = logger

    async def _get_decision_votes(self, decision_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Busca votos da decisão no MongoDB.

        Args:
            decision_id: ID da decisão

        Returns:
            Lista de votos ou None se não encontrado
        """
        # Buscar no consensus_decisions (não explainability_ledger)
        decision = await self.db.consensus_decisions.find_one(
            {"decision_id": decision_id}
        )

        if not decision:
            return None

        # Extrair specialist_votes (consensus_decisions usa specialist_votes)
        votes = decision.get("specialist_votes", [])

        # Adicionar decision_id para cada voto se não existir
        for vote in votes:
            if "decision_id" not in vote:
                vote["decision_id"] = decision_id

        return votes

    async def get_full_explanation(
        self,
        decision_id: str,
        include_counterfactuals: bool = False,
        include_temporal: bool = False,
    ) -> Dict[str, Any]:
        """
        Gera explicação completa para uma decisão.

        Args:
            decision_id: ID da decisão
            include_counterfactuals: Incluir análise contrafactual
            include_temporal: Incluir análise temporal

        Returns:
            Dicionário com explicação completa
        """
        votes = await self._get_decision_votes(decision_id)

        if votes is None:
            return None

        # Gerar explicação hierárquica
        hierarchical_result = self.hierarchical_explainer.explain(votes)

        result = {
            "decision_id": decision_id,
            "hierarchical_breakdown": hierarchical_result["hierarchical_breakdown"],
            "individual_contributions": hierarchical_result["individual_contributions"],
        }

        # Análise contrafactual (opcional)
        if include_counterfactuals:
            counterfactuals = self.counterfactual_analyzer.generate_all_counterfactuals(votes)
            result["counterfactuals"] = list(counterfactuals["scenarios"].values())
            # sensitivity_analysis contém {"flipped_count", "sensitivity_score", "stable"}
            result["sensitivity_score"] = counterfactuals["sensitivity_analysis"].get("sensitivity_score", 0.0)

        # Análise temporal (opcional)
        if include_temporal:
            seniority_changes = await self.temporal_tracker.get_seniority_changes(decision_id)
            if seniority_changes and "history" in seniority_changes:
                result["temporal_analysis"] = {
                    "current_seniority": seniority_changes.get("current_seniority", "unknown"),
                    "history": seniority_changes.get("history", []),
                    "trend": seniority_changes.get("trend", "stable"),
                    "volatility": seniority_changes.get("volatility", 0.0),
                }

        return result

    async def get_hierarchical_breakdown(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """
        Retorna apenas o breakdown hierárquico.

        Args:
            decision_id: ID da decisão

        Returns:
            Dicionário com breakdown hierárquico ou None
        """
        votes = await self._get_decision_votes(decision_id)

        if votes is None:
            return None

        result = self.hierarchical_explainer.explain(votes)

        return {
            "decision_id": decision_id,
            "hierarchical_breakdown": result["hierarchical_breakdown"],
        }

    async def get_individual_contributions(
        self, decision_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retorna apenas as contribuições individuais.

        Args:
            decision_id: ID da decisão

        Returns:
            Dicionário com contribuições individuais ou None
        """
        votes = await self._get_decision_votes(decision_id)

        if votes is None:
            return None

        result = self.hierarchical_explainer.explain(votes)

        return {
            "decision_id": decision_id,
            "individual_contributions": result["individual_contributions"],
            "total_specialists": len(result["individual_contributions"]),
        }

    async def get_counterfactuals(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """
        Retorna apenas a análise contrafactual.

        Args:
            decision_id: ID da decisão

        Returns:
            Dicionário com contrafactuais ou None
        """
        votes = await self._get_decision_votes(decision_id)

        if votes is None:
            return None

        result = self.counterfactual_analyzer.generate_all_counterfactuals(votes)

        return {
            "decision_id": decision_id,
            "counterfactuals": list(result["scenarios"].values()),
            "sensitivity_score": result["sensitivity_analysis"].get("sensitivity_score", 0.0),
        }

    async def get_temporal_analysis(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """
        Retorna apenas a análise temporal.

        Args:
            decision_id: ID da decisão

        Returns:
            Dicionário com análise temporal ou None
        """
        # Buscar votos primeiro para obter specialist_ids
        votes = await self._get_decision_votes(decision_id)

        if not votes:
            return None

        # Extrair specialist_ids dos votos
        specialist_ids = [vote.get("specialist_id") for vote in votes if vote.get("specialist_id")]

        if not specialist_ids:
            # Fallback para specialist_type se não tiver specialist_id
            specialist_ids = [vote.get("specialist_type") for vote in votes if vote.get("specialist_type")]

        if not specialist_ids:
            return None

        # Usar get_seniority_changes com a lista de specialist_ids
        seniority_changes = await self.temporal_tracker.get_seniority_changes(specialist_ids)

        if not seniority_changes or "history" not in seniority_changes:
            # Retornar análise vazia se não houver histórico
            return {
                "decision_id": decision_id,
                "temporal_analysis": {
                    "current_seniority": "unknown",
                    "history": [],
                    "trend": "stable",
                    "volatility": 0.0,
                }
            }

        # Construir análise temporal com o formato esperado
        temporal = {
            "current_seniority": seniority_changes.get("current_seniority", "unknown"),
            "history": seniority_changes.get("history", []),
            "trend": seniority_changes.get("trend", "stable"),
            "volatility": seniority_changes.get("volatility", 0.0),
        }

        return {
            "decision_id": decision_id,
            "temporal_analysis": temporal,
        }

    async def get_batch_explanations(
        self,
        decision_ids: List[str],
        include_counterfactuals: bool = False,
        include_temporal: bool = False,
    ) -> Dict[str, Any]:
        """
        Gera explicações em lote para múltiplas decisões.

        Args:
            decision_ids: Lista de IDs de decisão
            include_counterfactuals: Incluir análise contrafactual
            include_temporal: Incluir análise temporal

        Returns:
            Dicionário com explicações e falhas
        """
        explanations = []
        failed_ids = []

        for decision_id in decision_ids:
            try:
                explanation = await self.get_full_explanation(
                    decision_id, include_counterfactuals, include_temporal
                )
                if explanation:
                    explanations.append(explanation)
                else:
                    failed_ids.append(decision_id)
            except Exception as e:
                self.logger.error(
                    "batch_explanation_error",
                    decision_id=decision_id,
                    error=str(e),
                )
                failed_ids.append(decision_id)

        return {
            "explanations": explanations,
            "failed_ids": failed_ids,
            "summary": {
                "total_requested": len(decision_ids),
                "successful": len(explanations),
                "failed": len(failed_ids),
            },
        }


# Global service instance (inicializada no main.py)
v3_service: Optional[V3ExplanationService] = None


def get_v3_service() -> V3ExplanationService:
    """Retorna a instância do serviço v3."""
    if v3_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="V3 service not initialized. Check ENABLE_V3_API flag.",
        )
    return v3_service


# ========== ENDPOINTS ==========

@router.get(
    "/explainability/{decision_id}",
    response_model=FullExplanationResponse,
    summary="Full explanation (v3)",
    description="Returns complete hierarchical explanation for a decision.",
)
async def get_full_explanation_endpoint(
    decision_id: str,
    include_counterfactuals: bool = Query(
        False, description="Include counterfactual analysis"
    ),
    include_temporal: bool = Query(False, description="Include temporal analysis"),
):
    """
    Retorna explicação completa hierárquica.

    Inclui breakdown hierárquico e contribuições individuais.
    Opcionalmente inclui análise contrafactual e temporal.
    """
    service = get_v3_service()

    result = await service.get_full_explanation(
        decision_id, include_counterfactuals, include_temporal
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision not found: {decision_id}",
        )

    return FullExplanationResponse(**result)


@router.get(
    "/explainability/{decision_id}/hierarchical",
    response_model=HierarchicalBreakdownResponse,
    summary="Hierarchical breakdown only (v3)",
    description="Returns only the hierarchical breakdown for a decision.",
)
async def get_hierarchical_breakdown_endpoint(decision_id: str):
    """
    Retorna apenas o breakdown hierárquico.

    Inclui estatísticas por nível de senioridade, nível dominante
    e força de consenso.
    """
    service = get_v3_service()

    result = await service.get_hierarchical_breakdown(decision_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision not found: {decision_id}",
        )

    return HierarchicalBreakdownResponse(**result)


@router.get(
    "/explainability/{decision_id}/individual",
    response_model=IndividualContributionsResponse,
    summary="Individual contributions only (v3)",
    description="Returns only individual specialist contributions for a decision.",
)
async def get_individual_contributions_endpoint(decision_id: str):
    """
    Retorna apenas as contribuições individuais.

    Lista de especialistas ordenados por rank de influência.
    """
    service = get_v3_service()

    result = await service.get_individual_contributions(decision_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision not found: {decision_id}",
        )

    return IndividualContributionsResponse(**result)


@router.get(
    "/explainability/{decision_id}/counterfactuals",
    response_model=CounterfactualsResponse,
    summary="Counterfactuals only (v3)",
    description="Returns only counterfactual analysis for a decision.",
)
async def get_counterfactuals_endpoint(decision_id: str):
    """
    Retorna apenas a análise contrafactual.

    Cenários "e se" mostrando como mudanças poderiam alterar a decisão.
    """
    service = get_v3_service()

    result = await service.get_counterfactuals(decision_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision not found: {decision_id}",
        )

    return CounterfactualsResponse(**result)


@router.get(
    "/explainability/{decision_id}/temporal",
    response_model=TemporalAnalysisResponse,
    summary="Temporal analysis only (v3)",
    description="Returns only temporal analysis for a decision.",
)
async def get_temporal_analysis_endpoint(decision_id: str):
    """
    Retorna apenas a análise temporal.

    Histórico de mudanças de senioridade dos especialistas.
    """
    service = get_v3_service()

    result = await service.get_temporal_analysis(decision_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision not found or no temporal data: {decision_id}",
        )

    return TemporalAnalysisResponse(**result)


@router.post(
    "/explainability/batch",
    response_model=BatchExplanationResponse,
    summary="Batch comparison (v3)",
    description="Generate explanations for multiple decisions at once.",
)
async def batch_explanation_endpoint(request: BatchExplanationRequest):
    """
    Gera explicações em lote para múltiplas decisões.

    Útil para comparar decisões ou gerar relatórios.
    """
    service = get_v3_service()

    result = await service.get_batch_explanations(
        request.decision_ids,
        request.include_counterfactuals,
        request.include_temporal,
    )

    return BatchExplanationResponse(**result)


# ========== HELPER FUNCTIONS ==========

def create_v3_router(mongodb_client) -> APIRouter:
    """
    Factory function para criar o router v3 com service inicializado.

    Args:
        mongodb_client: Cliente MongoDB

    Returns:
        APIRouter configurado
    """
    global v3_service
    v3_service = V3ExplanationService(mongodb_client)
    return router
