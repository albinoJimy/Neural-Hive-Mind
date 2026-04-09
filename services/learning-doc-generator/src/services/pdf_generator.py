"""Gerador de PDF a partir de Markdown"""

import os
from datetime import datetime, timezone
from pathlib import Path

import structlog
from jinja2 import BaseLoader, Environment
from src.config import get_settings
from src.models import DocumentFormat, DocumentType, LearningDocument

logger = structlog.get_logger()


class PDFGenerator:
    """Gera PDFs a partir de Markdown e templates customizados"""

    def __init__(self):
        """Inicializa o gerador de PDF"""
        self.settings = get_settings()
        self._output_dir = self.settings.docs_output_dir
        self._template_dir = self.settings.docs_template_dir

        # Criar diretórios
        os.makedirs(self._output_dir, exist_ok=True)
        os.makedirs(self._template_dir, exist_ok=True)

        # Verificar se weasyprint está disponível
        self._weasyprint_available = self._check_weasyprint()

        # Cache de templates HTML
        self._html_templates: dict[str, str] = {}

    def _check_weasyprint(self) -> bool:
        """Verifica se weasyprint está instalado"""
        try:
            import weasyprint  # noqa: F401
            logger.info("WeasyPrint disponível para geração de PDF")
            return True
        except ImportError:
            logger.warning(
                "WeasyPrint não disponível. PDF generation será limitada.",
                hint="Instale com: pip install weasyprint",
            )
            return False

    async def generate_pdf(
        self,
        document: LearningDocument,
        markdown_content: str | None = None,
        template_name: str | None = None,
    ) -> str:
        """Gera PDF a partir de um documento

        Args:
            document: Dados do documento
            markdown_content: Conteúdo Markdown (se None, usa document.markdown_content)
            template_name: Nome do template HTML customizado

        Returns:
            Caminho do arquivo PDF gerado

        Raises:
            RuntimeError: Se weasyprint não estiver disponível
            ValueError: Se não há conteúdo para converter
        """
        if not self._weasyprint_available:
            raise RuntimeError(
                "WeasyPrint não está disponível. "
                "Instale com: pip install weasyprint ou habilite a extras opcional."
            )

        md_content = markdown_content or document.markdown_content
        if not md_content:
            raise ValueError("Conteúdo Markdown não disponível")

        try:
            # Converter Markdown para HTML
            html_content = await self._markdown_to_html(
                md_content, document, template_name
            )

            # Gerar PDF
            pdf_path = await self._html_to_pdf(html_content, document)

            logger.info(
                "PDF gerado com sucesso",
                doc_id=document.id,
                path=pdf_path,
                size=Path(pdf_path).stat().st_size,
            )
            return pdf_path

        except Exception:
            logger.exception("Erro ao gerar PDF", doc_id=document.id)
            raise

    async def _markdown_to_html(
        self,
        markdown_content: str,
        document: LearningDocument,
        template_name: str | None = None,
    ) -> str:
        """Converte Markdown para HTML

        Args:
            markdown_content: Conteúdo Markdown
            document: Dados do documento
            template_name: Nome do template customizado

        Returns:
            HTML completo
        """
        try:
            import markdown
        except ImportError as exc:
            raise RuntimeError("Markdown library não disponível") from exc

        # Converter Markdown para HTML
        md = markdown.Markdown(
            extensions=[
                "tables",
                "fenced_code",
                "codehilite",
                "toc",
                "nl2br",
                "sane_lists",
                "extra",
            ]
        )
        body_html = md.convert(markdown_content)

        # Obter template HTML
        template_path = Path(self._template_dir) / template_name if template_name else None
        if template_name and template_path.exists():
            template_string = template_path.read_text()
        else:
            template_string = self._get_default_template(document.type)

        # Renderizar template
        env = Environment(loader=BaseLoader())
        template = env.from_string(template_string)

        return template.render(
            title=document.title,
            content=body_html,
            generated_at=document.generated_at or datetime.now(timezone.utc),
            period_start=document.period_start,
            period_end=document.period_end,
            document_type=document.type.value,
            metadata=document.metadata,
        )

    async def _html_to_pdf(self, html_content: str, document: LearningDocument) -> str:
        """Converte HTML para PDF usando WeasyPrint

        Args:
            html_content: Conteúdo HTML
            document: Dados do documento

        Returns:
            Caminho do arquivo PDF
        """
        from weasyprint import CSS, HTML

        # Criar nome de arquivo
        safe_title = document.title.lower().replace(" ", "_").replace("/", "_")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_title}.pdf"
        filepath = Path(self._output_dir) / filename

        # CSS base para estilização
        base_css = self._get_base_css()

        # Gerar PDF
        HTML(string=html_content).write_pdf(
            str(filepath),
            stylesheets=[CSS(string=base_css)],
        )

        return str(filepath)

    def _get_base_css(self) -> str:
        """Retorna CSS base para o PDF"""
        return """
        @page {
            size: A4;
            margin: 2cm;
            @bottom-right {
                content: "Página " counter(page) " de " counter(pages);
                font-size: 9pt;
                color: #666;
            }
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            font-size: 11pt;
        }

        h1 {
            color: #1a1a1a;
            border-bottom: 2px solid #0066cc;
            padding-bottom: 0.3em;
            margin-top: 0;
            page-break-after: avoid;
        }

        h2 {
            color: #333;
            border-bottom: 1px solid #ddd;
            padding-bottom: 0.2em;
            margin-top: 1.5em;
            page-break-after: avoid;
        }

        h3 {
            color: #555;
            margin-top: 1.2em;
            page-break-after: avoid;
        }

        h4, h5, h6 {
            color: #666;
            page-break-after: avoid;
        }

        table {
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
            page-break-inside: avoid;
        }

        th, td {
            border: 1px solid #ddd;
            padding: 8px 12px;
            text-align: left;
        }

        th {
            background-color: #f5f5f5;
            font-weight: 600;
        }

        tr:nth-child(even) {
            background-color: #f9f9f9;
        }

        pre {
            background-color: #f5f5f5;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 1em;
            overflow-x: auto;
            page-break-inside: avoid;
        }

        code {
            font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
            font-size: 0.9em;
            background-color: #f5f5f5;
            padding: 2px 4px;
            border-radius: 3px;
        }

        pre code {
            background-color: transparent;
            padding: 0;
        }

        blockquote {
            border-left: 4px solid #0066cc;
            margin: 1em 0;
            padding-left: 1em;
            color: #555;
            page-break-inside: avoid;
        }

        ul, ol {
            margin: 1em 0;
        }

        li {
            margin: 0.5em 0;
        }

        a {
            color: #0066cc;
            text-decoration: none;
        }

        a:hover {
            text-decoration: underline;
        }

        img {
            max-width: 100%;
            height: auto;
            page-break-inside: avoid;
        }

        .metadata {
            background-color: #f9f9f9;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 1em;
            margin: 1em 0;
            font-size: 0.9em;
        }

        .metadata strong {
            color: #555;
        }

        .summary {
            background-color: #e6f3ff;
            border-left: 4px solid #0066cc;
            padding: 1em;
            margin: 1em 0;
            page-break-inside: avoid;
        }

        .insight {
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 1em;
            margin: 1em 0;
            page-break-inside: avoid;
        }

        .insight.high {
            border-left: 4px solid #dc3545;
        }

        .insight.medium {
            border-left: 4px solid #ffc107;
        }

        .insight.low {
            border-left: 4px solid #28a745;
        }

        .recommendation {
            background-color: #f0f8f0;
            border-left: 4px solid #28a745;
            padding: 0.8em;
            margin: 0.5em 0;
        }

        .page-break {
            page-break-before: always;
        }

        .no-break {
            page-break-inside: avoid;
        }
        """

    def _get_default_template(self, doc_type: DocumentType) -> str:
        """Retorna template HTML padrão para cada tipo de documento

        Nota: doc_type é mantido para compatibilidade futura,
        mas atualmente o mesmo template é usado para todos os tipos.
        """
        return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            font-size: 11pt;
            margin: 0;
            padding: 0;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2cm;
            margin-bottom: 2cm;
        }
        .header h1 {
            margin: 0;
            color: white;
            border: none;
        }
        .header .meta {
            margin-top: 1em;
            font-size: 0.9em;
            opacity: 0.9;
        }
        .content {
            padding: 0 2cm 2cm 2cm;
        }
        .footer {
            margin-top: 2cm;
            padding-top: 1cm;
            border-top: 1px solid #ddd;
            text-align: center;
            font-size: 0.8em;
            color: #666;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px 12px;
            text-align: left;
        }
        th {
            background-color: #f5f5f5;
        }
        pre {
            background-color: #f5f5f5;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 1em;
            overflow-x: auto;
        }
        code {
            font-family: "Monaco", "Menlo", monospace;
            font-size: 0.9em;
            background-color: #f5f5f5;
            padding: 2px 4px;
            border-radius: 3px;
        }
        blockquote {
            border-left: 4px solid #667eea;
            margin: 1em 0;
            padding-left: 1em;
            color: #555;
        }
        img {
            max-width: 100%;
            height: auto;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ title }}</h1>
        <div class="meta">
            <strong>Gerado em:</strong> {{ generated_at.strftime('%Y-%m-%d %H:%M:%S') }} UTC<br>
            {% if period_start and period_end %}
            <strong>Período:</strong> {{ period_start.strftime('%Y-%m-%d') }} a {{ period_end.strftime('%Y-%m-%d') }}<br>
            {% endif %}
            <strong>Tipo:</strong> {{ document_type.replace('_', ' ').title() }}
        </div>
    </div>
    <div class="content">
        {{ content|safe }}
    </div>
    <div class="footer">
        Gerado por Neural Hive-Mind Learning Documentation Generator v1.0.0<br>
        {{ generated_at.strftime('%Y-%m-%d %H:%M:%S') }} UTC
    </div>
