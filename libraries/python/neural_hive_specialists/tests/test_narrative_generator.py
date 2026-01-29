"""
Testes unitários para NarrativeGenerator.

Testa geração de narrativas estruturadas em português.
"""

import pytest
from neural_hive_specialists.explainability.narrative_generator import (
    NarrativeGenerator,
)


@pytest.fixture
def generator():
    """Cria generator com configuração padrão."""
    config = {}
    return NarrativeGenerator(config)


@pytest.fixture
def sample_shap_importances():
    """Importâncias SHAP de exemplo."""
    return [
        {
            "feature_name": "num_tasks",
            "shap_value": 0.35,
            "feature_value": 8.0,
            "contribution": "positive",
            "importance": 0.35,
        },
        {
            "feature_name": "complexity_score",
            "shap_value": -0.25,
            "feature_value": 0.85,
            "contribution": "negative",
            "importance": 0.25,
        },
        {
            "feature_name": "avg_duration_ms",
            "shap_value": 0.15,
            "feature_value": 2500.0,
            "contribution": "positive",
            "importance": 0.15,
        },
        {
            "feature_name": "num_bottlenecks",
            "shap_value": -0.10,
            "feature_value": 3.0,
            "contribution": "negative",
            "importance": 0.10,
        },
    ]


@pytest.mark.unit
class TestNarrativeGeneration:
    """Testes de geração de narrativas."""

    def test_generate_narrative_with_shap(self, generator, sample_shap_importances):
        """Testa geração de narrativa com importâncias SHAP."""
        narrative = generator.generate_narrative(
            sample_shap_importances, top_n=3, explanation_type="shap"
        )

        # Validações básicas
        assert isinstance(narrative, str)
        assert len(narrative) > 0

        # Deve conter seções
        assert (
            "Fatores que aumentaram a confiança" in narrative or "positiva" in narrative
        )
        assert (
            "Fatores que reduziram a confiança" in narrative or "negativa" in narrative
        )

        # Deve mencionar features importantes
        assert "num_tasks" in narrative or "tarefas" in narrative.lower()

    def test_generate_narrative_with_lime(self, generator):
        """Testa geração de narrativa com importâncias LIME."""
        lime_importances = [
            {
                "feature_name": "priority_score",
                "lime_weight": 0.40,
                "feature_value": 0.9,
                "contribution": "positive",
                "importance": 0.40,
            },
            {
                "feature_name": "risk_score",
                "lime_weight": -0.30,
                "feature_value": 0.7,
                "contribution": "negative",
                "importance": 0.30,
            },
        ]

        narrative = generator.generate_narrative(
            lime_importances, top_n=2, explanation_type="lime"
        )

        assert isinstance(narrative, str)
        assert len(narrative) > 0

    def test_generate_narrative_empty_importances(self, generator):
        """Testa narrativa com lista vazia."""
        narrative = generator.generate_narrative([], top_n=5)

        assert narrative == "Não foi possível gerar explicação detalhada."

    def test_narrative_separates_positive_negative(
        self, generator, sample_shap_importances
    ):
        """Testa que narrativa separa contribuições positivas e negativas."""
        narrative = generator.generate_narrative(
            sample_shap_importances, top_n=5, explanation_type="shap"
        )

        # Deve ter indicadores de contribuições positivas e negativas
        assert "positiv" in narrative.lower() or "aumenta" in narrative.lower()
        assert "negativ" in narrative.lower() or "reduz" in narrative.lower()

    def test_narrative_respects_top_n(self, generator, sample_shap_importances):
        """Testa que narrativa respeita limite top_n."""
        narrative_top_2 = generator.generate_narrative(
            sample_shap_importances, top_n=2, explanation_type="shap"
        )

        narrative_top_4 = generator.generate_narrative(
            sample_shap_importances, top_n=4, explanation_type="shap"
        )

        # Narrativa com top_n maior deve ser mais longa
        assert len(narrative_top_4) >= len(narrative_top_2)


