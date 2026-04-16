"""Testes unitários para WordParser."""

from unittest.mock import Mock, patch

import pytest

from src.services.parsers.word_parser import WordParser


@pytest.fixture
def word_parser():
    """Fixture para WordParser."""
    return WordParser()


@pytest.fixture
def sample_docx_bytes():
    """Fixture para bytes DOCX válidos (assinatura ZIP)."""
    # DOCX é um ZIP - magic number: PK
    return b"PK\x03\x04\nFake DOCX content"


@pytest.fixture
def invalid_docx_bytes():
    """Fixture para bytes inválidos."""
    return b"This is not a DOCX file"


class TestWordParserValidate:
    """Testes para método validate."""

    def test_validate_valid_docx(self, word_parser, sample_docx_bytes):
        """Testa validação de DOCX válido."""
        assert word_parser.validate(sample_docx_bytes) is True

    def test_validate_invalid_docx(self, word_parser, invalid_docx_bytes):
        """Testa validação de arquivo inválido."""
        assert word_parser.validate(invalid_docx_bytes) is False

    def test_validate_empty_bytes(self, word_parser):
        """Testa validação de bytes vazios."""
        assert word_parser.validate(b"") is False

    def test_validate_short_bytes(self, word_parser):
        """Testa validação de bytes insuficientes."""
        assert word_parser.validate(b"P") is False


class TestWordParserExtractText:
    """Testes para método extract_text."""

    @pytest.mark.asyncio
    async def test_extract_text_invalid_bytes(self, word_parser, invalid_docx_bytes):
        """Testa extração de texto de bytes inválidos."""
        result = await word_parser.extract_text(invalid_docx_bytes)
        assert result == ""

    @pytest.mark.asyncio
    async def test_extract_text_empty_bytes(self, word_parser):
        """Testa extração de texto de bytes vazios."""
        result = await word_parser.extract_text(b"")
        assert result == ""

    @pytest.mark.asyncio
    async def test_extract_text_with_paragraphs(self, word_parser, sample_docx_bytes):
        """Testa extração de texto de parágrafos."""
        with patch("src.services.parsers.word_parser.Document") as mock_doc_class:
            # Mock paragraphs
            mock_para1 = Mock()
            mock_para1.text = "First paragraph"
            mock_para2 = Mock()
            mock_para2.text = "Second paragraph"
            mock_para3 = Mock()
            mock_para3.text = ""  # Empty paragraph should be skipped

            # Mock document
            mock_doc = Mock()
            mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3]
            mock_doc.tables = []
            mock_doc_class.return_value = mock_doc

            result = await word_parser.extract_text(sample_docx_bytes)

            assert result == "First paragraph\n\nSecond paragraph"

    @pytest.mark.asyncio
    async def test_extract_text_with_tables(self, word_parser, sample_docx_bytes):
        """Testa extração de texto de tabelas."""
        with patch("src.services.parsers.word_parser.Document") as mock_doc_class:
            # Mock table
            mock_cell1 = Mock()
            mock_cell1.text = "Cell 1"
            mock_cell2 = Mock()
            mock_cell2.text = "Cell 2"

            mock_row = Mock()
            mock_row.cells = [mock_cell1, mock_cell2]

            mock_table = Mock()
            mock_table.rows = [mock_row]

            # Mock document
            mock_doc = Mock()
            mock_doc.paragraphs = []
            mock_doc.tables = [mock_table]
            mock_doc_class.return_value = mock_doc

            result = await word_parser.extract_text(sample_docx_bytes)

            assert result == "Cell 1 | Cell 2"

    @pytest.mark.asyncio
    async def test_extract_text_paragraphs_and_tables(
        self, word_parser, sample_docx_bytes
    ):
        """Testa extração de parágrafos e tabelas."""
        with patch("src.services.parsers.word_parser.Document") as mock_doc_class:
            # Mock paragraphs
            mock_para = Mock()
            mock_para.text = "Paragraph text"

            # Mock table
            mock_cell = Mock()
            mock_cell.text = "Table cell"
            mock_row = Mock()
            mock_row.cells = [mock_cell]
            mock_table = Mock()
            mock_table.rows = [mock_row]

            # Mock document
            mock_doc = Mock()
            mock_doc.paragraphs = [mock_para]
            mock_doc.tables = [mock_table]
            mock_doc_class.return_value = mock_doc

            result = await word_parser.extract_text(sample_docx_bytes)

            assert result == "Paragraph text\n\nTable cell"

    @pytest.mark.asyncio
    async def test_extract_text_document_error(self, word_parser, sample_docx_bytes):
        """Testa tratamento de erro na extração."""
        with patch("src.services.parsers.word_parser.Document") as mock_doc_class:
            mock_doc_class.side_effect = Exception("Document error")

            result = await word_parser.extract_text(sample_docx_bytes)

            assert result == ""

    @pytest.mark.asyncio
    async def test_extract_text_empty_cells_in_table(
        self, word_parser, sample_docx_bytes
    ):
        """Testa que células vazias em tabelas são ignoradas."""
        with patch("src.services.parsers.word_parser.Document") as mock_doc_class:
            # Mock table with empty cells
            mock_cell1 = Mock()
            mock_cell1.text = "Valid cell"
            mock_cell2 = Mock()
            mock_cell2.text = ""  # Empty cell

            mock_row = Mock()
            mock_row.cells = [mock_cell1, mock_cell2]

            mock_table = Mock()
            mock_table.rows = [mock_row]

            # Mock document
            mock_doc = Mock()
            mock_doc.paragraphs = []
            mock_doc.tables = [mock_table]
            mock_doc_class.return_value = mock_doc

            result = await word_parser.extract_text(sample_docx_bytes)

            assert result == "Valid cell"


