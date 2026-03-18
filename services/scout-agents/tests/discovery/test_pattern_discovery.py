"""
Testes para PatternDiscovery.

TDD: Testes escritos antes da implementação.
Espec: GAPS-05 Scout Agents
"""

import pytest
from unittest.mock import Mock, MagicMock
from pathlib import Path

# Import com skip automático se módulo não disponível
PatternDiscovery = pytest.importorskip('src.discovery.pattern_discovery').PatternDiscovery


class TestPatternDiscoveryInitialization:
    """Testes de inicialização do PatternDiscovery."""

    def test_discovery_initialization(self):
        """Testa que o discovery é inicializado corretamente."""
        discovery = PatternDiscovery()

        assert discovery is not None
        assert hasattr(discovery, 'patterns_db')

    def test_discovery_default_patterns(self):
        """Testa padrões pré-configurados."""
        discovery = PatternDiscovery()

        # Deve ter padrões comuns pré-configurados
        assert len(discovery.get_known_patterns()) > 0


class TestIdentifyRepositoryPattern:
    """Testes de identificação do padrão Repository."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_identify_repository_class_pattern(self, discovery):
        """Testa identificação de classe Repository."""
        code = """
class UserRepository:
    def find_by_id(self, user_id):
        pass

    def find_all(self):
        pass

    def save(self, user):
        pass

    def delete(self, user_id):
        pass
"""
        patterns = discovery.identify_patterns(code, "user_repository.py")

        assert any(p['name'] == 'repository' for p in patterns)
        assert any(p['confidence'] > 0.7 for p in patterns if p['name'] == 'repository')

    def test_identify_repository_with_db_methods(self, discovery):
        """Testa identificação por métodos comuns de DB."""
        code = """
class OrderRepository:
    def get(self, id):
        return self.db.query(id)

    def list(self, filters=None):
        return self.db.query()

    def create(self, data):
        return self.db.insert(data)

    def update(self, id, data):
        return self.db.update(id, data)

    def remove(self, id):
        return self.db.delete(id)
"""
        patterns = discovery.identify_patterns(code, "order_repository.py")

        repository_patterns = [p for p in patterns if p['name'] == 'repository']
        assert len(repository_patterns) > 0


class TestIdentifyServicePattern:
    """Testes de identificação do padrão Service."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_identify_service_class_pattern(self, discovery):
        """Testa identificação de classe Service."""
        code = """
class UserService:
    def __init__(self, repository, logger):
        self.repository = repository
        self.logger = logger

    def create_user(self, data):
        # Lógica de negócio
        user = self.repository.save(data)
        return user

    def get_user(self, user_id):
        return self.repository.find_by_id(user_id)
"""
        patterns = discovery.identify_patterns(code, "user_service.py")

        assert any(p['name'] == 'service' for p in patterns)

    def test_identify_service_with_business_logic(self, discovery):
        """Testa identificação por lógica de negócio."""
        code = """
class PaymentService:
    def process_payment(self, amount, card):
        self._validate_card(card)
        self._check_limit(amount)
        return self._charge(amount, card)

    def _validate_card(self, card):
        pass

    def _check_limit(self, amount):
        pass
"""
        patterns = discovery.identify_patterns(code, "payment_service.py")

        service_patterns = [p for p in patterns if p['name'] == 'service']
        assert len(service_patterns) > 0


class TestIdentifyFactoryPattern:
    """Testes de identificação do padrão Factory."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_identify_factory_class(self, discovery):
        """Testa identificação de classe Factory."""
        code = """
class ResponseFactory:
    def create_success(self, data):
        return {"status": "success", "data": data}

    def create_error(self, message):
        return {"status": "error", "message": message}

    @staticmethod
    def from_exception(exc):
        return ResponseFactory.create_error(str(exc))
"""
        patterns = discovery.identify_patterns(code, "response_factory.py")

        assert any(p['name'] == 'factory' for p in patterns)


class TestIdentifySingletonPattern:
    """Testes de identificação do padrão Singleton."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_identify_singleton_with_instance(self, discovery):
        """Testa identificação de singleton com _instance."""
        code = """
class DatabaseConnection:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.connection = None
            self.initialized = True
"""
        patterns = discovery.identify_patterns(code, "database.py")

        assert any(p['name'] == 'singleton' for p in patterns)


class TestIdentifyDecoratorPattern:
    """Testes de identificação do padrão Decorator."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_identify_wrapper_decorator(self, discovery):
        """Testa identificação de decorator com wrapper."""
        code = """
def cache_decorator(func):
    _cache = {}

    def wrapper(*args, **kwargs):
        key = (args, tuple(kwargs.items()))
        if key not in _cache:
            _cache[key] = func(*args, **kwargs)
        return _cache[key]

    return wrapper

