"""
Code Forge client for code generation and CI/CD pipeline management.
"""

import httpx
import structlog
import asyncio
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class GenerationRequest(BaseModel):
    """Code generation request."""
    ticket_id: str
    template_id: str
    parameters: Dict[str, Any]
    target_repo: str
    branch: str


class GenerationStatus(BaseModel):
    """Generation status response."""
    request_id: str
    status: str
    artifacts: list[Dict[str, Any]] = []
    pipeline_id: Optional[str] = None
    error: Optional[str] = None


class PipelineStatus(BaseModel):
    """CI/CD pipeline status."""
    pipeline_id: str
    status: str
    stage: str
    duration_ms: int
    artifacts: list[Dict[str, Any]] = []
    sbom: Optional[Dict[str, Any]] = None
    signature: Optional[str] = None


class CodeForgeClient:
    """Client for Code Forge service."""

    def __init__(
        self,
        base_url: str = "http://code-forge.neural-hive-execution:8000",
        timeout: int = 14400,  # 4 hours for long pipelines
    ):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=timeout)
        self.logger = logger.bind(service="code_forge_client")

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("code_forge.submit_generation")
    async def submit_generation_request(
        self,
        ticket_id: str,
        template_id: str,
        parameters: Dict[str, Any],
    ) -> str:
        """
        Submit code generation request.

        Args:
            ticket_id: Execution ticket ID
            template_id: Template identifier
            parameters: Generation parameters

        Returns:
            Request ID
        """
        request = GenerationRequest(
            ticket_id=ticket_id,
            template_id=template_id,
            parameters=parameters,
            target_repo=parameters.get("target_repo", ""),
            branch=parameters.get("branch", "main"),
        )

        self.logger.info(
            "submitting_generation_request",
            ticket_id=ticket_id,
            template_id=template_id,
        )

        response = await self.client.post(
            f"{self.base_url}/api/v1/generate",
            json=request.model_dump(),
        )
        response.raise_for_status()

        request_id = response.json()["request_id"]
        self.logger.info("generation_submitted", request_id=request_id)
        return request_id

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("code_forge.get_generation_status")
    async def get_generation_status(self, request_id: str) -> GenerationStatus:
        """
        Get generation status.

        Args:
            request_id: Generation request ID

        Returns:
            Generation status
        """
        response = await self.client.get(
            f"{self.base_url}/api/v1/generate/{request_id}"
        )
        response.raise_for_status()

        return GenerationStatus(**response.json())

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("code_forge.trigger_pipeline")
    async def trigger_pipeline(self, artifact_id: str) -> str:
        """
        Trigger CI/CD pipeline for artifact.

        Args:
            artifact_id: Artifact identifier

        Returns:
            Pipeline ID
        """
        self.logger.info("triggering_pipeline", artifact_id=artifact_id)

        response = await self.client.post(
            f"{self.base_url}/api/v1/pipelines",
            json={"artifact_id": artifact_id},
        )
        response.raise_for_status()

        pipeline_id = response.json()["pipeline_id"]
        self.logger.info("pipeline_triggered", pipeline_id=pipeline_id)
        return pipeline_id

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("code_forge.get_pipeline_status")
    async def get_pipeline_status(self, pipeline_id: str) -> PipelineStatus:
        """
        Get pipeline execution status.

        Args:
            pipeline_id: Pipeline identifier

        Returns:
            Pipeline status
        """
        response = await self.client.get(
            f"{self.base_url}/api/v1/pipelines/{pipeline_id}"
        )
        response.raise_for_status()

        return PipelineStatus(**response.json())

    async def wait_for_pipeline_completion(
        self,
        pipeline_id: str,
        poll_interval: int = 30,
        timeout: int = 14400,
    ) -> PipelineStatus:
        """
        Wait for pipeline to complete (with polling).

        Args:
            pipeline_id: Pipeline identifier
            poll_interval: Polling interval in seconds
            timeout: Total timeout in seconds

        Returns:
            Final pipeline status

        Raises:
            TimeoutError: If pipeline doesn't complete within timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            status = await self.get_pipeline_status(pipeline_id)

            if status.status in ["completed", "failed", "cancelled"]:
                return status

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Pipeline {pipeline_id} timed out after {timeout}s")

            await asyncio.sleep(poll_interval)
