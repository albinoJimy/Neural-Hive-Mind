from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from datetime import datetime
from typing import Optional
import structlog
import base64
import json

logger = structlog.get_logger()

start_time = datetime.now()

# HTTP Bearer security scheme
security = HTTPBearer(auto_error=False)


class SPIFFEJWTValidator:
    '''Validator for SPIFFE JWT-SVID tokens on HTTP endpoints'''

    def __init__(self, config, app_state):
        self.config = config
        self.app_state = app_state
        self.logger = logger.bind(component='spiffe_jwt_validator')

    async def validate_token(self, token: str) -> Optional[str]:
        '''
        Validate JWT-SVID token and extract SPIFFE ID

        Returns:
            SPIFFE ID if valid, None otherwise
        '''
        try:
            spiffe_manager = self.app_state.get('spiffe_manager')

            # Try to use PyJWT with proper verification
            try:
                import jwt
                from cryptography.hazmat.primitives import serialization
                JWT_AVAILABLE = True
            except ImportError:
                JWT_AVAILABLE = False

            if JWT_AVAILABLE and spiffe_manager:
                # Get trust bundle keys
                trust_bundle_keys = spiffe_manager.get_trust_bundle_keys()
                if not trust_bundle_keys:
                    await spiffe_manager.get_trust_bundle()
                    trust_bundle_keys = spiffe_manager.get_trust_bundle_keys()

                # Decode header to get kid
                unverified_header = jwt.get_unverified_header(token)
                kid = unverified_header.get('kid')

                # Find matching key
                public_key = None
                if kid and kid in trust_bundle_keys:
                    jwk = trust_bundle_keys[kid]
                    public_key = self._jwk_to_pem(jwk)
                elif trust_bundle_keys:
                    first_key = list(trust_bundle_keys.values())[0]
                    public_key = self._jwk_to_pem(first_key)

                if not public_key:
                    self.logger.warning('no_public_key_found', kid=kid)
                    return None

                # Verify and decode
                decoded = jwt.decode(
                    token,
                    public_key,
                    algorithms=['RS256', 'ES256', 'ES384'],
                    options={
                        'verify_signature': True,
                        'verify_exp': True,
                        'verify_nbf': True,
                        'verify_iat': True,
                        'require_exp': True,
                    }
                )

                spiffe_id = decoded.get('sub')
                if not spiffe_id or not spiffe_id.startswith('spiffe://'):
                    self.logger.warning('invalid_spiffe_id_in_token', sub=spiffe_id)
                    return None

                return spiffe_id

            else:
                # Fail-closed in production/staging
                environment = getattr(self.config, 'environment', 'development').lower()
                if environment in ('production', 'staging'):
                    self.logger.error(
                        'jwt_validation_unavailable_production',
                        jwt_lib=JWT_AVAILABLE,
                        spiffe_manager=spiffe_manager is not None,
                        environment=environment
                    )
                    return None

                # Dev fallback - decode without verification
                self.logger.warning('jwt_validation_unavailable_dev', environment=environment)
                parts = token.split('.')
                if len(parts) != 3:
                    return None

                payload_part = parts[1]
                padding = 4 - len(payload_part) % 4
                if padding != 4:
                    payload_part += '=' * padding

                payload = json.loads(base64.urlsafe_b64decode(payload_part))
                spiffe_id = payload.get('sub')

                if spiffe_id and spiffe_id.startswith('spiffe://'):
                    return spiffe_id
                return None

        except Exception as e:
            self.logger.error('jwt_validation_error', error=str(e))
            return None

    def _jwk_to_pem(self, jwk: dict) -> Optional[str]:
        '''Convert JWK to PEM format'''
        try:
            import jwt.algorithms as jwt_algs
            from cryptography.hazmat.primitives import serialization

            if hasattr(jwt_algs, 'RSAAlgorithm'):
                algo = jwt_algs.RSAAlgorithm(jwt_algs.RSAAlgorithm.SHA256)
                public_key = algo.from_jwk(json.dumps(jwk))
                pem = public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )
                return pem.decode('utf-8')
            return None
        except Exception as e:
            self.logger.error('jwk_to_pem_failed', error=str(e))
            return None


