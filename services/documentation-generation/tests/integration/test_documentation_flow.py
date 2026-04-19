"""Testes de integração Kafka para Documentation Generation."""

import json
from unittest.mock import AsyncMock, Mock

import pytest
from src.consumers.architecture_plan_consumer import ArchitecturePlanConsumer
from src.generators.markdown_generator import MarkdownGenerator
from src.producers.docs_producer import DocumentationProducer
from src.services.architecture_docs_generator import ArchitectureDocsGenerator
from src.services.code_doc_generator import CodeDocGenerator
from src.services.diagram_generator import DiagramGenerator
from src.services.readme_generator import ReadmeGenerator


@pytest.fixture()
def mock_settings():
    """Fixture com configurações de teste."""

    class MockSettings:
        kafka_bootstrap_servers = "localhost:9092"
        kafka_consumer_group = "test-documentation-consumers"
        kafka_input_topic = "architecture.plans.generated"
        kafka_output_topic = "documentation.generated"
        kafka_dlq_topic = "documentation.dlq"
        openai_api_key = "test-key"
        llm_model = "gpt-4"

    return MockSettings()


@pytest.fixture()
def mock_llm_client():
    """Fixture para mock LLM client."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message=Mock(
                        content="""# Test Project README

Test project description.

## Features

- User Management
- API Gateway
- Database Service

## Installation

docker-compose up -d

## Usage

See API documentation at /docs

## Tech Stack

