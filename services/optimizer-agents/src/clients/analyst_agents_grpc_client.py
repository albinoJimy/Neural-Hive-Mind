"""Cliente gRPC para Analyst Agents com suporte a mTLS via SPIFFE."""

import json
import time
from typing import Dict, List, Optional, Tuple

import grpc
import structlog
from google.protobuf.json_format import MessageToDict

from neural_hive_observability import instrument_grpc_channel
from src.config.settings import get_settings
from ..proto import analyst_agent_pb2, analyst_agent_pb2_grpc, optimizer_agent_pb2, optimizer_agent_pb2_grpc

# Importar SPIFFE/mTLS se disponível
try:
    from neural_hive_security import (
        SPIFFEManager,
        SPIFFEConfig,
        create_secure_grpc_channel,
        get_grpc_metadata_with_jwt,
    )
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False
    SPIFFEManager = None
    SPIFFEConfig = None

logger = structlog.get_logger()


class AnalystAgentsGrpcClient:
    """
    Cliente gRPC para Analyst Agents com suporte a mTLS via SPIFFE.

    Responsável por solicitar análises causais para otimizações.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        self.spiffe_manager: Optional[SPIFFEManager] = None

    async def connect(self):
        """Estabelecer canal gRPC com Analyst Agents com suporte a mTLS."""
        try:
            target = self.settings.analyst_agents_endpoint

            # Verificar se mTLS via SPIFFE está habilitado
            spiffe_x509_enabled = (
                getattr(self.settings, 'spiffe_enabled', False)
                and getattr(self.settings, 'spiffe_enable_x509', False)
                and SECURITY_LIB_AVAILABLE
            )

            if spiffe_x509_enabled:
                # Criar configuração SPIFFE
                spiffe_config = SPIFFEConfig(
                    workload_api_socket=self.settings.spiffe_socket_path,
                    trust_domain=self.settings.spiffe_trust_domain,
                    jwt_audience=self.settings.spiffe_jwt_audience,
                    jwt_ttl_seconds=self.settings.spiffe_jwt_ttl_seconds,
                    enable_x509=True,
                    environment=self.settings.environment
                )

                # Criar SPIFFE manager
                self.spiffe_manager = SPIFFEManager(spiffe_config)
                await self.spiffe_manager.initialize()

                # Criar canal seguro com mTLS
                # Permitir fallback inseguro apenas em ambientes de desenvolvimento
                is_dev_env = self.settings.environment.lower() in ('dev', 'development')
                self.channel = await create_secure_grpc_channel(
                    target=target,
                    spiffe_config=spiffe_config,
                    spiffe_manager=self.spiffe_manager,
                    fallback_insecure=is_dev_env
                )

                logger.info(
                    'mtls_channel_configured',
                    target=target,
                    environment=self.settings.environment
                )
            else:
                # Fallback para canal inseguro (apenas desenvolvimento)
                if self.settings.environment in ['production', 'staging', 'prod']:
                    raise RuntimeError(
                        f"mTLS is required in {self.settings.environment} but SPIFFE X.509 is disabled. "
                        "Set spiffe_enabled=True and spiffe_enable_x509=True."
                    )

                logger.warning(
                    'using_insecure_channel',
                    target=target,
                    environment=self.settings.environment,
                    warning='mTLS disabled - not for production use'
                )
                self.channel = grpc.aio.insecure_channel(
                    target,
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
                logger.info("analyst_agents_grpc_connected", endpoint=target)
            except asyncio.TimeoutError:
                logger.warning("analyst_agents_grpc_connection_timeout", endpoint=target)
        except Exception as e:
            logger.error("analyst_agents_grpc_connection_failed", error=str(e))
            raise

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """Obter metadata gRPC com JWT-SVID para autenticação."""
        if not getattr(self.settings, 'spiffe_enabled', False) or not self.spiffe_manager:
            return []

        try:
            audience = f"analyst-agents.{self.settings.spiffe_trust_domain}"
            return await get_grpc_metadata_with_jwt(
                spiffe_manager=self.spiffe_manager,
                audience=audience,
                environment=self.settings.environment
            )
        except Exception as e:
            logger.warning('jwt_svid_fetch_failed', error=str(e))
            if self.settings.environment in ['production', 'staging', 'prod']:
                raise
            return []

    async def disconnect(self):
        """Fechar canal gRPC e SPIFFE manager."""
        if self.spiffe_manager:
            await self.spiffe_manager.close()
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

            # Obter metadata com JWT-SVID
            metadata = await self._get_grpc_metadata()

            if hasattr(analyst_agent_pb2, "RequestCausalAnalysisRequest") and hasattr(
                self.stub, "RequestCausalAnalysis"
            ):
                request = analyst_agent_pb2.RequestCausalAnalysisRequest(
                    target_component=target_component,
                    degradation_metrics=degradation_metrics,
                    context=context,
                )
                response = await self.stub.RequestCausalAnalysis(request, timeout=self.settings.grpc_timeout, metadata=metadata)
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
                response = await self.stub.ExecuteAnalysis(request, timeout=self.settings.grpc_timeout, metadata=metadata)

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

            # Obter metadata com JWT-SVID
            metadata = await self._get_grpc_metadata()

            if hasattr(analyst_agent_pb2, "GetHistoricalInsightsRequest") and hasattr(self.stub, "GetHistoricalInsights"):
                request = analyst_agent_pb2.GetHistoricalInsightsRequest(
                    target_component=target_component, time_range=time_range
                )
                response = await self.stub.GetHistoricalInsights(request, timeout=self.settings.grpc_timeout, metadata=metadata)
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
                response = await self.stub.QueryInsights(request, timeout=self.settings.grpc_timeout, metadata=metadata)

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

            # Obter metadata com JWT-SVID
            metadata = await self._get_grpc_metadata()

            if hasattr(analyst_agent_pb2, "ValidateOptimizationHypothesisRequest") and hasattr(
                self.stub, "ValidateOptimizationHypothesis"
            ):
                request = analyst_agent_pb2.ValidateOptimizationHypothesisRequest(hypothesis=hypothesis)
                response = await self.stub.ValidateOptimizationHypothesis(request, timeout=self.settings.grpc_timeout, metadata=metadata)
            else:
                request = analyst_agent_pb2.ExecuteAnalysisRequest(
                    analysis_type="validate_optimization_hypothesis",
                    parameters={"hypothesis": json.dumps(hypothesis)},
                )
                response = await self.stub.ExecuteAnalysis(request, timeout=self.settings.grpc_timeout, metadata=metadata)

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
