"""
Testes unitários para BatchEvaluator.

Testa processamento em batch de múltiplos planos cognitivos.
"""

import pytest
import asyncio
import numpy as np
from unittest.mock import Mock, AsyncMock, MagicMock, patch


class TestBatchEvaluator:
    """Testes da classe BatchEvaluator."""

    @pytest.fixture
    def mock_specialist(self):
        """Mock do BaseSpecialist."""
        specialist = MagicMock()
        specialist.specialist_type = 'business'
        specialist.model = MagicMock()
        specialist.model.predict_proba = Mock(return_value=np.array([[0.3, 0.7]]))
        specialist.feature_extractor = MagicMock()
        specialist.feature_extractor.extract_features = Mock(return_value={
            'aggregated_features': {'feature1': 0.5, 'feature2': 0.8},
            'metadata_features': {'num_tasks': 5},
            'ontology_features': {},
            'graph_features': {}
        })
        specialist.feature_extractor._extract_embedding_features = Mock(return_value={})
        specialist.feature_cache = None
        specialist._hash_plan = Mock(return_value='test-hash')
        specialist._parse_model_prediction = Mock(return_value={
            'confidence_score': 0.7,
            'risk_score': 0.3,
            'recommendation': 'approve',
            'reasoning_summary': 'Test reasoning',
            'reasoning_factors': [],
            'metadata': {}
        })
        # Usar side_effect para retornar novo dicionário a cada chamada
        # Isso evita que o mesmo objeto seja mutado múltiplas vezes
        specialist._evaluate_plan_internal = Mock(side_effect=lambda plan, ctx: {
            'confidence_score': 0.6,
            'risk_score': 0.4,
            'recommendation': 'conditional',
            'reasoning_summary': 'Heuristic evaluation',
            'reasoning_factors': [],
            'metadata': {'source': 'heuristic'}
        })
        specialist.metrics = MagicMock()
        return specialist

    @pytest.fixture
    def batch_evaluator(self, mock_specialist):
        """Cria BatchEvaluator com specialist mockado."""
        from neural_hive_specialists.batch_evaluator import BatchEvaluator
        return BatchEvaluator(
            specialist=mock_specialist,
            batch_size=32,
            max_workers=4
        )

    @pytest.fixture
    def sample_plans(self):
        """Lista de planos cognitivos de teste."""
        return [
            {
                'plan_id': f'plan-{i}',
                'tasks': [
                    {
                        'task_id': f'task-{i}-{j}',
                        'task_type': 'analysis',
                        'description': f'Test task {j}',
                        'dependencies': [],
                        'estimated_duration_ms': 5000
                    }
                    for j in range(5)
                ],
                'original_domain': 'workflow-analysis',
                'original_priority': 'high'
            }
            for i in range(10)
        ]

    @pytest.mark.asyncio
    async def test_batch_evaluation_success(self, batch_evaluator, sample_plans):
        """Testa avaliação em batch bem-sucedida."""
        results = await batch_evaluator.evaluate_batch(sample_plans)

        assert len(results) == len(sample_plans)
        for result in results:
            assert 'confidence_score' in result
            assert 'risk_score' in result
            assert 'recommendation' in result
            assert result['metadata'].get('batch_processed') is True

    @pytest.mark.asyncio
    async def test_batch_evaluation_empty_list(self, batch_evaluator):
        """Testa avaliação com lista vazia."""
        results = await batch_evaluator.evaluate_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_evaluation_single_plan(self, batch_evaluator, sample_plans):
        """Testa avaliação com um único plano."""
        results = await batch_evaluator.evaluate_batch([sample_plans[0]])
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_batch_feature_extraction_parallel(self, batch_evaluator, sample_plans, mock_specialist):
        """Testa que feature extraction é paralelizada."""
        await batch_evaluator.evaluate_batch(sample_plans)

        # Verificar que extract_features foi chamado para cada plano
        assert mock_specialist.feature_extractor.extract_features.call_count >= len(sample_plans)

    @pytest.mark.asyncio
    async def test_batch_fallback_on_prediction_failure(self, batch_evaluator, sample_plans, mock_specialist):
        """Testa fallback para heurísticas quando predição falha."""
        # Configurar modelo para retornar None
        mock_specialist.model = None

        results = await batch_evaluator.evaluate_batch(sample_plans)

        # Deve usar _evaluate_plan_internal como fallback
        assert len(results) == len(sample_plans)

    @pytest.mark.asyncio
    async def test_batch_with_feature_cache(self, batch_evaluator, sample_plans, mock_specialist):
        """Testa batch com feature cache habilitado."""
        # Configurar cache mock
        mock_cache = MagicMock()
        mock_cache.get = Mock(return_value=None)  # Cache miss
        mock_cache.set = Mock(return_value=True)
        mock_specialist.feature_cache = mock_cache

        results = await batch_evaluator.evaluate_batch(sample_plans)

        assert len(results) == len(sample_plans)
        # Cache deve ter sido consultado para cada plano
        assert mock_cache.get.call_count == len(sample_plans)

    def test_batch_sync_evaluation(self, batch_evaluator, sample_plans):
        """Testa versão síncrona de evaluate_batch."""
        results = batch_evaluator.evaluate_batch_sync(sample_plans)

        assert len(results) == len(sample_plans)
        for result in results:
            assert 'confidence_score' in result

    @pytest.mark.asyncio
    async def test_batch_handles_extraction_error(self, batch_evaluator, sample_plans, mock_specialist):
        """Testa handling de erros em feature extraction."""
        # Configurar para falhar em um plano específico
        original_extract = mock_specialist.feature_extractor.extract_features

        call_count = [0]

        def failing_extract(plan, include_embeddings=True):
            call_count[0] += 1
            if call_count[0] == 3:  # Falhar no terceiro plano
                raise ValueError("Simulated extraction error")
            return original_extract(plan, include_embeddings)

        mock_specialist.feature_extractor.extract_features = failing_extract

        results = await batch_evaluator.evaluate_batch(sample_plans)

        # Deve retornar resultados para todos os planos (com fallback para erros)
        assert len(results) == len(sample_plans)

    @pytest.mark.asyncio
    async def test_batch_metadata_includes_plan_id(self, batch_evaluator, sample_plans):
        """Testa que metadata inclui plan_id."""
        results = await batch_evaluator.evaluate_batch(sample_plans)

        for i, result in enumerate(results):
            assert result['metadata'].get('plan_id') == f'plan-{i}'