- Python 3.12
- FastAPI
- Kafka
"""
                    )
                )
            ]
        )
    )
    return mock_client


@pytest.mark.asyncio()
async def test_architecture_plan_consumer_processes_message(mock_settings, mock_llm_client):
    """Testa que o consumer processa mensagens do Kafka."""
    # Arrange
    readme_generator = ReadmeGenerator(llm_client=mock_llm_client)
    code_doc_generator = CodeDocGenerator(llm_client=mock_llm_client)
    mock_producer = AsyncMock()

    consumer = ArchitecturePlanConsumer(
        readme_generator=readme_generator,
        code_doc_generator=code_doc_generator,
        producer=mock_producer,
    )
    consumer._bootstrap_servers = mock_settings.kafka_bootstrap_servers
    consumer._group_id = mock_settings.kafka_consumer_group
    consumer._input_topic = mock_settings.kafka_input_topic

    # Criar mensagem mock
    mock_message = Mock()
    mock_message.topic = mock_settings.kafka_input_topic
    mock_message.partition = 0
    mock_message.offset = 0
    mock_message.value = json.dumps(
        {
            "plan_id": "plan-123",
            "cognitive_plan_id": "cp-123",
            "project_name": "Test Project",
            "description": "A test project for integration testing",
            "architecture_type": "microservices",
            "components": [
                {"name": "User Management", "type": "service"},
                {"name": "API Gateway", "type": "gateway"},
                {"name": "Database", "type": "database"},
            ],
            "installation": "docker-compose up -d",
            "usage": "See API documentation at /docs",
            "tech_stack": "Python 3.12, FastAPI, Kafka",
        }
    ).encode("utf-8")

    # Act
    await consumer._process_message(mock_message)

    # Assert
    mock_producer.publish_documentation_generated.assert_called_once()


@pytest.mark.asyncio()
async def test_documentation_publisher_sends_to_kafka():
    """Testa que o producer envia eventos para o Kafka."""
    # Arrange
    producer = DocumentationProducer()
    producer._producer = AsyncMock()
    producer._producer.send_and_wait = AsyncMock()
    producer._running = True

    # Act
    await producer.publish_documentation_generated(
        document_id="doc-123",
        doc_type="readme",
        source_type="architecture",
        source_id="plan-123",
        title="Project README",
        file_path="docs/README.md",
    )

    # Assert
    producer._producer.send_and_wait.assert_called_once()


@pytest.mark.asyncio()
async def test_consumer_handles_invalid_json(mock_settings, mock_llm_client):
    """Testa que o consumer lida com JSON inválido."""
    # Arrange
    readme_generator = ReadmeGenerator(llm_client=mock_llm_client)
    code_doc_generator = CodeDocGenerator(llm_client=mock_llm_client)
    mock_producer = AsyncMock()

    consumer = ArchitecturePlanConsumer(
        readme_generator=readme_generator,
        code_doc_generator=code_doc_generator,
        producer=mock_producer,
    )

    # Criar mensagem com JSON inválido
    mock_message = Mock()
    mock_message.value = b"invalid json"

    # Act & Assert (não deve levantar exceção)
    await consumer._process_message(mock_message)


@pytest.mark.asyncio()
async def test_consumer_handles_missing_plan_id(mock_settings, mock_llm_client):
    """Testa que o consumer lida com plan_id ausente."""
    # Arrange
    readme_generator = ReadmeGenerator(llm_client=mock_llm_client)
    code_doc_generator = CodeDocGenerator(llm_client=mock_llm_client)
    mock_producer = AsyncMock()

    consumer = ArchitecturePlanConsumer(
        readme_generator=readme_generator,
        code_doc_generator=code_doc_generator,
        producer=mock_producer,
    )

    # Criar mensagem sem plan_id
    mock_message = Mock()
    mock_message.value = json.dumps(
        {
            "project_name": "Test",
            "description": "Test description",
        }
    ).encode("utf-8")

    # Act & Assert (não deve levantar exceção)
    await consumer._process_message(mock_message)

    # Producer não deve ser chamado (sem plan_id)
    mock_producer.publish_documentation_generated.assert_not_called()


@pytest.mark.asyncio()
async def test_end_to_end_documentation_flow(mock_settings, mock_llm_client):
    """Teste E2E: mensagem entra, documentação é gerada, evento publicado."""
    # Arrange
    readme_generator = ReadmeGenerator(llm_client=mock_llm_client)
    code_doc_generator = CodeDocGenerator(llm_client=mock_llm_client)
    mock_producer = AsyncMock()

    consumer = ArchitecturePlanConsumer(
        readme_generator=readme_generator,
        code_doc_generator=code_doc_generator,
        producer=mock_producer,
    )

    mock_message = Mock()
    mock_message.value = json.dumps(
        {
            "plan_id": "plan-e2e",
            "cognitive_plan_id": "cp-e2e",
            "project_name": "E2E Test Project",
            "description": "End to end test project with comprehensive documentation",
            "components": [
                {"name": "Service A", "type": "service"},
                {"name": "Service B", "type": "service"},
            ],
            "installation": "npm install",
            "usage": "npm start",
            "tech_stack": "Node.js, TypeScript",
        }
    ).encode("utf-8")

    # Act
    await consumer._process_message(mock_message)

    # Assert
    assert mock_producer.publish_documentation_generated.call_count == 1
    call_args = mock_producer.publish_documentation_generated.call_args
    assert call_args[1]["source_id"] == "plan-e2e"
    assert call_args[1]["doc_type"] == "readme"


@pytest.mark.asyncio()
async def test_markdown_generator_api_doc():
    """Testa geração de documentação de API em Markdown."""
    generator = MarkdownGenerator()

    document = generator.generate_api_doc(
        service_name="User Service",
        base_url="https://api.example.com/v1",
        endpoints=[
            {
                "method": "GET",
                "path": "/users",
                "description": "List all users",
                "params": [
                    {
                        "name": "limit",
                        "type": "integer",
                        "required": False,
                        "description": "Max results",
                    },
                    {
                        "name": "offset",
                        "type": "integer",
                        "required": False,
                        "description": "Pagination offset",
                    },
                ],
                "responses": {"200": "List of users", "400": "Bad request"},
            },
            {
                "method": "POST",
                "path": "/users",
                "description": "Create a new user",
                "params": [
                    {
                        "name": "name",
                        "type": "string",
                        "required": True,
                        "description": "User name",
                    },
                    {
                        "name": "email",
                        "type": "string",
                        "required": True,
                        "description": "User email",
                    },
                ],
                "responses": {"201": "User created", "400": "Validation error"},
            },
        ],
        description="User management API service",
    )

    assert document.doc_type == "api_docs"
    assert "User Service API Documentation" in document.content
    assert "GET /users" in document.content
    assert "POST /users" in document.content
    assert "limit" in document.content
    assert "name" in document.content


@pytest.mark.asyncio()
async def test_markdown_generator_user_guide():
    """Testa geração de guia de usuário em Markdown."""
    generator = MarkdownGenerator()

    document = generator.generate_user_guide(
        title="User Guide",
        features=[
            {
                "name": "Authentication",
                "description": "Secure login with OAuth2",
                "usage": "Click 'Login' button and authorize",
            },
            {
                "name": "Dashboard",
                "description": "Overview of your data",
                "usage": "Navigate to /dashboard",
            },
        ],
        getting_started="1. Create an account\n2. Verify your email\n3. Login",
        examples=[
            {
                "title": "Creating a Project",
                "description": "How to create a new project",
                "code": "project create --name MyProject",
                "language": "bash",
            }
        ],
    )

    assert document.title == "User Guide"
    assert "Authentication" in document.content
    assert "Dashboard" in document.content
    assert "Getting Started" in document.content
    assert "Creating a Project" in document.content
    assert "project create --name MyProject" in document.content


@pytest.mark.asyncio()
async def test_architecture_docs_generator(mock_llm_client):
    """Testa geração de documentação de arquitetura."""
    mock_llm_client.chat.completions.create = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message=Mock(
                        content="""# System Architecture

