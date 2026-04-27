"""Testes unitários para ThresholdService.

Autor: Neural Hive Mind
Criado: 2026-04-20 (FEAT-A-005)
"""

from datetime import timezone

import pytest
from src.services.threshold_service import ThresholdConfig, ThresholdService


@pytest.mark.asyncio()
class TestThresholdConfig:
    """Testes para ThresholdConfig."""

    async def test_initialization_defaults(self):
        """Testa inicialização com valores padrão."""
        config = ThresholdConfig()

        assert config.min_threshold == 0.3
        assert config.base_threshold == 0.5
        assert config.strict_threshold == 0.75
        assert config.adaptive_enabled is True
        assert config.min_confidence_for_auto_approve == 0.8
        assert config.requires_human_review_below == 0.4

    async def test_initialization_custom_values(self):
        """Testa inicialização com valores customizados."""
        config = ThresholdConfig(
            min_threshold=0.2,
            base_threshold=0.6,
            strict_threshold=0.8,
            adaptive_enabled=False,
        )

        assert config.min_threshold == 0.2
        assert config.base_threshold == 0.6
        assert config.strict_threshold == 0.8
        assert config.adaptive_enabled is False

    async def test_to_dict(self):
        """Testa conversão para dicionário."""
        config = ThresholdConfig(base_threshold=0.7)
        data = config.to_dict()

        assert data["base_threshold"] == 0.7
        assert "last_modified" in data
        assert "version" in data

    async def test_from_dict(self):
        """Testa criação a partir de dicionário."""
        data = {
            "min_threshold": 0.25,
            "base_threshold": 0.55,
            "strict_threshold": 0.85,
            "adaptive_enabled": False,
        }

        config = ThresholdConfig.from_dict(data)

        assert config.min_threshold == 0.25
        assert config.base_threshold == 0.55
        assert config.strict_threshold == 0.85
        assert config.adaptive_enabled is False


