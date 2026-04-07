"""
Testes expandidos para PatternDiscovery.
Cobertura de identificação de padrões de design.
"""
import pytest

from src.discovery.pattern_discovery import PatternDiscovery


@pytest.fixture
def pattern_discovery():
    """Instância de PatternDiscovery para testes."""
    return PatternDiscovery()


class TestPatternIdentification:
    """Testes de identificação de padrões."""

    def test_identify_repository_pattern(self, pattern_discovery):
        """Testa identificação de padrão Repository."""
        code = """
class UserRepository:
    def __init__(self, db):
        self.db = db

    def find(self, id):
        return self.db.query(id)

    def save(self, user):
        self.db.insert(user)

    def delete(self, id):
        self.db.remove(id)
"""
        patterns = pattern_discovery.identify_patterns(code, "user_repo.py")

        repo_patterns = [p for p in patterns if p["name"] == "repository"]
        assert len(repo_patterns) == 1
        assert repo_patterns[0]["confidence"] >= 0.5

    def test_identify_service_pattern(self, pattern_discovery):
        """Testa identificação de padrão Service."""
        code = """
class UserService:
    def __init__(self, repository):
        self.repository = repository

    def create_user(self, data):
        user = self.repository.save(data)
        return user

    def process_request(self, request):
        handler = self.get_handler(request.type)
        return handler.handle(request)

    def get_handler(self, type):
        return HandlerFactory.create(type)
"""
        patterns = pattern_discovery.identify_patterns(code, "user_service.py")

        service_patterns = [p for p in patterns if p["name"] == "service"]
        assert len(service_patterns) == 1

    def test_identify_factory_pattern(self, pattern_discovery):
        """Testa identificação de padrão Factory."""
        code = """
class UserFactory:
    def create(self, user_type):
        if user_type == "admin":
            return AdminUser()
        elif user_type == "regular":
            return RegularUser()
        return None

    def make(self, **kwargs):
        return self.create(kwargs.get("type"))
"""
        patterns = pattern_discovery.identify_patterns(code, "user_factory.py")

        factory_patterns = [p for p in patterns if p["name"] == "factory"]
        assert len(factory_patterns) >= 1

    def test_identify_singleton_pattern(self, pattern_discovery):
        """Testa identificação de padrão Singleton."""
        code = """
class ConnectionManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'):
            return
        self.initialized = True

    @staticmethod
    def get_instance():
        return ConnectionManager()
"""
        patterns = pattern_discovery.identify_patterns(code, "connection.py")

        singleton_patterns = [p for p in patterns if p["name"] == "singleton"]
        assert len(singleton_patterns) >= 1

    def test_identify_decorator_pattern(self, pattern_discovery):
        """Testa identificação de padrão Decorator."""
        code = """
def retry(max_attempts=3):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception:
                    if attempt == max_attempts - 1:
                        raise
            return None
        return wrapper
    return decorator

@retry(max_attempts=5)
def fetch_data():
    return data
"""
        patterns = pattern_discovery.identify_patterns(code, "decorators.py")

        decorator_patterns = [p for p in patterns if p["name"] == "decorator"]
        assert len(decorator_patterns) >= 1

    def test_identify_multiple_patterns(self, pattern_discovery):
        """Testa identificação de múltiplos padrões no mesmo código."""
        code = """
class Repository:
    def find(self):
        pass

class Service:
    def __init__(self, repository):
        self.repository = repository
"""
        patterns = pattern_discovery.identify_patterns(code, "mixed.py")

        assert len(patterns) >= 2
        pattern_names = {p["name"] for p in patterns}
        assert "repository" in pattern_names
        assert "service" in pattern_names


class TestPatternFrequency:
    """Testes de análise de frequência de padrões."""

    @pytest.fixture
    def sample_files(self):
        """Arquivos de exemplo para análise de frequência."""
        return {
            "repo1.py": """
class UserRepository:
    def find(self):
        pass
    def save(self):
        pass
""",
            "repo2.py": """
class ProductRepository:
    def find(self):
        pass
    def delete(self):
        pass
""",
            "service.py": """
class UserService:
    def create(self):
        pass
""",
        }

    def test_analyze_pattern_frequency(self, pattern_discovery, sample_files):
        """Testa análise de frequência de padrão."""
        result = pattern_discovery.analyze_pattern_frequency(sample_files, "repository")

        assert result["pattern"] == "repository"
        assert result["count"] == 2
        assert result["locations"] == ["repo1.py", "repo2.py"]
        assert result["average_confidence"] >= 0.5

    def test_calculate_pattern_confidence(self, pattern_discovery, sample_files):
        """Testa cálculo de confiança agregada."""
        confidence = pattern_discovery.calculate_pattern_confidence(sample_files, "repository")

        assert 0.0 <= confidence <= 1.0
        assert confidence > 0.0  # Deve detectar algo


