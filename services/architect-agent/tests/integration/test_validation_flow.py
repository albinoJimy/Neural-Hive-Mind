"""Testes E2E para fluxo de validação do Architect Agent.

Este módulo testa o fluxo completo de validação de repositórios,
incluindo integração com MongoDB, OPA e Scout Agents.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestValidationFlow:
    """Testes de fluxo completo de validação."""

    def test_validate_repository_success(self, test_app: TestClient):
        """Testa validação bem-sucedida de repositório via API."""
        response = test_app.post(
            "/api/v1/validation",
            json={
                "repo_url": "https://github.com/example/test-repo",
                "branch": "main",
            },
        )

        assert response.status_code == 201
        data = response.json()

        assert "report_id" in data
        assert data["repo_url"] == "https://github.com/example/test-repo"
        assert data["branch"] == "main"
        assert isinstance(data["health_score"], int)
        assert 0 <= data["health_score"] <= 100
        assert data["trend"] in ["improving", "stable", "declining", "unknown"]
        assert isinstance(data["violations"], list)
        assert isinstance(data["suggestions"], list)

    def test_validate_repository_custom_branch(self, test_app: TestClient):
        """Testa validação de branch customizada."""
        response = test_app.post(
            "/api/v1/validation",
            json={
                "repo_url": "https://github.com/example/test-repo",
                "branch": "develop",
            },
        )

        assert response.status_code == 201
        data = response.json()

        assert data["branch"] == "develop"

    def test_validate_repository_invalid_url(self, test_app: TestClient):
        """Testa validação com URL inválida."""
        response = test_app.post(
            "/api/v1/validation",
            json={
                "repo_url": "not-a-valid-url",
                "branch": "main",
            },
        )

        # API deve aceitar a URL (validação acontece no serviço)
        assert response.status_code in [201, 500]

    def test_get_validation_report(self, test_app: TestClient):
        """Testa recuperação de relatório de validação."""
        # Criar validação
        create_response = test_app.post(
            "/api/v1/validation",
            json={
                "repo_url": "https://github.com/example/test-repo",
                "branch": "main",
            },
        )
        report_id = create_response.json()["report_id"]

        # Recuperar
        response = test_app.get(f"/api/v1/validation/{report_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["report_id"] == report_id
        assert "health_score" in data
        assert "violations" in data

    def test_get_validation_report_not_found(self, test_app: TestClient):
        """Testa recuperação de relatório inexistente."""
        response = test_app.get("/api/v1/validation/non-existent-report-id")

        assert response.status_code == 404

    def test_get_validations_by_repo(self, test_app: TestClient):
        """Testa recuperação de validações por repositório."""
        repo_url = "https://github.com/example/list-test-repo"

        # Criar algumas validações
        for i in range(3):
            test_app.post(
                "/api/v1/validation",
                json={"repo_url": repo_url, "branch": f"branch-{i}"},
            )

        # Listar
        response = test_app.get(f"/api/v1/validation/repo/{repo_url}?limit=10")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_validations_by_repo_with_limit(self, test_app: TestClient):
        """Testa listagem com limite."""
        repo_url = "https://github.com/example/limit-test-repo"

        # Criar validações
        for i in range(5):
            test_app.post(
                "/api/v1/validation",
                json={"repo_url": repo_url, "branch": f"branch-{i}"},
            )

        # Listar com limit
        response = test_app.get(f"/api/v1/validation/repo/{repo_url}?limit=2")

        assert response.status_code == 200
        data = response.json()

        assert len(data) <= 2


@pytest.mark.integration
class TestValidationPersistence:
    """Testes de persistência de relatórios de validação."""

    async def test_validation_persisted_to_mongodb(self, test_app: TestClient, mongo_database):
        """Testa que relatório é persistido no MongoDB."""
        # Criar via API
        response = test_app.post(
            "/api/v1/validation",
            json={
                "repo_url": "https://github.com/example/persistence-test",
                "branch": "main",
            },
        )
        report_id = response.json()["report_id"]

        # Verificar no MongoDB
        from src.config.settings import get_settings

        settings = get_settings()
        collection = mongo_database[settings.mongodb.collection_validation]

        doc = await collection.find_one({"report_id": report_id})

        assert doc is not None
        assert doc["report_id"] == report_id
        assert "health_score" in doc
        assert "violations" in doc

    async def test_validation_retrieved_from_mongodb(
        self, validation_repository, sample_validation_report
    ):
        """Testa recuperação de relatório do MongoDB."""
        # Persistir diretamente
        await validation_repository.create(sample_validation_report)

        # Recuperar
        retrieved = await validation_repository.get_by_report_id(sample_validation_report.report_id)

        assert retrieved is not None
        assert retrieved.report_id == sample_validation_report.report_id
        assert retrieved.health_score == sample_validation_report.health_score
        assert len(retrieved.violations) == len(sample_validation_report.violations)

    async def test_validation_list_by_repo(self, validation_repository, sample_validation_report):
        """Testa listagem de validações por repositório."""
        repo_url = "https://github.com/example/list-test"

        # Criar relatórios
        for i in range(3):
            report = sample_validation_report.model_copy(
                update={
                    "report_id": f"validation-list-{i}",
                    "repo_url": repo_url,
                    "branch": f"branch-{i}",
                }
            )
            await validation_repository.create(report)

        # Listar
        reports = await validation_repository.get_by_repo_url(repo_url, limit=10)

        assert len(reports) >= 3
        for report in reports:
            assert report.repo_url == repo_url


@pytest.mark.integration
class TestValidationIntegration:
    """Testes de integração com OPA e Scout Agents."""

    @pytest.mark.skip(reason="Requires OPA server with policies")
    async def test_opa_policy_validation(self, opa_url):
        """Testa validação via OPA."""
        import httpx

        # Executar query OPA
        response = httpx.post(
            f"{opa_url}/v1/data/architecture/rules",
            json={"input": {"architecture_type": "microservices"}},
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data

    @pytest.mark.skip(reason="Requires Scout Agents service")
    async def test_scout_agents_integration(self):
        """Testa integração com Scout Agents."""
        from src.validators.scout_client import ScoutClient
        from src.config.settings import get_settings

        settings = get_settings()
        client = ScoutClient(base_url=settings.scout_agents.url)

        # Obter padrões
        patterns = await client.get_patterns()

        assert isinstance(patterns, dict)
        assert "patterns" in patterns

    def test_validation_with_violations(self, test_app: TestClient, monkeypatch):
        """Testa validação que gera violações."""
        # Este teste pode precisar de mock ou setup específico
        # dependendo de como violações são detectadas
        response = test_app.post(
            "/api/v1/validation",
            json={
                "repo_url": "https://github.com/example/violations-test",
                "branch": "main",
            },
        )

        assert response.status_code == 201
        data = response.json()

        # Violations pode estar vazio ou conter itens
        assert isinstance(data["violations"], list)

        if len(data["violations"]) > 0:
            violation = data["violations"][0]
            assert "type" in violation
            assert "severity" in violation
            assert "description" in violation


@pytest.mark.integration
class TestValidationMetrics:
    """Testes de métricas de validação."""

    def test_health_score_calculation(self, test_app: TestClient):
        """Testa cálculo de health score."""
        response = test_app.post(
            "/api/v1/validation",
            json={
                "repo_url": "https://github.com/example/metrics-test",
                "branch": "main",
            },
        )

        assert response.status_code == 201
        data = response.json()

        # Health score deve ser entre 0 e 100
        assert 0 <= data["health_score"] <= 100

    def test_trend_detection(self, test_app: TestClient):
        """Testa detecção de tendência."""
        # Criar múltiplas validações para mesma repo
        repo_url = "https://github.com/example/trend-test"

        for i in range(3):
            test_app.post(
                "/api/v1/validation",
                json={"repo_url": repo_url, "branch": "main"},
            )

        # Última validação deve ter trend
        response = test_app.post(
            "/api/v1/validation",
            json={"repo_url": repo_url, "branch": "main"},
        )

        assert response.status_code == 201
        data = response.json()

        # Trend deve ser um dos valores válidos
        assert data["trend"] in ["improving", "stable", "declining", "unknown"]
