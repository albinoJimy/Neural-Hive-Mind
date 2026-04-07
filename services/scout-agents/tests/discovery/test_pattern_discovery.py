"""
Testes para PatternDiscovery.

TDD: Testes escritos antes da implementação.
Espec: GAPS-05 Scout Agents
"""

import pytest

# Import com skip automático se módulo não disponível
PatternDiscovery = pytest.importorskip("src.discovery.pattern_discovery").PatternDiscovery


class TestPatternDiscoveryInitialization:
    """Testes de inicialização do PatternDiscovery."""

    def test_discovery_initialization(self):
        """Testa que o discovery é inicializado corretamente."""
        discovery = PatternDiscovery()

        assert discovery is not None
        assert hasattr(discovery, "patterns_db")

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

        assert any(p["name"] == "repository" for p in patterns)
        assert any(p["confidence"] >= 0.7 for p in patterns if p["name"] == "repository")

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

        repository_patterns = [p for p in patterns if p["name"] == "repository"]
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

        assert any(p["name"] == "service" for p in patterns)

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

        service_patterns = [p for p in patterns if p["name"] == "service"]
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

        assert any(p["name"] == "factory" for p in patterns)


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

        assert any(p["name"] == "singleton" for p in patterns)


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

        assert any(p["name"] == "decorator" for p in patterns)


class TestAnalyzePatternFrequency:
    """Testes de análise de frequência de padrões."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_count_pattern_occurrences(self, discovery):
        """Testa contagem de ocorrências de padrão."""
        files = {
            "user_repo.py": """
class UserRepository:
    def find(self, id): pass
    def save(self, data): pass
""",
            "order_repo.py": """
class OrderRepository:
    def find(self, id): pass
    def save(self, data): pass
""",
            "product_repo.py": """
class ProductRepository:
    def find(self, id): pass
    def save(self, data): pass
""",
            "user_service.py": """
class UserService:
    def create(self, data): pass
""",
        }

        frequency = discovery.analyze_pattern_frequency(files, "repository")

        assert frequency["count"] == 3
        assert frequency["locations"] == ["user_repo.py", "order_repo.py", "product_repo.py"]

    def test_calculate_pattern_confidence(self, discovery):
        """Testa cálculo de confiança do padrão."""
        files = {
            "repo1.py": "class Repository: pass",
            "repo2.py": "class Repository: pass",
            "repo3.py": "class Repository: pass",
            "other.py": "class Service: pass",
        }

        confidence = discovery.calculate_pattern_confidence(files, "repository")

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

        assert any("repository" in s["pattern"].lower() for s in suggestions)

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

        assert any("factory" in s["pattern"].lower() for s in suggestions)


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

        assert structure["name"] == "UserService"
        assert len(structure["methods"]) == 3
        assert any(m["name"] == "__init__" for m in structure["methods"])
        assert any(
            m["decorators"] == ["@validate"]
            for m in structure["methods"]
            if m["name"] == "create_user"
        )

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

        assert "OrderRepository" in dependencies or "repository" in dependencies


class TestPatternDocumentation:
    """Testes de documentação de padrões descobertos."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_generate_pattern_report(self, discovery):
        """Testa geração de relatório de padrões."""
        files = {"repo.py": "class Repository: pass", "service.py": "class Service: pass"}

        report = discovery.generate_pattern_report(files)

        assert "patterns_found" in report
        assert "total_files" in report
        assert report["total_files"] == 2

    def test_export_pattern_graph(self, discovery):
        """Testa exportação de grafo de padrões."""
        files = {"a.py": "class A: pass", "b.py": "class B: pass"}

        graph = discovery.export_pattern_graph(files)

        assert "nodes" in graph
        assert "edges" in graph


# ============================================================================
# Testes para Padrões Expandidos (15+ padrões)
# ============================================================================


class TestExpandedPatternCount:
    """Testa que todos os 15+ padrões estão configurados."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_minimum_15_patterns_configured(self, discovery):
        """Testa que há pelo menos 15 padrões configurados."""
        patterns = discovery.get_known_patterns()
        assert len(patterns) >= 15

    def test_patterns_have_categories(self, discovery):
        """Testa que todos os padrões têm categorias."""
        for pattern_name in discovery.get_known_patterns():
            info = discovery.get_pattern_info(pattern_name)
            assert info is not None
            assert "category" in info
            assert info["category"] in ["creational", "structural", "behavioral"]

    def test_category_distribution(self, discovery):
        """Testa distribuição de padrões por categoria."""
        categories = discovery.get_pattern_categories()

        # Pelo menos 4 padrões por categoria
        assert len(categories["creational"]) >= 4
        assert len(categories["structural"]) >= 5
        assert len(categories["behavioral"]) >= 6


class TestCreationalPatterns:
    """Testes para padrões criacionais expandidos."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_identify_builder_pattern(self, discovery):
        """Testa identificação do padrão Builder."""
        code = """
class UserBuilder:
    def __init__(self):
        self._result = None

    def with_name(self, name):
        self._name = name
        return self

    def with_email(self, email):
        self._email = email
        return self

    def build(self):
        return User(self._name, self._email)
"""
        patterns = discovery.identify_patterns(code, "user_builder.py")

        builder_patterns = [p for p in patterns if p["name"] == "builder"]
        assert len(builder_patterns) > 0
        assert builder_patterns[0]["confidence"] > 0.5

    def test_identify_prototype_pattern(self, discovery):
        """Testa identificação do padrão Prototype."""
        code = """
class DocumentPrototype:
    def clone(self):
        return DocumentPrototype(self.content, self.author)

    def __init__(self, content, author):
        self.content = content
        self.author = author
"""
        patterns = discovery.identify_patterns(code, "document.py")

        prototype_patterns = [p for p in patterns if p["name"] == "prototype"]
        assert len(prototype_patterns) > 0


