"""Testes unitários para PDFParser."""

from unittest.mock import Mock, patch

import pytest

from src.services.parsers.pdf_parser import PDFParser


@pytest.fixture
def pdf_parser():
    """Fixture para PDFParser."""
    return PDFParser()


@pytest.fixture
def sample_pdf_bytes():
    """Fixture para bytes PDF válidos (header mágico)."""
    # PDF mínimo válido com header mágico
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n%%EOF"


@pytest.fixture
def invalid_pdf_bytes():
    """Fixture para bytes inválidos."""
    return b"This is not a PDF file"


@pytest.fixture
def encrypted_pdf_bytes():
    """Fixture para PDF criptografado (header mágico)."""
    return b"%PDF-1.4\n%%EOF"


class TestPDFParserValidate:
    """Testes para método validate."""

    def test_validate_valid_pdf(self, pdf_parser, sample_pdf_bytes):
        """Testa validação de PDF válido."""
        assert pdf_parser.validate(sample_pdf_bytes) is True

    def test_validate_invalid_pdf(self, pdf_parser, invalid_pdf_bytes):
        """Testa validação de arquivo inválido."""
        assert pdf_parser.validate(invalid_pdf_bytes) is False

    def test_validate_empty_bytes(self, pdf_parser):
        """Testa validação de bytes vazios."""
        assert pdf_parser.validate(b"") is False

    def test_validate_short_bytes(self, pdf_parser):
        """Testa validação de bytes insuficientes."""
        assert pdf_parser.validate(b"%PD") is False


class TestPDFParserExtractText:
    """Testes para método extract_text."""

    @pytest.mark.asyncio
    async def test_extract_text_invalid_bytes(self, pdf_parser, invalid_pdf_bytes):
        """Testa extração de texto de bytes inválidos."""
        result = await pdf_parser.extract_text(invalid_pdf_bytes)
        assert result == ""

    @pytest.mark.asyncio
    async def test_extract_text_empty_bytes(self, pdf_parser):
        """Testa extração de texto de bytes vazios."""
        result = await pdf_parser.extract_text(b"")
        assert result == ""

    @pytest.mark.asyncio
    async def test_extract_text_with_pdfplumber_success(
        self, pdf_parser, sample_pdf_bytes
    ):
        """Testa extração bem-sucedida com pdfplumber."""
        with patch("src.services.parsers.pdf_parser.pdfplumber") as mock_pdfplumber:
            # Mock page
            mock_page = Mock()
            mock_page.extract_text.return_value = "Sample PDF content"

            # Mock pdf
            mock_pdf = Mock()
            mock_pdf.pages.__iter__ = Mock(return_value=iter([mock_page]))
            mock_pdf.__enter__ = Mock(return_value=mock_pdf)
            mock_pdf.__exit__ = Mock(return_value=False)

            mock_pdfplumber.open.return_value = mock_pdf

            result = await pdf_parser.extract_text(sample_pdf_bytes)

            # strip() remove espaços em branco no final
            assert result == "Sample PDF content"

    @pytest.mark.asyncio
    async def test_extract_text_pdfplumber_fallback_to_pypdf2(
        self, pdf_parser, sample_pdf_bytes
    ):
        """Testa fallback para PyPDF2 quando pdfplumber falha."""
        with patch("src.services.parsers.pdf_parser.pdfplumber") as mock_pdfplumber, \
             patch("src.services.parsers.pdf_parser.PyPDF2Reader") as mock_pypdf2:
            # pdfplumber raises exception
            mock_pdfplumber.open.side_effect = Exception("pdfplumber failed")

            # Mock PyPDF2 page
            mock_page = Mock()
            mock_page.extract_text.return_value = "Fallback text"

            # Mock PyPDF2 reader
            mock_reader = Mock()
            mock_reader.pages = [mock_page]
            mock_pypdf2.return_value = mock_reader

            result = await pdf_parser.extract_text(sample_pdf_bytes)

            # strip() remove espaços em branco no final
            assert result == "Fallback text"

    @pytest.mark.asyncio
    async def test_extract_text_both_parsers_fail(self, pdf_parser, sample_pdf_bytes):
        """Testa retorno vazio quando ambos parsers falham."""
        with patch("src.services.parsers.pdf_parser.pdfplumber") as mock_pdfplumber, \
             patch("src.services.parsers.pdf_parser.PyPDF2Reader") as mock_pypdf2:
            # Ambos falham
            mock_pdfplumber.open.side_effect = Exception("Failed")
            mock_pypdf2.side_effect = Exception("Failed")

            result = await pdf_parser.extract_text(sample_pdf_bytes)

            assert result == ""

    @pytest.mark.asyncio
    async def test_extract_text_multiple_pages(self, pdf_parser, sample_pdf_bytes):
        """Testa extração de múltiplas páginas."""
        with patch("src.services.parsers.pdf_parser.pdfplumber") as mock_pdfplumber:
            # Mock pages
            mock_page1 = Mock()
            mock_page1.extract_text.return_value = "Page 1 content"
            mock_page2 = Mock()
            mock_page2.extract_text.return_value = "Page 2 content"

            # Mock pdf
            mock_pdf = Mock()
            mock_pdf.pages.__iter__ = Mock(return_value=iter([mock_page1, mock_page2]))
            mock_pdf.__enter__ = Mock(return_value=mock_pdf)
            mock_pdf.__exit__ = Mock(return_value=False)

            mock_pdfplumber.open.return_value = mock_pdf

            result = await pdf_parser.extract_text(sample_pdf_bytes)

            # strip() remove espaços em branco no final, mas mantém separação entre páginas
            assert result == "Page 1 content\n\nPage 2 content"


