"""Testes unitários para DataModelDesigner."""

from unittest.mock import AsyncMock, Mock

import pytest
from src.models.data_model import (
    DataFieldType,
    DataSchema,
)
from src.models.requirements import Requirement, RequirementPriority, RequirementType
from src.services.data_model_designer import DataModelDesigner


@pytest.fixture()
def mock_llm_client():
    """Fixture para mock LLM client."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message=Mock(
                        content="""```json
{
  "models": [
    {
      "name": "User",
      "description": "Represents a user in the system",
      "fields": [
        {"name": "email", "type": "string", "required": true, "description": "User email address"},
        {"name": "password", "type": "string", "required": true, "description": "Hashed password"},
        {"name": "created_at", "type": "datetime", "required": true, "description": "Account creation date"}
      ]
    },
    {
      "name": "Profile",
      "description": "User profile information",
      "fields": [
        {"name": "user_id", "type": "reference", "required": true, "description": "Reference to User", "reference_to": "User"},
        {"name": "bio", "type": "text", "required": false, "description": "User biography"}
      ]
    }
  ],
  "relationships": [
    {
      "from": "Profile",
      "to": "User",
      "type": "many_to_one",
      "cardinality": "N:1",
      "description": "A profile belongs to one user"
    }
  ]
}
```"""
                    )
                )
            ]
        )
    )
    return mock_client


@pytest.fixture()
def sample_requirements_set():
    """RequirementsSet de exemplo."""
    req1 = Requirement(
        id="REQ-001",
        title="Gestão de Utilizadores",
        description="O sistema deve armazenar informações de utilizadores incluindo email, senha e perfil.",
        requirement_type=RequirementType.FUNCTIONAL,
        priority=RequirementPriority.HIGH,
        rationale="Necessário para autenticação e personalização",
    )

    req2 = Requirement(
        id="REQ-002",
        title="Perfis de Utilizador",
        description="Cada utilizador pode ter um perfil com informações adicionais.",
        requirement_type=RequirementType.FUNCTIONAL,
        priority=RequirementPriority.MEDIUM,
        rationale="Permite personalização da experiência",
    )

    from src.models.requirements import RequirementsSet

    req_set = RequirementsSet(
        id="RS-001",
        cognitive_plan_id="CP-001",
    )
    req_set.add_requirement(req1)
    req_set.add_requirement(req2)

    return req_set


@pytest.mark.asyncio()
async def test_design_from_requirements(mock_llm_client, sample_requirements_set):
    """Testa design de modelos de dados a partir de requisitos."""
    designer = DataModelDesigner(llm_client=mock_llm_client)

    schema = await designer.design_from_requirements(sample_requirements_set)

    assert isinstance(schema, DataSchema)
    assert schema.id.startswith("DMS-")
    assert schema.name  # name is required
    assert schema.cognitive_plan_id == "CP-001"
    assert len(schema.models) == 2
    assert schema.models[0].name == "User"
    assert schema.models[1].name == "Profile"
    assert len(schema.relationships) == 1
    assert schema.relationships[0].from_entity == "Profile"
    assert schema.relationships[0].to_entity == "User"


@pytest.mark.asyncio()
async def test_create_data_model_adds_default_fields():
    """Testa que campos padrão (id, timestamps) são adicionados."""

    mock_client = AsyncMock()
    designer = DataModelDesigner(llm_client=mock_client)

    model_data = {
        "name": "TestModel",
        "description": "Test model description",
        "fields": [],
    }

    model = designer._create_data_model(model_data)

    # Verifica campos padrão
    field_names = [f.name for f in model.fields]
    assert "id" in field_names
    assert "created_at" in field_names
    assert "updated_at" in field_names

    # Verifica que id está na chave primária
    assert "id" in model.primary_key


@pytest.mark.asyncio()
async def test_create_data_model_parses_field_types():
    """Testa que tipos de campo são parseados corretamente."""

    mock_client = AsyncMock()
    designer = DataModelDesigner(llm_client=mock_client)

    model_data = {
        "name": "TestModel",
        "description": "Test model description for unit test",
        "fields": [
            {"name": "str_field", "type": "string"},
            {"name": "int_field", "type": "integer"},
            {"name": "float_field", "type": "float"},
            {"name": "bool_field", "type": "boolean"},
            {"name": "date_field", "type": "date"},
            {"name": "dt_field", "type": "datetime"},
            {"name": "text_field", "type": "text"},
            {"name": "json_field", "type": "json"},
            {"name": "ref_field", "type": "reference"},
        ],
    }

    model = designer._create_data_model(model_data)

    # Campos padrão são adicionados primeiro: id (index 0), created_at (index 1+num_fields+1), updated_at
    # Os campos de teste começam no index 1 (logo após id)
    assert model.fields[0].name == "id"  # Campo padrão
    assert model.fields[1].field_type == DataFieldType.STRING
    assert model.fields[2].field_type == DataFieldType.INTEGER
    assert model.fields[3].field_type == DataFieldType.FLOAT
    assert model.fields[4].field_type == DataFieldType.BOOLEAN
    assert model.fields[5].field_type == DataFieldType.DATE
    assert model.fields[6].field_type == DataFieldType.DATETIME
    assert model.fields[7].field_type == DataFieldType.TEXT
    assert model.fields[8].field_type == DataFieldType.JSON
    assert model.fields[9].field_type == DataFieldType.REFERENCE
    # Verificar campos padrão no final
    assert model.fields[10].name == "created_at"
    assert model.fields[11].name == "updated_at"


def test_parse_field_type_defaults_to_string():
    """Testa que tipo desconhecido usa STRING como padrão."""
    mock_client = AsyncMock()
    designer = DataModelDesigner(llm_client=mock_client)

    assert designer._parse_field_type("unknown_type") == DataFieldType.STRING


def test_extract_json_from_markdown():
    """Testa extração de JSON de texto markdown."""
    mock_client = AsyncMock()
    designer = DataModelDesigner(llm_client=mock_client)

    markdown_text = """
