"""
API Endpoints para GDPR Right to Erasure
"""

import hashlib

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.erasure import (
    DataType,
    ErasureRequestInput,
    ErasureScope,
    ErasureStatusResponse,
    VerificationRequest,
)
from src.services.erasure_service import ErasureService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/gdpr", tags=["gdpr"])

# Referencia global para o servico
_erasure_service = None


def set_erasure_service(service: ErasureService):
    """Define referencia para o servico de exclusao"""
    global _erasure_service
    _erasure_service = service


def get_erasure_service() -> ErasureService:
    """Obtem servico de exclusao"""
    if _erasure_service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Servico de exclusao nao inicializado",
        )
    return _erasure_service


@router.post("/erasure", status_code=201, response_model=dict)
async def create_erasure_request(
    request_input: ErasureRequestInput,
    user_id: str = Query(..., description="ID do usuario solicitante"),
    service: ErasureService = Depends(get_erasure_service),
):
    """
    Cria solicitacao de exclusao de dados (GDPR Artigo 17).

    Requer autenticacao previa (via Keycloak).

    Envia email com token de verificacao para confirmar a solicitacao.
    O usuario deve clicar no link ou fornecer o token para prosseguir.

    Args:
        request_input: Dados da solicitacao
        user_id: ID do usuario autenticado
        service: Servico de exclusao

    Returns:
        Dict com request_id e instrucoes de verificacao

    Raises:
        400: Se dados invalidos
        409: Se ja existe solicitacao em andamento
        500: Se erro no processamento
    """
    user_id_hash = hashlib.sha256(user_id.encode()).hexdigest()[:16]
    logger.info("Recebendo solicitacao de exclusao", user_id_hash=user_id_hash)

    try:
        request = await service.create_erasure_request(
            user_id=user_id, input_data=request_input.model_dump()
        )

        return {
            "request_id": request.request_id,
            "status": request.status,
            "message": "Solicitacao criada. Enviamos um email com instrucoes de verificacao.",
            "expires_at": request.expires_at,
        }

    except ValueError as e:
        if "ja existe" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(e)
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao criar solicitacao", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar solicitacao: {e!s}",
        )


@router.post("/erasure/{request_id}/verify")
async def verify_erasure_request(
    request_id: str,
    verification: VerificationRequest,
    service: ErasureService = Depends(get_erasure_service),
):
    """
    Verifica solicitacao usando token enviado por email.

    Args:
        request_id: ID da solicitacao
        verification: Token de verificacao
        service: Servico de exclusao

    Returns:
        Dict com status atualizado

    Raises:
        400: Se token invalido
        404: Se solicitacao nao encontrada
    """
    logger.info("Verificando solicitacao", request_id=request_id)

    try:
        request = await service.verify_erasure_request(request_id, verification.token)

        return {
            "request_id": request.request_id,
            "status": request.status,
            "message": "Solicitacao verificada. O processamento iniciara em breve.",
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao verificar solicitacao", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao verificar: {e!s}",
        )


@router.post("/erasure/{request_id}/process")
async def process_erasure_request(
    request_id: str,
    service: ErasureService = Depends(get_erasure_service),
):
    """
    Inicia o processamento de uma solicitacao verificada.

    Esta operacao e geralmente acionada automaticamente apos a verificacao,
    mas pode ser chamada manualmente para reprocessar.

    Args:
        request_id: ID da solicitacao
        service: Servico de exclusao

    Returns:
        Dict com status do processamento

    Raises:
        400: Se solicitacao nao verificada
        404: Se solicitacao nao encontrada
    """
    logger.info("Iniciando processamento", request_id=request_id)

    try:
        request = await service.process_erasure_request(request_id)

        return {
            "request_id": request.request_id,
            "status": request.status,
            "message": "Processamento iniciado. Enviando comandos para os servicos.",
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao processar solicitacao", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar: {e!s}",
        )


@router.get("/erasure/{request_id}", response_model=ErasureStatusResponse)
async def get_erasure_status(
    request_id: str,
    service: ErasureService = Depends(get_erasure_service),
):
    """
    Consulta status de uma solicitacao de exclusao.

    Args:
        request_id: ID da solicitacao
        service: Servico de exclusao

    Returns:
        ErasureStatusResponse com detalhes do status

    Raises:
        404: Se solicitacao nao encontrada
    """
    logger.info("Consultando status", request_id=request_id)

    try:
        status_data = await service.get_erasure_status(request_id)
        return ErasureStatusResponse(**status_data)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("Erro ao consultar status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao consultar status: {e!s}",
        )


@router.get("/erasure")
async def list_erasure_requests(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: ErasureScope = Query(default=None),
    service: ErasureService = Depends(get_erasure_service),
):
    """
    Lista solicitacoes de exclusao (apenas admin).

    Requer role neural-hive-admin.

    Args:
        limit: Limite de resultados
        offset: Offset para paginacao
        status_filter: Filtro opcional por status
        service: Servico de exclusao

    Returns:
        Lista de solicitacoes
    """
    # TODO: Adicionar verificacao de role admin
    query = {}
    if status_filter:
        query["status"] = status_filter

    cursor = (
        service.collection.find(query)
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
    )
    requests = await cursor.to_list(length=limit)

    # Remover campos sensíveis
    safe_requests = []
    for req in requests:
        req.pop("verification_token", None)
        req.pop("user_id", None)
        safe_requests.append(req)

    return {
        "total": len(safe_requests),
        "requests": safe_requests,
    }