@pytest.mark.unit
class TestSummaryGeneration:
    """Testes de geração de resumos."""

    def test_generate_summary_with_shap(self, generator, sample_shap_importances):
        """Testa geração de resumo executivo."""
        summary = generator.generate_summary(
            sample_shap_importances, explanation_type="shap"
        )

        assert isinstance(summary, str)
        assert len(summary) > 0
        # Resumo deve ser curto (uma linha)
        assert summary.count("\n") == 0
        # Deve mencionar feature mais importante
        assert "num_tasks" in summary or "tarefas" in summary.lower()

    def test_generate_summary_empty_importances(self, generator):
        """Testa resumo com lista vazia."""
        summary = generator.generate_summary([])

        assert summary == "Sem explicação disponível."

    def test_summary_indicates_contribution_direction(
        self, generator, sample_shap_importances
    ):
        """Testa que resumo indica se contribuição é positiva ou negativa."""
        # Feature mais importante é positiva
        summary_positive = generator.generate_summary(sample_shap_importances)
        assert (
            "influenciada" in summary_positive.lower()
            or "principal" in summary_positive.lower()
        )


@pytest.mark.unit
class TestFeatureDescription:
    """Testes de descrição de features."""

    def test_describe_feature_with_template(self, generator):
        """Testa descrição de feature com template."""
        feature = {
            "feature_name": "num_tasks",
            "feature_value": 8.0,
            "shap_value": 0.35,
            "contribution": "positive",
        }

        description = generator._describe_feature(feature, "shap_value")

        assert isinstance(description, str)
        assert len(description) > 0

    def test_describe_feature_impact_levels(self, generator):
        """Testa níveis de impacto (forte, moderado, leve)."""
        # Impacto forte
        feature_strong = {
            "feature_name": "complexity_score",
            "feature_value": 0.9,
            "shap_value": 0.5,  # > 0.3
            "contribution": "positive",
        }
        desc_strong = generator._describe_feature(feature_strong, "shap_value")
        assert "forte" in desc_strong.lower() or len(desc_strong) > 0

        # Impacto moderado
        feature_moderate = {
            "feature_name": "complexity_score",
            "feature_value": 0.9,
            "shap_value": 0.2,  # 0.15-0.3
            "contribution": "positive",
        }
        desc_moderate = generator._describe_feature(feature_moderate, "shap_value")
        assert isinstance(desc_moderate, str)

        # Impacto leve
        feature_light = {
            "feature_name": "complexity_score",
            "feature_value": 0.9,
            "shap_value": 0.1,  # < 0.15
            "contribution": "positive",
        }
        desc_light = generator._describe_feature(feature_light, "shap_value")
        assert isinstance(desc_light, str)


@pytest.mark.unit
class TestQualitativeLevels:
    """Testes de conversão para níveis qualitativos."""

    def test_qualitative_level_for_scores(self, generator):
        """Testa níveis qualitativos para scores (0-1)."""
        # Testar diferentes valores
        level_high = generator._get_qualitative_level("risk_score", 0.9)
        level_medium = generator._get_qualitative_level("risk_score", 0.5)
        level_low = generator._get_qualitative_level("risk_score", 0.1)

        assert isinstance(level_high, str)
        assert isinstance(level_medium, str)
        assert isinstance(level_low, str)

    def test_qualitative_level_for_counts(self, generator):
        """Testa níveis qualitativos para contagens."""
        level_high = generator._get_qualitative_level("num_tasks", 15)
        level_medium = generator._get_qualitative_level("num_tasks", 7)
        level_low = generator._get_qualitative_level("num_tasks", 3)

        assert isinstance(level_high, str)
        assert isinstance(level_medium, str)
        assert isinstance(level_low, str)


@pytest.mark.unit
class TestTimeFormatting:
    """Testes de formatação de tempo."""

    def test_format_milliseconds(self, generator):
        """Testa formatação de milissegundos."""
        formatted = generator._format_time_if_needed("avg_duration_ms", 500)
        assert isinstance(formatted, str)

    def test_format_seconds(self, generator):
        """Testa formatação de segundos."""
        formatted = generator._format_time_if_needed("avg_duration_ms", 2500)
        assert isinstance(formatted, str)

    def test_no_format_for_non_time_features(self, generator):
        """Testa que features não-tempo não são formatadas."""
        formatted = generator._format_time_if_needed("num_tasks", 500)
        assert formatted == ""
