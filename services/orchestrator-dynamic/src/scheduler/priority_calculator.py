"""
PriorityCalculator - Calcula scores de priorização para tickets.

Combina risk_band, QoS e SLA urgency em score composto para priorização.
"""

import structlog
from datetime import datetime
from typing import Dict

from src.config.settings import OrchestratorSettings

logger = structlog.get_logger(__name__)


class PriorityCalculator:
    """
    Calculador de prioridades para execution tickets.

    Calcula score baseado em:
    - Risk band (40%): critical > high > normal > low
    - QoS (30%): delivery_mode + consistency
    - SLA urgency (30%): % de deadline consumido
    """

    # Mapeamento de risk_band para peso
    RISK_WEIGHTS = {
        'critical': 1.0,
        'high': 0.7,
        'normal': 0.5,
        'low': 0.3
    }

    # Mapeamento de delivery_mode para peso base
    QOS_DELIVERY_WEIGHTS = {
        'EXACTLY_ONCE': 1.0,
        'AT_LEAST_ONCE': 0.7,
        'AT_MOST_ONCE': 0.5
    }

    # Ajuste de consistência
    QOS_CONSISTENCY_MULTIPLIER = {
        'STRONG': 1.0,
        'EVENTUAL': 0.85
    }

    # Ajuste de durabilidade
    QOS_DURABILITY_MULTIPLIER = {
        'PERSISTENT': 1.0,
        'TRANSIENT': 0.9,
        'EPHEMERAL': 0.8
    }

    def __init__(self, config: OrchestratorSettings):
        """
        Inicializa o calculador.

        Args:
            config: Configurações do orchestrator
        """
        self.config = config
        self.logger = logger.bind(component='priority_calculator')

        # Pesos de priorização (podem ser customizados via config)
        self.priority_weights = config.scheduler_priority_weights or {
            'risk': 0.4,
            'qos': 0.3,
            'sla': 0.3
        }

    def calculate_priority_score(self, ticket: Dict) -> float:
        """
        Calcula priority score para um ticket.

        Args:
            ticket: Execution ticket

        Returns:
            Score normalizado [0.0, 1.0]
        """
        ticket_id = ticket.get('ticket_id', 'unknown')

        # Extrair componentes
        risk_band = ticket.get('risk_band', 'normal')
        qos = ticket.get('qos', {})
        sla = ticket.get('sla', {})
        created_at_raw = ticket.get('created_at', int(datetime.now().timestamp() * 1000))

        # Converter created_at para timestamp em ms (suporta ISO string ou int)
        created_at = self._convert_to_timestamp_ms(created_at_raw)

        # Calcular componentes individuais
        risk_weight = self._calculate_risk_weight(risk_band)
        qos_weight = self._calculate_qos_weight(qos)
        sla_urgency = self._calculate_sla_urgency(sla, created_at)

        # Combinar com pesos
        priority_score = (
            (risk_weight * self.priority_weights['risk']) +
            (qos_weight * self.priority_weights['qos']) +
            (sla_urgency * self.priority_weights['sla'])
        )

        # Normalizar para [0.0, 1.0]
        priority_score = min(max(priority_score, 0.0), 1.0)

        self.logger.debug(
            'priority_score_calculated',
            ticket_id=ticket_id,
            risk_band=risk_band,
            risk_weight=risk_weight,
            qos_weight=qos_weight,
            sla_urgency=sla_urgency,
            priority_score=priority_score
        )

        return priority_score

    def _calculate_risk_weight(self, risk_band: str) -> float:
        """
        Calcula peso baseado em risk_band.

        Args:
            risk_band: Banda de risco (critical/high/normal/low)

        Returns:
            Peso normalizado [0.0, 1.0]
        """
        weight = self.RISK_WEIGHTS.get(risk_band.lower(), 0.5)
        return weight

    def _calculate_qos_weight(self, qos: Dict) -> float:
        """
        Calcula peso baseado em QoS.

        Combina:
        - delivery_mode: Peso base (EXACTLY_ONCE, AT_LEAST_ONCE, AT_MOST_ONCE)
        - consistency: Multiplicador (STRONG, EVENTUAL)
        - durability: Multiplicador adicional (PERSISTENT, TRANSIENT, EPHEMERAL)

        Args:
            qos: Configuração de QoS (delivery_mode, consistency, durability)

        Returns:
            Peso normalizado [0.0, 1.0]
        """
        delivery_mode = qos.get('delivery_mode', 'AT_LEAST_ONCE')
        consistency = qos.get('consistency', 'EVENTUAL')
        durability = qos.get('durability', 'PERSISTENT')

        # Peso base do delivery mode
        base_weight = self.QOS_DELIVERY_WEIGHTS.get(delivery_mode, 0.7)

        # Ajustar por consistência
        consistency_multiplier = self.QOS_CONSISTENCY_MULTIPLIER.get(
            consistency,
            0.85
        )

        # Ajustar por durabilidade
        durability_multiplier = self.QOS_DURABILITY_MULTIPLIER.get(
            durability,
            1.0
        )

        # Combinar: base_weight * consistency * durability
        weight = base_weight * consistency_multiplier * durability_multiplier

        return min(max(weight, 0.0), 1.0)

    def _convert_to_timestamp_ms(self, value) -> int:
        """
        Converte valor para timestamp em milissegundos.

        Aceita:
        - int: Já é timestamp em ms, retorna direto
        - str: ISO 8601 string, converte para ms
        - float: Timestamp em ms, converte para int

        Args:
            value: Timestamp em ms (int) ou ISO string

        Returns:
            Timestamp em milissegundos (int)
        """
        if isinstance(value, int):
            return value
        elif isinstance(value, float):
            return int(value)
        elif isinstance(value, str):
            try:
                # Parse ISO 8601 string
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)
            except (ValueError, AttributeError):
                # Fallback: tentar parse direto como timestamp
                try:
                    return int(float(value))
                except (ValueError, TypeError):
                    # Se falhar, usar timestamp atual
                    self.logger.warning(
                        'invalid_timestamp_format',
                        value=value,
                        using_current_time=True
                    )
                    return int(datetime.now().timestamp() * 1000)
        else:
            # Tipo inesperado, usar timestamp atual
            self.logger.warning(
                'unexpected_timestamp_type',
                value_type=type(value).__name__,
                using_current_time=True
            )
            return int(datetime.now().timestamp() * 1000)

    def _calculate_sla_urgency(self, sla: Dict, created_at: int) -> float:
        """
        Calcula urgência baseada em SLA.

        Quanto mais próximo do deadline, maior a urgência.

        Args:
            sla: Configuração de SLA (deadline, timeout_ms)
            created_at: Timestamp de criação do ticket em ms (já convertido)

        Returns:
            Urgência normalizada [0.0, 1.0]
        """
        deadline_raw = sla.get('deadline')
        timeout_ms = sla.get('timeout_ms', 300000)  # Default 5 min

        # Converter deadline para timestamp ms se for string
        if deadline_raw is not None:
            deadline = self._convert_to_timestamp_ms(deadline_raw)
        else:
            # Se não há deadline explícito, usar created_at + timeout_ms
            deadline = created_at + timeout_ms

        # Calcular tempo decorrido
        now_ms = int(datetime.now().timestamp() * 1000)
        elapsed_ms = now_ms - created_at
        total_allowed_ms = deadline - created_at

        if total_allowed_ms <= 0:
            # Deadline já passou
            return 1.0

        # Calcular % de deadline consumido
        deadline_consumed_pct = (elapsed_ms / total_allowed_ms) * 100

        # Mapear para urgência
        if deadline_consumed_pct < 50:
            urgency = 0.3
        elif deadline_consumed_pct < 80:
            urgency = 0.7
        else:
            urgency = 1.0

        return urgency
