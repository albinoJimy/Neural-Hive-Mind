"""
Unit tests for OptimizationApplier service (optimizer-agents).

Tests automatic application of code and database optimizations.
"""

import os
from unittest.mock import patch

import pytest

from src.services.auto_applier import OptimizationApplier


class TestOptimizationApplierInitialization:
    """Test OptimizationApplier initialization."""

    def test_initialization_dry_run_true(self):
        """Test initialization with dry_run=True."""
        applier = OptimizationApplier(dry_run=True)

        assert applier.dry_run is True
        assert applier._applied_count == 0
        assert applier._skipped_count == 0

    def test_initialization_dry_run_false(self):
        """Test initialization with dry_run=False."""
        applier = OptimizationApplier(dry_run=False)

        assert applier.dry_run is False
        assert applier._applied_count == 0

    def test_initialization_default(self):
        """Test default initialization is dry run."""
        applier = OptimizationApplier()

        assert applier.dry_run is True


class TestSafetyChecks:
    """Test safety check functionality."""

    def test_check_safety_safe_recommendation(self, sample_code_recommendation):
        """Test safety check for safe recommendation."""
        applier = OptimizationApplier()

        result = applier._check_safety(sample_code_recommendation)

        assert result["safe"] is True

    def test_check_safety_test_file_blocked(self, sample_unsafe_recommendation):
        """Test safety check blocks test files."""
        applier = OptimizationApplier()

        result = applier._check_safety(sample_unsafe_recommendation)

        assert result["safe"] is False
        assert "test" in result["reason"].lower()

    def test_check_safety_config_file_blocked(self):
        """Test safety check blocks config files."""
        applier = OptimizationApplier()

        recommendation = {"file_path": "services/config/settings.yaml", "severity": "low"}

        result = applier._check_safety(recommendation)

        assert result["safe"] is False
        assert "config" in result["reason"].lower()

    def test_check_safety_migration_file_blocked(self):
        """Test safety check blocks migration files."""
        applier = OptimizationApplier()

        recommendation = {"file_path": "database/migrations/001_init.sql", "severity": "low"}

        result = applier._check_safety(recommendation)

        assert result["safe"] is False
        assert "migration" in result["reason"].lower()

    def test_check_safety_env_file_blocked(self):
        """Test safety check blocks .env files."""
        applier = OptimizationApplier()

        recommendation = {"file_path": ".env.production", "severity": "low"}

        result = applier._check_safety(recommendation)

        assert result["safe"] is False

    def test_check_safety_critical_severity_blocked(self, sample_critical_recommendation):
        """Test safety check blocks critical severity."""
        applier = OptimizationApplier()

        result = applier._check_safety(sample_critical_recommendation)

        assert result["safe"] is False
        assert "critical" in result["reason"].lower()

    def test_check_safety_unsupported_extension_blocked(self):
        """Test safety check blocks unsupported extensions."""
        applier = OptimizationApplier()

        recommendation = {"file_path": "video.mp4", "severity": "low"}

        result = applier._check_safety(recommendation)

        assert result["safe"] is False
        assert "extension" in result["reason"].lower()

    def test_check_safety_supported_extensions(self):
        """Test safety check allows supported extensions."""
        applier = OptimizationApplier()

        supported_files = [
            "test.py",
            "test.js",
            "test.ts",
            "test.go",
            "test.java",
            "test.rs",
            "test.cpp",
            "test.yaml",
            "test.json",
        ]

        for file_path in supported_files:
            recommendation = {"file_path": file_path, "severity": "low"}
            result = applier._check_safety(recommendation)
            assert result["safe"] is True, f"Failed for {file_path}"


class TestCodeOptimizationApplication:
    """Test code optimization application."""

    @pytest.mark.asyncio
    async def test_apply_code_optimization_missing_file_path(self, sample_code_recommendation):
        """Test applying optimization without file path."""
        applier = OptimizationApplier()
        recommendation = sample_code_recommendation.copy()
        recommendation["file_path"] = None

        result = await applier._apply_code_optimization(recommendation)

        assert result["success"] is False
        assert "file path" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_apply_code_optimization_file_not_found(self, sample_code_recommendation):
        """Test applying optimization to non-existent file."""
        applier = OptimizationApplier()

        result = await applier._apply_code_optimization(
            sample_code_recommendation, "/nonexistent/path"
        )

        assert result["success"] is False
        assert "not found" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_apply_code_optimization_no_diff(self, sample_code_recommendation):
        """Test applying optimization without code diff."""
        applier = OptimizationApplier()
        recommendation = sample_code_recommendation.copy()
        recommendation["code_diff"] = None

        with patch.object(os.path, "exists", return_value=True):
            result = await applier._apply_code_optimization(recommendation, "/fake/path")

            assert result["success"] is True
            assert result["applied"] is False
            assert "no code_diff" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_apply_code_optimization_dry_run(self, sample_code_recommendation):
        """Test dry run mode doesn't apply changes."""
        applier = OptimizationApplier(dry_run=True)

        result = await applier._apply_code_optimization(sample_code_recommendation, "/fake/path")

        assert result["success"] is True
        assert result["applied"] is False
        assert result["dry_run"] is True


