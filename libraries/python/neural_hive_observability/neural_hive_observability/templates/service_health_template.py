"""
Standardized Health Check Template for Neural Hive-Mind Services.

This template provides a standardized way to implement health checks
for all Neural Hive-Mind services using the observability library.

Usage:
    Copy this template to your service and modify it according to your
    service's specific components and requirements.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import logging

from fastapi import FastAPI, JSONResponse
from neural_hive_observability.health import (
    HealthManager, RedisHealthCheck, DatabaseHealthCheck, KafkaHealthCheck,
    CustomHealthCheck, HealthStatus
)

logger = logging.getLogger(__name__)

class ServiceHealthManager:
    """
    Standardized health manager for Neural Hive-Mind services.

    This class encapsulates common health check patterns and provides
    standardized endpoints for Kubernetes probes.
    """

    def __init__(self, service_name: str, component: str, layer: str, version: str = "1.0.0"):
        """
        Initialize health manager for a Neural Hive service.

        Args:
            service_name: Name of the service (e.g., "gateway-intencoes")
            component: Neural Hive component type (e.g., "gateway", "processor")
            layer: Neural Hive layer (e.g., "experiencia", "cognicao", "orquestracao")
            version: Service version
        """
        self.service_name = service_name
        self.component = component
        self.layer = layer
        self.version = version
        self.health_manager = HealthManager()
        self._initialized = False

    def add_redis_check(self, redis_client, name: str = "redis"):
        """Add Redis health check."""
        if redis_client:
            self.health_manager.add_check(
                RedisHealthCheck(name, lambda: redis_client.ping() if redis_client else False)
            )

    def add_database_check(self, connection_check, name: str = "database"):
        """Add database health check."""
        if connection_check:
            self.health_manager.add_check(
                DatabaseHealthCheck(name, connection_check)
            )

    def add_kafka_check(self, producer_check, name: str = "kafka"):
        """Add Kafka health check."""
        if producer_check:
            self.health_manager.add_check(
                KafkaHealthCheck(name, producer_check)
            )

    def add_custom_check(self, name: str, check_func, description: str = None):
        """Add custom health check for service-specific components."""
        self.health_manager.add_check(
            CustomHealthCheck(
                name,
                check_func,
                description or f"{name} component"
            )
        )

    def mark_initialized(self):
        """Mark the health manager as initialized."""
        self._initialized = True

    def is_initialized(self) -> bool:
        """Check if health manager is initialized."""
        return self._initialized

    async def get_health_response(self) -> Dict[str, Any]:
        """Get standardized health check response."""
        if not self._initialized:
            return {
                "status": "unhealthy",
                "message": "Health manager not initialized",
                "timestamp": datetime.utcnow().isoformat(),
                "version": self.version,
                "service_name": self.service_name
            }

        try:
            # Run all health checks
            health_results = await self.health_manager.check_all()
            overall_status = self.health_manager.get_overall_status()

            # Format results for response
            component_statuses = {}
            for name, result in health_results.items():
                component_statuses[name] = {
                    "status": result.status.value,
                    "message": result.message,
                    "duration_seconds": result.duration_seconds,
                    "timestamp": result.timestamp,
                    "details": result.details
                }

            return {
                "status": overall_status.value,
                "timestamp": datetime.utcnow().isoformat(),
                "version": self.version,
                "service_name": self.service_name,
                "neural_hive_component": self.component,
                "neural_hive_layer": self.layer,
                "components": component_statuses
            }

        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {
                "status": "unhealthy",
                "message": f"Health check error: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
                "version": self.version,
                "service_name": self.service_name
            }

    async def get_readiness_response(self, critical_checks: list = None) -> Dict[str, Any]:
        """
        Get standardized readiness check response.

        Args:
            critical_checks: List of critical component names that must be healthy
                           for the service to be considered ready. If None, all
                           components must be healthy.
        """
        if not self._initialized:
            return {
                "status": "not_ready",
                "message": "Health manager not initialized",
                "timestamp": datetime.utcnow().isoformat()
            }

        try:
            if critical_checks is None:
                # All components must be healthy
                overall_status = self.health_manager.get_overall_status()
                overall_ready = overall_status == HealthStatus.HEALTHY
            else:
                # Only critical components must be healthy
                overall_ready = True
                for check_name in critical_checks:
                    result = await self.health_manager.check_single(check_name)
                    if result and result.status != HealthStatus.HEALTHY:
                        overall_ready = False
                        break

            return {
                "status": "ready" if overall_ready else "not_ready",
                "timestamp": datetime.utcnow().isoformat(),
                "service_name": self.service_name,
                "neural_hive_component": self.component
            }

        except Exception as e:
            logger.error(f"Readiness check error: {e}")
            return {
                "status": "not_ready",
                "message": f"Readiness check error: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }

def setup_health_endpoints(app: FastAPI, health_manager: ServiceHealthManager, critical_checks: list = None):
    """
    Setup standardized health and readiness endpoints for a FastAPI app.

    Args:
        app: FastAPI application instance
        health_manager: Initialized ServiceHealthManager instance
        critical_checks: List of critical components for readiness check
    """

    @app.get("/health")
    async def health_check():
        """Standardized health check endpoint using Neural Hive-Mind observability library"""
        response_data = await health_manager.get_health_response()

        # Return appropriate HTTP status code based on health
        if response_data.get("status") == "unhealthy":
            return JSONResponse(status_code=503, content=response_data)
        elif response_data.get("status") == "degraded":
            return JSONResponse(status_code=200, content=response_data)
        else:
            return response_data

    @app.get("/ready")
    async def readiness_check():
        """Kubernetes readiness probe endpoint - checks if service is ready to accept traffic"""
        response_data = await health_manager.get_readiness_response(critical_checks)

        status_code = 200 if response_data.get("status") == "ready" else 503
        return JSONResponse(status_code=status_code, content=response_data)

    @app.get("/health/{component_name}")
    async def component_health_check(component_name: str):
        """Check health of a specific component"""
        if not health_manager.is_initialized():
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "message": "Health manager not initialized",
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        try:
            result = await health_manager.health_manager.check_single(component_name)
            if result is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "status": "not_found",
                        "message": f"Component '{component_name}' not found",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )

            response_data = {
                "component": component_name,
                "status": result.status.value,
                "message": result.message,
                "duration_seconds": result.duration_seconds,
                "timestamp": result.timestamp,
                "details": result.details
            }

            status_code = 503 if result.status == HealthStatus.UNHEALTHY else 200
            return JSONResponse(status_code=status_code, content=response_data)

        except Exception as e:
            logger.error(f"Component health check error for {component_name}: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "component": component_name,
                    "status": "unhealthy",
                    "message": f"Health check error: {str(e)}",
                    "timestamp": datetime.utcnow().isoformat()
                }
            )


# Example usage for different types of services:

def setup_gateway_health(app: FastAPI, redis_client=None, kafka_producer=None,
                        asr_pipeline=None, nlu_pipeline=None, oauth2_validator=None):
    """Example setup for Gateway service health checks."""
    health_manager = ServiceHealthManager(
        service_name="gateway-intencoes",
        component="gateway",
        layer="experiencia"
    )

    # Add component-specific health checks
    if redis_client:
        health_manager.add_redis_check(redis_client)

    if kafka_producer:
        health_manager.add_kafka_check(
            lambda: kafka_producer.is_ready() if kafka_producer else False
        )

    if asr_pipeline:
        health_manager.add_custom_check(
            "asr_pipeline",
            lambda: asr_pipeline.is_ready() if asr_pipeline else False,
            "ASR Pipeline"
        )

    if nlu_pipeline:
        health_manager.add_custom_check(
            "nlu_pipeline",
            lambda: nlu_pipeline.is_ready() if nlu_pipeline else False,
            "NLU Pipeline"
        )

    if oauth2_validator:
        health_manager.add_custom_check(
            "oauth2_validator",
            lambda: True,  # OAuth2 validator is healthy if initialized
            "OAuth2 Validator"
        )

    health_manager.mark_initialized()

    # Setup endpoints with critical components for readiness
    setup_health_endpoints(app, health_manager, critical_checks=["redis", "kafka"])

    return health_manager


def setup_processor_health(app: FastAPI, database_conn=None, message_queue=None):
    """Example setup for Processor service health checks."""
    health_manager = ServiceHealthManager(
        service_name="plan-processor",
        component="processor",
        layer="cognicao"
    )

    if database_conn:
        health_manager.add_database_check(
            lambda: database_conn.is_connected() if database_conn else False
        )

    if message_queue:
        health_manager.add_custom_check(
            "message_queue",
            lambda: message_queue.is_healthy() if message_queue else False,
            "Message Queue"
        )

    health_manager.mark_initialized()
    setup_health_endpoints(app, health_manager, critical_checks=["database"])

    return health_manager