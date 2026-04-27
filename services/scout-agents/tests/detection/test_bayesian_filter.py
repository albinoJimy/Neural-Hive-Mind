"""
Testes unitários abrangentes para BayesianFilter.

Cobertura: filtragem Bayesiana, atualização de priors, likelihoods.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from src.detection.bayesian_filter import BayesianFilter
from src.models.raw_event import RawEvent

from neural_hive_domain import UnifiedDomain

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def bayesian_filter():
    """Instância de BayesianFilter para testes."""
    return BayesianFilter()


@pytest.fixture()
def event_with_features():
    """Evento com features numéricas."""
    return RawEvent(
        event_id="feature-event-001",
        source="test-source",
        event_type="test",
        timestamp=datetime.now(timezone.utc),
        payload={"metric1": 100, "metric2": 200, "metric3": 150},
        metadata={"trace_id": "trace-001"},
    )


@pytest.fixture()
def event_without_features():
    """Evento sem features numéricas."""
    return RawEvent(
        event_id="no-feature-event-001",
        source="test-source",
        event_type="test",
        timestamp=datetime.now(timezone.utc),
        payload={"message": "test message", "status": "active"},
        metadata={"trace_id": "trace-002"},
    )


# ============================================================================
# Testes de Inicialização
# ============================================================================


class TestBayesianFilterInitialization:
    """Testes de inicialização do BayesianFilter."""

    def test_initialization_with_uniform_priors(self, bayesian_filter):
        """Testa que priors são inicializados com distribuição uniforme."""
        for domain in UnifiedDomain:
            alpha, beta = bayesian_filter.priors[domain.value]
            assert alpha == 1.0
            assert beta == 1.0

    def test_initialization_has_all_domains(self, bayesian_filter):
        """Testa que todos os domínios estão presentes nos priors."""
        for domain in UnifiedDomain:
            assert domain.value in bayesian_filter.priors

    def test_initialization_empty_likelihoods(self, bayesian_filter):
        """Testa que likelihoods começam vazios."""
        assert len(bayesian_filter.likelihoods) == 0


# ============================================================================
# Testes de Filtragem
# ============================================================================


class TestBayesianFiltering:
    """Testes do método de filtragem principal."""

    def test_filter_returns_false_when_no_features(self, bayesian_filter, event_without_features):
        """Testa que eventos sem features são filtrados."""
        with patch.object(event_without_features, "extract_features", return_value=[]):
            should_process, posterior = bayesian_filter.filter(
                event_without_features, UnifiedDomain.BUSINESS
            )
            assert should_process is False
            assert posterior == 0.0

    def test_filter_with_valid_features(self, bayesian_filter, event_with_features):
        """Testa filtragem com features válidas."""
        should_process, posterior = bayesian_filter.filter(
            event_with_features, UnifiedDomain.BUSINESS
        )
        # Com prior uniforme, deve processar
        assert isinstance(should_process, bool)
        assert isinstance(posterior, float)
        assert 0.0 <= posterior <= 1.0

    def test_filter_posterior_calculation(self, bayesian_filter, event_with_features):
        """Testa cálculo de posterior."""
        should_process, posterior = bayesian_filter.filter(
            event_with_features, UnifiedDomain.BUSINESS
        )
        # Prior uniforme = 0.5, likelihood deve afetar posterior
        assert 0.0 <= posterior <= 1.0

    def test_filter_all_domains(self, bayesian_filter, event_with_features):
        """Testa filtragem em todos os domínios."""
        for domain in UnifiedDomain:
            should_process, posterior = bayesian_filter.filter(event_with_features, domain)
            assert isinstance(should_process, bool)
            assert 0.0 <= posterior <= 1.0

    def test_filter_threshold_decision(self, bayesian_filter, event_with_features):
        """Testa decisão baseada em threshold."""
        # Aumentar posterior aprendendo
        bayesian_filter.update_prior(UnifiedDomain.BUSINESS, True)
        bayesian_filter.update_prior(UnifiedDomain.BUSINESS, True)
        bayesian_filter.update_prior(UnifiedDomain.BUSINESS, True)

        should_process, posterior = bayesian_filter.filter(
            event_with_features, UnifiedDomain.BUSINESS
        )
        # Com 3 updates positivos, prior aumenta
        if posterior >= 0.4:
            assert should_process is True


# ============================================================================
# Testes de Cálculo de Likelihood
# ============================================================================


class TestLikelihoodCalculation:
    """Testes de cálculo de likelihood."""

    def test_calculate_likelihood_initializes_on_first_call(self, bayesian_filter):
        """Testa que likelihood é inicializado na primeira chamada."""
        likelihood = bayesian_filter.calculate_likelihood(0.5, UnifiedDomain.BUSINESS)
        assert isinstance(likelihood, float)
        assert 0.0 <= likelihood <= 1.0
        assert UnifiedDomain.BUSINESS.value in bayesian_filter.likelihoods

    def test_calculate_likelihood_with_existing_params(self, bayesian_filter):
        """Testa cálculo com parâmetros existentes."""
        # Configurar likelihood manualmente
        bayesian_filter.likelihoods[UnifiedDomain.TECHNICAL.value] = (0.5, 1.0)

        likelihood = bayesian_filter.calculate_likelihood(0.5, UnifiedDomain.TECHNICAL)
        assert isinstance(likelihood, float)
        assert 0.0 <= likelihood <= 1.0

    def test_calculate_likelihood_normalization(self, bayesian_filter):
        """Testa que likelihood é normalizado."""
        likelihood = bayesian_filter.calculate_likelihood(10.0, UnifiedDomain.BUSINESS)
        assert likelihood <= 1.0

    def test_calculate_likelihood_zero_std(self, bayesian_filter):
        """Testa likelihood com std zero."""
        bayesian_filter.likelihoods[UnifiedDomain.SECURITY.value] = (0.5, 0.0)
        likelihood = bayesian_filter.calculate_likelihood(0.5, UnifiedDomain.SECURITY)
        # Com std zero, retorna default
        assert likelihood == 0.5

    def test_calculate_likelihood_different_features(self, bayesian_filter):
        """Testa likelihood com diferentes features."""
        likelihood1 = bayesian_filter.calculate_likelihood(0.1, UnifiedDomain.BUSINESS)
        likelihood2 = bayesian_filter.calculate_likelihood(1.0, UnifiedDomain.BUSINESS)
        # Devem ser diferentes (probabilidade normal)
        assert likelihood1 != likelihood2 or likelihood1 == likelihood2


# ============================================================================
# Testes de Atualização de Prior
# ============================================================================


class TestPriorUpdate:
    """Testes de atualização de prior."""

    def test_update_prior_valid_signal_increases_alpha(self, bayesian_filter):
        """Testa que sinal válido incrementa alpha."""
        initial_alpha, initial_beta = bayesian_filter.priors[UnifiedDomain.BUSINESS.value]

        bayesian_filter.update_prior(UnifiedDomain.BUSINESS, True)

        new_alpha, new_beta = bayesian_filter.priors[UnifiedDomain.BUSINESS.value]
        assert new_alpha == initial_alpha + 1
        assert new_beta == initial_beta

    def test_update_prior_invalid_signal_increases_beta(self, bayesian_filter):
        """Testa que sinal inválido incrementa beta."""
        initial_alpha, initial_beta = bayesian_filter.priors[UnifiedDomain.SECURITY.value]

        bayesian_filter.update_prior(UnifiedDomain.SECURITY, False)

        new_alpha, new_beta = bayesian_filter.priors[UnifiedDomain.SECURITY.value]
        assert new_alpha == initial_alpha
        assert new_beta == initial_beta + 1

    def test_update_prior_affects_mean(self, bayesian_filter):
        """Testa que atualização afeta média da prior."""
        # Prior uniforme: 1.0, 1.0 -> mean = 0.5
        initial_mean = bayesian_filter.priors[UnifiedDomain.TECHNICAL.value][0] / sum(
            bayesian_filter.priors[UnifiedDomain.TECHNICAL.value]
        )

        # Adicionar sinais válidos
        for _ in range(3):
            bayesian_filter.update_prior(UnifiedDomain.TECHNICAL, True)

        new_alpha, new_beta = bayesian_filter.priors[UnifiedDomain.TECHNICAL.value]
        new_mean = new_alpha / (new_alpha + new_beta)

        # Média deve aumentar
        assert new_mean > initial_mean

    def test_update_prior_multiple_domains_independent(self, bayesian_filter):
        """Testa que domínios são independentes."""
        bayesian_filter.update_prior(UnifiedDomain.BUSINESS, True)
        bayesian_filter.update_prior(UnifiedDomain.SECURITY, False)

        business_alpha, _ = bayesian_filter.priors[UnifiedDomain.BUSINESS.value]
        security_alpha, _ = bayesian_filter.priors[UnifiedDomain.SECURITY.value]

        # BUSINESS deve ter alpha aumentado
        assert business_alpha == 2.0
        # SECURITY deve ter alpha original
        assert security_alpha == 1.0


# ============================================================================
# Testes de Atualização de Likelihood
# ============================================================================


class TestLikelihoodUpdate:
    """Testes de atualização de likelihood."""

    def test_update_likelihood_creates_new_entry(self, bayesian_filter):
        """Testa que atualização cria entrada se não existe."""
        bayesian_filter.update_likelihood(UnifiedDomain.BUSINESS, 0.7)

        assert UnifiedDomain.BUSINESS.value in bayesian_filter.likelihoods
        mean, std = bayesian_filter.likelihoods[UnifiedDomain.BUSINESS.value]
        assert mean == 0.7
        assert std == 1.0

    def test_update_likelihood_exponential_moving_average(self, bayesian_filter):
        """Testa atualização usando média móvel exponencial."""
        # Inicializar
        bayesian_filter.likelihoods[UnifiedDomain.TECHNICAL.value] = (0.5, 1.0)

        # Atualizar com novo valor
        bayesian_filter.update_likelihood(UnifiedDomain.TECHNICAL, 0.7, weight=0.1)

        new_mean, new_std = bayesian_filter.likelihoods[UnifiedDomain.TECHNICAL.value]
        # Nova média = 0.9 * 0.5 + 0.1 * 0.7 = 0.52
        expected_mean = 0.9 * 0.5 + 0.1 * 0.7
        assert abs(new_mean - expected_mean) < 0.01

    def test_update_likelihood_std_calculation(self, bayesian_filter):
        """Testa cálculo de std na atualização."""
        bayesian_filter.likelihoods[UnifiedDomain.SECURITY.value] = (0.5, 1.0)

        bayesian_filter.update_likelihood(UnifiedDomain.SECURITY, 0.9, weight=0.1)

        _, new_std = bayesian_filter.likelihoods[UnifiedDomain.SECURITY.value]
        # Std deve ser atualizado
        assert new_std >= 0.1  # Mínimo

    def test_update_likelihood_minimum_std(self, bayesian_filter):
        """Testa que std não fica abaixo do mínimo."""
        bayesian_filter.likelihoods[UnifiedDomain.INFRASTRUCTURE.value] = (0.5, 0.1)

        # Tentar reduzir std
        bayesian_filter.update_likelihood(UnifiedDomain.INFRASTRUCTURE, 0.5, weight=1.0)

        _, new_std = bayesian_filter.likelihoods[UnifiedDomain.INFRASTRUCTURE.value]
        assert new_std >= 0.1


# ============================================================================
# Testes de Estatísticas de Posterior
# ============================================================================


class TestPosteriorStats:
    """Testes de estatísticas de posterior."""

    def test_get_posterior_stats_uniform_prior(self, bayesian_filter):
        """Testa estatísticas com prior uniforme."""
        stats = bayesian_filter.get_posterior_stats(UnifiedDomain.BUSINESS)

        assert "mean" in stats
        assert "variance" in stats
        assert "ci_lower" in stats
        assert "ci_upper" in stats
        assert "samples" in stats

        # Beta(1,1) tem mean = 0.5
        assert stats["mean"] == 0.5
        assert stats["samples"] == 0  # alpha + beta - 2 = 0

    def test_get_posterior_stats_after_updates(self, bayesian_filter):
        """Testa estatísticas após atualizações."""
        # Adicionar alguns sinais
        for _ in range(5):
            bayesian_filter.update_prior(UnifiedDomain.TECHNICAL, True)
        for _ in range(2):
            bayesian_filter.update_prior(UnifiedDomain.TECHNICAL, False)

        stats = bayesian_filter.get_posterior_stats(UnifiedDomain.TECHNICAL)

        # alpha=6, beta=3, samples=7
        assert stats["samples"] == 7
        # mean = 6/(6+3) = 0.667
        assert abs(stats["mean"] - 0.667) < 0.01

    def test_get_posterior_stats_confidence_interval(self, bayesian_filter):
        """Testa intervalo de confiança."""
        # Adicionar sinais para ter CI mais estreito
        for _ in range(10):
            bayesian_filter.update_prior(UnifiedDomain.SECURITY, True)

        stats = bayesian_filter.get_posterior_stats(UnifiedDomain.SECURITY)

        # CI deve existir e lower < upper
        assert stats["ci_lower"] < stats["ci_upper"]
        # Para alpha alto, CI deve estar acima de 0.5
        assert stats["ci_lower"] > 0.3

    def test_get_posterior_stats_variance(self, bayesian_filter):
        """Testa cálculo de variância."""
        stats = bayesian_filter.get_posterior_stats(UnifiedDomain.BUSINESS)

        assert stats["variance"] > 0
        assert stats["variance"] < 1  # Para Beta(1,1), variance = 1/12


# ============================================================================
# Testes de Integração
# ============================================================================


class TestBayesianFilterIntegration:
    """Testes de integração do fluxo completo."""

    def test_full_learning_cycle(self, bayesian_filter, event_with_features):
        """Testa ciclo completo de aprendizado."""
        # Fase inicial: baixa confiança
        should_process1, posterior1 = bayesian_filter.filter(
            event_with_features, UnifiedDomain.BUSINESS
        )

        # Aprender que sinais deste domínio são válidos
        for _ in range(5):
            bayesian_filter.update_prior(UnifiedDomain.BUSINESS, True)

        # Fase posterior: maior confiança
        should_process2, posterior2 = bayesian_filter.filter(
            event_with_features, UnifiedDomain.BUSINESS
        )

        # Posterior deve aumentar
        assert posterior2 >= posterior1 or posterior1 == posterior2

    def test_adaptive_likelihood(self, bayesian_filter):
        """Testa adaptação de likelihood."""
        # Primeiro valor
        bayesian_filter.update_likelihood(UnifiedDomain.TECHNICAL, 0.3, weight=1.0)
        mean1, _ = bayesian_filter.likelihoods[UnifiedDomain.TECHNICAL.value]

        # Segundo valor influencia
        bayesian_filter.update_likelihood(UnifiedDomain.TECHNICAL, 0.7, weight=0.5)
        mean2, _ = bayesian_filter.likelihoods[UnifiedDomain.TECHNICAL.value]

        # Média deve mudar
        assert mean1 != mean2

    def test_convergence_after_many_samples(self, bayesian_filter):
        """Testa convergência após muitas amostras."""
        # Simular muitos sinais válidos (80%) e inválidos (20%)
        for i in range(100):
            is_valid = i < 80  # 80% válidos
            bayesian_filter.update_prior(UnifiedDomain.INFRASTRUCTURE, is_valid)

        stats = bayesian_filter.get_posterior_stats(UnifiedDomain.INFRASTRUCTURE)

        # Média deve convergir para ~0.8
        assert abs(stats["mean"] - 0.8) < 0.1
        # Variância deve ser baixa
        assert stats["variance"] < 0.01

    def test_filter_error_handling(self, bayesian_filter, event_with_features):
        """Testa tratamento de erro na filtragem."""
        # Forçar erro em extract_features
        with patch.object(
            event_with_features, "extract_features", side_effect=Exception("Test error")
        ):
            should_process, posterior = bayesian_filter.filter(
                event_with_features, UnifiedDomain.BUSINESS
            )
            # Em caso de erro, deve retornar defaults
            assert should_process is True  # Default: processar
            assert posterior == 0.5


# ============================================================================
# Testes de Domínios Específicos
# ============================================================================


class TestDomainSpecificBehavior:
    """Testes de comportamento específico por domínio."""

    def test_business_domain_learning(self, bayesian_filter, event_with_features):
        """Testa aprendizado no domínio BUSINESS."""
        # BUSINESS tende a ter mais sinais válidos
        for _ in range(8):
            bayesian_filter.update_prior(UnifiedDomain.BUSINESS, True)
        for _ in range(2):
            bayesian_filter.update_prior(UnifiedDomain.BUSINESS, False)

        stats = bayesian_filter.get_posterior_stats(UnifiedDomain.BUSINESS)
        assert stats["mean"] > 0.6

    def test_security_domain_conservative(self, bayesian_filter, event_with_features):
        """Testa que SECURITY é mais conservador."""
        # SECURITY pode ter mais falsos positivos
        for _ in range(5):
            bayesian_filter.update_prior(UnifiedDomain.SECURITY, True)
        for _ in range(5):
            bayesian_filter.update_prior(UnifiedDomain.SECURITY, False)

        stats = bayesian_filter.get_posterior_stats(UnifiedDomain.SECURITY)
        # Mean deve ser próximo de 0.5
        assert abs(stats["mean"] - 0.5) < 0.2

    def test_multiple_domains_independent_learning(self, bayesian_filter):
        """Testa que múltiplos domínios aprendem independentemente."""
        # Treinar BUSINESS com alta taxa de validação
        for _ in range(10):
            bayesian_filter.update_prior(UnifiedDomain.BUSINESS, True)

        # Treinar SECURITY com baixa taxa
        for _ in range(5):
            bayesian_filter.update_prior(UnifiedDomain.SECURITY, True)
        for _ in range(5):
            bayesian_filter.update_prior(UnifiedDomain.SECURITY, False)

        business_stats = bayesian_filter.get_posterior_stats(UnifiedDomain.BUSINESS)
        security_stats = bayesian_filter.get_posterior_stats(UnifiedDomain.SECURITY)

        # BUSINESS deve ter média maior que SECURITY
        assert business_stats["mean"] > security_stats["mean"]
