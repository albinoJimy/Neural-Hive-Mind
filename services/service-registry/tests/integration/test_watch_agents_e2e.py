"""
Testes end-to-end para WatchAgents com servidor gRPC real

Testa o fluxo completo de streaming de eventos:
1. Cliente inicia watch
2. Servidor registra/atualiza/deregistra agentes
3. Cliente recebe eventos em tempo real
"""

import pytest
import grpc
import asyncio
import os
import sys

# Reutilizar fixtures e helpers de test_discover_e2e.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from .test_discover_e2e import (
    MockEtcdClient, MockPheromoneClient,
    create_grpc_server, create_grpc_channel, get_free_port
)

from proto import service_registry_pb2, service_registry_pb2_grpc


class TestWatchAgentsE2E:
    """Testes E2E para WatchAgents streaming"""

    @pytest.fixture
    def etcd_client(self):
        return MockEtcdClient()

    @pytest.fixture
    def pheromone_client(self):
        return MockPheromoneClient()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_watch_receives_register_events(self, etcd_client, pheromone_client):
        """Testa que watch recebe eventos de registro"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Iniciar watch em background
                events = []
                watch_started = asyncio.Event()

                async def watch_task():
                    try:
                        request = service_registry_pb2.WatchAgentsRequest(
                            agent_type=service_registry_pb2.WORKER
                        )
                        watch_started.set()
                        async for event in stub.WatchAgents(request):
                            events.append(event)
                            if len(events) >= 2:  # Esperar 2 eventos
                                break
                    except grpc.aio.AioRpcError as e:
                        if e.code() != grpc.StatusCode.CANCELLED:
                            raise

                watch = asyncio.create_task(watch_task())

                # Aguardar watch iniciar
                await watch_started.wait()
                await asyncio.sleep(0.1)

                # Registrar 2 workers
                for i in range(2):
                    await stub.Register(
                        service_registry_pb2.RegisterRequest(
                            agent_type=service_registry_pb2.WORKER,
                            capabilities=["python"],
                            metadata={"worker": str(i)},
                            namespace="default",
                            cluster="local",
                            version="1.0.0"
                        )
                    )

                # Aguardar eventos
                try:
                    await asyncio.wait_for(watch, timeout=5.0)
                except asyncio.TimeoutError:
                    watch.cancel()

                # Validar eventos
                assert len(events) == 2
                for event in events:
                    assert event.event_type == service_registry_pb2.AgentChangeEvent.REGISTERED
                    assert event.agent.agent_type == service_registry_pb2.WORKER
                    assert event.timestamp > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_watch_receives_deregister_events(self, etcd_client, pheromone_client):
        """Testa que watch recebe eventos de deregistro"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Registrar agent primeiro
                register_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )
                agent_id = register_response.agent_id

                # Iniciar watch
                events = []
                watch_started = asyncio.Event()

                async def watch_task():
                    try:
                        request = service_registry_pb2.WatchAgentsRequest(
                            agent_type=service_registry_pb2.WORKER
                        )
                        watch_started.set()
                        async for event in stub.WatchAgents(request):
                            events.append(event)
                            if event.event_type == service_registry_pb2.AgentChangeEvent.DEREGISTERED:
                                break
                    except grpc.aio.AioRpcError as e:
                        if e.code() != grpc.StatusCode.CANCELLED:
                            raise

                watch = asyncio.create_task(watch_task())
                await watch_started.wait()
                await asyncio.sleep(0.1)

                # Deregistrar agent
                await stub.Deregister(
                    service_registry_pb2.DeregisterRequest(agent_id=agent_id)
                )

                # Aguardar evento
                try:
                    await asyncio.wait_for(watch, timeout=5.0)
                except asyncio.TimeoutError:
                    watch.cancel()

                # Validar evento de deregistro
                deregister_events = [e for e in events if e.event_type == service_registry_pb2.AgentChangeEvent.DEREGISTERED]
                assert len(deregister_events) == 1
                assert deregister_events[0].agent.agent_id == agent_id

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_watch_filters_by_agent_type(self, etcd_client, pheromone_client):
        """Testa que watch filtra por tipo de agente"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Iniciar watch apenas para WORKER
                events = []
                watch_started = asyncio.Event()

                async def watch_task():
                    try:
                        request = service_registry_pb2.WatchAgentsRequest(
                            agent_type=service_registry_pb2.WORKER
                        )
                        watch_started.set()
                        async for event in stub.WatchAgents(request):
                            events.append(event)
                            if len(events) >= 2:
                                break
                    except grpc.aio.AioRpcError as e:
                        if e.code() != grpc.StatusCode.CANCELLED:
                            raise

                watch = asyncio.create_task(watch_task())
                await watch_started.wait()
                await asyncio.sleep(0.1)

                # Registrar 2 workers e 1 guard
                for i in range(2):
                    await stub.Register(
                        service_registry_pb2.RegisterRequest(
                            agent_type=service_registry_pb2.WORKER,
                            capabilities=["python"],
                            metadata={},
                            namespace="default",
                            cluster="local",
                            version="1.0.0"
                        )
                    )

                await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.GUARD,
                        capabilities=["security"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )

                # Aguardar eventos
                try:
                    await asyncio.wait_for(watch, timeout=5.0)
                except asyncio.TimeoutError:
                    watch.cancel()

                # Validar que apenas WORKER events foram recebidos
                assert len(events) == 2
                for event in events:
                    assert event.agent.agent_type == service_registry_pb2.WORKER

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_watch_handles_client_disconnect(self, etcd_client, pheromone_client):
        """Testa que watch lida com desconexão do cliente"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            channel = grpc.aio.insecure_channel(f'localhost:{port}')
            stub = service_registry_pb2_grpc.ServiceRegistryStub(channel)

            # Iniciar watch
            request = service_registry_pb2.WatchAgentsRequest(
                agent_type=service_registry_pb2.WORKER
            )
            call = stub.WatchAgents(request)

            # Aguardar um pouco
            await asyncio.sleep(0.1)

            # Cancelar watch
            call.cancel()

            # Verificar que o cancelamento é tratado corretamente
            try:
                async for _ in call:
                    pass
            except (grpc.aio.AioRpcError, asyncio.CancelledError) as e:
                # Ambos CancelledError e RpcError CANCELLED são aceitáveis
                if isinstance(e, grpc.aio.AioRpcError):
                    assert e.code() == grpc.StatusCode.CANCELLED
                # CancelledError é esperado quando a stream é cancelada
                pass

            await channel.close()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_watch_receives_heartbeat_updates(self, etcd_client, pheromone_client):
        """Testa que watch recebe eventos de atualização via heartbeat"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Registrar agent
                register_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )
                agent_id = register_response.agent_id

                # Iniciar watch
                events = []
                watch_started = asyncio.Event()

                async def watch_task():
                    try:
                        request = service_registry_pb2.WatchAgentsRequest(
                            agent_type=service_registry_pb2.WORKER
                        )
                        watch_started.set()
                        async for event in stub.WatchAgents(request):
                            events.append(event)
                            # Esperar evento de atualização
                            if event.event_type == service_registry_pb2.AgentChangeEvent.UPDATED:
                                break
                    except grpc.aio.AioRpcError as e:
                        if e.code() != grpc.StatusCode.CANCELLED:
                            raise

                watch = asyncio.create_task(watch_task())
                await watch_started.wait()
                await asyncio.sleep(0.1)

                # Enviar heartbeat (deve gerar evento UPDATED)
                await stub.Heartbeat(
                    service_registry_pb2.HeartbeatRequest(
                        agent_id=agent_id,
                        telemetry=service_registry_pb2.AgentTelemetry(
                            success_rate=0.95,
                            avg_duration_ms=100,
                            total_executions=50,
                            failed_executions=2
                        )
                    )
                )

                # Aguardar eventos
                try:
                    await asyncio.wait_for(watch, timeout=5.0)
                except asyncio.TimeoutError:
                    watch.cancel()

                # Validar que evento UPDATED foi recebido
                update_events = [e for e in events if e.event_type == service_registry_pb2.AgentChangeEvent.UPDATED]
                assert len(update_events) >= 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_watch_all_agent_types(self, etcd_client, pheromone_client):
        """Testa watch sem filtro de tipo recebe todos os agentes"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Iniciar watch sem filtro de tipo
                events = []
                watch_started = asyncio.Event()

                async def watch_task():
                    try:
                        request = service_registry_pb2.WatchAgentsRequest()  # Sem agent_type
                        watch_started.set()
                        async for event in stub.WatchAgents(request):
                            events.append(event)
                            if len(events) >= 3:
                                break
                    except grpc.aio.AioRpcError as e:
                        if e.code() != grpc.StatusCode.CANCELLED:
                            raise

                watch = asyncio.create_task(watch_task())
                await watch_started.wait()
                await asyncio.sleep(0.1)

                # Registrar diferentes tipos de agentes
                await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )

                await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.GUARD,
                        capabilities=["security"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )

                await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.ANALYST,
                        capabilities=["analysis"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )

                # Aguardar eventos
                try:
                    await asyncio.wait_for(watch, timeout=5.0)
                except asyncio.TimeoutError:
                    watch.cancel()

                # Validar que recebeu eventos de todos os tipos
                assert len(events) == 3
                agent_types = {e.agent.agent_type for e in events}
                assert service_registry_pb2.WORKER in agent_types
                assert service_registry_pb2.GUARD in agent_types
                assert service_registry_pb2.ANALYST in agent_types
