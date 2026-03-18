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