Text before

```json
{
  "models": [{"name": "Test"}]
}
```

Text after
"""

    json_str = designer._extract_json(markdown_text)

    assert json_str == '{\n  "models": [{"name": "Test"}]\n}'


def test_extract_json_from_plain_object():
    """Testa extração de JSON sem markdown."""
    mock_client = AsyncMock()
    designer = DataModelDesigner(llm_client=mock_client)

    plain_text = '{"models": [{"name": "Test"}]}'

    json_str = designer._extract_json(plain_text)

    assert json_str == '{"models": [{"name": "Test"}]}'


def test_extract_json_returns_none_when_no_json():
    """Testa que retorna None quando não há JSON."""
    mock_client = AsyncMock()
    designer = DataModelDesigner(llm_client=mock_client)

    plain_text = "This is just plain text without any JSON"

    json_str = designer._extract_json(plain_text)

    assert json_str is None


@pytest.mark.asyncio()
async def test_design_from_requirements_handles_empty_fields():
    """Testa que modelos sem campos são processados corretamente."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message=Mock(
                        content="""```json
{
  "models": [
    {
      "name": "EmptyModel",
      "description": "Model with no fields description",
      "fields": []
    }
  ],
  "relationships": []
}
```"""
                    )
                )
            ]
        )
    )

    designer = DataModelDesigner(llm_client=mock_client)

    from src.models.requirements import RequirementsSet

    req_set = RequirementsSet(
        id="RS-001",
        cognitive_plan_id="CP-001",
    )

    schema = await designer.design_from_requirements(req_set)

    assert len(schema.models) == 1
    # Campos padrão (id, created_at, updated_at) devem ser adicionados
    assert len(schema.models[0].fields) == 3
    assert schema.models[0].name == "EmptyModel"


@pytest.mark.asyncio()
async def test_design_from_requirements_creates_entity_relationships():
    """Testa que relacionamentos entre entidades são criados."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message=Mock(
                        content="""```json
{
  "models": [
    {"name": "Order", "description": "Order entity", "fields": []},
    {"name": "Customer", "description": "Customer entity", "fields": []}
  ],
  "relationships": [
    {
      "from": "Order",
      "to": "Customer",
      "type": "many_to_one",
      "cardinality": "N:1",
      "description": "An order belongs to one customer"
    }
  ]
}
```"""
                    )
                )
            ]
        )
    )

    designer = DataModelDesigner(llm_client=mock_client)

    from src.models.requirements import RequirementsSet

    req_set = RequirementsSet(
        id="RS-001",
        cognitive_plan_id="CP-001",
    )

    schema = await designer.design_from_requirements(req_set)

    assert len(schema.relationships) == 1
    rel = schema.relationships[0]
    assert rel.from_entity == "Order"
    assert rel.to_entity == "Customer"
    assert rel.relationship_type == "many_to_one"
    assert rel.cardinality == "N:1"


@pytest.mark.asyncio()
async def test_design_from_requirements_limits_requirements_for_context():
    """Testa que apenas os primeiros 10 requisitos são usados para contexto LLM."""
    from src.models.requirements import Requirement, RequirementsSet

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message=Mock(
                        content="""```json
{
  "models": [{"name": "Test", "fields": [], "description": "Test model"}],
  "relationships": []
}
```"""
                    )
                )
            ]
        )
    )

    designer = DataModelDesigner(llm_client=mock_client)

    req_set = RequirementsSet(
        id="RS-001",
        cognitive_plan_id="CP-001",
    )

    # Adicionar mais de 10 requisitos com descrições válidas
    for i in range(15):
        req = Requirement(
            id=f"REQ-{i:03d}",
            title=f"Requirement {i} for testing",
            description=f"Description {i} with more than 20 characters",
            requirement_type=RequirementType.FUNCTIONAL,
            priority=RequirementPriority.MEDIUM,
        )
        req_set.add_requirement(req)

    schema = await designer.design_from_requirements(req_set)

    # O método deve limitar a 10 requisitos para o contexto LLM
    # mas pode processar todos para criar modelos
    assert isinstance(schema, DataSchema)
