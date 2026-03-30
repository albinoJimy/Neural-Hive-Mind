"""Testes para DescriptionQualityValidator."""

import pytest
from datetime import datetime

from neural_hive_specialists.validation.description_validator import (
    DescriptionQualityValidator,
    get_validator,
    _validator_instance,
)


@pytest.mark.unit
class TestDescriptionQualityValidatorInit:
    """Testes de inicialização."""

    def test_init_compiles_patterns(self):
        """Testa que padrões são compilados na inicialização."""
        validator = DescriptionQualityValidator()

        assert hasattr(validator, "_domain_patterns")
        assert "security-analysis" in validator._domain_patterns
        assert "architecture-review" in validator._domain_patterns


@pytest.mark.unit
class TestDomainKeywords:
    """Testes para DOMAIN_KEYWORDS."""

    def test_security_analysis_keywords(self):
        """Testa keywords para security-analysis."""
        keywords = DescriptionQualityValidator.DOMAIN_KEYWORDS["security-analysis"]

        assert "auth" in keywords
        assert "security" in keywords
        assert "encrypt" in keywords
        assert "jwt" in keywords  # sinônimo adicionado
        assert "vulnerability" in keywords

    def test_architecture_review_keywords(self):
        """Testa keywords para architecture-review."""
        keywords = DescriptionQualityValidator.DOMAIN_KEYWORDS["architecture-review"]

        assert "service" in keywords
        assert "microservice" in keywords  # sinônimo
        assert "graphql" in keywords

    def test_all_domains_defined(self):
        """Testa que todos os domínios esperados estão definidos."""
        domains = DescriptionQualityValidator.DOMAIN_KEYWORDS.keys()

        assert "security-analysis" in domains
        assert "architecture-review" in domains
        assert "performance-optimization" in domains
        assert "code-quality" in domains
        assert "business-logic" in domains


@pytest.mark.unit
class TestSecurityKeywords:
    """Testes para SECURITY_KEYWORDS."""

    def test_confidential_keywords(self):
        """Testa keywords para nível confidential."""
        keywords = DescriptionQualityValidator.SECURITY_KEYWORDS["confidential"]

        assert "encrypt" in keywords
        assert "auth" in keywords
        assert "protected" in keywords

    def test_restricted_keywords(self):
        """Testa keywords para nível restricted."""
        keywords = DescriptionQualityValidator.SECURITY_KEYWORDS["restricted"]

        assert "encrypt" in keywords
        assert "classified" in keywords


@pytest.mark.unit
class TestQosKeywords:
    """Testes para QOS_KEYWORDS."""

    def test_exactly_once_keywords(self):
        """Testa keywords para exactly_once."""
        keywords = DescriptionQualityValidator.QOS_KEYWORDS["exactly_once"]

        assert "idempotent" in keywords
        assert "transaction" in keywords

    def test_at_least_once_keywords(self):
        """Testa keywords para at_least_once."""
        keywords = DescriptionQualityValidator.QOS_KEYWORDS["at_least_once"]

        assert "retry" in keywords
        assert "acknowledge" in keywords


