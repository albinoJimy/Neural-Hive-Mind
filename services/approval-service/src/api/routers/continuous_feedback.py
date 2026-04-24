"""
Continuous Feedback API Endpoints (EPIC 3.3 - FASE 0 IA/ML Integration)

Endpoints REST para coleta de feedback continuo para treinamento ML.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.continuous_feedback import (
    ContinuousFeedbackRequest,
    ContinuousFeedbackResponse,
    ContinuousFeedbackStats,
)
from src.security.auth import get_current_admin_user

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/feedback", tags=["continuous-feedback"])

# Referencia global para o servico
_continuous_feedback_service = None


def set_continuous_feedback_service(service):
    """Define referencia para o servico de continuous feedback"""
    global _continuous_feedback_service
    _continuous_feedback_service = service


def get_continuous_feedback_service():
    """Obtem servico de continuous feedback"""
    if _continuous_feedback_service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Servico de continuous feedback nao inicializado",
        )
    return _continuous_feedback_service


# NOTA: Endpoints especificos devem vir antes dos com path parameters
# para evitar conflitos de roteamento


@router.get("/continuous/stats", response_model=ContinuousFeedbackStats)
async def get_continuous_feedback_stats(
    user: dict = Depends(get_current_admin_user),
    service=Depends(get_continuous_feedback_service),
):
    """
    Retorna estatisticas de feedback continuo.

    Requer autenticacao JWT e role neural-hive-admin.

    Fornece metricas agregadas sobre feedbacks coletados incluindo:
    - Total de feedbacks
    - Acuracia (predicoes corretas / total)
    - Contagens por tipo (approvals correct/incorrect, rejections correct/incorrect)
    - Confianca media
    - Quantidade com features NLP enriquecidas

    Args:
        user: Usuario admin autenticado
        service: Servico de continuous feedback

    Returns:
        ContinuousFeedbackStats com metricas
    """
    logger.info("Consultando estatisticas de feedback continuo", user_id=user["user_id"])

    try:
        stats = await service.get_stats()
        return stats

    except Exception as e:
        logger.error("Erro ao obter estatisticas", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter estatisticas: {e!s}",
        )


@router.get("/continuous/health")
async def continuous_feedback_health(
    service=Depends(get_continuous_feedback_service),
):
    """
    Health check do servico de continuous feedback.

    Nao requer autenticacao.

    Returns:
        Dict com status do servico
    """
    nlp_enabled = service._nlp_extractor is not None

    return {
        "status": "healthy",
        "service": "continuous-feedback",
        "nlp_extractor_enabled": nlp_enabled,
        "collection": service.collection.name if service.collection else None,
    }


@router.get("/continuous")
async def list_continuous_feedbacks(
    limit: int = Query(default=50, ge=1, le=100, description="Limite de resultados"),
    offset: int = Query(default=0, ge=0, description="Offset para paginacao"),
    user: dict = Depends(get_current_admin_user),
    service=Depends(get_continuous_feedback_service),
):
    """
    Lista feedbacks continuos recentes.

    Requer autenticacao JWT e role neural-hive-admin.

    Args:
        limit: Limite de resultados (max 100)
        offset: Offset para paginacao
        user: Usuario admin autenticado
        service: Servico de continuous feedback

    Returns:
        Lista de feedbacks ordenados por timestamp DESC
    """
    logger.info(
        "Listando feedbacks continuos",
        user_id=user["user_id"],
        limit=limit,
        offset=offset,
    )

    try:
        feedbacks = await service.get_recent_feedbacks(limit=limit, offset=offset)
        return feedbacks

    except Exception as e:
        logger.error("Erro ao listar feedbacks", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar feedbacks: {e!s}",
        )


@router.post("/continuous", response_model=ContinuousFeedbackResponse, status_code=201)
async def submit_continuous_feedback(
    feedback: ContinuousFeedbackRequest,
    user: dict = Depends(get_current_admin_user),
    service=Depends(get_continuous_feedback_service),
):
    """
    Submete feedback continuo de predicao ML para treinamento.

    Requer autenticacao JWT e role neural-hive-admin.

    Este endpoint permite enviar feedback continuo sobre predicoes ML
    para enriquecer o dataset de treinamento. O feedback e processado
    com extracao de features NLP e enviado ao Kafka para o pipeline ML.

    Fluxo:
    1. Recebe feedback com predicao vs resultado real
    2. Extrai features NLP do texto da intent (se fornecido)
    3. Persiste no MongoDB (continuous_feedback collection)
    4. Publica no Kafka (ml.training_data topic)

    Args:
        feedback: ContinuousFeedbackRequest com dados do feedback
        user: Usuario admin autenticado
        service: Servico de continuous feedback

    Returns:
        ContinuousFeedbackResponse com resultado do processamento

    Raises:
        400: Se dados invalidos
        500: Se erro no processamento

    Example:
        ```json
        POST /api/v1/feedback/continuous
        {
            "prediction_id": "pred-12345",
            "prediction": "approve",
            "actual_result": "reject",
            "intent_text": "Adicionar novo endpoint de autenticacao",
            "plan_id": "plan-67890",
            "user_id": "user-abc",
            "confidence": 0.85,
            "model_version": "v1.2.0"
        }
        ```
    """
    logger.info(
        "Recebendo feedback continuo",
        user_id=user["user_id"],
        prediction_id=feedback.prediction_id,
        prediction=feedback.prediction,
        actual=feedback.actual_result,
    )

    # Validacao basica
    if feedback.prediction not in ("approve", "reject"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Predicao invalida: {feedback.prediction}. Deve ser 'approve' ou 'reject'",
        )

    if feedback.actual_result not in ("approve", "reject"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Resultado invalido: {feedback.actual_result}. Deve ser 'approve' ou 'reject'",
        )

    # Validar confianca se fornecida
    if feedback.confidence is not None and not (0.0 <= feedback.confidence <= 1.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Confianca deve estar entre 0.0 e 1.0, recebido: {feedback.confidence}",
        )

    try:
        result = await service.submit_feedback(feedback)
        return result

    except Exception as e:
        logger.error("Erro ao processar feedback continuo", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar feedback: {e!s}",
        )


@router.get("/continuous/{prediction_id}")
async def get_continuous_feedback(
    prediction_id: str,
    user: dict = Depends(get_current_admin_user),
    service=Depends(get_continuous_feedback_service),
):
    """
    Busca feedback continuo por prediction_id.

    Requer autenticacao JWT e role neural-hive-admin.

    Args:
        prediction_id: ID da predicao
        user: Usuario admin autenticado
        service: Servico de continuous feedback

    Returns:
        Dict com dados do feedback ou 404

    Raises:
        404: Se prediction_id nao encontrado
    """
    logger.info(
        "Buscando feedback continuo",
        user_id=user["user_id"],
        prediction_id=prediction_id,
    )

    feedback = await service.get_feedback_by_prediction_id(prediction_id)

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback nao encontrado: {prediction_id}",
        )

    return feedback
