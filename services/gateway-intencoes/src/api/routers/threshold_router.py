"""Router para gerenciamento de thresholds NLU externalizados.

Autor: Neural Hive Mind
Criado: 2026-04-20 (FEAT-A-005)
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from middleware.auth_middleware import get_current_admin_user

from services.threshold_service import ThresholdService

router = APIRouter(prefix="/api/v1/thresholds", tags=["thresholds"])

# ThresholdService global (inicializado no main.py)
_threshold_service: ThresholdService | None = None


def set_threshold_service(service: ThresholdService) -> None:
    """Define o serviço de thresholds global."""
    global _threshold_service
    _threshold_service = service


def _get_threshold_service() -> ThresholdService:
    """Obtém o serviço de thresholds ou lança erro."""
    if _threshold_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ThresholdService não disponível",
        )
    return _threshold_service


async def _check_threshold_value(value: float) -> None:
    """Valida valor de threshold."""
    if value < 0 or value > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valor de threshold deve estar entre 0 e 1",
        )


@router.get("/config")
async def get_threshold_config(
    domain: str | None = None,
    tenant_id: str | None = None,
    _user: dict[str, Any] = Depends(get_current_admin_user),
):
    """Obtém configuração de threshold para domínio/tenant.

    Args:
        domain: Nome do domínio (opcional)
        tenant_id: ID do tenant (opcional)

    Returns:
        Configuração de threshold
    """
    service = _get_threshold_service()

    try:
        if domain:
            config = await service.get_config_for(domain, tenant_id)
            return {
                "domain": domain,
                "tenant_id": tenant_id,
                "config": config.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # Retornar configuração global
        return {
            "global": service.global_config.to_dict(),
            "domains": service.domain_configs,
            "tenants": service.tenant_configs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter configuração: {err}",
        ) from err


@router.get("/stats")
async def get_threshold_stats(
    _user: dict[str, Any] = Depends(get_current_admin_user),
):
    """Obtém estatísticas do serviço de thresholds.

    Returns:
        Estatísticas atuais
    """
    service = _get_threshold_service()
    return service.get_stats()


@router.put("/update")
async def update_threshold(
    domain: str | None = None,
    tenant_id: str | None = None,
    threshold_type: str = "base_threshold",
    value: float = 0.5,
    _user: dict[str, Any] = Depends(get_current_admin_user),
):
    """Atualiza threshold em runtime.

    Args:
        domain: Nome do domínio (None para global)
        tenant_id: ID do tenant (None para todos)
        threshold_type: Tipo de threshold (base_threshold, strict_threshold, etc.)
        value: Novo valor

    Returns:
        Resultado da atualização
    """
    await _check_threshold_value(value)
    service = _get_threshold_service()

    success = await service.update_threshold(domain, tenant_id, threshold_type, value)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Falha ao atualizar threshold: tipo inválido ou erro interno",
        )

    return {
        "success": True,
        "message": f"Threshold {threshold_type} atualizado para {value}",
        "domain": domain,
        "tenant_id": tenant_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/reload")
async def reload_threshold_config(
    _user: dict[str, Any] = Depends(get_current_admin_user),
):
    """Recarrega configuração de thresholds do arquivo.

    Returns:
        Resultado da recarga
    """
    service = _get_threshold_service()

    success = await service.reload()

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao recarregar configuração",
        )

    return {
        "success": True,
        "message": "Configuração recarregada com sucesso",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/export")
async def export_threshold_config(
    _user: dict[str, Any] = Depends(get_current_admin_user),
):
    """Exporta configuração atual de thresholds.

    Returns:
        Configuração completa em formato JSON
    """
    service = _get_threshold_service()
    return service.export_config()


@router.get("/check")
async def check_threshold(
    confidence: float,
    domain: str = "BUSINESS",
    tenant_id: str | None = None,
    use_strict: bool = False,
    _user: dict[str, Any] = Depends(get_current_admin_user),
):
    """Verifica se um nível de confiança atinge o threshold configurado.

    Args:
        confidence: Score de confiança para verificar
        domain: Nome do domínio
        tenant_id: ID do tenant (opcional)
        use_strict: Se deve usar threshold estrito

    Returns:
        Resultado da verificação
    """
    await _check_threshold_value(confidence)
    service = _get_threshold_service()

    threshold = await service.get_threshold_for(domain, tenant_id, use_strict)
    meets_threshold = confidence >= threshold
    auto_approve = await service.should_auto_approve(confidence, domain, tenant_id)
    requires_review = await service.requires_human_review(confidence, domain, tenant_id)
    adaptive_enabled = await service.is_adaptive_enabled(domain, tenant_id)

    return {
        "confidence": confidence,
        "threshold": threshold,
        "meets_threshold": meets_threshold,
        "auto_approve": auto_approve,
        "requires_human_review": requires_review,
        "domain": domain,
        "tenant_id": tenant_id,
        "use_strict": use_strict,
        "adaptive_enabled": adaptive_enabled,
    }


@router.get("/cache-info")
async def get_cache_info(
    _user: dict[str, Any] = Depends(get_current_admin_user),
):
    """Obtém informações sobre o cache de thresholds.

    Returns:
        Informações do cache incluindo status de expiração
    """
    service = _get_threshold_service()
    return service.get_cache_info()