class TestDatabaseOptimizationApplication:
    """Test database optimization application."""

    @pytest.mark.asyncio
    async def test_apply_database_optimization(self, sample_database_recommendation):
        """Test database optimization is not auto-applied."""
        applier = OptimizationApplier()

        result = await applier._apply_database_optimization(
            sample_database_recommendation, "/fake/path"
        )

        assert result["success"] is True
        assert result["applied"] is False
        assert "manual" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_apply_database_optimization_includes_query(self, sample_database_recommendation):
        """Test database optimization includes suggested query."""
        applier = OptimizationApplier()

        result = await applier._apply_database_optimization(
            sample_database_recommendation, "/fake/path"
        )

        assert "query_suggestion" in result


class TestMainApplyRecommendation:
    """Test main apply recommendation method."""

    @pytest.mark.asyncio
    async def test_apply_recommendation_safe_blocked(self, sample_unsafe_recommendation):
        """Test unsafe recommendations are blocked."""
        applier = OptimizationApplier()

        result = await applier.apply_recommendation(sample_unsafe_recommendation)

        assert result["success"] is False
        assert result["skipped"] is True

    @pytest.mark.asyncio
    async def test_apply_recommendation_auto_apply_false(self):
        """Test recommendations without auto_apply flag are skipped."""
        applier = OptimizationApplier()

        recommendation = {"id": "test-001", "file_path": "test.py", "auto_apply": False}

        result = await applier.apply_recommendation(recommendation)

        assert result["success"] is False
        assert "auto_apply" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_apply_recommendation_unsupported_type(self):
        """Test unsupported target types are rejected."""
        applier = OptimizationApplier()

        recommendation = {"id": "test-001", "target_type": "unknown_type", "auto_apply": True}

        result = await applier.apply_recommendation(recommendation)

        assert result["success"] is False
        assert "unsupported" in result["reason"].lower()


class TestPatchParsing:
    """Test unified diff parsing."""

    def test_parse_unified_diff_single_hunk(self):
        """Test parsing a single hunk."""
        applier = OptimizationApplier()

        patch = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
-old line
+new line
 context line
"""

        hunks = applier._parse_unified_diff(patch)

        assert len(hunks) == 1
        assert hunks[0]["old_start"] == 0  # Line 1 - 1 (0-indexed)
        assert hunks[0]["old_count"] == 1
        assert hunks[0]["new_start"] == 0
        assert hunks[0]["new_count"] == 1

    def test_parse_unified_diff_multiple_hunks(self):
        """Test parsing multiple hunks."""
        applier = OptimizationApplier()

        patch = """--- a/test.py
+++ b/test.py
@@ -1,2 +1,2 @@
-old1
+new1
@@ -5,2 +5,2 @@
-old2
+new2
"""

        hunks = applier._parse_unified_diff(patch)

        assert len(hunks) == 2

    def test_parse_unified_diff_with_context(self):
        """Test parsing hunks with context lines."""
        applier = OptimizationApplier()

        patch = """--- a/test.py
+++ b/test.py
@@ -1,5 +1,5 @@
 line1
-old_line
+new_line
 line3
 line4
"""

        hunks = applier._parse_unified_diff(patch)

        assert len(hunks) == 1
        # Should have delete, insert, and context changes
        assert len(hunks[0]["changes"]) == 4

    def test_parse_unified_diff_empty(self):
        """Test parsing empty patch."""
        applier = OptimizationApplier()

        hunks = applier._parse_unified_diff("")

        assert len(hunks) == 0


class TestHunkApplication:
    """Test hunk application to file lines."""

    def test_apply_hunk_delete_line(self):
        """Test applying hunk with line deletion."""
        applier = OptimizationApplier()

        lines = ["line1", "to_delete", "line3"]
        hunk = {
            "old_start": 1,  # Line 2 (0-indexed)
            "old_count": 1,
            "new_start": 1,
            "new_count": 0,
            "changes": [("delete", "to_delete")],
        }

        new_lines, success = applier._apply_hunk_to_lines(lines, hunk)

        assert success is True
        assert "to_delete" not in new_lines
        assert len(new_lines) == 2

    def test_apply_hunk_insert_line(self):
        """Test applying hunk with line insertion."""
        applier = OptimizationApplier()

        lines = ["line1", "line2"]
        hunk = {
            "old_start": 1,
            "old_count": 0,
            "new_start": 1,
            "new_count": 1,
            "changes": [("insert", "new_line")],
        }

        new_lines, success = applier._apply_hunk_to_lines(lines, hunk)

        assert success is True
        assert "new_line" in new_lines
        assert len(new_lines) == 3

    def test_apply_hunk_context_mismatch(self):
        """Test hunk fails when context doesn't match."""
        applier = OptimizationApplier()

        lines = ["line1", "wrong_context", "line3"]
        hunk = {
            "old_start": 0,
            "old_count": 2,
            "new_start": 0,
            "new_count": 2,
            "changes": [("context", "line1"), ("context", "different_context")],  # Won't match
        }

        new_lines, success = applier._apply_hunk_to_lines(lines, hunk)

        assert success is False
        assert new_lines == lines  # Lines unchanged

    def test_apply_hunk_out_of_bounds(self):
        """Test hunk fails when out of bounds."""
        applier = OptimizationApplier()

        lines = ["line1", "line2"]
        hunk = {
            "old_start": 0,
            "old_count": 5,  # More lines than available
            "new_start": 0,
            "new_count": 5,
            "changes": [],
        }

        new_lines, success = applier._apply_hunk_to_lines(lines, hunk)

        assert success is False


