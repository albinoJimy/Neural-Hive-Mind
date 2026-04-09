"""Testes unitários para PDFGenerator"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    DocumentFormat,
    DocumentStatus,
    DocumentType,
    Insight,
    InsightConfidence,
    LearningDocument,
)
from src.services.pdf_generator import PDFGenerator


@pytest.fixture
def pdf_generator(tmp_path, monkeypatch):
    """Fixture para PDFGenerator"""
    # Create directories explicitly for the generator
    output_dir = tmp_path / "pdf_output"
    template_dir = tmp_path / "pdf_templates"
    output_dir.mkdir(exist_ok=True)
    template_dir.mkdir(exist_ok=True)

    # Set environment variables before creating generator
    monkeypatch.setenv("DOCS_OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("DOCS_TEMPLATE_DIR", str(template_dir))

    # Reset settings to pick up new env vars
    import src.config.settings
    src.config.settings._settings_instance = None

    gen = PDFGenerator()
    return gen


@pytest.fixture
def sample_document():
    """Fixture para documento de exemplo"""
    return LearningDocument(
        id="test-doc-123",
        title="Relatório de Teste",
        type=DocumentType.EXPERIMENT_REPORT,
        status=DocumentStatus.COMPLETED,
        summary="Resumo executivo de teste",
        period_start=datetime(2026, 1, 1),
        period_end=datetime(2026, 1, 31),
        markdown_content="""# Relatório de Teste

## Resumo Executivo

Este é um relatório de teste.

## Insights

1. **Insight 1:** Descrição do insight
2. **Insight 2:** Outra descrição

## Tabela de Exemplo

| Coluna 1 | Coluna 2 |
|----------|----------|
| Valor 1  | Valor 2  |

## Código de Exemplo

