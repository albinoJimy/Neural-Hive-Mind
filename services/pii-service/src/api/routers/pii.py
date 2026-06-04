"""Router REST para PII Service."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from src.config.settings import get_settings
from src.models.pii import MaskStrategy, PIIType
from src.services.pii_service import get_pii_service

pii_router = APIRouter(prefix="/api/v1/pii", tags=["PII"])
settings = get_settings()
pii_service = get_pii_service()


# Request/Response Models


class DetectRequest(BaseModel):
    """Request para detecção de PII."""

    text: str = Field(..., description="Texto para analisar", min_length=1)
    types: list[PIIType] | None = Field(None, description="Tipos de PII a detectar")
    min_confidence: float = Field(0.0, ge=0.0, le=1.0, description="Confiança mínima")
    language: str = Field("pt", description="Idioma do texto")


class DetectResponse(BaseModel):
    """Response para detecção de PII."""

    detected_pii: list[dict] = Field(..., description="PII detectado (INV-2: com positions)")
    total_found: int = Field(..., description="Total de PII encontrados")
    count_by_type: dict[str, int] = Field(..., description="Contagem por tipo")
    detected_at: str = Field(..., description="Timestamp da detecção")


class MaskRequest(BaseModel):
    """Request para mascaramento de PII."""

    text: str = Field(..., description="Texto para mascarar", min_length=1)
    strategy: MaskStrategy = Field(
        MaskStrategy.MASK_PARTIAL, description="Estratégia de mascaramento"
    )
    types: list[PIIType] | None = Field(None, description="Tipos de PII a mascarar")
    enable_reversible: bool = Field(False, description="Habilitar unmask reversível (INV-14)")
    enable_audit_log: bool = Field(True, description="Habilitar audit log (INV-13)")
    language: str = Field("pt", description="Idioma do texto")
    correlation_id: str | None = Field(None, description="ID de correlação")


class MaskResponse(BaseModel):
    """Response para mascaramento de PII."""

    masked_text: str = Field(..., description="Texto mascarado")
    detected_pii: list[dict] = Field(..., description="PII detectado e mascarado")
    masks: list[dict] = Field(..., description="Detalhes dos mascaramentos")
    mask_id: str | None = Field(None, description="ID do mascaramento (para unmask)")
    masked_at: str = Field(..., description="Timestamp do mascaramento")
    audit_log_id: str | None = Field(None, description="ID do audit log (se habilitado)")


class UnmaskRequest(BaseModel):
    """Request para desmascaramento de PII."""

    mask_id: str = Field(..., description="ID do mascaramento (token criptografado)")
    masked_text: str | None = Field(None, description="Texto mascarado (para validação)")
    enable_audit_log: bool = Field(True, description="Habilitar audit log (INV-13)")
    correlation_id: str | None = Field(None, description="ID de correlação")


class UnmaskResponse(BaseModel):
    """Response para desmascaramento de PII."""

    original_text: str = Field(..., description="Texto original desmascarado")
    success: bool = Field(..., description="Indica se o unmask foi bem-sucedido")
    error_message: str | None = Field(None, description="Mensagem de erro (se falhou)")
    unmasked_at: str = Field(..., description="Timestamp do desmascaramento")
    audit_log_id: str | None = Field(None, description="ID do audit log (se habilitado)")


class CapabilitiesResponse(BaseModel):
    """Response para capacidades do serviço."""

    supported_types: list[str] = Field(..., description="Tipos de PII suportados (INV-2: 7 tipos)")
    supported_strategies: list[str] = Field(..., description="Estratégias suportadas (INV-2: 3)")
    supports_reversible_unmask: bool = Field(..., description="Suporta unmask reversível (INV-14)")
    supports_audit_log: bool = Field(..., description="Suporta audit log (INV-13)")
    version: str = Field(..., description="Versão do serviço")


# Auth dependency
async def verify_auth(
    authorization: str | None = Header(None),
) -> tuple[str, str | None, str | None]:
    """
    Verifica autenticação JWT (R-P4: JWT auth required).

    Returns:
        Tupla (requestor_id, tenant_id, user_id)
    """
    if not settings.JWT_AUTH_REQUIRED:
        return "anonymous", None, None

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )

    # TODO: Implementar validação JWT real
    # Por enquanto, extrair do header Bearer
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        # Placeholder - em produção, validar JWT
        return f"user:{token[:8]}", None, None

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authorization header",
    )


# Endpoints


@pii_router.post("/detect", response_model=DetectResponse, status_code=status.HTTP_200_OK)
async def detect_pii(
    request: DetectRequest,
    auth: tuple = Depends(verify_auth),
):
    """
    Detecta PII em texto (INV-2: 7 tipos com positions).

    Args:
        request: Request com texto e parâmetros de detecção
        auth: Tupla (requestor_id, tenant_id, user_id) da autenticação

    Returns:
        DetectResponse com PII detectado
    """
    requestor_id, tenant_id, user_id = auth

    detected = pii_service.detect(
        text=request.text,
        types_to_detect=request.types,
        min_confidence=request.min_confidence,
    )

    # Contagem por tipo
    count_by_type: dict[str, int] = {}
    for pii in detected:
        pii_type = pii.type.value
        count_by_type[pii_type] = count_by_type.get(pii_type, 0) + 1

    # Converter para dict
    detected_dicts = [
        {
            "type": pii.type.value,
            "value": pii.value,
            "start": pii.start,  # INV-2: position requerido
            "end": pii.end,  # INV-2: position requerido
            "confidence": pii.confidence,
        }
        for pii in detected
    ]

    return DetectResponse(
        detected_pii=detected_dicts,
        total_found=len(detected),
        count_by_type=count_by_type,
        detected_at=datetime.now(timezone.utc).isoformat(),
    )


@pii_router.post("/mask", response_model=MaskResponse, status_code=status.HTTP_200_OK)
async def mask_pii(
    request: MaskRequest,
    auth: tuple = Depends(verify_auth),
):
    """
    Mascara PII em texto (R-P3: 3 strategies, R-P4: audit log).

    Args:
        request: Request com texto e parâmetros de mascaramento
        auth: Tupla (requestor_id, tenant_id, user_id) da autenticação

    Returns:
        MaskResponse com texto mascarado e detalhes
    """
    requestor_id, tenant_id, user_id = auth

    masked_text, detected_pii, mask_results, mask_id = await pii_service.mask(
        text=request.text,
        strategy=request.strategy,
        types_to_mask=request.types,
        enable_reversible=request.enable_reversible,
        requestor_id=requestor_id,
        tenant_id=tenant_id,
        user_id=user_id,
        correlation_id=request.correlation_id,
        enable_audit_log=request.enable_audit_log,
    )

    # Converter para dict
    detected_dicts = [
        {
            "type": pii.type.value,
            "value": pii.value,
            "start": pii.start,
            "end": pii.end,
            "confidence": pii.confidence,
            "masked_value": pii.masked_value,
        }
        for pii in detected_pii
    ]

    mask_results_dicts = [
        {
            "type": mask.type.value,
            "original_value": mask.original_value,
            "masked_value": mask.masked_value,
            "start": mask.start,
            "end": mask.end,
            "strategy_used": mask.strategy_used.value,
            "mask_id": mask.mask_id,
        }
        for mask in mask_results
    ]

    return MaskResponse(
        masked_text=masked_text,
        detected_pii=detected_dicts,
        masks=mask_results_dicts,
        mask_id=mask_id,
        masked_at=datetime.now(timezone.utc).isoformat(),
        audit_log_id=None,  # TODO: retornar ID do audit log
    )


@pii_router.post("/unmask", response_model=UnmaskResponse, status_code=status.HTTP_200_OK)
async def unmask_pii(
    request: UnmaskRequest,
    auth: tuple = Depends(verify_auth),
):
    """
    Remove máscara de PII (INV-14: AES-256-GCM reversible unmask).

    Args:
        request: Request com mask_id e parâmetros
        auth: Tupla (requestor_id, tenant_id, user_id) da autenticação

    Returns:
        UnmaskResponse com texto original
    """
    requestor_id, tenant_id, user_id = auth

    original_text, success, error_message = await pii_service.unmask(
        mask_id=request.mask_id,
        masked_text=request.masked_text,
        requestor_id=requestor_id,
        tenant_id=tenant_id,
        user_id=user_id,
        correlation_id=request.correlation_id,
        enable_audit_log=request.enable_audit_log,
    )

    return UnmaskResponse(
        original_text=original_text,
        success=success,
        error_message=error_message,
        unmasked_at=datetime.now(timezone.utc).isoformat(),
        audit_log_id=None,  # TODO: retornar ID do audit log
    )


@pii_router.get(
    "/capabilities", response_model=CapabilitiesResponse, status_code=status.HTTP_200_OK
)
async def get_capabilities():
    """
    Retorna capacidades do serviço PII.

    Returns:
        CapabilitiesResponse com tipos, estratégias e features suportadas
    """
    capabilities = pii_service.get_capabilities()

    return CapabilitiesResponse(**capabilities)
