"""Servidor gRPC para PII Service."""


import grpc
import structlog
from google.protobuf.timestamp_pb2 import Timestamp

from src.config.settings import get_settings
from src.models.pii import MaskStrategy
from src.proto import pii_pb2, pii_pb2_grpc
from src.services.pii_service import get_pii_service

logger = structlog.get_logger(__name__)
settings = get_settings()
pii_service = get_pii_service()


def _timestamp_now() -> Timestamp:
    """Cria Timestamp protobuf com data atual."""
    ts = Timestamp()
    ts.GetCurrentTime()
    return ts


def _pii_type_to_proto(pii_type):
    """Converte PIIType para protobuf."""
    type_map = {
        "EMAIL": pii_pb2.EMAIL,
        "PHONE": pii_pb2.PHONE,
        "CPF": pii_pb2.CPF,
        "CNPJ": pii_pb2.CNPJ,
        "CREDIT_CARD": pii_pb2.CREDIT_CARD,
        "SSN": pii_pb2.SSN,
        "ADDRESS": pii_pb2.ADDRESS,
        "IP_ADDRESS": pii_pb2.IP_ADDRESS,
        "UUID": pii_pb2.UUID,
        "API_KEY": pii_pb2.API_KEY,
        "NIF": pii_pb2.NIF,
        "IBAN": pii_pb2.IBAN,
        "PASSPORT": pii_pb2.PASSPORT,
        "POSTAL_CODE": pii_pb2.POSTAL_CODE,
        "RG": pii_pb2.RG,
        "TITULO_ELEITOR": pii_pb2.TITULO_ELEITOR,
        "BANK_ACCOUNT": pii_pb2.BANK_ACCOUNT,
        "PERSON": pii_pb2.PERSON,
        "ORG": pii_pb2.ORG,
        "DATE": pii_pb2.DATE,
        "PII_UNKNOWN": pii_pb2.PII_UNKNOWN,
    }
    return type_map.get(pii_type, pii_pb2.PII_UNKNOWN)


def _mask_strategy_to_proto(strategy):
    """Converte MaskStrategy para protobuf."""
    strategy_map = {
        "MASK_FULL": pii_pb2.MASK_FULL,
        "MASK_PARTIAL": pii_pb2.MASK_PARTIAL,
        "MASK_REDACT": pii_pb2.MASK_REDACT,
        "MASK_HASH": pii_pb2.MASK_HASH,
    }
    return strategy_map.get(strategy, pii_pb2.MASK_UNKNOWN)


