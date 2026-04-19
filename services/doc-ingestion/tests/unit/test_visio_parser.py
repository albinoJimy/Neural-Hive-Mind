"""Testes unitários para VisioParser."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.parsers.visio_parser import VisioParser


@pytest.fixture
def visio_parser():
    """Fixture para VisioParser."""
    return VisioParser()


@pytest.fixture
def sample_vsdx_bytes():
    """Fixture para bytes VSDX válidos (assinatura ZIP)."""
    # VSDX é ZIP - magic number: PK
    return b"PK\x03\x04\nFake VSDX content"


@pytest.fixture
def invalid_vsdx_bytes():
    """Fixture para bytes inválidos."""
    return b"This is not a VSDX file"


class TestVisioParserValidate:
    """Testes para método validate."""

    def test_validate_valid_vsdx(self, visio_parser, sample_vsdx_bytes):
        """Testa validação de VSDX válido."""
        # Mock ZipFile para ter conteúdo visio
        with patch("zipfile.ZipFile") as mock_zipfile:
            mock_zip = MagicMock()
            mock_zip.namelist.return_value = ["visio/pages/page1.xml"]
            mock_zipfile.return_value.__enter__.return_value = mock_zip

            assert visio_parser.validate(sample_vsdx_bytes) is True

    def test_validate_invalid_format(self, visio_parser, invalid_vsdx_bytes):
        """Testa validação de formato inválido."""
        assert visio_parser.validate(invalid_vsdx_bytes) is False

    def test_validate_empty_bytes(self, visio_parser):
        """Testa validação de bytes vazios."""
        assert visio_parser.validate(b"") is False

    def test_validate_short_bytes(self, visio_parser):
        """Testa validação de bytes insuficientes."""
        assert visio_parser.validate(b"P") is False

    def test_validate_no_visio_content(self, visio_parser, sample_vsdx_bytes):
        """Testa validação quando ZIP não tem conteúdo visio."""
        with patch("zipfile.ZipFile") as mock_zipfile:
            mock_zip = MagicMock()
            mock_zip.namelist.return_value = ["some/other/file.xml"]  # sem visio
            mock_zipfile.return_value.__enter__.return_value = mock_zip

            assert visio_parser.validate(sample_vsdx_bytes) is False


class TestVisioParserExtractText:
    """Testes para método extract_text."""

    @pytest.mark.asyncio
    async def test_extract_text_invalid_bytes(self, visio_parser, invalid_vsdx_bytes):
        """Testa extração de texto de bytes inválidos."""
        result = await visio_parser.extract_text(invalid_vsdx_bytes)
        assert result == ""

    @pytest.mark.asyncio
    async def test_extract_text_empty_bytes(self, visio_parser):
        """Testa extração de texto de bytes vazios."""
        result = await visio_parser.extract_text(b"")
        assert result == ""

    @pytest.mark.asyncio
    async def test_extract_text_with_visio_pages(self, visio_parser, sample_vsdx_bytes):
        """Testa extração de texto de páginas VSDX."""
        with patch("zipfile.ZipFile") as mock_zipfile:
            # Mock ZIP file
            mock_zip = MagicMock()
            mock_zip.namelist.return_value = ["visio/pages/page1.xml"]
            # XML com namespace correto do Visio
            xml_content = """<?xml version="1.0"?>
            <root xmlns:v="http://schemas.microsoft.com/office/visio/2012/main">
                <v:Text>
                    <v:cp>Shape text</v:cp>
                </v:Text>
            </root>"""
            mock_zip.read.return_value = xml_content.encode()
            mock_zipfile.return_value.__enter__.return_value = mock_zip

            result = await visio_parser.extract_text(sample_vsdx_bytes)

            assert result == "Shape text"

    @pytest.mark.asyncio
    async def test_extract_text_multiple_pages(self, visio_parser, sample_vsdx_bytes):
        """Testa extração de texto de múltiplas páginas."""
        with patch("zipfile.ZipFile") as mock_zipfile:
            # Mock ZIP file com 2 páginas
            mock_zip = MagicMock()

            def read_func(name):
                ns = 'xmlns:v="http://schemas.microsoft.com/office/visio/2012/main"'
                if "page1" in name:
                    return f'<?xml version="1.0"?><root {ns}><v:Text><v:cp>Page 1</v:cp></v:Text></root>'.encode()
                else:
                    return f'<?xml version="1.0"?><root {ns}><v:Text><v:cp>Page 2</v:cp></v:Text></root>'.encode()

            mock_zip.namelist.return_value = ["visio/pages/page1.xml", "visio/pages/page2.xml"]
            mock_zip.read.side_effect = read_func
            mock_zipfile.return_value.__enter__.return_value = mock_zip

            result = await visio_parser.extract_text(sample_vsdx_bytes)

            assert result == "Page 1\n\nPage 2"

    @pytest.mark.asyncio
    async def test_extract_text_zipfile_error(self, visio_parser, sample_vsdx_bytes):
        """Testa tratamento de erro do ZipFile."""
        with patch("zipfile.ZipFile") as mock_zipfile:
            mock_zipfile.side_effect = Exception("ZIP error")

            result = await visio_parser.extract_text(sample_vsdx_bytes)

            assert result == ""

    @pytest.mark.asyncio
    async def test_extract_text_empty_text_elements(self, visio_parser, sample_vsdx_bytes):
        """Testa que elementos de texto vazios são ignorados."""
        with patch("zipfile.ZipFile") as mock_zipfile:
            mock_zip = MagicMock()
            mock_zip.namelist.return_value = ["visio/pages/page1.xml"]
            # XML com elementos vazios
            ns = 'xmlns:v="http://schemas.microsoft.com/office/visio/2012/main"'
            xml_content = f'<?xml version="1.0"?><root {ns}><v:Text><v:cp>  </v:cp></v:Text></root>'
            mock_zip.read.return_value = xml_content.encode()
            mock_zipfile.return_value.__enter__.return_value = mock_zip

            result = await visio_parser.extract_text(sample_vsdx_bytes)

            # Texto vazio após strip deve retornar string vazia
            assert result == ""


class TestVisioParserExtractShapes:
    """Testes para método extract_shapes."""

    @pytest.mark.asyncio
    async def test_extract_shapes_invalid_bytes(self, visio_parser, invalid_vsdx_bytes):
        """Testa extração de shapes de bytes inválidos."""
        result = await visio_parser.extract_shapes(invalid_vsdx_bytes)
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_shapes_with_shapes(self, visio_parser, sample_vsdx_bytes):
        """Testa extração de shapes VSDX."""
        with patch("zipfile.ZipFile") as mock_zipfile:
            mock_zip = MagicMock()
            mock_zip.namelist.return_value = ["visio/pages/page1.xml"]
            # XML com shape e namespace correto
            xml_with_shape = """<?xml version="1.0"?>
            <root xmlns:v="http://schemas.microsoft.com/office/visio/2012/main">
                <v:Shape ID="1">
                    <v:Cell N="Name"><v:Value V="TestShape" /></v:Cell>
                    <v:Text><v:cp>Shape text</v:cp></v:Text>
                </v:Shape>
            </root>"""
            mock_zip.read.return_value = xml_with_shape.encode()
            mock_zipfile.return_value.__enter__.return_value = mock_zip

            result = await visio_parser.extract_shapes(sample_vsdx_bytes)

            assert len(result) == 1
            assert result[0]["id"] == "1"
            assert result[0]["text"] == "Shape text"

    @pytest.mark.asyncio
    async def test_extract_shapes_empty(self, visio_parser, sample_vsdx_bytes):
        """Testa extração quando não há shapes."""
        with patch("zipfile.ZipFile") as mock_zipfile:
            mock_zip = MagicMock()
            mock_zip.namelist.return_value = ["visio/pages/page1.xml"]
            mock_zip.read.return_value = b"<xml></xml>"
            mock_zipfile.return_value.__enter__.return_value = mock_zip

            result = await visio_parser.extract_shapes(sample_vsdx_bytes)

            assert result == []


class TestVisioParserExtractMetadata:
    """Testes para método extract_metadata."""

    @pytest.mark.asyncio
    async def test_extract_metadata_invalid_bytes(self, visio_parser, invalid_vsdx_bytes):
        """Testa extração de metadados de bytes inválidos."""
        result = await visio_parser.extract_metadata(invalid_vsdx_bytes)
        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_metadata_with_shapes(self, visio_parser, sample_vsdx_bytes):
        """Testa extração de metadados básicos."""
        with patch("zipfile.ZipFile") as mock_zipfile:
            mock_zip = MagicMock()
            mock_zip.namelist.return_value = ["visio/pages/page1.xml"]
            mock_zip.read.return_value = b"<xml></xml>"
            mock_zipfile.return_value.__enter__.return_value = mock_zip

            # Mock _extract_shapes_sync (chamado internamente por _extract_metadata_sync)
            with patch.object(visio_parser, "_extract_shapes_sync", return_value=[{"id": "1"}]):
                result = await visio_parser.extract_metadata(sample_vsdx_bytes)

                assert result["page_count"] == 1
                assert result["shape_count"] == 1

    @pytest.mark.asyncio
    async def test_extract_metadata_with_app_xml(self, visio_parser, sample_vsdx_bytes):
        """Testa extração de metadados do aplicativo."""
        with patch("zipfile.ZipFile") as mock_zipfile:
            mock_zip = MagicMock()
            mock_zip.namelist.return_value = ["visio/pages/page1.xml", "docProps/app.xml"]

            def read_func(name):
                if "app.xml" in name:
                    return b"<Properties><Application>Visio</Application><Scale>1.0</Scale></Properties>"
                return b"<xml></xml>"

            mock_zip.read.side_effect = read_func
            mock_zipfile.return_value.__enter__.return_value = mock_zip

            with patch.object(visio_parser, "_extract_shapes_sync", return_value=[]):
                result = await visio_parser.extract_metadata(sample_vsdx_bytes)

                assert result["application"] == "Visio"
                assert result["scale"] == "1.0"

    @pytest.mark.asyncio
    async def test_extract_metadata_with_core_xml(self, visio_parser, sample_vsdx_bytes):
        """Testa extração de metadados core (Dublin Core)."""
        with patch("zipfile.ZipFile") as mock_zipfile:
            mock_zip = MagicMock()
            mock_zip.namelist.return_value = ["visio/pages/page1.xml", "docProps/core.xml"]

            def read_func(name):
                if "core.xml" in name:
                    return b'<cp:coreProperties xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:cp="ns"><dc:title>Test Doc</dc:title><dc:creator>Test Author</dc:creator></cp:coreProperties>'
                return b"<xml></xml>"

            mock_zip.read.side_effect = read_func
            mock_zipfile.return_value.__enter__.return_value = mock_zip

            with patch.object(visio_parser, "_extract_shapes_sync", return_value=[]):
                result = await visio_parser.extract_metadata(sample_vsdx_bytes)

                assert result["title"] == "Test Doc"
                assert result["author"] == "Test Author"

    @pytest.mark.asyncio
    async def test_extract_metadata_extraction_error(self, visio_parser, sample_vsdx_bytes):
        """Testa tratamento de erro na extração de metadados."""
        with patch("zipfile.ZipFile") as mock_zipfile:
            mock_zipfile.side_effect = Exception("Read error")

            result = await visio_parser.extract_metadata(sample_vsdx_bytes)

            assert result == {}