def create_http_server(config, app_state):
    '''Criar servidor HTTP FastAPI para health checks e métricas'''

    app = FastAPI(
        title='Worker Agents',
        version='1.0.0',
        description='Worker Agents para execução distribuída de tarefas'
    )

    # SPIFFE JWT validator instance
    jwt_validator = SPIFFEJWTValidator(config, app_state)

    async def verify_spiffe_token(
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> Optional[str]:
        '''
        Dependency to verify SPIFFE JWT-SVID tokens.
        Returns the SPIFFE ID if valid, raises HTTPException otherwise.
        '''
        # Check if SPIFFE validation is enabled
        spiffe_enabled = getattr(config, 'spiffe_enabled', False)
        if not spiffe_enabled:
            return None

        # Check if fallback is allowed (for dev environments)
        fallback_allowed = getattr(config, 'spiffe_fallback_allowed', False)

        if credentials is None:
            if fallback_allowed:
                logger.warning('spiffe_auth_skipped_no_token', fallback_allowed=True)
                return None
            raise HTTPException(status_code=401, detail='Missing authentication token')

        spiffe_id = await jwt_validator.validate_token(credentials.credentials)

        if not spiffe_id:
            if fallback_allowed:
                logger.warning('spiffe_auth_failed_fallback', fallback_allowed=True)
                return None
            raise HTTPException(status_code=401, detail='Invalid or expired SPIFFE JWT token')

        return spiffe_id

    @app.get('/health')
    async def health():
        '''Health check (liveness probe) with Vault status'''
        overall_status = 'healthy'
        vault_status = {
            'enabled': getattr(config, 'vault_enabled', False),
            'status': 'disabled'
        }

        if vault_status['enabled']:
            vault_client = app_state.get('vault_client')
            if vault_client:
                try:
                    # Check if Vault client has health_check method
                    if hasattr(vault_client, 'vault_client') and vault_client.vault_client:
                        vault_healthy = await vault_client.vault_client.health_check()
                        vault_status['status'] = 'healthy' if vault_healthy else 'unhealthy'
                    else:
                        vault_status['status'] = 'client_not_initialized'

                    if vault_status['status'] == 'unhealthy':
                        # Check fail-open policy
                        vault_fail_open = getattr(config, 'vault_fail_open', False)
                        if not vault_fail_open:
                            overall_status = 'unhealthy'
                            vault_status['error'] = 'Vault unhealthy and fail_open=false'
                except Exception as e:
                    vault_status['status'] = 'error'
                    vault_status['error'] = str(e)
                    vault_fail_open = getattr(config, 'vault_fail_open', False)
                    if not vault_fail_open:
                        overall_status = 'unhealthy'
            else:
                vault_status['status'] = 'not_initialized'
                vault_fail_open = getattr(config, 'vault_fail_open', False)
                if not vault_fail_open:
                    overall_status = 'unhealthy'
                    vault_status['error'] = 'Vault enabled but client not initialized'

        return {
            'status': overall_status,
            'agent_id': config.agent_id,
            'timestamp': int(datetime.now().timestamp() * 1000),
            'checks': {
                'vault': vault_status
            }
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
    async def status(spiffe_id: Optional[str] = Depends(verify_spiffe_token)):
        '''Status do Worker Agent - requires SPIFFE JWT authentication'''
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
            },
            'authenticated_spiffe_id': spiffe_id
        }

    @app.on_event('startup')
    async def startup():
        logger.info('http_server_started', port=config.http_port)

    @app.on_event('shutdown')
    async def shutdown():
        logger.info('http_server_shutdown')

    return app
