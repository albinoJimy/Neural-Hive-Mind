from fastapi import FastAPI, Request
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
import structlog

from ..config import get_settings
from ..integration.generation_webhook import router as webhook_router, webhook_handler, WebhookHandler
from .pipeline_api import router as pipeline_router

logger = structlog.get_logger()
settings = get_settings()


def create_app() -> FastAPI:
    """Cria aplicação FastAPI"""

    app = FastAPI(
        title='Code Forge',
        description='Neural Code Generation Pipeline',
        version='1.0.0'
    )

    # Include webhook router
    app.include_router(webhook_router)
    app.include_router(pipeline_router)

    @app.get('/health')
    async def health():
        """Health check (liveness)"""
        return {'status': 'healthy', 'service': 'code-forge'}

    @app.get('/ready')
    async def ready(request: Request):
        """Readiness check - verifica conectividade com dependências"""
        dependencies = {}

        # Verificar Postgres
        try:
            if hasattr(request.app.state, 'postgres_client') and request.app.state.postgres_client:
                dependencies['postgres'] = 'connected'
            else:
                dependencies['postgres'] = 'disconnected'
        except Exception as e:
            logger.warning('postgres_health_check_failed', error=str(e))
            dependencies['postgres'] = 'disconnected'

        # Verificar MongoDB
        try:
            if hasattr(request.app.state, 'mongodb_client') and request.app.state.mongodb_client:
                dependencies['mongodb'] = 'connected'
            else:
                dependencies['mongodb'] = 'disconnected'
        except Exception as e:
            logger.warning('mongodb_health_check_failed', error=str(e))
            dependencies['mongodb'] = 'disconnected'

        # Verificar Redis (com health_check)
        try:
            if hasattr(request.app.state, 'redis_client') and request.app.state.redis_client:
                is_healthy = await request.app.state.redis_client.health_check()
                dependencies['redis'] = 'connected' if is_healthy else 'disconnected'
            else:
                dependencies['redis'] = 'disconnected'
        except Exception as e:
            logger.warning('redis_health_check_failed', error=str(e))
            dependencies['redis'] = 'disconnected'

        # Verificar Kafka consumer
        try:
            if hasattr(request.app.state, 'kafka_consumer') and request.app.state.kafka_consumer:
                dependencies['kafka_consumer'] = 'connected'
            else:
                dependencies['kafka_consumer'] = 'disconnected'
        except Exception as e:
            logger.warning('kafka_consumer_health_check_failed', error=str(e))
            dependencies['kafka_consumer'] = 'disconnected'

        # Verificar Kafka producer
        try:
            if hasattr(request.app.state, 'kafka_producer') and request.app.state.kafka_producer:
                dependencies['kafka_producer'] = 'connected'
            else:
                dependencies['kafka_producer'] = 'disconnected'
        except Exception as e:
            logger.warning('kafka_producer_health_check_failed', error=str(e))
            dependencies['kafka_producer'] = 'disconnected'

        # Verificar Git client
        try:
            if hasattr(request.app.state, 'git_client') and request.app.state.git_client:
                dependencies['git'] = 'connected'
            else:
                dependencies['git'] = 'disconnected'
        except Exception as e:
            logger.warning('git_health_check_failed', error=str(e))
            dependencies['git'] = 'disconnected'

        # Verificar Snyk client
        try:
            if hasattr(request.app.state, 'snyk_client') and request.app.state.snyk_client:
                if request.app.state.snyk_client.enabled:
                    dependencies['snyk'] = 'connected'
                else:
                    dependencies['snyk'] = 'disabled'
            else:
                dependencies['snyk'] = 'disconnected'
        except Exception as e:
            logger.warning('snyk_health_check_failed', error=str(e))
            dependencies['snyk'] = 'disconnected'

        # Verificar Trivy client
        try:
            if hasattr(request.app.state, 'trivy_client') and request.app.state.trivy_client:
                if request.app.state.trivy_client.enabled:
                    dependencies['trivy'] = 'connected'
                else:
                    dependencies['trivy'] = 'disabled'
            else:
                dependencies['trivy'] = 'disconnected'
        except Exception as e:
            logger.warning('trivy_health_check_failed', error=str(e))
            dependencies['trivy'] = 'disconnected'

        # Verificar SonarQube client
        try:
            if hasattr(request.app.state, 'sonarqube_client') and request.app.state.sonarqube_client:
                if request.app.state.sonarqube_client.enabled:
                    dependencies['sonarqube'] = 'connected'
                else:
                    dependencies['sonarqube'] = 'disabled'
            else:
                dependencies['sonarqube'] = 'disconnected'
        except Exception as e:
            logger.warning('sonarqube_health_check_failed', error=str(e))
            dependencies['sonarqube'] = 'disconnected'

        # Verificar Sigstore client
        try:
            if hasattr(request.app.state, 'sigstore_client') and request.app.state.sigstore_client:
                if request.app.state.sigstore_client.enabled:
                    dependencies['sigstore'] = 'connected'
                else:
                    dependencies['sigstore'] = 'disabled'
            else:
                dependencies['sigstore'] = 'disconnected'
        except Exception as e:
            logger.warning('sigstore_health_check_failed', error=str(e))
            dependencies['sigstore'] = 'disconnected'

        # Verificar S3 Artifact client (com health check)
        s3_enabled = False
        try:
            if hasattr(request.app.state, 's3_artifact_client') and request.app.state.s3_artifact_client:
                s3_enabled = True
                is_healthy = await request.app.state.s3_artifact_client.health_check()
                dependencies['s3'] = 'connected' if is_healthy else 'disconnected'
            else:
                dependencies['s3'] = 'disabled'
        except Exception as e:
            logger.warning('s3_health_check_failed', error=str(e))
            dependencies['s3'] = 'disconnected'

        # Verificar Service Registry client
        try:
            if hasattr(request.app.state, 'service_registry') and request.app.state.service_registry:
                dependencies['service_registry'] = 'connected'
            else:
                dependencies['service_registry'] = 'disconnected'
        except Exception as e:
            logger.warning('service_registry_health_check_failed', error=str(e))
            dependencies['service_registry'] = 'disconnected'

        # Verificar Ticket client
        try:
            if hasattr(request.app.state, 'ticket_client') and request.app.state.ticket_client:
                dependencies['ticket_client'] = 'connected'
            else:
                dependencies['ticket_client'] = 'disconnected'
        except Exception as e:
            logger.warning('ticket_client_health_check_failed', error=str(e))
            dependencies['ticket_client'] = 'disconnected'

        # Clientes opcionais (MCP, LLM, Analyst)
        try:
            if hasattr(request.app.state, 'mcp_client') and request.app.state.mcp_client:
                dependencies['mcp'] = 'connected'
        except Exception:
            pass

        try:
            if hasattr(request.app.state, 'llm_client') and request.app.state.llm_client:
                dependencies['llm'] = 'connected'
        except Exception:
            pass

        try:
            if hasattr(request.app.state, 'analyst_client') and request.app.state.analyst_client:
                dependencies['analyst'] = 'connected'
        except Exception:
            pass

        # Core dependencies (excluir opcionais do cálculo de readiness)
        # Dependências obrigatórias devem estar 'connected'
        mandatory_deps = ['postgres', 'mongodb', 'redis', 'kafka_consumer', 'kafka_producer', 'git', 'service_registry', 'ticket_client']

        # S3 é obrigatório quando configurado (s3_enabled = True)
        if s3_enabled:
            mandatory_deps.append('s3')

        # Dependências opcionais (podem estar 'connected' ou 'disabled')
        optional_deps = ['snyk', 'trivy', 'sonarqube', 'sigstore']
        # S3 é opcional quando não configurado
        if not s3_enabled:
            optional_deps.append('s3')

        mandatory_ready = all(dependencies.get(dep) == 'connected' for dep in mandatory_deps)
        optional_ready = all(dependencies.get(dep) in ('connected', 'disabled') for dep in optional_deps)
        all_ready = mandatory_ready and optional_ready

        return {
            'status': 'ready' if all_ready else 'not_ready',
            'ready': all_ready,
            'dependencies': dependencies
        }

    @app.get('/metrics')
    async def metrics():
        """Métricas Prometheus"""
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )

    return app
