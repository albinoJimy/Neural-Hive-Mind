"""
Factory para criação de servidor gRPC com observabilidade.
"""

import grpc
from concurrent import futures
import structlog
from typing import Any
import time
from datetime import datetime
from opentelemetry import trace
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer

from .config import SpecialistConfig
from .auth_interceptor import AuthInterceptor

try:
    from .proto_gen import specialist_pb2, specialist_pb2_grpc
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    specialist_pb2 = None
    specialist_pb2_grpc = None

logger = structlog.get_logger()


def create_grpc_server_with_observability(
    specialist: Any,
    config: SpecialistConfig
) -> grpc.Server:
    """
    Cria servidor gRPC com observabilidade integrada.

    Args:
        specialist: Instância do especialista (BaseSpecialist)
        config: Configuração do especialista

    Returns:
        Servidor gRPC configurado
    """
    logger.info(
        "Creating gRPC server",
        specialist_type=specialist.specialist_type,
        port=config.grpc_port,
        max_workers=config.grpc_max_workers
    )

    # Criar interceptors
    interceptors = []

    # Adicionar AuthInterceptor se autenticação estiver habilitada
    if config.enable_jwt_auth:
        auth_interceptor = AuthInterceptor(config, specialist.metrics)
        interceptors.append(auth_interceptor)
        logger.info(
            "JWT authentication enabled",
            algorithm=config.jwt_algorithm,
            public_endpoints=config.jwt_public_endpoints
        )
    else:
        logger.warning(
            "JWT authentication DISABLED - servidor em modo inseguro",
            specialist_type=specialist.specialist_type
        )

    # Criar servidor com interceptors
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=config.grpc_max_workers),
        interceptors=interceptors,
        options=[
            ('grpc.max_send_message_length', config.grpc_max_message_length),
            ('grpc.max_receive_message_length', config.grpc_max_message_length),
            ('grpc.so_reuseport', 1),
            ('grpc.keepalive_time_ms', 30000),
            ('grpc.keepalive_timeout_ms', 10000),
        ]
    )

    # Instrumentar servidor gRPC com OpenTelemetry
    if config.enable_tracing:
        try:
            GrpcInstrumentorServer().instrument_server(server)
            logger.info(
                "gRPC server instrumented with OpenTelemetry",
                specialist_type=specialist.specialist_type
            )
        except Exception as e:
            logger.warning(
                "Failed to instrument gRPC server - continuing without tracing",
                error=str(e)
            )

    # Registrar servicer
    servicer = SpecialistServicer(specialist)

    if PROTO_AVAILABLE and specialist_pb2_grpc:
        specialist_pb2_grpc.add_SpecialistServiceServicer_to_server(servicer, server)
        logger.info("Specialist servicer registered with protobuf")
    else:
        logger.warning("Protobuf stubs not available - servicer not registered")

    # Adicionar health check service
    try:
        from grpc_health.v1 import health_pb2_grpc
        health_servicer = HealthServicer(specialist)
        health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
        logger.info("Health servicer registered")
    except ImportError:
        logger.warning("grpc_health not available - health servicer not registered")

    # Bind port
    server.add_insecure_port(f'[::]:{config.grpc_port}')

    logger.info(
        "gRPC server created successfully",
        specialist_type=specialist.specialist_type,
        port=config.grpc_port,
        jwt_auth_enabled=config.enable_jwt_auth,
        interceptors_count=len(interceptors)
    )

    return server


