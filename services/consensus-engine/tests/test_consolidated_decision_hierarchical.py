"""
Testes unitários para modelos de decisão com campos hierárquicos.

TDD: Testes escritos antes da implementação (RED phase).
"""

from src.models.consolidated_decision import (
    ConsensusMethod,
    ConsensusMetrics,
    ConsolidatedDecision,
    DecisionType,
    SpecialistVote,
)


class TestSpecialistVoteHierarchicalFields:
    """Testes dos novos campos hierárquicos em SpecialistVote."""

    def test_specialist_vote_has_seniority_level_field(self):
        """SpecialistVote deve ter campo seniority_level opcional."""
        vote = SpecialistVote(
            specialist_type="business",
            opinion_id="op-123",
            confidence_score=0.85,
            risk_score=0.2,
            recommendation="approve",
            weight=1.0,
            processing_time_ms=100,
        )

        # Campo deve existir e ser opcional
        assert hasattr(vote, "seniority_level")
        assert vote.seniority_level is None  # Default quando não fornecido

    def test_specialist_vote_accepts_valid_seniority_level(self):
        """Deve aceitar níveis de senioridade válidos."""
        valid_levels = ["trainee", "junior", "mid_level", "senior", "expert"]

        for level in valid_levels:
            vote = SpecialistVote(
                specialist_type="business",
                opinion_id="op-123",
                confidence_score=0.85,
                risk_score=0.2,
                recommendation="approve",
                weight=1.0,
                processing_time_ms=100,
                seniority_level=level,
            )
            assert vote.seniority_level == level

    def test_specialist_vote_has_seniority_multiplier_field(self):
        """SpecialistVote deve ter campo seniority_multiplier opcional."""
        vote = SpecialistVote(
            specialist_type="business",
            opinion_id="op-123",
            confidence_score=0.85,
            risk_score=0.2,
            recommendation="approve",
            weight=1.0,
            processing_time_ms=100,
        )

        # Campo deve existir e ser opcional
        assert hasattr(vote, "seniority_multiplier")
        assert vote.seniority_multiplier is None  # Default quando não fornecido

    def test_specialist_vote_accepts_seniority_multiplier(self):
        """Deve aceitar multiplicador de senioridade."""
        vote = SpecialistVote(
            specialist_type="architecture",
            opinion_id="op-124",
            confidence_score=0.90,
            risk_score=0.1,
            recommendation="approve",
            weight=1.0,
            processing_time_ms=150,
            seniority_level="expert",
            seniority_multiplier=2.0,
        )

        assert vote.seniority_multiplier == 2.0

    def test_specialist_vote_with_all_hierarchical_fields(self):
        """Deve criar voto com todos os campos hierárquicos preenchidos."""
        vote = SpecialistVote(
            specialist_type="architecture",
            opinion_id="op-125",
            confidence_score=0.95,
            risk_score=0.05,
            recommendation="approve",
            weight=0.95,
            processing_time_ms=120,
            seniority_level="expert",
            seniority_multiplier=2.0,
        )

        assert vote.seniority_level == "expert"
        assert vote.seniority_multiplier == 2.0
        assert vote.weight == 0.95  # Peso ajustado pelo multiplicador


