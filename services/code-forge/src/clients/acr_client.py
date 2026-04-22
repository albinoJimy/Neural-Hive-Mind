"""
Cliente para integração com Azure Container Registry (ACR).

Suporta:
- Autenticação via Managed Identity (Pod Identity / Workload Identity)
- Fallback para Service Principal (client_id/secret)
- Cache de token com TTL
- Detecção automática de ambiente AKS
"""

import logging
from datetime import UTC, datetime

UTC = UTC  # type: ignore, timedelta

logger = logging.getLogger(__name__)

# TTL padrão para cache de token ACR (2 horas)
ACR_TOKEN_DEFAULT_TTL = 2 * 3600

# Azure IMDS endpoint para obter token de Managed Identity
AZURE_IMDS_ENDPOINT = "http://169.254.169.254/metadata/identity/oauth2/token"


class ACRToken:
    """Representa um token ACR cacheado."""

    def __init__(
        self,
        access_token: str,
        token_type: str,
        registry: str,
        expires_at: datetime,
        obtained_at: datetime,
    ):
        self.access_token = access_token
        self.token_type = token_type
        self.registry = registry
        self.expires_at = expires_at
        self.obtained_at = obtained_at

    def is_expired(self) -> bool:
        """Verifica se o token está expirado."""
        return datetime.now(UTC) >= self.expires_at

    def should_refresh(self, ttl_seconds: int) -> bool:
        """Verifica se o token deve ser renovado baseado no TTL."""
        age = (datetime.now(UTC) - self.obtained_at).total_seconds()
        return age >= ttl_seconds

    def get_credentials(self) -> str:
        """
        Retorna credencial no formato docker login.

        Returns:
            String no formato "<token>"
        """
        return self.access_token


