"""Serviço de Gerenciamento de Thresholds Externalizados para NLU.

Autor: Neural Hive Mind
Criado: 2026-04-20 (FEAT-A-005)

Permite configurar thresholds NLU via arquivo YAML ou feature flags,
com suporte a recarga em runtime sem reiniciar o serviço.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class ThresholdConfig:
    """Configuração de threshold para um domínio ou global."""

    def __init__(
        self,
        min_threshold: float = 0.3,
        base_threshold: float = 0.5,
        strict_threshold: float = 0.75,
        adaptive_enabled: bool = True,
        min_confidence_for_auto_approve: float = 0.8,
        requires_human_review_below: float = 0.4,
    ):
        """Inicializa configuração de threshold.

        Args:
            min_threshold: Threshold mínimo absoluto
            base_threshold: Threshold base padrão
            strict_threshold: Threshold para modo estrito
            adaptive_enabled: Se threshold adaptativo está habilitado
            min_confidence_for_auto_approve: Confiança mínima para auto-aprovação
            requires_human_review_below: Abaixo deste valor requer revisão humana
        """
        self.min_threshold = min_threshold
        self.base_threshold = base_threshold
        self.strict_threshold = strict_threshold
        self.adaptive_enabled = adaptive_enabled
        self.min_confidence_for_auto_approve = min_confidence_for_auto_approve
        self.requires_human_review_below = requires_human_review_below
        self.last_modified = datetime.now(timezone.utc)  # noqa: UP017
        self.version = 1

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        return {
            "min_threshold": self.min_threshold,
            "base_threshold": self.base_threshold,
            "strict_threshold": self.strict_threshold,
            "adaptive_enabled": self.adaptive_enabled,
            "min_confidence_for_auto_approve": self.min_confidence_for_auto_approve,
            "requires_human_review_below": self.requires_human_review_below,
            "last_modified": self.last_modified.isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThresholdConfig":
        """Cria instância a partir de dicionário."""
        config = cls(
            min_threshold=data.get("min_threshold", 0.3),
            base_threshold=data.get("base_threshold", 0.5),
            strict_threshold=data.get("strict_threshold", 0.75),
            adaptive_enabled=data.get("adaptive_enabled", True),
            min_confidence_for_auto_approve=data.get("min_confidence_for_auto_approve", 0.8),
            requires_human_review_below=data.get("requires_human_review_below", 0.4),
        )
        if "last_modified" in data:
            config.last_modified = datetime.fromisoformat(data["last_modified"])
        config.version = data.get("version", 1)
        return config


class ThresholdService:
    """Serviço para gerenciar thresholds NLU externalizados."""

    def __init__(
        self,
        config_path: str | None = None,
        enable_auto_reload: bool = False,
        reload_interval_seconds: int = 300,
        cache_ttl_seconds: int = 300,
    ):
        """Inicializa serviço de thresholds.

        Args:
            config_path: Caminho para arquivo de configuração YAML
            enable_auto_reload: Habilita recarga automática
            reload_interval_seconds: Intervalo de recarga em segundos
            cache_ttl_seconds: TTL do cache em segundos (0 = sem expiração)
        """
        self.config_path = config_path
        self.enable_auto_reload = enable_auto_reload
        self.reload_interval_seconds = reload_interval_seconds
        self.cache_ttl_seconds = cache_ttl_seconds

        # Configuração global (padrão para todos os domínios)
        self.global_config: ThresholdConfig = ThresholdConfig()

        # Configurações por domínio
        self.domain_configs: dict[str, ThresholdConfig] = {}

        # Configurações por tenant
        self.tenant_configs: dict[str, dict[str, ThresholdConfig]] = {}

        # Override por feature flags
        self.feature_flags: dict[str, Any] = {}

        # Controle de cache e reload
        self._last_reload: datetime | None = None
        self._last_cache_refresh: datetime | None = None
        self._reload_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Inicializa serviço carregando configurações."""
        if self.config_path:
            await self.load_from_file(self.config_path)
        else:
            logger.info("Nenhum caminho de configuração fornecido, usando defaults")

        # Iniciar auto-reload se habilitado
        if self.enable_auto_reload and self.config_path:
            self._reload_task = asyncio.create_task(self._auto_reload_loop())
            logger.info(
                "Auto-reload iniciado: intervalo=%ss",
                self.reload_interval_seconds,
            )

        logger.info(
            "ThresholdService inicializado: "
            "global_threshold=%s, domínios_configurados=%s, tenants_configurados=%s, cache_ttl=%ss",
            self.global_config.base_threshold,
            len(self.domain_configs),
            len(self.tenant_configs),
            self.cache_ttl_seconds,
        )

    async def _check_cache_expired(self) -> bool:
        """Verifica se o cache de configurações expirou.

        Returns:
            True se o cache expirou ou não foi inicializado
        """
        if self.cache_ttl_seconds <= 0:
            return False  # Cache sem expiração

        if self._last_cache_refresh is None:
            return True  # Cache nunca foi carregado

        elapsed = (datetime.now(UTC) - self._last_cache_refresh).total_seconds()
        return elapsed > self.cache_ttl_seconds

    async def _ensure_cache_fresh(self) -> None:
        """Garante que o cache está fresco, recarregando se necessário."""
        if await self._check_cache_expired():
            async with self._lock:
                # Double-check pattern
                if await self._check_cache_expired():
                    logger.info(
                        "threshold_cache_expired",
                        cache_age_seconds=(
                            (
                                datetime.now(timezone.utc) - self._last_cache_refresh  # noqa: UP017
                            ).total_seconds()
                            if self._last_cache_refresh
                            else None
                        ),
                        ttl=self.cache_ttl_seconds,
                    )
                    await self._refresh_cache()

    async def _refresh_cache(self) -> None:
        """Recarrega configurações do arquivo e atualiza o cache."""
        if self.config_path:
            success = await self.load_from_file(self.config_path)
            if success:
                self._last_cache_refresh = datetime.now(timezone.utc)  # noqa: UP017
                logger.info(
                    "threshold_cache_refreshed",
                    domains_count=len(self.domain_configs),
                    tenants_count=len(self.tenant_configs),
                )

    async def _auto_reload_loop(self) -> None:
        """Loop de auto-reload em background."""
        try:
            while True:
                await asyncio.sleep(self.reload_interval_seconds)
                await self._refresh_cache()
        except asyncio.CancelledError:
            logger.info("threshold_auto_reload_cancelled")
        except Exception:
            logger.exception("threshold_auto_reload_error")

    async def load_from_file(self, path: str) -> bool:
        """Carrega configurações de arquivo YAML.

        Args:
            path: Caminho para arquivo YAML

        Returns:
            True se carregado com sucesso
        """
        try:
            config_file = Path(path)
            if not config_file.exists():
                logger.warning("Arquivo de configuração não encontrado: %s", path)
                return False

            with open(config_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            await self._load_config_data(data)
            self._last_reload = datetime.now(timezone.utc)  # noqa: UP017

        except Exception:
            logger.exception("Erro carregando configuração de %s", path)
            return False
        else:
            logger.info("Configuração carregada de %s", path)
            return True

    async def _load_config_data(self, data: dict[str, Any]) -> None:
        """Carrega dados de configuração.

        Args:
            data: Dicionário com dados de configuração
        """
        # Carregar configuração global
        if "global" in data:
            self.global_config = ThresholdConfig.from_dict(data["global"])

        # Carregar configurações por domínio
        if "domains" in data:
            for domain_name, domain_data in data["domains"].items():
                self.domain_configs[domain_name] = ThresholdConfig.from_dict(domain_data)

        # Carregar configurações por tenant
        if "tenants" in data:
            for tenant_id, tenant_data in data["tenants"].items():
                self.tenant_configs[tenant_id] = {}
                if "domains" in tenant_data:
                    for domain_name, domain_data in tenant_data["domains"].items():
                        self.tenant_configs[tenant_id][domain_name] = ThresholdConfig.from_dict(
                            domain_data
                        )

        # Carregar feature flags
        if "feature_flags" in data:
            self.feature_flags = data["feature_flags"]

    async def get_threshold_for(
        self,
        domain: str,
        tenant_id: str | None = None,
        use_strict: bool = False,
    ) -> float:
        """Retorna threshold configurado para domínio/tenant.

        Args:
            domain: Nome do domínio
            tenant_id: ID do tenant (opcional)
            use_strict: Se deve usar threshold estrito

        Returns:
            Threshold configurado
        """
        config = await self._get_config(domain, tenant_id)

        if use_strict:
            return config.strict_threshold
        return config.base_threshold

    async def get_config_for(self, domain: str, tenant_id: str | None = None) -> ThresholdConfig:
        """Retorna configuração completa para domínio/tenant.

        Args:
            domain: Nome do domínio
            tenant_id: ID do tenant (opcional)

        Returns:
            Configuração de threshold
        """
        return await self._get_config(domain, tenant_id)

    async def _get_config(self, domain: str, tenant_id: str | None = None) -> ThresholdConfig:
        """Retorna configuração aplicável (precedência: tenant > domínio > global).

        Verifica cache TTL antes de retornar configuração.
        """
        # Garantir cache fresco
        await self._ensure_cache_fresh()

        # 1. Verificar configuração específica de tenant
        if tenant_id and tenant_id in self.tenant_configs:
            if domain in self.tenant_configs[tenant_id]:
                return self.tenant_configs[tenant_id][domain]
            # Se não tem domínio específico, usa global do tenant
            if "global" in self.tenant_configs[tenant_id]:
                return self.tenant_configs[tenant_id]["global"]

        # 2. Verificar configuração de domínio
        if domain in self.domain_configs:
            return self.domain_configs[domain]

        # 3. Retornar configuração global
        return self.global_config

    def _get_config_sync(self, domain: str, tenant_id: str | None = None) -> ThresholdConfig:
        """Retorna configuração aplicável sem verificar cache (versão síncrona).

        Usado internamente para evitar deadlocks em contextos síncronos.
        Precedência: tenant > domínio > global.
        """
        # 1. Verificar configuração específica de tenant
        if tenant_id and tenant_id in self.tenant_configs:
            if domain in self.tenant_configs[tenant_id]:
                return self.tenant_configs[tenant_id][domain]
            # Se não tem domínio específico, usa global do tenant
            if "global" in self.tenant_configs[tenant_id]:
                return self.tenant_configs[tenant_id]["global"]

        # 2. Verificar configuração de domínio
        if domain in self.domain_configs:
            return self.domain_configs[domain]

        # 3. Retornar configuração global
        return self.global_config

    async def should_auto_approve(
        self,
        confidence: float,
        domain: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Decide se resultado deve ser auto-aprovado.

        Args:
            confidence: Score de confiança
            domain: Nome do domínio
            tenant_id: ID do tenant

        Returns:
            True se deve auto-aprovar
        """
        config = await self._get_config(domain, tenant_id)
        return confidence >= config.min_confidence_for_auto_approve

    async def requires_human_review(
        self,
        confidence: float,
        domain: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Decide se resultado requer revisão humana.

        Args:
            confidence: Score de confiança
            domain: Nome do domínio
            tenant_id: ID do tenant

        Returns:
            True se requer revisão humana
        """
        config = await self._get_config(domain, tenant_id)
        return confidence < config.requires_human_review_below

    async def is_adaptive_enabled(self, domain: str, tenant_id: str | None = None) -> bool:
        """Verifica se threshold adaptativo está habilitado.

        Args:
            domain: Nome do domínio
            tenant_id: ID do tenant

        Returns:
            True se adaptativo está habilitado
        """
        config = await self._get_config(domain, tenant_id)
        return config.adaptive_enabled

    async def update_threshold(
        self,
        domain: str | None,
        tenant_id: str | None,
        threshold_type: str,
        value: float,
    ) -> bool:
        """Atualiza threshold em runtime.

        Args:
            domain: Nome do domínio (None para global)
            tenant_id: ID do tenant (None para todos)
            threshold_type: Tipo de threshold (base, strict, min, etc.)
            value: Novo valor

        Returns:
            True se atualizado com sucesso
        """
        try:
            if tenant_id and domain:
                # Atualizar tenant-specific
                if tenant_id not in self.tenant_configs:
                    self.tenant_configs[tenant_id] = {}
                if domain not in self.tenant_configs[tenant_id]:
                    self.tenant_configs[tenant_id][domain] = ThresholdConfig()

                config = self.tenant_configs[tenant_id][domain]
            elif domain:
                # Atualizar domínio
                if domain not in self.domain_configs:
                    self.domain_configs[domain] = ThresholdConfig()
                config = self.domain_configs[domain]
            else:
                # Atualizar global
                config = self.global_config

            # Atualizar campo específico
            if hasattr(config, threshold_type):
                setattr(config, threshold_type, value)
                config.version += 1
                config.last_modified = datetime.now(timezone.utc)  # noqa: UP017
                logger.info(
                    "Threshold atualizado: domain=%s, tenant=%s, %s=%s, version=%s",
                    domain,
                    tenant_id,
                    threshold_type,
                    value,
                    config.version,
                )
                return True
            logger.warning("Campo de threshold inválido: %s", threshold_type)
            return False  # noqa: TRY300

        except Exception:
            logger.exception("Erro atualizando threshold")
            return False

    async def reload(self) -> bool:
        """Recarrega configuração do arquivo.

        Returns:
            True se recarregado com sucesso
        """
        if self.config_path:
            success = await self.load_from_file(self.config_path)
            if success:
                self._last_cache_refresh = datetime.now(timezone.utc)  # noqa: UP017
            return success
        logger.warning("Nenhum arquivo de configuração para recarregar")
        return False

    def export_config(self) -> dict[str, Any]:
        """Exporta configuração atual como dicionário.

        Returns:
            Configuração completa
        """
        return {
            "global": self.global_config.to_dict(),
            "domains": {name: config.to_dict() for name, config in self.domain_configs.items()},
            "tenants": {
                tenant_id: {domain: config.to_dict() for domain, config in domains.items()}
                for tenant_id, domains in self.tenant_configs.items()
            },
            "feature_flags": self.feature_flags,
            "metadata": {
                "last_reload": self._last_reload.isoformat() if self._last_reload else None,
                "last_cache_refresh": (
                    self._last_cache_refresh.isoformat() if self._last_cache_refresh else None
                ),
                "auto_reload_enabled": self.enable_auto_reload,
                "reload_interval_seconds": self.reload_interval_seconds,
                "cache_ttl_seconds": self.cache_ttl_seconds,
                "cache_expired": asyncio.iscoroutinefunction(self._check_cache_expired),
            },
        }

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do serviço.

        Returns:
            Estatísticas atuais
        """
        return {
            "global_threshold": self.global_config.base_threshold,
            "domains_configured": len(self.domain_configs),
            "tenants_configured": len(self.tenant_configs),
            "feature_flags_count": len(self.feature_flags),
            "last_reload": self._last_reload.isoformat() if self._last_reload else None,
            "last_cache_refresh": (
                self._last_cache_refresh.isoformat() if self._last_cache_refresh else None
            ),
            "auto_reload_enabled": self.enable_auto_reload,
            "cache_ttl_seconds": self.cache_ttl_seconds,
        }

    def get_cache_info(self) -> dict[str, Any]:
        """Retorna informações sobre o cache.

        Returns:
            Informações do cache incluindo status de expiração
        """
        cache_age = None
        if self._last_cache_refresh:
            cache_age = (
                datetime.now(timezone.utc) - self._last_cache_refresh  # noqa: UP017
            ).total_seconds()

        return {
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "cache_age_seconds": cache_age,
            "cache_expired": (
                cache_age > self.cache_ttl_seconds
                if cache_age and self.cache_ttl_seconds > 0
                else False
            ),
            "last_cache_refresh": (
                self._last_cache_refresh.isoformat() if self._last_cache_refresh else None
            ),
            "auto_reload_enabled": self.enable_auto_reload,
            "reload_task_running": self._reload_task is not None and not self._reload_task.done(),
        }

    async def shutdown(self) -> None:
        """Para o serviço e limpa recursos."""
        if self._reload_task and not self._reload_task.done():
            self._reload_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reload_task
        logger.info("threshold_service_shutdown_complete")
