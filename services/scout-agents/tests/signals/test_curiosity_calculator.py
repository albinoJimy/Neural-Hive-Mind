"""
Testes para CuriosityCalculator.
Calcula score de curiosidade para decidir áreas interessantes para exploração.
"""
import pytest
from src.signals.curiosity_calculator import CuriosityCalculator
from src.exploration.codebase_explorer import CodebaseExplorer
import tempfile
from pathlib import Path


@pytest.fixture
def curiosity_calculator():
    """Instância de CuriosityCalculator para testes."""
    return CuriosityCalculator()


@pytest.fixture
def sample_codebase():
    """Cria codebase temporário para testes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Criar arquivos com diferentes níveis de "interesse"
        files = {
            'boring.py': '''
# Arquivo simples, pouco interessante
x = 1
y = 2
def add(a, b):
    return a + b
''',
            'interesting.py': '''
# Arquivo com padrões interessantes
from abc import ABC, abstractmethod

class Strategy(ABC):
    @abstractmethod
    def execute(self):
        pass

class ConcreteStrategy(Strategy):
    def execute(self):
        return "concrete"
''',
            'complex.py': '''
# Arquivo complexo com múltiplos padrões
from typing import Protocol, TypeVar, Generic
from dataclasses import dataclass
from enum import Enum

class State(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

@dataclass
class Config:
    timeout: int

class Context:
    def __init__(self):
        self._state = State.ACTIVE
        self._observers = []

    def attach(self, observer):
        self._observers.append(observer)

    def notify(self):
        for obs in self._observers:
            obs.update()

    def transition(self):
        if self._state == State.ACTIVE:
            self._state = State.INACTIVE
''',
        }
        for filename, content in files.items():
            Path(tmpdir, filename).write_text(content)

        yield tmpdir


class TestCuriosityScoreBasic:
    """Testes básicos de cálculo de curiosidade."""

    def test_calculate_score_simple_file(self, curiosity_calculator, sample_codebase):
        """Testa score de arquivo simples."""
        explorer = CodebaseExplorer(sample_codebase)
        boring_file = str(Path(sample_codebase) / 'boring.py')

        with open(boring_file, 'r') as f:
            code = f.read()

        score = curiosity_calculator.calculate_score(code, boring_file)

        # Arquivo simples deve ter score baixo
        assert 0 <= score <= 100
        assert score < 30

    def test_calculate_score_interesting_file(self, curiosity_calculator, sample_codebase):
        """Testa score de arquivo com padrões."""
        explorer = CodebaseExplorer(sample_codebase)
        interesting_file = str(Path(sample_codebase) / 'interesting.py')

        with open(interesting_file, 'r') as f:
            code = f.read()

        score = curiosity_calculator.calculate_score(code, interesting_file)

        # Arquivo com padrões deve ter score maior
        assert 0 <= score <= 100
        assert score > 30

    def test_calculate_score_complex_file(self, curiosity_calculator, sample_codebase):
        """Testa score de arquivo complexo."""
        complex_file = str(Path(sample_codebase) / 'complex.py')

        with open(complex_file, 'r') as f:
            code = f.read()

        score = curiosity_calculator.calculate_score(code, complex_file)

        # Arquivo complexo deve ter score alto
        assert 0 <= score <= 100
        assert score > 50


class TestCuriosityFactors:
    """Testes de fatores específicos de curiosidade."""

    def test_high_complexity_factor(self, curiosity_calculator):
        """Testa fator de complexidade ciclomática."""
        code = '''
def complex_function(x):
    if x > 0:
        if x > 10:
            if x > 100:
                for i in range(x):
                    if i % 2 == 0:
                        return i
    return 0
'''
        score = curiosity_calculator.calculate_score(code, "complex.py")

        # Alta complexidade aumenta score
        assert score > 10

    def test_pattern_density_factor(self, curiosity_calculator):
        """Testa fator de densidade de padrões."""
        code = '''
class Repository:
    def find(self):
        pass

class Service:
    def __init__(self, repo):
        self.repo = repo

class Factory:
    @staticmethod
    def create():
        return Service(Repository())

class Singleton:
    _instance = None
'''
        score = curiosity_calculator.calculate_score(code, "patterns.py")

        # Múltiplos padrões aumentam score significativamente
        assert score > 25

    def test_unknown_keywords_factor(self, curiosity_calculator):
        """Testa fator de palavras-chave desconhecidas."""
        code = '''
import some_unknown_library
from mysterious_module import UnknownClass

def function():
    obscure_pattern = True
    return enigmatic_result
'''
        score = curiosity_calculator.calculate_score(code, "unknown.py")

        # Palavras desconhecidas aumentam curiosidade
        assert score > 10

    def test_comment_ratio_factor(self, curiosity_calculator):
        """Testa fator de ratio de comentários."""
        code_with_docs = '''
"""
Este módulo implementa um padrão complexo.