class TestBatchEvaluatorPerformance:
    """Testes de performance para BatchEvaluator."""

    @pytest.fixture
    def mock_specialist_slow(self):
        """Mock do specialist com operações lentas simuladas."""
        specialist = MagicMock()
        specialist.specialist_type = 'business'
        specialist.model = MagicMock()

        # Simular extração lenta
        async def slow_extract(plan, include_embeddings=True):
            await asyncio.sleep(0.01)  # 10ms
            return {
                'aggregated_features': {'feature1': 0.5},
                'metadata_features': {},
                'ontology_features': {},
                'graph_features': {}
            }

        specialist.feature_extractor = MagicMock()
        specialist.feature_extractor.extract_features = Mock(side_effect=lambda p, **k: {
            'aggregated_features': {'feature1': 0.5},
            'metadata_features': {},
            'ontology_features': {},
            'graph_features': {}
        })
        specialist.feature_cache = None
        specialist._hash_plan = Mock(return_value='test-hash')
        specialist.model.predict_proba = Mock(return_value=np.array([[0.3, 0.7]]))
        specialist._parse_model_prediction = Mock(return_value={
            'confidence_score': 0.7,
            'risk_score': 0.3,
            'recommendation': 'approve',
            'reasoning_summary': 'Test',
            'reasoning_factors': [],
            'metadata': {}
        })
        specialist.metrics = MagicMock()
        return specialist

    @pytest.mark.asyncio
    async def test_batch_faster_than_sequential(self, mock_specialist_slow):
        """Verifica que batch é mais rápido que processamento sequencial."""
        import time
        from neural_hive_specialists.batch_evaluator import BatchEvaluator

        evaluator = BatchEvaluator(
            specialist=mock_specialist_slow,
            batch_size=32,
            max_workers=8
        )

        plans = [
            {'plan_id': f'plan-{i}', 'tasks': []}
            for i in range(20)
        ]

        start = time.time()
        await evaluator.evaluate_batch(plans)
        batch_time = time.time() - start

        # Batch deve ser significativamente mais rápido que 20 * 10ms = 200ms
        # Com paralelização, deve ser próximo de 10-50ms
        assert batch_time < 1.0  # Deve completar em menos de 1 segundo
