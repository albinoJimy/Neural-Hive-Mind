"""
Activity para verificações proativas de SLA durante execução do workflow.

Este módulo implementa atividade Temporal para monitoramento proativo de SLA,
permitindo detectar problemas de deadline e budget antes da consolidação final.

NOTA DE PERFORMANCE:
    Esta activity cria/fecha um novo SLAMonitor em cada execução. Em ambientes
    de alto volume, isso pode gerar overhead significativo devido a:
    - Criação de httpx.AsyncClient novo por chamada
    - Overhead de conexão HTTP para SLA Management System
    - Overhead de conexão Redis (se disponível)

    O padrão atual foi escolhido para:
    - Simplicidade de implementação
    - Evitar estado compartilhado entre activities (thread-safety)
    - Garantir cleanup adequado de recursos

    Para ambientes de alto volume (>100 workflows/min), considere:
    - Desabilitar monitoramento proativo (SLA_PROACTIVE_MONITORING_ENABLED=false)
    - Usar apenas monitoramento reativo em C5
    - Implementar singleton com connection pooling (requer cuidado com concorrência)
"""
import time
from typing import Any, Dict, List

import structlog
from temporalio import activity

from src.config.settings import get_settings
from src.observability.metrics import get_metrics
from src.sla.sla_monitor import SLAMonitor


logger = structlog.get_logger(__name__)


