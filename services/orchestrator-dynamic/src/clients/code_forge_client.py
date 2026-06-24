"""
HTTP Client para Code-Forge Service.

Fornece interface para chamar os pipelines do code-forge
a partir das activities do Fluxo G.
"""

import asyncio
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential


logger = structlog.get_logger(__name__)


class CodeForgeClientError(Exception):
    """Erro base do CodeForgeClient."""

    pass


class CodeForgeClient:
    """
    Cliente HTTP para o Code-Forge Service.

    Fornece métodos para:
    - Trigger pipeline de geração de código
    - Consultar status do pipeline
    - Aguardar conclusão do pipeline
    """

    def __init__(
        self,
        base_url: str = "code-forge.neural-hive.svc.cluster.local",
        port: int = 8080,
        timeout: float = 600.0,  # 10 minutos default
    ):
        """
        Inicializa o cliente do Code-Forge.

        Args:
            base_url: URL base do serviço code-forge
            port: Porta do serviço
            timeout: Timeout padrão para requisições (segundos)
        """
        self.base_url = f"http://{base_url}:{port}"
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self.logger = logger.bind(component="code_forge_client")

    async def initialize(self):
        """Inicializa o cliente HTTP."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
        self.logger.info("code_forge_client_initialized", base_url=self.base_url)

    async def close(self):
        """Fecha o cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _check_available(self) -> bool:
        """Verifica se o cliente está disponível."""
        return self._client is not None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def trigger_pipeline(
        self,
        artifact_id: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Dispara um pipeline de geração de código.

        Args:
            artifact_id: ID do artefato a ser gerado
            parameters: Parâmetros opcionais do pipeline

        Returns:
            Dict com pipeline_id e status inicial

        Raises:
            CodeForgeClientError: Se a requisição falhar
        """
        if not self._check_available():
            raise CodeForgeClientError("Cliente não inicializado")

        url = "/api/v1/pipelines"
        payload = {
            "artifact_id": artifact_id,
            "parameters": parameters or {},
        }

        self.logger.info("triggering_pipeline", artifact_id=artifact_id)

        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()

            result = response.json()
            self.logger.info(
                "pipeline_triggered",
                pipeline_id=result.get("pipeline_id"),
                status=result.get("status"),
            )
            return result

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "pipeline_trigger_failed",
                status_code=e.response.status_code,
                response=e.response.text,
            )
            raise CodeForgeClientError(f"Falha ao trigger pipeline: {e}") from e
        except httpx.RequestError as e:
            self.logger.error("pipeline_trigger_request_error", error=str(e))
            raise CodeForgeClientError(f"Erro de requisição: {e}") from e

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def get_pipeline_status(self, pipeline_id: str) -> dict[str, Any]:
        """
        Consulta o status de um pipeline.

        Args:
            pipeline_id: ID do pipeline

        Returns:
            Dict com status atual do pipeline

        Raises:
            CodeForgeClientError: Se a requisição falhar
        """
        if not self._check_available():
            raise CodeForgeClientError("Cliente não inicializado")

        url = f"/api/v1/pipelines/{pipeline_id}"

        try:
            response = await self._client.get(url)

            if response.status_code == 404:
                return {"pipeline_id": pipeline_id, "status": "not_found"}

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"pipeline_id": pipeline_id, "status": "not_found"}
            self.logger.error(
                "pipeline_status_failed",
                status_code=e.response.status_code,
                response=e.response.text,
            )
            raise CodeForgeClientError(f"Falha ao consultar status: {e}") from e
        except httpx.RequestError as e:
            self.logger.error("pipeline_status_request_error", error=str(e))
            raise CodeForgeClientError(f"Erro de requisição: {e}") from e

    async def wait_for_completion(
        self,
        pipeline_id: str,
        timeout: float = 600.0,
        poll_interval: float = 5.0,
    ) -> dict[str, Any]:
        """
        Aguarda a conclusão de um pipeline.

        Args:
            pipeline_id: ID do pipeline
            timeout: Timeout máximo em segundos
            poll_interval: Intervalo entre consultas em segundos

        Returns:
            Dict com resultado final do pipeline

        Raises:
            CodeForgeClientError: Se timeout ou erro
        """
        self.logger.info("waiting_pipeline_completion", pipeline_id=pipeline_id)

        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise CodeForgeClientError(
                    f"Timeout aguardando pipeline {pipeline_id} após {timeout}s"
                )

            status = await self.get_pipeline_status(pipeline_id)

            current_status = status.get("status")
            self.logger.debug(
                "pipeline_status_check",
                pipeline_id=pipeline_id,
                status=current_status,
                stage=status.get("stage"),
                elapsed=f"{elapsed:.1f}s",
            )

            # Estados terminais
            if current_status in ("completed", "failed", "cancelled"):
                self.logger.info(
                    "pipeline_completed",
                    pipeline_id=pipeline_id,
                    final_status=current_status,
                    duration_ms=status.get("duration_ms"),
                )
                return status

            # Se não for terminal, aguardar e consultar novamente
            await asyncio.sleep(poll_interval)

    async def trigger_and_wait(
        self,
        artifact_id: str,
        parameters: dict[str, Any] | None = None,
        timeout: float = 600.0,
    ) -> dict[str, Any]:
        """
        Dispara pipeline e aguarda conclusão.

        Args:
            artifact_id: ID do artefato
            parameters: Parâmetros do pipeline
            timeout: Timeout máximo

        Returns:
            Dict com resultado final
        """
        trigger_result = await self.trigger_pipeline(artifact_id, parameters)
        pipeline_id = trigger_result.get("pipeline_id")

        if not pipeline_id:
            raise CodeForgeClientError("Pipeline ID não retornado")

        return await self.wait_for_completion(pipeline_id, timeout)


# Singleton global
_client: CodeForgeClient | None = None


def get_code_forge_client() -> CodeForgeClient | None:
    """Retorna o cliente singleton."""
    return _client


async def initialize_code_forge_client(
    base_url: str = "code-forge.neural-hive.svc.cluster.local",
    port: int = 8080,
) -> CodeForgeClient:
    """
    Inicializa o cliente singleton do Code-Forge.

    Args:
        base_url: URL base do serviço
        port: Porta do serviço

    Returns:
        CodeForgeClient inicializado
    """
    global _client

    if _client is None:
        _client = CodeForgeClient(base_url=base_url, port=port)
        await _client.initialize()

    return _client


async def close_code_forge_client():
    """Fecha o cliente singleton do Code-Forge."""
    global _client

    if _client:
        await _client.close()
        _client = None
