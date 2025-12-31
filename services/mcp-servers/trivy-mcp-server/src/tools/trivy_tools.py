"""
Ferramentas MCP que wrapeiam o Trivy CLI.

Fornece ferramentas para scanning de:
- Imagens de container
- Sistemas de arquivos
- Repositórios Git
"""

import asyncio
import json
import shutil
import time
from typing import Any

import structlog
from fastmcp import FastMCP

from ..config import get_settings
from ..observability.metrics import (
    record_scan,
    record_scan_duration,
    record_vulnerabilities
)

logger = structlog.get_logger(__name__)


async def _execute_trivy(
    args: list[str],
    timeout: int | None = None
) -> dict[str, Any]:
    """
    Executa comando Trivy CLI.

    Args:
        args: Argumentos para o comando trivy
        timeout: Timeout em segundos (usa configuração se não especificado)

    Returns:
        Dicionário com resultado do scan ou erro
    """
    settings = get_settings()
    timeout = timeout or settings.trivy_timeout

    # Verificar se Trivy está disponível
    trivy_path = shutil.which(settings.trivy_path)
    if not trivy_path:
        return {
            "error": "Trivy CLI not found",
            "message": f"Trivy não está instalado ou não está no PATH: {settings.trivy_path}"
        }

    # Construir comando completo
    cmd = [trivy_path] + args + ["--format", "json", "--cache-dir", settings.trivy_cache_dir]

    logger.info("executing_trivy", command=cmd)
    start_time = time.time()

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )

        duration = time.time() - start_time

        if process.returncode != 0:
            logger.error(
                "trivy_execution_failed",
                returncode=process.returncode,
                stderr=stderr.decode()
            )
            return {
                "error": "Trivy execution failed",
                "returncode": process.returncode,
                "stderr": stderr.decode(),
                "duration_seconds": duration
            }

        # Parsear output JSON
        try:
            result = json.loads(stdout.decode())
            logger.info(
                "trivy_scan_completed",
                duration=duration
            )
            return {
                "success": True,
                "result": result,
                "duration_seconds": duration
            }
        except json.JSONDecodeError as e:
            return {
                "error": "Failed to parse Trivy output",
                "message": str(e),
                "stdout": stdout.decode()[:1000],
                "duration_seconds": duration
            }

    except asyncio.TimeoutError:
        duration = time.time() - start_time
        logger.error("trivy_timeout", timeout=timeout)
        return {
            "error": "Trivy scan timed out",
            "timeout_seconds": timeout,
            "duration_seconds": duration
        }
    except Exception as e:
        duration = time.time() - start_time
        logger.exception("trivy_execution_error", error=str(e))
        return {
            "error": "Trivy execution error",
            "message": str(e),
            "duration_seconds": duration
        }


def _count_vulnerabilities(result: dict[str, Any]) -> dict[str, int]:
    """Conta vulnerabilidades por severidade."""
    counts: dict[str, int] = {
        "CRITICAL": 0,
        "HIGH": 0,
        "MEDIUM": 0,
        "LOW": 0,
        "UNKNOWN": 0
    }

    # Navegar na estrutura do resultado Trivy
    results = result.get("Results", [])
    for r in results:
        vulnerabilities = r.get("Vulnerabilities", [])
        for vuln in vulnerabilities:
            severity = vuln.get("Severity", "UNKNOWN")
            counts[severity] = counts.get(severity, 0) + 1

    return counts


def register_trivy_tools(mcp: FastMCP) -> None:
    """Registra ferramentas Trivy no servidor MCP."""

    @mcp.tool()
    async def scan_image(
        image: str,
        severity: str = "HIGH,CRITICAL",
        ignore_unfixed: bool = True
    ) -> dict[str, Any]:
        """
        Escaneia imagem de container para vulnerabilidades usando Trivy.

        Args:
            image: Nome da imagem (ex: nginx:latest, alpine:3.18)
            severity: Severidades a reportar (CRITICAL, HIGH, MEDIUM, LOW)
            ignore_unfixed: Ignorar vulnerabilidades sem correção disponível

        Returns:
            Resultado do scan com vulnerabilidades encontradas
        """
        start_time = time.time()

        args = ["image", image, "--severity", severity]
        if ignore_unfixed:
            args.append("--ignore-unfixed")

        result = await _execute_trivy(args)
        duration = time.time() - start_time

        # Registrar métricas
        status = "success" if result.get("success") else "error"
        record_scan("image", status)
        record_scan_duration("image", duration)

        if result.get("success"):
            counts = _count_vulnerabilities(result.get("result", {}))
            for sev, count in counts.items():
                if count > 0:
                    record_vulnerabilities(sev, count)

            return {
                "success": True,
                "image": image,
                "vulnerability_counts": counts,
                "total_vulnerabilities": sum(counts.values()),
                "full_result": result.get("result"),
                "duration_seconds": duration
            }

        return result

    @mcp.tool()
    async def scan_filesystem(
        path: str,
        scanners: str = "vuln,config,secret",
        severity: str = "HIGH,CRITICAL"
    ) -> dict[str, Any]:
        """
        Escaneia sistema de arquivos para vulnerabilidades e misconfigurations.

        Args:
            path: Caminho do diretório a escanear
            scanners: Tipos de scan (vuln, config, secret, license)
            severity: Severidades a reportar

        Returns:
            Resultado do scan com issues encontrados
        """
        start_time = time.time()

        args = ["fs", path, "--scanners", scanners, "--severity", severity]

        result = await _execute_trivy(args)
        duration = time.time() - start_time

        status = "success" if result.get("success") else "error"
        record_scan("filesystem", status)
        record_scan_duration("filesystem", duration)

        if result.get("success"):
            counts = _count_vulnerabilities(result.get("result", {}))
            return {
                "success": True,
                "path": path,
                "scanners": scanners,
                "vulnerability_counts": counts,
                "total_vulnerabilities": sum(counts.values()),
                "full_result": result.get("result"),
                "duration_seconds": duration
            }

        return result

    @mcp.tool()
    async def scan_repository(
        repo_url: str,
        branch: str = "main",
        severity: str = "HIGH,CRITICAL"
    ) -> dict[str, Any]:
        """
        Escaneia repositório Git para vulnerabilidades.

        Args:
            repo_url: URL do repositório Git
            branch: Branch a escanear
            severity: Severidades a reportar

        Returns:
            Resultado do scan com vulnerabilidades encontradas
        """
        start_time = time.time()

        args = ["repo", repo_url, "--branch", branch, "--severity", severity]

        result = await _execute_trivy(args)
        duration = time.time() - start_time

        status = "success" if result.get("success") else "error"
        record_scan("repository", status)
        record_scan_duration("repository", duration)

        if result.get("success"):
            counts = _count_vulnerabilities(result.get("result", {}))
            return {
                "success": True,
                "repo_url": repo_url,
                "branch": branch,
                "vulnerability_counts": counts,
                "total_vulnerabilities": sum(counts.values()),
                "full_result": result.get("result"),
                "duration_seconds": duration
            }

        return result
