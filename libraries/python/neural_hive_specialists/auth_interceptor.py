"""
Interceptor gRPC para autenticação JWT.
"""
import grpc
import jwt
import structlog
import time
from typing import Callable, Any, Optional
from datetime import datetime, timezone

from .config import SpecialistConfig
from .metrics import SpecialistMetrics

logger = structlog.get_logger()


class AuthInterceptor(grpc.ServerInterceptor):
    """Interceptor para validação de JWT em requisições gRPC."""

    def __init__(self, config: SpecialistConfig, metrics: Optional[SpecialistMetrics] = None):
        self.config = config
        self.metrics = metrics
        self.jwt_secret = config.jwt_secret_key
        self.jwt_algorithm = config.jwt_algorithm
        self.jwt_issuer = config.jwt_issuer
        self.jwt_audience = config.jwt_audience
        self.public_endpoints = set(config.jwt_public_endpoints)

        logger.info(
            "AuthInterceptor initialized",
            algorithm=self.jwt_algorithm,
            issuer=self.jwt_issuer,
            audience=self.jwt_audience,
            public_endpoints=list(self.public_endpoints)
        )

    def intercept_service(self, continuation: Callable, handler_call_details: grpc.HandlerCallDetails) -> Any:
        """Intercepta chamadas gRPC e valida JWT."""

        # Extrair path completo e nome do método
        # Ex: /neural_hive.specialist.SpecialistService/EvaluatePlan ou /grpc.health.v1.Health/Check
        full_method = handler_call_details.method
        method_name = full_method.split('/')[-1]

        # Verificar se é endpoint público (comparar path completo ou nome do método)
        if full_method in self.public_endpoints or method_name in self.public_endpoints:
            logger.debug(
                "Public endpoint accessed, skipping authentication",
                method=full_method
            )
            # Registrar bypass na métrica unificada
            if self.metrics:
                self.metrics.increment_auth_request(full_method, 'bypassed')
            return continuation(handler_call_details)

        # Verificar se autenticação está habilitada
        if not self.config.enable_jwt_auth:
            logger.warning(
                "JWT authentication disabled, allowing request",
                method=full_method
            )
            return continuation(handler_call_details)

        # Extrair token do metadata
        metadata = dict(handler_call_details.invocation_metadata)
        auth_header = metadata.get('authorization', '')

        if not auth_header:
            logger.warning(
                "Missing authorization header",
                method=full_method
            )
            if self.metrics:
                self.metrics.increment_auth_request(full_method, 'failed')
                self.metrics.increment_auth_failure('missing_token')

            return self._create_abort_handler(
                continuation(handler_call_details),
                grpc.StatusCode.UNAUTHENTICATED,
                'Missing authorization header'
            )

        # Extrair token (formato: "Bearer <token>")
        token = self._extract_token(auth_header)
        if not token:
            logger.warning(
                "Invalid authorization header format",
                method=full_method,
                auth_header=auth_header[:20] + '...'  # Log apenas início
            )
            if self.metrics:
                self.metrics.increment_auth_request(full_method, 'failed')
                self.metrics.increment_auth_failure('invalid_format')

            return self._create_abort_handler(
                continuation(handler_call_details),
                grpc.StatusCode.UNAUTHENTICATED,
                'Invalid authorization header format. Expected: Bearer <token>'
            )

        # Validar token
        try:
            # Medir duração da validação
            validation_start = time.time()
            payload = self._validate_token(token)
            validation_duration = time.time() - validation_start

            # Observar métrica de duração
            if self.metrics:
                self.metrics.observe_auth_validation_duration(validation_duration)

            # Verificar permissões
            if not self._check_permissions(payload, full_method):
                logger.warning(
                    "Insufficient permissions",
                    method=full_method,
                    subject=payload.get('sub'),
                    service_type=payload.get('service_type')
                )
                if self.metrics:
                    self.metrics.increment_auth_request(full_method, 'failed')
                    self.metrics.increment_auth_failure('insufficient_permissions')

                return self._create_abort_handler(
                    continuation(handler_call_details),
                    grpc.StatusCode.PERMISSION_DENIED,
                    f'Insufficient permissions for method {full_method}'
                )

            # Autenticação bem-sucedida
            logger.info(
                "Authentication successful",
                method=full_method,
                subject=payload.get('sub'),
                service_type=payload.get('service_type')
            )
            if self.metrics:
                self.metrics.increment_auth_request(full_method, 'success')
                self.metrics.increment_auth_success(payload.get('service_type', 'unknown'))

            # Adicionar payload ao metadata (via continuation modificado)
            # Nota: No gRPC síncrono, não podemos modificar invocation_metadata diretamente
            # mas o payload foi validado e pode ser usado nos logs/métricas

            return continuation(handler_call_details)

        except jwt.ExpiredSignatureError:
            # Observar duração mesmo em caso de erro
            validation_duration = time.time() - validation_start
            if self.metrics:
                self.metrics.observe_auth_validation_duration(validation_duration)

            logger.warning(
                "Expired JWT token",
                method=full_method
            )
            if self.metrics:
                self.metrics.increment_auth_request(full_method, 'failed')
                self.metrics.increment_auth_failure('expired_token')

            return self._create_abort_handler(
                continuation(handler_call_details),
                grpc.StatusCode.UNAUTHENTICATED,
                'Token has expired'
            )

        except jwt.InvalidTokenError as e:
            # Observar duração mesmo em caso de erro
            validation_duration = time.time() - validation_start
            if self.metrics:
                self.metrics.observe_auth_validation_duration(validation_duration)

            logger.warning(
                "Invalid JWT token",
                method=full_method,
                error=str(e)
            )
            if self.metrics:
                self.metrics.increment_auth_request(full_method, 'failed')
                self.metrics.increment_auth_failure('invalid_token')

            return self._create_abort_handler(
                continuation(handler_call_details),
                grpc.StatusCode.UNAUTHENTICATED,
                f'Invalid token: {str(e)}'
            )

    def _create_abort_handler(self, handler: Any, code: grpc.StatusCode, details: str) -> Any:
        """
        Cria handler de abort apropriado baseado no tipo de RPC.

        Args:
            handler: Handler original retornado por continuation
            code: Código de status gRPC
            details: Mensagem de erro

        Returns:
            Handler apropriado para o tipo de RPC
        """
        # Funções de abort para unary (request único)
        def abort_unary(request, context):
            context.abort(code, details)

        # Funções de abort para streaming (response stream)
        def abort_streaming(request, context):
            context.abort(code, details)
            # Em streaming, yield nunca é alcançado após abort
            yield  # pragma: no cover

        # Detectar tipo de handler e retornar abort apropriado
        if handler and hasattr(handler, 'unary_unary') and handler.unary_unary:
            return grpc.unary_unary_rpc_method_handler(abort_unary)
        elif handler and hasattr(handler, 'unary_stream') and handler.unary_stream:
            return grpc.unary_stream_rpc_method_handler(abort_streaming)
        elif handler and hasattr(handler, 'stream_unary') and handler.stream_unary:
            return grpc.stream_unary_rpc_method_handler(abort_unary)
        elif handler and hasattr(handler, 'stream_stream') and handler.stream_stream:
            return grpc.stream_stream_rpc_method_handler(abort_streaming)
        else:
            # Fallback para unary_unary se tipo não detectado
            logger.warning(
                "Unable to detect handler type, defaulting to unary_unary",
                handler_type=type(handler).__name__
            )
            return grpc.unary_unary_rpc_method_handler(abort_unary)

    def _extract_token(self, auth_header: str) -> Optional[str]:
        """Extrai token do header Authorization."""
        parts = auth_header.split(' ')
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return None
        return parts[1]

    def _validate_token(self, token: str) -> dict:
        """Valida token JWT e retorna payload."""
        payload = jwt.decode(
            token,
            self.jwt_secret,
            algorithms=[self.jwt_algorithm],
            issuer=self.jwt_issuer,
            audience=self.jwt_audience,
            options={
                'verify_signature': True,
                'verify_exp': True,
                'verify_iat': True,
                'require': ['sub', 'exp', 'iat']
            }
        )
        return payload

    def _check_permissions(self, payload: dict, full_method: str) -> bool:
        """
        Verifica se o caller tem permissão para chamar o método.

        Args:
            payload: Payload decodificado do JWT
            full_method: Path completo do método (ex: /neural_hive.specialist.SpecialistService/EvaluatePlan)
        """

        # Verificar se service_type está presente
        service_type = payload.get('service_type')
        if not service_type:
            logger.warning(
                "Missing service_type claim in JWT",
                subject=payload.get('sub')
            )
            return False

        # Extrair nome do método do path completo
        method_name = full_method.split('/')[-1]

        # Regras de permissão por método
        # Por enquanto, qualquer serviço autenticado pode chamar qualquer método
        # No futuro, pode-se adicionar lógica mais granular:
        # - Apenas consensus-engine pode chamar EvaluatePlan
        # - Apenas admin services podem chamar GetCapabilities

        allowed_services = {
            'EvaluatePlan': ['consensus-engine', 'admin'],
            'GetCapabilities': ['consensus-engine', 'admin', 'monitoring']
        }

        allowed = allowed_services.get(method_name, [])
        if allowed and service_type not in allowed:
            return False

        return True