class ACRClient:
    """
    Cliente para autenticação com Azure Container Registry.

    Suporta múltiplos métodos de autenticação:
    1. Managed Identity (recomendado para AKS com Pod Identity)
    2. Service Principal (client_id/secret) - fallback
    3. Cache de token com TTL configurável
    """

    def __init__(
        self,
        registry: str,
        use_managed_identity: bool = True,
        client_id: str | None = None,
        client_secret: str | None = None,
        tenant_id: str | None = None,
        token_ttl: int = ACR_TOKEN_DEFAULT_TTL,
    ):
        """
        Inicializa o ACRClient.

        Args:
            registry: Registry ACR (ex: myregistry.azurecr.io)
            use_managed_identity: Se True, tenta usar Managed Identity
            client_id: Azure AD Client ID (para Service Principal)
            client_secret: Azure AD Client Secret (para Service Principal)
            tenant_id: Azure AD Tenant ID (para Service Principal)
            token_ttl: TTL do cache em segundos (default: 2 horas)
        """
        self.registry = registry
        self.use_managed_identity = use_managed_identity
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.token_ttl = token_ttl

        # Cache do token
        self._cached_token: ACRToken | None = None

        # Extrair nome do registry (sem .azurecr.io)
        self.registry_name = registry.replace(".azurecr.io", "")

    def _get_managed_identity_token(self) -> str | None:
        """
        Obtém token via Azure Managed Identity (IMDS).

        Returns:
            Token de acesso ou None se não disponível
        """
        try:
            import os

            # Verificar se estamos em AKS
            if "KUBERNETES_SERVICE_HOST" in os.environ or "KUBERNETES_PORT" in os.environ:
                # Tentar obter token via Azure IMDS
                import aiohttp

                # Parâmetros para IMDS
                params = {
                    "api-version": "2018-02-01",
                    "resource": "https://management.azure.com/",
                }

                # Se client_id fornecido, usar User Assigned Managed Identity
                if self.client_id:
                    params["client_id"] = self.client_id

                headers = {
                    "Metadata": "true",
                }

                # Fazer requisição para IMDS
                # Usar timeout curto (1 segundo) como requerido pelo IMDS
                async def fetch_token():
                    async with (
                        aiohttp.ClientSession() as session,
                        session.get(
                            AZURE_IMDS_ENDPOINT,
                            params=params,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=1),
                        ) as response,
                    ):
                        if response.status == 200:
                            data = await response.json()
                            return data.get("access_token")
                        return None

                # Executar função async
                import asyncio

                try:
                    token = asyncio.run(fetch_token())
                    if token:
                        logger.info("acr_managed_identity_token_obtained")
                        return token
                except TimeoutError:
                    logger.warning("acr_imds_timeout")
                except Exception as e:
                    logger.warning(f"acr_imds_failed: {e}")

        except ImportError:
            logger.warning("aiohttp_not_installed")
        except Exception as e:
            logger.warning(f"acr_managed_identity_failed: {e}")

        return None

    def _get_service_principal_token(self) -> str | None:
        """
        Obtém token via Service Principal.

        Returns:
            Token de acesso ou None se falhar
        """
        if not self.client_id or not self.client_secret or not self.tenant_id:
            logger.warning("acr_service_principal_incomplete_credentials")
            return None

        try:
            import requests

            # Azure AD token endpoint
            token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://management.azure.com/.default",
            }

            response = requests.post(token_url, data=data, timeout=10)

            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get("access_token")
                if access_token:
                    logger.info("acr_service_principal_token_obtained")
                    return access_token
            else:
                logger.error(f"acr_service_principal_failed: {response.status_code}")

        except ImportError:
            logger.warning("requests_not_installed")
        except Exception as e:
            logger.error(f"acr_service_principal_error: {e}")

        return None

    def get_acr_token(self) -> ACRToken:
        """
        Obtém token de autenticação ACR.

        Tenta obter do cache primeiro. Se expirado, faz nova requisição.

        Returns:
            ACRToken com credenciais cacheadas

        Raises:
            Exception: Se falhar ao obter token
        """
        # Verificar cache
        if self._cached_token and not self._cached_token.should_refresh(self.token_ttl):
            logger.debug("acr_token_cache_hit")
            return self._cached_token

        # Obter novo token
        logger.info("acr_fetching_new_token")

        # Tentar Managed Identity primeiro
        access_token = None

        if self.use_managed_identity:
            access_token = self._get_managed_identity_token()

        # Fallback para Service Principal
        if not access_token:
            access_token = self._get_service_principal_token()

        if not access_token:
            raise Exception(
                "Nenhum método de autenticação ACR disponível. "
                "Configure Managed Identity ou Service Principal credentials."
            )

        # Calcular expiração (tokens ACR expire, mas vamos usar um TTL conservador)
        # Tokens do Azure AD typically expiram em 1 hora
        expires_at = datetime.now(UTC) + timedelta(minutes=50)  # Margem de segurança
        obtained_at = datetime.now(UTC)

        token = ACRToken(
            access_token=access_token,
            token_type="Bearer",
            registry=self.registry,
            expires_at=expires_at,
            obtained_at=obtained_at,
        )

        # Atualizar cache
        self._cached_token = token

        logger.info(
            f"acr_token_obtained: registry={self.registry}, expires_at={expires_at.isoformat()}"
        )

        return token

    def get_acr_credentials(self) -> tuple[str, str]:
        """
        Obtém credenciais ACR formatadas para uso com Docker/Kaniko.

        Returns:
            Tuple (username, password) onde username é um token e password é vazio
            (ACR usa token OAuth como username)
        """
        token = self.get_acr_token()
        # ACR usa o token access_token como username, sem password
        return token.access_token, ""

    def is_acr_registry(self, image_uri: str) -> bool:
        """
        Verifica se uma URI aponta para ACR.

        Args:
            image_uri: URI da imagem

        Returns:
            True se for ACR, False caso contrário
        """
        return ".azurecr.io/" in image_uri or image_uri.endswith(".azurecr.io")

    def get_registry_endpoint(self, registry_name: str | None = None) -> str:
        """
        Constrói endpoint do registry ACR.

        Args:
            registry_name: Nome do registry (sem .azurecr.io)

        Returns:
            Endpoint do registry (ex: myregistry.azurecr.io)
        """
        name = registry_name or self.registry_name
        return f"{name}.azurecr.io"

    def refresh_if_needed(self) -> bool:
        """
        Renova token se necessário (baseado no TTL).

        Returns:
            True se token foi renovado, False se não era necessário
        """
        if self._cached_token and self._cached_token.should_refresh(self.token_ttl):
            self.get_acr_token()
            return True
        return False

    def invalidate_cache(self) -> None:
        """Invalida o cache do token."""
        self._cached_token = None
        logger.info("acr_token_cache_invalidated")


def get_acr_credentials(
    registry_uri: str,
    client_id: str | None = None,
    client_secret: str | None = None,
    tenant_id: str | None = None,
) -> tuple[str, str]:
    """
    Função de conveniência para obter credenciais ACR.

    Args:
        registry_uri: URI do registry ACR
        client_id: Azure AD Client ID (opcional)
        client_secret: Azure AD Client Secret (opcional)
        tenant_id: Azure AD Tenant ID (opcional)

    Returns:
        Tuple (username, password)
    """
    client = ACRClient(
        registry=registry_uri, client_id=client_id, client_secret=client_secret, tenant_id=tenant_id
    )

    return client.get_acr_credentials()


def detect_acr_registry(image_uri: str) -> bool:
    """
    Detecta se uma URI aponta para ACR.

    Args:
        image_uri: URI da imagem

    Returns:
        True se for ACR, False caso contrário
    """
    return ".azurecr.io/" in image_uri or image_uri.endswith(".azurecr.io")


def extract_acr_registry_name(image_uri: str) -> str | None:
    """
    Extrai o nome do registry de uma URI ACR.

    Args:
        image_uri: URI da imagem ACR

    Returns:
        Nome do registry (sem .azurecr.io) ou None
    """
    if not detect_acr_registry(image_uri):
        return None

    # myregistry.azurecr.io/myimage:tag -> myregistry
    if ".azurecr.io/" in image_uri:
        parts = image_uri.split(".azurecr.io/")
        if len(parts) >= 1:
            return parts[0]

    return None
