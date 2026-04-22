"""
MCP Client Integration for Analyst Agents.
Integra com scout-mcp-server e optimizer-mcp-server.
"""

import json
from typing import Any, Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()


class MCPIntegrationError(Exception):
    """Erro na integração MCP."""


class MCPIntegration:
    """Cliente para integração com MCP Servers."""

    def __init__(
        self,
        scout_url: str = "http://scout-mcp-server:8000",
        optimizer_url: str = "http://optimizer-mcp-server:8001",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.scout_url = scout_url
        self.optimizer_url = optimizer_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def initialize(self):
        """Inicializar cliente HTTP."""
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self):
        """Fechar cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _post(self, url: str, data: dict[str, Any]) -> dict[str, Any]:
        """Executar POST request com retry."""
        if not self._client:
            raise MCPIntegrationError("Client not initialized")

        try:
            response = await self._client.post(url, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error("mcp_http_error", url=url, error=str(e))
            raise MCPIntegrationError(f"HTTP error: {e}")
        except json.JSONDecodeError as e:
            logger.error("mcp_json_error", url=url, error=str(e))
            raise MCPIntegrationError(f"JSON decode error: {e}")

    async def scout_list_files(
        self, path: str = ".", pattern: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Listar arquivos via scout MCP server.

        Args:
            path: Caminho base para busca
            pattern: Padrão de filtro (opcional)

        Returns:
            Lista de arquivos encontrados
        """
        url = f"{self.scout_url}/tools/list_files"
        payload = {"path": path}
        if pattern:
            payload["pattern"] = pattern

        result = await self._post(url, payload)

        if result.get("status") != "success":
            raise MCPIntegrationError(f"Scout list_files failed: {result.get('error')}")

        return result.get("data", {}).get("files", [])

    async def scout_search_code(
        self, query: str, path: str = ".", file_pattern: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Buscar código via scout MCP server.

        Args:
            query: Query de busca
            path: Caminho base para busca
            file_pattern: Padrão de arquivo (opcional)

        Returns:
            Lista de resultados da busca
        """
        url = f"{self.scout_url}/tools/search_code"
        payload = {"query": query, "path": path}
        if file_pattern:
            payload["file_pattern"] = file_pattern

        result = await self._post(url, payload)

        if result.get("status") != "success":
            raise MCPIntegrationError(f"Scout search_code failed: {result.get('error')}")

        return result.get("data", {}).get("matches", [])

    async def scout_analyze_structure(self, path: str = ".") -> dict[str, Any]:
        """
        Analisar estrutura do código via scout MCP server.

        Args:
            path: Caminho base para análise

        Returns:
            Estrutura analisada
        """
        url = f"{self.scout_url}/tools/analyze_structure"
        payload = {"path": path}

        result = await self._post(url, payload)

        if result.get("status") != "success":
            raise MCPIntegrationError(f"Scout analyze_structure failed: {result.get('error')}")

        return result.get("data", {})

    async def optimizer_analyze_performance(self, code: str) -> dict[str, Any]:
        """
        Analisar performance via optimizer MCP server.

        Args:
            code: Código para analisar

        Returns:
            Análise de performance
        """
        url = f"{self.optimizer_url}/tools/analyze_performance"
        payload = {"code": code, "language": "python"}

        result = await self._post(url, payload)

        if result.get("status") != "success":
            raise MCPIntegrationError(
                f"Optimizer analyze_performance failed: {result.get('error')}"
            )

        return result.get("data", {})

    async def optimizer_suggest_refactors(self, code: str) -> list[dict[str, Any]]:
        """
        Sugerir refatorações via optimizer MCP server.

        Args:
            code: Código para analisar

        Returns:
            Lista de sugestões de refatoração
        """
        url = f"{self.optimizer_url}/tools/suggest_refactors"
        payload = {"code": code, "language": "python"}

        result = await self._post(url, payload)

        if result.get("status") != "success":
            raise MCPIntegrationError(f"Optimizer suggest_refactors failed: {result.get('error')}")

        return result.get("data", {}).get("suggestions", [])

    async def optimizer_optimize_queries(self, queries: list[str]) -> list[dict[str, Any]]:
        """
        Otimizar queries via optimizer MCP server.

        Args:
            queries: Lista de queries para otimizar

        Returns:
            Lista de queries otimizadas
        """
        url = f"{self.optimizer_url}/tools/optimize_queries"
        payload = {"queries": queries}

        result = await self._post(url, payload)

        if result.get("status") != "success":
            raise MCPIntegrationError(f"Optimizer optimize_queries failed: {result.get('error')}")

        return result.get("data", {}).get("optimized", [])

    async def execute_aggregated_analysis(
        self,
        analysis_type: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Executar análise agregada usando múltiplas ferramentas MCP.

        Args:
            analysis_type: Tipo de análise (code_discovery, performance_optimization)
            params: Parâmetros da análise

        Returns:
            Resultado agregado da análise
        """
        results = {
            "analysis_type": analysis_type,
            "tools_used": [],
            "data": {},
            "errors": [],
        }

        if analysis_type == "code_discovery":
            # Use scout tools
            try:
                files = await self.scout_list_files(
                    path=params.get("path", "."),
                    pattern=params.get("pattern"),
                )
                results["data"]["files"] = files
                results["tools_used"].append("scout_list_files")
            except MCPIntegrationError as e:
                results["errors"].append(f"scout_list_files: {e}")

            try:
                structure = await self.scout_analyze_structure(path=params.get("path", "."))
                results["data"]["structure"] = structure
                results["tools_used"].append("scout_analyze_structure")
            except MCPIntegrationError as e:
                results["errors"].append(f"scout_analyze_structure: {e}")

        elif analysis_type == "performance_optimization":
            # Use optimizer tools
            code = params.get("code", "")
            if code:
                try:
                    perf_analysis = await self.optimizer_analyze_performance(code)
                    results["data"]["performance"] = perf_analysis
                    results["tools_used"].append("optimizer_analyze_performance")
                except MCPIntegrationError as e:
                    results["errors"].append(f"optimizer_analyze_performance: {e}")

                try:
                    refactors = await self.optimizer_suggest_refactors(code)
                    results["data"]["refactors"] = refactors
                    results["tools_used"].append("optimizer_suggest_refactors")
                except MCPIntegrationError as e:
                    results["errors"].append(f"optimizer_suggest_refactors: {e}")

        return results

    async def health_check(self) -> dict[str, bool]:
        """
        Verificar saúde dos servidores MCP.

        Returns:
            Dict com status de cada servidor
        """
        health = {"scout": False, "optimizer": False}

        # Check if client is initialized
        if not self._client:
            return health

        # Check scout
        try:
            response = await self._client.get(f"{self.scout_url}/health")
            health["scout"] = response.status_code == 200
        except Exception:
            health["scout"] = False

        # Check optimizer
        try:
            response = await self._client.get(f"{self.optimizer_url}/health")
            health["optimizer"] = response.status_code == 200
        except Exception:
            health["optimizer"] = False

        return health