class PIIGrpcServicer(pii_pb2_grpc.PIIServiceServicer):
    """Implementação do servidor gRPC para PII Service."""

    async def Detect(self, request, context):
        """Detecta PII em texto (INV-2: 7 tipos com positions)."""
        try:
            # Detectar
            detected = pii_service.detect(
                text=request.text,
                types_to_detect=[t.name for t in request.types] if request.types else None,
                min_confidence=request.min_confidence,
            )

            # Contagem por tipo
            count_by_type = {}
            for pii in detected:
                pii_type_str = pii.type.value
                count_by_type[pii_type_str] = count_by_type.get(pii_type_str, 0) + 1

            # Construir response
            detected_pii = []
            for pii in detected:
                pii_found = pii_pb2.PIIFound(
                    type=_pii_type_to_proto(pii.type.value),
                    value=pii.value,
                    start=pii.start,  # INV-2: position requerido
                    end=pii.end,  # INV-2: position requerido
                    confidence=pii.confidence,
                )
                detected_pii.append(pii_found)

            response = pii_pb2.DetectResponse(
                detected_pii=detected_pii,
                total_found=len(detected),
                count_by_type=count_by_type,
                processing_time_ms=0,  # TODO: calcular
                detected_at=_timestamp_now(),
                language_used=request.language,
            )

            return response

        except Exception as e:
            logger.error("grpc_detect_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Detect failed: {str(e)}")
            return pii_pb2.DetectResponse()

    async def Mask(self, request, context):
        """Mascara PII em texto (R-P3: 3 strategies, R-P4: audit log)."""
        try:
            # Extrair context
            requestor_id = request.context.get("requestor_id", "grpc_anonymous")
            tenant_id = request.context.get("tenant_id")
            user_id = request.context.get("user_id")

            # Mapear estratégia do enum proto para o enum de domínio MaskStrategy.
            # pii_service.mask() espera o enum (usa strategy.value); passar a string
            # crua levantava "'str' object has no attribute 'value'".
            strategy_map = {
                pii_pb2.MASK_FULL: MaskStrategy.MASK_FULL,
                pii_pb2.MASK_PARTIAL: MaskStrategy.MASK_PARTIAL,
                pii_pb2.MASK_REDACT: MaskStrategy.MASK_REDACT,
                pii_pb2.MASK_HASH: MaskStrategy.MASK_HASH,
            }
            strategy = strategy_map.get(request.strategy, MaskStrategy.MASK_PARTIAL)

            # Tipos para mascarar
            types_to_mask = [t.name for t in request.types] if request.types else None

            # Mascara
            masked_text, detected_pii, mask_results, mask_id = await pii_service.mask(
                text=request.text,
                strategy=strategy,
                types_to_mask=types_to_mask,
                enable_reversible=request.enable_reversible,
                requestor_id=requestor_id,
                tenant_id=tenant_id,
                user_id=user_id,
                correlation_id=request.correlation_id,
                enable_audit_log=request.enable_audit_log,
            )

            # Construir response
            detected_pii_protos = []
            for pii in detected_pii:
                pii_found = pii_pb2.PIIFound(
                    type=_pii_type_to_proto(pii.type.value),
                    value=pii.value,
                    start=pii.start,
                    end=pii.end,
                    confidence=pii.confidence,
                    masked_value=pii.masked_value or "",
                )
                detected_pii_protos.append(pii_found)

            mask_results_protos = []
            for mask in mask_results:
                mask_result = pii_pb2.MaskResult(
                    type=_pii_type_to_proto(mask.type.value),
                    original_value=mask.original_value,
                    masked_value=mask.masked_value,
                    start=mask.start,
                    end=mask.end,
                    strategy_used=_mask_strategy_to_proto(mask.strategy_used.value),
                    mask_id=mask.mask_id or "",
                )
                mask_results_protos.append(mask_result)

            response = pii_pb2.MaskResponse(
                masked_text=masked_text,
                detected_pii=detected_pii_protos,
                masks=mask_results_protos,
                mask_id=mask_id or "",
                processing_time_ms=0,  # TODO: calcular
                masked_at=_timestamp_now(),
                audit_log_id="",  # TODO: retornar ID
            )

            return response

        except Exception as e:
            logger.error("grpc_mask_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Mask failed: {str(e)}")
            return pii_pb2.MaskResponse()

    async def Unmask(self, request, context):
        """Remove máscara de PII (INV-14: AES-256-GCM reversible unmask)."""
        try:
            # Extrair context
            requestor_id = request.context.get("requestor_id", "grpc_anonymous")
            tenant_id = request.context.get("tenant_id")
            user_id = request.context.get("user_id")

            # Unmask
            original_text, success, error_message = await pii_service.unmask(
                mask_id=request.mask_id,
                masked_text=request.masked_text,
                requestor_id=requestor_id,
                tenant_id=tenant_id,
                user_id=user_id,
                correlation_id=request.correlation_id,
                enable_audit_log=request.enable_audit_log,
            )

            response = pii_pb2.UnmaskResponse(
                original_text=original_text,
                success=success,
                error_message=error_message or "",
                processing_time_ms=0,  # TODO: calcular
                unmasked_at=_timestamp_now(),
                audit_log_id="",  # TODO: retornar ID
            )

            return response

        except Exception as e:
            logger.error("grpc_unmask_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Unmask failed: {str(e)}")
            return pii_pb2.UnmaskResponse()

    async def DetectAndMask(self, request, context):
        """Detecta e mascara em uma única operação."""
        # Reutilizar lógica de Mask
        mask_request = pii_pb2.MaskRequest(
            text=request.text,
            strategy=request.strategy,
            types=request.types,
            language=request.language,
            correlation_id=request.correlation_id,
            trace_id=request.trace_id,
            context=request.context,
            enable_audit_log=request.enable_audit_log,
            requestor_id=request.requestor_id,
            enable_reversible=request.enable_reversible,
        )
        return await self.Mask(mask_request, context)

    async def HealthCheck(self, request, context):
        """Health check do serviço PII."""
        response = pii_pb2.HealthCheckResponse(
            status=pii_pb2.HealthCheckResponse.SERVING,
            version=settings.VERSION,
            details={"service": "pii-service"},
        )
        return response

    async def GetCapabilities(self, request, context):
        """Retorna capacidades do serviço."""
        capabilities = pii_service.get_capabilities()

        # Mapear tipos
        supported_types = []
        for t in capabilities["supported_types"]:
            try:
                supported_types.append(_pii_type_to_proto(t))
            except KeyError:
                pass

        # Mapear estratégias
        supported_strategies = []
        for s in capabilities["supported_strategies"]:
            try:
                supported_strategies.append(_mask_strategy_to_proto(s))
            except KeyError:
                pass

        response = pii_pb2.GetCapabilitiesResponse(
            supported_types=supported_types,
            supported_strategies=supported_strategies,
            supports_reversible_unmask=capabilities["supports_reversible_unmask"],
            supports_audit_log=capabilities["supports_audit_log"],
            configuration=capabilities,
            version=capabilities["version"],
        )
        return response

    async def ValidateMaskToken(self, request, context):
        """Valida token de mascaramento."""
        try:
            reversible_mask = pii_service.reversible_mask
            validation = reversible_mask.validate_token(request.mask_id)

            response = pii_pb2.ValidateMaskTokenResponse(
                valid=validation.get("valid", False),
                error_message=validation.get("error_message", ""),
            )

            if "expires_at" in validation:
                ts = Timestamp()
                ts.FromJsonString(validation["expires_at"].isoformat())
                response.expires_at.CopyFrom(ts)

            return response

        except Exception as e:
            logger.error("grpc_validate_token_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Validate token failed: {str(e)}")
            return pii_pb2.ValidateMaskTokenResponse()


async def serve_grpc(port: int = 9021):
    """
    Inicia servidor gRPC.

    Args:
        port: Porta para escutar (padrão: 9021)
    """
    server = grpc.aio.server()

    pii_pb2_grpc.add_PIIServiceServicer_to_server(PIIGrpcServicer(), server)

    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    logger.info("starting_grpc_server", port=port, listen_addr=listen_addr)

    await server.start()
    await server.wait_for_termination()

    return server
