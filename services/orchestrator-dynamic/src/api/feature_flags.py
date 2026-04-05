"""
API REST para Gestão de Feature Flags Dinâmicas.

Fornece endpoints CRUD para gestão de feature flags com cache em Redis
e persistência em MongoDB. Integra com FeatureFlagService e RolloutStrategy.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Pydantic Schemas - Request/Response Models
# =============================================================================


class RolloutConfig(BaseModel):
    """Configuração de rollout para feature flag."""

    percentage: int | None = Field(
        None, ge=0, le=100, description="Percentual de tráfego (0-100)"
    )
    whitelist: list[str] | None = Field(
        default_factory=list, description="Lista de tenant_ids permitidos"
    )
    canary_list: list[str] | None = Field(
        default_factory=list, description="Lista de user_ids para canary"
    )
    namespaces: list[str] | None = Field(
        default_factory=list, description="Namespaces permitidos"
    )


class FeatureFlagCreate(BaseModel):
    """Schema para criação de feature flag."""

    flag_name: str = Field(
        ..., min_length=1, max_length=100, description="Nome único da flag"
    )
    description: str | None = Field(
        None, max_length=500, description="Descrição da flag"
    )
    enabled: bool = Field(default=False, description="Estado inicial da flag")
    rollout_strategy: str = Field(
        default="all", description="Estratégia: all, gradual, whitelist, canary"
    )
    rollout_config: RolloutConfig | None = Field(
        default_factory=RolloutConfig, description="Configuração de rollout"
    )
    created_by: str = Field(
        ..., min_length=1, max_length=100, description="Criador da flag"
    )
    owner: str | None = Field(None, max_length=100, description="Time responsável")
    tags: list[str] | None = Field(
        default_factory=list, description="Tags para organização"
    )


class FeatureFlagUpdate(BaseModel):
    """Schema para atualização de feature flag."""

    description: str | None = Field(None, max_length=500)
    enabled: bool | None = None
    rollout_strategy: str | None = Field(
        None, description="Estratégia: all, gradual, whitelist, canary"
    )
    rollout_config: RolloutConfig | None = None
    owner: str | None = Field(None, max_length=100)
    tags: list[str] | None = None


class FeatureFlagResponse(BaseModel):
    """Schema de resposta para feature flag."""

    flag_name: str
    description: str | None = None
    enabled: bool
    rollout_strategy: str
    rollout_config: dict
    created_at: str | None = None
    updated_at: str | None = None
    created_by: str
    owner: str | None = None
    tags: list[str]

    model_config = ConfigDict(from_attributes=True)


class FeatureFlagEvaluateRequest(BaseModel):
    """Schema para avaliação de flag."""

    flag_name: str = Field(..., description="Nome da flag a avaliar")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Contexto de avaliação (tenant_id, namespace, etc)",
    )


class FeatureFlagEvaluateResponse(BaseModel):
    """Schema de resposta de avaliação."""

    flag_name: str
    enabled: bool
    rollout_strategy: str
    result: bool
    context: dict[str, Any]


class BatchUpdateRequest(BaseModel):
    """Schema para batch update de flags."""

    updates: list[dict[str, Any]] = Field(
        ..., min_length=1, max_length=50, description="Lista de atualizações"
    )


class BatchUpdateResponse(BaseModel):
    """Schema de resposta de batch update."""

    updated: list[str]
    failed: list[dict[str, str]]
    total_updated: int
    total_failed: int


class ToggleResponse(BaseModel):
    """Schema de resposta de toggle."""

    flag_name: str
    enabled: bool
    previous_state: bool
    message: str


# =============================================================================
# Router Factory
# =============================================================================


def create_feature_flags_router(feature_flag_service: Any) -> APIRouter:
    """
    Cria router FastAPI para gestão de feature flags.

    Args:
        feature_flag_service: Instância de FeatureFlagService

    Returns:
        APIRouter configurado com endpoints CRUD
    """
    router = APIRouter(prefix="/api/v1/feature-flags", tags=["Feature Flags"])

    # -------------------------------------------------------------------------
    # POST /api/v1/feature-flags - Criar nova flag
    # -------------------------------------------------------------------------

    @router.post(
        "",
        response_model=FeatureFlagResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Criar feature flag",
        description="Cria uma nova feature flag com configuração de rollout.",
    )
    async def create_flag(payload: FeatureFlagCreate):
        """
        Cria uma nova feature flag.

        A flag é persistida no MongoDB e o cache é invalidado.
        """
        try:
            # Converter para dict
            flag_data = payload.model_dump(exclude_unset=True)

            # rollout_config já é dict após deserialização JSON
            # ou é RolloutConfig quando convertido via model_dump
            if flag_data.get("rollout_config"):
                # Se for um objeto RolloutConfig (não dict), converter
                if hasattr(flag_data["rollout_config"], "model_dump"):
                    flag_data["rollout_config"] = flag_data[
                        "rollout_config"
                    ].model_dump(exclude_unset=True)
                # Se já for dict, manter como está

            # Criar flag via serviço
            created = await feature_flag_service.set_flag(payload.flag_name, flag_data)

            # Buscar flag completa para resposta
            flag = await feature_flag_service.get_flag(payload.flag_name)
            if not flag:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Falha ao criar flag",
                )

            return FeatureFlagResponse(**flag)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao criar flag: {e!s}",
            )

    # -------------------------------------------------------------------------
    # GET /api/v1/feature-flags - Listar flags
    # -------------------------------------------------------------------------

    @router.get(
        "",
        response_model=list[FeatureFlagResponse],
        summary="Listar feature flags",
        description="Retorna todas as flags com opção de filtro por estado.",
    )
    async def list_flags(
        enabled: bool | None = Query(None, description="Filtrar apenas flags ativas"),
        limit: int = Query(
            100, ge=1, le=1000, description="Número máximo de resultados"
        ),
    ):
        """
        Lista todas as feature flags.

        Suporta filtro por estado (enabled) e paginação via limit.
        """
        try:
            flags = await feature_flag_service.list_flags(
                enabled_only=enabled if enabled is not None else False
            )

            # Aplicar limite
            if limit:
                flags = flags[:limit]

            return [FeatureFlagResponse(**flag) for flag in flags]

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao listar flags: {e!s}",
            )

    # -------------------------------------------------------------------------
    # GET /api/v1/feature-flags/{name} - Obter flag específica
    # -------------------------------------------------------------------------

    @router.get(
        "/{name}",
        response_model=FeatureFlagResponse,
        summary="Obter feature flag",
        description="Retorna configuração completa de uma feature flag.",
        responses={
            404: {"description": "Flag não encontrada"},
        },
    )
    async def get_flag(name: str):
        """
        Busca uma feature flag por nome.

        Retorna 404 se a flag não existir.
        """
        flag = await feature_flag_service.get_flag(name)

        if not flag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Flag '{name}' não encontrada",
            )

        return FeatureFlagResponse(**flag)

    # -------------------------------------------------------------------------
    # PUT /api/v1/feature-flags/{name} - Atualizar flag
    # -------------------------------------------------------------------------

    @router.put(
        "/{name}",
        response_model=FeatureFlagResponse,
        summary="Atualizar feature flag",
        description="Atualiza configuração de uma feature flag existente.",
        responses={
            404: {"description": "Flag não encontrada"},
        },
    )
    async def update_flag(name: str, payload: FeatureFlagUpdate):
        """
        Atualiza uma feature flag existente.

        Apenas os campos fornecidos são atualizados (PATCH semantics).
        O cache é invalidado automaticamente.
        """
        # Verificar se flag existe
        existing = await feature_flag_service.get_flag(name)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Flag '{name}' não encontrada",
            )

        try:
            # Converter para dict
            update_data = payload.model_dump(exclude_unset=True, exclude_none=True)

            # rollout_config já é dict após deserialização JSON
            # ou é RolloutConfig quando convertido via model_dump
            if update_data.get("rollout_config"):
                # Se for um objeto RolloutConfig (não dict), converter
                if hasattr(update_data["rollout_config"], "model_dump"):
                    update_data["rollout_config"] = update_data[
                        "rollout_config"
                    ].model_dump(exclude_unset=True)
                # Se já for dict, manter como está

            # Mesclar com dados existentes
            flag_data = {**existing, **update_data}

            # Atualizar via serviço
            await feature_flag_service.set_flag(name, flag_data)

            # Buscar flag atualizada
            updated = await feature_flag_service.get_flag(name)

            return FeatureFlagResponse(**updated)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao atualizar flag: {e!s}",
            )

    # -------------------------------------------------------------------------
    # DELETE /api/v1/feature-flags/{name} - Deletar flag
    # -------------------------------------------------------------------------

    @router.delete(
        "/{name}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Deletar feature flag",
        description="Remove uma feature flag permanentemente.",
        responses={
            404: {"description": "Flag não encontrada"},
        },
    )
    async def delete_flag(name: str):
        """
        Remove uma feature flag.

        A flag é removida do MongoDB e o cache é invalidado.
        """
        deleted = await feature_flag_service.delete_flag(name)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Flag '{name}' não encontrada",
            )

    # -------------------------------------------------------------------------
    # POST /api/v1/feature-flags/{name}/evaluate - Avaliar flag
    # -------------------------------------------------------------------------

    @router.post(
        "/{name}/evaluate",
        response_model=FeatureFlagEvaluateResponse,
        summary="Avaliar feature flag",
        description="Avalia se uma flag está ativa para o contexto fornecido.",
    )
    async def evaluate_flag(name: str, context: dict[str, Any] = None):
        """
        Avalia se uma feature flag está ativa para um contexto.

        O contexto deve conter informações como tenant_id, namespace, etc.
        dependendo da estratégia de rollout configurada.
        """
        flag = await feature_flag_service.get_flag(name)

        if not flag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Flag '{name}' não encontrada",
            )

        # Avaliar flag
        result = await feature_flag_service.evaluate_flag(name, context or {})

        return FeatureFlagEvaluateResponse(
            flag_name=name,
            enabled=flag.get("enabled", False),
            rollout_strategy=flag.get("rollout_strategy", "all"),
            result=result,
            context=context or {},
        )

    # -------------------------------------------------------------------------
    # POST /api/v1/feature-flags/{name}/toggle - Toggle flag
    # -------------------------------------------------------------------------

    @router.post(
        "/{name}/toggle",
        response_model=ToggleResponse,
        summary="Toggle feature flag",
        description="Ativa ou desativa uma feature flag rapidamente.",
        responses={
            404: {"description": "Flag não encontrada"},
        },
    )
    async def toggle_flag(name: str):
        """
        Alterna o estado de uma feature flag (enabled <-> disabled).

        Operação atômica que apenas inverte o estado enabled.
        """
        flag = await feature_flag_service.get_flag(name)

        if not flag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Flag '{name}' não encontrada",
            )

        previous_state = flag.get("enabled", False)
        new_state = not previous_state

        # Atualizar estado
        flag["enabled"] = new_state
        await feature_flag_service.set_flag(name, flag)

        action = "ativada" if new_state else "desativada"

        return ToggleResponse(
            flag_name=name,
            enabled=new_state,
            previous_state=previous_state,
            message=f"Flag '{name}' foi {action} com sucesso.",
        )

    # -------------------------------------------------------------------------
    # POST /api/v1/feature-flags/batch-update - Batch update
    # -------------------------------------------------------------------------

    @router.post(
        "/batch-update",
        response_model=BatchUpdateResponse,
        summary="Atualizar múltiplas flags",
        description="Atualiza múltiplas flags em uma única requisição.",
    )
    async def batch_update(payload: BatchUpdateRequest):
        """
        Atualiza múltiplas feature flags em batch.

        Processa cada atualização sequencialmente e retorna resumo.
        """
        updated = []
        failed = []

        for update in payload.updates:
            flag_name = update.get("flag_name")
            if not flag_name:
                failed.append(
                    {"error": "flag_name não fornecido", "update": str(update)}
                )
                continue

            try:
                # Verificar se flag existe
                existing = await feature_flag_service.get_flag(flag_name)
                if not existing:
                    failed.append(
                        {"flag_name": flag_name, "error": "Flag não encontrada"}
                    )
                    continue

                # Atualizar
                flag_data = {**existing, **update}
                await feature_flag_service.set_flag(flag_name, flag_data)
                updated.append(flag_name)

            except Exception as e:
                failed.append({"flag_name": flag_name, "error": str(e)})

        return BatchUpdateResponse(
            updated=updated,
            failed=failed,
            total_updated=len(updated),
            total_failed=len(failed),
        )

    return router