class TestWordParserExtractMetadata:
    """Testes para método extract_metadata."""

    @pytest.mark.asyncio
    async def test_extract_metadata_valid_docx(self, word_parser, sample_docx_bytes):
        """Testa extração de metadados de DOCX válido."""
        with patch("src.services.parsers.word_parser.Document") as mock_doc_class:
            # Mock core properties
            mock_props = Mock()
            mock_props.title = "Test Document"
            mock_props.author = "Test Author"
            mock_props.subject = "Test Subject"
            mock_props.comments = "Test Comments"
            mock_props.category = "Test Category"
            mock_props.created = "2026-04-16T12:00:00"
            mock_props.modified = "2026-04-16T13:00:00"
            mock_props.last_modified_by = "Editor"
            mock_props.revision = "2"
            mock_props.version = "1.0"

            # Mock sections
            mock_section = Mock()
            mock_doc = Mock()
            mock_doc.paragraphs = [Mock(), Mock()]  # 2 paragraphs
            mock_doc.tables = [Mock()]  # 1 table
            mock_doc.sections = [mock_section]  # 1 section
            mock_doc.core_properties = mock_props
            mock_doc_class.return_value = mock_doc

            result = await word_parser.extract_metadata(sample_docx_bytes)

            assert result["paragraph_count"] == 2
            assert result["table_count"] == 1
            assert result["section_count"] == 1
            assert result["title"] == "Test Document"
            assert result["author"] == "Test Author"
            assert result["subject"] == "Test Subject"
            assert result["comments"] == "Test Comments"
            assert result["category"] == "Test Category"
            assert result["last_modified_by"] == "Editor"
            assert result["revision"] == "2"
            assert result["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_extract_metadata_invalid_docx(self, word_parser, invalid_docx_bytes):
        """Testa extração de metadados de DOCX inválido."""
        result = await word_parser.extract_metadata(invalid_docx_bytes)
        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_metadata_minimal(self, word_parser, sample_docx_bytes):
        """Testa metadados mínimos (sem propriedades core)."""
        with patch("src.services.parsers.word_parser.Document") as mock_doc_class:
            # Mock com propriedades vazias
            mock_props = Mock()
            mock_props.title = None
            mock_props.author = None

            mock_doc = Mock()
            mock_doc.paragraphs = []
            mock_doc.tables = []
            mock_doc.sections = []
            mock_doc.core_properties = mock_props
            mock_doc_class.return_value = mock_doc

            result = await word_parser.extract_metadata(sample_docx_bytes)

            assert result["paragraph_count"] == 0
            assert result["table_count"] == 0
            assert result["section_count"] == 0
            assert "title" not in result
            assert "author" not in result

    @pytest.mark.asyncio
    async def test_extract_metadata_extraction_error(
        self, word_parser, sample_docx_bytes
    ):
        """Testa tratamento de erro na extração de metadados."""
        with patch("src.services.parsers.word_parser.Document") as mock_doc_class:
            mock_doc_class.side_effect = Exception("Read error")

            result = await word_parser.extract_metadata(sample_docx_bytes)

            # Erro retorna dicionário vazio, não string
            assert result == {}