@activity.defn
async def check_workflow_sla_proactive(
    workflow_id: str,
    tickets: List[Dict[str, Any]],
    checkpoint: str
) -> Dict[str, Any]:
    """
    Verifica SLA do workflow de forma proativa durante execução.

    Esta atividade realiza verificações leves de SLA em checkpoints específicos
    do workflow (pós-geração de tickets, pós-publicação) sem bloquear a execução.
    Alertas e violações formais continuam sendo tratados na consolidação (C5).

    Args:
        workflow_id: ID do workflow Temporal
        tickets: Lista de tickets gerados (format: dict com keys ticket_id, sla, etc)
        checkpoint: Identificador do checkpoint ('post_ticket_generation', 'post_ticket_publishing')

    Returns:
        Dict com resultados da verificação:
            - deadline_approaching (bool): Se deadline está próximo
            - critical_tickets (List[str]): IDs dos tickets críticos
            - remaining_seconds (float): Tempo mínimo restante
            - budget_critical (bool): Se budget está crítico (apenas checkpoint final)
            - checkpoint (str): Echo do checkpoint

    Raises:
        SLAMonitorUnavailable: Se SLA Management System indisponível (non-retryable)

    Behavior:
        - Fail-open: Retorna valores default em caso de erro
        - Não publica alertas ao Kafka (apenas logging)
        - Não registra violações formais
        - Timeout curto (5s) para não impactar latência do workflow
    """
    config = get_settings()
    metrics = get_metrics()
    start_time = time.time()

    # Verificar se monitoramento SLA está habilitado
    if not config.sla_management_enabled:
        logger.info(
            'SLA monitoring desabilitado, pulando verificação proativa',
            checkpoint=checkpoint
        )
        return _default_response(checkpoint)

    # Inicializar SLAMonitor
    sla_monitor = None
    try:
        # Obter Redis client (opcional, fail-open se indisponível)
        redis_client = None
        try:
            from src.clients.redis_client import get_redis_client
            redis_client = await get_redis_client(config)
        except Exception as redis_error:
            logger.warning(
                f'Redis indisponível para cache, continuando sem cache: {redis_error}'
            )

        # Criar e inicializar SLAMonitor
        sla_monitor = SLAMonitor(config, redis_client, metrics)
        await sla_monitor.initialize()

        # === Verificação de Deadline ===
        deadline_result = await sla_monitor.check_workflow_sla(workflow_id, tickets)

        deadline_approaching = deadline_result.get('deadline_approaching', False)
        critical_tickets = deadline_result.get('critical_tickets', [])
        remaining_seconds = deadline_result.get('remaining_seconds', 0.0)

        # Log de warning se deadline se aproximando
        if deadline_approaching:
            logger.warning(
                'Verificação proativa: deadline se aproximando',
                checkpoint=checkpoint,
                workflow_id=workflow_id,
                remaining_seconds=remaining_seconds,
                critical_tickets_count=len(critical_tickets)
            )
            # Registrar métrica de deadline approaching
            metrics.record_deadline_approaching()
            metrics.update_sla_remaining(
                workflow_id=workflow_id,
                risk_band='medium',  # Assumir medium para proativo
                remaining_seconds=remaining_seconds
            )

        # === Verificação de Budget (apenas no checkpoint final) ===
        budget_critical = False
        budget_data = None

        if checkpoint == 'post_ticket_publishing':
            try:
                is_critical, budget_data = await sla_monitor.check_budget_threshold(
                    service_name='orchestrator-dynamic',
                    threshold=config.sla_budget_critical_threshold
                )
                budget_critical = is_critical

                if budget_critical and budget_data:
                    logger.warning(
                        'Verificação proativa: budget crítico detectado',
                        checkpoint=checkpoint,
                        budget_remaining=budget_data.get('error_budget_remaining'),
                        status=budget_data.get('status')
                    )
            except Exception as budget_error:
                logger.warning(
                    f'Erro ao verificar budget no checkpoint {checkpoint}: {budget_error}'
                )

        # === Registrar Métricas de Performance ===
        duration = time.time() - start_time
        metrics.record_sla_check_duration(f'proactive_{checkpoint}', duration)

        # === Preparar Resposta ===
        response = {
            'deadline_approaching': deadline_approaching,
            'critical_tickets': critical_tickets,
            'remaining_seconds': remaining_seconds,
            'checkpoint': checkpoint
        }

        # Adicionar budget info apenas se checkpoint final
        if checkpoint == 'post_ticket_publishing':
            response['budget_critical'] = budget_critical
            if budget_data:
                response['budget_data'] = budget_data

        logger.info(
            'Verificação proativa de SLA concluída',
            checkpoint=checkpoint,
            workflow_id=workflow_id,
            deadline_approaching=deadline_approaching,
            duration_ms=duration * 1000
        )

        return response

    except Exception as e:
        # Fail-open: Log erro mas não bloqueia workflow
        logger.warning(
            f'Erro na verificação proativa de SLA (fail-open): {e}',
            checkpoint=checkpoint,
            workflow_id=workflow_id,
            exc_info=True
        )

        # Registrar métrica de erro
        metrics.record_sla_monitor_error('proactive_check')

        # Registrar duração mesmo em caso de erro
        duration = time.time() - start_time
        metrics.record_sla_check_duration(f'proactive_{checkpoint}_error', duration)

        # Retornar resposta default (fail-open)
        return _default_response(checkpoint)

    finally:
        # Cleanup: fechar SLAMonitor
        if sla_monitor:
            try:
                await sla_monitor.close()
            except Exception as close_error:
                logger.warning(f'Erro ao fechar SLAMonitor: {close_error}')


def _default_response(checkpoint: str) -> Dict[str, Any]:
    """
    Retorna resposta default para verificação proativa (fail-open).

    Args:
        checkpoint: Identificador do checkpoint

    Returns:
        Dict com valores default indicando nenhum problema detectado
    """
    response = {
        'deadline_approaching': False,
        'critical_tickets': [],
        'remaining_seconds': 0.0,
        'checkpoint': checkpoint
    }

    # Adicionar budget info para checkpoint final
    if checkpoint == 'post_ticket_publishing':
        response['budget_critical'] = False

    return response


# Erro customizado para SLA Monitor indisponível (non-retryable)
class SLAMonitorUnavailable(Exception):
    """Exceção lançada quando SLA Management System está indisponível."""
    pass
