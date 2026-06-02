"""Testes unitários para TokenCounter."""


from neural_hive_llm.token_counter import (
    ModelPricing,
    ModelProvider,
    TokenCounter,
    get_token_counter,
    MODEL_PRICING,
)


class TestModelPricing:
    """Testes para dados de precificação."""

    def test_model_pricing_data_structure(self):
        """Testa estrutura de dados de preços."""
        assert "gpt-4o" in MODEL_PRICING
        assert "claude-3-5-sonnet-20241022" in MODEL_PRICING

        provider, pricing = MODEL_PRICING["gpt-4o"]
        assert provider == ModelProvider.OPENAI
        assert isinstance(pricing, ModelPricing)
        assert pricing.input_price > 0
        assert pricing.output_price > 0

    def test_openai_pricing(self):
        """Testa preços da OpenAI."""
        provider, pricing = MODEL_PRICING["gpt-4o"]
        assert pricing.input_price == 2.50
        assert pricing.output_price == 10.00

    def test_anthropic_pricing(self):
        """Testa preços da Anthropic."""
        provider, pricing = MODEL_PRICING["claude-3-5-sonnet-20241022"]
        assert provider == ModelProvider.ANTHROPIC
        assert pricing.input_price > 0


class TestTokenCounter:
    """Testes para TokenCounter."""

    def test_initialization(self):
        """Testa inicialização do contador."""
        counter = TokenCounter(service_name="test_service")
        assert counter.service_name == "test_service"

    def test_get_pricing_known_model(self):
        """Testa obtenção de preço para modelo conhecido."""
        counter = TokenCounter()
        pricing = counter.get_pricing("gpt-4o")
        assert pricing is not None
        assert pricing.input_price > 0

    def test_get_pricing_unknown_model(self):
        """Testa obtenção de preço para modelo desconhecido."""
        counter = TokenCounter()
        # Modelos desconhecidos que não começam com gpt- ou claude
        # retornam None
        pricing = counter.get_pricing("completely-unknown-model")
        assert pricing is None

    def test_get_pricing_unknown_gpt_model_returns_default(self):
        """Testa que modelos gpt desconhecidos retornam padrão."""
        counter = TokenCounter()
        # Modelos começando com gpt- retornam pricing padrão
        pricing = counter.get_pricing("gpt-unknown")
        assert pricing is not None

    def test_calculate_cost_known_model(self):
        """Testa cálculo de custo para modelo conhecido."""
        counter = TokenCounter()
        cost_usd, provider = counter.calculate_cost(
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
        )
        assert cost_usd > 0
        assert provider == ModelProvider.OPENAI

    def test_calculate_cost_zero_tokens(self):
        """Testa cálculo com zero tokens."""
        counter = TokenCounter()
        cost_usd, provider = counter.calculate_cost(
            model="gpt-4o",
            input_tokens=0,
            output_tokens=0,
        )
        assert cost_usd == 0.0

    def test_calculate_cost_anthropic(self):
        """Testa cálculo de custo para Anthropic."""
        counter = TokenCounter()
        cost_usd, provider = counter.calculate_cost(
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500,
        )
        assert cost_usd > 0
        assert provider == ModelProvider.ANTHROPIC

    def test_record_usage(self):
        """Testa registro de uso."""
        counter = TokenCounter()
        result = counter.record_usage(
            model="gpt-4o",
            input_tokens=100,
            output_tokens=200,
        )
        assert result["total_tokens"] == 300
        assert result["provider"] == "openai"
        assert result["total_cost_usd"] > 0

    def test_estimate_tokens(self):
        """Testa estimativa de tokens."""
        counter = TokenCounter()
        # ~4 caracteres por token
        tokens = counter.estimate_tokens("Hello, world! This is a test.", model="gpt-4o")
        assert tokens > 0

    def test_estimate_tokens_empty_string(self):
        """Testa estimativa com string vazia."""
        counter = TokenCounter()
        tokens = counter.estimate_tokens("", model="gpt-4o")
        assert tokens == 0

    def test_estimate_tokens_long_text(self):
        """Testa estimativa com texto longo."""
        counter = TokenCounter()
        long_text = "word " * 1000  # ~5000 caracteres
        tokens = counter.estimate_tokens(long_text, model="gpt-4o")
        # Deve ser ~1250 tokens
        assert 1000 < tokens < 1500


class TestGlobalTokenCounter:
    """Testes para funções globais."""

    def test_get_token_counter_singleton(self):
        """Testa que get_token_counter retorna singleton."""
        counter1 = get_token_counter(service_name="service1")
        counter2 = get_token_counter(service_name="service2")
        # Mesma instância (ignora service_name nas chamadas subsequentes)
        assert counter1 is counter2

    def test_get_token_counter_initializes_once(self):
        """Testa que contador é inicializado apenas uma vez."""
        from neural_hive_llm.token_counter import reset_global_counter

        # Resetar para teste
        reset_global_counter()

        counter1 = get_token_counter(service_name="test1")
        counter2 = get_token_counter()
        assert counter1 is counter2
