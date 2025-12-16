import os
from dataclasses import dataclass
from typing import List, Optional
import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class SonarQubeAnalysis:
    """Resumo de execução SonarQube."""

    task_id: str
    passed: bool
    issues: List[dict]
    duration_seconds: Optional[float]
    logs: Optional[list]


class SonarQubeClient:
    """Cliente SonarQube REST API simplificado."""

    def __init__(self, base_url: str, token: str, timeout: int = 600):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={'Authorization': f'Bearer {token}'},
            timeout=timeout
        )
        self.logger = logger.bind(service='sonarqube_client')

    @classmethod
    def from_env(cls, config=None):
        base_url = os.getenv('SONARQUBE_URL') or getattr(config, 'sonarqube_url', None)
        token = os.getenv('SONARQUBE_TOKEN') or getattr(config, 'sonarqube_token', None)
        if not base_url or not token:
            raise ValueError('SonarQube config not found')
        return cls(base_url, token, timeout=getattr(config, 'sonarqube_timeout_seconds', 600))

    async def trigger_analysis(self, project_key: str, sources_path: str) -> SonarQubeAnalysis:
        """Dispara análise. Em ambientes locais retorna resultado simulado."""
        if not project_key:
            raise ValueError('project_key required')
        # Stub: em produção, disparar scanner. Aqui retornamos resultado mockado.
        self.logger.info('sonarqube_analysis_triggered', project_key=project_key, sources=sources_path)
        issues = []
        return SonarQubeAnalysis(
            task_id='local-task',
            passed=True,
            issues=issues,
            duration_seconds=15.0,
            logs=['SonarQube analysis simulated']
        )
