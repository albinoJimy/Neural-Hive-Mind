"""Tests for UnifiedDomain enum."""

import pytest
from pydantic import BaseModel

from neural_hive_domain import UnifiedDomain


class TestUnifiedDomainValues:
    """Test UnifiedDomain enum values."""

    def test_has_seven_values(self, all_domains):
        """Verify UnifiedDomain has exactly 7 domain values."""
        assert len(all_domains) == 7

    def test_expected_domains_exist(self):
        """Verify all expected domains are defined."""
        expected = [
            'BUSINESS',
            'TECHNICAL',
            'SECURITY',
            'INFRASTRUCTURE',
            'BEHAVIOR',
            'OPERATIONAL',
            'COMPLIANCE',
        ]
        for domain_name in expected:
            assert hasattr(UnifiedDomain, domain_name)
            assert getattr(UnifiedDomain, domain_name).value == domain_name

    def test_all_values_uppercase(self, all_domains):
        """Verify all domain values are uppercase."""
        for domain in all_domains:
            assert domain.value == domain.value.upper()
            assert domain.value.isupper()


class TestUnifiedDomainSerialization:
    """Test UnifiedDomain serialization behavior."""

    def test_string_conversion(self):
        """Verify domains convert to strings correctly."""
        assert str(UnifiedDomain.BUSINESS) == 'BUSINESS'
        assert str(UnifiedDomain.SECURITY) == 'SECURITY'

    def test_string_equality(self):
        """Verify domains are equal to their string values."""
        assert UnifiedDomain.BUSINESS == 'BUSINESS'
        assert UnifiedDomain.TECHNICAL == 'TECHNICAL'

    def test_json_serialization(self):
        """Verify domains serialize to JSON correctly."""
        import json

        domain = UnifiedDomain.SECURITY
        serialized = json.dumps(domain)
        assert serialized == '"SECURITY"'

    def test_json_deserialization(self):
        """Verify domains deserialize from JSON correctly."""
        import json

        value = json.loads('"BUSINESS"')
        domain = UnifiedDomain(value)
        assert domain == UnifiedDomain.BUSINESS


class TestUnifiedDomainPydanticIntegration:
    """Test UnifiedDomain integration with Pydantic models."""

    def test_pydantic_model_field(self):
        """Verify UnifiedDomain works as a Pydantic model field."""

        class TestModel(BaseModel):
            domain: UnifiedDomain

        model = TestModel(domain=UnifiedDomain.TECHNICAL)
        assert model.domain == UnifiedDomain.TECHNICAL

    def test_pydantic_model_from_string(self):
        """Verify Pydantic can construct UnifiedDomain from string."""

        class TestModel(BaseModel):
            domain: UnifiedDomain

        model = TestModel(domain='SECURITY')
        assert model.domain == UnifiedDomain.SECURITY

    def test_pydantic_model_serialization(self):
        """Verify Pydantic model serializes UnifiedDomain correctly."""

        class TestModel(BaseModel):
            domain: UnifiedDomain

        model = TestModel(domain=UnifiedDomain.INFRASTRUCTURE)
        data = model.model_dump()
        assert data['domain'] == 'INFRASTRUCTURE'

    def test_pydantic_model_json_serialization(self):
        """Verify Pydantic model JSON serializes UnifiedDomain correctly."""

        class TestModel(BaseModel):
            domain: UnifiedDomain

        model = TestModel(domain=UnifiedDomain.BEHAVIOR)
        json_str = model.model_dump_json()
        assert '"BEHAVIOR"' in json_str

    def test_pydantic_validation_error_invalid_domain(self):
        """Verify Pydantic raises error for invalid domain."""
        from pydantic import ValidationError

        class TestModel(BaseModel):
            domain: UnifiedDomain

        with pytest.raises(ValidationError):
            TestModel(domain='INVALID_DOMAIN')


class TestUnifiedDomainComparison:
    """Test UnifiedDomain comparison behavior."""

    def test_equality_with_same_domain(self):
        """Verify same domains are equal."""
        assert UnifiedDomain.BUSINESS == UnifiedDomain.BUSINESS

    def test_inequality_with_different_domain(self):
        """Verify different domains are not equal."""
        assert UnifiedDomain.BUSINESS != UnifiedDomain.TECHNICAL

    def test_membership_in_set(self):
        """Verify domains can be used in sets."""
        domain_set = {UnifiedDomain.BUSINESS, UnifiedDomain.SECURITY}
        assert UnifiedDomain.BUSINESS in domain_set
        assert UnifiedDomain.TECHNICAL not in domain_set

    def test_as_dict_key(self):
        """Verify domains can be used as dictionary keys."""
        domain_dict = {
            UnifiedDomain.BUSINESS: 'business_value',
            UnifiedDomain.SECURITY: 'security_value',
        }
        assert domain_dict[UnifiedDomain.BUSINESS] == 'business_value'


class TestUnifiedDomainIteration:
    """Test UnifiedDomain iteration behavior."""

    def test_iteration(self, all_domains):
        """Verify all domains can be iterated."""
        domain_list = list(UnifiedDomain)
        assert len(domain_list) == 7
        assert all(isinstance(d, UnifiedDomain) for d in domain_list)

    def test_contains_check(self):
        """Verify membership check works correctly."""
        assert 'BUSINESS' in [d.value for d in UnifiedDomain]
        assert 'INVALID' not in [d.value for d in UnifiedDomain]