class SpecialistServicer:
    """Implementação do serviço gRPC SpecialistService."""

    def __init__(self, specialist: Any):
        self.specialist = specialist
        logger.info(
            "Specialist servicer initialized",
            specialist_type=specialist.specialist_type
        )

    def EvaluatePlan(self, request, context):
        """
        Handler para avaliação de plano.

        Args:
            request: EvaluatePlanRequest
            context: gRPC context

        Returns:
            EvaluatePlanResponse
        """
        logger.info(
            "Received EvaluatePlan request",
            plan_id=request.plan_id,
            intent_id=request.intent_id,
            trace_id=request.trace_id
        )

        start_time = time.time()

        # Obter o span atual do gRPC instrumentor
        current_span = trace.get_current_span()
        if current_span and current_span.get_span_context().is_valid:
            current_span.set_attribute("specialist.type", self.specialist.specialist_type)
            current_span.set_attribute("specialist.version", self.specialist.version)
            current_span.set_attribute("plan.id", request.plan_id)
            current_span.set_attribute("intent.id", request.intent_id)

        try:
            # Extrair trace context dos metadados
            metadata = dict(context.invocation_metadata())

            # Extrair x-tenant-id do metadata gRPC e injetar no request.context
            tenant_id = metadata.get('x-tenant-id')
            if tenant_id:
                # Injetar tenant_id no request.context
                if isinstance(request.context, dict):
                    request.context['tenant_id'] = tenant_id
                else:
                    # Se é protobuf map, adicionar diretamente
                    request.context['tenant_id'] = tenant_id
                logger.debug(
                    "Tenant ID propagated from gRPC metadata to request context",
                    tenant_id=tenant_id,
                    plan_id=request.plan_id
                )

            # Chamar especialista (retorna dict)
            result = self.specialist.evaluate_plan(request)

            processing_time_ms = int((time.time() - start_time) * 1000)

            # Adicionar atributos de resultado ao span
            if current_span and isinstance(result, dict):
                opinion = result.get('opinion', {})
                current_span.set_attribute("opinion.id", result.get('opinion_id', ''))
                current_span.set_attribute("opinion.confidence_score", opinion.get('confidence_score', 0.0))
                current_span.set_attribute("opinion.risk_score", opinion.get('risk_score', 0.0))
                current_span.set_attribute("opinion.recommendation", opinion.get('recommendation', ''))
                current_span.set_attribute("processing.time_ms", processing_time_ms)

            logger.info(
                "EvaluatePlan completed successfully",
                plan_id=request.plan_id,
                opinion_id=result.get('opinion_id'),
                processing_time_ms=processing_time_ms
            )

            # Converter dict para protobuf response
            if PROTO_AVAILABLE and specialist_pb2:
                return self._build_evaluate_plan_response(result, processing_time_ms)
            else:
                # Fallback: retornar dict (não recomendado)
                return result

        except ValueError as e:
            # Capturar erros relacionados a tenant
            error_msg = str(e)
            if 'Tenant desconhecido' in error_msg or 'Tenant não encontrado' in error_msg:
                logger.warning(
                    "Unknown tenant",
                    plan_id=request.plan_id,
                    error=error_msg
                )
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(f"Tenant inválido: {error_msg}")
            elif 'Tenant inativo' in error_msg:
                logger.warning(
                    "Inactive tenant",
                    plan_id=request.plan_id,
                    error=error_msg
                )
                context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                context.set_details(f"Acesso negado: {error_msg}")
            else:
                logger.error(
                    "Validation error in EvaluatePlan",
                    plan_id=request.plan_id,
                    error=error_msg,
                    exc_info=True
                )
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(str(e))
            raise
        except Exception as e:
            logger.error(
                "EvaluatePlan failed",
                plan_id=request.plan_id,
                error=str(e),
                exc_info=True
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    def HealthCheck(self, request, context):
        """
        Handler para health check.

        Args:
            request: HealthCheckRequest
            context: gRPC context

        Returns:
            HealthCheckResponse
        """
        logger.debug("Received HealthCheck request")

        try:
            health_result = self.specialist.health_check()

            logger.debug(
                "HealthCheck completed",
                status=health_result['status']
            )

            # Converter dict para protobuf response
            if PROTO_AVAILABLE and specialist_pb2:
                return self._build_health_check_response(health_result)
            else:
                return health_result

        except Exception as e:
            logger.error("HealthCheck failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    def GetCapabilities(self, request, context):
        """
        Handler para obter capacidades.

        Args:
            request: GetCapabilitiesRequest
            context: gRPC context

        Returns:
            GetCapabilitiesResponse
        """
        logger.debug("Received GetCapabilities request")

        try:
            capabilities = self.specialist.get_capabilities()

            logger.debug(
                "GetCapabilities completed",
                specialist_type=capabilities['specialist_type']
            )

            # Converter dict para protobuf response
            if PROTO_AVAILABLE and specialist_pb2:
                return self._build_get_capabilities_response(capabilities)
            else:
                return capabilities

        except Exception as e:
            logger.error("GetCapabilities failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    def _build_evaluate_plan_response(self, result: dict, processing_time_ms: int):
        """Constrói EvaluatePlanResponse a partir de dict."""
        opinion_data = result.get('opinion', {})

        # Construir SpecialistOpinion
        reasoning_factors = [
            specialist_pb2.ReasoningFactor(
                factor_name=f.get('factor_name', ''),
                weight=f.get('weight', 0.0),
                score=f.get('score', 0.0),
                description=f.get('description', '')
            )
            for f in opinion_data.get('reasoning_factors', [])
        ]

        mitigations = [
            specialist_pb2.MitigationSuggestion(
                mitigation_id=m.get('mitigation_id', ''),
                description=m.get('description', ''),
                priority=m.get('priority', 'medium'),
                estimated_impact=m.get('estimated_impact', 0.0),
                required_actions=m.get('required_actions', [])
            )
            for m in opinion_data.get('mitigations', [])
        ]

        explainability = None
        if 'explainability' in opinion_data:
            exp_data = opinion_data['explainability']
            feature_importances = [
                specialist_pb2.FeatureImportance(
                    feature_name=f.get('feature_name', ''),
                    importance=f.get('importance', 0.0),
                    contribution=f.get('contribution', 'neutral')
                )
                for f in exp_data.get('feature_importances', [])
            ]
            explainability = specialist_pb2.ExplainabilityMetadata(
                method=exp_data.get('method', 'heuristic'),
                feature_importances=feature_importances,
                model_version=exp_data.get('model_version', ''),
                model_type=exp_data.get('model_type', '')
            )

        opinion = specialist_pb2.SpecialistOpinion(
            confidence_score=opinion_data.get('confidence_score', 0.0),
            risk_score=opinion_data.get('risk_score', 0.0),
            recommendation=opinion_data.get('recommendation', 'review_required'),
            reasoning_summary=opinion_data.get('reasoning_summary', ''),
            reasoning_factors=reasoning_factors,
            explainability_token=opinion_data.get('explainability_token', ''),
            explainability=explainability,
            mitigations=mitigations,
            metadata=opinion_data.get('metadata', {})
        )

        # Construir EvaluatePlanResponse
        from google.protobuf.timestamp_pb2 import Timestamp
        timestamp = Timestamp()
        timestamp.GetCurrentTime()

        return specialist_pb2.EvaluatePlanResponse(
            opinion_id=result.get('opinion_id', ''),
            specialist_type=result.get('specialist_type', ''),
            specialist_version=result.get('specialist_version', '1.0.0'),
            opinion=opinion,
            processing_time_ms=processing_time_ms,
            evaluated_at=timestamp
        )

    def _build_health_check_response(self, health_result: dict):
        """Constrói HealthCheckResponse a partir de dict."""
        status_map = {
            'SERVING': specialist_pb2.HealthCheckResponse.SERVING,
            'NOT_SERVING': specialist_pb2.HealthCheckResponse.NOT_SERVING,
            'UNKNOWN': specialist_pb2.HealthCheckResponse.UNKNOWN,
            'SERVICE_UNKNOWN': specialist_pb2.HealthCheckResponse.SERVICE_UNKNOWN
        }

        status = status_map.get(health_result.get('status', 'UNKNOWN'),
                               specialist_pb2.HealthCheckResponse.UNKNOWN)

        return specialist_pb2.HealthCheckResponse(
            status=status,
            details=health_result.get('details', {})
        )

    def _build_get_capabilities_response(self, capabilities: dict):
        """Constrói GetCapabilitiesResponse a partir de dict."""
        metrics_data = capabilities.get('metrics', {})

        metrics = None
        if metrics_data:
            from google.protobuf.timestamp_pb2 import Timestamp

            # Construir timestamp apenas se valor válido estiver disponível
            last_update = None
            last_model_update_str = metrics_data.get('last_model_update')

            if last_model_update_str:
                try:
                    # Tentar converter string ISO-8601 para datetime
                    dt = datetime.fromisoformat(last_model_update_str)
                    last_update = Timestamp()
                    last_update.FromDatetime(dt)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Invalid last_model_update format, skipping timestamp",
                        value=last_model_update_str,
                        error=str(e)
                    )
                    # last_update permanece None

            # Construir métricas (se last_update for None, o campo ficará com valor padrão)
            if last_update:
                metrics = specialist_pb2.CapabilityMetrics(
                    average_processing_time_ms=metrics_data.get('average_processing_time_ms', 0.0),
                    accuracy_score=metrics_data.get('accuracy_score', 0.0),
                    total_evaluations=metrics_data.get('total_evaluations', 0),
                    last_model_update=last_update
                )
            else:
                # Omitir last_model_update se não disponível
                metrics = specialist_pb2.CapabilityMetrics(
                    average_processing_time_ms=metrics_data.get('average_processing_time_ms', 0.0),
                    accuracy_score=metrics_data.get('accuracy_score', 0.0),
                    total_evaluations=metrics_data.get('total_evaluations', 0)
                )

        return specialist_pb2.GetCapabilitiesResponse(
            specialist_type=capabilities.get('specialist_type', ''),
            version=capabilities.get('version', ''),
            supported_domains=capabilities.get('supported_domains', []),
            supported_plan_versions=capabilities.get('supported_plan_versions', []),
            metrics=metrics,
            configuration=capabilities.get('configuration', {})
        )


class HealthServicer:
    """Implementação do serviço gRPC Health."""

    def __init__(self, specialist: Any):
        self.specialist = specialist
        logger.info("Health servicer initialized")

    def Check(self, request, context):
        """Handler para health check."""
        try:
            health_result = self.specialist.health_check()

            # Mapear para enum do gRPC Health
            if health_result['status'] == 'SERVING':
                status = 1  # SERVING
            else:
                status = 2  # NOT_SERVING

            return {
                'status': status
            }

        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return {
                'status': 2  # NOT_SERVING
            }

    def Watch(self, request, context):
        """Handler para watch health status (streaming)."""
        # Implementação simplificada - retornar status atual
        try:
            health_result = self.specialist.health_check()

            if health_result['status'] == 'SERVING':
                status = 1
            else:
                status = 2

            yield {'status': status}

        except Exception as e:
            logger.error("Health watch failed", error=str(e))
            yield {'status': 2}
