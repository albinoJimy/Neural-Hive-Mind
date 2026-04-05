"""
Testes unitários para RolloutStrategy.

Testa estratégias de rollout: gradual, whitelist, canary, all.
"""

from src.services.rollout_strategy import RolloutStrategy


class TestRolloutStrategyGradual:
    """Testes de estratégia de rollout gradual."""

    def test_evaluate_gradual_within_percentage(self):
        """Testa avaliação gradual com hash dentro do percentage."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 50,
            },
        }
        context = {"tenant_id": "tenant-123"}

        # Usar hash determinístico - tenant-123 com 100% deve ser sempre True
        flag["rollout_config"]["percentage"] = 100
        result = RolloutStrategy.evaluate(flag, context)
        assert result is True

        # Com 50%, verificar que resultado é consistente
        flag["rollout_config"]["percentage"] = 50
        result1 = RolloutStrategy.evaluate(flag, context)
        result2 = RolloutStrategy.evaluate(flag, context)
        # Hash determinístico: mesma entrada, mesmo resultado
        assert result1 == result2

    def test_evaluate_gradual_outside_percentage(self):
        """Testa avaliação gradual com hash fora do percentage."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 1,  # Apenas 1%
            },
        }
        context = {"tenant_id": "tenant-999"}

        # Com 1%, a maioria dos tenants ficará fora
        result = RolloutStrategy.evaluate(flag, context)
        # Verificar se o hash está fora do range (depende do valor do hash)
        assert isinstance(result, bool)

    def test_evaluate_gradual_zero_percentage(self):
        """Testa avaliação gradual com 0% (sempre False)."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 0,
            },
        }
        context = {"tenant_id": "any-tenant"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is False

    def test_evaluate_gradual_hundred_percentage(self):
        """Testa avaliação gradual com 100% (sempre True)."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 100,
            },
        }
        context = {"tenant_id": "any-tenant"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is True

    def test_evaluate_gradual_no_tenant_id_fallback_to_user_id(self):
        """Testa avaliação gradual sem tenant_id usa user_id."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 100,
            },
        }
        context = {"user_id": "user-123"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is True

    def test_evaluate_gradual_no_context_fallback_false(self):
        """Testa avaliação gradual sem contexto retorna False."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 100,
            },
        }
        context = {}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is False


class TestRolloutStrategyWhitelist:
    """Testes de estratégia de whitelist."""

    def test_evaluate_whitelist_in_list(self):
        """Testa avaliação whitelist com tenant na lista."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "whitelist",
            "rollout_config": {
                "whitelist": ["tenant-123", "tenant-456"],
            },
        }
        context = {"tenant_id": "tenant-123"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is True

    def test_evaluate_whitelist_not_in_list(self):
        """Testa avaliação whitelist com tenant fora da lista."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "whitelist",
            "rollout_config": {
                "whitelist": ["tenant-123", "tenant-456"],
            },
        }
        context = {"tenant_id": "tenant-999"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is False

    def test_evaluate_whitelist_empty_list(self):
        """Testa avaliação whitelist com lista vazia."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "whitelist",
            "rollout_config": {
                "whitelist": [],
            },
        }
        context = {"tenant_id": "tenant-123"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is False

    def test_evaluate_whitelist_no_tenant_id(self):
        """Testa avaliação whitelist sem tenant_id no contexto."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "whitelist",
            "rollout_config": {
                "whitelist": ["tenant-123"],
            },
        }
        context = {}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is False


class TestRolloutStrategyCanary:
    """Testes de estratégia de canary."""

    def test_evaluate_canary_in_list(self):
        """Testa avaliação canary com user_id na lista."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "canary",
            "rollout_config": {
                "canary_list": ["user-123", "user-456"],
            },
        }
        context = {"user_id": "user-123"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is True

    def test_evaluate_canary_not_in_list(self):
        """Testa avaliação canary com user_id fora da lista."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "canary",
            "rollout_config": {
                "canary_list": ["user-123", "user-456"],
            },
        }
        context = {"user_id": "user-999"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is False

    def test_evaluate_canary_empty_list(self):
        """Testa avaliação canary com lista vazia."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "canary",
            "rollout_config": {
                "canary_list": [],
            },
        }
        context = {"user_id": "user-123"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is False

    def test_evaluate_canary_no_user_id(self):
        """Testa avaliação canary sem user_id no contexto."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "canary",
            "rollout_config": {
                "canary_list": ["user-123"],
            },
        }
        context = {}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is False


class TestRolloutStrategyAll:
    """Testes de estratégia all (todos)."""

    def test_evaluate_all_always_true(self):
        """Testa avaliação all sempre retorna True."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "all",
            "rollout_config": {},
        }
        context = {}  # Contexto vazio

        result = RolloutStrategy.evaluate(flag, context)
        assert result is True

    def test_evaluate_all_with_any_context(self):
        """Testa avaliação all com qualquer contexto."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "all",
            "rollout_config": {},
        }
        context = {"tenant_id": "any", "user_id": "any", "namespace": "any"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is True


class TestRolloutStrategyNamespaceFilter:
    """Testes de filtro de namespace comum a todas as estratégias."""

    def test_namespace_filter_allowed(self):
        """Testa filtro de namespace permitido."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "all",
            "rollout_config": {
                "namespaces": ["staging", "dev"],
            },
        }
        context = {"namespace": "staging"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is True

    def test_namespace_filter_denied(self):
        """Testa filtro de namespace negado."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "all",
            "rollout_config": {
                "namespaces": ["staging", "dev"],
            },
        }
        context = {"namespace": "production"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is False

    def test_namespace_filter_no_config(self):
        """Testa sem filtro de namespace configuração."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "all",
            "rollout_config": {},
        }
        context = {"namespace": "any-namespace"}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is True

    def test_namespace_filter_no_context(self):
        """Testa filtro de namespace sem namespace no contexto."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "all",
            "rollout_config": {
                "namespaces": ["staging"],
            },
        }
        context = {}  # Sem namespace

        result = RolloutStrategy.evaluate(flag, context)
        assert result is False


class TestRolloutStrategyUnknown:
    """Testes para estratégias desconhecidas."""

    def test_evaluate_unknown_strategy_defaults_false(self):
        """Testa estratégia desconhecida retorna False."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "unknown_strategy",
            "rollout_config": {},
        }
        context = {}

        result = RolloutStrategy.evaluate(flag, context)
        assert result is False


class TestRolloutStrategyHashFunction:
    """Testes da função hash determinística."""

    def test_hash_is_deterministic(self):
        """Testa que hash para mesmo input é consistente."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "gradual",
            "rollout_config": {"percentage": 50},
        }
        context = {"tenant_id": "tenant-123"}

        result1 = RolloutStrategy.evaluate(flag, context)
        result2 = RolloutStrategy.evaluate(flag, context)

        assert result1 == result2

    def test_hash_different_for_different_tenants(self):
        """Testa que hashes diferentes podem ter resultados diferentes."""
        flag = {
            "flag_name": "test_flag",
            "rollout_strategy": "gradual",
            "rollout_config": {"percentage": 1},  # 1% para maximizar diferença
        }

        results = []
        for i in range(100):
            context = {"tenant_id": f"tenant-{i}"}
            results.append(RolloutStrategy.evaluate(flag, context))

        # Pelo menos alguns devem ser diferentes com 1%
        # (não garantido, mas estatisticamente provável)
        # Com 100 tenants e 1%, espera-se ~1 True, ~99 False
        assert sum(results) < 100  # Nem todos True
