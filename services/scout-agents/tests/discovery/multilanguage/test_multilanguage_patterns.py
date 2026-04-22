"""Testes para detecção de padrões multi-linguagem."""

import pytest
from src.discovery.multilanguage import MultiLanguagePatternDiscovery, PatternLanguage

# ========================================================================
# Fixtures
# ========================================================================


@pytest.fixture()
def multilang_discovery():
    """Instância do detector multi-linguagem."""
    return MultiLanguagePatternDiscovery()


# ========================================================================
# TypeScript Pattern Tests
# ========================================================================


class TestTypeScriptPatterns:
    """Testes para detecção de padrões em TypeScript."""

    def test_typescript_repository_pattern(self, multilang_discovery):
        """Detecta padrão Repository em TypeScript."""
        code = """
        export interface UserRepository {
            findById(id: string): Promise<User | null>;
            save(user: User): Promise<void>;
        }

        export class MongoUserRepository implements UserRepository {
            async findById(id: string): Promise<User | null> {
                return await this.collection.findOne({ _id: id });
            }

            async save(user: User): Promise<void> {
                await this.collection.updateOne(
                    { _id: user.id },
                    { $set: user },
                    { upsert: true }
                );
            }

            private collection: Collection<User>;
        }
        """
        patterns = multilang_discovery.discover_patterns(
            code, "user.repository.ts", PatternLanguage.TYPESCRIPT
        )

        repository_patterns = [p for p in patterns if p.name == "repository"]
        assert len(repository_patterns) > 0
        assert repository_patterns[0].confidence >= 0.5

    def test_typescript_singleton_pattern(self, multilang_discovery):
        """Detecta padrão Singleton em TypeScript."""
        code = """
        export class DatabaseConnection {
            private static instance: DatabaseConnection;
            private constructor() {}

            static getInstance(): DatabaseConnection {
                if (!DatabaseConnection.instance) {
                    DatabaseConnection.instance = new DatabaseConnection();
                }
                return DatabaseConnection.instance;
            }

            connect(): void {}
        }
        """
        patterns = multilang_discovery.discover_patterns(
            code, "database.ts", PatternLanguage.TYPESCRIPT
        )

        singleton_patterns = [p for p in patterns if p.name == "singleton"]
        assert len(singleton_patterns) > 0
        assert singleton_patterns[0].confidence >= 0.5

    def test_typescript_observer_pattern(self, multilang_discovery):
        """Detecta padrão Observer em TypeScript."""
        code = """
        interface Observer {
            update(data: any): void;
        }

        class Subject {
            private observers: Observer[] = [];

            attach(observer: Observer): void {
                this.observers.push(observer);
            }

            detach(observer: Observer): void {
                const index = this.observers.indexOf(observer);
                if (index > -1) {
                    this.observers.splice(index, 1);
                }
            }

            notify(data: any): void {
                this.observers.forEach(obs => obs.update(data));
            }
        }
        """
        patterns = multilang_discovery.discover_patterns(
            code, "subject.ts", PatternLanguage.TYPESCRIPT
        )

        observer_patterns = [p for p in patterns if p.name == "observer"]
        assert len(observer_patterns) > 0

    def test_typescript_factory_pattern(self, multilang_discovery):
        """Detecta padrão Factory em TypeScript."""
        code = """
        interface Payment {
            process(amount: number): void;
        }

        class CreditCardPayment implements Payment {
            process(amount: number): void {
                console.log(`Processing credit card payment: ${amount}`);
            }
        }

        class PayPalPayment implements Payment {
            process(amount: number): void {
                console.log(`Processing PayPal payment: ${amount}`);
            }
        }

        class PaymentFactory {
            static create(type: string): Payment {
                switch (type) {
                    case 'credit': return new CreditCardPayment();
                    case 'paypal': return new PayPalPayment();
                    default: throw new Error('Invalid payment type');
                }
            }
        }
        """
        patterns = multilang_discovery.discover_patterns(
            code, "payment.factory.ts", PatternLanguage.TYPESCRIPT
        )

        factory_patterns = [p for p in patterns if p.name == "factory"]
        assert len(factory_patterns) > 0

    def test_typescript_decorator_pattern(self, multilang_discovery):
        """Detecta padrão Decorator em TypeScript."""
        code = """
        interface Component {
            operation(): string;
        }

        class ConcreteComponent implements Component {
            operation(): string {
                return "ConcreteComponent";
            }
        }

        class Decorator implements Component {
            constructor(private component: Component) {}

            operation(): string {
                return this.component.operation();
            }
        }

        class ConcreteDecorator extends Decorator {
            operation(): string {
                return `ConcreteDecorator(${super.operation()})`;
            }
        }
        """
        patterns = multilang_discovery.discover_patterns(
            code, "decorator.ts", PatternLanguage.TYPESCRIPT
        )

        decorator_patterns = [p for p in patterns if p.name == "decorator"]
        assert len(decorator_patterns) > 0


