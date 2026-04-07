"""
Testes unitários para o modelo de senioridade.
"""

import pytest
from src.models.seniority import (
    SeniorityLevel,
    SENIORITY_MULTIPLIERS,
    SENIORITY_DESCRIPTIONS,
    SENIORITY_ORDER,
    get_seniority_multiplier,
    get_seniority_description,
    parse_seniority_level,
    compare_seniority,
)


class TestSeniorityLevel:
    """Testes do enum SeniorityLevel."""

    def test_all_levels_defined(self):
        """Verifica que todos os níveis esperados estão definidos."""
        expected = {"trainee", "junior", "mid_level", "senior", "expert"}
        actual = {level.value for level in SeniorityLevel}
        assert actual == expected

    def test_level_values_correct(self):
        """Verifica valores dos níveis."""
        assert SeniorityLevel.TRAINEE.value == "trainee"
        assert SeniorityLevel.JUNIOR.value == "junior"
        assert SeniorityLevel.MID_LEVEL.value == "mid_level"
        assert SeniorityLevel.SENIOR.value == "senior"
        assert SeniorityLevel.EXPERT.value == "expert"


class TestSeniorityMultipliers:
    """Testes dos multiplicadores de senioridade."""

    def test_trainee_has_half_weight(self):
        """Trainee deve ter 0.5x o peso base."""
        assert SENIORITY_MULTIPLIERS[SeniorityLevel.TRAINEE] == 0.5

    def test_junior_has_75_percent_weight(self):
        """Junior deve ter 0.75x o peso base."""
        assert SENIORITY_MULTIPLIERS[SeniorityLevel.JUNIOR] == 0.75

    def test_mid_level_has_base_weight(self):
        """Mid level deve ter 1.0x o peso base."""
        assert SENIORITY_MULTIPLIERS[SeniorityLevel.MID_LEVEL] == 1.0

    def test_senior_has_50_percent_more_weight(self):
        """Senior deve ter 1.5x o peso base."""
        assert SENIORITY_MULTIPLIERS[SeniorityLevel.SENIOR] == 1.5

    def test_expert_has_double_weight(self):
        """Expert deve ter 2.0x o peso base."""
        assert SENIORITY_MULTIPLIERS[SeniorityLevel.EXPERT] == 2.0

    def test_multipliers_increasing_order(self):
        """Multiplicadores devem ser crescentes."""
        multipliers = [
            SENIORITY_MULTIPLIERS[SeniorityLevel.TRAINEE],
            SENIORITY_MULTIPLIERS[SeniorityLevel.JUNIOR],
            SENIORITY_MULTIPLIERS[SeniorityLevel.MID_LEVEL],
            SENIORITY_MULTIPLIERS[SeniorityLevel.SENIOR],
            SENIORITY_MULTIPLIERS[SeniorityLevel.EXPERT],
        ]
        assert multipliers == sorted(multipliers)


class TestGetSeniorityMultiplier:
    """Testes da função get_seniority_multiplier."""

    def test_returns_correct_multiplier(self):
        """Deve retornar multiplicador correto para cada nível."""
        assert get_seniority_multiplier(SeniorityLevel.TRAINEE) == 0.5
        assert get_seniority_multiplier(SeniorityLevel.JUNIOR) == 0.75
        assert get_seniority_multiplier(SeniorityLevel.MID_LEVEL) == 1.0
        assert get_seniority_multiplier(SeniorityLevel.SENIOR) == 1.5
        assert get_seniority_multiplier(SeniorityLevel.EXPERT) == 2.0

    def test_raises_on_invalid_level(self):
        """Deve levantar ValueError para nível inválido."""
        with pytest.raises(ValueError):
            get_seniority_multiplier("invalid_level")


class TestSeniorityDescriptions:
    """Testes das descrições de senioridade."""

    def test_all_levels_have_descriptions(self):
        """Todos os níveis devem ter descrição."""
        for level in SeniorityLevel:
            assert level in SENIORITY_DESCRIPTIONS
            assert isinstance(SENIORITY_DESCRIPTIONS[level], str)
            assert len(SENIORITY_DESCRIPTIONS[level]) > 0


class TestGetSeniorityDescription:
    """Testes da função get_seniority_description."""

    def test_returns_description(self):
        """Deve retornar descrição do nível."""
        desc = get_seniority_description(SeniorityLevel.SENIOR)
        assert "avançada" in desc.lower()


class TestParseSeniorityLevel:
    """Testes da função parse_seniority_level."""

    @pytest.mark.parametrize(
        "input_str,expected",
        [
            ("trainee", SeniorityLevel.TRAINEE),
            ("TRAINEE", SeniorityLevel.TRAINEE),
            ("Trainee", SeniorityLevel.TRAINEE),
            ("senior", SeniorityLevel.SENIOR),
            ("expert", SeniorityLevel.EXPERT),
        ],
    )
    def test_parse_valid_strings(self, input_str, expected):
        """Deve fazer parse de strings válidas (case-insensitive)."""
        assert parse_seniority_level(input_str) == expected

    def test_raises_on_invalid_string(self):
        """Deve levantar ValueError para string inválida."""
        with pytest.raises(ValueError, match="Invalid seniority level"):
            parse_seniority_level("invalid")


class TestCompareSeniority:
    """Testes da função compare_seniority."""

    def test_trainee_less_than_senior(self):
        """Trainee deve ser menor que senior."""
        assert compare_seniority(SeniorityLevel.TRAINEE, SeniorityLevel.SENIOR) == -1

    def test_senior_greater_than_junior(self):
        """Senior deve ser maior que junior."""
        assert compare_seniority(SeniorityLevel.SENIOR, SeniorityLevel.JUNIOR) == 1

    def test_equal_levels(self):
        """Níveis iguais devem retornar 0."""
        assert compare_seniority(SeniorityLevel.MID_LEVEL, SeniorityLevel.MID_LEVEL) == 0

    def test_order_matches_enum_order(self):
        """Ordem de comparação deve bater com SENIORITY_ORDER."""
        for i in range(len(SENIORITY_ORDER) - 1):
            level1 = SENIORITY_ORDER[i]
            level2 = SENIORITY_ORDER[i + 1]
            assert compare_seniority(level1, level2) == -1
            assert compare_seniority(level2, level1) == 1


class TestSeniorityOrder:
    """Testes da lista SENIORITY_ORDER."""

    def test_order_is_ascending(self):
        """Ordem deve ser crescente (do menos ao mais experiente)."""
        assert SENIORITY_ORDER[0] == SeniorityLevel.TRAINEE
        assert SENIORITY_ORDER[-1] == SeniorityLevel.EXPERT

    def test_all_levels_included(self):
        """Todos os níveis devem estar na ordem."""
        assert set(SENIORITY_ORDER) == set(SeniorityLevel)