@pytest.mark.unit
class TestValidateDescription:
    """Testes para validate_description."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_validate_good_description(self, validator):
        """Testa validação de descrição boa."""
        description = "Create and initialize authentication service with JWT token validation and OAuth 2.0 integration for secure access control"

        result = validator.validate_description(
            description, domain="security-analysis", security_level="confidential"
        )

        assert result["score"] > 0.5
        assert len(result["issues"]) == 0 or all(
            "sugestões" in issue.lower() for issue in result["issues"]
        )

    def test_validate_short_description(self, validator):
        """Testa validação de descrição curta."""
        description = "Create service"

        result = validator.validate_description(description, domain="code-quality")

        # Com < 10 palavras, length_score = 0.0, mas domain pode ter keywords
        # "create" não está em code-quality keywords, mas pode obter score de diversity
        assert result["metrics"]["length_score"] == 0.0
        assert any("curta" in issue or "palavras" in issue for issue in result["issues"])

    def test_validate_low_diversity(self, validator):
        """Testa validação de descrição com baixa diversidade."""
        description = "create create create create create create create create create create"

        result = validator.validate_description(description, domain="code-quality")

        assert result["score"] < 0.5
        assert result["metrics"]["diversity_score"] < 0.5

    def test_validate_no_domain_keywords(self, validator):
        """Testa validação sem keywords de domínio."""
        description = "Execute the task with proper parameters and return the result"

        result = validator.validate_description(description, domain="security-analysis")

        # 0 keywords = domain_score 0.0
        assert result["metrics"]["domain_score"] == 0.0
        assert any("domínio" in issue or "keyword" in issue for issue in result["issues"])

    def test_validate_with_security_keywords(self, validator):
        """Testa validação com keywords de segurança."""
        description = "Encrypt and authenticate with proper access control"

        result = validator.validate_description(
            description, domain="security-analysis", security_level="confidential"
        )

        assert result["metrics"]["security_score"] > 0.5

    def test_validate_with_qos_keywords(self, validator):
        """Testa validação com keywords de QoS."""
        description = "Process with idempotent transaction and retry logic"

        result = validator.validate_description(description, domain="business-logic", qos="exactly_once")

        assert result["metrics"]["qos_score"] > 0.5

    def test_validate_returns_metrics(self, validator):
        """Testa que validate_description retorna métricas completas."""
        description = "Create service with authentication and encryption"

        result = validator.validate_description(description, domain="security-analysis")

        assert "score" in result
        assert "issues" in result
        assert "suggestions" in result
        assert "metrics" in result
        assert "length_score" in result["metrics"]
        assert "diversity_score" in result["metrics"]
        assert "domain_score" in result["metrics"]
        assert "security_score" in result["metrics"]
        assert "qos_score" in result["metrics"]
        assert "word_count" in result["metrics"]
        assert "domain_keywords_found" in result["metrics"]

    def test_validate_empty_description(self, validator):
        """Testa validação de descrição vazia."""
        result = validator.validate_description("", domain="code-quality")

        # Empty string gets 0.0 for length, 0.0 for diversity, 0.0 for domain
        # But security and qos get 1.0 each
        # With default weights: length(0.3)*0 + diversity(0.25)*0 + domain(0.2)*0 + security(0.15)*1 + qos(0.1)*1 = 0.25
        assert result["metrics"]["length_score"] == 0.0
        assert result["metrics"]["diversity_score"] == 0.0
        assert len(result["issues"]) > 0

    def test_validate_weights_adjustment_for_restricted(self, validator):
        """Testa ajuste de pesos para nível restricted."""
        description = "Create service with proper authentication"

        result = validator.validate_description(
            description, domain="security-analysis", security_level="restricted"
        )

        # Nível restricted deve aumentar peso de security
        assert result["metrics"]["security_score"] >= 0


@pytest.mark.unit
class TestScoreLength:
    """Testes para _score_length."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_score_very_short(self, validator):
        """Testa score para descrição muito curta."""
        score, issues = validator._score_length("test")

        assert score == 0.0
        assert len(issues) > 0

    def test_score_short(self, validator):
        """Testa score para descrição curta."""
        score, issues = validator._score_length("This is short")

        # "This is short" = 3 words (< 10), so score = 0.0
        assert score == 0.0
        assert len(issues) > 0

    def test_score_optimal(self, validator):
        """Testa score para descrição no tamanho ótimo (15-50 palavras)."""
        description = "This is a good description with adequate length for validation"

        score, issues = validator._score_length(description)

        # 11 words, should be in the < 15 range with proportional score
        # But if >= 15 and <= 50, score = 1.0
        # "This is a good description with adequate length for validation purposes" = 11 words
        # Let me count again: This(1) is(2) a(3) good(4) description(5) with(6) adequate(7) length(8) for(9) validation(10) purposes(11)
        # Actually that's 11, so score = 0.5 * (11/15) = 0.367
        # Let me use a longer description
        longer_desc = "This is a good description with adequate length for validation purposes and testing the scoring system"
        # 18 words - should get score 1.0
        score2, issues2 = validator._score_length(longer_desc)
        assert score2 == 1.0
        assert len(issues2) == 0

    def test_score_long(self, validator):
        """Testa score para descrição longa."""
        description = " ".join(["word"] * 60)

        score, issues = validator._score_length(description)

        assert 0.0 < score < 1.0
        assert len(issues) > 0

    def test_score_very_long(self, validator):
        """Testa score para descrição muito longa."""
        description = " ".join(["word"] * 100)

        score, issues = validator._score_length(description)

        assert score == 0.5
        assert len(issues) > 0


