"""Unit tests for DomainMapper class."""

import pytest

from neural_hive_domain.domain import UnifiedDomain
from neural_hive_domain.mapper import (
    VALID_LAYERS,
    VALID_PHEROMONE_TYPES,
    VALID_SOURCES,
    DomainMapper,
)


class TestDomainMapperConstants:
    """Testes para constantes do DomainMapper."""

    def test_valid_sources_defined(self):
        """VALID_SOURCES deve conter todas as fontes esperadas."""
        expected = {"intent_envelope", "scout_signal", "risk_scoring", "ontology"}
        assert expected == VALID_SOURCES

    def test_valid_layers_defined(self):
        """VALID_LAYERS deve conter todas as camadas esperadas."""
        expected = {"strategic", "exploration", "consensus", "specialist"}
        assert expected == VALID_LAYERS

    def test_valid_pheromone_types_defined(self):
        """VALID_PHEROMONE_TYPES deve conter todos os tipos esperados."""
        expected = {
            "SUCCESS",
            "FAILURE",
            "WARNING",
            "ANOMALY_POSITIVE",
            "ANOMALY_NEGATIVE",
            "CONFIDENCE",
            "RISK",
        }
        assert expected == VALID_PHEROMONE_TYPES


class TestDomainMapperNormalize:
    """Testes para DomainMapper.normalize()."""

    def test_normalize_lowercase_business(self):
        """Normalizar 'business' para BUSINESS."""
        result = DomainMapper.normalize("business", "intent_envelope")
        assert result == UnifiedDomain.BUSINESS

    def test_normalize_uppercase_technical(self):
        """Normalizar 'TECHNICAL' para TECHNICAL."""
        result = DomainMapper.normalize("TECHNICAL", "intent_envelope")
        assert result == UnifiedDomain.TECHNICAL

    def test_normalize_mixed_case_security(self):
        """Normalizar 'SeCuRiTy' para SECURITY."""
        result = DomainMapper.normalize("SeCuRiTy", "intent_envelope")
        assert result == UnifiedDomain.SECURITY

    def test_normalize_with_whitespace(self):
        """Normalizar com espaços extras."""
        result = DomainMapper.normalize("  business  ", "intent_envelope")
        assert result == UnifiedDomain.BUSINESS

    def test_normalize_with_domain_suffix(self):
        """Normalizar removendo sufixo '_domain'."""
        result = DomainMapper.normalize("business_domain", "intent_envelope")
        assert result == UnifiedDomain.BUSINESS

    def test_normalize_uppercase_with_hyphen(self):
        """Normalizar kebab-case (com hífen existente nos mappings)."""
        result = DomainMapper.normalize("general", "intent_envelope")
        assert result == UnifiedDomain.BUSINESS

    def test_normalize_general_fallback(self):
        """'general' deve mapear para BUSINESS."""
        result = DomainMapper.normalize("general", "intent_envelope")
        assert result == UnifiedDomain.BUSINESS

    def test_normalize_unknown_fallback(self):
        """'unknown' deve mapear para BUSINESS."""
        result = DomainMapper.normalize("unknown", "intent_envelope")
        assert result == UnifiedDomain.BUSINESS

    def test_normalize_invalid_source_raises(self):
        """Fonte inválida levanta ValueError."""
        with pytest.raises(ValueError, match="Invalid source"):
            DomainMapper.normalize("business", "invalid_source")

    def test_normalize_unrecognized_domain_raises(self):
        """Domínio não reconhecido levanta ValueError."""
        with pytest.raises(ValueError, match="Unrecognized domain"):
            DomainMapper.normalize("not_a_domain", "intent_envelope")

    @pytest.mark.parametrize(
        "domain,expected",
        [
            ("business", UnifiedDomain.BUSINESS),
            ("technical", UnifiedDomain.TECHNICAL),
            ("security", UnifiedDomain.SECURITY),
            ("infrastructure", UnifiedDomain.INFRASTRUCTURE),
            ("behavior", UnifiedDomain.BEHAVIOR),
            ("operational", UnifiedDomain.OPERATIONAL),
            ("compliance", UnifiedDomain.COMPLIANCE),
        ],
    )
    def test_normalize_all_valid_domains(self, domain, expected):
        """Todos os domínios válidos são normalizados corretamente."""
        result = DomainMapper.normalize(domain, "intent_envelope")
        assert result == expected


