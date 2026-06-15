"""Testes para o tratamento de backoff do consumer (FIX-CP-001 / BUG-2).

Regressão: a exceção "Backoff em andamento" era tratada como erro de negócio
sem sleep, fazendo o consumer re-pollar a mesma mensagem em tight-loop (offset
estagnado, lag residual). O helper _extract_backoff_seconds permite dormir o
tempo restante e quebrar o loop.
"""

import pytest

from src.consumers.plan_consumer import PlanConsumer


@pytest.fixture()
def consumer_stub():
    """Instância sem __init__ (evita deps pesadas) para testar helpers puros."""
    return PlanConsumer.__new__(PlanConsumer)


def test_extract_backoff_from_message(consumer_stub):
    err = Exception("Backoff em andamento: 12.5s restantes")
    assert consumer_stub._extract_backoff_seconds(err) == 12.5


def test_extract_backoff_integer_seconds(consumer_stub):
    err = Exception("Backoff em andamento: 4s restantes")
    assert consumer_stub._extract_backoff_seconds(err) == 4.0


def test_non_backoff_error_returns_none(consumer_stub):
    assert consumer_stub._extract_backoff_seconds(ValueError("plano inválido")) is None


def test_systemic_error_not_treated_as_backoff(consumer_stub):
    assert consumer_stub._extract_backoff_seconds(ConnectionError("mongodb down")) is None


def test_backoff_message_without_number_returns_none(consumer_stub):
    err = Exception("Backoff em andamento")
    assert consumer_stub._extract_backoff_seconds(err) is None
