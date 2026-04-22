"""Testes unitários para PostmanParser."""

import json

import pytest

from src.services.parsers.postman_parser import PostmanParser


@pytest.fixture
def postman_parser():
    """Fixture para PostmanParser."""
    return PostmanParser()


@pytest.fixture
def sample_postman_v21():
    """Fixture para coleção Postman v2.1 válida."""
    collection = {
        "info": {
            "name": "Test API Collection",
            "description": "Test description",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "version": "1.0.0",
        },
        "item": [
            {
                "name": "Get Users",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "https://api.example.com/users",
                        "protocol": "https",
                        "host": ["api", "example", "com"],
                        "path": ["users"],
                    },
                    "header": [{"key": "Authorization", "value": "Bearer token123"}],
                },
            },
            {
                "name": "Create User",
                "request": {
                    "method": "POST",
                    "url": "https://api.example.com/users",
                    "body": {"mode": "raw", "raw": '{"name": "John", "email": "john@example.com"}'},
                },
            },
            {
                "name": "API Folder",
                "item": [
                    {
                        "name": "Delete User",
                        "request": {"method": "DELETE", "url": "https://api.example.com/users/1"},
                    }
                ],
            },
        ],
    }
    return json.dumps(collection).encode()


@pytest.fixture
def invalid_postman_json():
    """Fixture para JSON inválido."""
    return b"This is not valid JSON"


@pytest.fixture
def valid_json_not_postman():
    """Fixture para JSON válido mas não é coleção Postman."""
    return json.dumps({"data": "value"}).encode()


class TestPostmanParserValidate:
    """Testes para método validate."""

    def test_validate_valid_postman_v21(self, postman_parser, sample_postman_v21):
        """Testa validação de coleção Postman v2.1 válida."""
        assert postman_parser.validate(sample_postman_v21) is True

    def test_validate_invalid_json(self, postman_parser, invalid_postman_json):
        """Testa validação de JSON inválido."""
        assert postman_parser.validate(invalid_postman_json) is False

    def test_validate_valid_json_not_postman(self, postman_parser, valid_json_not_postman):
        """Testa validação de JSON válido sem estrutura Postman."""
        assert postman_parser.validate(valid_json_not_postman) is False

    def test_validate_empty_bytes(self, postman_parser):
        """Testa validação de bytes vazios."""
        assert postman_parser.validate(b"") is False

    def test_validate_json_array(self, postman_parser):
        """Testa validação de JSON array (inválido como Postman)."""
        # Array JSON não é uma coleção Postman válida
        assert postman_parser.validate(b"[]") is False


