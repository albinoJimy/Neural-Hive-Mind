import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR / "services/self-healing-engine/src"))
import time

from src.clients.self_healing_client import CircuitBreaker


@pytest.mark.integration
def test_circuit_breaker_opens_after_failures():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout=1)

    cb.record_failure()
    cb.record_failure()
    assert cb.is_open() is False

    cb.record_failure()
    assert cb.is_open() is True


@pytest.mark.integration
def test_circuit_breaker_resets_after_timeout():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=1)
    cb.record_failure()
    assert cb.is_open() is True

    time.sleep(1.1)
    assert cb.is_open() is False
