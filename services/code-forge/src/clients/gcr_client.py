"""
Cliente para integração com Google Container Registry (GCR).

Suporta:
- Autenticação via OAuth2 com Service Account credentials
- Workload Identity Federation para GKE
- Cache de token com TTL
- Detecção automática de ambiente GKE
"""

import json
import logging
from datetime import datetime, timezone, timedelta

UTC = UTC  # type: ignore

logger = logging.getLogger(__name__)

# TTL padrão para cache de token GCR (1 hora)
GCR_TOKEN_DEFAULT_TTL = 3600


class GCRToken:
    """Representa um token GCR cacheado."""

    def __init__(
        self, access_token: str, token_type: str, expires_at: datetime, obtained_at: datetime
    ):
        self.access_token = access_token
        self.token_type = token_type
        self.expires_at = expires_at
        self.obtained_at = obtained_at

    def is_expired(self) -> bool:
        """Verifica se o token está expirado."""
        return datetime.now(timezone.utc) >= self.expires_at

    def should_refresh(self, ttl_seconds: int) -> bool:
        """Verifica se o token deve ser renovado baseado no TTL."""
        age = (datetime.now(timezone.utc) - self.obtained_at).total_seconds()
        return age >= ttl_seconds

    def get_credentials(self) -> str:
        """
        Retorna credencial no formato docker login.

        Returns:
            String no formato "oauth2accesstoken://<token>"
        """
        return f"oauth2accesstoken://{self.access_token}"


