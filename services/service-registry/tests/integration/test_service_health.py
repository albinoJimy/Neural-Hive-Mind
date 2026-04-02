"""Testes de integração para health check do service-registry (gRPC)."""

import pytest
from grpc.health.v1 import health_pb2, health_pb2_grpc


@pytest.mark.asyncio
class TestServiceRegistryHealth:
    """Testes de health check do Service Registry via gRPC."""

    @pytest.mark.skip(reason="Requires running gRPC server")
    async def test_grpc_health_check_serving(self, grpc_channel):
        """Testa health check gRPC retorna SERVING."""
        stub = health_pb2_grpc.HealthStub(grpc_channel)
        response = await stub.Check(health_pb2.HealthCheckRequest(service=""))

        assert response.status == health_pb2.HealthCheckResponse.SERVING

    @pytest.mark.skip(reason="Requires running gRPC server")
    async def test_grpc_watch_health(self, grpc_channel):
        """Testa watch de health check gRPC."""
        stub = health_pb2_grpc.HealthStub(grpc_channel)
        request = health_pb2.HealthCheckRequest(service="")

        responses = []
        async for response in stub.Watch(request):
            responses.append(response)
            if len(responses) >= 2:
                break

        assert len(responses) >= 1
        assert responses[0].status == health_pb2.HealthCheckResponse.SERVING