class TestValidation:
    """Test optimization validation."""

    @pytest.mark.asyncio
    async def test_validate_application_improvement(self):
        """Test validation with improvement."""
        applier = OptimizationApplier()

        before = {"duration_ms": 1000}
        after = {"duration_ms": 800}

        result = await applier.validate_application(before, after)

        assert result["valid"] is True
        assert result["improvement_pct"] == 20.0

    @pytest.mark.asyncio
    async def test_validate_application_degradation(self):
        """Test validation with degradation."""
        applier = OptimizationApplier()

        before = {"duration_ms": 1000}
        after = {"duration_ms": 1200}

        result = await applier.validate_application(before, after)

        assert result["valid"] is True
        assert result["improvement_pct"] == -20.0
        assert result["successful"] is False

    @pytest.mark.asyncio
    async def test_validate_application_no_baseline(self):
        """Test validation without baseline metrics."""
        applier = OptimizationApplier()

        before = {}
        after = {"duration_ms": 800}

        result = await applier.validate_application(before, after)

        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_validate_application_zero_baseline(self):
        """Test validation with zero baseline."""
        applier = OptimizationApplier()

        before = {"duration_ms": 0}
        after = {"duration_ms": 100}

        result = await applier.validate_application(before, after)

        assert result["valid"] is False


class TestStatistics:
    """Test statistics tracking."""

    def test_get_stats(self):
        """Test getting applier statistics."""
        applier = OptimizationApplier()

        stats = applier.get_stats()

        assert "applied" in stats
        assert "skipped" in stats
        assert stats["applied"] == 0
        assert stats["skipped"] == 0


class TestPatchApplicationIntegration:
    """Test full patch application integration."""

    @pytest.mark.asyncio
    async def test_apply_patch_creates_backup(self, sample_code_recommendation, tmp_path):
        """Test patch application creates backup file."""
        applier = OptimizationApplier(dry_run=False)

        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("original content\n")

        recommendation = sample_code_recommendation.copy()
        recommendation["code_diff"] = """--- a/test.py
+++ b/test.py
@@ -1,1 +1,1 @@
-original content
+new content
"""

        result = await applier._apply_patch(
            str(test_file), recommendation["code_diff"], recommendation
        )

        # Check backup was created
        backup_files = list(tmp_path.glob("*.backup.*"))
        assert len(backup_files) > 0
        assert result["backup_path"] is not None

    @pytest.mark.asyncio
    async def test_apply_patch_success(self, tmp_path):
        """Test successful patch application."""
        applier = OptimizationApplier(dry_run=False)

        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("old_line\n")

        patch = """--- a/test.py
+++ b/test.py
@@ -1,1 +1,1 @@
-old_line
+new_line
"""

        result = await applier._apply_patch(str(test_file), patch, {"id": "test-001"})

        assert result["success"] is True
        assert result["applied"] is True

        # Verify file was modified
        new_content = test_file.read_text()
        assert "new_line" in new_content
        assert "old_line" not in new_content


class TestGuardPatterns:
    """Test guard pattern matching."""

    def test_guard_pattern_tests_directory(self):
        """Test pattern matches test directories."""
        import re

        test_path = "src/tests/test_file.py"
        for pattern in OptimizationApplier.__dict__["SAFE_GUARD_PATTERNS"]:
            if pattern and "test" in pattern:
                # Check if pattern matches
                if re.match(pattern, test_path):
                    assert True
                    return
        assert False, "No test pattern matched"

    def test_guard_pattern_test_prefix(self):
        """Test pattern matches test_ prefix files."""
        import re

        test_path = "src/test_module.py"
        for pattern in OptimizationApplier.__dict__["SAFE_GUARD_PATTERNS"]:
            if pattern and "test_" in pattern:
                if re.match(pattern, test_path):
                    assert True
                    return
        assert False, "No test_ pattern matched"

    def test_guard_pattern_secrets_directory(self):
        """Test pattern matches secrets directory."""
        import re

        test_path = "src/secrets/api_key.yaml"
        for pattern in OptimizationApplier.__dict__["SAFE_GUARD_PATTERNS"]:
            if pattern and "secret" in pattern:
                if re.match(pattern, test_path):
                    assert True
                    return
        assert False, "No secrets pattern matched"

    def test_guard_pattern_key_files(self):
        """Test pattern matches .key files."""
        import re

        test_path = "config/private.key"
        for pattern in OptimizationApplier.__dict__["SAFE_GUARD_PATTERNS"]:
            if pattern and ".key" in pattern:
                if re.match(pattern, test_path):
                    assert True
                    return
        assert False, "No .key pattern matched"
