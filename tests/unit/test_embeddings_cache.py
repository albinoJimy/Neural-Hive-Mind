import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "libraries" / "python"))

from neural_hive_specialists.feature_extraction.embeddings_generator import (  # noqa: E402
    EmbeddingsGenerator,
)
from neural_hive_specialists.feature_extraction.feature_extractor import (  # noqa: E402
    FeatureExtractor,
)


class FakeModel:
    """Modelo de teste leve para gerar embeddings determinísticos."""

    def get_sentence_embedding_dimension(self):
        return 3

    def encode(self, sentences, convert_to_numpy=True, batch_size=None):
        if isinstance(sentences, str):
            sentences = [sentences]
        embeddings = []
        for text in sentences:
            value = float(len(text.strip()))
            embeddings.append(np.array([value, value + 1, value + 2], dtype=float))
        return np.stack(embeddings)


class DummyMetrics:
    """Coletor simples para validar chamadas de métricas."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.durations = []
        self.cache_sizes = []

    def increment_embedding_cache_hit(self):
        self.hits += 1

    def increment_embedding_cache_miss(self):
        self.misses += 1

    def observe_embedding_generation_duration(self, duration: float, cache_status: str):
        self.durations.append((cache_status, duration))

    def set_embedding_cache_size(self, size: int):
        self.cache_sizes.append(size)


def _build_generator(**kwargs) -> EmbeddingsGenerator:
    original_load = EmbeddingsGenerator._load_model
    EmbeddingsGenerator._load_model = lambda self: None
    try:
        generator = EmbeddingsGenerator(**kwargs)
    finally:
        EmbeddingsGenerator._load_model = original_load

    generator.model = FakeModel()
    generator.embedding_dim = generator.model.get_sentence_embedding_dimension()
    generator.clear_cache()
    return generator


def test_embeddings_cache_hit_and_miss():
    generator = _build_generator(cache_size=2, batch_size=4)

    tasks = [{'description': 'Test task'}]
    first_embeddings = generator.generate_task_embeddings(tasks)
    stats_after_miss = generator.get_cache_stats()

    second_embeddings = generator.generate_task_embeddings(tasks)
    stats_after_hit = generator.get_cache_stats()

    assert np.allclose(first_embeddings, second_embeddings)
    assert stats_after_hit['total_hits'] > stats_after_miss['total_hits']
    assert stats_after_hit['total_misses'] >= stats_after_miss['total_misses']


def test_embeddings_cache_normalizes_descriptions():
    generator = _build_generator(cache_size=2, batch_size=2)

    tasks = [{'description': '  Normalize Me  '}]
    generator.generate_task_embeddings(tasks)
    stats_after_first = generator.get_cache_stats()

    tasks_normalized = [{'description': 'normalize me'}]
    embeddings_second = generator.generate_task_embeddings(tasks_normalized)
    stats_after_second = generator.get_cache_stats()

    assert embeddings_second.shape == (1, generator.embedding_dim)
    assert stats_after_second['total_hits'] > stats_after_first['total_hits']


def test_cache_eviction_respects_max_size():
    generator = _build_generator(cache_size=1, batch_size=2)

    generator.generate_task_embeddings([{'description': 'first'}])
    generator.generate_task_embeddings([{'description': 'second'}])

    assert len(generator._embedding_cache) == 1
    assert list(generator._embedding_cache.keys())[0] == generator._hash_description('second')


def test_metrics_are_incremented_on_hits_and_misses():
    metrics = DummyMetrics()
    generator = _build_generator(cache_size=2, batch_size=2, metrics=metrics)

    generator.generate_task_embeddings([{'description': 'metrics'}])
    generator.generate_task_embeddings([{'description': 'metrics'}])

    assert metrics.hits >= 1
    assert metrics.misses >= 1
    assert metrics.cache_sizes[-1] <= 2
    assert any(status == 'miss' for status, _ in metrics.durations)


def test_feature_extractor_skips_embeddings_when_disabled():
    original_load = EmbeddingsGenerator._load_model
    EmbeddingsGenerator._load_model = lambda self: None
    try:
        extractor = FeatureExtractor(config={}, metrics=None)
    finally:
        EmbeddingsGenerator._load_model = original_load

    extractor.embeddings_generator.model = FakeModel()
    extractor.embeddings_generator.embedding_dim = extractor.embeddings_generator.model.get_sentence_embedding_dimension()

    plan = {
        'plan_id': 'skip-embeddings',
        'tasks': [{'description': 'skip me', 'dependencies': []}],
        'original_domain': 'test',
        'original_priority': 'normal'
    }

    features = extractor.extract_features(plan, include_embeddings=False)

    assert features['embedding_features'] == {}
    assert 'mean_norm' not in features['aggregated_features']


def test_generate_embeddings_batch_handles_multiple_plans():
    generator = _build_generator(cache_size=4, batch_size=3)

    plans = [
        {'tasks': [{'description': 'plan one task one'}, {'description': 'plan one task two'}]},
        {'tasks': [{'description': 'plan two task one'}]},
    ]

    batched = generator.generate_embeddings_batch(plans)

    assert len(batched) == len(plans)
    assert batched[0].shape[0] == 2
    assert batched[1].shape[0] == 1


def test_empty_tasks_returns_zero_embeddings_and_stats():
    generator = _build_generator(cache_size=2, batch_size=2)

    empty_embeddings = generator.generate_task_embeddings([])
    assert empty_embeddings.shape == (0, generator.embedding_dim)

    stats = generator.extract_statistical_features(empty_embeddings)
    assert stats == {
        'mean_norm': 0.0,
        'std_norm': 0.0,
        'max_norm': 0.0,
        'min_norm': 0.0,
        'avg_diversity': 0.0
    }