# ========================================================================
# JavaScript Pattern Tests
# ========================================================================


class TestJavaScriptPatterns:
    """Testes para detecção de padrões em JavaScript."""

    def test_javascript_service_pattern(self, multilang_discovery):
        """Detecta padrão Service em JavaScript."""
        code = """
        class UserService {
            constructor(userRepository) {
                this.userRepository = userRepository;
            }

            async getUserById(userId) {
                return await this.userRepository.findById(userId);
            }

            async createUser(userData) {
                const user = new User(userData);
                return await this.userRepository.save(user);
            }
        }

        module.exports = UserService;
        """
        patterns = multilang_discovery.discover_patterns(
            code, "user.service.js", PatternLanguage.JAVASCRIPT
        )

        service_patterns = [p for p in patterns if p.name == "service"]
        assert len(service_patterns) > 0

    def test_javascript_strategy_pattern(self, multilang_discovery):
        """Detecta padrão Strategy em JavaScript."""
        code = """
        class SortStrategy {
            sort(array) {
                throw new Error('Must implement');
            }
        }

        class BubbleSort extends SortStrategy {
            sort(array) {
                // Bubble sort implementation
                return array;
            }
        }

        class QuickSort extends SortStrategy {
            sort(array) {
                // Quick sort implementation
                return array;
            }
        }

        class SortContext {
            setStrategy(strategy) {
                this.strategy = strategy;
            }

            executeSort(array) {
                return this.strategy.sort(array);
            }
        }
        """
        patterns = multilang_discovery.discover_patterns(
            code, "sort.strategy.js", PatternLanguage.JAVASCRIPT
        )

        strategy_patterns = [p for p in patterns if p.name == "strategy"]
        assert len(strategy_patterns) > 0

    def test_javascript_builder_pattern(self, multilang_discovery):
        """Detecta padrão Builder em JavaScript."""
        code = """
        class UserBuilder {
            constructor() {
                this.name = '';
                this.email = '';
                this.age = 0;
            }

            withName(name) {
                this.name = name;
                return this;
            }

            withEmail(email) {
                this.email = email;
                return this;
            }

            withAge(age) {
                this.age = age;
                return this;
            }

            build() {
                return new User(this);
            }
        }
        """
        patterns = multilang_discovery.discover_patterns(
            code, "user.builder.js", PatternLanguage.JAVASCRIPT
        )

        builder_patterns = [p for p in patterns if p.name == "builder"]
        assert len(builder_patterns) > 0


# ========================================================================
# YAML Pattern Tests
# ========================================================================


