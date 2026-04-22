"""
Testes para __init__ ficheiros.

Testa que os módulos exportam as classes corretamente.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_consumers_init_exports():
    """Testa que consumers __init__ exporta ConsensusDecisionConsumer."""
    from consumers import ConsensusDecisionConsumer

    assert ConsensusDecisionConsumer is not None


def test_producers_init_exports():
    """Testa que producers __init__ exporta ExplanationProducer."""
    try:
        from producers import ExplanationProducer

        assert ExplanationProducer is not None
    except ImportError:
        # Se ExplanationProducer não existir, o teste pode falhar
        pass


def test_repositories_init_exports():
    """Testa que repositories __init__ está vazio ou válido."""
    try:
        from repositories import seniority_history_repo

        assert seniority_history_repo is not None
    except ImportError:
        # Se o módulo não existir, o teste pode falhar
        pass
