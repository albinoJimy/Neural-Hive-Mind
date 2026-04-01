"""Cliente HTTP para integração com Optimizer MCP Server."""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx


class Severity(Enum):
    """Níveis de severidade de problemas."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class OptimizationIssue:
    """Representa um problema encontrado."""

    file: str
    line: int
    column: int
    severity: str
    category: str
    message: str
    suggestion: str | None = None


@dataclass
class FileMetrics:
    """Métricas de um arquivo."""

    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    functions: int = 0
    classes: int = 0
    avg_function_length: float = 0.0
    max_function_length: int = 0
    max_complexity: int = 0


@dataclass
class FileAnalysisResult:
    """Resultado de análise de arquivo."""

    file_path: str
    metrics: FileMetrics
    issues: list[OptimizationIssue]
    issue_count: int
    summary: dict[str, str]


@dataclass
class DirectoryAnalysisResult:
    """Resultado de análise de diretório."""

    summary: dict[str, Any]
    severity_breakdown: dict[str, int]
    category_breakdown: dict[str, int]
    top_files: list[dict[str, Any]]
    issues: list[OptimizationIssue]


@dataclass
class OptimizationRecommendation:
    """Recomendação de otimização."""

    priority: str
    category: str
    title: str
    description: str
    actions: list[str]


@dataclass
class RecommendationsResult:
    """Resultado de recomendações."""

    path: str
    recommendations: list[OptimizationRecommendation]
    total_recommendations: int
    summary: dict[str, int]


class OptimizerMCPClientError(Exception):
    """Erro de comunicação com Optimizer MCP Server."""

    pass


class OptimizerMCPClient:
    """
    Cliente HTTP para comunicação com Optimizer MCP Server.

    O servidor expõe endpoints REST para análise de código:
    - /health - Health check
    - /analyze-file - Analisa arquivo específico
    - /analyze-directory - Analisa diretório completo
    - /recommendations - Gera recomendações de otimização
    - /code-smells - Detecta code smells
    - /execute - Executa ferramenta específica
    """

    def __init__(
        self,
        base_url: str = "http://optimizer-mcp-server.neural-hive-mind.svc.cluster.local:8080",
        timeout: float = 30.0,
    ):
        """
        Inicializa cliente.

        Args:
            base_url: URL base do Optimizer MCP Server
            timeout: Timeout para requisições (segundos)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Retorna cliente HTTP (lazy initialization)."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Fecha cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> dict[str, str]:
        """
        Verifica saúde do servidor.

        Returns:
            Dict com status do servidor
        """
        client = await self._get_client()
        try:
            response = await client.get("/health")
            response.raise_for_status()
            return await response.json()
        except httpx.HTTPError as e:
            raise OptimizerMCPClientError(f"Health check failed: {e}")

    async def analyze_file(self, file_path: str) -> FileAnalysisResult:
        """
        Analisa arquivo específico.

        Args:
            file_path: Caminho do arquivo (relativo ao base path do servidor)

        Returns:
            FileAnalysisResult com métricas e issues
        """
        client = await self._get_client()
        try:
            response = await client.get(
                "/analyze-file",
                params={"path": file_path},
            )
            response.raise_for_status()
            data = await response.json()

            metrics = FileMetrics(**data["metrics"])
            issues = [
                OptimizationIssue(
                    file=i["file"],
                    line=i["line"],
                    column=i["column"],
                    severity=i["severity"],
                    category=i["category"],
                    message=i["message"],
                    suggestion=i.get("suggestion"),
                )
                for i in data.get("issues", [])
            ]

            return FileAnalysisResult(
                file_path=data["file_path"],
                metrics=metrics,
                issues=issues,
                issue_count=data["issue_count"],
                summary=data["summary"],
            )

        except httpx.HTTPError as e:
            raise OptimizerMCPClientError(f"Analyze file failed: {e}")

    async def analyze_directory(
        self,
        path: str = ".",
        exclude_dirs: list[str] | None = None,
    ) -> DirectoryAnalysisResult:
        """
        Analisa diretório completo.

        Args:
            path: Caminho do diretório
            exclude_dirs: Diretórios a excluir

        Returns:
            DirectoryAnalysisResult com análise agregada
        """
        client = await self._get_client()
        try:
            params = {"path": path}
            if exclude_dirs:
                params["exclude_dirs"] = ",".join(exclude_dirs)

            response = await client.get("/analyze-directory", params=params)
            response.raise_for_status()
            data = await response.json()

            issues = [
                OptimizationIssue(
                    file=i["file"],
                    line=i["line"],
                    column=i["column"],
                    severity=i["severity"],
                    category=i["category"],
                    message=i["message"],
                    suggestion=i.get("suggestion"),
                )
                for i in data.get("issues", [])
            ]

            return DirectoryAnalysisResult(
                summary=data["summary"],
                severity_breakdown=data["severity_breakdown"],
                category_breakdown=data["category_breakdown"],
                top_files=data["top_files"],
                issues=issues,
            )

        except httpx.HTTPError as e:
            raise OptimizerMCPClientError(f"Analyze directory failed: {e}")

    async def get_recommendations(
        self,
        path: str = ".",
    ) -> RecommendationsResult:
        """
        Obtém recomendações de otimização.

        Args:
            path: Caminho do diretório

        Returns:
            RecommendationsResult com recomendações priorizadas
        """
        client = await self._get_client()
        try:
            response = await client.get(
                "/recommendations",
                params={"path": path},
            )
            response.raise_for_status()
            data = await response.json()

            recommendations = [
                OptimizationRecommendation(
                    priority=r["priority"],
                    category=r["category"],
                    title=r["title"],
                    description=r["description"],
                    actions=r["actions"],
                )
                for r in data.get("recommendations", [])
            ]

            return RecommendationsResult(
                path=data["path"],
                recommendations=recommendations,
                total_recommendations=data["total_recommendations"],
                summary=data["summary"],
            )

        except httpx.HTTPError as e:
            raise OptimizerMCPClientError(f"Get recommendations failed: {e}")

    async def detect_code_smells(
        self,
        path: str = ".",
        severity: str = "medium",
    ) -> dict[str, Any]:
        """
        Detecta code smells no projeto.

        Args:
            path: Caminho do diretório
            severity: Severidade mínima (low, medium, high, critical)

        Returns:
            Dict com code smells encontrados
        """
        client = await self._get_client()
        try:
            response = await client.get(
                "/code-smells",
                params={"path": path, "severity": severity},
            )
            response.raise_for_status()
            return await response.json()

        except httpx.HTTPError as e:
            raise OptimizerMCPClientError(f"Detect code smells failed: {e}")

    async def execute_tool(
        self,
        tool: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Executa ferramenta específica via POST /execute.

        Args:
            tool: Nome da ferramenta
            params: Parâmetros da ferramenta

        Returns:
            Resultado da execução
        """
        client = await self._get_client()
        try:
            response = await client.post(
                "/execute",
                json={"tool": tool, "params": params},
            )
            response.raise_for_status()
            return await response.json()

        except httpx.HTTPError as e:
            raise OptimizerMCPClientError(f"Execute tool failed: {e}")

    async def get_available_tools(self) -> list[dict[str, str]]:
        """
        Lista ferramentas disponíveis.

        Returns:
            Lista de ferramentas com nome e descrição
        """
        client = await self._get_client()
        try:
            response = await client.get("/tools")
            response.raise_for_status()
            data = await response.json()
            return data.get("tools", [])

        except httpx.HTTPError as e:
            raise OptimizerMCPClientError(f"Get tools failed: {e}")


# Cliente síncrono wrapper
class SyncOptimizerMCPClient:
    """Wrapper síncrono para OptimizerMCPClient."""

    def __init__(
        self,
        base_url: str = "http://optimizer-mcp-server.neural-hive-mind.svc.cluster.local:8080",
        timeout: float = 30.0,
    ):
        """
        Inicializa cliente síncrono.

        Args:
            base_url: URL base do Optimizer MCP Server
            timeout: Timeout para requisições (segundos)
        """
        self._async_client = OptimizerMCPClient(base_url=base_url, timeout=timeout)

    def health_check(self) -> dict[str, str]:
        """Verifica saúde do servidor."""
        return asyncio.run(self._async_client.health_check())

    def analyze_file(self, file_path: str) -> FileAnalysisResult:
        """Analisa arquivo específico."""
        return asyncio.run(self._async_client.analyze_file(file_path))

    def analyze_directory(
        self,
        path: str = ".",
        exclude_dirs: list[str] | None = None,
    ) -> DirectoryAnalysisResult:
        """Analisa diretório completo."""
        return asyncio.run(self._async_client.analyze_directory(path, exclude_dirs))

    def get_recommendations(self, path: str = ".") -> RecommendationsResult:
        """Obtém recomendações de otimização."""
        return asyncio.run(self._async_client.get_recommendations(path))

    def detect_code_smells(self, path: str = ".", severity: str = "medium") -> dict[str, Any]:
        """Detecta code smells no projeto."""
        return asyncio.run(self._async_client.detect_code_smells(path, severity))

    def execute_tool(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        """Executa ferramenta específica."""
        return asyncio.run(self._async_client.execute_tool(tool, params))

    def get_available_tools(self) -> list[dict[str, str]]:
        """Lista ferramentas disponíveis."""
        return asyncio.run(self._async_client.get_available_tools())

    def close(self) -> None:
        """Fecha cliente HTTP."""
        asyncio.run(self._async_client.close())