@cache_decorator
def expensive_operation(x):
    return x ** 2
"""
        patterns = discovery.identify_patterns(code, "cache.py")

        assert any(p['name'] == 'decorator' for p in patterns)


class TestAnalyzePatternFrequency:
    """Testes de análise de frequência de padrões."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_count_pattern_occurrences(self, discovery):
        """Testa contagem de ocorrências de padrão."""
        files = {
            'user_repo.py': '''
class UserRepository:
    def find(self, id): pass
    def save(self, data): pass
''',
            'order_repo.py': '''
class OrderRepository:
    def find(self, id): pass
    def save(self, data): pass
''',
            'product_repo.py': '''
class ProductRepository:
    def find(self, id): pass
    def save(self, data): pass
''',
            'user_service.py': '''
class UserService:
    def create(self, data): pass
'''
        }

        frequency = discovery.analyze_pattern_frequency(files, 'repository')

        assert frequency['count'] == 3
        assert frequency['locations'] == ['user_repo.py', 'order_repo.py', 'product_repo.py']

    def test_calculate_pattern_confidence(self, discovery):
        """Testa cálculo de confiança do padrão."""
        files = {
            'repo1.py': 'class Repository: pass',
            'repo2.py': 'class Repository: pass',
            'repo3.py': 'class Repository: pass',
            'other.py': 'class Service: pass'
        }

        confidence = discovery.calculate_pattern_confidence(files, 'repository')

        assert confidence > 0.5
        assert confidence <= 1.0


class TestSuggestPatternApplication:
    """Testes de sugestão de aplicação de padrões."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_suggest_repository_for_data_access(self, discovery):
        """Testa sugestão de Repository para acesso de dados."""
        code = """
class UserData:
    def get_user(self, id):
        return db.query(f"SELECT * FROM users WHERE id = {id}")

    def save_user(self, user):
        db.insert("users", user)
"""

        suggestions = discovery.suggest_patterns(code, "user_data.py")

        assert any('repository' in s['pattern'].lower() for s in suggestions)

    def test_suggest_factory_for_object_creation(self, discovery):
        """Testa sugestão de Factory para criação de objetos."""
        code = """
def create_response(status, data):
    if status == "success":
        return {"status": status, "data": data}
    elif status == "error":
        return {"status": status, "error": data}
    elif status == "pending":
        return {"status": status, "message": data}
    # ... mais variações
"""

        suggestions = discovery.suggest_patterns(code, "responses.py")

        assert any('factory' in s['pattern'].lower() for s in suggestions)


class TestPatternMatchingWithAST:
    """Testes de matching de padrões usando AST."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_extract_class_structure(self, discovery):
        """Testa extração da estrutura de classe."""
        code = """
class UserService:
    def __init__(self, repo):
        self.repo = repo

    def get_user(self, id):
        return self.repo.find(id)

    @validate
    def create_user(self, data):
        return self.repo.save(data)
"""

        structure = discovery.extract_class_structure(code, "user_service.py")

        assert structure['name'] == 'UserService'
        assert len(structure['methods']) == 3
        assert any(m['name'] == '__init__' for m in structure['methods'])
        assert any(m['decorators'] == ['@validate'] for m in structure['methods'] if m['name'] == 'create_user')

    def test_detect_dependencies_between_classes(self, discovery):
        """Testa detecção de dependências entre classes."""
        code1 = """
class OrderService:
    def __init__(self, repository):
        self.repository = repository
"""

        code2 = """
class OrderRepository:
    def find(self, id): pass
"""

        # Adicionar código ao discovery
        discovery.add_code_sample("order_service.py", code1)
        discovery.add_code_sample("order_repository.py", code2)

        dependencies = discovery.detect_class_dependencies("OrderService")

        assert 'OrderRepository' in dependencies or 'repository' in dependencies


class TestPatternDocumentation:
    """Testes de documentação de padrões descobertos."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_generate_pattern_report(self, discovery):
        """Testa geração de relatório de padrões."""
        files = {
            'repo.py': 'class Repository: pass',
            'service.py': 'class Service: pass'
        }

        report = discovery.generate_pattern_report(files)

        assert 'patterns_found' in report
        assert 'total_files' in report
        assert report['total_files'] == 2

    def test_export_pattern_graph(self, discovery):
        """Testa exportação de grafo de padrões."""
        files = {
            'a.py': 'class A: pass',
            'b.py': 'class B: pass'
        }

        graph = discovery.export_pattern_graph(files)

        assert 'nodes' in graph
        assert 'edges' in graph
