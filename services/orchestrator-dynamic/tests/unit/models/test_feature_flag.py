"""
Testes unitários para FeatureFlag models.

Cobertura:
- FeatureFlag model (criação, validação, serialização)
- RolloutStrategy e seus subtipos
- Conditions (WhitelistCondition, PercentageCondition, AttributeCondition)
- Operações de enable/disable
- Validações de enums e campos obrigatórios
"""
from datetime import datetime
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from src.models.feature_flag import (
    AttributeCondition,
    ConditionType,
    FeatureFlag,
    OperatorType,
    PercentageCondition,
    RolloutStrategy,
    RolloutType,
    WhitelistCondition,
)


class TestFeatureFlag:
    """Testes para FeatureFlag model."""

    def test_create_minimal_feature_flag(self):
        """Testa criação de flag com campos mínimos."""
        flag = FeatureFlag(
            name="test_feature",
            description="Test feature flag",
            enabled=True,
        )

        assert flag.name == "test_feature"
        assert flag.description == "Test feature flag"
        assert flag.enabled is True
        assert flag.rollout_strategy.type == RolloutType.IMMEDIATE
        assert isinstance(flag.created_at, datetime)
        assert isinstance(flag.updated_at, datetime)

    def test_create_feature_flag_with_all_fields(self):
        """Testa criação de flag com todos os campos."""
        strategy = RolloutStrategy(
            type=RolloutType.GRADUAL,
            percentage=50,
            whitelist=["tenant-123", "tenant-456"],
        )

        flag = FeatureFlag(
            name="complex_feature",
            description="Complex feature flag",
            enabled=False,
            rollout_strategy=strategy,
            owner="platform-team",
            tags=["experiment", "q1-2026"],
        )

        assert flag.name == "complex_feature"
        assert flag.enabled is False
        assert flag.rollout_strategy.type == RolloutType.GRADUAL
        assert flag.rollout_strategy.percentage == 50
        assert flag.owner == "platform-team"
        assert "experiment" in flag.tags

    def test_feature_flag_enable_disable(self):
        """Testa métodos de enable/disable."""
        flag = FeatureFlag(name="test", description="test", enabled=False)

        assert flag.enabled is False

        flag.enable()
        assert flag.enabled is True

        flag.disable()
        assert flag.enabled is False

    def test_enable_updates_timestamp(self):
        """Testa que enable() atualiza updated_at."""
        flag = FeatureFlag(name="test", description="test", enabled=False)
        original_updated_at = flag.updated_at

        import time

        time.sleep(0.01)  # Pequena garantia de diferença de tempo
        flag.enable()

        assert flag.updated_at > original_updated_at

    def test_to_dict_serialization(self):
        """Testa serialização para dicionário."""
        flag = FeatureFlag(
            name="test_feature",
            description="Test",
            enabled=True,
            owner="test-owner",
            tags=["tag1", "tag2"],
        )

        data = flag.to_dict()

        assert data["name"] == "test_feature"
        assert data["enabled"] is True
        assert data["owner"] == "test-owner"
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)

    def test_from_dict_deserialization(self):
        """Testa desserialização de dicionário."""
        data = {
            "name": "test_feature",
            "description": "Test",
            "enabled": True,
            "rollout_strategy": {"type": "immediate"},
            "owner": "test-owner",
            "tags": ["tag1"],
        }

        flag = FeatureFlag.from_dict(data)

        assert flag.name == "test_feature"
        assert flag.enabled is True
        assert flag.owner == "test-owner"

    def test_name_required(self):
        """Testa que name é obrigatório."""
        with pytest.raises(ValidationError) as exc_info:
            FeatureFlag(description="test", enabled=True)

        assert "name" in str(exc_info.value).lower()

    def test_enabled_defaults_to_false(self):
        """Testa valor default de enabled."""
        flag = FeatureFlag(name="test", description="test")

        assert flag.enabled is False


class TestRolloutStrategy:
    """Testes para RolloutStrategy."""

    def test_default_immediate_strategy(self):
        """Testa estratégia default (immediate)."""
        strategy = RolloutStrategy()

        assert strategy.type == RolloutType.IMMEDIATE
        assert strategy.percentage == 100
        assert strategy.whitelist == []

    def test_gradual_strategy_with_percentage(self):
        """Testa estratégia gradual com percentagem."""
        strategy = RolloutStrategy(type=RolloutType.GRADUAL, percentage=30)

        assert strategy.type == RolloutType.GRADUAL
        assert strategy.percentage == 30

    def test_cannotary_strategy_with_whitelist(self):
        """Testa estratégia canary com whitelist."""
        strategy = RolloutStrategy(
            type=RolloutType.CANARY, whitelist=["tenant-1", "tenant-2"]
        )

        assert strategy.type == RolloutType.CANARY
        assert len(strategy.whitelist) == 2

    def test_percentage_validation_range(self):
        """Testa validação de percentage (0-100)."""
        with pytest.raises(ValidationError):
            RolloutStrategy(type=RolloutType.GRADUAL, percentage=150)

        with pytest.raises(ValidationError):
            RolloutStrategy(type=RolloutType.GRADUAL, percentage=-10)

    def test_percentage_defaults_to_100(self):
        """Testa valor default de percentage."""
        strategy = RolloutStrategy(type=RolloutType.GRADUAL)

        assert strategy.percentage == 100


