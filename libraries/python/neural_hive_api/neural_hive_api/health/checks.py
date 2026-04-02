"""Base health check classes."""

from abc import ABC, abstractmethod
from .models import HealthStatus, CheckResult


class BaseHealthCheck(ABC):
    """Base class para health checks."""

    def __init__(self, name: str, critical: bool = True):
        self.name = name
        self.critical = critical

    @abstractmethod
    async def check(self) -> CheckResult:
        """Executa o check e retorna resultado."""
        pass
