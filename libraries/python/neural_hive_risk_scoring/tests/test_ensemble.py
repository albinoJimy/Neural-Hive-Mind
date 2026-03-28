"""
Testes para RiskEnsemble
"""

import pytest
from unittest.mock import Mock

from neural_hive_risk_scoring import (
    RiskEnsemble,
    RiskModel,
    EnsembleMethod,
    EnsembleResult,
    RiskScoringConfig,
    RiskBand,
    RiskAssessment,
    UnifiedDomain
)


@pytest.fixture
def config():
    """Configuração de teste."""
    return RiskScoringConfig()


@pytest.fixture
def sample_models():
    """Modelos de exemplo para ensemble."""
    def model1_assessor(entity, domain):
        return RiskAssessment(
            score=0.3,
            band=RiskBand.LOW,
            domain=domain,
            factors={},
            reasoning='Model 1: Low risk'
        )

    def model2_assessor(entity, domain):
        return RiskAssessment(
            score=0.7,
            band=RiskBand.HIGH,
            domain=domain,
            factors={},
            reasoning='Model 2: High risk'
        )

    def model3_assessor(entity, domain):
        return RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=domain,
            factors={},
            reasoning='Model 3: Medium risk'
        )

    return [
        RiskModel(name='conservative', assessor=model1_assessor, weight=1.0),
        RiskModel(name='aggressive', assessor=model2_assessor, weight=1.0),
        RiskModel(name='moderate', assessor=model3_assessor, weight=1.0)
    ]


@pytest.fixture
def ensemble(config, sample_models):
    """Ensemble de teste."""
    ens = RiskEnsemble(
        method=EnsembleMethod.WEIGHTED_AVERAGE,
        config=config,
        min_models=2
    )
    for model in sample_models:
        ens.add_model(model)
    return ens


@pytest.fixture
def sample_entity():
    """Entidade de exemplo."""
    return {'id': 'test-entity', 'name': 'Test Plan'}


class TestRiskModel:
    """Testes para RiskModel."""

    def test_init(self):
        """Testa inicialização."""
        def assessor(e, d):
            return None

        model = RiskModel(
            name='test_model',
            assessor=assessor,
            weight=0.8,
            domains=[UnifiedDomain.BUSINESS, UnifiedDomain.TECHNICAL]
        )

        assert model.name == 'test_model'
        assert model.weight == 0.8
        assert len(model.domains) == 2

    def test_assess_supported_domain(self):
        """Testa avaliação em domínio suportado."""
        def assessor(e, d):
            return RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=d,
                factors={},
                reasoning='test'
            )

        model = RiskModel(
            name='test',
            assessor=assessor,
            domains=[UnifiedDomain.BUSINESS]
        )

        result = model.assess({}, UnifiedDomain.BUSINESS)

        assert result is not None
        assert result.score == 0.5

    def test_assess_unsupported_domain(self):
        """Testa avaliação em domínio não suportado."""
        def assessor(e, d):
            return RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=d,
                factors={},
                reasoning='test'
            )

        model = RiskModel(
            name='test',
            assessor=assessor,
            domains=[UnifiedDomain.BUSINESS]  # Apenas BUSINESS
        )

        result = model.assess({}, UnifiedDomain.SECURITY)

        assert result is None

    def test_record_accuracy(self):
        """Testa registro de acurácia."""
        def assessor(e, d):
            return RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=d,
                factors={},
                reasoning='test'
            )

        model = RiskModel(name='test', assessor=assessor)

        model.record_accuracy(0.85)
        model.record_accuracy(0.90)

        assert model.get_accuracy() == pytest.approx(0.875)


