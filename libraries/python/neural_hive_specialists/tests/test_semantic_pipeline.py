"""
Testes unitários para SemanticPipeline.

Cobertura para semantic_pipeline/semantic_pipeline.py
"""

import pytest
from unittest.mock import Mock, patch


class TestSemanticPipeline:
    """Testes para SemanticPipeline."""

    @pytest.fixture
    def config(self):
        """Configuração de teste."""
        return {
            "embeddings_model": "all-MiniLM-L6-v2",
            "semantic_similarity_threshold": 0.4,
            "semantic_analysis_weight": 0.6,
            "ontology_analysis_weight": 0.4,
        }

    @pytest.fixture
    def mock_feature_extractor(self):
        """Feature extractor mockado."""
        mock_fe = Mock()
        mock_fe.extract_features = Mock(
            return_value={
                "metadata_features": {"domain": "technical"},
                "task_features": {"num_tasks": 2},
            }
        )
        return mock_fe

    @pytest.fixture
    def sample_cognitive_plan(self):
        """Plano cognitivo de exemplo."""
        return {
            "plan_id": "test-plan-123",
            "intent_id": "test-intent-456",
            "tasks": [
                {
                    "task_id": "task-1",
                    "description": "Implementar autenticação JWT com refresh tokens",
                    "domain": "security",
                    "complexity": 0.7,
                },
                {
                    "task_id": "task-2",
                    "description": "Adicionar cache Redis para otimizar queries",
                    "domain": "performance",
                    "complexity": 0.5,
                },
            ],
            "metadata": {"domain": "technical"},
        }

    @pytest.fixture
    def sample_context(self):
        """Contexto de exemplo."""
        return {
            "user_id": "test-user",
            "session_id": "test-session",
        }

    def test_init_with_default_weights(self, config, mock_feature_extractor):
        """Testa inicialização com pesos padrão."""
        # Remover pesos para usar padrões
        config.pop("semantic_analysis_weight", None)
        config.pop("ontology_analysis_weight", None)

        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)

        assert pipeline.semantic_weight == 0.6
        assert pipeline.ontology_weight == 0.4
        assert pipeline.config == config
        assert pipeline.feature_extractor == mock_feature_extractor

    def test_init_with_custom_weights(self, config, mock_feature_extractor):
        """Testa inicialização com pesos customizados."""
        config["semantic_analysis_weight"] = 0.7
        config["ontology_analysis_weight"] = 0.3

        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)

        assert pipeline.semantic_weight == 0.7
        assert pipeline.ontology_weight == 0.3

    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.SemanticAnalyzer")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.OntologyBasedEvaluator")
    def test_evaluate_plan_success(
        self,
        mock_ontology_evaluator_class,
        mock_semantic_analyzer_class,
        config,
        mock_feature_extractor,
        sample_cognitive_plan,
        sample_context,
    ):
        """Testa avaliação bem-sucedida de plano."""
        # Mock SemanticAnalyzer
        mock_semantic_analyzer = Mock()
        mock_semantic_analyzer.analyze_security = Mock(return_value=0.8)
        mock_semantic_analyzer.analyze_architecture = Mock(return_value=0.7)
        mock_semantic_analyzer.analyze_performance = Mock(return_value=0.6)
        mock_semantic_analyzer.analyze_code_quality = Mock(return_value=0.75)
        mock_semantic_analyzer_class.return_value = mock_semantic_analyzer

        # Mock OntologyBasedEvaluator
        mock_ontology_evaluator = Mock()
        mock_ontology_evaluator.evaluate_security_level = Mock(return_value=0.7)
        mock_ontology_evaluator.evaluate_architecture_compliance = Mock(return_value=0.65)
        mock_ontology_evaluator.evaluate_complexity = Mock(return_value=0.4)
        mock_ontology_evaluator.evaluate_risk_patterns = Mock(return_value=0.3)
        mock_ontology_evaluator.get_domain_recommendations = Mock(return_value="approve")
        mock_ontology_evaluator_class.return_value = mock_ontology_evaluator

        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)
        result = pipeline.evaluate_plan(sample_cognitive_plan, sample_context)

        # Verificar estrutura do resultado
        assert "confidence_score" in result
        assert "risk_score" in result
        assert "recommendation" in result
        assert "reasoning_summary" in result
        assert "reasoning_factors" in result
        assert "mitigations" in result
        assert "metadata" in result

        # Verificar valores
        assert 0.0 <= result["confidence_score"] <= 1.0
        assert 0.0 <= result["risk_score"] <= 1.0
        assert result["recommendation"] == "approve"

    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.SemanticAnalyzer")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.OntologyBasedEvaluator")
    def test_evaluate_plan_generates_mitigations_for_low_scores(
        self,
        mock_ontology_evaluator_class,
        mock_semantic_analyzer_class,
        config,
        mock_feature_extractor,
        sample_cognitive_plan,
        sample_context,
    ):
        """Testa que mitigações são geradas para scores baixos."""
        # Mock com scores baixos
        mock_semantic_analyzer = Mock()
        mock_semantic_analyzer.analyze_security = Mock(return_value=0.4)
        mock_semantic_analyzer.analyze_architecture = Mock(return_value=0.5)
        mock_semantic_analyzer.analyze_performance = Mock(return_value=0.4)
        mock_semantic_analyzer.analyze_code_quality = Mock(return_value=0.3)
        mock_semantic_analyzer_class.return_value = mock_semantic_analyzer

        mock_ontology_evaluator = Mock()
        mock_ontology_evaluator.evaluate_security_level = Mock(return_value=0.5)
        mock_ontology_evaluator.evaluate_architecture_compliance = Mock(return_value=0.5)
        mock_ontology_evaluator.evaluate_complexity = Mock(return_value=0.3)
        mock_ontology_evaluator.evaluate_risk_patterns = Mock(return_value=0.3)
        mock_ontology_evaluator.get_domain_recommendations = Mock(return_value="review_required")
        mock_ontology_evaluator_class.return_value = mock_ontology_evaluator

        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)
        result = pipeline.evaluate_plan(sample_cognitive_plan, sample_context)

        # Verificar que mitigações foram geradas
        assert len(result["mitigations"]) > 0

        # Verificar tipos de mitigação
        mitigation_types = [m["mitigation_type"] for m in result["mitigations"]]
        assert "security_improvement" in mitigation_types
        assert "architecture_refactoring" in mitigation_types
        assert "performance_optimization" in mitigation_types
        assert "quality_enhancement" in mitigation_types

    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.SemanticAnalyzer")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.OntologyBasedEvaluator")
    def test_evaluate_plan_with_empty_tasks(
        self,
        mock_ontology_evaluator_class,
        mock_semantic_analyzer_class,
        config,
        mock_feature_extractor,
        sample_context,
    ):
        """Testa avaliação com plano sem tarefas."""
        empty_plan = {
            "plan_id": "empty-plan",
            "tasks": [],
            "metadata": {"domain": "technical"},
        }

        mock_semantic_analyzer = Mock()
        mock_semantic_analyzer.analyze_security = Mock(return_value=0.5)
        mock_semantic_analyzer.analyze_architecture = Mock(return_value=0.5)
        mock_semantic_analyzer.analyze_performance = Mock(return_value=0.5)
        mock_semantic_analyzer.analyze_code_quality = Mock(return_value=0.5)
        mock_semantic_analyzer_class.return_value = mock_semantic_analyzer

        mock_ontology_evaluator = Mock()
        mock_ontology_evaluator.evaluate_security_level = Mock(return_value=0.5)
        mock_ontology_evaluator.evaluate_architecture_compliance = Mock(return_value=0.5)
        mock_ontology_evaluator.evaluate_complexity = Mock(return_value=0.5)
        mock_ontology_evaluator.evaluate_risk_patterns = Mock(return_value=0.5)
        mock_ontology_evaluator.get_domain_recommendations = Mock(return_value="review_required")
        mock_ontology_evaluator_class.return_value = mock_ontology_evaluator

        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)
        result = pipeline.evaluate_plan(empty_plan, sample_context)

        # Deve retornar resultado válido mesmo sem tarefas
        assert "confidence_score" in result
        assert "risk_score" in result

    def test_evaluate_plan_exception_returns_fallback(
        self,
        config,
        mock_feature_extractor,
        sample_cognitive_plan,
        sample_context,
    ):
        """Testa que exceções retornam fallback neutro."""
        # Feature extractor que lança exceção
        mock_feature_extractor.extract_features = Mock(side_effect=Exception("Test error"))

        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)
        result = pipeline.evaluate_plan(sample_cognitive_plan, sample_context)

        # Verificar fallback
        assert result["confidence_score"] == 0.5
        assert result["risk_score"] == 0.5
        assert result["recommendation"] == "review_required"
        assert "error" in result["metadata"]
        assert result["metadata"]["evaluation_method"] == "fallback"

    def test_generate_reasoning(self, config, mock_feature_extractor):
        """Testa geração de narrativa de raciocínio."""
        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)

        reasoning = pipeline._generate_reasoning(
            security_score=0.8,
            architecture_score=0.7,
            performance_score=0.6,
            quality_score=0.75,
            risk_score=0.3,
            confidence_score=0.7,
            recommendation="approve",
        )

        assert "confiança=0.70" in reasoning
        assert "risco=0.30" in reasoning
        assert "segurança=0.80" in reasoning
        assert "arquitetura=0.70" in reasoning
        assert "performance=0.60" in reasoning
        assert "qualidade=0.75" in reasoning
        assert "approve" in reasoning

    def test_generate_mitigations_all_low_scores(self, config, mock_feature_extractor):
        """Testa geração de mitigações quando todos os scores são baixos."""
        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)

        mitigations = pipeline._generate_mitigations(
            security_score=0.4,
            architecture_score=0.5,
            performance_score=0.4,
            quality_score=0.3,
        )

        # Todos devem ter mitigações
        assert len(mitigations) == 4

        # Verificar prioridades
        priorities = [m["priority"] for m in mitigations]
        assert "high" in priorities
        assert "medium" in priorities
        assert "low" in priorities

    def test_generate_mitigations_no_mitigations_for_high_scores(
        self, config, mock_feature_extractor
    ):
        """Testa que scores altos não geram mitigações."""
        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)

        mitigations = pipeline._generate_mitigations(
            security_score=0.8,
            architecture_score=0.8,
            performance_score=0.8,
            quality_score=0.8,
        )

        # Nenhuma mitigação deve ser gerada
        assert len(mitigations) == 0

    def test_generate_mitigations_mixed_scores(self, config, mock_feature_extractor):
        """Testa mitigações para scores mistos."""
        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)

        mitigations = pipeline._generate_mitigations(
            security_score=0.4,  # Baixo - deve ter mitigação
            architecture_score=0.7,  # OK - sem mitigação
            performance_score=0.5,  # Limítrofe - deve ter mitigação
            quality_score=0.8,  # OK - sem mitigação
        )

        # Apenas 2 mitigações (security e performance)
        assert len(mitigations) == 2

        mitigation_types = [m["mitigation_type"] for m in mitigations]
        assert "security_improvement" in mitigation_types
        assert "performance_optimization" in mitigation_types

    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.SemanticAnalyzer")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.OntologyBasedEvaluator")
    def test_evaluate_plan_metadata_contains_all_scores(
        self,
        mock_ontology_evaluator_class,
        mock_semantic_analyzer_class,
        config,
        mock_feature_extractor,
        sample_cognitive_plan,
        sample_context,
    ):
        """Testa que metadados contêm todos os scores."""
        mock_semantic_analyzer = Mock()
        mock_semantic_analyzer.analyze_security = Mock(return_value=0.8)
        mock_semantic_analyzer.analyze_architecture = Mock(return_value=0.7)
        mock_semantic_analyzer.analyze_performance = Mock(return_value=0.6)
        mock_semantic_analyzer.analyze_code_quality = Mock(return_value=0.75)
        mock_semantic_analyzer_class.return_value = mock_semantic_analyzer

        mock_ontology_evaluator = Mock()
        mock_ontology_evaluator.evaluate_security_level = Mock(return_value=0.7)
        mock_ontology_evaluator.evaluate_architecture_compliance = Mock(return_value=0.65)
        mock_ontology_evaluator.evaluate_complexity = Mock(return_value=0.4)
        mock_ontology_evaluator.evaluate_risk_patterns = Mock(return_value=0.3)
        mock_ontology_evaluator.get_domain_recommendations = Mock(return_value="approve")
        mock_ontology_evaluator_class.return_value = mock_ontology_evaluator

        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)
        result = pipeline.evaluate_plan(sample_cognitive_plan, sample_context)

        metadata = result["metadata"]

        # Verificar scores semânticos
        assert "semantic_scores" in metadata
        assert "security" in metadata["semantic_scores"]
        assert "architecture" in metadata["semantic_scores"]
        assert "performance" in metadata["semantic_scores"]
        assert "quality" in metadata["semantic_scores"]

        # Verificar scores ontológicos
        assert "ontology_scores" in metadata
        assert "security" in metadata["ontology_scores"]
        assert "architecture" in metadata["ontology_scores"]

        # Verificar outros metadados
        assert metadata["evaluation_method"] == "semantic_pipeline"
        assert "domain" in metadata
        assert "num_tasks" in metadata

    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.SemanticAnalyzer")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.OntologyBasedEvaluator")
    def test_evaluate_plan_clamps_scores_to_valid_range(
        self,
        mock_ontology_evaluator_class,
        mock_semantic_analyzer_class,
        config,
        mock_feature_extractor,
        sample_cognitive_plan,
        sample_context,
    ):
        """Testa que scores são limitados ao intervalo [0, 1]."""
        # Mock que retorna valores inválidos
        mock_semantic_analyzer = Mock()
        mock_semantic_analyzer.analyze_security = Mock(return_value=1.5)  # > 1.0
        mock_semantic_analyzer.analyze_architecture = Mock(return_value=-0.2)  # < 0
        mock_semantic_analyzer.analyze_performance = Mock(return_value=0.6)
        mock_semantic_analyzer.analyze_code_quality = Mock(return_value=0.7)
        mock_semantic_analyzer_class.return_value = mock_semantic_analyzer

        mock_ontology_evaluator = Mock()
        mock_ontology_evaluator.evaluate_security_level = Mock(return_value=0.7)
        mock_ontology_evaluator.evaluate_architecture_compliance = Mock(return_value=0.65)
        mock_ontology_evaluator.evaluate_complexity = Mock(return_value=0.4)
        mock_ontology_evaluator.evaluate_risk_patterns = Mock(return_value=0.3)
        mock_ontology_evaluator.get_domain_recommendations = Mock(return_value="approve")
        mock_ontology_evaluator_class.return_value = mock_ontology_evaluator

        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)
        result = pipeline.evaluate_plan(sample_cognitive_plan, sample_context)

        # Verificar que scores estão clamped
        assert 0.0 <= result["confidence_score"] <= 1.0
        assert 0.0 <= result["risk_score"] <= 1.0

    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.SemanticAnalyzer")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_pipeline.OntologyBasedEvaluator")
    def test_evaluate_plan_reasoning_factors_structure(
        self,
        mock_ontology_evaluator_class,
        mock_semantic_analyzer_class,
        config,
        mock_feature_extractor,
        sample_cognitive_plan,
        sample_context,
    ):
        """Testa estrutura dos fatores de raciocínio."""
        mock_semantic_analyzer = Mock()
        mock_semantic_analyzer.analyze_security = Mock(return_value=0.8)
        mock_semantic_analyzer.analyze_architecture = Mock(return_value=0.7)
        mock_semantic_analyzer.analyze_performance = Mock(return_value=0.6)
        mock_semantic_analyzer.analyze_code_quality = Mock(return_value=0.75)
        mock_semantic_analyzer_class.return_value = mock_semantic_analyzer

        mock_ontology_evaluator = Mock()
        mock_ontology_evaluator.evaluate_security_level = Mock(return_value=0.7)
        mock_ontology_evaluator.evaluate_architecture_compliance = Mock(return_value=0.65)
        mock_ontology_evaluator.evaluate_complexity = Mock(return_value=0.4)
        mock_ontology_evaluator.evaluate_risk_patterns = Mock(return_value=0.3)
        mock_ontology_evaluator.get_domain_recommendations = Mock(return_value="approve")
        mock_ontology_evaluator_class.return_value = mock_ontology_evaluator

        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)
        result = pipeline.evaluate_plan(sample_cognitive_plan, sample_context)

        reasoning_factors = result["reasoning_factors"]

        # Verificar estrutura de cada fator
        expected_factors = [
            "semantic_security_analysis",
            "semantic_architecture_analysis",
            "semantic_performance_analysis",
            "semantic_quality_analysis",
            "complexity_evaluation",
            "risk_patterns",
        ]

        factor_names = [f["factor_name"] for f in reasoning_factors]
        for expected in expected_factors:
            assert expected in factor_names

        # Verificar campos de cada fator
        for factor in reasoning_factors:
            assert "factor_name" in factor
            assert "weight" in factor
            assert "score" in factor
            assert "description" in factor
            assert isinstance(factor["weight"], (int, float))
            assert isinstance(factor["score"], (int, float))
            assert isinstance(factor["description"], str)

    def test_mitigation_structure(self, config, mock_feature_extractor):
        """Testa estrutura das mitigações."""
        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import SemanticPipeline

        pipeline = SemanticPipeline(config, mock_feature_extractor)

        mitigations = pipeline._generate_mitigations(
            security_score=0.4,
            architecture_score=0.5,
            performance_score=0.4,
            quality_score=0.3,
        )

        # Verificar estrutura de cada mitigação
        for mitigation in mitigations:
            assert "mitigation_type" in mitigation
            assert "description" in mitigation
            assert "priority" in mitigation
            assert "estimated_effort" in mitigation
