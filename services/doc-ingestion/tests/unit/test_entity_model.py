"""Testes unitários para modelos de entidades."""

from src.models.entities import EntitySet, EntityType, ExtractedEntity


def test_entity_type_enum():
    """Testa enum EntityType."""
    # Assert
    assert EntityType.FUNCTIONALITY == "functionality"
    assert EntityType.REQUIREMENT == "requirement"
    assert EntityType.DATA_MODEL == "data_model"
    assert EntityType.API == "api"
    assert EntityType.TECH_STACK == "tech_stack"
    assert EntityType.DEPENDENCY == "dependency"


def test_extracted_entity_creation():
    """Testa criação de ExtractedEntity."""
    # Arrange & Act
    entity = ExtractedEntity(
        id="ENT-001",
        type=EntityType.FUNCTIONALITY,
        name="User Authentication",
        description="Sistema de autenticação de usuários",
        source_text="O sistema deve permitir autenticação via email e senha",
        confidence_score=0.95,
        document_id="DOC-001",
    )

    # Assert
    assert entity.id == "ENT-001"
    assert entity.type == EntityType.FUNCTIONALITY
    assert entity.name == "User Authentication"
    assert entity.description == "Sistema de autenticação de usuários"
    assert entity.confidence_score == 0.95
    assert entity.document_id == "DOC-001"


def test_extracted_entity_with_optional_fields():
    """Testa ExtractedEntity com campos opcionais."""
    # Arrange & Act
    entity = ExtractedEntity(
        id="ENT-002",
        type=EntityType.API,
        name="GET /api/users",
        description="Endpoint para listar usuários",
        source_text="GET /api/users - retorna lista de usuários",
        confidence_score=0.88,
        document_id="DOC-002",
        page_number=5,
        section="API Reference",
        metadata={
            "method": "GET",
            "path": "/api/users",
            "auth_required": True,
        },
    )

    # Assert
    assert entity.page_number == 5
    assert entity.section == "API Reference"
    assert entity.metadata["method"] == "GET"
    assert entity.metadata["auth_required"] is True


def test_extracted_entity_default_values():
    """Testa valores padrão de ExtractedEntity."""
    # Arrange & Act
    entity = ExtractedEntity(
        id="ENT-003",
        type=EntityType.REQUIREMENT,
        name="Req 1",
        description="Requisito",
        source_text="Texto fonte",
        confidence_score=0.75,
        document_id="DOC-003",
    )

    # Assert
    assert entity.page_number is None
    assert entity.section is None
    assert entity.metadata == {}


def test_extracted_entity_validation():
    """Testa validação de confidence_score."""
    # Arrange - valor válido
    entity = ExtractedEntity(
        id="ENT-004",
        type=EntityType.DATA_MODEL,
        name="User Model",
        description="Modelo de usuário",
        source_text="User model",
        confidence_score=1.0,
        document_id="DOC-004",
    )

    # Assert
    assert entity.confidence_score == 1.0


def test_entity_set_creation():
    """Testa criação de EntitySet."""
    # Arrange
    entities = [
        ExtractedEntity(
            id="ENT-001",
            type=EntityType.FUNCTIONALITY,
            name="Func 1",
            description="Funcionalidade 1",
            source_text="Texto",
            confidence_score=0.9,
            document_id="DOC-001",
        ),
        ExtractedEntity(
            id="ENT-002",
            type=EntityType.REQUIREMENT,
            name="Req 1",
            description="Requisito 1",
            source_text="Texto",
            confidence_score=0.85,
            document_id="DOC-001",
        ),
        ExtractedEntity(
            id="ENT-003",
            type=EntityType.DATA_MODEL,
            name="Model 1",
            description="Modelo 1",
            source_text="Texto",
            confidence_score=0.92,
            document_id="DOC-001",
        ),
        ExtractedEntity(
            id="ENT-004",
            type=EntityType.API,
            name="API 1",
            description="API 1",
            source_text="Texto",
            confidence_score=0.88,
            document_id="DOC-001",
        ),
        ExtractedEntity(
            id="ENT-005",
            type=EntityType.TECH_STACK,
            name="Tech 1",
            description="Tech 1",
            source_text="Texto",
            confidence_score=0.90,
            document_id="DOC-001",
        ),
    ]

    # Act
    entity_set = EntitySet(document_id="DOC-001", entities=entities)

    # Assert
    assert entity_set.document_id == "DOC-001"
    assert len(entity_set.entities) == 5
    assert entity_set.functionality_count == 1
    assert entity_set.requirement_count == 1
    assert entity_set.data_model_count == 1
    assert entity_set.api_count == 1
    assert entity_set.tech_stack_count == 1
    assert entity_set.dependency_count == 0


def test_entity_set_with_multiple_entities_per_type():
    """Testa EntitySet com múltiplas entidades por tipo."""
    # Arrange
    entities = [
        ExtractedEntity(
            id=f"ENT-{i:03d}",
            type=EntityType.FUNCTIONALITY if i < 3 else EntityType.REQUIREMENT,
            name=f"Entity {i}",
            description=f"Description {i}",
            source_text="Text",
            confidence_score=0.9,
            document_id="DOC-002",
        )
        for i in range(5)
    ]

    # Act
    entity_set = EntitySet(document_id="DOC-002", entities=entities)

    # Assert
    assert entity_set.functionality_count == 3
    assert entity_set.requirement_count == 2


def test_entity_set_default_values():
    """Testa valores padrão de EntitySet."""
    # Arrange & Act
    entity_set = EntitySet(document_id="DOC-003", entities=[])

    # Assert
    assert entity_set.entities == []
    assert entity_set.functionality_count == 0
    assert entity_set.requirement_count == 0
    assert entity_set.data_model_count == 0
    assert entity_set.api_count == 0
    assert entity_set.tech_stack_count == 0
    assert entity_set.dependency_count == 0


def test_entity_set_extracted_at():
    """Testa campo extracted_at de EntitySet."""
    # Arrange & Act
    entity_set = EntitySet(document_id="DOC-004", entities=[])

    # Assert
    assert entity_set.extracted_at is not None
    assert entity_set.total_count == 0


def test_entity_set_total_count():
    """Testa propriedade total_count de EntitySet."""
    # Arrange
    entities = [
        ExtractedEntity(
            id=f"ENT-{i:03d}",
            type=EntityType.FUNCTIONALITY,
            name=f"Entity {i}",
            description=f"Description {i}",
            source_text="Text",
            confidence_score=0.9,
            document_id="DOC-005",
        )
        for i in range(10)
    ]

    # Act
    entity_set = EntitySet(document_id="DOC-005", entities=entities)

    # Assert
    assert entity_set.total_count == 10