class TestWhitelistCondition:
    """Testes para WhitelistCondition."""

    def test_create_whitelist_condition(self):
        """Testa criação de condição de whitelist."""
        condition = WhitelistCondition(
            type=ConditionType.WHITELIST, values=["user-1", "user-2"]
        )

        assert condition.type == ConditionType.WHITELIST
        assert condition.values == ["user-1", "user-2"]

    def test_evaluate_match_in_whitelist(self):
        """Testa avaliação quando valor está na whitelist."""
        condition = WhitelistCondition(
            type=ConditionType.WHITELIST, values=["tenant-123", "tenant-456"]
        )

        assert condition.evaluate("tenant-123", {}) is True
        assert condition.evaluate("tenant-999", {}) is False

    def test_evaluate_with_context_attribute(self):
        """Testa avaliação usando atributo do contexto."""
        condition = WhitelistCondition(
            type=ConditionType.WHITELIST,
            values=["user-1"],
            attribute="user_id",
        )

        context = {"user_id": "user-1"}
        assert condition.evaluate(None, context) is True

        context = {"user_id": "user-2"}
        assert condition.evaluate(None, context) is False


class TestPercentageCondition:
    """Testes para PercentageCondition."""

    def test_create_percentage_condition(self):
        """Testa criação de condição percentual."""
        condition = PercentageCondition(type=ConditionType.PERCENTAGE, percentage=50)

        assert condition.type == ConditionType.PERCENTAGE
        assert condition.percentage == 50

    def test_evaluate_deterministic_hashing(self):
        """Testa avaliação determinística baseada em hash."""
        condition = PercentageCondition(
            type=ConditionType.PERCENTAGE, percentage=50
        )

        # Para mesma chave, resultado deve ser consistente
        result1 = condition.evaluate("test-key", {})
        result2 = condition.evaluate("test-key", {})

        assert result1 == result2

    def test_evaluate_respects_percentage(self):
        """Testa que avaliação respeita a percentagem configurada."""
        condition = PercentageCondition(
            type=ConditionType.PERCENTAGE, percentage=100
        )

        # 100% deve sempre retornar True
        assert condition.evaluate("any-key", {}) is True

        condition = PercentageCondition(
            type=ConditionType.PERCENTAGE, percentage=0
        )

        # 0% deve sempre retornar False
        assert condition.evaluate("any-key", {}) is False


class TestAttributeCondition:
    """Testes para AttributeCondition."""

    def test_create_attribute_condition(self):
        """Testa criação de condição baseada em atributo."""
        condition = AttributeCondition(
            type=ConditionType.ATTRIBUTE,
            attribute="namespace",
            operator=OperatorType.EQUALS,
            value="staging",
        )

        assert condition.type == ConditionType.ATTRIBUTE
        assert condition.attribute == "namespace"
        assert condition.operator == OperatorType.EQUALS
        assert condition.value == "staging"

    def test_evaluate_equals_operator(self):
        """Testa operador EQUALS."""
        condition = AttributeCondition(
            type=ConditionType.ATTRIBUTE,
            attribute="environment",
            operator=OperatorType.EQUALS,
            value="production",
        )

        context = {"environment": "production"}
        assert condition.evaluate(None, context) is True

        context = {"environment": "staging"}
        assert condition.evaluate(None, context) is False

    def test_evaluate_not_equals_operator(self):
        """Testa operador NOT_EQUALS."""
        condition = AttributeCondition(
            type=ConditionType.ATTRIBUTE,
            attribute="risk_band",
            operator=OperatorType.NOT_EQUALS,
            value="critical",
        )

        context = {"risk_band": "high"}
        assert condition.evaluate(None, context) is True

        context = {"risk_band": "critical"}
        assert condition.evaluate(None, context) is False

    def test_evaluate_in_operator(self):
        """Testa operador IN."""
        condition = AttributeCondition(
            type=ConditionType.ATTRIBUTE,
            attribute="tenant_id",
            operator=OperatorType.IN,
            value=["tenant-1", "tenant-2"],
        )

        context = {"tenant_id": "tenant-1"}
        assert condition.evaluate(None, context) is True

        context = {"tenant_id": "tenant-999"}
        assert condition.evaluate(None, context) is False

    def test_evaluate_missing_attribute_returns_false(self):
        """Testa que atributo ausente retorna False."""
        condition = AttributeCondition(
            type=ConditionType.ATTRIBUTE,
            attribute="namespace",
            operator=OperatorType.EQUALS,
            value="staging",
        )

        context = {"other_attribute": "value"}
        assert condition.evaluate(None, context) is False


