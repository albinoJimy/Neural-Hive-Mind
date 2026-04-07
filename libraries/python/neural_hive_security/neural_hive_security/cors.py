"""
CORS configuration utilities for Neural Hive Mind services.

Fornece configuração centralizada de CORS por ambiente e tipo de serviço.
Remove wildcards inseguros de produção enquanto mantém desenvolvedores produtivos.
"""

import warnings
from typing import List


class CORSConfig:
    """
    Configuração centralizada de CORS por ambiente.

    Serviços PÚBLICOS (com frontend web): Usam origens específicas por ambiente
    Serviços INTERNOS (gRPC/Kafka): Desabilitam CORS (lista vazia)
    """

    # Ambiente de desenvolvimento - localhost e portas comuns
    DEV_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8080",
    ]

    # Ambiente de staging - domínios de staging
    STAGING_ORIGINS: List[str] = [
        "https://staging.neural-hive.local",
        "https://staging-app.neural-hive.local",
        "https://gateway-staging.neural-hive.local",
        "https://approval-staging.neural-hive.local",
        "https://grafana.neural-hive.local",
    ]

    # Ambiente de produção - domínios reais
    PROD_ORIGINS: List[str] = [
        "https://neural-hive.com",
        "https://app.neural-hive.com",
        "https://gateway.neural-hive.com",
        "https://approval.neural-hive.com",
        "https://admin.neural-hive.com",
        "https://grafana.neural-hive.com",
    ]

    # Serviços internos não usam CORS
    INTERNAL_SERVICES: List[str] = []

    @classmethod
    def get_origins_for_environment(
        cls, environment: str, is_public_api: bool = False
    ) -> List[str]:
        """
        Retorna origens CORS permitidas para o ambiente.

        Args:
            environment: Ambiente (dev, staging, prod, production)
            is_public_api: Se True, retorna origens do ambiente.
                           Se False, retorna lista vazia (serviço interno).

        Returns:
            Lista de origens permitidas.

        Examples:
            >>> CORSConfig.get_origins_for_environment("dev", is_public_api=True)
            ['http://localhost:3000', 'http://localhost:8000', ...]

            >>> CORSConfig.get_origins_for_environment("prod", is_public_api=False)
            []
        """
        # Serviços internos não usam CORS
        if not is_public_api:
            return cls.INTERNAL_SERVICES

        # Normaliza: remove hífens e underscores do final e do início
        # Mantém hífens no meio (ex: "prod-env" vira "prod-env", não "prodev")
        env = environment.lower().strip("-_")

        # Match exato ou prefixo
        if env in ("dev", "development") or env.startswith("dev"):
            return cls.DEV_ORIGINS
        elif env in ("staging", "stage") or env.startswith("staging") or env.startswith("stage"):
            return cls.STAGING_ORIGINS
        elif (
            env in ("prod", "production") or env.startswith("prod") or env.startswith("production")
        ):
            return cls.PROD_ORIGINS
        else:
            # Default para dev em caso de ambiente desconhecido
            return cls.DEV_ORIGINS

    @classmethod
    def validate_no_wildcard(cls, origins: List[str], environment: str) -> bool:
        """
        Valida que não existe wildcard (*) nas origens em produção.

        Raises:
            ValueError: Se encontrar wildcard em produção.

        Args:
            origins: Lista de origens a validar
            environment: Ambiente atual

        Returns:
            True se válido

        Examples:
            >>> CORSConfig.validate_no_wildcard(["*"], "prod")
            ValueError: Wildcard CORS not allowed in production
        """
        env = environment.lower()

        # Permite wildcard em dev/staging para facilitar desenvolvimento
        if env in ("dev", "development", "staging", "stage"):
            return True

        # Produção não pode ter wildcard
        if "*" in origins:
            raise ValueError(
                "Wildcard CORS ('*') is not allowed in production. "
                f"Environment: {environment}, Origins: {origins}"
            )

        return True

    @classmethod
    def warn_if_wildcard_in_production(cls, origins: List[str], environment: str) -> None:
        """
        Emite aviso se detectar wildcard CORS em produção.

        Não lança exceção, apenas avisa via logging/warnings.

        Args:
            origins: Lista de origens a validar
            environment: Ambiente atual

        Examples:
            >>> CORSConfig.warn_if_wildcard_in_production(["*"], "prod")
            UserWarning: Potential security issue: Wildcard CORS detected in production environment
        """
        env = environment.lower()

        # Apenas verifica em produção
        if env not in ("prod", "production") or not env.startswith("prod"):
            return

        if "*" in origins:
            warnings.warn(
                f"Potential security issue: Wildcard CORS ('*') detected in production environment. "
                f"Environment: {environment}. "
                f"This allows any origin to access your API. Consider using specific origins.",
                UserWarning,
                stacklevel=2,
            )

    @classmethod
    def get_cors_middleware_config(cls, environment: str, is_public_api: bool = False) -> dict:
        """
        Retorna configuração completa para CORSMiddleware do FastAPI.

        Args:
            environment: Ambiente atual
            is_public_api: Se é API pública

        Returns:
            Dict com configurações para CORSMiddleware

        Examples:
            >>> config = CORSConfig.get_cors_middleware_config("prod", is_public_api=True)
            >>> app.add_middleware(CORSMiddleware, **config)
        """
        origins = cls.get_origins_for_environment(environment, is_public_api)

        # Valida produção
        cls.validate_no_wildcard(origins, environment)

        return {
            "allow_origins": origins,
            "allow_credentials": True if is_public_api else False,
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "allow_headers": ["*"],
            "expose_headers": ["X-Request-ID", "X-Correlation-ID"],
        }


# Função auxiliar para compatibilidade
def get_cors_origins(environment: str, is_public_api: bool = False) -> List[str]:
    """
    Alias simplificado para CORSConfig.get_origins_for_environment().

    Args:
        environment: Ambiente (dev, staging, prod)
        is_public_api: Se é API pública

    Returns:
        Lista de origens permitidas
    """
    return CORSConfig.get_origins_for_environment(environment, is_public_api)
