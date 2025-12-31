"""
Cliente HTTP para SonarQube REST API.

Fornece métodos para interação com a API do SonarQube
com retry, timeout e tratamento de erros.
"""

import asyncio
from typing import Any, Optional

import aiohttp
import structlog

from ..config import get_settings

logger = structlog.get_logger(__name__)


class SonarQubeClient:
    """Cliente assíncrono para SonarQube REST API."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.sonarqube_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Retorna ou cria sessão HTTP."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.settings.sonarqube_timeout)
            headers = {}

            if self.settings.sonarqube_token:
                headers["Authorization"] = f"Bearer {self.settings.sonarqube_token}"

            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=headers
            )
        return self._session

    async def close(self) -> None:
        """Fecha a sessão HTTP."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        retries: int = 3
    ) -> dict[str, Any]:
        """
        Executa requisição HTTP com retry.

        Args:
            method: Método HTTP (GET, POST, etc)
            endpoint: Endpoint da API (ex: /api/qualitygates/project_status)
            params: Query parameters
            data: Body da requisição
            retries: Número de tentativas

        Returns:
            Resposta JSON da API
        """
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"

        for attempt in range(retries):
            try:
                async with session.request(
                    method,
                    url,
                    params=params,
                    json=data
                ) as response:
                    if response.status == 401:
                        return {
                            "error": "Authentication failed",
                            "message": "Token SonarQube inválido ou expirado"
                        }

                    if response.status == 404:
                        return {
                            "error": "Not found",
                            "message": f"Recurso não encontrado: {endpoint}"
                        }

                    if response.status >= 400:
                        text = await response.text()
                        return {
                            "error": f"HTTP {response.status}",
                            "message": text[:500]
                        }

                    return await response.json()

            except asyncio.TimeoutError:
                logger.warning(
                    "sonarqube_request_timeout",
                    attempt=attempt + 1,
                    endpoint=endpoint
                )
                if attempt == retries - 1:
                    return {
                        "error": "Timeout",
                        "message": f"Timeout após {retries} tentativas"
                    }
                await asyncio.sleep(2 ** attempt)

            except aiohttp.ClientError as e:
                logger.warning(
                    "sonarqube_request_error",
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt == retries - 1:
                    return {
                        "error": "Connection error",
                        "message": str(e)
                    }
                await asyncio.sleep(2 ** attempt)

        return {"error": "Unknown error"}

    async def get_quality_gate(self, project_key: str) -> dict[str, Any]:
        """
        Obtém status do Quality Gate para um projeto.

        Args:
            project_key: Chave do projeto no SonarQube

        Returns:
            Status do Quality Gate
        """
        return await self._request(
            "GET",
            "/api/qualitygates/project_status",
            params={"projectKey": project_key}
        )

    async def search_issues(
        self,
        project_key: str,
        severities: str = "MAJOR,CRITICAL,BLOCKER",
        types: str = "BUG,VULNERABILITY,CODE_SMELL",
        page_size: int = 100
    ) -> dict[str, Any]:
        """
        Busca issues de um projeto.

        Args:
            project_key: Chave do projeto
            severities: Severidades a filtrar
            types: Tipos de issues a filtrar
            page_size: Número de issues por página

        Returns:
            Lista de issues encontrados
        """
        return await self._request(
            "GET",
            "/api/issues/search",
            params={
                "componentKeys": project_key,
                "severities": severities,
                "types": types,
                "ps": page_size
            }
        )

    async def get_component_measures(
        self,
        project_key: str,
        metrics: str = "bugs,vulnerabilities,code_smells,coverage,duplicated_lines_density"
    ) -> dict[str, Any]:
        """
        Obtém métricas de um componente.

        Args:
            project_key: Chave do projeto
            metrics: Métricas a buscar

        Returns:
            Métricas do componente
        """
        return await self._request(
            "GET",
            "/api/measures/component",
            params={
                "component": project_key,
                "metricKeys": metrics
            }
        )

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """
        Obtém status de uma task de análise.

        Args:
            task_id: ID da task

        Returns:
            Status da task
        """
        return await self._request(
            "GET",
            "/api/ce/task",
            params={"id": task_id}
        )

    async def wait_for_analysis(
        self,
        task_id: str,
        poll_interval: Optional[int] = None,
        max_attempts: Optional[int] = None
    ) -> dict[str, Any]:
        """
        Aguarda conclusão de uma análise.

        Args:
            task_id: ID da task
            poll_interval: Intervalo entre verificações (segundos)
            max_attempts: Número máximo de tentativas

        Returns:
            Status final da task
        """
        poll_interval = poll_interval or self.settings.sonarqube_poll_interval
        max_attempts = max_attempts or self.settings.sonarqube_max_poll_attempts

        for attempt in range(max_attempts):
            result = await self.get_task_status(task_id)

            if "error" in result:
                return result

            status = result.get("task", {}).get("status")

            if status == "SUCCESS":
                return {
                    "success": True,
                    "status": status,
                    "task": result.get("task")
                }
            elif status in ("FAILED", "CANCELED"):
                return {
                    "error": f"Analysis {status.lower()}",
                    "task": result.get("task")
                }

            logger.debug(
                "waiting_for_analysis",
                task_id=task_id,
                status=status,
                attempt=attempt + 1
            )
            await asyncio.sleep(poll_interval)

        return {
            "error": "Timeout",
            "message": f"Análise não concluída após {max_attempts * poll_interval}s"
        }