class TestConsensusMetricsHierarchicalFields:
    """Testes dos novos campos hierárquicos em ConsensusMetrics."""

    def test_consensus_metrics_has_weighted_by_seniority_field(self):
        """ConsensusMetrics deve ter campo weighted_by_seniority."""
        metrics = ConsensusMetrics(
            divergence_score=0.15,
            convergence_time_ms=500,
            unanimous=True,
            fallback_used=False,
            pheromone_strength=0.8,
            bayesian_confidence=0.85,
            voting_confidence=0.88,
        )

        # Campo deve existir
        assert hasattr(metrics, "weighted_by_seniority")
        # Default deve ser False (backward compatibility)
        assert metrics.weighted_by_seniority is False

    def test_consensus_metrics_has_seniority_distribution_field(self):
        """ConsensusMetrics deve ter campo seniority_distribution."""
        metrics = ConsensusMetrics(
            divergence_score=0.15,
            convergence_time_ms=500,
            unanimous=True,
            fallback_used=False,
            pheromone_strength=0.8,
            bayesian_confidence=0.85,
            voting_confidence=0.88,
        )

        # Campo deve existir
        assert hasattr(metrics, "seniority_distribution")
        # Default deve ser dict vazio (backward compatibility)
        assert metrics.seniority_distribution == {}

    def test_consensus_metrics_has_consensus_method_hierarchical_field(self):
        """ConsensusMetrics deve indicar se método hierárquico foi usado."""
        metrics = ConsensusMetrics(
            divergence_score=0.15,
            convergence_time_ms=500,
            unanimous=True,
            fallback_used=False,
            pheromone_strength=0.8,
            bayesian_confidence=0.85,
            voting_confidence=0.88,
            consensus_method_hierarchical=True,
        )

        assert metrics.consensus_method_hierarchical is True

    def test_consensus_metrics_with_all_hierarchical_fields(self):
        """Deve criar métricas com todos os campos hierárquicos."""
        metrics = ConsensusMetrics(
            divergence_score=0.10,
            convergence_time_ms=450,
            unanimous=False,
            fallback_used=False,
            pheromone_strength=0.9,
            bayesian_confidence=0.88,
            voting_confidence=0.90,
            weighted_by_seniority=True,
            seniority_distribution={
                "trainee": 0,
                "junior": 1,
                "mid_level": 2,
                "senior": 1,
                "expert": 1,
            },
            consensus_method_hierarchical=True,
        )

        assert metrics.weighted_by_seniority is True
        assert metrics.seniority_distribution == {
            "trainee": 0,
            "junior": 1,
            "mid_level": 2,
            "senior": 1,
            "expert": 1,
        }
        assert metrics.consensus_method_hierarchical is True


class TestConsolidatedDecisionHierarchicalFields:
    """Testes de integração com ConsolidatedDecision."""

    def test_consolidated_decision_with_hierarchical_votes(self):
        """Deve criar decisão com votos contendo campos hierárquicos."""
        votes = [
            SpecialistVote(
                specialist_type="business",
                opinion_id="op-1",
                confidence_score=0.85,
                risk_score=0.2,
                recommendation="approve",
                weight=0.85,
                processing_time_ms=100,
                seniority_level="senior",
                seniority_multiplier=1.5,
            ),
            SpecialistVote(
                specialist_type="architecture",
                opinion_id="op-2",
                confidence_score=0.90,
                risk_score=0.1,
                recommendation="approve",
                weight=0.95,
                processing_time_ms=120,
                seniority_level="expert",
                seniority_multiplier=2.0,
            ),
        ]

        metrics = ConsensusMetrics(
            divergence_score=0.10,
            convergence_time_ms=300,
            unanimous=True,
            fallback_used=False,
            pheromone_strength=0.9,
            bayesian_confidence=0.88,
            voting_confidence=0.90,
            weighted_by_seniority=True,
            seniority_distribution={"senior": 1, "expert": 1},
            consensus_method_hierarchical=True,
        )

        decision = ConsolidatedDecision(
            plan_id="plan-123",
            intent_id="intent-123",
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.BAYESIAN,
            aggregated_confidence=0.88,
            aggregated_risk=0.15,
            specialist_votes=votes,
            consensus_metrics=metrics,
            explainability_token="token-abc",
            reasoning_summary="All specialists approved",
        )

        assert len(decision.specialist_votes) == 2
        assert decision.specialist_votes[0].seniority_level == "senior"
        assert decision.specialist_votes[1].seniority_multiplier == 2.0
        assert decision.consensus_metrics.weighted_by_seniority is True
        assert decision.consensus_metrics.seniority_distribution == {"senior": 1, "expert": 1}