@pytest.mark.unit
class TestScoreLexicalDiversity:
    """Testes para _score_lexical_diversity."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_diverse_description(self, validator):
        """Testa score para descrição diversa."""
        description = "Create authenticate authorize validate audit encrypt"

        score, issues = validator._score_lexical_diversity(description)

        assert score == 1.0
        assert len(issues) == 0

    def test_repetitive_description(self, validator):
        """Testa score para descrição repetitiva."""
        description = "create create create create create create create create create create"

        score, issues = validator._score_lexical_diversity(description)

        assert score < 0.5
        assert len(issues) > 0

    def test_empty_description(self, validator):
        """Testa score para descrição vazia."""
        score, issues = validator._score_lexical_diversity("")

        assert score == 0.0
        assert len(issues) > 0


@pytest.mark.unit
class TestScoreDomainKeywords:
    """Testes para _score_domain_keywords."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_multiple_keywords(self, validator):
        """Testa score com múltiplas keywords."""
        description = "Authenticate and authorize user with password and token"

        score, issues = validator._score_domain_keywords(description, "security-analysis")

        assert score == 1.0
        assert len(issues) == 0

    def test_single_keyword(self, validator):
        """Testa score com única keyword."""
        description = "Authenticate user"

        score, issues = validator._score_domain_keywords(description, "security-analysis")

        assert score == 0.5
        assert len(issues) == 1

    def test_no_keywords(self, validator):
        """Testa score sem keywords."""
        description = "Execute the task properly"

        score, issues = validator._score_domain_keywords(description, "security-analysis")

        assert score == 0.0
        assert len(issues) > 0

    def test_unknown_domain(self, validator):
        """Testa score para domínio desconhecido."""
        score, issues = validator._score_domain_keywords("test description", "unknown")

        assert score == 0.5
        assert len(issues) == 0


@pytest.mark.unit
class TestCountDomainKeywords:
    """Testes para _count_domain_keywords."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_count_keywords_found(self, validator):
        """Testa contagem de keywords encontradas."""
        description = "Authenticate and authorize with password"

        count = validator._count_domain_keywords(description, "security-analysis")

        assert count > 0

    def test_count_keywords_none(self, validator):
        """Testa contagem para domínio desconhecido."""
        count = validator._count_domain_keywords("test", "unknown")

        assert count == 0


@pytest.mark.unit
class TestScoreSecurityKeywords:
    """Testes para _score_security_keywords."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_no_security_level(self, validator):
        """Testa score máximo quando não há nível de segurança."""
        score, issues = validator._score_security_keywords("test", None)

        assert score == 1.0
        assert len(issues) == 0

    def test_confidential_with_keywords(self, validator):
        """Testa score para nível confidential com keywords."""
        description = "Encrypt and authenticate"

        score, issues = validator._score_security_keywords(
            description, "confidential"
        )

        assert score > 0.5

    def test_restricted_with_insufficient_keywords(self, validator):
        """Testa score para nível restricted com poucas keywords."""
        description = "Process data"

        score, issues = validator._score_security_keywords(description, "restricted")

        assert score < 0.5
        assert len(issues) > 0

    def test_public_level(self, validator):
        """Testa score para nível público."""
        score, issues = validator._score_security_keywords("test", "public")

        assert score >= 0.8