class TestYAMLPatterns:
    """Testes para detecção de padrões em YAML."""

    def test_yaml_kubernetes_deployment(self, multilang_discovery):
        """Detecta padrão Kubernetes Deployment."""
        code = """
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: nginx-deployment
          labels:
            app: nginx
        spec:
          replicas: 3
          selector:
            matchLabels:
              app: nginx
          template:
            metadata:
              labels:
                app: nginx
            spec:
              containers:
              - name: nginx
                image: nginx:1.14.2
                ports:
                - containerPort: 80
        """
        patterns = multilang_discovery.discover_patterns(
            code, "deployment.yaml", PatternLanguage.YAML
        )

        # Deve detectar estrutura de configuração Kubernetes
        assert len(patterns) >= 1
        assert any(p.confidence > 0 for p in patterns)

    def test_yaml_docker_compose(self, multilang_discovery):
        """Detecta padrão Docker Compose."""
        code = """
        version: '3.8'
        services:
          web:
            build: .
            ports:
              - "5000:5000"
            volumes:
              - .:/code
            environment:
              FLASK_ENV: development
          redis:
            image: redis:alpine
        """
        patterns = multilang_discovery.discover_patterns(
            code, "docker-compose.yml", PatternLanguage.YAML
        )

        # Deve detectar estrutura de orquestração
        assert len(patterns) >= 1

    def test_yaml_ci_config(self, multilang_discovery):
        """Detecta padrão de CI/CD em YAML."""
        code = """
        name: CI Pipeline
        on:
          push:
            branches: [ main ]
        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v2
              - name: Run tests
                run: pytest
        """
        patterns = multilang_discovery.discover_patterns(
            code, ".github/workflows/ci.yml", PatternLanguage.YAML
        )

        assert len(patterns) >= 1


# ========================================================================
# JSON Pattern Tests
# ========================================================================


class TestJSONPatterns:
    """Testes para detecção de padrões em JSON."""

    def test_json_api_response(self, multilang_discovery):
        """Detecta padrão de resposta API em JSON."""
        code = """
        {
            "users": [
                {
                    "id": "1",
                    "name": "John Doe",
                    "email": "john@example.com",
                    "roles": ["admin", "user"]
                }
            ],
            "pagination": {
                "page": 1,
                "perPage": 10,
                "total": 100
            },
            "metadata": {
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }
        """
        patterns = multilang_discovery.discover_patterns(code, "users.json", PatternLanguage.JSON)

        # Deve detectar estrutura de dados
        assert len(patterns) >= 1

    def test_json_config_structure(self, multilang_discovery):
        """Detecta padrão de configuração em JSON."""
        code = """
        {
            "database": {
                "host": "localhost",
                "port": 5432,
                "name": "mydb"
            },
            "redis": {
                "host": "localhost",
                "port": 6379
            },
            "features": {
                "featureA": true,
                "featureB": false
            }
        }
        """
        patterns = multilang_discovery.discover_patterns(code, "config.json", PatternLanguage.JSON)

        assert len(patterns) >= 1


# ========================================================================
# Cross-Language Tests
# ========================================================================


class TestCrossLanguagePatterns:
    """Testes de padrões consistente entre linguagens."""

    def test_repository_across_languages(self, multilang_discovery):
        """Verifica que Repository é detectado em múltiplas linguagens."""
        python_code = """
class UserRepository:
    def find_by_id(self, user_id: str):
        pass
    def save(self, user):
        pass
"""

        typescript_code = """
class UserRepository {
    findById(id: string) { return null; }
    save(user: User) {}
}
"""

        js_code = """
class UserRepository {
    findById(id) { return null; }
    save(user) {}
}
"""

        python_patterns = multilang_discovery.discover_patterns(
            python_code, "user.py", PatternLanguage.PYTHON
        )
        ts_patterns = multilang_discovery.discover_patterns(
            typescript_code, "user.ts", PatternLanguage.TYPESCRIPT
        )
        js_patterns = multilang_discovery.discover_patterns(
            js_code, "user.js", PatternLanguage.JAVASCRIPT
        )

        # Todas devem detectar repository
        assert any(p.name == "repository" for p in python_patterns)
        assert any(p.name == "repository" for p in ts_patterns)
        assert any(p.name == "repository" for p in js_patterns)


