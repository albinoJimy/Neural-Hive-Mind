"""Testes para APIDocsGenerator."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from src.generators.api_docs_generator import APIDocsGenerator
from src.models import DocFormat, DocType


@pytest.fixture
def generator():
    mock_client = AsyncMock()
    return APIDocsGenerator(llm_client=mock_client)


@pytest.fixture
def sample_endpoints():
    """Endpoints de exemplo para testes."""
    return [
        {
            "path": "/users",
            "method": "GET",
            "summary": "List all users",
            "description": "Retrieves a list of all users",
            "tags": ["users"],
            "parameters": [
                {
                    "name": "limit",
                    "in": "query",
                    "type": "integer",
                    "required": False,
                    "description": "Maximum number of results",
                }
            ],
            "responses": {
                "200": {"description": "List of users"},
                "400": {"description": "Bad request"},
            },
        },
        {
            "path": "/users",
            "method": "POST",
            "summary": "Create user",
            "description": "Creates a new user",
            "tags": ["users"],
            "request_body": {
                "required": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                    },
                },
            },
            "responses": {
                "201": {"description": "User created"},
                "400": {"description": "Validation error"},
            },
        },
    ]


def test_generate_openapi_spec(generator, sample_endpoints):
    """Testa geração de especificação OpenAPI."""
    spec = generator.generate_openapi(
        title="Test API",
        version="1.0.0",
        endpoints=sample_endpoints,
        base_url="https://api.test.com",
        description="Test API for unit tests",
    )

    assert spec["openapi"] == "3.0.0"
    assert spec["info"]["title"] == "Test API"
    assert spec["info"]["version"] == "1.0.0"
    assert len(spec["servers"]) == 1
    assert spec["servers"][0]["url"] == "https://api.test.com"
    assert "/users" in spec["paths"]
    assert "get" in spec["paths"]["/users"]
    assert "post" in spec["paths"]["/users"]


def test_generate_openapi_json(generator, sample_endpoints):
    """Testa geração de JSON string."""
    json_str = generator.generate_openapi_json(
        title="Test API",
        version="1.0.0",
        endpoints=sample_endpoints,
    )

    spec = json.loads(json_str)
    assert spec["info"]["title"] == "Test API"
    assert isinstance(spec["paths"], dict)


def test_openapi_parameters(generator, sample_endpoints):
    """Testa que parâmetros são incluídos corretamente."""
    spec = generator.generate_openapi(
        title="Test API",
        version="1.0.0",
        endpoints=sample_endpoints,
    )

    get_op = spec["paths"]["/users"]["get"]
    assert "parameters" in get_op
    assert len(get_op["parameters"]) == 1
    assert get_op["parameters"][0]["name"] == "limit"
    assert get_op["parameters"][0]["in"] == "query"


def test_openapi_request_body(generator, sample_endpoints):
    """Testa que request body é incluído corretamente."""
    spec = generator.generate_openapi(
        title="Test API",
        version="1.0.0",
        endpoints=sample_endpoints,
    )

    post_op = spec["paths"]["/users"]["post"]
    assert "requestBody" in post_op
    assert post_op["requestBody"]["required"] is True
    assert "application/json" in post_op["requestBody"]["content"]


def test_openapi_responses(generator, sample_endpoints):
    """Testa que respostas são incluídas corretamente."""
    spec = generator.generate_openapi(
        title="Test API",
        version="1.0.0",
        endpoints=sample_endpoints,
    )

    get_op = spec["paths"]["/users"]["get"]
    assert "responses" in get_op
    assert "200" in get_op["responses"]
    assert "400" in get_op["responses"]


def test_openapi_operation_id_generation(generator):
    """Testa geração de operation_id."""
    endpoints = [
        {
            "path": "/users/{id}",
            "method": "GET",
            "summary": "Get user by ID",
        }
    ]

    spec = generator.generate_openapi(
        title="Test API",
        version="1.0.0",
        endpoints=endpoints,
    )

    operation = spec["paths"]["/users/{id}"]["get"]
    assert "operationId" in operation
    # O operation_id substitui / por _
    assert "get" in operation["operationId"]
    assert "users" in operation["operationId"]


def test_generate_fallback_markdown(generator, sample_endpoints):
    """Testa geração de Markdown sem LLM (fallback)."""
    openapi_spec = generator.generate_openapi(
        title="Test API",
        version="1.0.0",
        endpoints=sample_endpoints,
        base_url="https://api.test.com",
    )

    markdown = generator._generate_fallback_markdown(
        title="Test API",
        endpoints=sample_endpoints,
        base_url="https://api.test.com",
        description="Test API description",
        openapi_spec=openapi_spec,
    )

    assert "# Test API API Documentation" in markdown
    assert "https://api.test.com" in markdown
    assert "GET /users" in markdown
    assert "POST /users" in markdown
    assert "Parameters:" in markdown
    assert "| Name |" in markdown


def test_generate_swagger_ui_html(generator):
    """Testa geração de HTML Swagger UI."""
    openapi_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {},
    }

    html = generator.generate_swagger_ui_html(
        openapi_spec=openapi_spec,
        title="API Docs",
    )

    assert "<!DOCTYPE html>" in html
    assert "swagger-ui" in html
    assert "API Docs" in html
    assert "SwaggerUIBundle" in html


@pytest.mark.asyncio
async def test_generate_markdown_with_mock_llm(sample_endpoints):
    """Testa geração de Markdown com LLM mockado."""
    from unittest.mock import AsyncMock, Mock

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message=Mock(
                        content="""# Test API Documentation

## Overview

This is a test API.

## Endpoints

### GET /users

List all users.

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| limit | query | integer | No | Max results |

**Responses:**
- **200**: List of users
- **400**: Bad request

---
"""
                    )
                )
            ]
        )
    )

    generator = APIDocsGenerator(llm_client=mock_client)

    document = await generator.generate_markdown(
        title="Test API",
        endpoints=sample_endpoints,
        base_url="https://api.test.com",
        description="Test API for unit tests",
    )

    assert document.doc_type == DocType.API_DOCS
    assert document.format == DocFormat.MARKDOWN
    # O título é gerado automaticamente como "{title} API Documentation"
    assert "API Documentation" in document.title
    assert "GET /users" in document.content


def test_empty_endpoints_list(generator):
    """Testa comportamento com lista de endpoints vazia."""
    spec = generator.generate_openapi(
        title="Empty API",
        version="1.0.0",
        endpoints=[],
    )

    assert spec["paths"] == {}
    assert spec["info"]["title"] == "Empty API"


def test_endpoint_without_optional_fields(generator):
    """Testa endpoint com campos mínimos."""
    endpoints = [
        {
            "path": "/health",
            "method": "GET",
        }
    ]

    spec = generator.generate_openapi(
        title="Minimal API",
        version="1.0.0",
        endpoints=endpoints,
    )

    assert "/health" in spec["paths"]
    assert "get" in spec["paths"]["/health"]