class TestRolloutType:
    """Testes para RolloutType enum."""

    def test_rollout_type_values(self):
        """Testa valores do enum."""
        assert RolloutType.IMMEDIATE == "immediate"
        assert RolloutType.GRADUAL == "gradual"
        assert RolloutType.CANARY == "canary"
        assert RolloutType.SCHEDULED == "scheduled"


class TestConditionType:
    """Testes para ConditionType enum."""

    def test_condition_type_values(self):
        """Testa valores do enum."""
        assert ConditionType.WHITELIST == "whitelist"
        assert ConditionType.PERCENTAGE == "percentage"
        assert ConditionType.ATTRIBUTE == "attribute"


class TestOperatorType:
    """Testes para OperatorType enum."""

    def test_operator_type_values(self):
        """Testa valores do enum."""
        assert OperatorType.EQUALS == "equals"
        assert OperatorType.NOT_EQUALS == "not_equals"
        assert OperatorType.IN == "in"
        assert OperatorType.NOT_IN == "not_in"
        assert OperatorType.GREATER_THAN == "greater_than"
        assert OperatorType.LESS_THAN == "less_than"


class TestFeatureFlagConditions:
    """Testes para condições complexas em FeatureFlag."""

    def test_feature_flag_with_conditions(self):
        """Testa flag com múltiplas condições."""
        flag = FeatureFlag(
            name="conditional_feature",
            description="Feature with conditions",
            enabled=True,
            conditions=[
                WhitelistCondition(
                    type=ConditionType.WHITELIST,
                    values=["tenant-123"],
                    attribute="tenant_id",
                ),
                AttributeCondition(
                    type=ConditionType.ATTRIBUTE,
                    attribute="environment",
                    operator=OperatorType.EQUALS,
                    value="staging",
                ),
            ],
        )

        assert len(flag.conditions) == 2
        assert isinstance(flag.conditions[0], WhitelistCondition)
        assert isinstance(flag.conditions[1], AttributeCondition)

    def test_evaluate_all_conditions_with_and_logic(self):
        """Testa avaliação com lógica AND (todas devem passar)."""
        flag = FeatureFlag(
            name="conditional_feature",
            description="Feature with AND conditions",
            enabled=True,
            conditions=[
                WhitelistCondition(
                    type=ConditionType.WHITELIST,
                    values=["tenant-123"],
                    attribute="tenant_id",
                ),
                AttributeCondition(
                    type=ConditionType.ATTRIBUTE,
                    attribute="environment",
                    operator=OperatorType.EQUALS,
                    value="staging",
                ),
            ],
        )

        # Ambas condições passam
        context = {"tenant_id": "tenant-123", "environment": "staging"}
        assert flag.is_enabled_for(context) is True

        # Apenas primeira condição passa
        context = {"tenant_id": "tenant-123", "environment": "production"}
        assert flag.is_enabled_for(context) is False

        # Nenhuma condição passa
        context = {"tenant_id": "tenant-999", "environment": "production"}
        assert flag.is_enabled_for(context) is False

    def test_disabled_flag_always_false(self):
        """Testa que flag desabilitada sempre retorna False."""
        flag = FeatureFlag(
            name="disabled_feature",
            description="Disabled feature",
            enabled=False,
            conditions=[
                WhitelistCondition(
                    type=ConditionType.WHITELIST,
                    values=["*"],  # Wildcard
                    attribute="any",
                ),
            ],
        )

        assert flag.is_enabled_for({"any": "value"}) is False

    def test_flag_without_conditions_always_true_when_enabled(self):
        """Testa que flag sem condições retorna True quando habilitada."""
        flag = FeatureFlag(
            name="unconditional_feature",
            description="Unconditional feature",
            enabled=True,
        )

        assert flag.is_enabled_for({}) is True

    def test_percentage_rollout_evaluation(self):
        """Testa avaliação de rollout percentual."""
        strategy = RolloutStrategy(
            type=RolloutType.GRADUAL, percentage=50
        )

        flag = FeatureFlag(
            name="percentage_feature",
            description="Percentage rollout",
            enabled=True,
            rollout_strategy=strategy,
        )

        # Testa consistência para mesma chave
        context = {"user_id": "user-123"}
        result1 = flag.is_enabled_for(context)
        result2 = flag.is_enabled_for(context)

        assert result1 == result2