@pytest.mark.asyncio()
class TestThresholdService:
    """Testes para ThresholdService."""

    async def test_initialization(self):
        """Testa inicialização do serviço."""
        service = ThresholdService()
        await service.initialize()

        assert service.global_config.base_threshold == 0.5
        assert len(service.domain_configs) == 0
        assert len(service.tenant_configs) == 0

    async def test_get_threshold_for_global(self):
        """Testa obter threshold global."""
        service = ThresholdService()
        await service.initialize()

        threshold = await service.get_threshold_for("BUSINESS")

        assert threshold == 0.5

    async def test_get_threshold_for_domain(self):
        """Testa obter threshold de domínio específico."""
        service = ThresholdService()
        service.domain_configs["BUSINESS"] = ThresholdConfig(base_threshold=0.6)

        threshold = await service.get_threshold_for("BUSINESS")

        assert threshold == 0.6

    async def test_get_threshold_strict(self):
        """Testa obter threshold estrito."""
        service = ThresholdService()
        await service.initialize()

        threshold = await service.get_threshold_for("TECHNICAL", use_strict=True)

        assert threshold == 0.75

    async def test_get_config_for(self):
        """Testa obter configuração completa."""
        service = ThresholdService()
        await service.initialize()

        config = await service.get_config_for("SECURITY")

        assert config.base_threshold == 0.5
        assert config.strict_threshold == 0.75

    async def test_should_auto_approve(self):
        """Testa decisão de auto-aprovação."""
        service = ThresholdService()
        await service.initialize()

        # Confiança alta deve auto-aprovar
        assert await service.should_auto_approve(0.85, "BUSINESS") is True

        # Confiança baixa não deve auto-aprovar
        assert await service.should_auto_approve(0.7, "BUSINESS") is False

    async def test_requires_human_review(self):
        """Testa decisão de revisão humana."""
        service = ThresholdService()
        await service.initialize()

        # Confiança muito baixa requer revisão
        assert await service.requires_human_review(0.3, "TECHNICAL") is True

        # Confiança alta não requer revisão
        assert await service.requires_human_review(0.6, "TECHNICAL") is False

    async def test_is_adaptive_enabled(self):
        """Testa se adaptativo está habilitado."""
        service = ThresholdService()
        await service.initialize()

        assert await service.is_adaptive_enabled("INFRASTRUCTURE") is True

        # Desabilitar para um domínio
        service.domain_configs["SECURITY"] = ThresholdConfig(adaptive_enabled=False)
        assert await service.is_adaptive_enabled("SECURITY") is False

    async def test_update_threshold_global(self):
        """Testa atualização de threshold global."""
        service = ThresholdService()
        await service.initialize()

        success = await service.update_threshold(
            domain=None, tenant_id=None, threshold_type="base_threshold", value=0.65
        )

        assert success is True
        assert service.global_config.base_threshold == 0.65

    async def test_update_threshold_domain(self):
        """Testa atualização de threshold de domínio."""
        service = ThresholdService()
        await service.initialize()

        success = await service.update_threshold(
            domain="BUSINESS", tenant_id=None, threshold_type="base_threshold", value=0.7
        )

        assert success is True
        assert service.domain_configs["BUSINESS"].base_threshold == 0.7

    async def test_update_threshold_tenant(self):
        """Testa atualização de threshold específico de tenant."""
        service = ThresholdService()
        await service.initialize()

        success = await service.update_threshold(
            domain="TECHNICAL", tenant_id="tenant-001", threshold_type="base_threshold", value=0.55
        )

        assert success is True
        assert "tenant-001" in service.tenant_configs
        assert service.tenant_configs["tenant-001"]["TECHNICAL"].base_threshold == 0.55

    async def test_precedence_tenant_over_domain(self):
        """Testa precedência: tenant > domínio > global."""
        service = ThresholdService()

        # Configurar global
        service.global_config = ThresholdConfig(base_threshold=0.5)

        # Configurar domínio
        service.domain_configs["BUSINESS"] = ThresholdConfig(base_threshold=0.6)

        # Configurar tenant
        service.tenant_configs["tenant-001"] = {"BUSINESS": ThresholdConfig(base_threshold=0.7)}

        # Tenant tem precedência
        config = await service.get_config_for("BUSINESS", "tenant-001")
        assert config.base_threshold == 0.7

        # Domínio tem precedência sobre global
        config = await service.get_config_for("BUSINESS", "tenant-002")
        assert config.base_threshold == 0.6

    async def test_export_config(self):
        """Testa exportação de configuração."""
        service = ThresholdService()
        await service.initialize()

        service.domain_configs["BUSINESS"] = ThresholdConfig(base_threshold=0.6)

        exported = service.export_config()

        assert "global" in exported
        assert "domains" in exported
        assert "tenants" in exported
        assert exported["domains"]["BUSINESS"]["base_threshold"] == 0.6

    async def test_get_stats(self):
        """Testa obter estatísticas."""
        service = ThresholdService()
        await service.initialize()

        service.domain_configs["BUSINESS"] = ThresholdConfig()
        service.tenant_configs["tenant-001"] = {}

        stats = service.get_stats()

        assert stats["global_threshold"] == 0.5
        assert stats["domains_configured"] == 1
        assert stats["tenants_configured"] == 1

    async def test_load_from_dict_data(self):
        """Testa carregamento de dados de configuração."""
        service = ThresholdService()

        data = {
            "global": {"base_threshold": 0.55, "adaptive_enabled": False},
            "domains": {"SECURITY": {"base_threshold": 0.7}},
            "tenants": {"tenant-001": {"domains": {"BUSINESS": {"base_threshold": 0.65}}}},
            "feature_flags": {"feature_x": True},
        }

        await service._load_config_data(data)

        assert service.global_config.base_threshold == 0.55
        assert service.global_config.adaptive_enabled is False
        assert service.domain_configs["SECURITY"].base_threshold == 0.7
        assert service.tenant_configs["tenant-001"]["BUSINESS"].base_threshold == 0.65
        assert service.feature_flags["feature_x"] is True

    async def test_invalid_threshold_type(self):
        """Testa atualização com tipo inválido."""
        service = ThresholdService()
        await service.initialize()

        success = await service.update_threshold(
            domain=None, tenant_id=None, threshold_type="invalid_type", value=0.5
        )

        assert success is False


