import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT / "libraries" / "python"))

from neural_hive_specialists.feature_extraction.ontology_mapper import (  # noqa: E402
    OntologyMapper,
)


class DummyEmbeddingsGenerator:
    """Gerador de embeddings determinístico para testes."""

    def __init__(self):
        self.embedding_dim = 3

    def get_embeddings(self, descriptions):
        embeddings = []
        for desc in descriptions:
            value = float(len(desc))
            embeddings.append(np.array([value, value + 1, value + 2], dtype=float))
        return embeddings


def test_indicator_embeddings_precomputed():
    """Valida que embeddings de indicadores são pré-computados no __init__()."""
    mapper = OntologyMapper(embeddings_generator=DummyEmbeddingsGenerator())
    assert len(mapper._indicator_embeddings_cache) > 0
    assert 'service' in mapper._indicator_embeddings_cache


def test_semantic_similarity_threshold_configurable():
    """Valida que threshold é configurável."""
    mapper = OntologyMapper(
        embeddings_generator=DummyEmbeddingsGenerator(),
        semantic_similarity_threshold=0.5
    )
    assert mapper.semantic_similarity_threshold == 0.5


def test_calculate_semantic_matches_batch():
    """Valida que _calculate_semantic_matches usa batch processing."""
    mock_embeddings_gen = DummyEmbeddingsGenerator()
    mapper = OntologyMapper(embeddings_generator=mock_embeddings_gen)

    call_count = 0
    original_method = mock_embeddings_gen.get_embeddings

    def counting_wrapper(descriptions):
        nonlocal call_count
        call_count += 1
        return original_method(descriptions)

    mock_embeddings_gen.get_embeddings = counting_wrapper

    mapper._indicator_embeddings_cache = {
        'indicator1': np.array([1.0, 1.0, 1.0]),
        'indicator2': np.array([2.0, 2.0, 2.0])
    }

    mapper._calculate_semantic_matches(
        task_descriptions=['task1', 'task2', 'task3'],
        indicators=['indicator1', 'indicator2']
    )

    assert call_count == 1


def test_semantic_match_average_rule():
    """
    Garante que a contagem de matches usa a média das similaridades.
    Um indicador alto e outro baixo deve ainda considerar a média final.
    """
    class CustomGen(DummyEmbeddingsGenerator):
        def get_embeddings(self, descriptions):
            # Primeiro elemento para tarefa 1 terá norma alta, tarefa 2 baixa
            embeddings = []
            for desc in descriptions:
                if desc == "high_match":
                    embeddings.append(np.array([10.0, 0.0, 0.0]))
                elif desc == "low_match":
                    embeddings.append(np.array([0.1, 0.0, 0.0]))
                elif desc.startswith("indicator_high"):
                    embeddings.append(np.array([10.0, 0.0, 0.0]))
                else:
                    embeddings.append(np.array([0.0, 10.0, 0.0]))
            return embeddings

    gen = CustomGen()
    mapper = OntologyMapper(
        embeddings_generator=gen,
        semantic_similarity_threshold=0.5
    )

    mapper._indicator_embeddings_cache = {
        'indicator_high': np.array([10.0, 0.0, 0.0]),
        'indicator_low': np.array([0.0, 10.0, 0.0])
    }

    matches = mapper._calculate_semantic_matches(
        task_descriptions=["high_match", "low_match"],
        indicators=["indicator_high", "indicator_low"]
    )

    # high_match -> média ~0.5 (um alto, um baixo) => conta
    # low_match -> média baixa => não conta
    assert matches == 1