</body>
</html>
"""

    async def generate_from_markdown_file(
        self, markdown_path: str, output_path: str | None = None
    ) -> str:
        """Gera PDF a partir de um arquivo Markdown

        Args:
            markdown_path: Caminho do arquivo Markdown
            output_path: Caminho de saída do PDF (opcional)

        Returns:
            Caminho do arquivo PDF gerado
        """
        md_path = Path(markdown_path)
        if not md_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {markdown_path}")

        markdown_content = md_path.read_text(encoding="utf-8")

        # Criar documento básico
        document = LearningDocument(
            title=md_path.stem,
            type=DocumentType.EXPERIMENT_REPORT,
        )

        # Gerar PDF
        pdf_path = await self.generate_pdf(document, markdown_content)

        # Se caminho de saída especificado, mover arquivo
        if output_path and output_path != pdf_path:
            import shutil
            shutil.move(pdf_path, output_path)
            pdf_path = output_path

        return pdf_path

    async def generate_batch(
        self, documents: list[tuple[LearningDocument, str]]
    ) -> list[str]:
        """Gera PDFs em lote

        Args:
            documents: Lista de tuplas (documento, conteúdo_markdown)

        Returns:
            Lista de caminhos dos PDFs gerados
        """
        pdf_paths = []
        for document, markdown_content in documents:
            try:
                pdf_path = await self.generate_pdf(document, markdown_content)
                pdf_paths.append(pdf_path)
            except Exception:
                logger.exception(
                    "Erro ao gerar PDF em lote",
                    doc_id=document.id,
                )
                pdf_paths.append(None)

        return pdf_paths

    def is_available(self) -> bool:
        """Verifica se a geração de PDF está disponível"""
        return self._weasyprint_available

    def get_supported_formats(self) -> list[str]:
        """Retorna formatos suportados"""
        formats = [DocumentFormat.MARKDOWN.value]
        if self._weasyprint_available:
            formats.append(DocumentFormat.PDF.value)
        return formats

    async def close(self) -> None:
        """Fecha recursos"""
        self._html_templates.clear()
