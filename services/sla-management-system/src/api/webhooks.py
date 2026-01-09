"""
Router FastAPI para webhooks (Alertmanager).
"""

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import structlog

from ..services.slo_manager import SLOManager
from ..services.budget_calculator import BudgetCalculator
from ..services.policy_enforcer import PolicyEnforcer
from ..clients.postgresql_client import PostgreSQLClient


router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = structlog.get_logger(__name__)


# Request models
class AlertmanagerAlert(BaseModel):
    status: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    startsAt: str
    endsAt: str
    generatorURL: str


class AlertmanagerWebhook(BaseModel):
    version: str
    groupKey: str
    status: str
    receiver: str
    groupLabels: Dict[str, str]
    commonLabels: Dict[str, str]
    commonAnnotations: Dict[str, str]
    externalURL: str
    alerts: List[AlertmanagerAlert]


# Response model
class WebhookResponse(BaseModel):
    message: str
    alerts_processed: int


# Dependency injection
def get_slo_manager() -> SLOManager:
    """
    Retorna a instância de SLOManager do estado da aplicação.

    Em produção, é sobrescrito via dependency_overrides do FastAPI em main.py.
    Este fallback acessa o singleton do módulo diretamente.
    """
    from .. import main
    if main.slo_manager is None:
        raise HTTPException(
            status_code=503,
            detail="SLOManager não inicializado. Serviço iniciando."
        )
    return main.slo_manager


def get_budget_calculator() -> BudgetCalculator:
    """
    Retorna a instância de BudgetCalculator do estado da aplicação.

    Em produção, é sobrescrito via dependency_overrides do FastAPI em main.py.
    Este fallback acessa o singleton do módulo diretamente.
    """
    from .. import main
    if main.budget_calculator is None:
        raise HTTPException(
            status_code=503,
            detail="BudgetCalculator não inicializado. Serviço iniciando."
        )
    return main.budget_calculator


def get_policy_enforcer() -> PolicyEnforcer:
    """
    Retorna a instância de PolicyEnforcer do estado da aplicação.

    Em produção, é sobrescrito via dependency_overrides do FastAPI em main.py.
    Este fallback acessa o singleton do módulo diretamente.
    """
    from .. import main
    if main.policy_enforcer is None:
        raise HTTPException(
            status_code=503,
            detail="PolicyEnforcer não inicializado. Serviço iniciando."
        )
    return main.policy_enforcer


def get_postgresql_client() -> PostgreSQLClient:
    """
    Retorna a instância de PostgreSQLClient do estado da aplicação.

    Em produção, é sobrescrito via dependency_overrides do FastAPI em main.py.
    Este fallback acessa o singleton do módulo diretamente.
    """
    from .. import main
    if main.postgresql_client is None:
        raise HTTPException(
            status_code=503,
            detail="PostgreSQLClient não inicializado. Serviço iniciando."
        )
    return main.postgresql_client


@router.post("/alertmanager", response_model=WebhookResponse)
async def alertmanager_webhook(
    payload: AlertmanagerWebhook,
    slo_manager: SLOManager = Depends(get_slo_manager),
    budget_calculator: BudgetCalculator = Depends(get_budget_calculator),
    policy_enforcer: PolicyEnforcer = Depends(get_policy_enforcer),
    pg_client: PostgreSQLClient = Depends(get_postgresql_client)
):
    """
    Webhook receiver para Alertmanager.

    Processa alertas de SLO violations e aciona políticas de freeze se necessário.
    """
    alerts_processed = 0

    logger.info(
        "alertmanager_webhook_received",
        status=payload.status,
        alerts_count=len(payload.alerts)
    )

    for alert in payload.alerts:
        # Filtrar alertas com label slo
        slo_label = alert.labels.get("slo")
        if not slo_label:
            continue

        # Processar alerta de SLO
        try:
            # Buscar SLO correspondente
            slos = await slo_manager.list_slos({"service_name": alert.labels.get("service", "")})
            slo = next((s for s in slos if s.name == slo_label), None)

            if not slo:
                logger.warning(
                    "slo_not_found_for_alert",
                    slo_label=slo_label,
                    service=alert.labels.get("service")
                )
                continue

            # Buscar budget atual
            budget = await budget_calculator.get_budget(slo.slo_id, use_cache=False)

            if budget:
                # Incrementar contador de violações
                # TODO: Implementar update de violations_count

                # Avaliar políticas de freeze
                freeze_events = await policy_enforcer.evaluate_policies(budget)

                if freeze_events:
                    logger.info(
                        "freeze_triggered_by_alert",
                        slo_id=slo.slo_id,
                        service=slo.service_name,
                        freeze_events=len(freeze_events)
                    )

            alerts_processed += 1

            logger.info(
                "alert_processed",
                alertname=alert.labels.get("alertname"),
                slo=slo_label,
                severity=alert.labels.get("severity"),
                status=alert.status
            )

        except Exception as e:
            logger.error(
                "alert_processing_failed",
                slo_label=slo_label,
                error=str(e)
            )
            continue

    return WebhookResponse(
        message="Webhook processed",
        alerts_processed=alerts_processed
    )
