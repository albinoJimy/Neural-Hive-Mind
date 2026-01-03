"""Service Registry client for service discovery."""
import asyncio
from typing import Dict, List, Optional
import time
import grpc
import structlog
from neural_hive_integration.proto_stubs import service_registry_pb2, service_registry_pb2_grpc

logger = structlog.get_logger()


class ServiceRegistryClient:
    """Client for Service Registry integration."""

    def __init__(self, host: str, port: int, connect_timeout_seconds: float = 10.0):
        """Initialize Service Registry client.

        Args:
            host: Service Registry host
            port: Service Registry port
            connect_timeout_seconds: Connection/call timeout in seconds
        """
        self.target = f"{host}:{port}"
        self.connect_timeout_seconds = connect_timeout_seconds
        self.service_id: str = None
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None

    async def _ensure_connection(self):
        """Ensure gRPC connection is established."""
        if not self.channel:
            # Configure channel options for connection backoff
            options = [
                ('grpc.initial_reconnect_backoff_ms', 1000),
                ('grpc.max_reconnect_backoff_ms', 10000),
                ('grpc.keepalive_time_ms', 30000),
                ('grpc.keepalive_timeout_ms', 10000),
            ]
            self.channel = grpc.aio.insecure_channel(self.target, options=options)
            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)

    async def register(
        self,
        service_name: str,
        capabilities: List[str],
        metadata: Dict,
        max_retries: int = 5,
        initial_delay: float = 1.0,
    ):
        """Register service with Service Registry with retry logic.

        Args:
            service_name: Name of the service to register
            capabilities: List of service capabilities
            metadata: Service metadata
            max_retries: Maximum number of registration attempts
            initial_delay: Initial delay between retries (exponential backoff)
        """
        for attempt in range(max_retries):
            try:
                logger.info(
                    "registering_with_service_registry",
                    target=self.target,
                    service_name=service_name,
                    attempt=attempt + 1,
                )

                await self._ensure_connection()

                request = service_registry_pb2.RegisterRequest(
                    agent_type=service_registry_pb2.WORKER,  # Usando WORKER como tipo genérico
                    capabilities=capabilities,
                    metadata=metadata,
                    namespace="production",  # Ajustar conforme ambiente se necessário
                    cluster="neural-hive",
                    version=metadata.get("version", "unknown"),
                )

                # Apply timeout to avoid blocking indefinitely
                response = await asyncio.wait_for(
                    self.stub.Register(request),
                    timeout=self.connect_timeout_seconds,
                )
                self.service_id = response.agent_id

                logger.info("service_registered", service_id=self.service_id)
                return

            except asyncio.TimeoutError:
                delay = initial_delay * (2**attempt)
                logger.warning(
                    "service_registration_timeout",
                    timeout_seconds=self.connect_timeout_seconds,
                    attempt=attempt + 1,
                    retry_in_seconds=delay,
                )

                # Reset connection on failure
                if self.channel:
                    await self.channel.close()
                    self.channel = None
                    self.stub = None

                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error("service_registration_exhausted_retries")
                    raise

            except Exception as e:
                delay = initial_delay * (2**attempt)  # Exponential backoff
                logger.warning(
                    "service_registration_failed",
                    error=str(e),
                    attempt=attempt + 1,
                    retry_in_seconds=delay,
                )

                # Reset connection on failure
                if self.channel:
                    await self.channel.close()
                    self.channel = None
                    self.stub = None

                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error("service_registration_exhausted_retries")
                    raise

    async def send_heartbeat(self, health_data: Dict):
        """Send heartbeat to Service Registry."""
        if not self.service_id:
            return
        await self._ensure_connection()
        try:
            telemetry = service_registry_pb2.AgentTelemetry(
                success_rate=health_data.get("success_rate", 1.0),
                avg_duration_ms=health_data.get("avg_duration_ms", 0),
                total_executions=health_data.get("total_executions", 0),
                failed_executions=health_data.get("failed_executions", 0),
                last_execution_at=int(time.time() * 1000)
            )
            request = service_registry_pb2.HeartbeatRequest(
                agent_id=self.service_id,
                telemetry=telemetry
            )
            # Apply timeout to heartbeat calls
            await asyncio.wait_for(
                self.stub.Heartbeat(request),
                timeout=self.connect_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "heartbeat_timeout",
                timeout_seconds=self.connect_timeout_seconds,
            )
        except Exception as e:
            logger.error("heartbeat_failed", error=str(e))

    async def deregister(self):
        """Deregister service from Service Registry."""
        if not self.service_id:
            return
        await self._ensure_connection()
        try:
            request = service_registry_pb2.DeregisterRequest(agent_id=self.service_id)
            # Apply timeout to deregister call
            await asyncio.wait_for(
                self.stub.Deregister(request),
                timeout=self.connect_timeout_seconds,
            )
            logger.info("service_deregistered", service_id=self.service_id)
        except asyncio.TimeoutError:
            logger.warning(
                "deregister_timeout",
                timeout_seconds=self.connect_timeout_seconds,
            )
        except Exception as e:
            logger.error("deregister_failed", error=str(e))
        finally:
            if self.channel:
                await self.channel.close()
                self.channel = None