# ========================================================================
# Confidence Scoring Tests
# ========================================================================


class TestConfidenceScoring:
    """Testes de pontuação de confiança."""

    def test_confidence_increases_with_keywords(self, multilang_discovery):
        """Confiança aumenta com palavras-chave presentes."""
        weak_code = """
        class DataManager {
            process(data) {}
        }
        """

        strong_code = """
        class UserRepository {
            findById(id) { return this.data[id]; }
            save(user) { this.data[user.id] = user; }
            delete(id) { delete this.data[id]; }
        }
        """

        weak_patterns = multilang_discovery.discover_patterns(
            weak_code, "weak.js", PatternLanguage.JAVASCRIPT
        )
        strong_patterns = multilang_discovery.discover_patterns(
            strong_code, "strong.js", PatternLanguage.JAVASCRIPT
        )

        weak_confidence = max([p.confidence for p in weak_patterns], default=0)
        strong_confidence = max([p.confidence for p in strong_patterns], default=0)

        assert strong_confidence >= weak_confidence

    def test_confidence_range_valid(self, multilang_discovery):
        """Confiança sempre entre 0 e 1."""
        code = """
        class TestService {
            testMethod() {}
        }
        """

        patterns = multilang_discovery.discover_patterns(
            code, "test.ts", PatternLanguage.TYPESCRIPT
        )

        for pattern in patterns:
            assert 0.0 <= pattern.confidence <= 1.0


# ========================================================================
# Language Detection Tests
# ========================================================================


class TestLanguageDetection:
    """Testes de detecção automática de linguagem."""

    def test_detect_language_from_extension(self, multilang_discovery):
        """Detecta linguagem baseado na extensão."""
        test_cases = [
            ("test.py", PatternLanguage.PYTHON),
            ("test.ts", PatternLanguage.TYPESCRIPT),
            ("test.js", PatternLanguage.JAVASCRIPT),
            ("test.yaml", PatternLanguage.YAML),
            ("test.yml", PatternLanguage.YAML),
            ("test.json", PatternLanguage.JSON),
        ]

        for filename, expected_lang in test_cases:
            detected = multilang_discovery.detect_language(filename)
            assert detected == expected_lang, f"Failed for {filename}"

    def test_unknown_extension_defaults_to_python(self, multilang_discovery):
        """Extensão desconhecida defaulta para Python."""
        detected = multilang_discovery.detect_language("unknown.xyz")
        assert detected == PatternLanguage.PYTHON


# ========================================================================
# Edge Cases Tests
# ========================================================================


class TestEdgeCases:
    """Testes de casos extremos."""

    def test_empty_code_returns_empty_patterns(self, multilang_discovery):
        """Código vazio retorna lista vazia."""
        patterns = multilang_discovery.discover_patterns("", "empty.ts", PatternLanguage.TYPESCRIPT)

        assert len(patterns) == 0

    def test_code_without_patterns(self, multilang_discovery):
        """Código sem padrões reconhecíveis."""
        code = """
        // Just comments
        /* Multi line comment */
        const x = 42;
        """

        patterns = multilang_discovery.discover_patterns(
            code, "simple.js", PatternLanguage.JAVASCRIPT
        )

        # Pode retornar padrões com baixa confiança ou nenhum
        for pattern in patterns:
            assert pattern.confidence < 0.5

    def test_very_long_code(self, multilang_discovery):
        """Lida com código muito longo."""
        # Gerar código longo
        methods = "\n".join([f"    method{i}() {{ return {i}; }}" for i in range(100)])
        code = f"""
        class BigClass {{
            {methods}
        }}
        """

        patterns = multilang_discovery.discover_patterns(code, "big.ts", PatternLanguage.TYPESCRIPT)

        # Não deve quebrar
        assert isinstance(patterns, list)