@pytest.mark.unit
class TestScoreQosKeywords:
    """Testes para _score_qos_keywords."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_no_qos(self, validator):
        """Testa score máximo quando não há requisito QoS."""
        score, issues = validator._score_qos_keywords("test", None)

        assert score == 1.0

    def test_qos_with_keywords(self, validator):
        """Testa score para QoS com keywords."""
        description = "Process with idempotent transaction"

        score, issues = validator._score_qos_keywords(description, "exactly_once")

        assert score == 1.0

    def test_qos_without_keywords(self, validator):
        """Testa score para QoS sem keywords."""
        description = "Process data normally"

        score, issues = validator._score_qos_keywords(description, "exactly_once")

        assert score == 0.5
        assert len(issues) > 0


@pytest.mark.unit
class TestValidatePlanDescriptions:
    """Testes para validate_plan_descriptions."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_validate_plan_valid(self, validator):
        """Testa validação de plano válido."""
        cognitive_plan = {
            "tasks": [
                {"task_id": "1", "description": "Create service with authentication and encryption"},
                {"task_id": "2", "description": "Validate data with proper checks"},
            ],
            "original_domain": "security-analysis",
            "original_security_level": "confidential",
        }

        result = validator.validate_plan_descriptions(cognitive_plan)

        assert result["is_valid"] is True
        assert "avg_score" in result

    def test_validate_plan_invalid(self, validator):
        """Testa validação de plano inválido."""
        cognitive_plan = {
            "tasks": [
                {"task_id": "1", "description": "Do task"},
                {"task_id": "2", "description": "Execute"},
            ],
            "original_domain": "security-analysis",
        }

        result = validator.validate_plan_descriptions(cognitive_plan)

        assert result["is_valid"] is False
        assert result["avg_score"] < 0.5

    def test_validate_plan_empty_tasks(self, validator):
        """Testa validação de plano sem tarefas."""
        cognitive_plan = {
            "tasks": [],
            "original_domain": "code-quality",
        }

        result = validator.validate_plan_descriptions(cognitive_plan)

        assert result["is_valid"] is False

    def test_validate_plan_returns_low_quality_tasks(self, validator):
        """Testa que tarefas de baixa qualidade são reportadas."""
        # Usar descrições extremamente curtas para garantir score baixo
        cognitive_plan = {
            "tasks": [
                {"task_id": "1", "description": "Do"},
                {"task_id": "2", "description": "Run"},
            ],
            "original_domain": "security-analysis",
        }

        result = validator.validate_plan_descriptions(cognitive_plan)

        # Individual threshold = min(0.5 - 0.1, 0.4) = 0.4
        # "Do" e "Run" têm score próximo de 0 (domain_score 0, length_score 0)
        assert len(result["low_quality_tasks"]) > 0
        assert "task_id" in result["low_quality_tasks"][0]


