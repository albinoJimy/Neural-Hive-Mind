"""
Ferramentas MCP que wrapeiam a API do SonarQube.

Fornece ferramentas para:
- Verificar status do Quality Gate
- Buscar issues de código
- Obter métricas de qualidade
"""

import time
from typing import Any

import structlog
from fastmcp import FastMCP

from ..clients import SonarQubeClient

logger = structlog.get_logger(__name__)

# Cliente singleton
_client: SonarQubeClient | None = None


def get_client() -> SonarQubeClient:
    """Retorna cliente SonarQube singleton."""
    global _client
    if _client is None:
        _client = SonarQubeClient()
    return _client


def register_sonarqube_tools(mcp: FastMCP) -> None:
    """Registra ferramentas SonarQube no servidor MCP."""

    @mcp.tool()
    async def get_quality_gate(
        project_key: str
    ) -> dict[str, Any]:
        """
        Obtém status do Quality Gate para um projeto SonarQube.

        Args:
            project_key: Chave do projeto no SonarQube (ex: my-project)

        Returns:
            Status do Quality Gate (PASSED, FAILED, ERROR)
        """
        start_time = time.time()
        client = get_client()

        result = await client.get_quality_gate(project_key)
        duration = time.time() - start_time

        if "error" in result:
            return {
                "success": False,
                "project_key": project_key,
                "error": result.get("error"),
                "message": result.get("message"),
                "duration_seconds": duration
            }

        project_status = result.get("projectStatus", {})
        status = project_status.get("status", "UNKNOWN")

        conditions = []
        for condition in project_status.get("conditions", []):
            conditions.append({
                "metric": condition.get("metricKey"),
                "status": condition.get("status"),
                "value": condition.get("actualValue"),
                "threshold": condition.get("errorThreshold")
            })

        return {
            "success": True,
            "project_key": project_key,
            "status": status,
            "conditions": conditions,
            "duration_seconds": duration
        }

    @mcp.tool()
    async def get_issues(
        project_key: str,
        severity: str = "MAJOR,CRITICAL,BLOCKER",
        issue_type: str = "BUG,VULNERABILITY,CODE_SMELL"
    ) -> dict[str, Any]:
        """
        Busca issues de código para um projeto SonarQube.

        Args:
            project_key: Chave do projeto no SonarQube
            severity: Severidades a filtrar (INFO, MINOR, MAJOR, CRITICAL, BLOCKER)
            issue_type: Tipos de issues (BUG, VULNERABILITY, CODE_SMELL, SECURITY_HOTSPOT)

        Returns:
            Lista de issues encontrados com localização e detalhes
        """
        start_time = time.time()
        client = get_client()

        result = await client.search_issues(
            project_key=project_key,
            severities=severity,
            types=issue_type
        )
        duration = time.time() - start_time

        if "error" in result:
            return {
                "success": False,
                "project_key": project_key,
                "error": result.get("error"),
                "message": result.get("message"),
                "duration_seconds": duration
            }

        issues = []
        for issue in result.get("issues", []):
            issues.append({
                "key": issue.get("key"),
                "severity": issue.get("severity"),
                "type": issue.get("type"),
                "message": issue.get("message"),
                "component": issue.get("component"),
                "line": issue.get("line"),
                "status": issue.get("status"),
                "effort": issue.get("effort"),
                "tags": issue.get("tags", [])
            })

        # Contar por severidade
        severity_counts: dict[str, int] = {}
        for issue in issues:
            sev = issue.get("severity", "UNKNOWN")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # Contar por tipo
        type_counts: dict[str, int] = {}
        for issue in issues:
            t = issue.get("type", "UNKNOWN")
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "success": True,
            "project_key": project_key,
            "total_issues": result.get("total", len(issues)),
            "severity_counts": severity_counts,
            "type_counts": type_counts,
            "issues": issues[:50],  # Limitar a 50 issues no retorno
            "duration_seconds": duration
        }

    @mcp.tool()
    async def get_metrics(
        project_key: str,
        metrics: str = "bugs,vulnerabilities,code_smells,coverage,duplicated_lines_density,ncloc"
    ) -> dict[str, Any]:
        """
        Obtém métricas de qualidade de código para um projeto.

        Args:
            project_key: Chave do projeto no SonarQube
            metrics: Métricas a obter (separadas por vírgula)

        Returns:
            Valores das métricas solicitadas
        """
        start_time = time.time()
        client = get_client()

        result = await client.get_component_measures(
            project_key=project_key,
            metrics=metrics
        )
        duration = time.time() - start_time

        if "error" in result:
            return {
                "success": False,
                "project_key": project_key,
                "error": result.get("error"),
                "message": result.get("message"),
                "duration_seconds": duration
            }

        component = result.get("component", {})
        measures = {}

        for measure in component.get("measures", []):
            metric = measure.get("metric")
            value = measure.get("value")

            # Converter valores numéricos
            try:
                if "." in str(value):
                    value = float(value)
                else:
                    value = int(value)
            except (ValueError, TypeError):
                pass

            measures[metric] = value

        return {
            "success": True,
            "project_key": project_key,
            "component_name": component.get("name"),
            "measures": measures,
            "duration_seconds": duration
        }

    @mcp.tool()
    async def wait_for_analysis(
        task_id: str,
        timeout_seconds: int = 300
    ) -> dict[str, Any]:
        """
        Aguarda conclusão de uma análise SonarQube.

        Args:
            task_id: ID da task de análise
            timeout_seconds: Tempo máximo de espera

        Returns:
            Status final da análise
        """
        start_time = time.time()
        client = get_client()

        # Calcular número de tentativas baseado no timeout
        poll_interval = 5
        max_attempts = timeout_seconds // poll_interval

        result = await client.wait_for_analysis(
            task_id=task_id,
            poll_interval=poll_interval,
            max_attempts=max_attempts
        )
        duration = time.time() - start_time

        if "error" in result:
            return {
                "success": False,
                "task_id": task_id,
                "error": result.get("error"),
                "message": result.get("message"),
                "duration_seconds": duration
            }

        task = result.get("task", {})

        return {
            "success": True,
            "task_id": task_id,
            "status": task.get("status"),
            "component_key": task.get("componentKey"),
            "analysis_id": task.get("analysisId"),
            "execution_time_ms": task.get("executionTimeMs"),
            "duration_seconds": duration
        }
