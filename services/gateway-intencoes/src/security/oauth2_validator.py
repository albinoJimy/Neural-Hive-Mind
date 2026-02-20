"""
Validador OAuth2/JWT para Neural Hive-Mind
Integra com Keycloak para validação de tokens
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

import httpx
from jose import JWTError, jwt
from jose.exceptions import JWKError
from opentelemetry import trace
from prometheus_client import Counter, Histogram, Gauge

from config.settings import get_settings

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Métricas Prometheus
token_validations_total = Counter(
    "oauth2_token_validations_total",
    "Total de validações de token",
    ["status", "client_id"],
)

token_validation_duration = Histogram(
    "oauth2_token_validation_duration_seconds",
    "Duração das validações de token",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

jwks_cache_hits = Gauge("oauth2_jwks_cache_hits_total", "Total de hits no cache JWKS")

jwks_cache_misses = Gauge(
    "oauth2_jwks_cache_misses_total", "Total de misses no cache JWKS"
)


class TokenValidationError(Exception):
    """Erro na validação de token"""

    pass


class JWKSCache:
    """Cache para JWKS (JSON Web Key Set)"""

    def __init__(self, cache_duration: int = 300):  # 5 minutos
        self.cache_duration = cache_duration
        self.jwks: Optional[Dict] = None
        self.last_fetch: Optional[datetime] = None
        self.http_client: Optional[httpx.AsyncClient] = None

    async def get_jwks(self, jwks_uri: str) -> Dict:
        """Obter JWKS com cache"""
        now = datetime.now()

        # Verificar se cache é válido
        if (
            self.jwks
            and self.last_fetch
            and (now - self.last_fetch).total_seconds() < self.cache_duration
        ):
            jwks_cache_hits.inc()
            return self.jwks

        # Buscar JWKS atualizado
        jwks_cache_misses.inc()

        if not self.http_client:
            self.http_client = httpx.AsyncClient(timeout=10.0)

        try:
            with tracer.start_as_current_span(
                "jwks_fetch", attributes={"uri": jwks_uri}
            ):
                response = await self.http_client.get(jwks_uri)
                response.raise_for_status()

                self.jwks = response.json()
                self.last_fetch = now

                logger.info(
                    f"JWKS atualizado com {len(self.jwks.get('keys', []))} chaves"
                )
                return self.jwks

        except httpx.HTTPError as e:
            logger.error(f"Erro ao buscar JWKS de {jwks_uri}: {e}")
            if self.jwks:  # Usar cache expirado em caso de erro
                logger.warning("Usando JWKS expirado devido ao erro")
                return self.jwks
            raise TokenValidationError(f"Não foi possível obter JWKS: {e}")

    async def close(self):
        """Fechar cliente HTTP"""
        if self.http_client:
            await self.http_client.aclose()


class OAuth2Validator:
    """Validador OAuth2/JWT integrado com Keycloak"""

    def __init__(self):
        self.settings = get_settings()
        self.jwks_cache = JWKSCache()
        self.http_client: Optional[httpx.AsyncClient] = None

    async def initialize(self):
        """Inicializar validador"""
        self.http_client = httpx.AsyncClient(timeout=10.0)

        # Pre-caregar JWKS
        try:
            await self.jwks_cache.get_jwks(self.settings.jwks_uri)
            logger.info("OAuth2Validator inicializado com sucesso")
        except Exception as e:
            logger.warning(f"Erro ao pre-carregar JWKS: {e}")

    async def close(self):
        """Fechar recursos"""
        await self.jwks_cache.close()
        if self.http_client:
            await self.http_client.aclose()

    async def validate_token(
        self,
        token: str,
        required_scopes: Optional[List[str]] = None,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validar token JWT completo"""
        start_time = datetime.now()

        try:
            with tracer.start_as_current_span(
                "token_validation", attributes={"client_id": client_id or "unknown"}
            ):
                # 1. Decodificar header para obter kid
                unverified_header = jwt.get_unverified_header(token)
                kid = unverified_header.get("kid")

                if not kid:
                    raise TokenValidationError("Token JWT não contém 'kid' no header")

                # 2. Obter JWKS
                jwks = await self.jwks_cache.get_jwks(self.settings.jwks_uri)

                # 3. Encontrar chave correspondente
                key = self._find_key(jwks, kid)

                # 4. Validar assinatura e claims
                # Nota: audience pode ser string ou lista no token, validamos manualmente
                # Nota: issuer validado manualmente para aceitar com/sem /auth
                payload = jwt.decode(
                    token,
                    key,
                    algorithms=["RS256"],
                    options={
                        "verify_aud": False,  # Validamos manualmente
                        "verify_iss": False,  # Validamos manualmente
                    },
                )

                # Validar issuer manualmente (aceita qualquer URL com realm correto)
                token_iss = payload.get("iss")
                realm_path_modern = f"/realms/{self.settings.keycloak_realm}"
                realm_path_legacy = f"/auth/realms/{self.settings.keycloak_realm}"

                # Aceita qualquer base URL desde que termine com o path correto do realm
                if not (
                    token_iss.endswith(realm_path_modern)
                    or token_iss.endswith(realm_path_legacy)
                ):
                    raise TokenValidationError(
                        f"Issuer inválido: {token_iss} (realm esperado: {self.settings.keycloak_realm})"
                    )

                # Validar audience manualmente (aceita string ou lista)
                token_aud = payload.get("aud")
                valid_audiences = [self.settings.keycloak_client_id, "account"]

                if isinstance(token_aud, str):
                    if token_aud not in valid_audiences:
                        raise TokenValidationError(f"Audience inválido: {token_aud}")
                elif isinstance(token_aud, list):
                    if not any(aud in valid_audiences for aud in token_aud):
                        raise TokenValidationError(
                            f"Nenhum audience válido encontrado: {token_aud}"
                        )
                else:
                    raise TokenValidationError("Token não contém audience válido")

                # 5. Validações adicionais
                await self._validate_token_claims(payload, required_scopes, client_id)

                duration = (datetime.now() - start_time).total_seconds()
                token_validation_duration.observe(duration)
                token_validations_total.labels(
                    status="success", client_id=client_id or "unknown"
                ).inc()

                return payload

        except JWTError as e:
            duration = (datetime.now() - start_time).total_seconds()
            token_validation_duration.observe(duration)
            token_validations_total.labels(
                status="jwt_error", client_id=client_id or "unknown"
            ).inc()

            logger.warning(f"Token JWT inválido: {e}")
            raise TokenValidationError(f"Token JWT inválido: {e}")

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            token_validation_duration.observe(duration)
            token_validations_total.labels(
                status="error", client_id=client_id or "unknown"
            ).inc()

            logger.error(f"Erro na validação do token: {e}")
            raise TokenValidationError(f"Erro na validação: {e}")

    def _find_key(self, jwks: Dict, kid: str) -> Dict:
        """Encontrar chave JWKS pelo kid"""
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key

        raise TokenValidationError(f"Chave JWKS não encontrada para kid: {kid}")

    async def _validate_token_claims(
        self,
        payload: Dict[str, Any],
        required_scopes: Optional[List[str]] = None,
        client_id: Optional[str] = None,
    ):
        """Validar claims específicos do token"""

        # Validar expiração
        exp = payload.get("exp")
        if not exp or datetime.fromtimestamp(exp) < datetime.now():
            raise TokenValidationError("Token expirado")

        # Validar issued at
        iat = payload.get("iat")
        if not iat or datetime.fromtimestamp(iat) > datetime.now():
            raise TokenValidationError("Token não é válido ainda")

        # Validar client_id se especificado
        if client_id:
            token_client_id = payload.get("azp") or payload.get("client_id")
            if token_client_id != client_id:
                raise TokenValidationError(
                    f"Client ID inválido: esperado {client_id}, recebido {token_client_id}"
                )

        # Validar scopes se especificados (exceto service accounts)
        # Service accounts (client_credentials) têm acesso total
        preferred_username = payload.get("preferred_username", "")
        is_service_account = preferred_username.startswith("service-account-")

        if required_scopes and not is_service_account:
            token_scopes = payload.get("scope", "").split()
            missing_scopes = set(required_scopes) - set(token_scopes)
            if missing_scopes:
                raise TokenValidationError(
                    f"Scopes insuficientes: faltando {missing_scopes}"
                )

        # Validar roles do Neural Hive-Mind (exceto para service accounts)
        # Service accounts (client_credentials) não têm roles de usuário
        is_service_account = payload.get("azp") and not payload.get(
            "sub", ""
        ).startswith("user-")
        preferred_username = payload.get("preferred_username", "")

        if not is_service_account and not preferred_username.startswith(
            "service-account-"
        ):
            realm_access = payload.get("realm_access", {})
            roles = realm_access.get("roles", [])

            if "neural-hive-user" not in roles and "neural-hive-admin" not in roles:
                raise TokenValidationError(
                    "Token não tem roles válidos do Neural Hive-Mind"
                )

    async def validate_offline(self, token: str) -> Dict[str, Any]:
        """Validação offline básica (sem verificar assinatura)"""
        try:
            # Decodificar sem verificar assinatura (apenas para desenvolvimento/fallback)
            unverified_payload = jwt.get_unverified_claims(token)

            # Validar expiração
            exp = unverified_payload.get("exp")
            if not exp or datetime.fromtimestamp(exp) < datetime.now():
                raise TokenValidationError("Token expirado")

            # Validar issuer
            iss = unverified_payload.get("iss")
            expected_issuer = f"{self.settings.keycloak_url}/auth/realms/{self.settings.keycloak_realm}"
            if iss != expected_issuer:
                raise TokenValidationError(f"Issuer inválido: {iss}")

            return unverified_payload

        except JWTError as e:
            raise TokenValidationError(f"Token malformado: {e}")

    async def introspect_token(self, token: str) -> Dict[str, Any]:
        """Introspecção de token via endpoint Keycloak"""
        if not self.http_client:
            raise TokenValidationError("Cliente HTTP não inicializado")

        introspect_url = f"{self.settings.keycloak_url}/auth/realms/{self.settings.keycloak_realm}/protocol/openid-connect/token/introspect"

        try:
            with tracer.start_as_current_span("token_introspect"):
                # Preparar dados para introspecção
                data = {"token": token, "client_id": self.settings.keycloak_client_id}

                if self.settings.keycloak_client_secret:
                    data["client_secret"] = self.settings.keycloak_client_secret

                response = await self.http_client.post(
                    introspect_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                response.raise_for_status()
                result = response.json()

                if not result.get("active", False):
                    raise TokenValidationError("Token inativo segundo introspecção")

                return result

        except httpx.HTTPError as e:
            logger.error(f"Erro na introspecção do token: {e}")
            raise TokenValidationError(f"Erro na introspecção: {e}")

    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """Obter informações do usuário via token"""
        if not self.http_client:
            raise TokenValidationError("Cliente HTTP não inicializado")

        userinfo_url = f"{self.settings.keycloak_url}/auth/realms/{self.settings.keycloak_realm}/protocol/openid-connect/userinfo"

        try:
            with tracer.start_as_current_span("userinfo_fetch"):
                response = await self.http_client.get(
                    userinfo_url, headers={"Authorization": f"Bearer {token}"}
                )

                response.raise_for_status()
                return response.json()

        except httpx.HTTPError as e:
            logger.error(f"Erro ao obter user info: {e}")
            raise TokenValidationError(f"Erro ao obter user info: {e}")

    def extract_user_context(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extrair contexto do usuário do payload JWT"""
        return {
            "user_id": payload.get("sub"),
            "username": payload.get("preferred_username"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "roles": payload.get("realm_access", {}).get("roles", []),
            "scopes": payload.get("scope", "").split(),
            "client_id": payload.get("azp") or payload.get("client_id"),
            "session_id": payload.get("session_state"),
            "is_admin": "neural-hive-admin"
            in payload.get("realm_access", {}).get("roles", []),
        }


# Validador global singleton
_oauth2_validator: Optional[OAuth2Validator] = None


async def get_oauth2_validator() -> OAuth2Validator:
    """Obter validador OAuth2 singleton"""
    global _oauth2_validator

    if _oauth2_validator is None:
        _oauth2_validator = OAuth2Validator()
        await _oauth2_validator.initialize()

    return _oauth2_validator


async def close_oauth2_validator():
    """Fechar validador OAuth2 global"""
    global _oauth2_validator

    if _oauth2_validator:
        await _oauth2_validator.close()
        _oauth2_validator = None