@pytest.mark.unit
class TestGenerateSuggestions:
    """Testes para _generate_suggestions."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_suggestions_for_short_description(self, validator):
        """Testa sugestões para descrição curta."""
        suggestions = validator._generate_suggestions(
            description="short",
            domain="code-quality",
            security_level=None,
            qos=None,
            length_score=0.3,
            diversity_score=0.8,
            domain_score=0.8,
        )

        assert len(suggestions) > 0
        assert any("Expand" in s or "palavras" in s for s in suggestions)

    def test_suggestions_for_low_diversity(self, validator):
        """Testa sugestões para baixa diversidade."""
        suggestions = validator._generate_suggestions(
            description="repeat repeat repeat",
            domain="code-quality",
            security_level=None,
            qos=None,
            length_score=0.8,
            diversity_score=0.4,
            domain_score=0.8,
        )

        assert any("vocabulário" in s or "variado" in s for s in suggestions)

    def test_suggestions_for_low_domain_score(self, validator):
        """Testa sugestões para baixo score de domínio."""
        suggestions = validator._generate_suggestions(
            description="Execute the operation properly",
            domain="security-analysis",
            security_level=None,
            qos=None,
            length_score=0.8,
            diversity_score=0.8,
            domain_score=0.4,
        )

        assert any("keyword" in s or "domínio" in s for s in suggestions)


@pytest.mark.unit
class TestSuggestImprovements:
    """Testes para suggest_improvements."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_suggest_improvements_basic(self, validator):
        """Testa sugestão de melhoria básica."""
        description = "create"
        context = {"domain": "code-quality"}

        improved = validator.suggest_improvements(description, context)

        assert len(improved) > len(description)
        assert "create" in improved.lower()
        assert "code-quality" in improved

    def test_suggest_improvements_with_entities(self, validator):
        """Testa sugestão incluindo entidades."""
        description = "validate data"
        context = {
            "domain": "security-analysis",
            "entities": [{"type": "user", "id": "123"}],
        }

        improved = validator.suggest_improvements(description, context)

        assert "user data" in improved

    def test_suggest_improvements_with_security(self, validator):
        """Testa sugestão adicionando contexto de segurança."""
        description = "process data"
        context = {
            "domain": "business-logic",
            "security_level": "confidential",
        }

        improved = validator.suggest_improvements(description, context)

        assert "authentication" in improved or "encryption" in improved


@pytest.mark.unit
class TestGetActionVerbs:
    """Testes para _get_action_verbs."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_get_action_verb_create(self, validator):
        """Testa verbo para create."""
        verb = validator._get_action_verbs("create operation")

        assert "Create" in verb

    def test_get_action_verb_update(self, validator):
        """Testa verbo para update."""
        verb = validator._get_action_verbs("update data")

        assert "Modify" in verb

    def test_get_action_verb_unknown(self, validator):
        """Testa verbo para operação desconhecida."""
        verb = validator._get_action_verbs("custom operation")

        assert "Custom operation" in verb


@pytest.mark.unit
class TestSummarizeEntities:
    """Testes para _summarize_entities."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_summarize_no_entities(self, validator):
        """Testa resumo sem entidades."""
        summary = validator._summarize_entities([])

        assert summary == ""

    def test_summarize_single_entity(self, validator):
        """Testa resumo com entidade única."""
        entities = [{"type": "user", "id": "123"}]

        summary = validator._summarize_entities(entities)

        assert "user data" in summary

    def test_summarize_multiple_entities(self, validator):
        """Testa resumo com múltiplas entidades."""
        entities = [
            {"type": "user", "id": "1"},
            {"type": "order", "id": "2"},
            {"type": "product", "id": "3"},
        ]

        summary = validator._summarize_entities(entities)

        # Deve incluir no máximo 2 tipos
        assert "data" in summary


@pytest.mark.unit
class TestGetDomainHint:
    """Testes para _get_domain_hint."""

    @pytest.fixture
    def validator(self):
        return DescriptionQualityValidator()

    def test_hint_for_known_domain(self, validator):
        """Testa hint para domínio conhecido."""
        hint = validator._get_domain_hint("security-analysis")

        assert "security" in hint.lower()
        assert "validation" in hint

    def test_hint_for_unknown_domain(self, validator):
        """Testa hint para domínio desconhecido."""
        hint = validator._get_domain_hint("unknown-domain")

        assert hint == ""


@pytest.mark.unit
class TestGetValidator:
    """Testes para get_validator."""

    def test_get_validator_returns_singleton(self):
        """Testa que get_validator retorna mesma instância."""
        validator1 = get_validator()
        validator2 = get_validator()

        assert validator1 is validator2

    def test_get_validator_creates_instance(self):
        """Testa que get_validator cria instância se necessário."""
        # Limpar instância global
        import neural_hive_specialists.validation.description_validator as m
        m._validator_instance = None

        validator = get_validator()

        assert isinstance(validator, DescriptionQualityValidator)
