import json
import time
from typing import Dict, Optional

import grpc
import structlog
from google.protobuf.json_format import MessageToDict

from neural_hive_observability import instrument_grpc_channel
from src.config.settings import get_settings
from ..proto import analyst_agent_pb2, analyst_agent_pb2_grpc, optimizer_agent_pb2, optimizer_agent_pb2_grpc

logger = structlog.get_logger()


class AnalystAgentsGrpcClient:
    """
    Cliente gRPC para Analyst Agents.

    Responsável por solicitar análises causais para otimizações.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None

    async def connect(self):
        """Estabelecer canal gRPC com Analyst Agents."""
        try:
            self.channel = grpc.aio.insecure_channel(
                self.settings.analyst_agents_endpoint,
                options=[
                    ("grpc.max_send_message_length", 100 * 1024 * 1024),
                    ("grpc.max_receive_message_length", 100 * 1024 * 1024),
                    ("grpc.keepalive_time_ms", 30000),
                ],
            )
            self.channel = instrument_grpc_channel(self.channel, service_name='analyst-agents')

            # Criar stub real
            self.stub = analyst_agent_pb2_grpc.AnalystAgentServiceStub(self.channel)

            import asyncio
            try:
                await asyncio.wait_for(self.channel.channel_ready(), timeout=5.0)
                logger.info("analyst_agents_grpc_connected", endpoint=self.settings.analyst_agents_endpoint)
            except asyncio.TimeoutError:
                logger.warning("analyst_agents_grpc_connection_timeout", endpoint=self.settings.analyst_agents_endpoint)
        except Exception as e:
            logger.error("analyst_agents_grpc_connection_failed", error=str(e))

    async def disconnect(self):
        """Fechar canal gRPC."""
        if self.channel:
            await self.channel.close()
            logger.info("analyst_agents_grpc_disconnected")

    async def request_causal_analysis(
        self, target_component: str, degradation_metrics: Dict, context: Dict
    ) -> Optional[Dict]:
        """
        Solicitar análise causal de degradação.

        Args:
            target_component: Componente com degradação
            degradation_metrics: Métricas indicando degradação
            context: Contexto adicional

        Returns:
            Análise causal ou None se falhou
        """
        try:
            if not self.stub:
                raise RuntimeError("AnalystAgents gRPC stub not initialized")

            request = None
            response = None

            if hasattr(analyst_agent_pb2, "RequestCausalAnalysisRequest") and hasattr(
                self.stub, "RequestCausalAnalysis"
            ):
                request = analyst_agent_pb2.RequestCausalAnalysisRequest(
                    target_component=target_component,
                    degradation_metrics=degradation_metrics,
                    context=context,
                )
                response = await self.stub.RequestCausalAnalysis(request, timeout=self.settings.grpc_timeout)
            else:
                # Fallback para RPC existente ExecuteAnalysis
                request = analyst_agent_pb2.ExecuteAnalysisRequest(
                    analysis_type="causal_analysis",
                    parameters={
                        "target_component": target_component,
                        "degradation_metrics": json.dumps(degradation_metrics),
                        "context": json.dumps(context),
                    },
                )
                response = await self.stub.ExecuteAnalysis(request, timeout=self.settings.grpc_timeout)

            response_dict = MessageToDict(response, preserving_proto_field_name=True)
            logger.info("causal_analysis_retrieved", target_component=target_component)
            return response_dict

        except grpc.RpcError as e:
            logger.error("request_causal_analysis_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("request_causal_analysis_failed", error=str(e))
            return None

    async def get_historical_insights(self, target_component: str, time_range: str = "24h") -> Optional[Dict]:
        """
        Obter insights históricos para um componente.

        Nota: o proto atual não expõe filtro explícito por componente; quando
        usando QueryInsights como fallback, os filtros são aproximados via
        campos de tempo e reutilizando `insight_type` como hint de componente.

        Args:
            target_component: Nome do componente
            time_range: Intervalo de tempo

        Returns:
            Insights históricos ou None se falhou
        """
        try:
            if not self.stub:
                raise RuntimeError("AnalystAgents gRPC stub not initialized")

            if hasattr(analyst_agent_pb2, "GetHistoricalInsightsRequest") and hasattr(self.stub, "GetHistoricalInsights"):
                request = analyst_agent_pb2.GetHistoricalInsightsRequest(
                    target_component=target_component, time_range=time_range
                )
                response = await self.stub.GetHistoricalInsights(request, timeout=self.settings.grpc_timeout)
            else:
                now_ms = int(time.time() * 1000)
                start_ms = now_ms
                try:
                    amount = int(time_range[:-1])
                    unit = time_range[-1].lower()
                    if unit == "h":
                        start_ms = now_ms - amount * 60 * 60 * 1000
                    elif unit == "d":
                        start_ms = now_ms - amount * 24 * 60 * 60 * 1000
                except Exception:
                    start_ms = 0

                request = analyst_agent_pb2.QueryInsightsRequest(
                    insight_type=target_component or "ANY",  # Reaproveitado como hint de componente
                    priority="ANY",
                    start_timestamp=start_ms,
                    end_timestamp=now_ms,
                    limit=50,
                    offset=0,
                )
                response = await self.stub.QueryInsights(request, timeout=self.settings.grpc_timeout)

            insights = MessageToDict(response, preserving_proto_field_name=True)
            logger.info(
                "historical_insights_retrieved",
                target_component=target_component,
                count=insights.get("insights_count") or len(insights.get("insights", [])),
            )
            return insights

        except grpc.RpcError as e:
            logger.error("get_historical_insights_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("get_historical_insights_failed", error=str(e))
            return None

    async def validate_optimization_hypothesis(self, hypothesis: Dict) -> Optional[Dict]:
        """
        Validar hipótese de otimização com análise causal.

        Args:
            hypothesis: Hipótese de otimização

        Returns:
            Validação ou None se falhou
        """
        try:
            if not self.stub:
                raise RuntimeError("AnalystAgents gRPC stub not initialized")

            if hasattr(analyst_agent_pb2, "ValidateOptimizationHypothesisRequest") and hasattr(
                self.stub, "ValidateOptimizationHypothesis"
            ):
                request = analyst_agent_pb2.ValidateOptimizationHypothesisRequest(hypothesis=hypothesis)
                response = await self.stub.ValidateOptimizationHypothesis(request, timeout=self.settings.grpc_timeout)
            else:
                request = analyst_agent_pb2.ExecuteAnalysisRequest(
                    analysis_type="validate_optimization_hypothesis",
                    parameters={"hypothesis": json.dumps(hypothesis)},
                )
                response = await self.stub.ExecuteAnalysis(request, timeout=self.settings.grpc_timeout)

            validation = MessageToDict(response, preserving_proto_field_name=True)
            logger.info(
                "hypothesis_validated",
                hypothesis_id=hypothesis.get("hypothesis_id"),
                is_valid=validation.get("is_valid"),
            )
            return validation

        except grpc.RpcError as e:
            logger.error("validate_optimization_hypothesis_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("validate_optimization_hypothesis_failed", error=str(e))
            return None
