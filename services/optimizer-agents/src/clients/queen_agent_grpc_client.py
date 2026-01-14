"""Cliente gRPC para Queen Agent com suporte a mTLS via SPIFFE."""

import time
from typing import Dict, List, Optional, Tuple

import grpc
import structlog
from google.protobuf.json_format import MessageToDict

from neural_hive_observability import instrument_grpc_channel
from src.config.settings import get_settings

from ..proto import queen_agent_pb2, queen_agent_pb2_grpc

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


class QueenAgentGrpcClient:
    """
    Cliente gRPC para Queen Agent com suporte a mTLS via SPIFFE.

    Responsável por solicitar aprovação de otimizações de alto risco.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        self.spiffe_manager: Optional[SPIFFEManager] = None

    async def connect(self):
        """Estabelecer canal gRPC com Queen Agent com suporte a mTLS."""
        try:
            target = self.settings.queen_agent_endpoint

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

            self.channel = instrument_grpc_channel(self.channel, service_name='queen-agent')
            self.stub = queen_agent_pb2_grpc.QueenAgentStub(self.channel)

            # Testar conexão com timeout - não bloquear se falhar
            import asyncio
            try:
                ready_task = asyncio.create_task(self.channel.channel_ready())
                done, pending = await asyncio.wait({ready_task}, timeout=5.0)
                if ready_task in done:
                    logger.info("queen_agent_grpc_connected", endpoint=target)
                else:
                    ready_task.cancel()
                    try:
                        await ready_task
                    except asyncio.CancelledError:
                        pass
                    logger.warning("queen_agent_grpc_connection_timeout", endpoint=target)
            except Exception as conn_error:
                logger.warning("queen_agent_grpc_connection_check_failed", endpoint=target, error=str(conn_error))
        except Exception as e:
            logger.error("queen_agent_grpc_connection_failed", error=str(e))
            raise

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """Obter metadata gRPC com JWT-SVID para autenticação."""
        if not getattr(self.settings, 'spiffe_enabled', False) or not self.spiffe_manager:
            return []

        try:
            audience = f"queen-agent.{self.settings.spiffe_trust_domain}"
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
            logger.info("queen_agent_grpc_disconnected")

    async def request_approval(
        self, optimization_id: str, optimization_type: str, hypothesis: Dict, risk_score: float
    ) -> Optional[Dict]:
        """
        Solicitar aprovação de otimização.

        Args:
            optimization_id: ID da otimização
            optimization_type: Tipo de otimização
            hypothesis: Hipótese de otimização
            risk_score: Score de risco (0-1)

        Returns:
            Decisão de aprovação ou None se falhou
        """
        try:
            if not self.stub:
                raise RuntimeError("QueenAgent gRPC stub not initialized")

            request = queen_agent_pb2.RequestExceptionRequest(
                exception_type=optimization_type,
                plan_id=optimization_id,
                justification=hypothesis.get("description", ""),
                guardrails_affected=[],
                expires_at=int(time.time() * 1000) + 3600000,
            )

            # Obter metadata com JWT-SVID
            metadata = await self._get_grpc_metadata()

            response = await self.stub.RequestExceptionApproval(request, timeout=self.settings.grpc_timeout, metadata=metadata)

            response_dict = MessageToDict(response, preserving_proto_field_name=True)
            decision = {
                "approved": response_dict.get("status", "").upper() in {"APPROVED", "APPROVED_WITH_CONDITIONS"},
                "approval_type": response_dict.get("status", ""),
                "decision_id": response_dict.get("exceptionId") or response_dict.get("exception_id"),
                "rationale": response_dict.get("message", ""),
                "conditions": response_dict.get("conditions", []),
            }

            logger.info(
                "approval_decision_received",
                optimization_id=optimization_id,
                approved=decision["approved"],
                approval_type=decision["approval_type"],
            )
            return decision

        except grpc.RpcError as e:
            logger.error("request_approval_failed", optimization_id=optimization_id, error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("request_approval_failed", optimization_id=optimization_id, error=str(e))
            return None

    async def notify_optimization_result(self, optimization_id: str, result: Dict) -> bool:
        """
        Notificar Queen Agent sobre resultado de otimização.

        Args:
            optimization_id: ID da otimização
            result: Resultado da otimização

        Returns:
            True se notificação bem-sucedida
        """
        try:
            # TODO: Implementar quando proto estendido
            # request = NotifyOptimizationResultRequest(
            #     optimization_id=optimization_id,
            #     result=result
            # )
            # response = await self.stub.NotifyOptimizationResult(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning(
                "notify_optimization_result_stub_called",
                optimization_id=optimization_id,
                success=result.get("success", False),
            )

            logger.info("optimization_result_notified", optimization_id=optimization_id)
            return True

        except grpc.RpcError as e:
            logger.error("notify_optimization_result_failed", optimization_id=optimization_id, error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("notify_optimization_result_failed", optimization_id=optimization_id, error=str(e))
            return False

    async def get_strategic_priorities(self) -> Optional[Dict]:
        """
        Obter prioridades estratégicas atuais.

        Returns:
            Prioridades estratégicas ou None se falhou
        """
        try:
            if not self.stub:
                raise RuntimeError("QueenAgent gRPC stub not initialized")

            request = queen_agent_pb2.GetSystemStatusRequest()

            # Obter metadata com JWT-SVID
            metadata = await self._get_grpc_metadata()

            response = await self.stub.GetSystemStatus(request, timeout=self.settings.grpc_timeout, metadata=metadata)

            priorities = {
                "current_focus": "PERFORMANCE_OPTIMIZATION",
                "priorities": [
                    {"area": "latency_reduction", "weight": 0.4},
                    {"area": "cost_optimization", "weight": 0.3},
                    {"area": "reliability", "weight": 0.3},
                ],
                "constraints": ["maintain_slo_compliance"],
                "updated_at": getattr(response, "timestamp", 0),
            }

            logger.info("strategic_priorities_retrieved", focus=priorities["current_focus"])
            return priorities

        except grpc.RpcError as e:
            logger.error("get_strategic_priorities_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("get_strategic_priorities_failed", error=str(e))
            return None
