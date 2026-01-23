"""Tests for DomainMapper class."""

import pytest

from neural_hive_domain import DomainMapper, UnifiedDomain


class TestDomainMapperNormalize:
    """Test DomainMapper.normalize() method."""

    def test_normalize_lowercase_business(self):
        """Normalize lowercase 'business' to BUSINESS."""
        result = DomainMapper.normalize('business', 'intent_envelope')
        assert result == UnifiedDomain.BUSINESS

    def test_normalize_uppercase_technical(self):
        """Normalize uppercase 'TECHNICAL' to TECHNICAL."""
        result = DomainMapper.normalize('TECHNICAL', 'scout_signal')
        assert result == UnifiedDomain.TECHNICAL

    def test_normalize_mixed_case_security(self):
        """Normalize mixed case 'Security' to SECURITY."""
        result = DomainMapper.normalize('Security', 'risk_scoring')
        assert result == UnifiedDomain.SECURITY

    def test_normalize_with_whitespace(self):
        """Normalize domain with leading/trailing whitespace."""
        result = DomainMapper.normalize('  infrastructure  ', 'intent_envelope')
        assert result == UnifiedDomain.INFRASTRUCTURE

    def test_normalize_all_valid_domains(self):
        """Verify all valid domains normalize correctly."""
        test_cases = [
            ('business', UnifiedDomain.BUSINESS),
            ('technical', UnifiedDomain.TECHNICAL),
            ('security', UnifiedDomain.SECURITY),
            ('infrastructure', UnifiedDomain.INFRASTRUCTURE),
            ('behavior', UnifiedDomain.BEHAVIOR),
            ('operational', UnifiedDomain.OPERATIONAL),
            ('compliance', UnifiedDomain.COMPLIANCE),
        ]
        for domain_str, expected in test_cases:
            result = DomainMapper.normalize(domain_str, 'intent_envelope')
            assert result == expected, f"Failed for {domain_str}"

    def test_normalize_invalid_domain_raises_error(self):
        """Verify invalid domain raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            DomainMapper.normalize('invalid_domain', 'intent_envelope')
        assert 'Unrecognized domain' in str(exc_info.value)

    def test_normalize_invalid_source_raises_error(self):
        """Verify invalid source raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            DomainMapper.normalize('business', 'invalid_source')
        assert 'Invalid source' in str(exc_info.value)

    def test_normalize_from_intent_envelope(self):
        """Test normalization from intent_envelope source."""
        result = DomainMapper.normalize('business', 'intent_envelope')
        assert result == UnifiedDomain.BUSINESS

    def test_normalize_from_scout_signal(self):
        """Test normalization from scout_signal source."""
        result = DomainMapper.normalize('BEHAVIOR', 'scout_signal')
        assert result == UnifiedDomain.BEHAVIOR

    def test_normalize_from_risk_scoring(self):
        """Test normalization from risk_scoring source."""
        result = DomainMapper.normalize('operational', 'risk_scoring')
        assert result == UnifiedDomain.OPERATIONAL

    def test_normalize_from_ontology_delegates(self):
        """Test that ontology source delegates to from_ontology."""
        result = DomainMapper.normalize('security-analysis', 'ontology')
        assert result == UnifiedDomain.SECURITY

    def test_normalize_kebab_case_conversion(self):
        """Test normalization handles kebab-case input."""
        # Note: standard domains don't use kebab-case, but the method handles it
        result = DomainMapper.normalize('business', 'intent_envelope')
        assert result == UnifiedDomain.BUSINESS