class GCRClient:
    """
    Cliente para autenticação com Google Container Registry.

    Suporta múltiplos métodos de autenticação:
    1. Workload Identity Federation (recomendado para GKE)
    2. Service Account key (JSON key file)
    3. Cache de token com TTL configurável
    """

    def __init__(
        self,
        registry: str = "gcr.io",
        use_workload_identity: bool = True,
        service_account_key_path: str | None = None,
        service_account_email: str | None = None,
        token_ttl: int = GCR_TOKEN_DEFAULT_TTL,
    ):
        """
        Inicializa o GCRClient.

        Args:
            registry: Registry GCR (default: gcr.io)
            use_workload_identity: Se True, tenta usar Workload Identity Federation
            service_account_key_path: Caminho para JSON key file
            service_account_email: Email da service account (para logging)
            token_ttl: TTL do cache em segundos (default: 1 hora)
        """
        self.registry = registry
        self.use_workload_identity = use_workload_identity
        self.service_account_key_path = service_account_key_path
        self.service_account_email = service_account_email
        self.token_ttl = token_ttl

        # Cache do token
        self._cached_token: GCRToken | None = None

    def _get_workload_identity_token(self) -> str | None:
        """
        Obtém token via Workload Identity Federation.

        Returns:
            Token de acesso ou None se não disponível
        """
        try:
            # Em GKE com Workload Identity Federation, o token está disponível
            # via metadata do pod ou variável de ambiente
            import os

            # Verificar se estamos em GKE
            if "KUBERNES_SERVICE_HOST" in os.environ or "KUBERNES_PORT" in os.environ:
                # Tentar ler token de metadata do pod
                # GKE injeta o token em /var/run/secrets/google.com...
                token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"

                if os.path.exists(token_path):
                    with open(token_path) as f:
                        token = f.read().strip()
                    logger.info("gcr_wif_token_obtained")
                    return token

            # Verificar se há token via variável de ambiente
            # (para desenvolvimento local)
            env_token = os.environ.get("GCR_TOKEN")
            if env_token:
                logger.info("gcr_env_token_found")
                return env_token

        except Exception as e:
            logger.warning(f"gcr_wif_token_failed: {e}")

        return None

    def _get_service_account_token(self) -> str | None:
        """
        Obtém token via Service Account key file.

        Returns:
            Token de acesso ou None se falhar
        """
        if not self.service_account_key_path:
            return None

        try:
            with open(self.service_account_key_path) as f:
                key_data = json.load(f)

            # Extrair access_token
            access_token = key_data.get("access_token")
            if not access_token:
                logger.error("gcr_key_missing_access_token")
                return None

            logger.info(
                f"gcr_service_account_token_obtained: {self.service_account_email or 'N/A'}"
            )
            return access_token

        except FileNotFoundError:
            logger.warning(f"gcr_key_file_not_found: {self.service_account_key_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"gcr_key_file_invalid_json: {e}")
            return None
        except Exception as e:
            logger.error(f"gcr_key_file_error: {e}")
            return None

    def get_gcr_token(self, image_name: str | None = None) -> GCRToken:
        """
        Obtém token de autenticação GCR.

        Tenta obter do cache primeiro. Se expirado, faz nova requisição.

        Args:
            image_name: Nome completo da imagem GCR (ex: gcr.io/project/image:tag)

        Returns:
            GCRToken com credenciais cacheadas

        Raises:
            Exception: Se falhar ao obter token
        """
        # Verificar cache
        if self._cached_token and not self._cached_token.should_refresh(self.token_ttl):
            logger.debug("gcr_token_cache_hit")
            return self._cached_token

        # Obter novo token
        logger.info("gcr_fetching_new_token")

        # Tentar Workload Identity Federation primeiro
        access_token = None

        if self.use_workload_identity:
            access_token = self._get_workload_identity_token()

        # Fallback para Service Account key
        if not access_token and self.service_account_key_path:
            access_token = self._get_service_account_token()

        if not access_token:
            raise Exception(
                "Nenhum método de autenticação GCR disponível. "
                "Configure Workload Identity Federation ou Service Account key."
            )

        # Calcular expiração (tokens GCR expire em 1 hora por padrão)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        obtained_at = datetime.now(timezone.utc)

        token = GCRToken(
            access_token=access_token,
            token_type="oauth2_access_token",
            expires_at=expires_at,
            obtained_at=obtained_at,
        )

        # Atualizar cache
        self._cached_token = token

        logger.info(f"gcr_token_obtained: expires_at={expires_at.isoformat()}")

        return token

    def get_gcr_credentials(self, image_name: str | None = None) -> str:
        """
        Obtém credenciais GCR formatadas para uso com Docker/Kaniko.

        Args:
            image_name: Nome completo da imagem GCR (opcional)

        Returns:
            String no formato "oauth2accesstoken://<token>"
        """
        token = self.get_gcr_token(image_name)
        return token.get_credentials()

    def is_gcr_registry(self, image_uri: str) -> bool:
        """
        Verifica se uma URI aponta para GCR.

        Args:
            image_uri: URI da imagem

        Returns:
            True se for GCR, False caso contrário
        """
        return (
            image_uri.startswith("gcr.io/")
            or image_uri.startswith("us.")
            or image_uri.startswith("eu.")  # US regions (ex: us.gcr.io)
            or image_uri.startswith("asia.")  # EU regions (ex: eu.gcr.io)
            or image_uri.startswith("st.")  # Asia regions  # Stealth registry
        )

    def get_registry_endpoint(self, region: str = "us") -> str:
        """
        Constrói endpoint do registry GCR para região específica.

        Args:
            region: Região GCR (us, eu, asia, etc.)

        Returns:
            Endpoint do registry (ex: gcr.io, us.gcr.io, etc.)
        """
        if region == "us":
            return "gcr.io"
        return f"{region}.gcr.io"

    def refresh_if_needed(self, image_name: str | None = None) -> bool:
        """
        Renova token se necessário (baseado no TTL).

        Args:
            image_name: Nome da imagem GCR (opcional)

        Returns:
            True se token foi renovado, False se não era necessário
        """
        if self._cached_token and self._cached_token.should_refresh(self.token_ttl):
            self.get_gcr_token(image_name)
            return True
        return False

    def invalidate_cache(self) -> None:
        """Invalida o cache do token."""
        self._cached_token = None
        logger.info("gcr_token_cache_invalidated")

    def get_full_image_uri(self, project_id: str, image_name: str, tag: str = "latest") -> str:
        """
        Constrói URI completa da imagem GCR.

        Args:
            project_id: ID do projeto GCR
            image_name: Nome da imagem
            tag: Tag da imagem

        Returns:
            URI completa (ex: gcr.io/project-id/image:tag)
        """
        return f"{self.registry}/{project_id}/{image_name}:{tag}"


def get_gcr_credentials(image_uri: str, service_account_key_path: str | None = None) -> str:
    """
    Função de conveniência para obter credenciais GCR.

    Args:
        image_uri: URI da imagem GCR
        service_account_key_path: Caminho para key file (opcional)

    Returns:
        String no formato "oauth2accesstoken://<token>"
    """
    client = GCRClient(service_account_key_path=service_account_key_path)

    return client.get_gcr_credentials(image_uri)


def detect_gcr_registry(image_uri: str) -> bool:
    """
    Detecta se uma URI aponta para GCR.

    Args:
        image_uri: URI da imagem

    Returns:
        True se for GCR, False caso contrário
    """
    client = GCRClient()
    return client.is_gcr_registry(image_uri)


def extract_gcr_project(image_uri: str) -> str | None:
    """
    Extrai project ID de uma URI GCR.

    Args:
        image_uri: URI da imagem GCR

    Returns:
        Project ID ou None
    """
    # gcr.io/project-id/image:tag
    if image_uri.startswith("gcr.io/"):
        parts = image_uri[len("gcr.io/") :].split("/")
        if len(parts) >= 2:
            return parts[0]

    # us.gcr.io/project-id/image:tag
    if ".gcr.io/" in image_uri:
        parts = image_uri.split(".gcr.io/")
        if len(parts) >= 2:
            return parts[1].split("/")[0]

    return None