class TestToAvroDictHierarchicalFields:
    """Testes de serialização Avro com campos hierárquicos."""

    def test_to_avro_dict_includes_seniority_level(self):
        """to_avro_dict() deve incluir seniority_level quando presente."""
        vote = SpecialistVote(
            specialist_type="business",
            opinion_id="op-123",
            confidence_score=0.85,
            risk_score=0.2,
            recommendation="approve",
            weight=1.0,
            processing_time_ms=100,
            seniority_level="senior",
            seniority_multiplier=1.5,
        )

        # Usar o método to_avro_dict através de ConsolidatedDecision
        metrics = ConsensusMetrics(
            divergence_score=0.10,
            convergence_time_ms=300,
            unanimous=True,
            fallback_used=False,
            pheromone_strength=0.9,
            bayesian_confidence=0.85,
            voting_confidence=0.88,
        )

        decision = ConsolidatedDecision(
            plan_id="plan-123",
            intent_id="intent-123",
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.BAYESIAN,
            aggregated_confidence=0.85,
            aggregated_risk=0.2,
            specialist_votes=[vote],
            consensus_metrics=metrics,
            explainability_token="token-xyz",
            reasoning_summary="Test",
        )

        avro_dict = decision.to_avro_dict()

        # Verificar que votos incluem novos campos
        vote_dict = avro_dict["specialist_votes"][0]
        assert "seniority_level" in vote_dict
        assert vote_dict["seniority_level"] == "senior"
        assert "seniority_multiplier" in vote_dict
        assert vote_dict["seniority_multiplier"] == 1.5

    def test_to_avro_dict_includes_consensus_metrics_hierarchical_fields(self):
        """to_avro_dict() deve incluir campos hierárquicos de consensus_metrics."""
        metrics = ConsensusMetrics(
            divergence_score=0.10,
            convergence_time_ms=300,
            unanimous=True,
            fallback_used=False,
            pheromone_strength=0.9,
            bayesian_confidence=0.85,
            voting_confidence=0.88,
            weighted_by_seniority=True,
            seniority_distribution={"senior": 1, "expert": 1},
            consensus_method_hierarchical=True,
        )

        decision = ConsolidatedDecision(
            plan_id="plan-123",
            intent_id="intent-123",
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.BAYESIAN,
            aggregated_confidence=0.85,
            aggregated_risk=0.2,
            specialist_votes=[],
            consensus_metrics=metrics,
            explainability_token="token-xyz",
            reasoning_summary="Test",
        )

        avro_dict = decision.to_avro_dict()
        metrics_dict = avro_dict["consensus_metrics"]

        assert "weighted_by_seniority" in metrics_dict
        assert metrics_dict["weighted_by_seniority"] is True
        assert "seniority_distribution" in metrics_dict
        assert metrics_dict["seniority_distribution"] == {"senior": 1, "expert": 1}
        assert "consensus_method_hierarchical" in metrics_dict
        assert metrics_dict["consensus_method_hierarchical"] is True

    def test_to_avro_dict_handles_missing_hierarchical_fields(self):
        """to_avro_dict() deve lidar com campos hierárquicos ausentes (backward compatibility)."""
        vote = SpecialistVote(
            specialist_type="business",
            opinion_id="op-123",
            confidence_score=0.85,
            risk_score=0.2,
            recommendation="approve",
            weight=1.0,
            processing_time_ms=100,
            # Não incluir seniority_level ou seniority_multiplier
        )

        metrics = ConsensusMetrics(
            divergence_score=0.10,
            convergence_time_ms=300,
            unanimous=True,
            fallback_used=False,
            pheromone_strength=0.9,
            bayesian_confidence=0.85,
            voting_confidence=0.88,
            # Não incluir campos hierárquicos
        )

        decision = ConsolidatedDecision(
            plan_id="plan-123",
            intent_id="intent-123",
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.BAYESIAN,
            aggregated_confidence=0.85,
            aggregated_risk=0.2,
            specialist_votes=[vote],
            consensus_metrics=metrics,
            explainability_token="token-xyz",
            reasoning_summary="Test",
        )

        # Não deve levantar erro
        avro_dict = decision.to_avro_dict()

        # Campos devem estar presentes com valores None/default
        vote_dict = avro_dict["specialist_votes"][0]
        assert "seniority_level" in vote_dict
        assert vote_dict["seniority_level"] is None
        assert "seniority_multiplier" in vote_dict
        assert vote_dict["seniority_multiplier"] is None


class TestBackwardCompatibility:
    """Testes de backward compatibility."""

    def test_old_vote_format_still_works(self):
        """Votos no formato antigo (sem campos hierárquicos) devem funcionar."""
        # Deve criar voto sem erro mesmo sem os novos campos
        vote = SpecialistVote(
            specialist_type="business",
            opinion_id="op-123",
            confidence_score=0.85,
            risk_score=0.2,
            recommendation="approve",
            weight=1.0,
            processing_time_ms=100,
        )

        assert vote.specialist_type == "business"
        assert vote.seniority_level is None
        assert vote.seniority_multiplier is None

    def test_old_metrics_format_still_works(self):
        """Métricas no formato antigo devem funcionar."""
        metrics = ConsensusMetrics(
            divergence_score=0.15,
            convergence_time_ms=500,
            unanimous=True,
            fallback_used=False,
            pheromone_strength=0.8,
            bayesian_confidence=0.85,
            voting_confidence=0.88,
        )

        assert metrics.weighted_by_seniority is False
        assert metrics.seniority_distribution == {}
