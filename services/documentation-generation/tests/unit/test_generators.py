"""Testes unitários para Documentation Generation."""

from unittest.mock import AsyncMock, Mock

import pytest
from src.models import (
    DocFormat,
    DocType,
    ReadmeRequest,
)
from src.services.code_doc_generator import CodeDocGenerator
from src.services.diagram_generator import DiagramGenerator
from src.services.readme_generator import ReadmeGenerator


@pytest.fixture()
def mock_llm_response():
    """Fixture para mock LLM response."""
    mock = Mock()
    mock.choices = [Mock()]
    mock.choices[0].message = Mock()
    mock.choices[0].message.content = """# Test Project

This is a test project.

## Features

- Feature 1
- Feature 2

## Installation

Run `pip install test-project`

## Usage

```python
import test_project
test_project.run()
```
"""
    return mock


@pytest.fixture()
def readme_generator(mock_llm_response):
    """Fixture para ReadmeGenerator."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)
    return ReadmeGenerator(llm_client=mock_client)


@pytest.mark.asyncio()
async def test_generate_readme(readme_generator):
    """Testa geração de README."""
    request = ReadmeRequest(
        project_name="Test Project",
        project_description="A test project for documentation",
        features=["Feature 1", "Feature 2"],
        installation="pip install test-project",
        usage="python -m test_project",
    )

    document = await readme_generator.generate(request)

    assert document.doc_type == DocType.README
    assert document.format == DocFormat.MARKDOWN
    assert "Test Project" in document.content
    assert document.file_path == "README.md"


@pytest.mark.asyncio()
async def test_diagram_generator():
    """Testa geração de diagramas Mermaid."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = """sequenceDiagram
    participant User
    participant System
    User->>System: Request
    System-->>User: Response
"""

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    generator = DiagramGenerator(llm_client=mock_client)
    document = await generator.generate(
        description="User requests data from system", diagram_type="sequence"
    )

    assert document.doc_type == DocType.DIAGRAM
    assert document.format == DocFormat.MERMAID
    assert "sequenceDiagram" in document.content


@pytest.mark.asyncio()
async def test_code_doc_generator():
    """Testa geração de documentação de código."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = """# Code Documentation

## Purpose
This function calculates the sum of two numbers.

## Parameters
- a: First number
- b: Second number

## Returns
The sum of a and b

## Example
```python
result = calculate_sum(1, 2)  # Returns 3
```
"""

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    generator = CodeDocGenerator(llm_client=mock_client)
    document = await generator.generate_from_code(
        code="def calculate_sum(a, b): return a + b", file_path="utils/math.py", language="python"
    )

    assert document.doc_type == DocType.API_DOCS
    assert "calculate_sum" in document.content


def test_extract_python_functions(mock_llm_response):
    """Testa extração de funções Python."""
    mock_client = AsyncMock()
    generator = CodeDocGenerator(llm_client=mock_client)

    code = """
def hello_world():
    \"\"\"Prints hello world.\"\"\"
    print("Hello, World!")

class Calculator:
    \"\"\"A simple calculator.\"\"\"
    def add(self, a, b):
        return a + b
"""

    items = generator.extract_functions(code, "python")

    assert len(items) == 3
    assert items[0]["name"] == "hello_world"
    assert items[0]["type"] == "function"
    assert items[1]["name"] == "Calculator"
    assert items[1]["type"] == "class"


def test_extract_functions_empty_code(mock_llm_response):
    """Testa extração de código vazio."""
    mock_client = AsyncMock()
    generator = CodeDocGenerator(llm_client=mock_client)
    items = generator.extract_functions("", "python")
    assert items == []


def test_extract_functions_invalid_code(mock_llm_response):
    """Testa extração de código inválido."""
    mock_client = AsyncMock()
    generator = CodeDocGenerator(llm_client=mock_client)
    items = generator.extract_functions("this is not valid python code", "python")
    assert items == []
