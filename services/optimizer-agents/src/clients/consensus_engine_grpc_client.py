"""Cliente gRPC para Consensus Engine com suporte a mTLS via SPIFFE."""

from typing import Dict, List, Optional, Tuple

import grpc
import structlog

from neural_hive_observability import instrument_grpc_channel
from src.config.settings import get_settings

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

# Proto imports - will be available after `make proto` compilation
try:
    from proto import consensus_engine_extensions_pb2, consensus_engine_extensions_pb2_grpc
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    logger.warning("consensus_proto_not_compiled", message="Run 'make proto' to compile protocol buffers")


class ConsensusEngineGrpcClient:
    """
    Cliente gRPC para Consensus Engine com suporte a mTLS via SPIFFE.

    Responsável por recalibração de pesos dos especialistas.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        self.spiffe_manager: Optional[SPIFFEManager] = None

    async def connect(self):
        """Estabelecer canal gRPC com Consensus Engine com suporte a mTLS."""
        try:
            target = self.settings.consensus_engine_endpoint

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

                logger.info('mtls_channel_configured', target=target, environment=self.settings.environment)
            else:
                # Fallback para canal inseguro (apenas desenvolvimento)
                if self.settings.environment in ['production', 'staging', 'prod']:
                    raise RuntimeError(
                        f"mTLS is required in {self.settings.environment} but SPIFFE X.509 is disabled."
                    )

                logger.warning('using_insecure_channel', target=target, environment=self.settings.environment)
                self.channel = grpc.aio.insecure_channel(
                    target,
                    options=[
                        ("grpc.max_send_message_length", 100 * 1024 * 1024),
                        ("grpc.max_receive_message_length", 100 * 1024 * 1024),
                        ("grpc.keepalive_time_ms", 30000),
                    ],
                )

            self.channel = instrument_grpc_channel(self.channel, service_name='consensus-engine')

            # Criar stub quando proto estiver compilado
            if PROTO_AVAILABLE:
                self.stub = consensus_engine_extensions_pb2_grpc.ConsensusOptimizationStub(self.channel)
                logger.info("consensus_engine_stub_created")
            else:
                logger.warning("consensus_engine_stub_not_created", reason="proto_not_compiled")

            # Testar conexão com timeout
            import asyncio
            try:
                await asyncio.wait_for(self.channel.channel_ready(), timeout=5.0)
                logger.info("consensus_engine_grpc_connected", endpoint=target)
            except asyncio.TimeoutError:
                logger.warning("consensus_engine_grpc_connection_timeout", endpoint=target)
        except Exception as e:
            logger.error("consensus_engine_grpc_connection_failed", error=str(e))
            raise

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """Obter metadata gRPC com JWT-SVID para autenticação."""
        if not getattr(self.settings, 'spiffe_enabled', False) or not self.spiffe_manager:
            return []

        try:
            audience = f"consensus-engine.{self.settings.spiffe_trust_domain}"
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
            logger.info("consensus_engine_grpc_disconnected")

    async def get_current_weights(self) -> Optional[Dict[str, float]]:
        """
        Obter pesos atuais dos especialistas.

        Returns:
            Dict com {specialist_type: weight}
        """
        try:
            if PROTO_AVAILABLE and self.stub:
                request = consensus_engine_extensions_pb2.GetCurrentWeightsRequest()
                response = await self.stub.GetCurrentWeights(request, timeout=self.settings.grpc_timeout)
                weights = dict(response.weights)
                logger.info("current_weights_retrieved", weights=weights, source="grpc")
                return weights
            else:
                # Stub temporário quando proto não compilado
                logger.warning("get_current_weights_stub_called", reason="proto_not_available")
                weights = {
                    "technical": 0.20,
                    "safety": 0.20,
                    "business": 0.20,
                    "ethical": 0.20,
                    "legal": 0.20,
                }
                logger.info("current_weights_retrieved", weights=weights, source="stub")
                return weights

        except grpc.RpcError as e:
            logger.error("get_current_weights_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("get_current_weights_failed", error=str(e))
            return None

    async def update_weights(
        self, weights: Dict[str, float], justification: str, optimization_id: str
    ) -> bool:
        """
        Atualizar pesos dos especialistas.

        Args:
            weights: Novos pesos {specialist_type: weight}
            justification: Justificativa da mudança
            optimization_id: ID da otimização

        Returns:
            True se bem-sucedido
        """
        try:
            if PROTO_AVAILABLE and self.stub:
                request = consensus_engine_extensions_pb2.UpdateWeightsRequest(
                    weights=weights,
                    justification=justification,
                    optimization_id=optimization_id,
                    validate_before_apply=True
                )
                response = await self.stub.UpdateWeights(request, timeout=self.settings.grpc_timeout)
                logger.info(
                    "weights_updated",
                    optimization_id=optimization_id,
                    weights=weights,
                    success=response.success,
                    source="grpc"
                )
                return response.success
            else:
                # Stub temporário quando proto não compilado
                logger.warning(
                    "update_weights_stub_called",
                    weights=weights,
                    justification=justification,
                    optimization_id=optimization_id,
                    reason="proto_not_available"
                )
                logger.info(
                    "weights_updated",
                    optimization_id=optimization_id,
                    weights=weights,
                    source="stub"
                )
                return True

        except grpc.RpcError as e:
            logger.error(
                "update_weights_failed",
                optimization_id=optimization_id,
                error=str(e),
                code=e.code(),
            )
            return False
        except Exception as e:
            logger.error("update_weights_failed", optimization_id=optimization_id, error=str(e))
            return False

    async def get_consensus_metrics(self, time_range: str = "1h") -> Optional[Dict]:
        """
        Obter métricas de consenso.

        Args:
            time_range: Intervalo de tempo (ex: "1h", "24h")

        Returns:
            Dict com métricas de consenso
        """
        try:
            if PROTO_AVAILABLE and self.stub:
                request = consensus_engine_extensions_pb2.GetConsensusMetricsRequest(time_range=time_range)
                response = await self.stub.GetConsensusMetrics(request, timeout=self.settings.grpc_timeout)
                metrics = {
                    "average_divergence": response.average_divergence,
                    "average_confidence": response.average_confidence,
                    "average_risk": response.average_risk,
                    "specialist_accuracy": dict(response.specialist_accuracy),
                    "total_decisions": response.total_decisions,
                }
                logger.info("consensus_metrics_retrieved", time_range=time_range, source="grpc")
                return metrics
            else:
                # Stub temporário quando proto não compilado
                logger.warning("get_consensus_metrics_stub_called", time_range=time_range, reason="proto_not_available")
                metrics = {
                    "average_divergence": 0.12,
                    "average_confidence": 0.85,
                    "average_risk": 0.15,
                    "specialist_accuracy": {
                        "technical": 0.88,
                        "safety": 0.92,
                        "business": 0.85,
                        "ethical": 0.90,
                        "legal": 0.87,
                    },
                    "total_decisions": 1234,
                }
                logger.info("consensus_metrics_retrieved", time_range=time_range, source="stub")
                return metrics

        except grpc.RpcError as e:
            logger.error("get_consensus_metrics_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("get_consensus_metrics_failed", error=str(e))
            return None

    async def validate_weight_adjustment(self, proposed_weights: Dict[str, float]) -> bool:
        """
        Validar se ajuste de pesos é seguro.

        Args:
            proposed_weights: Pesos propostos

        Returns:
            True se válido
        """
        try:
            if PROTO_AVAILABLE and self.stub:
                request = consensus_engine_extensions_pb2.ValidateWeightAdjustmentRequest(
                    proposed_weights=proposed_weights
                )
                response = await self.stub.ValidateWeightAdjustment(request, timeout=self.settings.grpc_timeout)
                logger.info("weight_adjustment_validated", weights=proposed_weights, valid=response.is_valid, source="grpc")
                return response.is_valid
            else:
                # Validações locais temporárias quando proto não compilado
                logger.warning("validate_weight_adjustment_stub_called", reason="proto_not_available")

                # Verificar se somam 1.0 (±0.01 tolerância)
                total = sum(proposed_weights.values())
                if not (0.99 <= total <= 1.01):
                    logger.warning("weights_do_not_sum_to_one", total=total)
                    return False

                # Verificar se todos >= 0.1 e <= 0.4 (evitar dominância)
                for specialist, weight in proposed_weights.items():
                    if not (0.1 <= weight <= 0.4):
                        logger.warning("weight_out_of_range", specialist=specialist, weight=weight)
                        return False

                # Verificar se todos os 5 especialistas estão presentes
                required_specialists = {"technical", "safety", "business", "ethical", "legal"}
                if set(proposed_weights.keys()) != required_specialists:
                    logger.warning("missing_specialists", provided=list(proposed_weights.keys()))
                    return False

                logger.info("weight_adjustment_validated", weights=proposed_weights, source="stub")
                return True

        except grpc.RpcError as e:
            logger.error("validate_weight_adjustment_failed", error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("validate_weight_adjustment_failed", error=str(e))
            return False

    async def rollback_weights(self, optimization_id: str) -> bool:
        """
        Reverter pesos para versão anterior.

        Args:
            optimization_id: ID da otimização a reverter

        Returns:
            True se bem-sucedido
        """
        try:
            if PROTO_AVAILABLE and self.stub:
                request = consensus_engine_extensions_pb2.RollbackWeightsRequest(
                    optimization_id=optimization_id
                )
                response = await self.stub.RollbackWeights(request, timeout=self.settings.grpc_timeout)
                logger.info("weights_rolled_back", optimization_id=optimization_id, success=response.success, source="grpc")
                return response.success
            else:
                # Stub temporário quando proto não compilado
                logger.warning("rollback_weights_stub_called", optimization_id=optimization_id, reason="proto_not_available")
                logger.info("weights_rolled_back", optimization_id=optimization_id, source="stub")
                return True

        except grpc.RpcError as e:
            logger.error("rollback_weights_failed", optimization_id=optimization_id, error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("rollback_weights_failed", optimization_id=optimization_id, error=str(e))
            return False