class TestPatternSuggestions:
    """Testes de sugestão de padrões."""

    def test_suggest_repository_for_data_access_class(self, pattern_discovery):
        """Testa sugestão de padrão Repository para classe com acesso a dados."""
        code = """
class UserManager:
    def __init__(self, db):
        self.db = db

    def get_user(self, user_id):
        return self.db.query(user_id)

    def update_user(self, user_id, data):
        self.db.update(user_id, data)

    def delete_user(self, user_id):
        self.db.delete(user_id)
"""
        suggestions = pattern_discovery.suggest_patterns(code, "user_manager.py")

        repo_suggestions = [s for s in suggestions if s["pattern"] == "Repository"]
        assert len(repo_suggestions) >= 1

    def test_suggest_factory_for_multiple_create_methods(self, pattern_discovery):
        """Testa sugestão de padrão Factory para múltiplos métodos de criação."""
        code = """
class ObjectCreator:
    def create_user(self):
        return User()

    def create_product(self):
        return Product()

    def create_order(self):
        return Order()
"""
        suggestions = pattern_discovery.suggest_patterns(code, "creator.py")

        factory_suggestions = [s for s in suggestions if s["pattern"] == "Factory"]
        assert len(factory_suggestions) >= 1

    def test_suggest_no_patterns_for_simple_class(self, pattern_discovery):
        """Testa que não sugere padrões para classe simples."""
        code = """
class Utils:
    @staticmethod
    def format_date(date):
        return date.strftime("%Y-%m-%d")

    @staticmethod
    def calculate_sum(numbers):
        return sum(numbers)
"""
        suggestions = pattern_discovery.suggest_patterns(code, "utils.py")

        # Pode sugerir algo, mas não deve serRepository
        assert all(s["confidence"] < 0.8 for s in suggestions)


class TestPatternReporting:
    """Testes de geração de relatórios."""

    @pytest.fixture
    def report_files(self):
        """Arquivos para teste de relatório."""
        return {
            "repo.py": """
class UserRepository:
    def find(self):
        pass
""",
            "service.py": """
class UserService:
    def __init__(self, repo):
        self.repo = repo
""",
        }

    def test_generate_pattern_report(self, pattern_discovery, report_files):
        """Testa geração de relatório de padrões."""
        report = pattern_discovery.generate_pattern_report(report_files)

        assert "total_files" in report
        assert report["total_files"] == 2
        assert "patterns_found" in report
        assert "pattern_summary" in report

        # Verificar que detectou padrões
        assert report["patterns_found"] >= 1
        summary = report["pattern_summary"]
        assert len(summary) >= 1

    def test_export_pattern_graph(self, pattern_discovery, report_files):
        """Testa exportação de grafo de padrões."""
        graph = pattern_discovery.export_pattern_graph(report_files)

        assert "nodes" in graph
        assert "edges" in graph
        assert "total_patterns" in graph
        assert graph["total_patterns"] >= 1


class TestClassStructureExtraction:
    """Testes de extração de estrutura de classes."""

    def test_extract_class_structure_success(self, pattern_discovery):
        """Testa extração bem-sucedida de estrutura de classe."""
        code = '''
class MyClass:
    """Docstring da classe."""

    class_var = 42

    def __init__(self):
        self.value = 10

    @property
    def prop(self):
        return self.value

    def method1(self):
        pass

    @staticmethod
    def static_method():
        pass
'''
        structure = pattern_discovery.extract_class_structure(code, "test.py")

        assert structure["name"] == "MyClass"
        assert len(structure["methods"]) == 4  # __init__, prop, method1, static_method
        assert "class_var" in structure["attributes"]

        # Verificar decorators dos métodos (não da classe)
        prop_method = next((m for m in structure["methods"] if m["name"] == "prop"), None)
        assert prop_method is not None
        assert "@property" in prop_method["decorators"]

        static_method = next(
            (m for m in structure["methods"] if m["name"] == "static_method"), None
        )
        assert static_method is not None
        assert "@staticmethod" in static_method["decorators"]

    def test_extract_class_structure_no_class(self, pattern_discovery):
        """Testa extração quando não há classe."""
        code = """
def standalone_function():
    pass
"""
        structure = pattern_discovery.extract_class_structure(code, "test.py")

        assert structure["name"] is None
        assert structure["methods"] == []
        assert structure["attributes"] == []


class TestClassDependencies:
    """Testes de detecção de dependências de classe."""

    def test_detect_dependencies_via_init(self, pattern_discovery):
        """Testa detecção de dependências via __init__."""
        code = """
class OrderService:
    def __init__(self, user_repo, product_repo, notifier):
        self.user_repo = user_repo
        self.product_repo = product_repo
        self.notifier = notifier
"""
        pattern_discovery.add_code_sample("test.py", code)

        deps = pattern_discovery.detect_class_dependencies("OrderService")

        assert "user_repo" in deps
        assert "product_repo" in deps
        assert "notifier" in deps

    def test_detect_repository_dependencies(self, pattern_discovery):
        """Testa detecção de dependências de repositórios."""
        code = """
class UserService:
    def __init__(self):
        self.user_repo = UserRepository(db())
        self.logger = Logger()
"""
        pattern_discovery.add_code_sample("test.py", code)

        deps = pattern_discovery.detect_class_dependencies("UserService")

        # Deve detectar user_repo como dependência nomeada
        assert any("repo" in dep.lower() for dep in deps)
