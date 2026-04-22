"""Testes para FingerprintExtractor."""

import pytest

from neural_hive_specialists.evolution_hooks.fingerprint_extractor import FingerprintExtractor
from neural_hive_specialists.evolution_hooks.models import (
    DurationRange,
    Fingerprint,
    TaskCountRange,
)


@pytest.fixture()
def extractor():
    """Retorna instancia do FingerprintExtractor."""
    return FingerprintExtractor()


class TestFingerprintExtractor:
    """Testes para FingerprintExtractor."""

    def test_extract_from_minimal_plan(self, extractor):
        """Extrai fingerprint de plano minimal."""
        plan = {
            "plan_id": "test-1",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [{"name": "build", "task_type": "BUILD"}],
        }

        result = extractor.extract(plan)

        assert isinstance(result, Fingerprint)
        assert result.domain == "technical"
        assert result.priority == "normal"
        assert result.task_count_range == TaskCountRange.SMALL

    def test_extract_task_types(self, extractor):
        """Extrai tipos unicos de tarefas."""
        plan = {
            "plan_id": "test-2",
            "original_domain": "business",
            "original_priority": "high",
            "tasks": [
                {"task_type": "BUILD"},
                {"task_type": "TEST"},
                {"task_type": "BUILD"},  # Duplicado
                {"task_type": "DEPLOY"},
            ],
        }

        result = extractor.extract(plan)

        assert set(result.task_types) == {"BUILD", "TEST", "DEPLOY"}

    def test_calculate_avg_dependencies(self, extractor):
        """Calcula media de dependencias."""
        plan = {
            "plan_id": "test-3",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [
                {"dependencies": ["task1", "task2"]},
                {"dependencies": ["task3"]},
                {"dependencies": []},
            ],
        }

        result = extractor.extract(plan)

        assert result.avg_dependency_count == pytest.approx(1.0)

    def test_complexity_signature_generation(self, extractor):
        """Gera signature de complexidade."""
        plan = {
            "plan_id": "test-4",
            "original_domain": "technical",
            "original_priority": "high",
            "tasks": [
                {"task_type": "BUILD", "estimated_duration_ms": 5000},
                {"task_type": "TEST", "estimated_duration_ms": 2000},
            ],
        }

        result = extractor.extract(plan)

        assert len(result.complexity_signature) > 0
        assert isinstance(result.complexity_signature, str)

    def test_extract_medium_task_count_range(self, extractor):
        """Extrai range MEDIUM para 5-20 tarefas."""
        plan = {
            "plan_id": "test-5",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [{"task_type": "BUILD"} for _ in range(10)],
        }

        result = extractor.extract(plan)

        assert result.task_count_range == TaskCountRange.MEDIUM

    def test_extract_large_task_count_range(self, extractor):
        """Extrai range LARGE para >20 tarefas."""
        plan = {
            "plan_id": "test-6",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [{"task_type": "BUILD"} for _ in range(25)],
        }

        result = extractor.extract(plan)

        assert result.task_count_range == TaskCountRange.LARGE

    def test_extract_empty_task_types(self, extractor):
        """Extrai lista vazia quando sem tarefas."""
        plan = {
            "plan_id": "test-7",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [],
        }

        result = extractor.extract(plan)

        assert result.task_types == []

    def test_extract_has_conditional_dependencies(self, extractor):
        """Detecta dependencias condicionais."""
        plan = {
            "plan_id": "test-8",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [{"dependencies": [{"task": "task1", "condition": "on_success"}]}],
        }

        result = extractor.extract(plan)

        assert result.has_conditional_deps is True

    def test_extract_no_conditional_dependencies(self, extractor):
        """Detecta ausencia de dependencias condicionais."""
        plan = {
            "plan_id": "test-9",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [{"dependencies": ["task1", "task2"]}],
        }

        result = extractor.extract(plan)

        assert result.has_conditional_deps is False

    def test_extract_short_duration_range(self, extractor):
        """Extrai range SHORT para duracao <1s."""
        plan = {
            "plan_id": "test-10",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [
                {"task_type": "BUILD", "estimated_duration_ms": 500},
                {"task_type": "TEST", "estimated_duration_ms": 300},
            ],
        }

        result = extractor.extract(plan)

        assert result.estimated_duration_range == DurationRange.SHORT

    def test_extract_medium_duration_range(self, extractor):
        """Extrai range MEDIUM para duracao 1s-10s."""
        plan = {
            "plan_id": "test-11",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [
                {"task_type": "BUILD", "estimated_duration_ms": 5000},
                {"task_type": "TEST", "estimated_duration_ms": 3000},
            ],
        }

        result = extractor.extract(plan)

        assert result.estimated_duration_range == DurationRange.MEDIUM

    def test_extract_long_duration_range(self, extractor):
        """Extrai range LONG para duracao >10s."""
        plan = {
            "plan_id": "test-12",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [
                {"task_type": "BUILD", "estimated_duration_ms": 15000},
                {"task_type": "TEST", "estimated_duration_ms": 20000},
            ],
        }

        result = extractor.extract(plan)

        assert result.estimated_duration_range == DurationRange.LONG

    def test_extract_unknown_task_type(self, extractor):
        """Lida com task_type ausente (UNKNOWN)."""
        plan = {
            "plan_id": "test-13",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [{"name": "task1"}],  # Sem task_type
        }

        result = extractor.extract(plan)

        assert "UNKNOWN" in result.task_types

    def test_extract_default_values(self, extractor):
        """Usa valores defaults quando campos ausentes."""
        plan = {"plan_id": "test-14", "tasks": []}

        result = extractor.extract(plan)

        assert result.domain == "unknown"
        assert result.priority == "normal"

    def test_extract_zero_dependencies_no_tasks(self, extractor):
        """Retorna 0 dependencias quando sem tarefas."""
        plan = {
            "plan_id": "test-15",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [],
        }

        result = extractor.extract(plan)

        assert result.avg_dependency_count == 0.0

    def test_signature_format(self, extractor):
        """Verifica formato da signature: {domain[0].upper()}-{count[0].upper()}-{hash}."""
        plan = {
            "plan_id": "test-16",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [{"task_type": "BUILD"}],
        }

        result = extractor.extract(plan)

        # Formato: T-S-{4char_hash}
        assert result.complexity_signature.startswith("T-S-")
        assert len(result.complexity_signature) == 8  # "T-S-" (4) + 4 chars hash
