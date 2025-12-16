"""
Exemplo de instrumentação gRPC com Neural Hive Observability.

Mostra como criar servidor instrumentado, usar @trace_grpc_method e
extrair contexto via extract_grpc_context.
"""

from concurrent import futures
from dataclasses import dataclass
from typing import Optional

import grpc
from opentelemetry.context import detach

from neural_hive_observability import (
    ObservabilityConfig,
    create_instrumented_grpc_server,
    extract_grpc_context,
    init_observability,
    get_config,
    trace_grpc_method,
)


# Exemplos de mensagens (substitua pelos types gerados pelo protobuf)
@dataclass
class EvaluatePlanRequest:
    intent_id: Optional[str]
    payload: str


@dataclass
class EvaluatePlanResponse:
    status: str
    intent_id: Optional[str]


class SpecialistServiceServicer:
    """Servicer gRPC com tracing automático."""

    @trace_grpc_method(include_request=True, include_response=True)
    def EvaluatePlan(self, request: EvaluatePlanRequest, context: grpc.ServicerContext) -> EvaluatePlanResponse:
        # Extrair contexto de baggage e trace do metadata
        ctx, token = extract_grpc_context(context)
        try:
            intent_id = ctx.get("intent_id") or request.intent_id

            # Lógica de negócio simplificada
            return EvaluatePlanResponse(status="ok", intent_id=intent_id)
        finally:
            if token:
                detach(token)


def serve():
    # Inicializa a observabilidade e obtém configuração
    init_observability(
        service_name="specialist-service",
        neural_hive_component="specialist",
        neural_hive_layer="cognicao",
        neural_hive_domain="plans",
    )

    config = get_config() or ObservabilityConfig(
        service_name="specialist-service",
        neural_hive_component="specialist",
        neural_hive_layer="cognicao",
    )

    server = create_instrumented_grpc_server(config, max_workers=5)

    # Substitua a linha abaixo pelo registrador gerado pelo protobuf
    # add_SpecialistServiceServicer_to_server(SpecialistServiceServicer(), server)

    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