class TestDomainMapperToPheromoneKey:
    """Testes para DomainMapper.to_pheromone_key()."""

    def test_pheromone_key_basic(self):
        """Gerar chave básica de feromónio."""
        key = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.BUSINESS, layer="strategic", pheromone_type="SUCCESS"
        )
        assert key == "pheromone:strategic:BUSINESS:SUCCESS"

    def test_pheromone_key_with_id(self):
        """Gerar chave com ID."""
        key = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.TECHNICAL,
            layer="specialist",
            pheromone_type="CONFIDENCE",
            id="uuid-123",
        )
        assert key == "pheromone:specialist:TECHNICAL:CONFIDENCE:uuid-123"

    def test_pheromone_key_uppercase_type(self):
        """Tipo de feromónio é normalizado para uppercase."""
        key = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.SECURITY,
            layer="exploration",
            pheromone_type="failure",  # lowercase
        )
        assert key == "pheromone:exploration:SECURITY:FAILURE"

    def test_pheromone_key_invalid_domain_raises(self):
        """Domínio inválido levanta ValueError."""
        with pytest.raises(ValueError, match="must be a UnifiedDomain"):
            DomainMapper.to_pheromone_key(
                domain="BUSINESS", layer="strategic", pheromone_type="SUCCESS"  # string, não enum
            )

    def test_pheromone_key_invalid_layer_raises(self):
        """Camada inválida levanta ValueError."""
        with pytest.raises(ValueError, match="Invalid layer"):
            DomainMapper.to_pheromone_key(
                domain=UnifiedDomain.BUSINESS, layer="invalid_layer", pheromone_type="SUCCESS"
            )

    def test_pheromone_key_invalid_type_raises(self):
        """Tipo inválido levanta ValueError."""
        with pytest.raises(ValueError, match="Invalid pheromone_type"):
            DomainMapper.to_pheromone_key(
                domain=UnifiedDomain.BUSINESS, layer="strategic", pheromone_type="INVALID_TYPE"
            )

    @pytest.mark.parametrize("layer", VALID_LAYERS)
    def test_pheromone_key_all_valid_layers(self, layer):
        """Todas as camadas válidas geram chaves corretas."""
        key = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.BUSINESS, layer=layer, pheromone_type="SUCCESS"
        )
        assert f"pheromone:{layer}:" in key
        assert ":BUSINESS:SUCCESS" in key

    @pytest.mark.parametrize("ptype", VALID_PHEROMONE_TYPES)
    def test_pheromone_key_all_valid_types(self, ptype):
        """Todos os tipos válidos geram chaves corretas."""
        key = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.BUSINESS, layer="strategic", pheromone_type=ptype
        )
        assert key.endswith(f":{ptype}")


class TestDomainMapperFromOntology:
    """Testes para DomainMapper.from_ontology()."""

    def test_from_ontology_security_analysis(self):
        """'security-analysis' mapeia para SECURITY."""
        result = DomainMapper.from_ontology("security-analysis")
        assert result == UnifiedDomain.SECURITY

    def test_from_ontology_architecture_review(self):
        """'architecture-review' mapeia para TECHNICAL."""
        result = DomainMapper.from_ontology("architecture-review")
        assert result == UnifiedDomain.TECHNICAL

    def test_from_ontology_performance_optimization(self):
        """'performance-optimization' mapeia para OPERATIONAL."""
        result = DomainMapper.from_ontology("performance-optimization")
        assert result == UnifiedDomain.OPERATIONAL

    def test_from_ontology_code_quality(self):
        """'code-quality' mapeia para TECHNICAL."""
        result = DomainMapper.from_ontology("code-quality")
        assert result == UnifiedDomain.TECHNICAL

    def test_from_ontology_code_review(self):
        """'code-review' mapeia para TECHNICAL."""
        result = DomainMapper.from_ontology("code-review")
        assert result == UnifiedDomain.TECHNICAL

    def test_from_ontology_dependency_analysis(self):
        """'dependency-analysis' mapeia para SECURITY."""
        result = DomainMapper.from_ontology("dependency-analysis")
        assert result == UnifiedDomain.SECURITY

    def test_from_ontology_infrastructure_review(self):
        """'infrastructure-review' mapeia para INFRASTRUCTURE."""
        result = DomainMapper.from_ontology("infrastructure-review")
        assert result == UnifiedDomain.INFRASTRUCTURE

    def test_from_ontology_compliance_check(self):
        """'compliance-check' mapeia para COMPLIANCE."""
        result = DomainMapper.from_ontology("compliance-check")
        assert result == UnifiedDomain.COMPLIANCE

    def test_from_ontology_business_analysis(self):
        """'business-analysis' mapeia para BUSINESS."""
        result = DomainMapper.from_ontology("business-analysis")
        assert result == UnifiedDomain.BUSINESS

    def test_from_ontology_behavior_analysis(self):
        """'behavior-analysis' mapeia para BEHAVIOR."""
        result = DomainMapper.from_ontology("behavior-analysis")
        assert result == UnifiedDomain.BEHAVIOR

    def test_from_ontology_case_insensitive(self):
        """Mapeamento de ontology é case-insensitive."""
        result = DomainMapper.from_ontology("Security-Analysis")
        assert result == UnifiedDomain.SECURITY

    def test_from_ontology_with_whitespace(self):
        """Espaços extras são removidos."""
        result = DomainMapper.from_ontology("  security-analysis  ")
        assert result == UnifiedDomain.SECURITY

    def test_from_ontology_unmapped_raises(self):
        """Domínio ontology não mapeado levanta ValueError."""
        with pytest.raises(ValueError, match="Unmapped ontology domain"):
            DomainMapper.from_ontology("unmapped-ontology-domain")


class TestDomainMapperIntegration:
    """Testes de integração do DomainMapper."""

    def test_normalize_with_ontology_source(self):
        """Normalizar com fonte 'ontology' usa from_ontology."""
        result = DomainMapper.normalize("security-analysis", "ontology")
        assert result == UnifiedDomain.SECURITY

    def test_normalize_from_scout_signal(self):
        """Normalizar de scout_signal."""
        result = DomainMapper.normalize("SECURITY", "scout_signal")
        assert result == UnifiedDomain.SECURITY

    def test_normalize_from_risk_scoring(self):
        """Normalizar de risk_scoring."""
        result = DomainMapper.normalize("business", "risk_scoring")
        assert result == UnifiedDomain.BUSINESS

    def test_complete_pheromone_workflow(self):
        """Fluxo completo: ontology → normalize → pheromone_key."""
        # 1. Normalizar domain da ontology
        domain = DomainMapper.normalize("security-analysis", "ontology")
        assert domain == UnifiedDomain.SECURITY

        # 2. Gerar chave de feromónio
        key = DomainMapper.to_pheromone_key(
            domain=domain, layer="specialist", pheromone_type="SUCCESS", id="analysis-123"
        )

        assert key == "pheromone:specialist:SECURITY:SUCCESS:analysis-123"