class TestStructuralPatterns:
    """Testes para padrões estruturais expandidos."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_identify_adapter_pattern(self, discovery):
        """Testa identificação do padrão Adapter."""
        code = """
class UserServiceAdapter:
    def __init__(self, adaptee):
        self._adaptee = adaptee

    def get_user_data(self, user_id):
        # Adapta o formato do serviço legacy
        legacy_data = self._adaptee.fetch_user(user_id)
        return self._convert_format(legacy_data)

    def _convert_format(self, data):
        return {'id': data['user_id'], 'name': data['name']}
"""
        patterns = discovery.identify_patterns(code, "user_adapter.py")

        adapter_patterns = [p for p in patterns if p["name"] == "adapter"]
        assert len(adapter_patterns) > 0

    def test_identify_bridge_pattern(self, discovery):
        """Testa identificação do padrão Bridge."""
        code = """
class RemoteControlBridge:
    def __init__(self, implementation):
        self._implementation = implementation

    def turn_on(self):
        self._implementation.on()

    def turn_off(self):
        self._implementation.off()
"""
        patterns = discovery.identify_patterns(code, "remote_control.py")

        bridge_patterns = [p for p in patterns if p["name"] == "bridge"]
        assert len(bridge_patterns) > 0

    def test_identify_composite_pattern(self, discovery):
        """Testa identificação do padrão Composite."""
        code = """
class CompositeNode:
    def __init__(self):
        self._children = []

    def add(self, child):
        self._children.append(child)

    def remove(self, child):
        self._children.remove(child)

    def get_children(self):
        return self._children
"""
        patterns = discovery.identify_patterns(code, "composite.py")

        composite_patterns = [p for p in patterns if p["name"] == "composite"]
        assert len(composite_patterns) > 0

    def test_identify_facade_pattern(self, discovery):
        """Testa identificação do padrão Facade."""
        code = """
class DatabaseFacade:
    def __init__(self):
        self._users_service = UserService()
        self._posts_service = PostsService()
        self._comments_service = CommentsService()

    def initialize(self):
        self._users_service.connect()
        self._posts_service.connect()
        self._comments_service.connect()

    def get_user_posts(self, user_id):
        return self._posts_service.fetch_by_user(user_id)

    def get_user_comments(self, user_id):
        return self._comments_service.fetch_by_user(user_id)
"""
        patterns = discovery.identify_patterns(code, "database_facade.py")

        facade_patterns = [p for p in patterns if p["name"] == "facade"]
        assert len(facade_patterns) > 0

    def test_identify_proxy_pattern(self, discovery):
        """Testa identificação do padrão Proxy."""
        code = """
class DatabaseProxy:
    def __init__(self, real_database):
        self._real_subject = real_database

    def query(self, sql):
        return self._real_subject.query(sql)

    def __getattr__(self, name):
        return getattr(self._real_subject, name)
