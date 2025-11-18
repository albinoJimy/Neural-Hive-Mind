"""
Testes unitários para PriorityCalculator.

Cobertura:
- Cálculo de score de prioridade para diferentes risk bands
- Aplicação de pesos padrão e customizados
- Cálculo de peso de risco
- Cálculo de peso de QoS
- Valores padrão de QoS
- Cálculo de urgência de SLA
- Normalização de scores
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from typing import Dict, Any

from src.scheduler.priority_calculator import PriorityCalculator
from src.config.settings import OrchestratorSettings


@pytest.fixture
def mock_config_default():
    """Config com pesos padrão."""
    config = MagicMock(spec=OrchestratorSettings)
    config.scheduler_priority_weights = {"risk": 0.4, "qos": 0.3, "sla": 0.3}
    return config


@pytest.fixture
def mock_config_custom():
    """Config com pesos customizados."""
    config = MagicMock(spec=OrchestratorSettings)
    config.scheduler_priority_weights = {"risk": 0.5, "qos": 0.3, "sla": 0.2}
    return config


@pytest.fixture
def ticket_critical() -> Dict[str, Any]:
    """Ticket com risco crítico, QoS alto, deadline se aproximando."""
    deadline = datetime.utcnow() + timedelta(minutes=6)  # 90% do tempo consumido (1h total)
    created = datetime.utcnow() - timedelta(minutes=54)

    return {
        "ticket_id": "ticket-critical",
        "risk_band": "critical",
        "qos": {
            "delivery_mode": "EXACTLY_ONCE",
            "consistency": "STRONG",
            "durability": "PERSISTENT"
        },
        "sla": {
            "deadline": deadline.isoformat(),
            "timeout_ms": 3600000
        },
        "created_at": created.isoformat(),
        "estimated_duration_ms": 1000
    }


@pytest.fixture
def ticket_low() -> Dict[str, Any]:
    """Ticket com risco baixo, QoS baixo, deadline segura."""
    deadline = datetime.utcnow() + timedelta(minutes=48)  # 20% do tempo consumido
    created = datetime.utcnow() - timedelta(minutes=12)

    return {
        "ticket_id": "ticket-low",
        "risk_band": "low",
        "qos": {
            "delivery_mode": "AT_MOST_ONCE",
            "consistency": "EVENTUAL",
            "durability": "EPHEMERAL"
        },
        "sla": {
            "deadline": deadline.isoformat(),
            "timeout_ms": 3600000
        },
        "created_at": created.isoformat(),
        "estimated_duration_ms": 1000
    }


@pytest.fixture
def ticket_deadline_approaching() -> Dict[str, Any]:
    """Ticket com 90% do SLA consumido."""
    deadline = datetime.utcnow() + timedelta(minutes=6)
    created = datetime.utcnow() - timedelta(minutes=54)

    return {
        "ticket_id": "ticket-deadline-approaching",
        "risk_band": "normal",
        "qos": {
            "delivery_mode": "AT_LEAST_ONCE",
            "consistency": "EVENTUAL",
            "durability": "PERSISTENT"
        },
        "sla": {
            "deadline": deadline.isoformat(),
            "timeout_ms": 3600000
        },
        "created_at": created.isoformat(),
        "estimated_duration_ms": 1000
    }


@pytest.fixture
def ticket_deadline_safe() -> Dict[str, Any]:
    """Ticket com 20% do SLA consumido."""
    deadline = datetime.utcnow() + timedelta(minutes=48)
    created = datetime.utcnow() - timedelta(minutes=12)

    return {
        "ticket_id": "ticket-deadline-safe",
        "risk_band": "normal",
        "qos": {
            "delivery_mode": "AT_LEAST_ONCE",
            "consistency": "EVENTUAL",
            "durability": "PERSISTENT"
        },
        "sla": {
            "deadline": deadline.isoformat(),
            "timeout_ms": 3600000
        },
        "created_at": created.isoformat(),
        "estimated_duration_ms": 1000
    }


@pytest.fixture
def ticket_no_deadline() -> Dict[str, Any]:
    """Ticket sem deadline explícito."""
    created = datetime.utcnow() - timedelta(minutes=30)

    return {
        "ticket_id": "ticket-no-deadline",
        "risk_band": "normal",
        "qos": {
            "delivery_mode": "AT_LEAST_ONCE",
            "consistency": "EVENTUAL",
            "durability": "PERSISTENT"
        },
        "sla": {
            "timeout_ms": 3600000
        },
        "created_at": created.isoformat(),
        "estimated_duration_ms": 1000
    }


class TestPriorityCalculator:
    """Testes para PriorityCalculator."""

    def test_calculate_priority_score_critical_risk(self, mock_config_default, ticket_critical):
        """Testa score para ticket crítico com QoS alto e SLA urgente."""
        calculator = PriorityCalculator(mock_config_default)

        score = calculator.calculate_priority_score(ticket_critical)

        # Esperado: risk=1.0, qos=1.0, sla≈0.9
        # Score = (1.0 * 0.4) + (1.0 * 0.3) + (0.9 * 0.3) ≈ 0.97
        assert 0.94 <= score <= 1.0
        assert score > 0.9

    def test_calculate_priority_score_low_risk(self, mock_config_default, ticket_low):
        """Testa score para ticket com risco baixo, QoS baixo, SLA segura."""
        calculator = PriorityCalculator(mock_config_default)

        score = calculator.calculate_priority_score(ticket_low)

        # Esperado: risk=0.3, qos≈0.35, sla≈0.2
        # Score = (0.3 * 0.4) + (0.35 * 0.3) + (0.2 * 0.3) ≈ 0.285
        assert 0.20 <= score <= 0.40

    def test_calculate_priority_score_default_weights(self, mock_config_default):
        """Verifica que pesos padrão são aplicados."""
        calculator = PriorityCalculator(mock_config_default)

        ticket = {
            "risk_band": "high",
            "qos": {"delivery_mode": "AT_LEAST_ONCE", "consistency": "EVENTUAL", "durability": "PERSISTENT"},
            "sla": {"deadline": (datetime.utcnow() + timedelta(hours=1)).isoformat(), "timeout_ms": 3600000},
            "created_at": datetime.utcnow().isoformat()
        }

        score = calculator.calculate_priority_score(ticket)

        # Verificar que score está no range esperado
        assert 0.0 <= score <= 1.0

    def test_calculate_priority_score_custom_weights(self, mock_config_custom):
        """Verifica que pesos customizados são aplicados."""
        calculator = PriorityCalculator(mock_config_custom)

        # Pesos: risk=0.5, qos=0.3, sla=0.2
        ticket = {
            "risk_band": "critical",
            "qos": {"delivery_mode": "EXACTLY_ONCE", "consistency": "STRONG", "durability": "PERSISTENT"},
            "sla": {"deadline": (datetime.utcnow() + timedelta(hours=1)).isoformat(), "timeout_ms": 3600000},
            "created_at": datetime.utcnow().isoformat()
        }

        score = calculator.calculate_priority_score(ticket)

        # Com pesos customizados, risco tem mais peso
        assert score > 0.7

    @pytest.mark.parametrize("risk_band,expected_weight", [
        ("critical", 1.0),
        ("high", 0.7),
        ("normal", 0.5),
        ("low", 0.3),
        ("unknown", 0.5)
    ])
    def test_calculate_risk_weight(self, mock_config_default, risk_band, expected_weight):
        """Testa todos os risk bands."""
        calculator = PriorityCalculator(mock_config_default)

        weight = calculator._calculate_risk_weight(risk_band)

        assert weight == expected_weight

    def test_calculate_qos_weight_exactly_once_strong(self, mock_config_default):
        """Testa QoS com maiores garantias."""
        calculator = PriorityCalculator(mock_config_default)

        qos = {
            "delivery_mode": "EXACTLY_ONCE",
            "consistency": "STRONG",
            "durability": "PERSISTENT"
        }

        weight = calculator._calculate_qos_weight(qos)

        # 1.0 * 1.0 * 1.0 = 1.0
        assert weight == 1.0

    def test_calculate_qos_weight_at_least_once_eventual(self, mock_config_default):
        """Testa QoS com garantias médias."""
        calculator = PriorityCalculator(mock_config_default)

        qos = {
            "delivery_mode": "AT_LEAST_ONCE",
            "consistency": "EVENTUAL",
            "durability": "PERSISTENT"
        }

        weight = calculator._calculate_qos_weight(qos)

        # 0.7 * 0.85 * 1.0 = 0.595
        assert abs(weight - 0.595) < 0.01

    def test_calculate_qos_weight_defaults(self, mock_config_default):
        """Testa que valores padrão são usados quando QoS está vazio."""
        calculator = PriorityCalculator(mock_config_default)

        qos = {}

        weight = calculator._calculate_qos_weight(qos)

        # Padrão: AT_LEAST_ONCE (0.7) * EVENTUAL (0.85) * PERSISTENT (1.0) = 0.595
        assert abs(weight - 0.595) < 0.01

    def test_calculate_sla_urgency_deadline_approaching(
        self, mock_config_default, ticket_deadline_approaching
    ):
        """Testa urgência com 90% do deadline consumido."""
        calculator = PriorityCalculator(mock_config_default)

        urgency = calculator._calculate_sla_urgency(
            ticket_deadline_approaching["sla"],
            ticket_deadline_approaching["created_at"]
        )

        # 90% consumido → urgency ≈ 0.9 ou 1.0
        assert urgency >= 0.85

    def test_calculate_sla_urgency_deadline_safe(
        self, mock_config_default, ticket_deadline_safe
    ):
        """Testa urgência com 20% do deadline consumido."""
        calculator = PriorityCalculator(mock_config_default)

        urgency = calculator._calculate_sla_urgency(
            ticket_deadline_safe["sla"],
            ticket_deadline_safe["created_at"]
        )

        # 20% consumido → urgency ≈ 0.2
        assert 0.15 <= urgency <= 0.35

    def test_calculate_sla_urgency_deadline_passed(self, mock_config_default):
        """Testa urgência quando deadline já passou."""
        calculator = PriorityCalculator(mock_config_default)

        # Deadline no passado
        deadline = datetime.utcnow() - timedelta(minutes=10)
        created = datetime.utcnow() - timedelta(hours=2)

        sla = {
            "deadline": deadline.isoformat(),
            "timeout_ms": 3600000
        }

        urgency = calculator._calculate_sla_urgency(sla, created.isoformat())

        # Deadline passou → urgency = 1.0
        assert urgency == 1.0

    def test_calculate_sla_urgency_no_deadline(
        self, mock_config_default, ticket_no_deadline
    ):
        """Testa urgência quando não há deadline explícito."""
        calculator = PriorityCalculator(mock_config_default)

        urgency = calculator._calculate_sla_urgency(
            ticket_no_deadline["sla"],
            ticket_no_deadline["created_at"]
        )

        # Usa created_at + timeout_ms como deadline
        # 30 minutos passados de 60 → 50% consumido
        assert 0.4 <= urgency <= 0.6

    def test_priority_score_normalization(self, mock_config_default):
        """Testa que score é sempre normalizado para [0.0, 1.0]."""
        calculator = PriorityCalculator(mock_config_default)

        # Teste com valores extremos
        tickets = [
            {
                "risk_band": "critical",
                "qos": {"delivery_mode": "EXACTLY_ONCE", "consistency": "STRONG", "durability": "PERSISTENT"},
                "sla": {
                    "deadline": (datetime.utcnow() - timedelta(hours=1)).isoformat(),  # Passado
                    "timeout_ms": 3600000
                },
                "created_at": (datetime.utcnow() - timedelta(hours=2)).isoformat()
            },
            {
                "risk_band": "low",
                "qos": {"delivery_mode": "AT_MOST_ONCE", "consistency": "EVENTUAL", "durability": "EPHEMERAL"},
                "sla": {
                    "deadline": (datetime.utcnow() + timedelta(days=1)).isoformat(),
                    "timeout_ms": 3600000
                },
                "created_at": datetime.utcnow().isoformat()
            }
        ]

        for ticket in tickets:
            score = calculator.calculate_priority_score(ticket)

            # Verificar range
            assert 0.0 <= score <= 1.0
