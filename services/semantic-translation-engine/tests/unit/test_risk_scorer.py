"""
Testes unitários para o RiskScorer

Testa avaliação de risco multi-domínio, floor de risco para operações
destrutivas, e integração com DestructiveDetector.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.models.cognitive_plan import RiskBand, TaskNode
from src.services.risk_scorer import RiskScorer


class TestRiskScorerMultiDomain:
    """Testes para avaliação multi-domínio"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """Create RiskScorer instance"""
        return RiskScorer(settings)

    @pytest.fixture
    def sample_tasks_safe(self):
        """Tasks seguras para teste"""
        return [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Query users',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-2',
                task_type='transform',
                description='Transform data',
                dependencies=['task-1']
            )
        ]

    @pytest.fixture
    def intermediate_repr(self):
        """Representação intermediária de teste"""
        return {
            'metadata': {
                'priority': 'high',
                'security_level': 'confidential'
            }
        }

    def test_score_multi_domain_returns_four_values(
        self, risk_scorer, intermediate_repr, sample_tasks_safe
    ):
        """Verificar que retorna tupla com 4 elementos"""
        result = risk_scorer.score_multi_domain(intermediate_repr, sample_tasks_safe)

        assert isinstance(result, tuple)
        assert len(result) == 4

        score, band, factors, matrix = result
        assert isinstance(score, float)
        assert isinstance(band, RiskBand)
        assert isinstance(factors, dict)
        assert isinstance(matrix, dict)

    def test_score_multi_domain_risk_matrix_contains_all_domains(
        self, risk_scorer, intermediate_repr, sample_tasks_safe
    ):
        """Verificar que risk_matrix contém todos os campos do RiskMatrix"""
        _, _, _, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr, sample_tasks_safe
        )

        # Verificar campos obrigatórios do RiskMatrix
        assert 'entity_id' in risk_matrix
        assert 'entity_type' in risk_matrix
        assert 'assessments' in risk_matrix
        assert 'overall_score' in risk_matrix
        assert 'overall_band' in risk_matrix
        assert 'highest_risk_domain' in risk_matrix
        assert 'created_at' in risk_matrix

        # Verificar entity_type é 'plan'
        assert risk_matrix['entity_type'] == 'plan'

        # Verificar overall_score é float entre 0 e 1
        assert isinstance(risk_matrix['overall_score'], float)
        assert 0.0 <= risk_matrix['overall_score'] <= 1.0

        # Verificar que assessments contém todos os domínios
        assessments = risk_matrix['assessments']
        assert 'business' in assessments
        assert 'security' in assessments
        assert 'operational' in assessments

        # Verificar que cada assessment tem os campos esperados
        for domain, assessment in assessments.items():
            assert 'score' in assessment
            assert 'band' in assessment
            assert 'domain' in assessment
            assert 'factors' in assessment
            assert isinstance(assessment['score'], float)
            assert 0.0 <= assessment['score'] <= 1.0

    def test_score_multi_domain_aggregates_scores_correctly(
        self, risk_scorer, intermediate_repr, sample_tasks_safe
    ):
        """Verificar agregação de scores com pesos corretos"""
        _, _, _, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr, sample_tasks_safe
        )

        # Extrair scores dos assessments
        assessments = risk_matrix['assessments']
        business_score = assessments['business']['score']
        security_score = assessments['security']['score']
        operational_score = assessments['operational']['score']

        # Calcular manualmente com pesos
        expected = (
            business_score * 0.4 +
            security_score * 0.35 +
            operational_score * 0.25
        )

        # Overall deve ser próximo ao calculado (ou maior se floor aplicado)
        assert risk_matrix['overall_score'] >= expected - 0.01

    def test_score_multi_domain_safe_operations_no_floor(
        self, risk_scorer, intermediate_repr, sample_tasks_safe
    ):
        """Tasks não destrutivas não devem ter floor aplicado"""
        score, band, factors, matrix = risk_scorer.score_multi_domain(
            intermediate_repr, sample_tasks_safe
        )

        assert factors['destructive'] == 0.0

    def test_score_multi_domain_returns_valid_band(
        self, risk_scorer, intermediate_repr, sample_tasks_safe
    ):
        """Verificar que banda de risco é válida"""
        _, band, _, _ = risk_scorer.score_multi_domain(
            intermediate_repr, sample_tasks_safe
        )

        assert band in [RiskBand.LOW, RiskBand.MEDIUM, RiskBand.HIGH, RiskBand.CRITICAL]

    def test_score_multi_domain_highest_risk_domain_is_correct(
        self, risk_scorer, intermediate_repr, sample_tasks_safe
    ):
        """Verificar que highest_risk_domain é o domínio com maior score"""
        _, _, _, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr, sample_tasks_safe
        )

        assessments = risk_matrix['assessments']
        domain_scores = {
            domain: assessment['score']
            for domain, assessment in assessments.items()
        }

        # Encontrar domínio com maior score
        expected_highest = max(domain_scores, key=domain_scores.get)

        assert risk_matrix['highest_risk_domain'] == expected_highest


class TestRiskScorerFloorApplication:
    """Testes para aplicação de floor de risco"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """Create RiskScorer instance"""
        return RiskScorer(settings)

    def test_apply_risk_floor_low_severity(self, risk_scorer):
        """is_destructive=True, severity='low', base_score=0.5 → floor 0.7"""
        result = risk_scorer._apply_risk_floor(0.5, True, 'low')
        assert result == 0.7

    def test_apply_risk_floor_medium_severity(self, risk_scorer):
        """is_destructive=True, severity='medium', base_score=0.6 → floor 0.7"""
        result = risk_scorer._apply_risk_floor(0.6, True, 'medium')
        assert result == 0.7

    def test_apply_risk_floor_high_severity(self, risk_scorer):
        """is_destructive=True, severity='high', base_score=0.5 → floor 0.8"""
        result = risk_scorer._apply_risk_floor(0.5, True, 'high')
        assert result == 0.8

    def test_apply_risk_floor_critical_severity(self, risk_scorer):
        """is_destructive=True, severity='critical', base_score=0.7 → floor 0.9"""
        result = risk_scorer._apply_risk_floor(0.7, True, 'critical')
        assert result == 0.9

    def test_apply_risk_floor_no_change_if_above_floor(self, risk_scorer):
        """Score acima do floor não deve ser modificado"""
        result = risk_scorer._apply_risk_floor(0.85, True, 'low')
        assert result == 0.85

    def test_apply_risk_floor_not_applied_for_safe_operations(self, risk_scorer):
        """is_destructive=False não aplica floor"""
        result = risk_scorer._apply_risk_floor(0.3, False, 'low')
        assert result == 0.3


class TestRiskScorerDestructiveIntegration:
    """Testes de integração com DestructiveDetector"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """Create RiskScorer instance"""
        return RiskScorer(settings)

    @pytest.fixture
    def sample_tasks_destructive(self):
        """Tasks destrutivas para teste"""
        return [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete old records',
                dependencies=[]
            )
        ]

    @pytest.fixture
    def intermediate_repr(self):
        """Representação intermediária de teste"""
        return {
            'metadata': {
                'priority': 'medium',
                'security_level': 'internal'
            }
        }

    def test_score_multi_domain_integrates_destructive_detector(
        self, risk_scorer, intermediate_repr, sample_tasks_destructive
    ):
        """Verificar integração com DestructiveDetector"""
        score, band, factors, matrix = risk_scorer.score_multi_domain(
            intermediate_repr, sample_tasks_destructive
        )

        # Floor deve ser aplicado para operação destrutiva
        assert score >= 0.7
        assert factors['destructive'] == 1.0

    def test_score_multi_domain_destructive_tasks_in_factors(
        self, risk_scorer, intermediate_repr, sample_tasks_destructive
    ):
        """Tasks destrutivas devem ter destructive=1.0 em factors"""
        _, _, factors, _ = risk_scorer.score_multi_domain(
            intermediate_repr, sample_tasks_destructive
        )

        assert factors['destructive'] == 1.0

    def test_score_multi_domain_safe_tasks_in_factors(self, risk_scorer, intermediate_repr):
        """Tasks seguras devem ter destructive=0.0 em factors"""
        safe_tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Query users',
                dependencies=[]
            )
        ]
        _, _, factors, _ = risk_scorer.score_multi_domain(intermediate_repr, safe_tasks)

        assert factors['destructive'] == 0.0

    def test_score_multi_domain_severity_affects_floor(self, risk_scorer, intermediate_repr):
        """Diferentes severidades devem resultar em diferentes floors"""
        # Criar tasks que triggeram critical severity (high impact indicator)
        critical_tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete all production data',
                dependencies=[]
            )
        ]

        score, _, _, _ = risk_scorer.score_multi_domain(intermediate_repr, critical_tasks)

        # Floor para critical é 0.9
        assert score >= 0.9


class TestRiskScorerScoreAggregation:
    """Testes para agregação de scores"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """Create RiskScorer instance"""
        return RiskScorer(settings)

    def test_aggregate_scores_weighted_average(self, risk_scorer):
        """Verificar cálculo de média ponderada"""
        result = risk_scorer._aggregate_scores(0.5, 0.6, 0.4)

        # Esperado: (0.5 * 0.4) + (0.6 * 0.35) + (0.4 * 0.25) = 0.2 + 0.21 + 0.1 = 0.51
        expected = 0.51
        assert abs(result - expected) < 0.001

    def test_aggregate_scores_normalizes_to_range(self, risk_scorer):
        """Resultado deve estar sempre em [0, 1]"""
        # Testar com todos 0.0
        result_zeros = risk_scorer._aggregate_scores(0.0, 0.0, 0.0)
        assert result_zeros == 0.0

        # Testar com todos 1.0
        result_ones = risk_scorer._aggregate_scores(1.0, 1.0, 1.0)
        assert result_ones == 1.0

    def test_aggregate_scores_handles_edge_cases(self, risk_scorer):
        """Testar edge cases com scores extremos"""
        # Mix extremo
        result = risk_scorer._aggregate_scores(0.0, 1.0, 0.0)

        # Esperado: (0.0 * 0.4) + (1.0 * 0.35) + (0.0 * 0.25) = 0.35
        expected = 0.35
        assert abs(result - expected) < 0.001
        assert 0.0 <= result <= 1.0


class TestRiskScorerBackwardCompatibility:
    """Testes de compatibilidade com método score() original"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """Create RiskScorer instance"""
        return RiskScorer(settings)

    @pytest.fixture
    def sample_tasks(self):
        """Tasks de teste"""
        return [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Query users',
                dependencies=[]
            )
        ]

    @pytest.fixture
    def intermediate_repr(self):
        """Representação intermediária de teste"""
        return {
            'metadata': {
                'priority': 'medium',
                'security_level': 'internal'
            }
        }

    def test_score_method_still_works(
        self, risk_scorer, intermediate_repr, sample_tasks
    ):
        """Verificar que método score() original ainda funciona"""
        result = risk_scorer.score(intermediate_repr, sample_tasks)

        assert isinstance(result, tuple)
        assert len(result) == 3

        score, band, factors = result
        assert isinstance(score, float)
        assert isinstance(band, RiskBand)
        assert isinstance(factors, dict)

    def test_score_and_score_multi_domain_coexist(
        self, risk_scorer, intermediate_repr, sample_tasks
    ):
        """Verificar que ambos os métodos podem ser chamados no mesmo scorer"""
        # Chamar método original
        score1, band1, factors1 = risk_scorer.score(intermediate_repr, sample_tasks)

        # Chamar método multi-domínio
        score2, band2, factors2, matrix = risk_scorer.score_multi_domain(
            intermediate_repr, sample_tasks
        )

        # Ambos devem retornar resultados válidos
        assert 0.0 <= score1 <= 1.0
        assert 0.0 <= score2 <= 1.0
        assert band1 in [RiskBand.LOW, RiskBand.MEDIUM, RiskBand.HIGH, RiskBand.CRITICAL]
        assert band2 in [RiskBand.LOW, RiskBand.MEDIUM, RiskBand.HIGH, RiskBand.CRITICAL]


class TestRiskScorerLogging:
    """Testes para logging estruturado"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """Create RiskScorer instance"""
        return RiskScorer(settings)

    @pytest.fixture
    def sample_tasks(self):
        """Tasks de teste"""
        return [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Query users',
                dependencies=[]
            )
        ]

    @pytest.fixture
    def intermediate_repr(self):
        """Representação intermediária de teste"""
        return {
            'metadata': {
                'priority': 'medium',
                'security_level': 'internal'
            }
        }

    @patch('src.services.risk_scorer.logger')
    def test_score_multi_domain_logs_structured_data(
        self, mock_logger, risk_scorer, intermediate_repr, sample_tasks
    ):
        """Verificar que log contém dados estruturados"""
        risk_scorer.score_multi_domain(intermediate_repr, sample_tasks)

        mock_logger.info.assert_called()
        call_args = mock_logger.info.call_args

        # Verificar que foi chamado com campos esperados
        assert 'risk_score' in call_args.kwargs or 'risk_score=' in str(call_args)

    @patch('src.services.risk_scorer.logger')
    def test_apply_risk_floor_logs_warning_when_applied(
        self, mock_logger, risk_scorer
    ):
        """Verificar que warning é emitido quando floor é aplicado"""
        risk_scorer._apply_risk_floor(0.5, True, 'low')

        mock_logger.warning.assert_called()
        call_args = mock_logger.warning.call_args

        # Verificar mensagem de warning
        assert 'Floor de risco aplicado' in call_args.args[0]


class TestRiskScorerEdgeCases:
    """Testes para edge cases"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """Create RiskScorer instance"""
        return RiskScorer(settings)

    @pytest.fixture
    def intermediate_repr(self):
        """Representação intermediária de teste"""
        return {
            'metadata': {
                'priority': 'medium',
                'security_level': 'internal'
            }
        }

    def test_score_multi_domain_empty_tasks_list(self, risk_scorer, intermediate_repr):
        """Lista vazia de tasks não deve causar erro"""
        score, band, factors, matrix = risk_scorer.score_multi_domain(
            intermediate_repr, []
        )

        # Deve retornar resultado válido
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert isinstance(band, RiskBand)

    def test_score_multi_domain_missing_metadata(self, risk_scorer):
        """intermediate_repr sem campos obrigatórios deve usar valores padrão"""
        empty_repr = {'metadata': {}}
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Query users',
                dependencies=[]
            )
        ]

        # Não deve lançar exceção
        score, band, factors, matrix = risk_scorer.score_multi_domain(empty_repr, tasks)

        assert isinstance(score, float)
        assert isinstance(band, RiskBand)

    def test_score_multi_domain_high_complexity_tasks(self, risk_scorer, intermediate_repr):
        """20+ tasks com muitas dependências devem aumentar complexity"""
        # Criar 20 tasks com dependências
        tasks = []
        for i in range(20):
            deps = [f'task-{j}' for j in range(max(0, i-3), i)]
            tasks.append(TaskNode(
                task_id=f'task-{i}',
                task_type='transform',
                description=f'Transform data {i}',
                dependencies=deps
            ))

        score, band, factors, matrix = risk_scorer.score_multi_domain(
            intermediate_repr, tasks
        )

        # Score deve ser elevado devido à complexidade
        assert score > 0.3  # Score não trivial esperado


class TestRiskScorerBandClassification:
    """Testes para classificação de banda de risco"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """Create RiskScorer instance"""
        return RiskScorer(settings)

    def test_classify_band_low(self, risk_scorer):
        """Score < 0.4 → LOW"""
        band = risk_scorer._classify_band_from_score(0.3)
        assert band == RiskBand.LOW

    def test_classify_band_medium(self, risk_scorer):
        """0.4 <= Score < 0.7 → MEDIUM"""
        band = risk_scorer._classify_band_from_score(0.5)
        assert band == RiskBand.MEDIUM

    def test_classify_band_high(self, risk_scorer):
        """0.7 <= Score < 0.9 → HIGH"""
        band = risk_scorer._classify_band_from_score(0.75)
        assert band == RiskBand.HIGH

    def test_classify_band_critical(self, risk_scorer):
        """Score >= 0.9 → CRITICAL"""
        band = risk_scorer._classify_band_from_score(0.95)
        assert band == RiskBand.CRITICAL

    def test_classify_band_boundary_medium(self, risk_scorer):
        """Score == 0.4 → MEDIUM"""
        band = risk_scorer._classify_band_from_score(0.4)
        assert band == RiskBand.MEDIUM

    def test_classify_band_boundary_high(self, risk_scorer):
        """Score == 0.7 → HIGH"""
        band = risk_scorer._classify_band_from_score(0.7)
        assert band == RiskBand.HIGH

    def test_classify_band_boundary_critical(self, risk_scorer):
        """Score == 0.9 → CRITICAL"""
        band = risk_scorer._classify_band_from_score(0.9)
        assert band == RiskBand.CRITICAL
