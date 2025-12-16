"""
OptimizerGrpcClient - Cliente gRPC para Optimizer Agents.

Cliente assíncrono para obter previsões de carga e recomendações de agendamento
do subsistema de ML Predictive Scheduling.
"""

import sys
import grpc
import structlog
from typing import Dict, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from neural_hive_observability.grpc_instrumentation import instrument_grpc_channel
from neural_hive_observability.context import inject_context_to_metadata

from src.config.settings import OrchestratorSettings

# Adicionar path para protos do optimizer-agents
sys.path.insert(0, '../optimizer-agents/src')

try:
    from proto import optimizer_agent_pb2, optimizer_agent_pb2_grpc
except ImportError:
    # Fallback - proto ainda não compilado
    optimizer_agent_pb2 = None
    optimizer_agent_pb2_grpc = None

logger = structlog.get_logger(__name__)


class OptimizerGrpcClient:
    """
    Cliente gRPC para Optimizer Agents.

    Fornece acesso às funcionalidades de ML Predictive Scheduling:
    - Previsões de carga (LoadPredictor)
    - Recomendações de agendamento (SchedulingOptimizer)
    """

    def __init__(self, config: OrchestratorSettings):
        """
        Inicializa o cliente.

        Args:
            config: Configurações do orchestrator
        """
        self.config = config
        self.logger = logger.bind(component='optimizer_grpc_client')
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None

    async def initialize(self):
        """Inicializa canal gRPC e stub."""
        # Check se proto está disponível
        if optimizer_agent_pb2 is None or optimizer_agent_pb2_grpc is None:
            self.logger.warning('optimizer_proto_not_found_skipping_client')
            # Não falhar - permitir que orchestrator funcione sem optimizer
            return

        host = self.config.optimizer_agents_endpoint.split(':')[0]
        port = int(self.config.optimizer_agents_endpoint.split(':')[1])
        target = f'{host}:{port}'

        self.logger.info('initializing_optimizer_grpc_channel', target=target)

        try:
            # Criar canal insecure
            self.channel = instrument_grpc_channel(
                grpc.aio.insecure_channel(target),
                service_name="orchestrator-dynamic",
                target_service="optimizer-agents"
            )

            # Criar stub
            self.stub = optimizer_agent_pb2_grpc.OptimizerAgentStub(self.channel)

            # Testar conectividade com timeout
            await self.channel.channel_ready()

            self.logger.info('optimizer_grpc_channel_ready', target=target)

        except Exception as e:
            self.logger.error(
                'optimizer_grpc_initialization_error',
                error=str(e),
                target=target
            )
            # Não falhar - permitir que orchestrator funcione sem optimizer
            self.stub = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=0.5, max=2)
    )
    async def get_load_forecast(
        self,
        horizon_minutes: int,
        include_confidence_intervals: bool = False
    ) -> Optional[Dict]:
        """
        Obtém previsão de carga futura.

        Args:
            horizon_minutes: Horizonte de previsão em minutos (60, 360, 1440)
            include_confidence_intervals: Incluir intervalos de confiança

        Returns:
            Dict com forecast e metadata ou None se indisponível
        """
        if self.stub is None:
            self.logger.debug('optimizer_stub_not_initialized_skipping_forecast')
            return None

        self.logger.info(
            'requesting_load_forecast',
            horizon_minutes=horizon_minutes
        )

        try:
            # Chamar RPC
            if optimizer_agent_pb2 is None:
                return None

            request = optimizer_agent_pb2.LoadForecastRequest(
                horizon_minutes=horizon_minutes,
                include_confidence_intervals=include_confidence_intervals
            )

            metadata = inject_context_to_metadata([])
            response = await self.stub.GetLoadForecast(request, metadata=metadata, timeout=10)

            # Converter resposta para dict
            forecast = {
                'forecast': [
                    {
                        'timestamp': point.timestamp,
                        'ticket_count': point.ticket_count,
                        'resource_demand': {
                            'cpu_cores': point.resource_demand.cpu_cores,
                            'memory_mb': point.resource_demand.memory_mb,
                        },
                        'confidence_lower': point.confidence_lower if include_confidence_intervals else None,
                        'confidence_upper': point.confidence_upper if include_confidence_intervals else None,
                    }
                    for point in response.forecast
                ],
                'metadata': {
                    'model_horizon': response.metadata.model_horizon,
                    'horizon_requested': response.metadata.horizon_requested,
                    'forecast_generated_at': response.metadata.forecast_generated_at,
                    'data_points_used': response.metadata.data_points_used,
                    'confidence_level': response.metadata.confidence_level,
                }
            }

            self.logger.info(
                'load_forecast_received',
                points=len(forecast['forecast'])
            )
            span = trace.get_current_span()
            span.set_attribute("rpc.service", "OptimizerAgent")
            span.set_attribute("rpc.method", "GetLoadForecast")
            span.set_attribute("neural.hive.ml.horizon_minutes", horizon_minutes)
            span.set_attribute("neural.hive.ml.forecast_points", len(forecast['forecast']))

            return forecast

        except grpc.RpcError as e:
            self.logger.error(
                'load_forecast_rpc_error',
                code=e.code(),
                details=e.details()
            )
            return None
        except Exception as e:
            self.logger.error('load_forecast_error', error=str(e))
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=0.5, max=2)
    )
    async def get_scheduling_recommendation(
        self,
        current_state: Dict
    ) -> Optional[Dict]:
        """
        Obtém recomendação de otimização de agendamento.

        Args:
            current_state: Estado atual contendo:
                - current_load: Carga atual (nº de tickets)
                - worker_utilization: Utilização de workers (0-1)
                - queue_depth: Profundidade da fila
                - sla_compliance: Compliance de SLA (0-1)

        Returns:
            Dict com action, justification, expected_improvement, risk_score, confidence
            ou None se indisponível
        """
        if self.stub is None:
            self.logger.debug('optimizer_stub_not_initialized_skipping_recommendation')
            return None

        self.logger.info(
            'requesting_scheduling_recommendation',
            current_load=current_state.get('current_load'),
            worker_utilization=current_state.get('worker_utilization')
        )

        try:
            # Chamar RPC
            if optimizer_agent_pb2 is None:
                return None

            request = optimizer_agent_pb2.SchedulingRecommendationRequest(
                current_load=current_state.get('current_load', 0),
                worker_utilization=current_state.get('worker_utilization', 0.0),
                queue_depth=current_state.get('queue_depth', 0),
                sla_compliance=current_state.get('sla_compliance', 1.0),
            )

            metadata = inject_context_to_metadata([])
            response = await self.stub.GetSchedulingRecommendation(request, metadata=metadata, timeout=5)

            # Converter resposta para dict
            recommendation = {
                'action': response.action,
                'justification': response.justification,
                'expected_improvement': response.expected_improvement,
                'risk_score': response.risk_score,
                'confidence': response.confidence,
            }

            self.logger.info(
                'scheduling_recommendation_received',
                action=recommendation['action'],
                confidence=recommendation['confidence']
            )
            span = trace.get_current_span()
            span.set_attribute("rpc.service", "OptimizerAgent")
            span.set_attribute("rpc.method", "GetSchedulingRecommendation")

            return recommendation

        except grpc.RpcError as e:
            self.logger.error(
                'scheduling_recommendation_rpc_error',
                code=e.code(),
                details=e.details()
            )
            return None
        except Exception as e:
            self.logger.error('scheduling_recommendation_error', error=str(e))
            return None

    async def close(self):
        """Fecha canal gRPC."""
        if self.channel:
            try:
                await self.channel.close()
                self.logger.info('optimizer_grpc_channel_closed')
            except Exception as e:
                self.logger.error('optimizer_channel_close_error', error=str(e))
