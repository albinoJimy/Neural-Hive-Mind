"""Health router implementation."""

from datetime import datetime, timezone
from fastapi import FastAPI
from .models import HealthResponse, HealthStatus
from .checks import BaseHealthCheck


class HealthRouter:
    """Router padronizado de health check."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.checks: list[BaseHealthCheck] = []

    def register_check(self, check: BaseHealthCheck) -> None:
        """Registra um check customizado."""
        self.checks.append(check)

    def add_route(self, app: FastAPI) -> None:
        """Adiciona rotas de health à app FastAPI."""
        app.add_api_route("/health", self._health)
        app.add_api_route("/health/live", self._liveness)
        app.add_api_route("/health/ready", self._readiness)

    async def _execute_checks(self) -> dict[str, tuple[HealthStatus, bool]]:
        """Executa todos os checks e retorna resultados com criticidade."""
        results = {}
        for check in self.checks:
            try:
                result = await check.check()
                results[result.name] = (result.status, check.critical)
            except Exception:
                results[check.name] = (HealthStatus.UNHEALTHY, check.critical)
        return results

    def _aggregate_status(self, checks: dict[str, tuple[HealthStatus, bool]]) -> HealthStatus:
        """Agrega status dos checks considerando criticidade."""
        if not checks:
            return HealthStatus.HEALTHY

        has_critical_unhealthy = any(
            status == HealthStatus.UNHEALTHY and critical
            for status, critical in checks.values()
        )
        has_any_unhealthy = any(
            status == HealthStatus.UNHEALTHY
            for status, _ in checks.values()
        )
        has_degraded = any(
            status == HealthStatus.DEGRADED
            for status, _ in checks.values()
        )

        if has_critical_unhealthy:
            return HealthStatus.UNHEALTHY
        if has_any_unhealthy or has_degraded:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    async def _health(self) -> HealthResponse:
        """Endpoint principal - status agregado."""
        checks_with_critical = await self._execute_checks()
        status = self._aggregate_status(checks_with_critical)
        checks = {name: status for name, (status, _) in checks_with_critical.items()}
        return HealthResponse(
            status=status,
            service=self.service_name,
            timestamp=datetime.now(timezone.utc),
            checks=checks
        )

    async def _liveness(self) -> HealthResponse:
        """Liveness probe - serviço está vivo?"""
        return HealthResponse(
            status=HealthStatus.HEALTHY,
            service=self.service_name,
            timestamp=datetime.now(timezone.utc),
            checks={}
        )

    async def _readiness(self) -> HealthResponse:
        """Readiness probe - serviço pode receber tráfego?"""
        checks_with_critical = await self._execute_checks()
        status = self._aggregate_status(checks_with_critical)
        checks = {name: status for name, (status, _) in checks_with_critical.items()}
        return HealthResponse(
            status=status,
            service=self.service_name,
            timestamp=datetime.now(timezone.utc),
            checks=checks
        )