class TestPostmanParserExtractApis:
    """Testes para método extract_apis."""

    @pytest.mark.asyncio
    async def test_extract_apis_invalid_json(self, postman_parser, invalid_postman_json):
        """Testa extração de JSON inválido."""
        result = await postman_parser.extract_apis(invalid_postman_json)
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_apis_empty_bytes(self, postman_parser):
        """Testa extração de bytes vazios."""
        result = await postman_parser.extract_apis(b"")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_apis_v21_collection(self, postman_parser, sample_postman_v21):
        """Testa extração de coleção v2.1."""
        result = await postman_parser.extract_apis(sample_postman_v21)

        assert len(result) == 3
        # Primeira API
        assert result[0]["method"] == "GET"
        assert "api.example.com" in result[0]["url"]
        assert result[0]["name"] == "Get Users"
        # Segunda API
        assert result[1]["method"] == "POST"
        assert "api.example.com" in result[1]["url"]
        assert result[1]["body_mode"] == "raw"
        # Terceira API (em folder)
        assert result[2]["method"] == "DELETE"
        assert result[2]["folder"] == "API Folder"

    @pytest.mark.asyncio
    async def test_extract_apis_with_headers(self, postman_parser):
        """Testa extração com headers."""
        collection = {
            "info": {
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": [
                {
                    "name": "Test",
                    "request": {
                        "method": "GET",
                        "url": "https://api.test.com/endpoint",
                        "header": [
                            {"key": "Authorization", "value": "Bearer token"},
                            {"key": "Content-Type", "value": "application/json"},
                        ],
                    },
                }
            ],
        }
        content = json.dumps(collection).encode()

        result = await postman_parser.extract_apis(content)

        assert len(result) == 1
        assert result[0]["headers"]["Authorization"] == "Bearer token"
        assert result[0]["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_extract_apis_nested_folders(self, postman_parser):
        """Testa extração com pastas aninhadas."""
        collection = {
            "info": {
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": [
                {
                    "name": "Parent Folder",
                    "item": [
                        {
                            "name": "Child Folder",
                            "item": [
                                {
                                    "name": "Nested API",
                                    "request": {
                                        "method": "GET",
                                        "url": "https://api.test.com/nested",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        content = json.dumps(collection).encode()

        result = await postman_parser.extract_apis(content)

        assert len(result) == 1
        # Folder deve ser "Child Folder" (mais próximo do request)
        assert "Folder" in result[0]["folder"]

    @pytest.mark.asyncio
    async def test_extract_apis_minimal_request(self, postman_parser):
        """Testa extração com request mínimo."""
        collection = {
            "info": {
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": [{"name": "Minimal", "request": {"url": "https://api.test.com/minimal"}}],
        }
        content = json.dumps(collection).encode()

        result = await postman_parser.extract_apis(content)

        assert len(result) == 1
        # Método default é GET
        assert result[0]["method"] == "GET"

    @pytest.mark.asyncio
    async def test_extract_apis_without_url(self, postman_parser):
        """Testa que requests sem URL são ignorados."""
        collection = {
            "info": {
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": [{"name": "No URL", "request": {"method": "POST"}}],
        }
        content = json.dumps(collection).encode()

        result = await postman_parser.extract_apis(content)

        # Request sem URL não deve ser incluído
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_extract_apis_with_auth(self, postman_parser):
        """Testa extração com configuração de autenticação."""
        collection = {
            "info": {
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": [
                {
                    "name": "Auth API",
                    "request": {
                        "method": "POST",
                        "url": "https://api.test.com/auth",
                        "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "abc123"}]},
                    },
                }
            ],
        }
        content = json.dumps(collection).encode()

        result = await postman_parser.extract_apis(content)

        assert len(result) == 1
        assert result[0]["auth_type"] == "bearer"


class TestPostmanParserExtractMetadata:
    """Testes para método extract_metadata."""

    @pytest.mark.asyncio
    async def test_extract_metadata_invalid_json(self, postman_parser, invalid_postman_json):
        """Testa extração de metadados de JSON inválido."""
        result = await postman_parser.extract_metadata(invalid_postman_json)
        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_metadata_v21(self, postman_parser, sample_postman_v21):
        """Testa extração de metadados de coleção v2.1."""
        result = await postman_parser.extract_metadata(sample_postman_v21)

        assert result["name"] == "Test API Collection"
        assert result["description"] == "Test description"
        assert result["api_count"] == 3
        assert result["folder_count"] == 1
        assert "schema" in result
        assert result["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_extract_metadata_with_dict_description(self, postman_parser):
        """Testa extração quando description é um dict."""
        collection = {
            "info": {
                "name": "Test",
                "description": {"content": "Rich description", "version": "1"},
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [],
        }
        content = json.dumps(collection).encode()

        result = await postman_parser.extract_metadata(content)

        assert result["description"] == "Rich description"

    @pytest.mark.asyncio
    async def test_extract_metadata_minimal(self, postman_parser):
        """Testa metadados mínimos."""
        collection = {
            "info": {
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": [],
        }
        content = json.dumps(collection).encode()

        result = await postman_parser.extract_metadata(content)

        assert result["api_count"] == 0
        assert result["folder_count"] == 0
        assert "schema" in result