A implementação usa múltiplas abordagens:
1. Strategy pattern para execução
2. Observer pattern para notificações
"""

class WellDocumented:
    """Classe bem documentada."""
    pass
'''
        score = curiosity_calculator.calculate_score(code_with_docs, "documented.py")

        # Documentação aumenta score
        assert score > 5


class TestCuriosityComparison:
    """Testes de comparação de curiosidade."""

    def test_rank_files_by_curiosity(self, curiosity_calculator, sample_codebase):
        """Testa ordenação de arquivos por curiosidade."""
        explorer = CodebaseExplorer(sample_codebase)

        files = [
            str(Path(sample_codebase) / 'boring.py'),
            str(Path(sample_codebase) / 'interesting.py'),
            str(Path(sample_codebase) / 'complex.py'),
        ]

        scores = []
        for filepath in files:
            with open(filepath, 'r') as f:
                code = f.read()
            scores.append((filepath, curiosity_calculator.calculate_score(code, filepath)))

        # Ordenar por score
        scores.sort(key=lambda x: x[1], reverse=True)

        # complex.py deve ter o maior score
        assert 'complex.py' in scores[0][0]
        # boring.py deve ter o menor score
        assert 'boring.py' in scores[-1][0]

    def test_threshold_filtering(self, curiosity_calculator, sample_codebase):
        """Testa filtragem por threshold de curiosidade."""
        threshold = 25

        interesting_files = []
        for filepath in Path(sample_codebase).glob('*.py'):
            with open(filepath, 'r') as f:
                code = f.read()
            score = curiosity_calculator.calculate_score(code, str(filepath))
            if score >= threshold:
                interesting_files.append((filepath.name, score))

        # Deve ter pelo menos 2 arquivos "interessantes"
        assert len(interesting_files) >= 2


class TestCuriosityDecay:
    """Testes de decaimento de curiosidade."""

    def test_recently_visited_lower_score(self, curiosity_calculator):
        """Testa que arquivos visitados recentemente têm score reduzido."""
        code = '''
class InterestingClass:
    def method(self):
        pass
'''
        filename = "interesting.py"

        # Primeira visita - score original
        original_score = curiosity_calculator.calculate_score(code, filename)

        # Registrar visita
        curiosity_calculator.mark_visited(filename)

        # Segunda visita - score deve ser menor
        decayed_score = curiosity_calculator.calculate_score(code, filename, consider_visits=True)

        assert decayed_score < original_score

    def test_decay_factor_configurable(self, curiosity_calculator):
        """Testa que fator de decaimento é configurável."""
        curiosity_calculator.decay_factor = 0.9  # 10% de decaimento por visita

        code = '''
class Test:
    pass
'''
        filename = "test.py"

        score1 = curiosity_calculator.calculate_score(code, filename)
        curiosity_calculator.mark_visited(filename)
        score2 = curiosity_calculator.calculate_score(code, filename, consider_visits=True)

        # Com decay de 0.9, segunda visita deve ter ~10% de redução
        expected_ratio = 0.9
        actual_ratio = score2 / score1 if score1 > 0 else 1
        assert abs(actual_ratio - expected_ratio) < 0.1


class TestCuriosityAggregation:
    """Testes de agregação de curiosidade."""

    def test_directory_curiosity(self, curiosity_calculator, sample_codebase):
        """Testa cálculo de curiosidade agregada de diretório."""
        dir_score = curiosity_calculator.calculate_directory_curiosity(sample_codebase)

        # Score agregado deve estar entre min e max
        assert 0 <= dir_score <= 100

    def test_most_curious_directory(self, curiosity_calculator):
        """Testa encontrar diretório mais curioso."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Criar subdiretórios
            dir_a = Path(tmpdir) / 'module_a'
            dir_b = Path(tmpdir) / 'module_b'
            dir_a.mkdir()
            dir_b.mkdir()

            # dir_b tem código mais interessante
            (dir_a / 'simple.py').write_text('x = 1')
            (dir_b / 'complex.py').write_text('''
class Complex:
    def __init__(self):
        self._observers = []
    def attach(self, obs):
        self._observers.append(obs)
''')

            scores = curiosity_calculator.rank_directories(tmpdir)

            # module_b deve ter score maior que module_a
            assert scores['module_b'] > scores['module_a']
