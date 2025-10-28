"""
Webhook handler para notificações de conclusão de pipelines CI/CD.
"""

import structlog
import hmac
import hashlib
import os
import json
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from prometheus_client import Counter

from neural_hive_integration import ExecutionTicketClient

logger = structlog.get_logger()

# Metrics
webhooks_received = Counter(
    "neural_hive_code_forge_webhooks_received_total",
    "Total webhooks received",
    ["source"],
)
pipelines_completed = Counter(
    "neural_hive_code_forge_pipelines_completed_total",
    "Total pipelines completed",
    ["status"],
)
signature_validation_failures = Counter(
    "neural_hive_code_forge_signature_validation_failures_total",
    "Total signature validation failures",
)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


class PipelineArtifact(BaseModel):
    """Artefato gerado pelo pipeline."""
    artifact_id: str
    artifact_type: str  # container, iac, library, etc
    location: str
    checksum: str


class SBOM(BaseModel):
    """Software Bill of Materials."""
    format: str  # cyclonedx, spdx
    version: str
    components: List[Dict[str, Any]]


class PipelineCompletedPayload(BaseModel):
    """Payload do webhook de pipeline completo."""
    pipeline_id: str
    artifact_id: str
    ticket_id: Optional[str] = None
    status: str  # completed, failed, cancelled
    duration_ms: int
    artifacts: List[PipelineArtifact] = []
    sbom: Optional[SBOM] = None
    signature: Optional[str] = None
    logs_url: Optional[str] = None
    metadata: Dict[str, Any] = {}


class WebhookHandler:
    """Handler para webhooks de pipelines."""

    def __init__(self, webhook_secret: Optional[str] = None):
        self.ticket_client = ExecutionTicketClient()
        self.logger = logger.bind(component="webhook_handler")
        # Obter secret do ambiente ou usar parâmetro
        self.webhook_secret = webhook_secret or os.getenv("WEBHOOK_SECRET", "")

    async def initialize(self):
        """Inicializar handler."""
        if not self.webhook_secret:
            self.logger.warning("webhook_secret_not_configured_signatures_will_not_be_validated")
        self.logger.info("webhook_handler_initialized")

    async def close(self):
        """Fechar handler."""
        await self.ticket_client.close()

    def _validate_signature(self, payload_bytes: bytes, signature: str) -> bool:
        """
        Validar assinatura HMAC-SHA256 do webhook.

        Args:
            payload_bytes: Payload raw em bytes
            signature: Assinatura fornecida no header (formato: sha256=<hex>)

        Returns:
            True se assinatura válida, False caso contrário
        """
        if not self.webhook_secret:
            self.logger.debug("webhook_secret_not_set_skipping_validation")
            return True

        if not signature:
            self.logger.warning("signature_header_missing")
            return False

        # Extrair hash da assinatura (formato: sha256=<hash>)
        if not signature.startswith("sha256="):
            self.logger.warning("invalid_signature_format", signature_prefix=signature[:10])
            return False

        provided_hash = signature[7:]  # Remove 'sha256='

        # Calcular HMAC esperado
        expected_hash = hmac.new(
            self.webhook_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        # Comparação constant-time para prevenir timing attacks
        is_valid = hmac.compare_digest(expected_hash, provided_hash)

        if not is_valid:
            self.logger.warning(
                "signature_validation_failed",
                expected_hash_prefix=expected_hash[:10],
                provided_hash_prefix=provided_hash[:10],
            )
            signature_validation_failures.inc()

        return is_valid

    async def handle_pipeline_completed(
        self,
        payload: PipelineCompletedPayload,
        payload_bytes: bytes,
        signature: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Processar webhook de pipeline completo.

        Args:
            payload: Dados do pipeline
            payload_bytes: Payload raw em bytes para validação HMAC
            signature: Assinatura HMAC do webhook

        Returns:
            Response data
        """
        webhooks_received.labels(source="pipeline").inc()

        self.logger.info(
            "pipeline_completed_webhook",
            pipeline_id=payload.pipeline_id,
            status=payload.status,
            duration_ms=payload.duration_ms,
        )

        # Validar assinatura HMAC
        if not self._validate_signature(payload_bytes, signature or ""):
            self.logger.error(
                "webhook_signature_invalid",
                pipeline_id=payload.pipeline_id,
            )
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        pipelines_completed.labels(status=payload.status).inc()

        # Atualizar ticket se fornecido
        if payload.ticket_id:
            try:
                ticket_status = "completed" if payload.status == "completed" else "failed"
                result = {
                    "pipeline_id": payload.pipeline_id,
                    "artifacts": [a.dict() for a in payload.artifacts],
                    "duration_ms": payload.duration_ms,
                    "logs_url": payload.logs_url,
                }

                if payload.sbom:
                    result["sbom"] = payload.sbom.dict()
                if payload.signature:
                    result["signature"] = payload.signature

                await self.ticket_client.update_ticket_status(
                    ticket_id=payload.ticket_id,
                    status=ticket_status,
                    result=result,
                )

                self.logger.info(
                    "ticket_updated_from_webhook",
                    ticket_id=payload.ticket_id,
                    status=ticket_status,
                )

            except Exception as e:
                self.logger.error(
                    "ticket_update_failed",
                    ticket_id=payload.ticket_id,
                    error=str(e),
                )

        # Publicar evento em telemetria
        # TODO: Integrar com FlowCTelemetryPublisher

        return {
            "status": "processed",
            "pipeline_id": payload.pipeline_id,
            "ticket_updated": payload.ticket_id is not None,
        }


# Global handler instance
webhook_handler: Optional[WebhookHandler] = None


def get_webhook_handler() -> WebhookHandler:
    """Get global webhook handler instance."""
    global webhook_handler
    if webhook_handler is None:
        raise RuntimeError("Webhook handler not initialized")
    return webhook_handler


@router.post("/pipeline-completed")
async def pipeline_completed_webhook(
    request: Request,
    x_webhook_signature: Optional[str] = Header(None),
):
    """
    Endpoint para receber notificações de pipelines completados.

    Headers:
        X-Webhook-Signature: HMAC-SHA256 signature (formato: sha256=<hex>)

    Body:
        PipelineCompletedPayload
    """
    handler = get_webhook_handler()

    try:
        # Ler body raw para validação HMAC
        body_bytes = await request.body()

        # Parse payload
        body_str = body_bytes.decode('utf-8')
        payload_dict = json.loads(body_str)
        payload = PipelineCompletedPayload(**payload_dict)

        result = await handler.handle_pipeline_completed(
            payload=payload,
            payload_bytes=body_bytes,
            signature=x_webhook_signature,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("webhook_processing_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