```python
def hello():
    print("Hello, World!")
```
""",
    )


@pytest.fixture
def sample_insights():
    """Fixture para insights de exemplo"""
    return [
        Insight(
            title="Melhoria de Accuracy",
            description="O modelo melhorou em 5%",
            evidence={"accuracy_before": 0.85, "accuracy_after": 0.90},
            confidence=InsightConfidence.HIGH,
            experiment_ids=["exp-1", "exp-2"],
            category="improvement",
        ),
        Insight(
            title="Aumento de Latência",
            description="Latência aumentou em 10ms",
            evidence={"latency_before": 100, "latency_after": 110},
            confidence=InsightConfidence.MEDIUM,
            experiment_ids=["exp-1"],
            category="regression",
        ),
    ]


class TestPDFGeneratorInit:
    """Testes de inicialização do PDFGenerator"""

    def test_check_weasyprint_availability(self, pdf_generator):
        """Testa verificação de disponibilidade do WeasyPrint"""
        is_available = pdf_generator.is_available()
        assert isinstance(is_available, bool)

    def test_get_supported_formats(self, pdf_generator):
        """Testa obtenção de formatos suportados"""
        formats = pdf_generator.get_supported_formats()
        assert DocumentFormat.MARKDOWN.value in formats
        assert isinstance(formats, list)


class TestMarkdownToHTML:
    """Testes de conversão de Markdown para HTML"""

    @pytest.mark.asyncio
    async def test_markdown_to_html_basic(self, pdf_generator, sample_document):
        """Testa conversão básica de Markdown para HTML"""
        html = await pdf_generator._markdown_to_html(
            sample_document.markdown_content,
            sample_document,
            None,
        )

        assert ("<!DOCTYPE html>" in html or "<html" in html.lower())
        assert "<body>" in html
        assert sample_document.title in html
        assert "Resumo Executivo" in html

    @pytest.mark.asyncio
    async def test_markdown_to_html_with_tables(self, pdf_generator, sample_document):
        """Testa conversão de tabelas Markdown para HTML"""
        markdown = "| Col1 | Col2 |\n|------|------|\n| A | B |"
        html = await pdf_generator._markdown_to_html(
            markdown,
            sample_document,
            None,
        )

        assert "<table>" in html or "<td>" in html

    @pytest.mark.asyncio
    async def test_markdown_to_html_with_code(self, pdf_generator, sample_document):
        """Testa conversão de código Markdown para HTML"""
        markdown = "```python\nprint('test')\n```"
        html = await pdf_generator._markdown_to_html(
            markdown,
            sample_document,
            None,
        )

        assert "<code>" in html or "<pre>" in html

    @pytest.mark.asyncio
    async def test_markdown_to_html_custom_template(
        self, pdf_generator, sample_document, tmp_path
    ):
        """Testa uso de template HTML customizado"""
        # Criar template customizado
        template_content = """
        <!DOCTYPE html>
        <html>
        <head><title>{{ title }}</title></head>
        <body>
            <h1>CUSTOM: {{ title }}</h1>
            {{ content|safe }}
        </body>
        </html>
        """
        template_path = tmp_path / "custom.html"
        template_path.write_text(template_content)

        # Usar template customizado
        with patch.object(pdf_generator, "_template_dir", str(tmp_path)):
            html = await pdf_generator._markdown_to_html(
                sample_document.markdown_content,
                sample_document,
                "custom.html",
            )

            assert "CUSTOM:" in html


class TestHTMLToPDF:
    """Testes de conversão de HTML para PDF"""

    @pytest.mark.asyncio
    async def test_html_to_pdf_without_weasyprint(self, pdf_generator):
        """Testa erro quando WeasyPrint não está disponível"""
        with patch.object(pdf_generator, "_weasyprint_available", False):
            with pytest.raises(RuntimeError, match="WeasyPrint não está disponível"):
                await pdf_generator.generate_pdf(
                    document=sample_document,
                    markdown_content="# Test",
                )

    @pytest.mark.asyncio
    async def test_html_to_pdf_missing_content(self, pdf_generator):
        """Testa erro quando não há conteúdo Markdown"""
        if not pdf_generator.is_available():
            pytest.skip("WeasyPrint não disponível")

        doc = LearningDocument(
            title="Test", type=DocumentType.EXPERIMENT_REPORT
        )

        with pytest.raises(ValueError, match="Conteúdo Markdown não disponível"):
            await pdf_generator.generate_pdf(doc)


class TestPDFGeneration:
    """Testes de geração completa de PDF"""

    @pytest.mark.asyncio
    async def test_generate_pdf_success(
        self, pdf_generator, sample_document, tmp_path
    ):
        """Testa geração bem-sucedida de PDF"""
        if not pdf_generator.is_available():
            pytest.skip("WeasyPrint não disponível")

        with patch.object(pdf_generator, "_output_dir", str(tmp_path)):
            pdf_path = await pdf_generator.generate_pdf(sample_document)

            assert os.path.exists(pdf_path)
            assert pdf_path.endswith(".pdf")
            assert os.path.getsize(pdf_path) > 0

    @pytest.mark.asyncio
    async def test_generate_pdf_with_custom_template(
        self, pdf_generator, sample_document, tmp_path
    ):
        """Testa geração de PDF com template customizado"""
        if not pdf_generator.is_available():
            pytest.skip("WeasyPrint não disponível")

        # Criar template customizado
        template_content = """
        <!DOCTYPE html>
        <html>
        <head><title>{{ title }}</title></head>
        <body><h1>{{ title }}</h1>{{ content|safe }}</body>
        </html>
        """
        template_path = tmp_path / "templates" / "custom.html"
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(template_content)

        with patch.object(pdf_generator, "_template_dir", str(template_path.parent)):
            with patch.object(pdf_generator, "_output_dir", str(tmp_path)):
                pdf_path = await pdf_generator.generate_pdf(
                    sample_document, template_name="custom.html"
                )

                assert os.path.exists(pdf_path)


class TestFromMarkdownFile:
    """Testes de geração a partir de arquivo Markdown"""

    @pytest.mark.asyncio
    async def test_generate_from_markdown_file(self, pdf_generator, tmp_path):
        """Testa geração de PDF a partir de arquivo Markdown"""
        if not pdf_generator.is_available():
            pytest.skip("WeasyPrint não disponível")

        # Criar arquivo Markdown temporário
        md_content = "# Test Document\n\nThis is a test."
        md_file = tmp_path / "test.md"
        md_file.write_text(md_content)

        with patch.object(pdf_generator, "_output_dir", str(tmp_path)):
            pdf_path = await pdf_generator.generate_from_markdown_file(str(md_file))

            assert os.path.exists(pdf_path)
            assert pdf_path.endswith(".pdf")

    @pytest.mark.asyncio
    async def test_generate_from_nonexistent_file(self, pdf_generator):
        """Testa erro com arquivo inexistente"""
        with pytest.raises(FileNotFoundError):
            await pdf_generator.generate_from_markdown_file("/nonexistent/file.md")


class TestBatchGeneration:
    """Testes de geração em lote"""

    @pytest.mark.asyncio
    async def test_generate_batch(self, pdf_generator, sample_document, tmp_path):
        """Testa geração de PDFs em lote"""
        if not pdf_generator.is_available():
            pytest.skip("WeasyPrint não disponível")

        docs = [
            (sample_document, "# Doc 1"),
            (
                LearningDocument(
                    title="Doc 2", type=DocumentType.WEEKLY_SUMMARY
                ),
                "# Doc 2",
            ),
        ]

        with patch.object(pdf_generator, "_output_dir", str(tmp_path)):
            pdf_paths = await pdf_generator.generate_batch(docs)

            assert len(pdf_paths) == 2
            for path in pdf_paths:
                if path:  # Pode ser None em caso de erro
                    assert os.path.exists(path)


class TestTemplates:
    """Testes de templates HTML"""

    def test_get_default_template_returns_html(self, pdf_generator):
        """Testa se o template padrão retorna HTML válido"""
        for doc_type in DocumentType:
            template = pdf_generator._get_default_template(doc_type)
            assert ("<!DOCTYPE html>" in template or "<html" in template.lower())
            assert "</html>" in template

    def test_get_base_css_returns_styles(self, pdf_generator):
        """Testa se o CSS base retorna estilos válidos"""
        css = pdf_generator._get_base_css()
        assert "@page" in css
        assert "body {" in css
        assert "h1 {" in css
        assert "table {" in css
        assert "pre {" in css
        assert "code {" in css


class TestEdgeCases:
    """Testes de casos extremos"""

    @pytest.mark.asyncio
    async def test_empty_markdown_content(self, pdf_generator, sample_document):
        """Testa comportamento com conteúdo vazio"""
        if not pdf_generator.is_available():
            pytest.skip("WeasyPrint não disponível")

        with pytest.raises(ValueError):
            await pdf_generator.generate_pdf(sample_document, markdown_content="")

    @pytest.mark.asyncio
    async def test_markdown_with_special_characters(
        self, pdf_generator, sample_document, tmp_path
    ):
        """Testa Markdown com caracteres especiais"""
        if not pdf_generator.is_available():
            pytest.skip("WeasyPrint não disponível")

        special_md = "# Test <>&\"\n\nÁéíóú ñ ß"
        html = await pdf_generator._markdown_to_html(
            special_md, sample_document, None
        )

        assert "Test" in html
        # HTML entities devem estar presentes ou os caracteres preservados

    @pytest.mark.asyncio
    async def test_very_long_markdown(self, pdf_generator, sample_document, tmp_path):
        """Testa Markdown muito longo"""
        if not pdf_generator.is_available():
            pytest.skip("WeasyPrint não disponível")

        long_md = "# Long Document\n\n" + "## Section\n\nContent\n" * 100
        html = await pdf_generator._markdown_to_html(long_md, sample_document, None)

        assert "Long Document" in html

    @pytest.mark.asyncio
    async def test_markdown_with_insights(
        self, pdf_generator, sample_document, sample_insights
    ):
        """Testa Markdown com insights"""
        doc = sample_document
        doc.insights = sample_insights

        html = await pdf_generator._markdown_to_html(
            doc.markdown_content, doc, None
        )

        # Template deve incluir título do documento
        assert doc.title in html


class TestClose:
    """Testes de fechamento de recursos"""

    @pytest.mark.asyncio
    async def test_close_clears_cache(self, pdf_generator):
        """Testa se close limpa o cache de templates"""
        pdf_generator._html_templates["test"] = "value"
        await pdf_generator.close()

        assert len(pdf_generator._html_templates) == 0