## Overview

This system uses microservices architecture.

## Components

- API Gateway: Routes requests
- User Service: Manages users
- Database: Stores data

## Communication

Services communicate via Kafka messaging.

## Diagram

```mermaid
graph TD
    Gateway[API Gateway]
    UserSvc[User Service]
    DB[(Database)]
    Gateway --> UserSvc
    UserSvc --> DB
```
"""
                    )
                )
            ]
        )
    )

    generator = ArchitectureDocsGenerator(llm_client=mock_llm_client)

    document = await generator.generate_from_requirements(
        system_name="Test System",
        description="A test microservices system",
        components=[
            {
                "name": "API Gateway",
                "responsibility": "Route requests to services",
                "interfaces": ["REST API", "GraphQL"],
            },
            {
                "name": "User Service",
                "responsibility": "Manage user data",
                "interfaces": ["gRPC", "Kafka events"],
            },
        ],
        non_functional=["High availability", "Scalability", "Security"],
        patterns=["CQRS", "Event Sourcing"],
    )

    assert document.doc_type == "architecture"
    assert "Test System" in document.title
    assert "microservices" in document.content.lower()


@pytest.mark.asyncio()
async def test_diagram_generator_sequence(mock_llm_client):
    """Testa geração de diagrama de sequência."""
    mock_llm_client.chat.completions.create = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message=Mock(
                        content="""sequenceDiagram
    participant User
    participant API
    participant DB
    User->>API: POST /users
    API->>DB: INSERT user
    DB-->>API: user created
    API-->>User: 201 Created
"""
                    )
                )
            ]
        )
    )

    generator = DiagramGenerator(llm_client=mock_llm_client)

    document = await generator.generate(
        description="User creates account through API",
        diagram_type="sequence",
    )

    assert document.doc_type == "diagram"
    assert "sequenceDiagram" in document.content
    assert "User" in document.content
    assert "API" in document.content


@pytest.mark.asyncio()
async def test_markdown_generator_format_table():
    """Testa formatação de tabela em Markdown."""
    generator = MarkdownGenerator()

    table = generator.format_table(
        headers=["Name", "Type", "Required"],
        rows=[
            ["id", "integer", "Yes"],
            ["name", "string", "Yes"],
            ["email", "string", "No"],
        ],
    )

    assert "| Name" in table
    assert "| id" in table
    assert "| integer" in table
    assert "---" in table  # separator line


@pytest.mark.asyncio()
async def test_markdown_generator_changelog():
    """Testa geração de CHANGELOG."""
    generator = MarkdownGenerator()

    document = generator.generate_changelog(
        project_name="My Project",
        versions=[
            {
                "version": "1.0.0",
                "date": "2026-04-01",
                "changes": [
                    {"type": "added", "description": "Initial release"},
                    {"type": "added", "description": "User authentication"},
                    {"type": "fixed", "description": "Login bug"},
                ],
            },
            {
                "version": "0.9.0",
                "date": "2026-03-15",
                "changes": [
                    {"type": "added", "description": "Beta release"},
                ],
            },
        ],
    )

    assert "My Project" in document.content
    assert "## [1.0.0]" in document.content
    assert "### Added" in document.content
    assert "### Fixed" in document.content
    assert "Initial release" in document.content
