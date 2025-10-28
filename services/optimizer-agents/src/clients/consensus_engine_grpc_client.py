from typing import Dict, Optional

import grpc
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger()


class ConsensusEngineGrpcClient:
    """
    Cliente gRPC para Consensus Engine.

    Responsável por recalibração de pesos dos especialistas.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None

    async def connect(self):
        """Estabelecer canal gRPC com Consensus Engine."""
        try:
            # Criar canal gRPC assíncrono
            self.channel = grpc.aio.insecure_channel(
                self.settings.consensus_engine_endpoint,
                options=[
                    ("grpc.max_send_message_length", 100 * 1024 * 1024),
                    ("grpc.max_receive_message_length", 100 * 1024 * 1024),
                    ("grpc.keepalive_time_ms", 30000),
                ],
            )

            # TODO: Criar stub quando proto estendido for compilado
            # from consensus_engine_pb2_grpc import ConsensusEngineStub
            # self.stub = ConsensusEngineStub(self.channel)

            # Testar conexão
            await self.channel.channel_ready()

            logger.info("consensus_engine_grpc_connected", endpoint=self.settings.consensus_engine_endpoint)
        except Exception as e:
            logger.error("consensus_engine_grpc_connection_failed", error=str(e))
            raise

    async def disconnect(self):
        """Fechar canal gRPC."""
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
            # TODO: Implementar quando proto estendido
            # request = GetCurrentWeightsRequest()
            # response = await self.stub.GetCurrentWeights(request, timeout=self.settings.grpc_timeout)
            # weights = dict(response.weights)

            # Stub temporário
            logger.warning("get_current_weights_stub_called")
            weights = {
                "technical": 0.20,
                "safety": 0.20,
                "business": 0.20,
                "ethical": 0.20,
                "legal": 0.20,
            }

            logger.info("current_weights_retrieved", weights=weights)
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
            # TODO: Implementar quando proto estendido
            # request = UpdateWeightsRequest(
            #     weights=weights,
            #     justification=justification,
            #     optimization_id=optimization_id
            # )
            # response = await self.stub.UpdateWeights(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning(
                "update_weights_stub_called",
                weights=weights,
                justification=justification,
                optimization_id=optimization_id,
            )

            logger.info(
                "weights_updated",
                optimization_id=optimization_id,
                weights=weights,
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
            # TODO: Implementar quando proto estendido
            # request = GetConsensusMetricsRequest(time_range=time_range)
            # response = await self.stub.GetConsensusMetrics(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning("get_consensus_metrics_stub_called", time_range=time_range)
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

            logger.info("consensus_metrics_retrieved", time_range=time_range)
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
            # TODO: Implementar quando proto estendido
            # request = ValidateWeightAdjustmentRequest(proposed_weights=proposed_weights)
            # response = await self.stub.ValidateWeightAdjustment(request, timeout=self.settings.grpc_timeout)
            # return response.valid

            # Validações locais temporárias
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

            logger.info("weight_adjustment_validated", weights=proposed_weights)
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
            # TODO: Implementar quando proto estendido
            # request = RollbackWeightsRequest(optimization_id=optimization_id)
            # response = await self.stub.RollbackWeights(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning("rollback_weights_stub_called", optimization_id=optimization_id)

            logger.info("weights_rolled_back", optimization_id=optimization_id)
            return True

        except grpc.RpcError as e:
            logger.error("rollback_weights_failed", optimization_id=optimization_id, error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("rollback_weights_failed", optimization_id=optimization_id, error=str(e))
            return False
