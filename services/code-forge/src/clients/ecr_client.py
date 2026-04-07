"""
Cliente para integração com Amazon ECR (Elastic Container Registry).

Suporta:
- Obtenção de token de autenticação via IAM Role (IRSA)
- Fallback para credenciais estáticas (access key/secret)
- Cache de token com TTL
- Detecção automática de ambiente EKS
"""

import base64
import logging
from datetime import datetime, timezone, timedelta

UTC = timezone.utc  # type: ignore

logger = logging.getLogger(__name__)

# TTL padrão para cache de token ECR (12 horas)
ECR_TOKEN_DEFAULT_TTL = 12 * 3600

# Timestamp de quando o token foi obtido
# e quando expira


class ECRToken:
    """Representa um token ECR cacheado."""

    def __init__(
        self,
        username: str,
        password: str,
        endpoint: str,
        expires_at: datetime,
        obtained_at: datetime,
    ):
        self.username = username
        self.password = password
        self.endpoint = endpoint
        self.expires_at = expires_at
        self.obtained_at = obtained_at

    def is_expired(self) -> bool:
        """Verifica se o token está expirado."""
        return datetime.now(UTC) >= self.expires_at

    def should_refresh(self, ttl_seconds: int) -> bool:
        """Verifica se o token deve ser renovado baseado no TTL."""
        age = (datetime.now(UTC) - self.obtained_at).total_seconds()
        return age >= ttl_seconds

    def get_credentials(self) -> tuple[str, str]:
        """Retorna username e password."""
        return self.username, self.password


