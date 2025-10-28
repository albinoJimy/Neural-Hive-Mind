from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from datetime import datetime
import structlog

logger = structlog.get_logger()

start_time = datetime.now()


def create_http_server(config, app_state):
    '''Criar servidor HTTP FastAPI para health checks e métricas'''

    app = FastAPI(
        title='Worker Agents',
        version='1.0.0',
        description='Worker Agents para execução distribuída de tarefas'
    )

    @app.get('/health')
    async def health():
        '''Health check (liveness probe)'''
        return {
            'status': 'healthy',
            'agent_id': config.agent_id,
            'timestamp': int(datetime.now().timestamp() * 1000)
        }

    @app.get('/ready')
    async def ready():
        '''Readiness check'''
        registry_client = app_state.get('registry_client')
        execution_engine = app_state.get('execution_engine')

        checks = {
            'registered': registry_client.is_registered() if registry_client else False,
            'active_tasks': len(execution_engine.active_tasks) if execution_engine else 0,
            'max_concurrent': config.max_concurrent_tasks
        }

        is_ready = checks['registered']

        if is_ready:
            return {'ready': True, 'checks': checks}
        else:
            return {'ready': False, 'checks': checks}, 503

    @app.get('/metrics')
    async def metrics():
        '''Expor métricas Prometheus'''
        return PlainTextResponse(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )

    @app.get('/api/v1/status')
    async def status():
        '''Status do Worker Agent'''
        registry_client = app_state.get('registry_client')
        execution_engine = app_state.get('execution_engine')
        uptime_seconds = (datetime.now() - start_time).total_seconds()

        return {
            'agent_id': config.agent_id,
            'agent_type': 'WORKER',
            'capabilities': config.supported_task_types,
            'active_tasks': len(execution_engine.active_tasks) if execution_engine else 0,
            'max_concurrent_tasks': config.max_concurrent_tasks,
            'registered': registry_client.is_registered() if registry_client else False,
            'uptime_seconds': int(uptime_seconds),
            'telemetry': {
                'namespace': config.namespace,
                'cluster': config.cluster,
                'version': config.service_version
            }
        }

    @app.on_event('startup')
    async def startup():
        logger.info('http_server_started', port=config.http_port)

    @app.on_event('shutdown')
    async def shutdown():
        logger.info('http_server_shutdown')

    return app