class TestRiskEnsemble:
    """Testes para RiskEnsemble."""

    def test_init(self, config):
        """Testa inicialização."""
        ens = RiskEnsemble(method=EnsembleMethod.MAJORITY_VOTE, config=config)

        assert ens.method == EnsembleMethod.MAJORITY_VOTE
        assert ens.min_models == 2
        assert len(ens._models) == 0

    def test_add_model(self, ensemble):
        """Testa adição de modelo."""
        initial_count = len(ensemble._models)

        def new_assessor(e, d):
            return RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=d,
                factors={},
                reasoning='test'
            )

        new_model = RiskModel(name='new_model', assessor=new_assessor)
        ensemble.add_model(new_model)

        assert len(ensemble._models) == initial_count + 1

    def test_remove_model(self, ensemble):
        """Testa remoção de modelo."""
        initial_count = len(ensemble._models)

        ensemble.remove_model('conservative')

        assert len(ensemble._models) == initial_count - 1

    def test_assess_weighted_average(self, ensemble, sample_entity):
        """Testa avaliação por média ponderada."""
        result = ensemble.assess(
            entity=sample_entity,
            domain=UnifiedDomain.BUSINESS,
            entity_id='test-entity'
        )

        assert result.entity_id == 'test-entity'
        assert result.domain == UnifiedDomain.BUSINESS
        assert 0.0 <= result.final_score <= 1.0
        assert result.model_count == 3
        assert result.method == EnsembleMethod.WEIGHTED_AVERAGE

    def test_assess_majority_vote(self, config, sample_models, sample_entity):
        """Testa avaliação por votação de maioria."""
        ens = RiskEnsemble(
            method=EnsembleMethod.MAJORITY_VOTE,
            config=config
        )
        for model in sample_models:
            ens.add_model(model)

        result = ens.assess(
            entity=sample_entity,
            domain=UnifiedDomain.TECHNICAL,
            entity_id='test-entity'
        )

        # Deve ter resultado de maioria
        assert result.final_band in [RiskBand.LOW, RiskBand.HIGH, RiskBand.MEDIUM]
        assert result.model_count == 3

    def test_assess_maximum(self, config, sample_models, sample_entity):
        """Testa avaliação por BUCKET_VOTE (mais próximo de máximo)."""
        ens = RiskEnsemble(
            method=EnsembleMethod.BUCKET_VOTE,
            config=config
        )
        for model in sample_models:
            ens.add_model(model)

        result = ens.assess(
            entity=sample_entity,
            domain=UnifiedDomain.SECURITY,
            entity_id='test-entity'
        )

        # Deve ter resultado válido
        assert 0.0 <= result.final_score <= 1.0

    def test_insufficient_models_with_fallback(self, config, sample_entity):
        """Testa fallback com modelos insuficientes."""
        ens = RiskEnsemble(
            method=EnsembleMethod.WEIGHTED_AVERAGE,
            config=config,
            min_models=5,  # Requer mais que temos
            fallback_to_default=True
        )

        # Adicionar apenas 1 modelo
        def single_assessor(e, d):
            return RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=d,
                factors={},
                reasoning='test'
            )

        ens.add_model(RiskModel(name='single', assessor=single_assessor))

        result = ens.assess(
            entity=sample_entity,
            domain=UnifiedDomain.BUSINESS,
            entity_id='test-entity'
        )

        # Deve usar fallback
        assert result.model_count == 1

    def test_insufficient_models_without_fallback(self, config, sample_models, sample_entity):
        """Testa erro sem fallback."""
        ens = RiskEnsemble(
            method=EnsembleMethod.WEIGHTED_AVERAGE,
            config=config,
            min_models=10,
            fallback_to_default=False
        )
        for model in sample_models:
            ens.add_model(model)

        with pytest.raises(ValueError, match="Modelos insuficientes"):
            ens.assess(
                entity=sample_entity,
                domain=UnifiedDomain.BUSINESS,
                entity_id='test-entity'
            )

    def test_confidence_calculation(self, ensemble, sample_entity):
        """Testa cálculo de confiança."""
        result = ensemble.assess(
            entity=sample_entity,
            domain=UnifiedDomain.BUSINESS,
            entity_id='test-entity'
        )

        assert 0.0 <= result.confidence <= 1.0

    def test_consensus_calculation(self, ensemble, sample_entity):
        """Testa cálculo de consenso."""
        result = ensemble.assess(
            entity=sample_entity,
            domain=UnifiedDomain.BUSINESS,
            entity_id='test-entity'
        )

        assert 0.0 <= result.consensus_level <= 1.0

    def test_get_model_stats(self, ensemble):
        """Testa obtenção de estatísticas dos modelos."""
        stats = ensemble.get_model_stats()

        assert len(stats) == 3
        assert all('name' in s for s in stats)
        assert all('weight' in s for s in stats)
        assert all('call_count' in s for s in stats)

    def test_stacking_method(self, config, sample_models, sample_entity):
        """Testa método de stacking."""
        ens = RiskEnsemble(
            method=EnsembleMethod.STACKING,
            config=config
        )

        # Configurar acurácias diferentes
        sample_models[0].record_accuracy(0.7)
        sample_models[1].record_accuracy(0.9)
        sample_models[2].record_accuracy(0.8)

        for model in sample_models:
            ens.add_model(model)

        result = ens.assess(
            entity=sample_entity,
            domain=UnifiedDomain.BUSINESS,
            entity_id='test-entity'
        )

        # Resultado deve existir
        assert result is not None

    def test_reweight_by_accuracy(self, config):
        """Testa recalibração de pesos por acurácia."""
        ens = RiskEnsemble(method=EnsembleMethod.WEIGHTED_AVERAGE, config=config)

        def assessor(e, d):
            return RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=d,
                factors={},
                reasoning='test'
            )

        model1 = RiskModel(name='m1', assessor=assessor, weight=1.0)
        model2 = RiskModel(name='m2', assessor=assessor, weight=1.0)

        model1.record_accuracy(0.7)
        model2.record_accuracy(0.9)

        ens.add_model(model1)
        ens.add_model(model2)

        old_weights = {m.name: m.weight for m in ens._models}

        ens.reweight_by_accuracy()

        new_weights = {m.name: m.weight for m in ens._models}

        # Pesos devem ter mudado
        # Model2 com maior acurácia deve ter maior peso
        assert new_weights['m2'] > new_weights['m1']

    def test_result_to_dict(self, ensemble, sample_entity):
        """Testa conversão de resultado para dicionário."""
        result = ensemble.assess(
            entity=sample_entity,
            domain=UnifiedDomain.BUSINESS,
            entity_id='test-entity'
        )

        result_dict = result.to_dict()

        assert 'entity_id' in result_dict
        assert 'domain' in result_dict
        assert 'final_score' in result_dict
        assert 'final_band' in result_dict
        assert 'model_votes' in result_dict
        assert 'confidence' in result_dict
