import grpc
import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, RetryError
import structlog
from google.protobuf.timestamp_pb2 import Timestamp


def _json_datetime_serializer(obj):
    """
    Custom JSON serializer for objects not serializable by default json code.

    Handles datetime objects returned by Avro deserializer for timestamp-millis fields.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')

# Importar stubs gerados do specialist.proto
from neural_hive_specialists.proto_gen import specialist_pb2, specialist_pb2_grpc

logger = structlog.get_logger()


class SpecialistsGrpcClient:
    '''Cliente gRPC para invocar especialistas neurais em paralelo'''

    def __init__(self, config):
        self.config = config
        self.channels = {}
        self.stubs = {}

    async def initialize(self):
        '''Inicializar canais gRPC para todos os especialistas'''
        specialist_endpoints = {
            'business': self.config.specialist_business_endpoint,
            'technical': self.config.specialist_technical_endpoint,
            'behavior': self.config.specialist_behavior_endpoint,
            'evolution': self.config.specialist_evolution_endpoint,
            'architecture': self.config.specialist_architecture_endpoint
        }

        for specialist_type, endpoint in specialist_endpoints.items():
            # Criar canal gRPC assíncrono
            channel = grpc.aio.insecure_channel(
                endpoint,
                options=[
                    ('grpc.max_send_message_length', 4 * 1024 * 1024),
                    ('grpc.max_receive_message_length', 4 * 1024 * 1024),
                    ('grpc.keepalive_time_ms', 30000),
                    ('grpc.keepalive_timeout_ms', 10000),
                ]
            )

            # Criar stub
            stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

            self.channels[specialist_type] = channel
            self.stubs[specialist_type] = stub

            logger.info(
                'gRPC channel initialized',
                specialist_type=specialist_type,
                endpoint=endpoint
            )

    async def evaluate_plan(
        self,
        specialist_type: str,
        cognitive_plan: Dict[str, Any],
        trace_context: Dict[str, str]
    ) -> Dict[str, Any]:
        '''Invocar especialista individual para avaliar plano com retry'''

        # Usar AsyncRetrying para suportar código async
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10)
        ):
            with attempt:
                stub = self.stubs.get(specialist_type)
                if not stub:
                    raise ValueError(f'Especialista {specialist_type} não configurado')

                # DEBUG: Log estado do cognitive_plan antes da serialização
                logger.debug(
                    'Preparando cognitive_plan para gRPC',
                    specialist_type=specialist_type,
                    plan_id=cognitive_plan.get('plan_id'),
                    has_version='version' in cognitive_plan,
                    version_value=cognitive_plan.get('version'),
                    cognitive_plan_keys=list(cognitive_plan.keys())
                )

                # Serializar plano para bytes (JSON)
                # Usar serializer customizado para lidar com datetime do Avro deserializer
                plan_bytes = json.dumps(
                    cognitive_plan,
                    default=_json_datetime_serializer
                ).encode('utf-8')

                # DEBUG: Log do JSON serializado para verificar integridade
                logger.debug(
                    'cognitive_plan serializado para JSON',
                    specialist_type=specialist_type,
                    plan_id=cognitive_plan.get('plan_id'),
                    json_size_bytes=len(plan_bytes),
                    json_preview=plan_bytes[:500].decode('utf-8')
                )

                # Criar request
                request = specialist_pb2.EvaluatePlanRequest(
                    plan_id=cognitive_plan['plan_id'],
                    intent_id=cognitive_plan['intent_id'],
                    correlation_id=cognitive_plan.get('correlation_id', ''),
                    trace_id=trace_context.get('trace_id', ''),
                    span_id=trace_context.get('span_id', ''),
                    cognitive_plan=plan_bytes,
                    plan_version=cognitive_plan.get('version', '1.0.0'),
                    context={},
                    timeout_ms=self.config.grpc_timeout_ms
                )

                # Invocar com timeout
                try:
                    response = await asyncio.wait_for(
                        stub.EvaluatePlan(request),
                        timeout=self.config.grpc_timeout_ms / 1000.0
                    )

                    # Converter response para dict
                    # Converter Timestamp protobuf para ISO string
                    from datetime import datetime, timezone

                    expected_response_type = specialist_pb2.EvaluatePlanResponse
                    if response is None:
                        logger.error(
                            'Resposta vazia do especialista',
                            specialist_type=specialist_type,
                            plan_id=cognitive_plan['plan_id']
                        )
                        raise ValueError(f'Response from {specialist_type} is None')

                    if not isinstance(response, expected_response_type):
                        logger.error(
                            'Tipo inesperado de resposta do especialista',
                            specialist_type=specialist_type,
                            plan_id=cognitive_plan['plan_id'],
                            expected_type=expected_response_type.__name__,
                            response_type=type(response).__name__,
                            response_repr=str(response)
                        )
                        raise TypeError(
                            f'Unexpected response type from {specialist_type}: {type(response).__name__}'
                        )

                    has_evaluated_at = response.HasField('evaluated_at')
                    if not has_evaluated_at or response.evaluated_at is None:
                        logger.error(
                            'Response sem evaluated_at',
                            specialist_type=specialist_type,
                            plan_id=cognitive_plan['plan_id'],
                            response_type=type(response).__name__,
                            has_field=has_evaluated_at
                        )
                        raise ValueError(f'Response from {specialist_type} missing evaluated_at field')

                    evaluated_at = response.evaluated_at
                    if not isinstance(evaluated_at, Timestamp):
                        logger.error(
                            'Tipo inválido para evaluated_at',
                            specialist_type=specialist_type,
                            plan_id=cognitive_plan['plan_id'],
                            evaluated_at_type=type(evaluated_at).__name__
                        )
                        raise TypeError(
                            f'Invalid evaluated_at type from {specialist_type}: {type(evaluated_at).__name__}'
                        )

                    # Validações preventivas do timestamp
                    if not hasattr(evaluated_at, 'seconds') or not hasattr(evaluated_at, 'nanos'):
                        raise AttributeError(
                            f'Timestamp missing required fields: '
                            f'has_seconds={hasattr(evaluated_at, "seconds")}, '
                            f'has_nanos={hasattr(evaluated_at, "nanos")}'
                        )

                    if not isinstance(evaluated_at.seconds, int) or not isinstance(evaluated_at.nanos, int):
                        raise TypeError(
                            f'Timestamp fields have invalid types: '
                            f'seconds={type(evaluated_at.seconds).__name__}, '
                            f'nanos={type(evaluated_at.nanos).__name__}'
                        )

                    if evaluated_at.seconds <= 0:
                        raise ValueError(
                            f'Invalid timestamp seconds: {evaluated_at.seconds} (must be > 0)'
                        )

                    if not (0 <= evaluated_at.nanos < 1_000_000_000):
                        raise ValueError(
                            f'Invalid timestamp nanos: {evaluated_at.nanos} (must be 0-999999999)'
                        )

                    # Converter timestamp para datetime
                    try:
                        evaluated_datetime = datetime.fromtimestamp(
                            evaluated_at.seconds + evaluated_at.nanos / 1e9,
                            tz=timezone.utc
                        )

                        logger.debug(
                            'Timestamp converted successfully',
                            specialist_type=specialist_type,
                            seconds=evaluated_at.seconds,
                            nanos=evaluated_at.nanos,
                            datetime_iso=evaluated_datetime.isoformat()
                        )
                    except (AttributeError, TypeError, ValueError) as e:
                        # Capturar valores reais para debug
                        seconds_value = getattr(evaluated_at, 'seconds', None)
                        nanos_value = getattr(evaluated_at, 'nanos', None)

                        logger.error(
                            'Erro ao converter evaluated_at timestamp',
                            specialist_type=specialist_type,
                            plan_id=cognitive_plan['plan_id'],
                            evaluated_at_type=type(evaluated_at).__name__,
                            has_seconds=hasattr(evaluated_at, 'seconds'),
                            has_nanos=hasattr(evaluated_at, 'nanos'),
                            seconds_value=seconds_value,
                            nanos_value=nanos_value,
                            seconds_type=type(seconds_value).__name__ if seconds_value is not None else 'None',
                            nanos_type=type(nanos_value).__name__ if nanos_value is not None else 'None',
                            error=str(e),
                            error_type=type(e).__name__
                        )
                        raise

                    return {
                        'opinion_id': response.opinion_id,
                        'specialist_type': response.specialist_type,
                        'specialist_version': response.specialist_version,
                        'opinion': self._opinion_to_dict(response.opinion),
                        'processing_time_ms': response.processing_time_ms,
                        'evaluated_at': evaluated_datetime.isoformat()
                    }

                except asyncio.TimeoutError:
                    logger.error(
                        'Timeout ao invocar especialista',
                        specialist_type=specialist_type,
                        plan_id=cognitive_plan['plan_id'],
                        timeout_ms=self.config.grpc_timeout_ms
                    )
                    raise
                except grpc.RpcError as e:
                    logger.error(
                        'Erro gRPC ao invocar especialista',
                        specialist_type=specialist_type,
                        plan_id=cognitive_plan['plan_id'],
                        error=str(e),
                        code=e.code()
                    )
                    raise
                except Exception as e:
                    import traceback
                    logger.error(
                        'Exceção não tratada ao invocar especialista',
                        specialist_type=specialist_type,
                        plan_id=cognitive_plan['plan_id'],
                        error=str(e),
                        error_type=type(e).__name__,
                        traceback=traceback.format_exc()
                    )
                    raise

    async def evaluate_plan_parallel(
        self,
        cognitive_plan: Dict[str, Any],
        trace_context: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        '''Invocar todos os especialistas em paralelo'''
        specialist_types = ['business', 'technical', 'behavior', 'evolution', 'architecture']

        logger.info(
            'Invocando especialistas em paralelo',
            plan_id=cognitive_plan['plan_id'],
            num_specialists=len(specialist_types)
        )

        # Criar tasks para invocação paralela
        tasks = [
            self.evaluate_plan(specialist_type, cognitive_plan, trace_context)
            for specialist_type in specialist_types
        ]

        # Executar em paralelo com gather
        # return_exceptions=True para capturar falhas individuais
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Processar resultados
        opinions = []
        errors = []

        for specialist_type, result in zip(specialist_types, results):
            if isinstance(result, Exception):
                logger.error(
                    'Falha ao obter parecer de especialista',
                    specialist_type=specialist_type,
                    error=str(result)
                )
                errors.append({'specialist_type': specialist_type, 'error': str(result)})
            else:
                opinions.append(result)

        # Verificar se temos pareceres suficientes (mínimo 3 de 5)
        if len(opinions) < 3:
            raise ValueError(
                f'Pareceres insuficientes: {len(opinions)}/5. '
                f'Erros: {errors}'
            )

        logger.info(
            'Pareceres coletados',
            plan_id=cognitive_plan['plan_id'],
            num_opinions=len(opinions),
            num_errors=len(errors)
        )

        return opinions

    def _opinion_to_dict(self, opinion) -> Dict[str, Any]:
        '''Converte SpecialistOpinion protobuf para dict'''
        return {
            'confidence_score': opinion.confidence_score,
            'risk_score': opinion.risk_score,
            'recommendation': opinion.recommendation,
            'reasoning_summary': opinion.reasoning_summary,
            'reasoning_factors': [
                {
                    'factor_name': f.factor_name,
                    'weight': f.weight,
                    'score': f.score,
                    'description': f.description
                }
                for f in opinion.reasoning_factors
            ],
            'explainability_token': opinion.explainability_token,
            'explainability': {
                'method': opinion.explainability.method,
                'model_version': opinion.explainability.model_version,
                'model_type': opinion.explainability.model_type
            },
            'mitigations': [
                {
                    'mitigation_id': m.mitigation_id,
                    'description': m.description,
                    'priority': m.priority,
                    'estimated_impact': m.estimated_impact,
                    'required_actions': list(m.required_actions)
                }
                for m in opinion.mitigations
            ],
            'metadata': dict(opinion.metadata)
        }

    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        '''Verificar saúde de todos os especialistas'''
        health_results = {}

        for specialist_type, stub in self.stubs.items():
            try:
                request = specialist_pb2.HealthCheckRequest(
                    service_name=f'specialist-{specialist_type}'
                )
                response = await asyncio.wait_for(
                    stub.HealthCheck(request),
                    timeout=5.0
                )

                health_results[specialist_type] = {
                    'status': response.status,
                    'details': dict(response.details)
                }
            except Exception as e:
                health_results[specialist_type] = {
                    'status': 'NOT_SERVING',
                    'error': str(e)
                }

        return health_results

    async def close(self):
        '''Fechar todos os canais gRPC'''
        for specialist_type, channel in self.channels.items():
            await channel.close()
            logger.info('gRPC channel fechado', specialist_type=specialist_type)
