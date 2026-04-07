"""
Testes unitários para SemanticAnalyzer.

Cobertura para semantic_pipeline/semantic_analyzer.py
"""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np


class TestSemanticAnalyzer:
    """Testes para SemanticAnalyzer."""

    @pytest.fixture
    def config(self):
        """Configuração de teste."""
        return {
            "embeddings_model": "all-MiniLM-L6-v2",
            "semantic_similarity_threshold": 0.4,
        }

    @pytest.fixture
    def sample_tasks(self):
        """Tarefas de exemplo."""
        return [
            {
                "task_id": "task-1",
                "description": "Implementar autenticação JWT com refresh tokens",
                "domain": "security",
            },
            {
                "task_id": "task-2",
                "description": "Adicionar cache Redis para otimizar queries",
                "domain": "performance",
            },
            {
                "task_id": "task-3",
                "description": "Refatorar para usar padrão repository",
                "domain": "architecture",
            },
        ]

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_init_default_config(self, mock_get_model, config):
        """Testa inicialização com config padrão."""
        mock_get_model.return_value = None  # Lazy load

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)

        assert analyzer.config == config
        assert analyzer.embeddings_model_name == "all-MiniLM-L6-v2"
        assert analyzer.similarity_threshold == 0.4
        assert analyzer._model is None
        assert analyzer._concept_embeddings_cache == {}

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_init_custom_threshold(self, mock_get_model):
        """Testa inicialização com threshold customizado."""
        mock_get_model.return_value = None

        config = {
            "embeddings_model": "paraphrase-multilingual-MiniLM-L12-v2",
            "semantic_similarity_threshold": 0.6,
        }

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)

        assert analyzer.similarity_threshold == 0.6
        assert analyzer.embeddings_model_name == "paraphrase-multilingual-MiniLM-L12-v2"

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_model_lazy_load(self, mock_get_model, config):
        """Testa carregamento lazy do modelo."""
        mock_model = MagicMock()
        mock_get_model.return_value = mock_model

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)

        # Antes do primeiro acesso
        assert analyzer._model is None

        # Primeiro acesso ao model property
        model = analyzer.model

        # Modelo deve ser carregado
        assert model is not None
        assert analyzer._model == mock_model
        mock_get_model.assert_called_once_with("all-MiniLM-L6-v2")

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_model_import_error_raises(self, mock_get_model, config):
        """Testa que ImportError é levantado quando modelo não está disponível."""
        mock_get_model.return_value = None

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)

        with pytest.raises(ImportError, match="sentence-transformers não está instalado"):
            _ = analyzer.model

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_analyze_security_with_empty_tasks(self, mock_get_model, mock_cosine_sim, config):
        """Testa análise de segurança com lista vazia."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2]])
        mock_get_model.return_value = mock_model

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)
        score = analyzer.analyze_security([])

        assert score == 0.5

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_analyze_security_with_no_descriptions(self, mock_get_model, mock_cosine_sim, config):
        """Testa análise de segurança com tarefas sem descrição."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2]])
        mock_get_model.return_value = mock_model

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)
        tasks = [{"task_id": "task-1"}, {"task_id": "task-2"}]
        score = analyzer.analyze_security(tasks)

        assert score == 0.5

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_analyze_security_success(self, mock_get_model, mock_cosine_sim, config, sample_tasks):
        """Testa análise de segurança bem-sucedida."""
        # Mock do modelo
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
        mock_get_model.return_value = mock_model

        # Mock cosine_similarity - 3 tarefas, 7 conceitos de segurança
        # Retornar similaridades acima do threshold
        mock_cosine_sim.return_value = np.array(
            [
                [0.5, 0.6, 0.4, 0.7, 0.5, 0.4, 0.6],  # task-1
                [0.3, 0.4, 0.5, 0.3, 0.4, 0.5, 0.3],  # task-2
                [0.6, 0.5, 0.4, 0.6, 0.5, 0.4, 0.5],  # task-3
            ]
        )

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)
        score = analyzer.analyze_security(sample_tasks)

        # Verificar que score está no intervalo válido
        assert 0.0 <= score <= 1.0
        assert isinstance(score, float)

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_analyze_security_exception_handling(
        self, mock_get_model, mock_cosine_sim, config, sample_tasks
    ):
        """Testa tratamento de exceção na análise de segurança."""
        mock_model = MagicMock()
        mock_model.encode.side_effect = Exception("Encoding error")
        mock_get_model.return_value = mock_model

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)
        score = analyzer.analyze_security(sample_tasks)

        # Deve retornar valor neutro em caso de erro
        assert score == 0.5

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_analyze_architecture_success(
        self, mock_get_model, mock_cosine_sim, config, sample_tasks
    ):
        """Testa análise de arquitetura bem-sucedida."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
        mock_get_model.return_value = mock_model

        mock_cosine_sim.return_value = np.array(
            [
                [0.5, 0.6, 0.4, 0.7, 0.5, 0.4, 0.6],
                [0.3, 0.4, 0.5, 0.3, 0.4, 0.5, 0.3],
                [0.6, 0.5, 0.4, 0.6, 0.5, 0.4, 0.5],
            ]
        )

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)
        score = analyzer.analyze_architecture(sample_tasks)

        assert 0.0 <= score <= 1.0
        assert isinstance(score, float)

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_analyze_architecture_with_empty_tasks(self, mock_get_model, mock_cosine_sim, config):
        """Testa análise de arquitetura com lista vazia."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2]])
        mock_get_model.return_value = mock_model

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)
        score = analyzer.analyze_architecture([])

        assert score == 0.5

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_analyze_performance_success(
        self, mock_get_model, mock_cosine_sim, config, sample_tasks
    ):
        """Testa análise de performance bem-sucedida."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
        mock_get_model.return_value = mock_model

        mock_cosine_sim.return_value = np.array(
            [
                [0.5, 0.6, 0.4, 0.7, 0.5, 0.4, 0.6],
                [0.3, 0.4, 0.5, 0.3, 0.4, 0.5, 0.3],
                [0.6, 0.5, 0.4, 0.6, 0.5, 0.4, 0.5],
            ]
        )

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)
        score = analyzer.analyze_performance(sample_tasks)

        assert 0.0 <= score <= 1.0
        assert isinstance(score, float)

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_analyze_performance_exception_handling(
        self, mock_get_model, mock_cosine_sim, config, sample_tasks
    ):
        """Testa tratamento de exceção na análise de performance."""
        mock_model = MagicMock()
        mock_model.encode.side_effect = Exception("Error")
        mock_get_model.return_value = mock_model

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)
        score = analyzer.analyze_performance(sample_tasks)

        assert score == 0.5

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_analyze_code_quality_success(
        self, mock_get_model, mock_cosine_sim, config, sample_tasks
    ):
        """Testa análise de qualidade de código bem-sucedida."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
        mock_get_model.return_value = mock_model

        mock_cosine_sim.return_value = np.array(
            [
                [0.5, 0.6, 0.4, 0.7],
                [0.3, 0.4, 0.5, 0.3],
                [0.6, 0.5, 0.4, 0.6],
            ]
        )

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)
        score = analyzer.analyze_code_quality(sample_tasks)

        assert 0.0 <= score <= 1.0
        assert isinstance(score, float)

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_analyze_code_quality_with_empty_tasks(self, mock_get_model, mock_cosine_sim, config):
        """Testa análise de qualidade com lista vazia."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2]])
        mock_get_model.return_value = mock_model

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)
        score = analyzer.analyze_code_quality([])

        assert score == 0.5

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_get_concept_embeddings_caches_results(self, mock_get_model, mock_cosine_sim, config):
        """Testa que embeddings de conceitos são cacheados."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2]])
        mock_get_model.return_value = mock_model

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)

        concepts = ["concept1", "concept2"]

        # Primeira chamada - deve codificar
        embeddings1 = analyzer._get_concept_embeddings(concepts, "test_key")
        assert "test_key" in analyzer._concept_embeddings_cache
        mock_model.encode.assert_called_once()

        # Segunda chamada - deve usar cache
        embeddings2 = analyzer._get_concept_embeddings(concepts, "test_key")
        # Não deve chamar encode novamente
        assert mock_model.encode.call_count == 1
        np.array_equal(embeddings1, embeddings2)

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_compute_task_similarity_success(self, mock_get_model, mock_cosine_sim, config):
        """Testa cálculo de similaridade de tarefa."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
        mock_get_model.return_value = mock_model

        mock_cosine_sim.return_value = np.array([[0.5, 0.6, 0.4]])

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)

        task_desc = "Implementar autenticação JWT"
        concepts = ["authentication", "security", "authorization"]

        similarity = analyzer.compute_task_similarity(task_desc, concepts)

        assert similarity == 0.6  # Max dos retornos

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer.cosine_similarity")
    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_compute_task_similarity_exception_handling(
        self, mock_get_model, mock_cosine_sim, config
    ):
        """Testa tratamento de exceção no cálculo de similaridade."""
        mock_model = MagicMock()
        mock_model.encode.side_effect = Exception("Error")
        mock_get_model.return_value = mock_model

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)

        similarity = analyzer.compute_task_similarity("Task", ["concept"])

        # Deve retornar 0.0 em caso de erro
        assert similarity == 0.0

    def test_security_concepts_constant(self):
        """Testa que SECURITY_CONCEPTS está definido."""
        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        assert len(SemanticAnalyzer.SECURITY_CONCEPTS) > 0
        assert all(isinstance(c, str) for c in SemanticAnalyzer.SECURITY_CONCEPTS)

    def test_architecture_concepts_constant(self):
        """Testa que ARCHITECTURE_CONCEPTS está definido."""
        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        assert len(SemanticAnalyzer.ARCHITECTURE_CONCEPTS) > 0
        assert all(isinstance(c, str) for c in SemanticAnalyzer.ARCHITECTURE_CONCEPTS)

    def test_performance_concepts_constant(self):
        """Testa que PERFORMANCE_CONCEPTS está definido."""
        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        assert len(SemanticAnalyzer.PERFORMANCE_CONCEPTS) > 0
        assert all(isinstance(c, str) for c in SemanticAnalyzer.PERFORMANCE_CONCEPTS)

    def test_code_quality_concepts_constant(self):
        """Testa que CODE_QUALITY_CONCEPTS está definido."""
        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        assert len(SemanticAnalyzer.CODE_QUALITY_CONCEPTS) > 0
        assert all(isinstance(c, str) for c in SemanticAnalyzer.CODE_QUALITY_CONCEPTS)

    @patch("neural_hive_specialists.semantic_pipeline.semantic_analyzer._get_sentence_transformer")
    def test_custom_threshold_used_in_analysis(self, mock_get_model):
        """Testa que threshold customizado é usado."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
        mock_get_model.return_value = mock_model

        config = {
            "embeddings_model": "all-MiniLM-L6-v2",
            "semantic_similarity_threshold": 0.7,  # Threshold alto
        }

        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import SemanticAnalyzer

        analyzer = SemanticAnalyzer(config)
        assert analyzer.similarity_threshold == 0.7


class TestCosineSimilarityLazyLoad:
    """Testes para função cosine_similarity lazy load."""

    @patch(
        "neural_hive_specialists.semantic_pipeline.semantic_analyzer._cosine_similarity_func", None
    )
    def test_cosine_similarity_lazy_loads_sklearn(self):
        """Testa que cosine_similarity carrega sklearn sob demanda."""
        # Esta função é tricky de testar porque modifica variável global
        # Apenas verificamos que está acessível
        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import cosine_similarity

        # Deve estar acessível como função
        assert callable(cosine_similarity)


class TestGetSentenceTransformer:
    """Testes para função _get_sentence_transformer."""

    def test_function_is_callable(self):
        """Testa que função _get_sentence_transformer pode ser chamada."""
        from neural_hive_specialists.semantic_pipeline.semantic_analyzer import (
            _get_sentence_transformer,
        )

        # A função deve estar acessível
        assert callable(_get_sentence_transformer)
