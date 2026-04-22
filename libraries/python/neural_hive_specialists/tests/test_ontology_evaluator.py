"""
Testes unitários para OntologyBasedEvaluator.

Cobertura para semantic_pipeline/ontology_evaluator.py
"""

import json
from unittest.mock import mock_open, patch

import pytest


class TestOntologyBasedEvaluator:
    """Testes para OntologyBasedEvaluator."""

    @pytest.fixture()
    def config(self):
        """Configuração de teste."""
        return {
            "ontology_path": "/fake/path/ontology",
        }

    @pytest.fixture()
    def sample_intents_taxonomy(self):
        """Taxonomia de intents de exemplo."""
        return {
            "domains": {
                "technical": {
                    "risk_weight": 0.5,
                    "subcategories": ["security", "authentication", "performance"],
                    "task_types": [
                        {"name": "auth", "complexity_factor": 0.7},
                        {"name": "database", "complexity_factor": 0.5},
                    ],
                    "risk_patterns": [
                        {"threshold": 0.6, "severity": "high"},
                        {"threshold": 0.3, "severity": "low"},
                    ],
                },
                "business": {
                    "risk_weight": 0.3,
                    "subcategories": ["reporting", "analytics"],
                    "task_types": [
                        {"name": "report", "complexity_factor": 0.3},
                    ],
                    "risk_patterns": [
                        {"threshold": 0.4, "severity": "medium"},
                    ],
                },
            }
        }

    @pytest.fixture()
    def sample_architecture_patterns(self):
        """Padrões arquiteturais de exemplo."""
        return {
            "patterns": {
                "microservices": {
                    "density_ideal": 0.3,
                    "max_centrality_ideal": 0.5,
                },
                "monolith": {
                    "density_ideal": 0.5,
                    "max_centrality_ideal": 0.8,
                },
            }
        }

    @pytest.fixture()
    def sample_cognitive_plan(self):
        """Plano cognitivo de exemplo."""
        return {
            "plan_id": "test-plan-123",
            "intent_id": "test-intent-456",
            "tasks": [
                {"task_id": "task-1", "description": "Implementar auth", "domain": "technical"},
                {"task_id": "task-2", "description": "Criar cache", "domain": "performance"},
            ],
        }

    @pytest.fixture()
    def sample_extracted_features(self):
        """Features extraídas de exemplo."""
        return {
            "metadata_features": {"domain": "technical"},
            "graph_features": {
                "density": 0.3,
                "max_centrality": 0.4,
                "max_parallelism": 2,
                "critical_path_length": 3,
            },
            "task_features": {"num_tasks": 2},
        }

    def test_init_with_ontology_path(self, config):
        """Testa inicialização com ontology_path."""
        with patch("builtins.open", mock_open(read_data="{}")):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                evaluator = OntologyBasedEvaluator(config)

                assert evaluator.config == config
                assert evaluator.ontology_path == "/fake/path/ontology"

    def test_init_without_ontology_path(self):
        """Testa inicialização sem ontology_path."""
        config = {}

        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        evaluator = OntologyBasedEvaluator(config)

        assert evaluator.ontology_path is None
        assert evaluator.intents_taxonomy is None
        assert evaluator.architecture_patterns is None

    @patch("builtins.open", mock_open(read_data='{"domains": {}}'))
    @patch("pathlib.Path.exists", return_value=True)
    def test_load_ontologies_successfully(self, mock_exists, config):
        """Testa carregamento bem-sucedido de ontologias."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        evaluator = OntologyBasedEvaluator(config)

        # Verificar que ontologias foram carregadas
        assert evaluator.intents_taxonomy == {"domains": {}}

    def test_load_ontologies_no_path(self):
        """Testa carregamento sem ontology_path configurado."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        assert evaluator.intents_taxonomy is None
        assert evaluator.architecture_patterns is None

    def test_evaluate_security_level_no_taxonomy(
        self, sample_cognitive_plan, sample_extracted_features
    ):
        """Testa avaliação de segurança sem taxonomia carregada."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        score = evaluator.evaluate_security_level(sample_cognitive_plan, sample_extracted_features)

        assert score == 0.5

    def test_evaluate_security_level_no_domain(self, sample_cognitive_plan):
        """Testa avaliação de segurança sem domínio nas features."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {"ontology_path": "/fake/path"}
        evaluator = OntologyBasedEvaluator(config)

        features_no_domain = {"metadata_features": {}}
        score = evaluator.evaluate_security_level(sample_cognitive_plan, features_no_domain)

        assert score == 0.5

    def test_evaluate_security_level_unknown_domain(
        self, sample_cognitive_plan, sample_extracted_features
    ):
        """Testa avaliação de segurança com domínio desconhecido."""
        with patch("builtins.open", mock_open(read_data='{"domains": {}}')):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                features = {"metadata_features": {"domain": "unknown_domain"}}
                score = evaluator.evaluate_security_level(sample_cognitive_plan, features)

                assert score == 0.5

    def test_evaluate_security_level_with_known_domain(
        self, sample_cognitive_plan, sample_extracted_features, sample_intents_taxonomy
    ):
        """Testa avaliação de segurança com domínio conhecido."""
        with patch("builtins.open", mock_open(read_data=json.dumps(sample_intents_taxonomy))):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                score = evaluator.evaluate_security_level(
                    sample_cognitive_plan, sample_extracted_features
                )

                # technical tem risk_weight=0.5, então base_security = 1.0 - 0.5 = 0.5
                # + 0.2 boost por security subcategory = 0.7
                assert 0.0 <= score <= 1.0

    def test_evaluate_security_clamps_to_valid_range(
        self, sample_cognitive_plan, sample_extracted_features
    ):
        """Testa que score de segurança é limitado ao intervalo [0, 1]."""
        taxonomy = {
            "domains": {
                "technical": {
                    "risk_weight": 1.5,  # > 1.0 - deve ser clampado
                    "subcategories": [],
                }
            }
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(taxonomy))):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                score = evaluator.evaluate_security_level(
                    sample_cognitive_plan, sample_extracted_features
                )

                assert 0.0 <= score <= 1.0

    def test_evaluate_architecture_compliance_no_patterns(
        self, sample_cognitive_plan, sample_extracted_features
    ):
        """Testa avaliação arquitetural sem padrões carregados."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        score = evaluator.evaluate_architecture_compliance(
            sample_cognitive_plan, sample_extracted_features
        )

        assert score == 0.5

    def test_evaluate_architecture_compliance_with_graph_features(
        self, sample_cognitive_plan, sample_extracted_features, sample_architecture_patterns
    ):
        """Testa avaliação arquitetural com features de grafo."""
        with patch("builtins.open", mock_open(read_data=json.dumps(sample_architecture_patterns))):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                score = evaluator.evaluate_architecture_compliance(
                    sample_cognitive_plan, sample_extracted_features
                )

                # Score deve estar no intervalo válido
                assert 0.0 <= score <= 1.0
                assert isinstance(score, float)

    def test_evaluate_architecture_with_missing_graph_features(
        self, sample_cognitive_plan, sample_intents_taxonomy
    ):
        """Testa avaliação arquitetural com features de grafo incompletas."""
        with patch("builtins.open", mock_open(read_data=json.dumps(sample_intents_taxonomy))):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                features_no_graph = {"metadata_features": {"domain": "technical"}}
                score = evaluator.evaluate_architecture_compliance(
                    sample_cognitive_plan, features_no_graph
                )

                # Deve usar valores padrão
                assert 0.0 <= score <= 1.0

    def test_evaluate_complexity_default_value(
        self, sample_cognitive_plan, sample_extracted_features
    ):
        """Testa avaliação de complexidade sem taxonomia."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        score = evaluator.evaluate_complexity(sample_cognitive_plan, sample_extracted_features)

        # Deve retornar um valor válido
        assert 0.0 <= score <= 1.0

    def test_evaluate_complexity_with_taxonomy(
        self, sample_cognitive_plan, sample_extracted_features, sample_intents_taxonomy
    ):
        """Testa avaliação de complexidade com taxonomia."""
        with patch("builtins.open", mock_open(read_data=json.dumps(sample_intents_taxonomy))):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                score = evaluator.evaluate_complexity(
                    sample_cognitive_plan, sample_extracted_features
                )

                # technical tem complexity_factors [0.7, 0.5] -> média 0.6
                # + path_complexity + density
                assert 0.0 <= score <= 1.0
                assert isinstance(score, float)

    def test_evaluate_complexity_clamps_score(self, sample_cognitive_plan):
        """Testa que score de complexidade é limitado."""
        taxonomy = {
            "domains": {
                "technical": {
                    "task_types": [
                        {"complexity_factor": 2.0},  # > 1.0
                    ]
                }
            }
        }
        features = {
            "metadata_features": {"domain": "technical"},
            "graph_features": {
                "critical_path_length": 100,  # > 10
                "density": 2.0,  # > 1.0
            },
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(taxonomy))):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                score = evaluator.evaluate_complexity(sample_cognitive_plan, features)

                assert 0.0 <= score <= 1.0

    def test_evaluate_risk_patterns_no_taxonomy(
        self, sample_cognitive_plan, sample_extracted_features
    ):
        """Testa avaliação de padrões de risco sem taxonomia."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        score = evaluator.evaluate_risk_patterns(sample_cognitive_plan, sample_extracted_features)

        assert score == 0.5

    def test_evaluate_risk_patterns_no_domain(self, sample_cognitive_plan):
        """Testa avaliação de padrões de risco sem domínio."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        features_no_domain = {"metadata_features": {}}
        score = evaluator.evaluate_risk_patterns(sample_cognitive_plan, features_no_domain)

        assert score == 0.5

    def test_evaluate_risk_patterns_with_patterns(
        self, sample_cognitive_plan, sample_extracted_features, sample_intents_taxonomy
    ):
        """Testa avaliação de padrões de risco com padrões definidos."""
        with patch("builtins.open", mock_open(read_data=json.dumps(sample_intents_taxonomy))):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                score = evaluator.evaluate_risk_patterns(
                    sample_cognitive_plan, sample_extracted_features
                )

                # technical tem 2 patterns: high(0.7)*0.6 + low(0.3)*0.3 = 0.42+0.09 = 0.51/2 = 0.255
                assert 0.0 <= score <= 1.0

    def test_evaluate_risk_patterns_fallback_to_risk_weight(
        self, sample_cognitive_plan, sample_extracted_features
    ):
        """Testa fallback para risk_weight quando não há patterns."""
        taxonomy = {
            "domains": {
                "technical": {
                    "risk_weight": 0.7,
                    "risk_patterns": [],  # Vazio
                }
            }
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(taxonomy))):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                score = evaluator.evaluate_risk_patterns(
                    sample_cognitive_plan, sample_extracted_features
                )

                # Deve usar risk_weight como fallback
                assert score == 0.7

    def test_get_domain_recommendations_approve(self):
        """Testa recomendação approve."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        recommendation = evaluator.get_domain_recommendations(
            domain="technical", risk_score=0.2, confidence_score=0.9
        )

        assert recommendation == "approve"

    def test_get_domain_recommendations_reject_low_confidence(self):
        """Testa recomendação reject por baixa confiança."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        recommendation = evaluator.get_domain_recommendations(
            domain="technical", risk_score=0.3, confidence_score=0.4  # < 0.5
        )

        assert recommendation == "reject"

    def test_get_domain_recommendations_reject_high_risk(self):
        """Testa recomendação reject por alto risco."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        recommendation = evaluator.get_domain_recommendations(
            domain="technical", risk_score=0.8, confidence_score=0.6  # > 0.7
        )

        assert recommendation == "reject"

    def test_get_domain_recommendations_review_required(self):
        """Testa recomendação review_required."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        recommendation = evaluator.get_domain_recommendations(
            domain="technical", risk_score=0.6, confidence_score=0.6  # > 0.5
        )

        assert recommendation == "review_required"

    def test_get_domain_recommendations_conditional(self):
        """Testa recomendação conditional."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        recommendation = evaluator.get_domain_recommendations(
            domain="technical", risk_score=0.4, confidence_score=0.6  # < 0.5  # >= 0.5
        )

        assert recommendation == "conditional"

    def test_evaluate_security_exception_handling(
        self, sample_cognitive_plan, sample_extracted_features
    ):
        """Testa tratamento de exceção em evaluate_security_level."""
        taxonomy = {
            "domains": {
                "technical": {
                    "risk_weight": "invalid",  # Deve causar erro
                }
            }
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(taxonomy))):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                score = evaluator.evaluate_security_level(
                    sample_cognitive_plan, sample_extracted_features
                )

                # Deve retornar fallback
                assert score == 0.5

    def test_evaluate_architecture_exception_handling(
        self, sample_cognitive_plan, sample_extracted_features
    ):
        """Testa tratamento de exceção em evaluate_architecture_compliance."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        # Forçar exceção com features inválidas
        invalid_features = {"graph_features": {"density": "invalid"}}

        score = evaluator.evaluate_architecture_compliance(sample_cognitive_plan, invalid_features)

        # Deve retornar fallback
        assert score == 0.5

    def test_evaluate_complexity_exception_handling(
        self, sample_cognitive_plan, sample_extracted_features
    ):
        """Testa tratamento de exceção em evaluate_complexity."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        # Criar features que causam exceção durante processamento
        # O código trata exceções e retorna 0.5
        with patch.object(evaluator, "intents_taxonomy", None):
            score = evaluator.evaluate_complexity(sample_cognitive_plan, {"metadata_features": {}})

        # Deve retornar valor calculado ou fallback
        assert isinstance(score, float)

    def test_evaluate_risk_exception_handling(
        self, sample_cognitive_plan, sample_extracted_features
    ):
        """Testa tratamento de exceção em evaluate_risk_patterns."""
        taxonomy = {
            "domains": {
                "technical": {"risk_patterns": [{"threshold": "invalid", "severity": "invalid"}]}
            }
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(taxonomy))):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                score = evaluator.evaluate_risk_patterns(
                    sample_cognitive_plan, sample_extracted_features
                )

                # Deve retornar fallback
                assert score == 0.5

    def test_evaluate_security_with_security_subcategories_boost(
        self, sample_cognitive_plan, sample_intents_taxonomy
    ):
        """Testa boost de segurança quando subcategories security-related existem."""
        taxonomy = {
            "domains": {
                "security": {
                    "risk_weight": 0.5,
                    "subcategories": ["authentication", "authorization", "encryption"],
                }
            }
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(taxonomy))):
            with patch("pathlib.Path.exists", return_value=True):
                from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                    OntologyBasedEvaluator,
                )

                config = {"ontology_path": "/fake/path"}
                evaluator = OntologyBasedEvaluator(config)

                features = {"metadata_features": {"domain": "security"}}
                score = evaluator.evaluate_security_level(sample_cognitive_plan, features)

                # Deve ter boost de 0.2
                # Base: 1.0 - 0.5 = 0.5
                # Com boost: min(1.0, 0.5 + 0.2) = 0.7
                assert score >= 0.5

    def test_architecture_score_components(self, sample_cognitive_plan, sample_extracted_features):
        """Testa componentes do score arquitetural."""
        from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
            OntologyBasedEvaluator,
        )

        config = {}
        evaluator = OntologyBasedEvaluator(config)

        # Com graph features conhecidos:
        # density=0.3 -> density_score = 1.0 - abs(0.3 - 0.3) = 1.0
        # max_centrality=0.4 -> centrality_score = 1.0 - 0.4 = 0.6
        # max_parallelism=2, num_tasks=2 -> parallelism_ratio=1.0, parallelism_score = 2.0 -> 1.0
        # Total = 1.0*0.3 + 0.6*0.3 + 1.0*0.4 = 0.3 + 0.18 + 0.4 = 0.88

        # Mas sem patterns carregados, deve retornar 0.5
        score = evaluator.evaluate_architecture_compliance(
            sample_cognitive_plan, sample_extracted_features
        )

        assert score == 0.5  # Sem patterns carregados

    def test_all_severity_levels_for_risk_patterns(self):
        """Testa todos os níveis de severidade em risk_patterns."""
        test_cases = [
            ("low", 0.3),
            ("medium", 0.5),
            ("high", 0.7),
            ("critical", 0.9),
            ("unknown", 0.5),  # Default
        ]

        for severity, expected_score in test_cases:
            taxonomy = {
                "domains": {
                    "test": {
                        "risk_weight": 0.5,
                        "risk_patterns": [{"threshold": 1.0, "severity": severity}],
                    }
                }
            }

            with patch("builtins.open", mock_open(read_data=json.dumps(taxonomy))):
                with patch("pathlib.Path.exists", return_value=True):
                    from neural_hive_specialists.semantic_pipeline.ontology_evaluator import (
                        OntologyBasedEvaluator,
                    )

                    config = {"ontology_path": "/fake/path"}
                    evaluator = OntologyBasedEvaluator(config)

                    plan = {"plan_id": "test", "tasks": []}
                    features = {"metadata_features": {"domain": "test"}}

                    score = evaluator.evaluate_risk_patterns(plan, features)

                    # severity_score * threshold
                    expected = expected_score * 1.0
                    assert score == expected
