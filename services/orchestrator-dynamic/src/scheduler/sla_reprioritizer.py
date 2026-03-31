"""
SLARePrioritizer - Re-prioritização baseada em eventos SLA.

Monitora eventos de SLA e dispara re-prioritização de tickets
quando deadlines se aproximam ou urgência aumenta.
"""
import structlog
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from src.scheduler.reprioritizer import RePrioritizer
from src.scheduler.queue_manager import QueueManager
from src.scheduler.priority_calculator import PriorityCalculator


logger = structlog.get_logger(__name__)


class SLARePrioritizer:
    """
    Gerencia re-prioritização baseada em eventos SLA.

    Monitors:
    - SLA warnings (deadline se aproximando)
    - Mudanças de risk_band
    - Mudanças de deadline
    - Eventos de SLA breach

    Integra com:
    - SLA Management System via Kafka
    - RePrioritizer para executar mudanças de prioridade
    """

    # Thresholds para re-prioritização automática
    SLA_URGENCY_CRITICAL_THRESHOLD = 0.8
    DEADLINE_REMAINING_HIGH_THRESHOLD = 0.3  # 30% restante
    DEADLINE_REMAINING_CRITICAL_THRESHOLD = 0.15  # 15% restante

    def __init__(
        self,
        reprioritizer: RePrioritizer,
        queue_manager: QueueManager
    ):
        """
        Inicializa o re-priorizador SLA.

        Args:
            reprioritizer: RePrioritizer para executar mudanças
            queue_manager: Gerenciador de filas
        """
        self.reprioritizer = reprioritizer
        self.queue_manager = queue_manager
        self.logger = logger.bind(component='sla_reprioritizer')

    async def on_sla_warning(
        self,
        event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Processa evento de SLA warning e re-prioriza se necessário.

        Args:
            event: Evento SLA com campos:
                - ticket_id: ID do ticket
                - plan_id: ID do plano
                - sla_urgency: Urgência SLA [0.0, 1.0]
                - deadline_remaining_pct: % restante [0.0, 1.0]
                - current_queue: Fila atual (opcional)

        Returns:
            Resultado da re-priorização
        """
        ticket_id = event.get('ticket_id', 'unknown')
        sla_urgency = event.get('sla_urgency', 0.0)
        deadline_remaining_pct = event.get('deadline_remaining_pct', 1.0)

        self.logger.info(
            'sla_warning_received',
            ticket_id=ticket_id,
            sla_urgency=sla_urgency,
            deadline_remaining_pct=deadline_remaining_pct
        )

        # Verificar se deve re-priorizar
        if not self.reprioritizer.should_reprioritize_on_sla_warning(
            sla_urgency,
            deadline_remaining_pct
        ):
            self.logger.debug(
                'sla_warning_no_reprioritization',
                ticket_id=ticket_id,
                reason='thresholds_not_met'
            )
            return {'ticket_id': ticket_id, 'action': 'none', 'reason': 'thresholds_not_met'}

        # Determinar nova prioridade
        new_priority = self._calculate_sla_based_priority(
            sla_urgency,
            deadline_remaining_pct
        )

        self.logger.info(
            'sla_warning_reprioritization',
            ticket_id=ticket_id,
            new_priority=new_priority,
            sla_urgency=sla_urgency,
            deadline_remaining_pct=deadline_remaining_pct
        )

        return {
            'ticket_id': ticket_id,
            'action': 'reprioritize',
            'new_priority': new_priority,
            'sla_urgency': sla_urgency,
            'deadline_remaining_pct': deadline_remaining_pct
        }

    async def on_risk_band_changed(
        self,
        event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Processa mudança de risk_band e re-prioriza.

        Args:
            event: Evento com campos:
                - ticket_id: ID do ticket
                - old_risk_band: Banda de risco anterior
                - new_risk_band: Nova banda de risco
                - reason: Razão da mudança

        Returns:
            Resultado da re-priorização
        """
        ticket_id = event.get('ticket_id', 'unknown')
        old_risk_band = event.get('old_risk_band', 'unknown')
        new_risk_band = event.get('new_risk_band', 'unknown')

        self.logger.info(
            'risk_band_changed',
            ticket_id=ticket_id,
            old_risk_band=old_risk_band,
            new_risk_band=new_risk_band,
            reason=event.get('reason', 'unknown')
        )

        # Mapear risk_band para prioridade
        new_priority = self._map_risk_band_to_priority(new_risk_band)

        self.logger.info(
            'risk_band_reprioritization',
            ticket_id=ticket_id,
            old_risk_band=old_risk_band,
            new_risk_band=new_risk_band,
            new_priority=new_priority
        )

        return {
            'ticket_id': ticket_id,
            'action': 'reprioritize',
            'old_priority': self._map_risk_band_to_priority(old_risk_band),
            'new_priority': new_priority,
            'old_risk_band': old_risk_band,
            'new_risk_band': new_risk_band
        }

    async def on_deadline_approaching(
        self,
        event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Processa evento de deadline se aproximando.

        Args:
            event: Evento com campos:
                - ticket_id: ID do ticket
                - deadline_timestamp: Timestamp do deadline
                - remaining_ms: Milissegundos restantes

        Returns:
            Resultado da re-priorização
        """
        ticket_id = event.get('ticket_id', 'unknown')
        remaining_ms = event.get('remaining_ms', 0)

        # Calcular % restante (assumindo timeout padrão de 5 min)
        default_timeout_ms = 300000  # 5 minutos
        deadline_remaining_pct = remaining_ms / default_timeout_ms

        self.logger.info(
            'deadline_approaching',
            ticket_id=ticket_id,
            remaining_ms=remaining_ms,
            deadline_remaining_pct=deadline_remaining_pct
        )

        # Se menos de 30% restante, elevar para HIGH
        # Se menos de 15% restante, elevar para CRITICAL
        if deadline_remaining_pct < self.DEADLINE_REMAINING_CRITICAL_THRESHOLD:
            new_priority = 'CRITICAL'
        elif deadline_remaining_pct < self.DEADLINE_REMAINING_HIGH_THRESHOLD:
            new_priority = 'HIGH'
        else:
            new_priority = None

        if not new_priority:
            return {
                'ticket_id': ticket_id,
                'action': 'none',
                'reason': 'deadline_not_critical'
            }

        self.logger.info(
            'deadline_reprioritization',
            ticket_id=ticket_id,
            new_priority=new_priority,
            remaining_ms=remaining_ms
        )

        return {
            'ticket_id': ticket_id,
            'action': 'reprioritize',
            'new_priority': new_priority,
            'remaining_ms': remaining_ms
        }

    async def on_sla_breach(
        self,
        event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Processa evento de SLA breach.

        Args:
            event: Evento com campos:
                - ticket_id: ID do ticket
                - breach_type: Tipo de breach
                - sla_details: Detalhes do SLA

        Returns:
            Resultado da re-priorização
        """
        ticket_id = event.get('ticket_id', 'unknown')
        breach_type = event.get('breach_type', 'unknown')

        self.logger.warning(
            'sla_breach_occurred',
            ticket_id=ticket_id,
            breach_type=breach_type
        )

        # Em caso de breach, elevar para CRITICAL imediatamente
        return {
            'ticket_id': ticket_id,
            'action': 'reprioritize',
            'new_priority': 'CRITICAL',
            'reason': 'sla_breach',
            'breach_type': breach_type
        }

    def _calculate_sla_based_priority(
        self,
        sla_urgency: float,
        deadline_remaining_pct: float
    ) -> str:
        """
        Calcula prioridade baseada em SLA.

        Args:
            sla_urgency: Urgência SLA [0.0, 1.0]
            deadline_remaining_pct: % de deadline restante [0.0, 1.0]

        Returns:
            Nível de prioridade (CRITICAL/HIGH/NORMAL/LOW)
        """
        # CRITICAL: urgência > 0.8 ou menos de 15% restante
        if sla_urgency > self.SLA_URGENCY_CRITICAL_THRESHOLD or \
           deadline_remaining_pct < self.DEADLINE_REMAINING_CRITICAL_THRESHOLD:
            return 'CRITICAL'

        # HIGH: urgência > 0.6 ou menos de 30% restante
        if sla_urgency > 0.6 or deadline_remaining_pct < self.DEADLINE_REMAINING_HIGH_THRESHOLD:
            return 'HIGH'

        # NORMAL: caso contrário
        return 'NORMAL'

    def _map_risk_band_to_priority(self, risk_band: str) -> str:
        """
        Mapeia risk_band para nível de prioridade.

        Args:
            risk_band: Banda de risco (critical/high/normal/low)

        Returns:
            Nível de prioridade
        """
        mapping = {
            'critical': 'CRITICAL',
            'high': 'HIGH',
            'normal': 'NORMAL',
            'low': 'LOW'
        }
        return mapping.get(risk_band.lower(), 'NORMAL')

    def should_reprioritize_on_sla_event(self, event_type: str, event_data: Dict[str, Any]) -> bool:
        """
        Determina se evento SLA deve disparar re-prioritização.

        Args:
            event_type: Tipo do evento (sla_warning, deadline_approaching, etc)
            event_data: Dados do evento

        Returns:
            True se deve re-priorizar
        """
        if event_type == 'sla_warning':
            sla_urgency = event_data.get('sla_urgency', 0.0)
            deadline_remaining_pct = event_data.get('deadline_remaining_pct', 1.0)
            return self.reprioritizer.should_reprioritize_on_sla_warning(
                sla_urgency,
                deadline_remaining_pct
            )

        if event_type == 'deadline_approaching':
            remaining_ms = event_data.get('remaining_ms', 0)
            default_timeout_ms = 300000
            deadline_remaining_pct = remaining_ms / default_timeout_ms
            return deadline_remaining_pct < self.DEADLINE_REMAINING_HIGH_THRESHOLD

        if event_type == 'sla_breach':
            return True

        if event_type == 'risk_band_changed':
            old_band = event_data.get('old_risk_band', '')
            new_band = event_data.get('new_risk_band', '')
            return old_band != new_band

        return False
