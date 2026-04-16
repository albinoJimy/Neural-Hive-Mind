"""Testes para modelos DocumentationSet e Diagram."""

import pytest
from src.models import (
    Diagram,
    DiagramType,
    DocFormat,
    DocType,
    Document,
    DocumentationSet,
)


@pytest.fixture
def sample_document():
    """Documento de exemplo."""
    return Document(
        id="doc-1",
        doc_type=DocType.API_DOCS,
        format=DocFormat.MARKDOWN,
        title="API Docs",
        content="# API\n\nContent here",
    )


@pytest.fixture
def sample_diagram():
    """Diagrama de exemplo."""
    return Diagram(
        id="diag-1",
        diagram_type=DiagramType.SEQUENCE,
        title="User Flow",
        mermaid_code="sequenceDiagram\n    User->>System: Request",
    )


def test_documentation_set_creation():
    """Testa criação de DocumentationSet."""
    doc_set = DocumentationSet(
        id="set-1",
        project_id="proj-1",
    )

    assert doc_set.id == "set-1"
    assert doc_set.project_id == "proj-1"
    assert doc_set.documents == []
    assert doc_set.diagrams == []
    assert doc_set.metadata == {}


def test_documentation_set_add_document(sample_document):
    """Testa adição de documento ao conjunto."""
    doc_set = DocumentationSet(
        id="set-1",
        project_id="proj-1",
    )

    doc_set.add_document(sample_document)

    assert len(doc_set.documents) == 1
    assert doc_set.documents[0].id == "doc-1"
    assert doc_set.updated_at is not None


def test_documentation_set_add_diagram(sample_diagram):
    """Testa adição de diagrama ao conjunto."""
    doc_set = DocumentationSet(
        id="set-1",
        project_id="proj-1",
    )

    doc_set.add_diagram(sample_diagram)

    assert len(doc_set.diagrams) == 1
    assert doc_set.diagrams[0].id == "diag-1"
    assert doc_set.updated_at is not None


def test_documentation_set_get_by_type(sample_document):
    """Testa filtro de documentos por tipo."""
    doc_set = DocumentationSet(
        id="set-1",
        project_id="proj-1",
    )

    doc_set.add_document(sample_document)

    readme = Document(
        id="doc-2",
        doc_type=DocType.README,
        format=DocFormat.MARKDOWN,
        title="README",
        content="...",
    )
    doc_set.add_document(readme)

    api_docs = doc_set.get_by_type(DocType.API_DOCS)
    assert len(api_docs) == 1
    assert api_docs[0].id == "doc-1"

    readmes = doc_set.get_by_type(DocType.README)
    assert len(readmes) == 1
    assert readmes[0].id == "doc-2"


def test_documentation_set_get_diagrams_by_type(sample_diagram):
    """Testa filtro de diagramas por tipo."""
    doc_set = DocumentationSet(
        id="set-1",
        project_id="proj-1",
    )

    doc_set.add_diagram(sample_diagram)

    flowchart = Diagram(
        id="diag-2",
        diagram_type=DiagramType.FLOWCHART,
        title="Process Flow",
        mermaid_code="graph TD\n    A-->B",
    )
    doc_set.add_diagram(flowchart)

    sequences = doc_set.get_diagrams_by_type(DiagramType.SEQUENCE)
    assert len(sequences) == 1
    assert sequences[0].id == "diag-1"

    flowcharts = doc_set.get_diagrams_by_type(DiagramType.FLOWCHART)
    assert len(flowcharts) == 1
    assert flowcharts[0].id == "diag-2"


def test_diagram_creation():
    """Testa criação de Diagram."""
    diagram = Diagram(
        id="diag-1",
        diagram_type=DiagramType.SEQUENCE,
        title="User Authentication",
        mermaid_code="sequenceDiagram\n    User->>Auth: Login",
    )

    assert diagram.id == "diag-1"
    assert diagram.diagram_type == DiagramType.SEQUENCE
    assert diagram.title == "User Authentication"
    assert "sequenceDiagram" in diagram.mermaid_code
    assert diagram.rendered_content is None
    assert diagram.metadata == {}


