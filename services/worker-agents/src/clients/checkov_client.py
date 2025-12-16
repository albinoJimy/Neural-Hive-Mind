import asyncio
from dataclasses import dataclass
from typing import List
import structlog

logger = structlog.get_logger()


@dataclass
class CheckovReport:
    """Resultado de um scan Checkov."""

    passed: bool
    findings: List[dict]
    duration_seconds: float
    logs: List[str]


class CheckovClient:
    """Wrapper mínimo para execução do Checkov."""

    def __init__(self, config=None):
        self.logger = logger.bind(service='checkov_client')
        self.timeout = getattr(config, 'checkov_timeout_seconds', 300) if config else 300

    async def scan_iac(self, directory: str) -> CheckovReport:
        """Executa scan de IaC (stub async)."""
        self.logger.info('checkov_scan_started', directory=directory)
        await asyncio.sleep(1)
        findings: List[dict] = []
        return CheckovReport(
            passed=True,
            findings=findings,
            duration_seconds=1.0,
            logs=['Checkov scan simulated']
        )