class ECRClient:
    """
    Cliente para autenticação com Amazon ECR.

    Suporta múltiplos métodos de autenticação:
    1. IRSA (IAM Roles for Service Accounts) - recomendado para EKS
    2. Credenciais estáticas (access key/secret) - fallback
    3. Cache de token com TTL configurável
    """

    def __init__(
        self,
        region: str = "us-east-1",
        use_irsa: bool = True,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        token_ttl: int = ECR_TOKEN_DEFAULT_TTL,
    ):
        """
        Inicializa o ECRClient.

        Args:
            region: Região AWS (default: us-east-1)
            use_irsa: Se True, tenta usar IRSA primeiro
            access_key_id: AWS Access Key ID (fallback)
            secret_access_key: AWS Secret Access Key (fallback)
            token_ttl: TTL do cache em segundos (default: 12h)
        """
        self.region = region
        self.use_irsa = use_irsa
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.token_ttl = token_ttl

        # Cache do token
        self._cached_token: ECRToken | None = None
        self._boto3_session = None

    def _get_boto3_session(self):
        """
        Obtém ou cria sessão boto3.

        Returns:
            Session do boto3 configurada
        """
        if self._boto3_session is None:
            import boto3

            if self.use_irsa:
                # Tentar usar IRSA (web identity token)
                # O boto3 detecta automaticamente IRSA em EKS
                try:
                    self._boto3_session = boto3.Session(region_name=self.region)
                    logger.info(f"ecr_using_irsa, region: {self.region}")
                except Exception as e:
                    logger.warning(f"ecr_irsa_failed: {e}")
                    # Fallback para credenciais estáticas
                    if self.access_key_id and self.secret_access_key:
                        self._boto3_session = boto3.Session(
                            region_name=self.region,
                            aws_access_key_id=self.access_key_id,
                            aws_secret_access_key=self.secret_access_key,
                        )
                        logger.info("ecr_using_static_credentials")
                    else:
                        raise
            else:
                # Usar credenciais estáticas ou default chain
                session_kwargs = {"region_name": self.region}
                if self.access_key_id and self.secret_access_key:
                    session_kwargs.update(
                        {
                            "aws_access_key_id": self.access_key_id,
                            "aws_secret_access_key": self.secret_access_key,
                        }
                    )

                self._boto3_session = boto3.Session(**session_kwargs)
                logger.info(f"ecr_session_created, region: {self.region}")

        return self._boto3_session

    def get_ecr_token(self, registry_id: str | None = None) -> ECRToken:
        """
        Obtém token de autenticação ECR.

        Tenta obter do cache primeiro. Se expirado, faz nova requisição.

        Args:
            registry_id: ID do registry ECR (opcional, para cross-account)

        Returns:
            ECRToken com credenciais cacheadas

        Raises:
            Exception: Se falhar ao obter token
        """
        # Verificar cache
        if self._cached_token and not self._cached_token.should_refresh(self.token_ttl):
            logger.debug("ecr_token_cache_hit")
            return self._cached_token

        # Obter novo token
        logger.info("ecr_fetching_new_token")

        try:
            session = self._get_boto3_session()
            client = session.client("ecr")

            get_auth_token_kwargs = {}
            if registry_id:
                get_auth_token_kwargs["registryIds"] = [registry_id]

            response = client.get_authorization_token(**get_auth_token_kwargs)

            # Extrair dados da resposta
            auth_data = response["authorizationData"][0]
            authorization_token = base64.b64decode(auth_data["authorizationToken"]).decode("utf-8")
            username, password = authorization_token.split(":", 1)

            # Endpoint do registry (sem https://)
            endpoint = auth_data["proxyEndpoint"].replace("https://", "")

            # Calcular expiração (ECR tokens expiram em 12h)
            expires_at = datetime.now(UTC)
            if "expiresAt" in auth_data:
                # AWS retorna a data de expiração
                from dateutil import parser as date_parser

                expires_at = date_parser.parse(auth_data["expiresAt"])
            else:
                # Default: 12 horas
                expires_at = datetime.now(UTC).replace(microsecond=0)
                expires_at += timedelta(hours=12)

            obtained_at = datetime.now(UTC)

            token = ECRToken(
                username=username,
                password=password,
                endpoint=endpoint,
                expires_at=expires_at,
                obtained_at=obtained_at,
            )

            # Atualizar cache
            self._cached_token = token

            logger.info(
                f"ecr_token_obtained: endpoint={endpoint}, expires_at={expires_at.isoformat()}"
            )

            return token

        except ImportError as e:
            # boto3 não instalado
            logger.error(f"boto3_not_installed: {e}")
            raise Exception("boto3 é necessário para ECR. Instale com: pip install boto3")
        except Exception as e:
            logger.error(f"ecr_token_fetch_failed: {e}")
            raise

    def get_ecr_credentials(self, registry_id: str | None = None) -> tuple[str, str, str]:
        """
        Obtém credenciais ECR formatadas para uso com Docker/Kaniko.

        Args:
            registry_id: ID do registry ECR (opcional)

        Returns:
            Tuple (username, password, endpoint)
        """
        token = self.get_ecr_token(registry_id)
        return token.username, token.password, token.endpoint

    def is_irsa_available(self) -> bool:
        """
        Verifica se IRSA (IAM Roles for Service Accounts) está disponível.

        Returns:
            True se IRSA está configurado e disponível
        """
        if not self.use_irsa:
            return False

        # Verificar presença de variáveis de ambiente IRSA
        import os

        has_web_identity = "AWS_WEB_IDENTITY_TOKEN_FILE" in os.environ
        has_role_arn = "AWS_ROLE_ARN" in os.environ

        if has_web_identity and has_role_arn:
            return True

        # Verificar se consegue assumir role via web identity
        try:
            session = self._get_boto3_session()
            sts = session.client("sts")
            sts.get_caller_identity()
            return True
        except Exception:
            return False

    def get_registry_uri(self, account_id: str | None = None, region: str | None = None) -> str:
        """
        Constrói URI do registry ECR.

        Args:
            account_id: ID da conta AWS (default: auto-detect)
            region: Região (default: usar configurada)

        Returns:
            URI do registry (ex: 123456789012.dkr.ecr.us-east-1.amazonaws.com)
        """
        region = region or self.region

        if account_id:
            return f"{account_id}.dkr.ecr.{region}.amazonaws.com"

        # Auto-detect account ID via STS
        try:
            session = self._get_boto3_session()
            sts = session.client("sts")
            response = sts.get_caller_identity()
            account_id = response["Account"]
            return f"{account_id}.dkr.ecr.{region}.amazonaws.com"
        except Exception as e:
            logger.warning(f"sts_account_detection_failed: {e}")
            raise

    def refresh_if_needed(self, registry_id: str | None = None) -> bool:
        """
        Renova token se necessário (baseado no TTL).

        Args:
            registry_id: ID do registry ECR (opcional)

        Returns:
            True se token foi renovado, False se não era necessário
        """
        if self._cached_token and self._cached_token.should_refresh(self.token_ttl):
            self.get_ecr_token(registry_id)
            return True
        return False

    def invalidate_cache(self) -> None:
        """Invalida o cache do token."""
        self._cached_token = None
        logger.info("ecr_token_cache_invalidated")


def get_ecr_credentials(
    registry_uri: str,
    region: str = "us-east-1",
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
) -> tuple[str, str]:
    """
    Função de conveniência para obter credenciais ECR.

    Args:
        registry_uri: URI do registry ECR
        region: Região AWS
        access_key_id: AWS Access Key ID (opcional)
        secret_access_key: AWS Secret Access Key (opcional)

    Returns:
        Tuple (username, password)
    """
    client = ECRClient(
        region=region, access_key_id=access_key_id, secret_access_key=secret_access_key
    )

    username, password, endpoint = client.get_ecr_credentials()
    return username, password


def detect_ecr_registry(image_uri: str) -> bool:
    """
    Detecta se uma URI de imagem aponta para ECR.

    Args:
        image_uri: URI completa da imagem

    Returns:
        True se for ECR, False caso contrário
    """
    return ".dkr.ecr." in image_uri and ".amazonaws.com" in image_uri


def extract_ecr_region(image_uri: str) -> str | None:
    """
    Extrai região de uma URI ECR.

    Args:
        image_uri: URI da imagem ECR

    Returns:
        Região (ex: us-east-1) ou None
    """
    if not detect_ecr_registry(image_uri):
        return None

    # .dkr.ecr.<region>.amazonaws.com
    parts = image_uri.split(".dkr.ecr.")
    if len(parts) < 2:
        return None

    region_part = parts[1].split(".amazonaws.com")[0]
    return region_part
