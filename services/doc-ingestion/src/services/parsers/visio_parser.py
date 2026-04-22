"""Parser para documentos Visio (VSDX) usando lxml e ZIP."""

import asyncio
import io
import zipfile
from typing import Any

from lxml import etree
from structlog import get_logger

logger = get_logger(__name__)

# Namespace XML do Visio VSDX
VISIO_NS = {
    "v": "http://schemas.microsoft.com/office/visio/2012/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


class VisioParser:
    """Parser para extrair texto e shapes de arquivos Visio (VSDX).

    Nota: Apenas VSDX (baseado em ZIP/XML) é suportado.
    VSD (binário legado) não é suportado diretamente.
    """

    def __init__(self) -> None:
        """Inicializa o parser Visio."""

    async def extract_text(self, file_content: bytes) -> str:
        """
        Extrai texto de todos os elementos de texto do VSDX.

        Args:
            file_content: Conteúdo binário do arquivo VSDX.

        Returns:
            Texto extraído concatenado de todos os elementos.
            Retorna string vazia em caso de erro ou formato VSD binário.
        """
        if not self._validate_vsdx_bytes(file_content):
            logger.warning("vsdx_invalid_bytes", size=len(file_content))
            return ""

        # Executa operação síncrona em thread pool
        return await asyncio.to_thread(self._extract_text_sync, file_content)

    def _extract_text_sync(self, file_content: bytes) -> str:
        """
        Extrai texto de forma síncrona (executada em thread pool).

        Args:
            file_content: Conteúdo binário do arquivo VSDX.

        Returns:
            Texto extraído concatenado de todos os elementos.
        """
        try:
            extracted_texts = []

            with zipfile.ZipFile(io.BytesIO(file_content)) as zip_file:
                # Procura por arquivos XML que contêm texto
                for file_name in zip_file.namelist():
                    if file_name.endswith(".xml") and "visio/pages" in file_name:
                        try:
                            xml_content = zip_file.read(file_name)
                            texts = self._parse_text_from_xml(xml_content)
                            extracted_texts.extend(texts)
                        except Exception as e:
                            logger.warning("vsdx_page_parse_failed", file=file_name, error=str(e))
                            continue

            result = "\n\n".join(extracted_texts)

            logger.info(
                "vsdx_text_extracted",
                text_count=len(extracted_texts),
                char_count=len(result),
            )

            return result

        except Exception as e:
            logger.error("vsdx_extraction_failed", error=str(e))
            return ""

    async def extract_shapes(self, file_content: bytes) -> list[dict[str, Any]]:
        """
        Extrai informações sobre shapes do VSDX.

        Args:
            file_content: Conteúdo binário do arquivo VSDX.

        Returns:
            Lista de dicionários com informações dos shapes (id, name, text).
            Retorna lista vazia em caso de erro.
        """
        if not self._validate_vsdx_bytes(file_content):
            return []

        # Executa operação síncrona em thread pool
        return await asyncio.to_thread(self._extract_shapes_sync, file_content)

    def _extract_shapes_sync(self, file_content: bytes) -> list[dict[str, Any]]:
        """
        Extrai shapes de forma síncrona (executada em thread pool).

        Args:
            file_content: Conteúdo binário do arquivo VSDX.

        Returns:
            Lista de dicionários com informações dos shapes.
        """
        shapes: list[dict[str, Any]] = []

        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as zip_file:
                for file_name in zip_file.namelist():
                    if file_name.endswith(".xml") and "visio/pages" in file_name:
                        try:
                            xml_content = zip_file.read(file_name)
                            page_shapes = self._parse_shapes_from_xml(xml_content)
                            shapes.extend(page_shapes)
                        except Exception as e:
                            logger.warning("vsdx_shapes_parse_failed", file=file_name, error=str(e))
                            continue

            logger.info("vsdx_shapes_extracted", shape_count=len(shapes))
            return shapes

        except Exception as e:
            logger.error("vsdx_shapes_extraction_failed", error=str(e))
            return []

    async def extract_metadata(self, file_content: bytes) -> dict[str, Any]:
        """
        Extrai metadados do documento Visio.

        Args:
            file_content: Conteúdo binário do arquivo VSDX.

        Returns:
            Dicionário com metadados: page_count, shape_count, etc.
        """
        if not self._validate_vsdx_bytes(file_content):
            return {}

        # Executa operação síncrona em thread pool
        return await asyncio.to_thread(self._extract_metadata_sync, file_content)

    def _extract_metadata_sync(self, file_content: bytes) -> dict[str, Any]:
        """
        Extrai metadados de forma síncrona (executada em thread pool).

        Args:
            file_content: Conteúdo binário do arquivo VSDX.

        Returns:
            Dicionário com metadados.
        """
        metadata: dict[str, Any] = {}

        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as zip_file:
                # Contar páginas
                page_files = [
                    f for f in zip_file.namelist() if "visio/pages" in f and f.endswith(".xml")
                ]
                metadata["page_count"] = len(page_files)

                # Contar shapes
                shapes = self._extract_shapes_sync(file_content)
                metadata["shape_count"] = len(shapes)

                # Extrair metadados do arquivo principal
                if "docProps/app.xml" in zip_file.namelist():
                    try:
                        app_xml = zip_file.read("docProps/app.xml")
                        app_metadata = self._parse_app_metadata(app_xml)
                        metadata.update(app_metadata)
                    except Exception:
                        pass

                if "docProps/core.xml" in zip_file.namelist():
                    try:
                        core_xml = zip_file.read("docProps/core.xml")
                        core_metadata = self._parse_core_metadata(core_xml)
                        metadata.update(core_metadata)
                    except Exception:
                        pass

                logger.info("vsdx_metadata_extracted", page_count=metadata.get("page_count"))

        except Exception as e:
            logger.error("vsdx_metadata_extraction_failed", error=str(e))
            return {}

        return metadata

    async def parse(self, file_content: bytes) -> str:
        """
        Parse principal do VSDX - extrai texto.

        Args:
            file_content: Conteúdo binário do arquivo VSDX.

        Returns:
            Texto extraído do documento.
        """
        return await self.extract_text(file_content)

    def validate(self, file_content: bytes) -> bool:
        """
        Valida se o conteúdo é um VSDX válido.

        Args:
            file_content: Conteúdo binário do arquivo.

        Returns:
            True se for um VSDX válido, False caso contrário.
        """
        return self._validate_vsdx_bytes(file_content)

    def _validate_vsdx_bytes(self, file_content: bytes) -> bool:
        """
        Valida bytes como VSDX verificando assinatura ZIP e estrutura.

        Args:
            file_content: Conteúdo binário a validar.

        Returns:
            True se tiver estrutura VSDX válida.
        """
        if not file_content or len(file_content) < 4:
            return False

        # VSDX é ZIP-based
        if file_content[:2] != b"PK":
            return False

        # Verifica se contém estrutura visio
        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as zip_file:
                # Procura por indicadores de VSDX
                has_visio_content = any("visio" in name.lower() for name in zip_file.namelist())
                return has_visio_content
        except Exception:
            return False

    def _parse_text_from_xml(self, xml_content: bytes) -> list[str]:
        """
        Faz parsing de texto de XML do Visio.

        Args:
            xml_content: Conteúdo XML como bytes.

        Returns:
            Lista de textos encontrados.
        """
        texts = []

        try:
            root = etree.fromstring(xml_content)

            # Busca por elementos de texto no namespace Visio
            for text_elem in root.xpath("//v:Text//v:cp", namespaces=VISIO_NS):
                text_content = text_elem.text
                if text_content and text_content.strip():
                    texts.append(text_content.strip())

        except Exception as e:
            logger.warning("vsdx_xml_parse_failed", error=str(e))

        return texts

    def _parse_shapes_from_xml(self, xml_content: bytes) -> list[dict[str, Any]]:
        """
        Faz parsing de shapes de XML do Visio.

        Args:
            xml_content: Conteúdo XML como bytes.

        Returns:
            Lista de dicionários com informações dos shapes.
        """
        shapes = []

        try:
            root = etree.fromstring(xml_content)

            # Busca por elementos Shape
            for shape_elem in root.xpath("//v:Shape", namespaces=VISIO_NS):
                shape_info: dict[str, Any] = {}

                # ID do shape
                shape_id = shape_elem.get("ID", "")
                if shape_id:
                    shape_info["id"] = shape_id

                # Nome do shape
                name_elem = shape_elem.xpath("./v:Cell[@N='Name']/v:Value", namespaces=VISIO_NS)
                if name_elem is not None and len(name_elem) > 0:
                    shape_info["name"] = name_elem[0].get("V", "")

                # Texto do shape
                text_elem = shape_elem.xpath(".//v:Text", namespaces=VISIO_NS)
                if text_elem:
                    text_parts = []
                    for cp in text_elem[0].xpath(".//v:cp", namespaces=VISIO_NS):
                        if cp.text:
                            text_parts.append(cp.text)
                    if text_parts:
                        shape_info["text"] = "".join(text_parts)

                # Tipo do shape
                type_elem = shape_elem.xpath(
                    "./v:Cell[@N='ShapeType']/v:Value", namespaces=VISIO_NS
                )
                if type_elem is not None and len(type_elem) > 0:
                    shape_info["type"] = type_elem[0].get("V", "")

                if shape_info:
                    shapes.append(shape_info)

        except Exception as e:
            logger.warning("vsdx_shapes_xml_parse_failed", error=str(e))

        return shapes

    def _parse_app_metadata(self, xml_content: bytes) -> dict[str, Any]:
        """
        Faz parsing de metadados de aplicativo do Visio.

        Args:
            xml_content: Conteúdo XML como bytes.

        Returns:
            Dicionário com metadados do aplicativo.
        """
        metadata: dict[str, Any] = {}

        try:
            root = etree.fromstring(xml_content)

            # Application
            app_elem = root.find("{*}Application")
            if app_elem is not None and app_elem.text:
                metadata["application"] = app_elem.text

            # Scale
            scale_elem = root.find("{*}Scale")
            if scale_elem is not None and scale_elem.text:
                metadata["scale"] = scale_elem.text

        except Exception as e:
            logger.warning("vsdx_app_metadata_parse_failed", error=str(e))

        return metadata

    def _parse_core_metadata(self, xml_content: bytes) -> dict[str, Any]:
        """
        Faz parsing de metadados core do Visio (Dublin Core).

        Args:
            xml_content: Conteúdo XML como bytes.

        Returns:
            Dicionário com metadados core.
        """
        metadata: dict[str, Any] = {}

        try:
            root = etree.fromstring(xml_content)

            # Namespace Dublin Core
            ns = {"dc": "http://purl.org/dc/elements/1.1/", "dcterms": "http://purl.org/dc/terms/"}

            # Title
            title_elem = root.find("{*}title", ns)
            if title_elem is not None and title_elem.text:
                metadata["title"] = title_elem.text

            # Creator
            creator_elem = root.find("{*}creator", ns)
            if creator_elem is not None and creator_elem.text:
                metadata["author"] = creator_elem.text

            # Description
            desc_elem = root.find("{*}description", ns)
            if desc_elem is not None and desc_elem.text:
                metadata["description"] = desc_elem.text

        except Exception as e:
            logger.warning("vsdx_core_metadata_parse_failed", error=str(e))

        return metadata