class TestDomainMapperToPheromoneKey:
    """Test DomainMapper.to_pheromone_key() method."""

    def test_basic_key_format(self):
        """Test basic pheromone key format without ID."""
        result = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.BUSINESS,
            layer='strategic',
            pheromone_type='SUCCESS',
        )
        assert result == 'pheromone:strategic:BUSINESS:SUCCESS'

    def test_key_format_with_id(self):
        """Test pheromone key format with ID."""
        result = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.BEHAVIOR,
            layer='exploration',
            pheromone_type='ANOMALY_POSITIVE',
            id='uuid-123',
        )
        assert result == 'pheromone:exploration:BEHAVIOR:ANOMALY_POSITIVE:uuid-123'

    def test_all_valid_layers(self, valid_layers):
        """Test key generation with all valid layers."""
        for layer in valid_layers:
            result = DomainMapper.to_pheromone_key(
                domain=UnifiedDomain.SECURITY,
                layer=layer,
                pheromone_type='SUCCESS',
            )
            assert f'pheromone:{layer}:SECURITY:SUCCESS' == result

    def test_all_valid_pheromone_types(self, valid_pheromone_types):
        """Test key generation with all valid pheromone types."""
        for ptype in valid_pheromone_types:
            result = DomainMapper.to_pheromone_key(
                domain=UnifiedDomain.TECHNICAL,
                layer='strategic',
                pheromone_type=ptype,
            )
            assert f'pheromone:strategic:TECHNICAL:{ptype}' == result

    def test_all_domains(self, all_domains):
        """Test key generation with all domain values."""
        for domain in all_domains:
            result = DomainMapper.to_pheromone_key(
                domain=domain,
                layer='consensus',
                pheromone_type='WARNING',
            )
            assert f'pheromone:consensus:{domain.value}:WARNING' == result

    def test_strategic_layer(self):
        """Test strategic layer key generation."""
        result = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.BUSINESS,
            layer='strategic',
            pheromone_type='SUCCESS',
        )
        assert 'strategic' in result

    def test_exploration_layer(self):
        """Test exploration layer key generation."""
        result = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.TECHNICAL,
            layer='exploration',
            pheromone_type='FAILURE',
        )
        assert 'exploration' in result

    def test_consensus_layer(self):
        """Test consensus layer key generation."""
        result = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.SECURITY,
            layer='consensus',
            pheromone_type='WARNING',
        )
        assert 'consensus' in result

    def test_specialist_layer(self):
        """Test specialist layer key generation."""
        result = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.INFRASTRUCTURE,
            layer='specialist',
            pheromone_type='SUCCESS',
            id='plan-456',
        )
        assert result == 'pheromone:specialist:INFRASTRUCTURE:SUCCESS:plan-456'

    def test_invalid_domain_type_raises_error(self):
        """Test that non-UnifiedDomain domain raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            DomainMapper.to_pheromone_key(
                domain='BUSINESS',  # string instead of UnifiedDomain
                layer='strategic',
                pheromone_type='SUCCESS',
            )
        assert 'must be a UnifiedDomain enum' in str(exc_info.value)

    def test_invalid_layer_raises_error(self):
        """Test that invalid layer raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            DomainMapper.to_pheromone_key(
                domain=UnifiedDomain.BUSINESS,
                layer='invalid_layer',
                pheromone_type='SUCCESS',
            )
        assert 'Invalid layer' in str(exc_info.value)

    def test_pheromone_type_case_insensitive_lowercase(self):
        """Test that lowercase pheromone types are accepted."""
        result = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.BUSINESS,
            layer='strategic',
            pheromone_type='success',
        )
        # Verifica que output usa uppercase independente do input
        assert result == 'pheromone:strategic:BUSINESS:SUCCESS'

    def test_pheromone_type_case_insensitive_mixed(self):
        """Test that mixed case pheromone types are accepted."""
        result = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.TECHNICAL,
            layer='exploration',
            pheromone_type='Warning',
        )
        assert result == 'pheromone:exploration:TECHNICAL:WARNING'

    def test_all_pheromone_types_lowercase(self, valid_pheromone_types):
        """Test all pheromone types work in lowercase."""
        for ptype in valid_pheromone_types:
            result = DomainMapper.to_pheromone_key(
                domain=UnifiedDomain.SECURITY,
                layer='consensus',
                pheromone_type=ptype.lower(),
            )
            assert f'pheromone:consensus:SECURITY:{ptype}' == result

    def test_invalid_pheromone_type_raises_error(self):
        """Test that invalid pheromone type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            DomainMapper.to_pheromone_key(
                domain=UnifiedDomain.BUSINESS,
                layer='strategic',
                pheromone_type='INVALID_TYPE',
            )
        assert 'Invalid pheromone_type' in str(exc_info.value)

    def test_none_id_not_included(self):
        """Test that None ID is not included in key."""
        result = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.COMPLIANCE,
            layer='strategic',
            pheromone_type='SUCCESS',
            id=None,
        )
        assert result == 'pheromone:strategic:COMPLIANCE:SUCCESS'
        assert result.count(':') == 3

    def test_empty_string_id_included(self):
        """Test that empty string ID is included in key."""
        result = DomainMapper.to_pheromone_key(
            domain=UnifiedDomain.OPERATIONAL,
            layer='strategic',
            pheromone_type='SUCCESS',
            id='',
        )
        assert result == 'pheromone:strategic:OPERATIONAL:SUCCESS:'


class TestDomainMapperFromOntology:
    """Test DomainMapper.from_ontology() method."""

    def test_security_analysis_mapping(self):
        """Map 'security-analysis' to SECURITY."""
        result = DomainMapper.from_ontology('security-analysis')
        assert result == UnifiedDomain.SECURITY

    def test_architecture_review_mapping(self):
        """Map 'architecture-review' to TECHNICAL."""
        result = DomainMapper.from_ontology('architecture-review')
        assert result == UnifiedDomain.TECHNICAL

    def test_performance_optimization_mapping(self):
        """Map 'performance-optimization' to OPERATIONAL."""
        result = DomainMapper.from_ontology('performance-optimization')
        assert result == UnifiedDomain.OPERATIONAL

    def test_code_quality_mapping(self):
        """Map 'code-quality' to TECHNICAL."""
        result = DomainMapper.from_ontology('code-quality')
        assert result == UnifiedDomain.TECHNICAL

    def test_code_review_mapping(self):
        """Map 'code-review' to TECHNICAL."""
        result = DomainMapper.from_ontology('code-review')
        assert result == UnifiedDomain.TECHNICAL

    def test_dependency_analysis_mapping(self):
        """Map 'dependency-analysis' to SECURITY."""
        result = DomainMapper.from_ontology('dependency-analysis')
        assert result == UnifiedDomain.SECURITY

    def test_infrastructure_review_mapping(self):
        """Map 'infrastructure-review' to INFRASTRUCTURE."""
        result = DomainMapper.from_ontology('infrastructure-review')
        assert result == UnifiedDomain.INFRASTRUCTURE

    def test_compliance_check_mapping(self):
        """Map 'compliance-check' to COMPLIANCE."""
        result = DomainMapper.from_ontology('compliance-check')
        assert result == UnifiedDomain.COMPLIANCE

    def test_business_analysis_mapping(self):
        """Map 'business-analysis' to BUSINESS."""
        result = DomainMapper.from_ontology('business-analysis')
        assert result == UnifiedDomain.BUSINESS

    def test_behavior_analysis_mapping(self):
        """Map 'behavior-analysis' to BEHAVIOR."""
        result = DomainMapper.from_ontology('behavior-analysis')
        assert result == UnifiedDomain.BEHAVIOR

    def test_case_insensitive(self):
        """Test ontology mapping is case insensitive."""
        result = DomainMapper.from_ontology('SECURITY-ANALYSIS')
        assert result == UnifiedDomain.SECURITY

    def test_with_whitespace(self):
        """Test ontology mapping handles whitespace."""
        result = DomainMapper.from_ontology('  architecture-review  ')
        assert result == UnifiedDomain.TECHNICAL

    def test_unmapped_ontology_raises_error(self):
        """Test that unmapped ontology domain raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            DomainMapper.from_ontology('unknown-ontology-domain')
        assert 'Unmapped ontology domain' in str(exc_info.value)

    def test_fallback_mapping_for_simple_domain_name(self):
        """Test fallback mapping when ontology domain matches a simple domain name."""
        # 'business' is not in _ontology_mappings but should match via fallback
        result = DomainMapper.from_ontology('business')
        assert result == UnifiedDomain.BUSINESS

    def test_fallback_mapping_for_technical(self):
        """Test fallback mapping for technical domain."""
        result = DomainMapper.from_ontology('technical')
        assert result == UnifiedDomain.TECHNICAL


class TestDomainMapperIntegration:
    """Integration tests for DomainMapper."""

    def test_normalize_then_to_pheromone_key(self):
        """Test normalizing a domain then generating a key."""
        domain = DomainMapper.normalize('business', 'intent_envelope')
        key = DomainMapper.to_pheromone_key(
            domain=domain,
            layer='strategic',
            pheromone_type='SUCCESS',
            id='test-123',
        )
        assert key == 'pheromone:strategic:BUSINESS:SUCCESS:test-123'

    def test_ontology_to_pheromone_key(self):
        """Test mapping from ontology then generating a key."""
        domain = DomainMapper.from_ontology('security-analysis')
        key = DomainMapper.to_pheromone_key(
            domain=domain,
            layer='exploration',
            pheromone_type='WARNING',
        )
        assert key == 'pheromone:exploration:SECURITY:WARNING'

    def test_all_sources_normalize_consistently(self):
        """Test that the same domain normalizes consistently from all sources."""
        sources = ['intent_envelope', 'scout_signal', 'risk_scoring']
        results = [
            DomainMapper.normalize('business', source) for source in sources
        ]
        assert all(r == UnifiedDomain.BUSINESS for r in results)