def test_diagram_with_rendered_content():
    """Testa diagrama com conteúdo renderizado."""
    diagram = Diagram(
        id="diag-1",
        diagram_type=DiagramType.C4,
        title="System Architecture",
        mermaid_code="...",
        rendered_content="<svg>...</svg>",
    )

    assert diagram.rendered_content == "<svg>...</svg>"


def test_diagram_types():
    """Testa tipos de diagrama disponíveis."""
    assert DiagramType.SEQUENCE == "sequence"
    assert DiagramType.FLOWCHART == "flowchart"
    assert DiagramType.C4 == "c4"
    assert DiagramType.ER == "er"
    assert DiagramType.CLASS == "class"
    assert DiagramType.STATE == "state"
    assert DiagramType.GANTT == "gantt"


def test_documentation_set_metadata():
    """Testa metadados do DocumentationSet."""
    doc_set = DocumentationSet(
        id="set-1",
        project_id="proj-1",
        metadata={"version": "1.0", "author": "test"},
    )

    assert doc_set.metadata["version"] == "1.0"
    assert doc_set.metadata["author"] == "test"


def test_diagram_metadata():
    """Testa metadados do Diagram."""
    diagram = Diagram(
        id="diag-1",
        diagram_type=DiagramType.SEQUENCE,
        title="Test",
        mermaid_code="...",
        metadata={"source": "ai-generated", "confidence": 0.95},
    )

    assert diagram.metadata["source"] == "ai-generated"
    assert diagram.metadata["confidence"] == 0.95


def test_documentation_set_multiple_filters():
    """Testa filtros múltiplos no DocumentationSet."""
    doc_set = DocumentationSet(id="set-1", project_id="proj-1")

    # Adicionar vários documentos
    for i in range(5):
        doc = Document(
            id=f"doc-{i}",
            doc_type=DocType.API_DOCS if i % 2 == 0 else DocType.README,
            format=DocFormat.MARKDOWN,
            title=f"Document {i}",
            content="...",
        )
        doc_set.add_document(doc)

    api_docs = doc_set.get_by_type(DocType.API_DOCS)
    readmes = doc_set.get_by_type(DocType.README)

    assert len(api_docs) == 3
    assert len(readmes) == 2


def test_document_version_default():
    """Testa versão padrão do documento."""
    doc = Document(
        id="doc-1",
        doc_type=DocType.API_DOCS,
        title="API Docs",
        content="# API\n\nContent here",
    )

    assert doc.version == "1.0.0"


def test_document_checksum_calculated():
    """Testa que checksum é calculado automaticamente."""
    doc = Document(
        id="doc-1",
        doc_type=DocType.API_DOCS,
        title="API Docs",
        content="# API\n\nContent here",
    )

    # Checksum deve ser um hash MD5 (32 caracteres hexadecimais)
    assert doc.checksum is not None
    assert len(doc.checksum) == 32
    assert all(c in "0123456789abcdef" for c in doc.checksum)


def test_document_word_count_calculated():
    """Testa que word_count é calculado automaticamente."""
    doc = Document(
        id="doc-1",
        doc_type=DocType.API_DOCS,
        title="API Docs",
        content="# API\n\nContent here with some words",
    )

    # 7 palavras: #, API, Content, here, with, some, words
    assert doc.word_count == 7


def test_document_empty_content():
    """Testa documento com conteúdo vazio."""
    doc = Document(
        id="doc-1",
        doc_type=DocType.API_DOCS,
        title="Empty Doc",
        content="",
    )

    assert doc.checksum is None
    assert doc.word_count == 0


def test_document_increment_version():
    """Testa incremento de versão do documento."""
    doc = Document(
        id="doc-1",
        doc_type=DocType.API_DOCS,
        title="API Docs",
        content="Content",
    )

    assert doc.version == "1.0.0"

    new_version = doc.increment_version()
    assert new_version == "1.0.1"
    assert doc.version == "1.0.1"


def test_document_update_content():
    """Testa atualização de conteúdo com recálculo."""
    doc = Document(
        id="doc-1",
        doc_type=DocType.API_DOCS,
        title="API Docs",
        content="Original content",
    )

    original_checksum = doc.checksum
    original_word_count = doc.word_count

    # Atualizar conteúdo
    doc.update_content("New content with different words")

    assert doc.checksum != original_checksum
    assert doc.word_count != original_word_count
    assert doc.word_count == 5  # "New content with different words"
    assert doc.content == "New content with different words"