"""
        patterns = discovery.identify_patterns(code, "database_proxy.py")

        proxy_patterns = [p for p in patterns if p["name"] == "proxy"]
        assert len(proxy_patterns) > 0


class TestBehavioralPatterns:
    """Testes para padrões comportamentais expandidos."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_identify_strategy_pattern(self, discovery):
        """Testa identificação do padrão Strategy."""
        code = """
class PaymentStrategy:
    def execute(self, amount):
        raise NotImplementedError

class CreditCardStrategy(PaymentStrategy):
    def execute(self, amount):
        return self._process_credit_card(amount)

    def _process_credit_card(self, amount):
        return f"Processed ${amount}"
"""
        patterns = discovery.identify_patterns(code, "payment.py")

        strategy_patterns = [p for p in patterns if p["name"] == "strategy"]
        assert len(strategy_patterns) > 0

    def test_identify_observer_pattern(self, discovery):
        """Testa identificação do padrão Observer."""
        code = """
class NewsPublisher:
    def __init__(self):
        self._subscribers = []

    def attach(self, subscriber):
        self._subscribers.append(subscriber)

    def detach(self, subscriber):
        self._subscribers.remove(subscriber)

    def notify(self, news):
        for sub in self._subscribers:
            sub.update(news)
"""
        patterns = discovery.identify_patterns(code, "news_publisher.py")

        observer_patterns = [p for p in patterns if p["name"] == "observer"]
        assert len(observer_patterns) > 0

    def test_identify_command_pattern(self, discovery):
        """Testa identificação do padrão Command."""
        code = """
class SaveCommand:
    def __init__(self, receiver):
        self._receiver = receiver

    def execute(self):
        return self._receiver.save()

    def undo(self):
        return self._receiver.delete_last()
"""
        patterns = discovery.identify_patterns(code, "save_command.py")

        command_patterns = [p for p in patterns if p["name"] == "command"]
        assert len(command_patterns) > 0

    def test_identify_chain_pattern(self, discovery):
        """Testa identificação do padrão Chain of Responsibility."""
        code = """
class AuthenticationHandler:
    def __init__(self):
        self._next = None

    def set_next(self, handler):
        self._next = handler
        return handler

    def handle(self, request):
        if self.can_handle(request):
            return self.do_handle(request)
        elif self._next:
            return self._next.handle(request)
        return None

    def can_handle(self, request):
        return True
"""
        patterns = discovery.identify_patterns(code, "auth_handler.py")

        chain_patterns = [p for p in patterns if p["name"] == "chain"]
        assert len(chain_patterns) > 0

    def test_identify_template_method_pattern(self, discovery):
        """Testa identificação do padrão Template Method."""
        code = """
class DataProcessorTemplate:
    def process(self, data):
        self.validate(data)
        result = self.transform(data)
        self.save(result)
        return result

    def validate(self, data):
        raise NotImplementedError

    def transform(self, data):
        raise NotImplementedError

    def save(self, result):
        pass
"""
        patterns = discovery.identify_patterns(code, "processor.py")

        template_patterns = [p for p in patterns if p["name"] == "template_method"]
        assert len(template_patterns) > 0

    def test_identify_mediator_pattern(self, discovery):
        """Testa identificação do padrão Mediator."""
        code = """
class ChatMediator:
    def __init__(self):
        self._colleagues = []

    def register(self, colleague):
        self._colleagues.append(colleague)

    def send(self, message, sender):
        for colleague in self._colleagues:
            if colleague != sender:
                colleague.receive(message)
"""
        patterns = discovery.identify_patterns(code, "chat_mediator.py")

        mediator_patterns = [p for p in patterns if p["name"] == "mediator"]
        assert len(mediator_patterns) > 0

    def test_identify_memento_pattern(self, discovery):
        """Testa identificação do padrão Memento."""
        code = """
class TextEditorMemento:
    def __init__(self, state):
        self._state = state

    def get_state(self):
        return self._state

    def save(self):
        return TextEditorMemento(self._content)

    def restore(self, memento):
        self._content = memento.get_state()
"""
        patterns = discovery.identify_patterns(code, "text_editor.py")

        memento_patterns = [p for p in patterns if p["name"] == "memento"]
        assert len(memento_patterns) > 0

    def test_identify_state_pattern(self, discovery):
        """Testa identificação do padrão State."""
        code = """
class OrderContext:
    def __init__(self):
        self._state = None

    def change_state(self, state):
        self._state = state

    def process(self):
        return self._state.handle()

class PendingState:
    def handle(self):
        return "Order pending"
"""
        patterns = discovery.identify_patterns(code, "order_state.py")

        state_patterns = [p for p in patterns if p["name"] == "state"]
        assert len(state_patterns) > 0


class TestPatternCategoryMethods:
    """Testes para métodos de categoria de padrões."""

    @pytest.fixture
    def discovery(self):
        return PatternDiscovery()

    def test_get_patterns_by_category_creational(self, discovery):
        """Testa obter padrões criacionais."""
        patterns = discovery.get_patterns_by_category("creational")
        assert "repository" in patterns
        assert "factory" in patterns
        assert "builder" in patterns

    def test_get_patterns_by_category_structural(self, discovery):
        """Testa obter padrões estruturais."""
        patterns = discovery.get_patterns_by_category("structural")
        assert "adapter" in patterns
        assert "composite" in patterns
        assert "facade" in patterns

    def test_get_patterns_by_category_behavioral(self, discovery):
        """Testa obter padrões comportamentais."""
        patterns = discovery.get_patterns_by_category("behavioral")
        assert "strategy" in patterns
        assert "observer" in patterns
        assert "command" in patterns

    def test_get_pattern_info(self, discovery):
        """Testa obter informações de padrão específico."""
        info = discovery.get_pattern_info("observer")
        assert info is not None
        assert info["name"] == "observer"
        assert info["category"] == "behavioral"
        assert "keywords" in info
        assert "common_methods" in info

    def test_get_pattern_info_invalid(self, discovery):
        """Testa obter informações de padrão inexistente."""
        info = discovery.get_pattern_info("nonexistent")
        assert info is None
