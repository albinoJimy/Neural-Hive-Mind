"""
API de alertas proativos para SLA Management System.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from ..clients.postgresql_client import PostgreSQLClient
from ..models.alert_rule import (
    Alert,
    AlertChannel,
    AlertCondition,
    AlertConditionType,
    AlertRule,
    AlertSeverity,
)
from ..services.alert_engine import AlertEngine

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

# Referência global para o serviço
_alert_engine: Optional[AlertEngine] = None
_postgresql_client: Optional[PostgreSQLClient] = None


def set_alert_engine(engine: AlertEngine):
    """Define referência para o motor de alertas."""
    global _alert_engine
    _alert_engine = engine


def get_alert_engine() -> AlertEngine:
    """Obtém motor de alertas."""
    if _alert_engine is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Motor de alertas não inicializado",
        )
    return _alert_engine


def set_postgresql_client(client: PostgreSQLClient):
    """Define referência para o cliente PostgreSQL."""
    global _postgresql_client
    _postgresql_client = client


def get_postgresql_client() -> PostgreSQLClient:
    """Obtém cliente PostgreSQL."""
    if _postgresql_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PostgreSQL client não inicializado",
        )
    return _postgresql_client


# -------------------------------------------------------------------------
# Requisição/Resposta Models
# -------------------------------------------------------------------------


class CreateAlertRuleRequest(BaseModel):
    """Request para criar regra de alerta."""

    name: str
    description: Optional[str] = None
    enabled: bool = True
    condition_type: AlertConditionType
    threshold: float
    window_hours: Optional[int] = None
    service_name: Optional[str] = None
    slo_id: Optional[str] = None
    severity: AlertSeverity
    channels: List[AlertChannel]
    channel_config: dict = {}
    cooldown_minutes: int = 30


class UpdateAlertRuleRequest(BaseModel):
    """Request para atualizar regra de alerta."""

    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    condition_type: Optional[AlertConditionType] = None
    threshold: Optional[float] = None
    window_hours: Optional[int] = None
    service_name: Optional[str] = None
    slo_id: Optional[str] = None
    severity: Optional[AlertSeverity] = None
    channels: Optional[List[AlertChannel]] = None
    channel_config: Optional[dict] = None
    cooldown_minutes: Optional[int] = None


class AcknowledgeAlertRequest(BaseModel):
    """Request para reconhecer alerta."""

    acknowledged_by: str


class ResolveAlertRequest(BaseModel):
    """Request para resolver alerta."""

    resolved_by: str


# -------------------------------------------------------------------------
# Endpoints de Regras de Alerta
# -------------------------------------------------------------------------


@router.post("/rules", response_model=AlertRule, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(request: CreateAlertRuleRequest):
    """
    Cria uma nova regra de alerta.

    A regra será avaliada continuamente pelo motor de alertas.
    Quando a condição for atendida, alertas serão disparados
    para os canais configurados.
    """
    from datetime import datetime, timezone

    condition = AlertCondition(
        condition_type=request.condition_type,
        threshold=request.threshold,
        window_hours=request.window_hours,
        service_name=request.service_name,
        slo_id=request.slo_id,
    )

    rule = AlertRule(
        rule_id="",  # Será gerado pelo serviço
        name=request.name,
        description=request.description,
        enabled=request.enabled,
        condition=condition,
        severity=request.severity,
        channels=request.channels,
        channel_config=request.channel_config,
        cooldown_minutes=request.cooldown_minutes,
        created_at=datetime.now(timezone.utc),
    )

    engine = get_alert_engine()
    created = await engine.create_rule(rule)
    return created


@router.get("/rules", response_model=List[AlertRule])
async def list_alert_rules():
    """Lista todas as regras de alerta."""
    engine = get_alert_engine()
    return await engine.list_rules()


@router.get("/rules/{rule_id}", response_model=AlertRule)
async def get_alert_rule(rule_id: str):
    """Busca uma regra de alerta por ID."""
    engine = get_alert_engine()
    rule = await engine.get_rule(rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Regra {rule_id} não encontrada"
        )
    return rule


@router.put("/rules/{rule_id}", response_model=AlertRule)
async def update_alert_rule(rule_id: str, request: UpdateAlertRuleRequest):
    """Atualiza uma regra de alerta existente."""
    engine = get_alert_engine()

    # Converter request para dict, removendo None values
    updates = request.model_dump(exclude_unset=True)

    # Se condition_type fornecido, criar AlertCondition
    if "condition_type" in updates:
        # Buscar regra atual para manter valores não fornecidos
        current_rule = await engine.get_rule(rule_id)
        if not current_rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Regra {rule_id} não encontrada"
            )

        condition_data = {
            "condition_type": updates.pop("condition_type"),
            "threshold": updates.pop("threshold", current_rule.condition.threshold),
            "window_hours": updates.pop("window_hours", current_rule.condition.window_hours),
            "service_name": updates.pop("service_name", current_rule.condition.service_name),
            "slo_id": updates.pop("slo_id", current_rule.condition.slo_id),
        }
        updates["condition"] = AlertCondition(**condition_data)

    updated = await engine.update_rule(rule_id, updates)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Regra {rule_id} não encontrada"
        )
    return updated


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(rule_id: str):
    """Remove uma regra de alerta."""
    engine = get_alert_engine()
    success = await engine.delete_rule(rule_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Regra {rule_id} não encontrada"
        )


# -------------------------------------------------------------------------
# Endpoints de Alertas
# -------------------------------------------------------------------------


@router.get("", response_model=List[Alert])
async def list_alerts(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    severity: Optional[AlertSeverity] = None,
    slo_id: Optional[str] = None,
    service_name: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    resolved: Optional[bool] = None,
):
    """
    Lista alertas com filtros opcionais.

    Retorna histórico de alertas disparados, podendo filtrar por:
    - severidade
    - SLO
    - serviço
    - status de reconhecimento
    - status de resolução
    """
    client = get_postgresql_client()
    return await client.list_alerts(
        limit=limit,
        offset=offset,
        severity=severity,
        slo_id=slo_id,
        service_name=service_name,
        acknowledged=acknowledged,
        resolved=resolved,
    )


@router.get("/{alert_id}", response_model=Alert)
async def get_alert(alert_id: str):
    """Busca um alerta por ID."""
    client = get_postgresql_client()
    alert = await client.get_alert(alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Alerta {alert_id} não encontrado"
        )
    return alert


@router.post("/{alert_id}/acknowledge", response_model=Alert)
async def acknowledge_alert(alert_id: str, request: AcknowledgeAlertRequest):
    """
    Reconhece um alerta.

    Marca o alerta como reconhecido pelo usuário especificado.
    Isso indica que o time está ciente do alerta e está trabalhando nele.
    """
    client = get_postgresql_client()
    success = await client.acknowledge_alert(alert_id, request.acknowledged_by)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Alerta {alert_id} não encontrado"
        )
    alert = await client.get_alert(alert_id)
    return alert


@router.post("/{alert_id}/resolve", response_model=Alert)
async def resolve_alert(alert_id: str, request: ResolveAlertRequest):
    """
    Marca alerta como resolvido.

    Indica que a condição que causou o alerta foi corrigida.
    """
    client = get_postgresql_client()
    success = await client.resolve_alert(alert_id, request.resolved_by)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Alerta {alert_id} não encontrado"
        )
    alert = await client.get_alert(alert_id)
    return alert


@router.get("/statistics/summary", response_model=dict)
async def get_alert_statistics():
    """
    Retorna estatísticas de alertas.

    Inclui:
    - Total de alertas
    - Contagem por severidade
    - Contagem por canal
    - Alertas recentes
    """
    client = get_postgresql_client()
    stats = await client.get_alert_statistics()

    # Adicionar estatísticas de regras
    engine = get_alert_engine()
    rules = await engine.list_rules()

    stats.update(
        {
            "total_rules": len(rules),
            "active_rules": sum(1 for r in rules if r.enabled),
        }
    )

    return stats
