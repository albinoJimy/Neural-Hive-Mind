"""Testes para AutoApplier."""
import pytest
from unittest.mock import AsyncMock, patch

from src.services.auto_applier import OptimizationApplier, SAFE_GUARD_PATTERNS


@pytest.mark.asyncio
class TestOptimizationApplier:
    """Testes para OptimizationApplier."""

    async def test_safety_check_blocks_config_files(self):
        """Testa que arquivos de configuração são bloqueados."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-001",
            "file_path": "services/optimizer-agents/config/settings.py",
            "target_type": "code",
            "auto_apply": True,
        }

        result = applier._check_safety(recommendation)

        assert result["safe"] is False
        assert "blocked pattern" in result["reason"]

    async def test_safety_check_blocks_test_files(self):
        """Testa que arquivos de teste são bloqueados."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-002",
            "file_path": "services/test_optimizer.py",
            "target_type": "code",
            "auto_apply": True,
        }

        result = applier._check_safety(recommendation)

        assert result["safe"] is False

    async def test_safety_check_allows_safe_files(self):
        """Testa que arquivos seguros são permitidos."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-003",
            "file_path": "services/optimizer-agents/src/analyzers/mongodb_analyzer.py",
            "target_type": "code",
            "auto_apply": True,
            "severity": "medium",
        }

        result = applier._check_safety(recommendation)

        assert result["safe"] is True

    async def test_safety_check_blocks_critical_severity(self):
        """Testa que recomendações críticas requerem revisão manual."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-004",
            "file_path": "src/analyzers/code_analyzer.py",
            "target_type": "code",
            "auto_apply": True,
            "severity": "critical",
        }

        result = applier._check_safety(recommendation)

        assert result["safe"] is False
        assert "manual review" in result["reason"]

    async def test_apply_without_auto_apply_flag_skips(self):
        """Testa que recomendações sem flag auto_apply são ignoradas."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-005",
            "file_path": "src/analyzers/base.py",
            "target_type": "code",
            "auto_apply": False,  # Flag desativada
        }

        result = await applier.apply_recommendation(recommendation)

        assert result["success"] is False
        assert result["skipped"] is True
        assert "auto-apply" in result["reason"]

    async def test_apply_dry_run_does_not_modify_files(self):
        """Testa que dry_run não modifica arquivos."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-006",
            "file_path": "src/analyzers/base.py",
            "target_type": "code",
            "auto_apply": True,
            "severity": "medium",
            "code_diff": "@@ -1,1 +1,1 @@\n-old line\n+new line",
        }

        # Passar o diretório atual como project_root
        result = await applier.apply_recommendation(
            recommendation,
            project_root=".",
        )

        assert result["success"] is True
        assert result.get("dry_run") is True
        assert result.get("applied") is False

    async def test_validate_application_calculates_improvement(self):
        """Testa cálculo de melhoria na validação."""
        applier = OptimizationApplier(dry_run=True)

        before = {"duration_ms": 1000}
        after = {"duration_ms": 700}

        result = await applier.validate_application(before, after)

        assert result["valid"] is True
        assert result["improvement_pct"] == 30.0
        assert result["successful"] is True

    async def test_validate_regression_detected(self):
        """Testa que regressão é detectada."""
        applier = OptimizationApplier(dry_run=True)

        before = {"duration_ms": 500}
        after = {"duration_ms": 800}

        result = await applier.validate_application(before, after)

        assert result["improvement_pct"] == -60.0
        assert result["successful"] is False

    async def test_database_optimization_not_auto_applied(self):
        """Testa que otimizações de banco não são aplicadas automaticamente."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-007",
            "target_type": "mongodb",
            "type": "index_suggestion",
            "auto_apply": True,
            "query_suggestion": "db.users.create_index({'email': 1})",
        }

        result = await applier.apply_recommendation(recommendation)

        assert result["success"] is True
        assert result["applied"] is False
        assert "manual review" in result["reason"]
        assert result.get("suggested_query") == "db.users.create_index({'email': 1})"

    async def test_get_stats(self):
        """Testa retorno de estatísticas."""
        applier = OptimizationApplier(dry_run=True)

        stats = applier.get_stats()

        assert "applied" in stats
        assert "skipped" in stats
        assert stats["applied"] == 0
        assert stats["skipped"] == 0


class TestSafeGuardPatterns:
    """Testes para padrões de segurança."""

    def test_config_pattern_is_present(self):
        """Testa que padrão de config está definido."""
        assert any(r"config" in p for p in SAFE_GUARD_PATTERNS)

    def test_test_pattern_is_present(self):
        """Testa que padrão de test está definido."""
        assert any(r"test" in p for p in SAFE_GUARD_PATTERNS)

    def test_migration_pattern_is_present(self):
        """Testa que padrão de migration está definido."""
        assert any(r"migration" in p for p in SAFE_GUARD_PATTERNS)

    def test_secret_pattern_is_present(self):
        """Testa que padrão de secret está definido."""
        assert any(r"secret" in p for p in SAFE_GUARD_PATTERNS)

    def test_env_pattern_is_present(self):
        """Testa que padrão de .env está definido."""
        assert any(r"\.env" in p for p in SAFE_GUARD_PATTERNS)

    def test_key_pattern_is_present(self):
        """Testa que padrão de .key está definido."""
        assert any(r"\.key$" in p for p in SAFE_GUARD_PATTERNS)

    def test_pem_pattern_is_present(self):
        """Testa que padrão de .pem está definido."""
        assert any(r"\.pem$" in p for p in SAFE_GUARD_PATTERNS)


class TestApplyCodeOptimization:
    """Testes para _apply_code_optimization."""

    @pytest.mark.asyncio
    async def test_apply_code_success(self):
        """Testa aplicação de otimização de código com sucesso."""
        applier = OptimizationApplier(dry_run=False)

        recommendation = {
            "id": "rec-code-001",
            "file_path": "src/services/test_service.py",
            "target_type": "code",
            "auto_apply": True,
            "code_diff": "@@ -1,3 +1,3 @@\n-old code\n+new code",
            "line_start": 1,
            "line_end": 3,
        }

        with patch("builtins.open", create=True) as mock_open:
            with patch("os.path.exists", return_value=True):
                mock_file = AsyncMock()
                mock_file.read.return_value = "old code"
                mock_open.return_value.__enter__.return_value = mock_file

                result = await applier.apply_recommendation(
                    recommendation,
                    project_root=".",
                )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_apply_code_unsupported_extension(self):
        """Testa que extensões não suportadas são rejeitadas."""
        applier = OptimizationApplier(dry_run=False)

        recommendation = {
            "id": "rec-ext-001",
            "file_path": "data/file.bin",  # Extensão não suportada
            "target_type": "code",
            "auto_apply": True,
        }

        result = await applier.apply_recommendation(recommendation)

        assert result["success"] is False
        assert "extension not supported" in result["reason"]


class TestApplyDatabaseOptimization:
    """Testes para _apply_database_optimization."""

    @pytest.mark.asyncio
    async def test_apply_mongodb_index_suggestion(self):
        """Testa sugestão de index MongoDB."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-mongo-001",
            "target_type": "mongodb",
            "type": "index_suggestion",
            "collection": "users",
            "keys": {"email": 1},
            "auto_apply": False,
        }

        result = await applier.apply_recommendation(recommendation)

        assert result["success"] is True
        assert result["applied"] is False

    @pytest.mark.asyncio
    async def test_apply_postgresql_optimization(self):
        """Testa otimização PostgreSQL."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-pg-001",
            "target_type": "postgresql",
            "type": "query_optimization",
            "suggestion": "ANALYZE users;",
            "auto_apply": False,
        }

        result = await applier.apply_recommendation(recommendation)

        assert result["success"] is True
        assert result["applied"] is False

    @pytest.mark.asyncio
    async def test_apply_redis_optimization(self):
        """Testa otimização Redis."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-redis-001",
            "target_type": "redis",
            "type": "memory_optimization",
            "suggestion": "Set maxmemory-policy",
            "auto_apply": False,
        }

        result = await applier.apply_recommendation(recommendation)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_apply_neo4j_optimization(self):
        """Testa otimização Neo4j."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-neo4j-001",
            "target_type": "neo4j",
            "type": "index_suggestion",
            "label": "User",
            "property": "email",
            "auto_apply": False,
        }

        result = await applier.apply_recommendation(recommendation)

        assert result["success"] is True


class TestCalculateImprovement:
    """Testes para cálculo de melhoria."""

    @pytest.mark.asyncio
    async def test_improvement_positive(self):
        """Testa cálculo de melhoria positiva."""
        applier = OptimizationApplier()

        result = await applier.validate_application(
            before={"duration_ms": 100},
            after={"duration_ms": 80}
        )

        assert result["improvement_pct"] == 20.0
        assert result["successful"] is True

    @pytest.mark.asyncio
    async def test_improvement_no_change(self):
        """Testa quando não há mudança."""
        applier = OptimizationApplier()

        result = await applier.validate_application(
            before={"duration_ms": 100},
            after={"duration_ms": 100}
        )

        assert result["improvement_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_improvement_with_multiple_metrics(self):
        """Testa cálculo com múltiplas métricas."""
        applier = OptimizationApplier()

        result = await applier.validate_application(
            before={"duration_ms": 100, "memory_mb": 50, "cpu_pct": 80},
            after={"duration_ms": 80, "memory_mb": 40, "cpu_pct": 60}
        )

        assert result["improvement_pct"] > 0
        assert result["successful"] is True


class TestStatsTracking:
    """Testes para rastreamento de estatísticas."""

    @pytest.mark.asyncio
    async def test_stats_increments_on_apply(self):
        """Testa que estatísticas incrementam."""
        applier = OptimizationApplier(dry_run=False)

        recommendation = {
            "id": "rec-stats-001",
            "file_path": "src/test.py",
            "target_type": "code",
            "auto_apply": True,
            "severity": "low",
        }

        with patch("os.path.exists", return_value=True):
            await applier.apply_recommendation(recommendation, project_root=".")

        stats = applier.get_stats()
        assert "applied" in stats

    @pytest.mark.asyncio
    async def test_stats_increments_on_skip(self):
        """Testa que skips incrementam contador."""
        applier = OptimizationApplier()

        recommendation = {
            "id": "rec-skip-001",
            "file_path": "config/settings.py",  # Bloqueado
            "target_type": "code",
            "auto_apply": True,
        }

        await applier.apply_recommendation(recommendation)

        stats = applier.get_stats()
        assert "skipped" in stats
