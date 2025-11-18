"""
TrivyClient - Cliente para scanning de secrets com Trivy.

Responsável por:
- Scanning de configurações em busca de secrets
- Scanning de parameters de ExecutionTickets
- Detecção de credenciais expostas
- Scanning de imagens Docker (futuro)
"""

from typing import List, Dict, Optional
import structlog
import httpx
import json
import yaml
import asyncio
import time
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class TrivyClient:
    """
    Cliente para interação com Trivy scanner.
    """

    def __init__(
        self,
        base_url: str = "http://trivy:8080",
        timeout: float = 30.0
    ):
        """
        Inicializa o TrivyClient.

        Args:
            base_url: URL base do Trivy server
            timeout: Timeout em segundos para requests
        """
        self.base_url = base_url
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        """
        Inicializa cliente HTTP e verifica conectividade.

        Raises:
            Exception se Trivy não estiver disponível
        """
        try:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )

            # Verificar conectividade
            response = await self.client.get("/healthz")
            response.raise_for_status()

            logger.info(
                "trivy_client.connected",
                base_url=self.base_url
            )

        except Exception as e:
            logger.error(
                "trivy_client.connection_failed",
                base_url=self.base_url,
                error=str(e)
            )
            raise

    async def close(self) -> None:
        """
        Fecha cliente HTTP.
        """
        if self.client:
            await self.client.aclose()
            logger.info("trivy_client.closed")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def scan_config(
        self,
        config_content: str,
        config_type: str = "yaml"
    ) -> dict:
        """
        Escaneia configuração em busca de secrets.

        Args:
            config_content: Conteúdo da configuração
            config_type: Tipo da configuração (yaml, json, etc)

        Returns:
            Resultado do scanning com secrets encontrados

        Raises:
            Exception se scanning falhar
        """
        if not self.client:
            raise Exception("Trivy client not connected")

        start_time = time.time()
        scan_status = "success"

        try:
            # Preparar payload para Trivy
            payload = {
                "target": "config",
                "scanners": ["secret"],
                "config": {
                    "content": config_content,
                    "type": config_type
                }
            }

            # Executar scan
            response = await self.client.post(
                "/scan",
                json=payload
            )
            response.raise_for_status()

            result = response.json()

            # Extrair secrets encontrados
            secrets = self._extract_secrets(result)

            logger.info(
                "trivy_client.scan_complete",
                secrets_found=len(secrets),
                config_type=config_type
            )

            return {
                "secrets": secrets,
                "scan_metadata": {
                    "scanner": "trivy",
                    "config_type": config_type,
                    "scan_time": result.get("scan_time")
                }
            }

        except httpx.HTTPStatusError as e:
            scan_status = "error"
            logger.error(
                "trivy_client.scan_failed",
                status_code=e.response.status_code,
                error=str(e)
            )
            raise

        except Exception as e:
            scan_status = "error"
            logger.error("trivy_client.scan_error", error=str(e))
            raise

        finally:
            # Registrar métricas
            try:
                from src.observability.metrics import trivy_scans_total, trivy_scan_duration_seconds
                duration = time.time() - start_time
                trivy_scans_total.labels(scan_type="config", status=scan_status).inc()
                trivy_scan_duration_seconds.observe(duration)
            except Exception:
                pass  # Não falhar se métricas falharem

    async def scan_parameters(self, parameters: dict) -> List[dict]:
        """
        Escaneia parameters de ExecutionTicket em busca de secrets.

        Args:
            parameters: Dicionário de parameters do ticket

        Returns:
            Lista de secrets encontrados

        Raises:
            Exception se scanning falhar
        """
        try:
            # Converter parameters para YAML temporário
            config_content = yaml.dump(parameters, default_flow_style=False)

            # Executar scan
            result = await self.scan_config(config_content, config_type="yaml")

            secrets = result.get("secrets", [])

            if secrets:
                logger.warning(
                    "trivy_client.secrets_detected_in_parameters",
                    secrets_count=len(secrets),
                    secret_types=[s.get("type") for s in secrets]
                )

            return secrets

        except Exception as e:
            logger.error(
                "trivy_client.scan_parameters_failed",
                error=str(e)
            )
            # Retornar lista vazia em caso de erro (graceful degradation)
            return []

    async def scan_image(self, image: str) -> dict:
        """
        Escaneia imagem Docker em busca de vulnerabilidades e secrets.

        Args:
            image: Nome da imagem Docker

        Returns:
            Resultado do scanning da imagem

        Raises:
            Exception se scanning falhar

        Note:
            Implementação futura para Phase 3
        """
        if not self.client:
            raise Exception("Trivy client not connected")

        start_time = time.time()
        scan_status = "success"

        try:
            payload = {
                "target": "image",
                "image": image,
                "scanners": ["vuln", "secret"]
            }

            response = await self.client.post(
                "/scan",
                json=payload
            )
            response.raise_for_status()

            result = response.json()

            logger.info(
                "trivy_client.image_scan_complete",
                image=image,
                vulnerabilities=len(result.get("vulnerabilities", [])),
                secrets=len(self._extract_secrets(result))
            )

            return result

        except Exception as e:
            scan_status = "error"
            logger.error(
                "trivy_client.scan_image_failed",
                image=image,
                error=str(e)
            )
            raise

        finally:
            # Registrar métricas
            try:
                from src.observability.metrics import trivy_scans_total, trivy_scan_duration_seconds
                duration = time.time() - start_time
                trivy_scans_total.labels(scan_type="image", status=scan_status).inc()
                trivy_scan_duration_seconds.observe(duration)
            except Exception:
                pass  # Não falhar se métricas falharem

    def _extract_secrets(self, scan_result: dict) -> List[dict]:
        """
        Extrai secrets do resultado do scan Trivy.

        Args:
            scan_result: Resultado completo do scan

        Returns:
            Lista de secrets encontrados formatados
        """
        secrets = []

        # Trivy retorna secrets em diferentes formatos dependendo da versão
        # Suportar ambos os formatos

        # Formato 1: results -> secrets
        results = scan_result.get("Results", [])
        for result in results:
            for secret in result.get("Secrets", []):
                secrets.append(self._format_secret(secret))

        # Formato 2: secrets direto
        for secret in scan_result.get("secrets", []):
            secrets.append(self._format_secret(secret))

        return secrets

    def _format_secret(self, secret: dict) -> dict:
        """
        Formata secret para formato padronizado.

        Args:
            secret: Secret bruto do Trivy

        Returns:
            Secret formatado
        """
        return {
            "type": self._normalize_secret_type(secret.get("RuleID", "unknown")),
            "match": secret.get("Match", ""),
            "line": secret.get("StartLine", 0),
            "title": secret.get("Title", ""),
            "severity": secret.get("Severity", "UNKNOWN"),
            "category": secret.get("Category", "secret")
        }

    def _normalize_secret_type(self, rule_id: str) -> str:
        """
        Normaliza tipo de secret para categorias conhecidas.

        Args:
            rule_id: Rule ID do Trivy

        Returns:
            Tipo normalizado do secret
        """
        # Mapeamento de rule IDs para tipos conhecidos
        type_mapping = {
            "aws-access-key-id": "aws-access-key",
            "aws-secret-access-key": "aws-secret-key",
            "github-pat": "github-token",
            "github-token": "github-token",
            "gitlab-token": "gitlab-token",
            "slack-token": "slack-token",
            "slack-webhook": "slack-webhook",
            "private-key": "private-key",
            "rsa-private-key": "rsa-private-key",
            "ssh-private-key": "ssh-private-key",
            "jwt": "jwt-token",
            "generic-api-key": "api-key",
            "password": "password",
            "connection-string": "database-connection-string"
        }

        # Normalizar rule_id para lowercase
        rule_id_lower = rule_id.lower()

        # Buscar mapeamento exato
        for key, value in type_mapping.items():
            if key in rule_id_lower:
                return value

        # Default: retornar rule_id original
        return rule_id

    async def health_check(self) -> bool:
        """
        Verifica saúde do Trivy server.

        Returns:
            True se Trivy está saudável
        """
        try:
            if not self.client:
                return False

            response = await self.client.get("/healthz")
            return response.status_code == 200

        except Exception as e:
            logger.warning("trivy_client.health_check_failed", error=str(e))
            return False
