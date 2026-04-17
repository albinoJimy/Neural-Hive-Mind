"""Parser para documentos PDF usando pdfplumber e PyPDF2."""

import io
from typing import Any

import pdfplumber
from PyPDF2 import PdfReader as PyPDF2Reader
from structlog import get_logger

logger = get_logger(__name__)


class PDFParser:
    """Parser para extrair texto e metadados de arquivos PDF."""

    def __init__(self) -> None:
        """Inicializa o parser PDF."""
        self._use_pdfplumber = True  # Primary parser
        self._fallback_parser = "pypdf2"

    async def extract_text(self, file_content: bytes) -> str:
        """
        Extrai texto de todas as páginas do PDF.

        Args:
            file_content: Conteúdo binário do arquivo PDF.

        Returns:
            Texto extraído de todas as páginas concatenado.
            Retorna string vazia em caso de erro.
        """
        if not self._validate_pdf_bytes(file_content):
            logger.warning("pdf_invalid_bytes", size=len(file_content))
            return ""

        extracted_text = ""

        # Tenta pdfplumber primeiro (melhor extração de texto)
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    try:
                        page_text = page.extract_text() or ""
                        extracted_text += page_text + "\n\n"
                    except Exception as e:
                        logger.error(
                            "pdf_page_extract_failed",
                            page=page_num,
                            error=str(e),
                        )
                        continue

            if extracted_text.strip():
                logger.info(
                    "pdf_text_extracted",
                    parser="pdfplumber",
                    char_count=len(extracted_text),
                )
                return extracted_text.strip()

        except Exception as e:
            logger.warning(
                "pdfplumber_extraction_failed",
                error=str(e),
                fallback="pypdf2",
            )

        # Fallback para PyPDF2
        return await self._extract_text_pypdf2(file_content)

    async def _extract_text_pypdf2(self, file_content: bytes) -> str:
        """
        Extrai texto usando PyPDF2 como fallback.

        Args:
            file_content: Conteúdo binário do arquivo PDF.

        Returns:
            Texto extraído ou string vazia.
        """
        try:
            pdf_reader = PyPDF2Reader(io.BytesIO(file_content))
            extracted_text = ""

            for page in pdf_reader.pages:
                try:
                    page_text = page.extract_text() or ""
                    extracted_text += page_text + "\n\n"
                except Exception as e:
                    logger.error("pypdf2_page_extract_failed", error=str(e))
                    continue

            logger.info(
                "pdf_text_extracted",
                parser="pypdf2",
                char_count=len(extracted_text),
            )
            return extracted_text.strip()

        except Exception as e:
            logger.error("pypdf2_extraction_failed", error=str(e))
            return ""

    async def extract_metadata(self, file_content: bytes) -> dict[str, Any]:
        """
        Extrai metadados do PDF.

        Args:
            file_content: Conteúdo binário do arquivo PDF.

        Returns:
            Dicionário com metadados: page_count, title, author, encrypted, etc.
        """
        if not self._validate_pdf_bytes(file_content):
            return {}

        metadata: dict[str, Any] = {}

        try:
            pdf_reader = PyPDF2Reader(io.BytesIO(file_content))

            # Contagem de páginas
            metadata["page_count"] = len(pdf_reader.pages)

            # Metadados do documento
            pdf_info = pdf_reader.metadata
            if pdf_info:
                metadata["title"] = pdf_info.get("/Title", "").strip()
                metadata["author"] = pdf_info.get("/Author", "").strip()
                metadata["subject"] = pdf_info.get("/Subject", "").strip()
                metadata["creator"] = pdf_info.get("/Creator", "").strip()
                metadata["producer"] = pdf_info.get("/Producer", "").strip()
                metadata["creation_date"] = pdf_info.get("/CreationDate", "")

            # Status de criptografia
            metadata["encrypted"] = pdf_reader.is_encrypted

            # PDF version
            if hasattr(pdf_reader, "pdf_header"):
                header = pdf_reader.pdf_header
                if header and hasattr(header, "version"):
                    metadata["pdf_version"] = f"1.{header.version}"

            logger.info("pdf_metadata_extracted", page_count=metadata.get("page_count"))

        except Exception as e:
            logger.error("pdf_metadata_extraction_failed", error=str(e))
            return {}

        return metadata

    def validate(self, file_content: bytes) -> bool:
        """
        Valida se o conteúdo é um PDF válido.

        Args:
            file_content: Conteúdo binário do arquivo.

        Returns:
            True se for um PDF válido, False caso contrário.
        """
        return self._validate_pdf_bytes(file_content)

    def _validate_pdf_bytes(self, file_content: bytes) -> bool:
        """
        Valida bytes como PDF verificando o header mágico.

        Args:
            file_content: Conteúdo binário a validar.

        Returns:
            True se tiver header PDF válido.
        """
        if not file_content or len(file_content) < 5:
            return False

        # PDF magic number: %PDF-
        return file_content[:5] == b"%PDF-"