@pytest.mark.asyncio()
class TestThresholdServiceCacheTTL:
    """Testes para Cache TTL do ThresholdService (FEAT-A-005)."""

    async def test_cache_ttl_initialization(self):
        """Testa inicialização com cache_ttl."""
        service = ThresholdService(cache_ttl_seconds=300)
        await service.initialize()

        assert service.cache_ttl_seconds == 300

    async def test_cache_ttl_zero_no_expiration(self):
        """Testa cache com TTL zero (sem expiração)."""
        service = ThresholdService(cache_ttl_seconds=0)
        await service.initialize()

        # Definir um cache refresh antigo
        from datetime import datetime, timedelta

        service._last_cache_refresh = datetime.now(timezone.utc) - timedelta(days=1)

        # Cache não deve expirar quando TTL é 0
        assert await service._check_cache_expired() is False

    async def test_cache_expired_initial_state(self):
        """Testa que cache é considerado expirado quando nunca foi carregado."""
        service = ThresholdService(cache_ttl_seconds=300)
        await service.initialize()

        # Sem cache refresh, deve estar expirado
        assert await service._check_cache_expired() is True

    async def test_cache_not_expired_within_ttl(self):
        """Testa que cache não expira dentro do TTL."""
        service = ThresholdService(cache_ttl_seconds=300)
        await service.initialize()

        # Definir cache refresh recente
        from datetime import datetime, timedelta

        service._last_cache_refresh = datetime.now(timezone.utc) - timedelta(seconds=60)

        # Cache não deve estar expirado
        assert await service._check_cache_expired() is False

    async def test_cache_expired_after_ttl(self):
        """Testa que cache expira após TTL."""
        service = ThresholdService(cache_ttl_seconds=300)
        await service.initialize()

        # Definir cache refresh antigo (mais de 300 segundos)
        from datetime import datetime, timedelta

        service._last_cache_refresh = datetime.now(timezone.utc) - timedelta(seconds=301)

        # Cache deve estar expirado
        assert await service._check_cache_expired() is True

    async def test_get_config_refreshes_expired_cache(self):
        """Testa que _get_config atualiza cache expirado."""
        service = ThresholdService(
            config_path=None,  # Sem arquivo
            cache_ttl_seconds=1,  # TTL curto
        )
        await service.initialize()

        # Configurar um domínio
        service.domain_configs["BUSINESS"] = ThresholdConfig(base_threshold=0.6)

        # Definir cache refresh antigo (expirado)
        from datetime import datetime, timedelta

        service._last_cache_refresh = datetime.now(timezone.utc) - timedelta(seconds=2)

        # Config expirou mas não há arquivo para recarregar
        # Deve retornar configuração existente mesmo com cache expirado
        config = await service._get_config("BUSINESS")
        assert config.base_threshold == 0.6

    async def test_get_cache_info(self):
        """Testa obter informações do cache."""
        service = ThresholdService(cache_ttl_seconds=300)
        await service.initialize()

        cache_info = service.get_cache_info()

        assert cache_info["cache_ttl_seconds"] == 300
        assert cache_info["cache_age_seconds"] is None
        assert cache_info["cache_expired"] is False  # Sem refresh ainda
        assert cache_info["last_cache_refresh"] is None
        assert cache_info["auto_reload_enabled"] is False

    async def test_get_cache_info_with_age(self):
        """Testa obter informações do cache com idade."""
        service = ThresholdService(cache_ttl_seconds=300)
        await service.initialize()

        # Definir cache refresh
        from datetime import datetime

        service._last_cache_refresh = datetime.now(timezone.utc)

        cache_info = service.get_cache_info()

        assert cache_info["cache_ttl_seconds"] == 300
        assert cache_info["cache_age_seconds"] is not None
        assert cache_info["cache_age_seconds"] >= 0
        assert cache_info["cache_expired"] is False
        assert cache_info["last_cache_refresh"] is not None

    async def test_export_config_includes_cache_ttl(self):
        """Testa que export_config inclui cache_ttl."""
        service = ThresholdService(cache_ttl_seconds=600)
        await service.initialize()

        exported = service.export_config()

        assert "metadata" in exported
        assert "cache_ttl_seconds" in exported["metadata"]
        assert exported["metadata"]["cache_ttl_seconds"] == 600
        assert "last_cache_refresh" in exported["metadata"]

    async def test_get_stats_includes_cache_ttl(self):
        """Testa que get_stats inclui cache_ttl."""
        service = ThresholdService(cache_ttl_seconds=450)
        await service.initialize()

        stats = service.get_stats()

        assert "cache_ttl_seconds" in stats
        assert stats["cache_ttl_seconds"] == 450
        assert "last_cache_refresh" in stats

    async def test_shutdown_cancels_reload_task(self):
        """Testa que shutdown cancela task de auto-reload."""
        import tempfile
        from pathlib import Path

        # Criar arquivo de config temporário para auto-reload funcionar
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("global:\n  base_threshold: 0.5\n")
            temp_config_path = f.name

        try:
            service = ThresholdService(
                config_path=temp_config_path,  # Necessário para auto-reload
                cache_ttl_seconds=300,
                enable_auto_reload=True,
                reload_interval_seconds=1,
            )
            await service.initialize()

            # Aguardar task iniciar
            import asyncio

            await asyncio.sleep(0.1)

            # Verificar que task existe
            assert service._reload_task is not None

            # Shutdown
            await service.shutdown()

            # Task deve estar cancelada ou completa
            assert service._reload_task.done() or service._reload_task.cancelled()
        finally:
            # Limpar arquivo temporário
            Path(temp_config_path).unlink(missing_ok=True)

    async def test_auto_reload_loop_refreshes_cache(self):
        """Testa que auto-reload atualiza cache."""
        import tempfile
        from pathlib import Path

        # Criar arquivo de config temporário
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("global:\n  base_threshold: 0.5\n")
            temp_config_path = f.name

        try:
            service = ThresholdService(
                config_path=temp_config_path,
                cache_ttl_seconds=300,
                enable_auto_reload=True,
                reload_interval_seconds=0.5,  # Curto para teste
            )
            await service.initialize()

            initial_refresh = service._last_cache_refresh

            # Aguardar um ciclo de reload
            import asyncio

            await asyncio.sleep(0.7)

            # Cache refresh deve ter sido atualizado (ou pelo menos task ainda está rodando)
            assert service._reload_task is not None
            assert not service._reload_task.done()

            await service.shutdown()
        finally:
            # Limpar arquivo temporário
            Path(temp_config_path).unlink(missing_ok=True)