class TestPDFParserExtractMetadata:
    """Testes para método extract_metadata."""

    @pytest.mark.asyncio
    async def test_extract_metadata_valid_pdf(self, pdf_parser, sample_pdf_bytes):
        """Testa extração de metadados de PDF válido."""
        with patch("src.services.parsers.pdf_parser.PyPDF2Reader") as mock_reader_class:
            # Mock reader
            mock_reader = Mock()
            mock_reader.pages = [Mock(), Mock()]  # 2 páginas
            mock_reader.is_encrypted = False

            # Mock metadata
            mock_info = {
                "/Title": "Test Document",
                "/Author": "Test Author",
                "/Subject": "Test Subject",
                "/Creator": "Test Creator",
                "/Producer": "Test Producer",
                "/CreationDate": "D:20260416120000Z",
            }
            mock_reader.metadata = mock_info

            # Mock header
            mock_header = Mock()
            mock_header.version = 4
            mock_reader.pdf_header = mock_header

            mock_reader_class.return_value = mock_reader

            result = await pdf_parser.extract_metadata(sample_pdf_bytes)

            assert result["page_count"] == 2
            assert result["title"] == "Test Document"
            assert result["author"] == "Test Author"
            assert result["subject"] == "Test Subject"
            assert result["creator"] == "Test Creator"
            assert result["producer"] == "Test Producer"
            assert result["creation_date"] == "D:20260416120000Z"
            assert result["encrypted"] is False
            assert result["pdf_version"] == "1.4"

    @pytest.mark.asyncio
    async def test_extract_metadata_invalid_pdf(self, pdf_parser, invalid_pdf_bytes):
        """Testa extração de metadados de PDF inválido."""
        result = await pdf_parser.extract_metadata(invalid_pdf_bytes)
        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_metadata_encrypted_pdf(
        self, pdf_parser, encrypted_pdf_bytes
    ):
        """Testa metadados de PDF criptografado."""
        with patch("src.services.parsers.pdf_parser.PyPDF2Reader") as mock_reader_class:
            mock_reader = Mock()
            mock_reader.pages = []
            mock_reader.is_encrypted = True
            mock_reader.metadata = None
            mock_reader_class.return_value = mock_reader

            result = await pdf_parser.extract_metadata(encrypted_pdf_bytes)

            assert result["encrypted"] is True
            assert result["page_count"] == 0

    @pytest.mark.asyncio
    async def test_extract_metadata_no_metadata_dict(self, pdf_parser, sample_pdf_bytes):
        """Testa PDF sem dicionário de metadados."""
        with patch("src.services.parsers.pdf_parser.PyPDF2Reader") as mock_reader_class:
            mock_reader = Mock()
            mock_reader.pages = [Mock()]
            mock_reader.is_encrypted = False
            mock_reader.metadata = None
            mock_reader_class.return_value = mock_reader

            result = await pdf_parser.extract_metadata(sample_pdf_bytes)

            assert result["page_count"] == 1
            assert result["encrypted"] is False
            assert "title" not in result

    @pytest.mark.asyncio
    async def test_extract_metadata_extraction_error(
        self, pdf_parser, sample_pdf_bytes
    ):
        """Testa tratamento de erro na extração de metadados."""
        with patch("src.services.parsers.pdf_parser.PyPDF2Reader") as mock_reader_class:
            mock_reader_class.side_effect = Exception("Read error")

            result = await pdf_parser.extract_metadata(sample_pdf_bytes)

            assert result == {}
