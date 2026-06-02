"""Gerador de relatórios em formato Markdown"""

import os
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from jinja2 import (
    BaseLoader,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    Template,
    select_autoescape,
)
from src.config import get_settings
from src.models import DocumentType, Insight, LearningDocument

logger = structlog.get_logger()


class MarkdownReportGenerator:
    """Gera relatórios em formato Markdown"""

    def __init__(self):
        """Inicializa o gerador"""
        self.settings = get_settings()
        self._jinja_env: Optional[Environment] = None
        self._output_dir = self.settings.docs_output_dir

        # Criar diretório de saída
        os.makedirs(self._output_dir, exist_ok=True)

    async def initialize(self) -> None:
        """Inicializa o ambiente Jinja2"""
        try:
            # Verificar se existe diretório de templates customizados
            template_dir = self.settings.docs_template_dir
            if os.path.exists(template_dir):
                loader = FileSystemLoader(template_dir)
                logger.info("Usando templates customizados", dir=template_dir)
            else:
                loader = BaseLoader()
                logger.info("Usando templates embutidos")

            self._jinja_env = Environment(
                loader=loader,
                autoescape=select_autoescape(),
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )

        except Exception as e:
            logger.error("Erro ao inicializar Jinja2", error=str(e), exc_info=True)
            raise

    async def generate(
        self,
        document: LearningDocument,
        template_name: Optional[str] = None,
    ) -> str:
        """Gera o conteúdo Markdown para um documento

        Args:
            document: Dados do documento
            template_name: Nome do template customizado (opcional)

        Returns:
            String com conteúdo Markdown
        """
        if not self._jinja_env:
            await self.initialize()

        try:
            # Selecionar template
            if template_name and self._jinja_env.loader:
                template = self._jinja_env.get_template(template_name)
            else:
                template = self._get_default_template(document.type)

            # Contexto para renderização
            context = self._build_context(document)

            # Renderizar
            markdown_content = template.render(**context)

            logger.info(
                "Markdown gerado",
                doc_type=document.type,
                length=len(markdown_content),
            )
            return markdown_content

        except Exception as e:
            logger.error("Erro ao gerar Markdown", error=str(e), exc_info=True)
            raise

    def _build_context(self, document: LearningDocument) -> dict[str, Any]:
        """Constrói contexto para renderização do template"""
        return {
            "document": document,
            "title": document.title,
            "generated_at": document.generated_at or datetime.now(timezone.utc),
            "period_start": document.period_start,
            "period_end": document.period_end,
            "summary": document.summary,
            "insights": document.insights,
            "recommendations": document.recommendations,
            "experiment_runs": document.experiment_runs,
            "metadata": document.metadata,
            "plots": document.plots,
            "format_insight": self._format_insight,
            "format_metric": self._format_metric,
            "format_duration": self._format_duration,
            "calculate_improvement": self._calculate_improvement,
        }

    def _format_insight(self, insight: Insight) -> str:
        """Formata insight para Markdown"""
        confidence_emoji = {
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢",
        }
        emoji = confidence_emoji.get(insight.confidence.value, "⚪")
        return f"{emoji} **{insight.title}**\n\n{insight.description}"

    def _format_metric(self, value: float, decimals: int = 4) -> str:
        """Formata métrica para exibição"""
        if value >= 100:
            return f"{value:.2f}"
        elif value >= 1:
            return f"{value:.3f}"
        else:
            return f"{value:.{decimals}f}"

    def _format_duration(self, seconds: float) -> str:
        """Formata duração em texto legível"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"

    def _calculate_improvement(self, current: float, baseline: float, decimals: int = 1) -> float:
        """Calcula percentual de melhoria"""
        if baseline == 0:
            return 0.0
        return ((current - baseline) / baseline) * 100

    def _get_default_template(self, doc_type: DocumentType) -> Template:
        """Retorna o template padrão para cada tipo de documento"""
        template_string = self._get_template_string(doc_type)
        return self._jinja_env.from_string(template_string)

    def _get_template_string(self, doc_type: DocumentType) -> str:
        """Retorna o string do template para cada tipo"""

        # Template base para experiment_report
        if doc_type == DocumentType.EXPERIMENT_REPORT:
            return """# {{ title }}

**Gerado em:** {{ generated_at.strftime('%Y-%m-%d %H:%M:%S') UTC }
**Período:** {% if period_start %}{{ period_start.strftime('%Y-%m-%d') }} a {{ period_end.strftime('%Y-%m-%d') }}{% else %}N/A{% endif %}
**Experimentos Analisados:** {{ experiment_runs|length }}

---

## Resumo Executivo

{{ summary }}

{% if insights %}

## Insights Principais

{% for insight in insights %}
### {{ insight.title }}

**Confiança:** {{ insight.confidence.value|upper }}
**Categoria:** {{ insight.category or 'Geral' }}

{{ insight.description }}

**Evidências:**
{% for key, value in insight.evidence.items() %}
- **{{ key }}:** {{ value }}
{% endfor %}

{% if insight.experiment_ids %}
**Runs relacionados:** `{{ insight.experiment_ids|join(', ') }}`
{% endif %}

---
{% endfor %}
{% endif %}

{% if experiment_runs %}

## Experimentos Analisados

| ID | Nome | Status | Início | Fim | Métricas Principais |
|----|------|--------|--------|-----|---------------------|
{% for run in experiment_runs %}
| {{ run.run_id[:8] }} | {{ run.name }} | {{ run.status }} | {% if run.start_time %}{{ run.start_time.strftime('%Y-%m-%d %H:%M') }}{% else %}N/A{% endif %} | {% if run.end_time %}{{ run.end_time.strftime('%Y-%m-%d %H:%M') }}{% else %}N/A{% endif %} | {% if run.metrics.get('val_accuracy') %}val_acc: {{ format_metric(run.metrics['val_accuracy']) }}{% endif %}{% if run.metrics.get('accuracy') %}, acc: {{ format_metric(run.metrics['accuracy']) }}{% endif %} |
{% endfor %}

{% endif %}

{% if experiment_runs %}

## Análise Detalhada

{% for run in experiment_runs %}
### Experimento: {{ run.name }}

**Run ID:** `{{ run.run_id }}`
**Status:** {{ run.status }}
**Experimento ID:** {{ run.experiment_id }}

**Datas:**
- Início: {% if run.start_time %}{{ run.start_time.strftime('%Y-%m-%d %H:%M:%S') }}{% else %}N/A{% endif %}
- Fim: {% if run.end_time %}{{ run.end_time.strftime('%Y-%m-%d %H:%M:%S') }}{% else %}N/A{% endif %}
{% if run.start_time and run.end_time %}
- Duração: {{ format_duration((run.end_time - run.start_time).total_seconds()) }}
{% endif %}

**Métricas:**
{% for metric_name, metric_value in run.metrics.items() %}
- **{{ metric_name }}:** {{ format_metric(metric_value) }}
{% endfor %}

**Parâmetros:**
{% for param_name, param_value in run.params.items() %}
- **{{ param_name }}:** {{ param_value }}
{% endfor %}

**Tags:**
{% for tag_name, tag_value in run.tags.items() %}
- **{{ tag_name }}:** {{ tag_value }}
{% endfor %}

**Artifacts:**
{% if run.artifact_uri %}
- URI: `{{ run.artifact_uri }}`
{% endif %}

---
{% endfor %}
{% endif %}

{% if recommendations %}

## Recomendações

Com base na análise, recomendamos:

{% for rec in recommendations %}
{{ loop.index }}. {{ rec }}
{% endfor %}

{% endif %}

{% if plots %}

## Visualizações

{% for plot_path in plots %}
### Gráfico {{ loop.index }}

![{{ loop.index }}]({{ plot_path }})

{% endfor %}
{% endif %}

---

## Apêndice

**Fonte de Dados:** MLflow runs `{% for run in experiment_runs %}{{ run.run_id }}{% if not loop.last %}, {% endif %}{% endfor %}`
**Template Version:** {{ document.template_version }}
**Gerado por:** Learning Documentation Generator v1.0.0
"""

        # Template para weekly/monthly/daily summary
        elif doc_type in (
            DocumentType.WEEKLY_SUMMARY,
            DocumentType.MONTHLY_SUMMARY,
            DocumentType.DAILY_SUMMARY,
        ):
            return """# {{ title }} - Relatório {{ period_name }}

**Gerado em:** {{ generated_at.strftime('%Y-%m-%d %H:%M:%S') UTC }
**Período:** {% if period_start %}{{ period_start.strftime('%Y-%m-%d') }} a {{ period_end.strftime('%Y-%m-%d') }}{% endif %}
**Experimentos Analisados:** {{ experiment_runs|length }}

---

## Resumo Executivo

{{ summary }}

{% if insights %}

## Insights do Período

### Performance de Modelos

{% set perf_insights = insights|selectattr('category', 'equalto', 'performance')|list %}
{% if perf_insights %}
{% for insight in perf_insights %}
{{ format_insight(insight) }}

{% endfor %}
{% else %}
Nenhum insight de performance identificado neste período.
{% endif %}

### Melhorias Identificadas

{% set imp_insights = insights|selectattr('category', 'equalto', 'improvement')|list %}
{% if imp_insights %}
{% for insight in imp_insights %}
{{ format_insight(insight) }}

{% endfor %}
{% else %}
Nenhuma melhoria significativa identificada.
{% endif %}

### Regressões Detectadas

{% set reg_insights = insights|selectattr('category', 'equalto', 'regression')|list %}
{% if reg_insights %}
{% for insight in reg_insights %}
{{ format_insight(insight) }}

{% endfor %}
{% else %}
Nenhuma regressão detectada.
{% endif %}

### Tendências

{% set trend_insights = insights|selectattr('category', 'equalto', 'trend')|list %}
{% if trend_insights %}
{% for insight in trend_insights %}
{{ format_insight(insight) }}

{% endfor %}
{% else %}
Nenhuma tendência identificada.
{% endif %}

{% endif %}

{% if recommendations %}

## Recomendações

{% for rec in recommendations %}
{{ loop.index }}. {{ rec }}
{% endfor %}

{% endif %}

---

## Apêndice

**Total de Experimentos:** {{ experiment_runs|length }}
**Experimentos Concluídos:** {{ experiment_runs|selectattr('status', 'equalto', 'FINISHED')|list|length }}
**Experimentos Falhados:** {{ experiment_runs|selectattr('status', 'equalto', 'FAILED')|list|length }}
**Template Version:** {{ document.template_version }}
"""

        # Template para promotion_report
        elif doc_type == DocumentType.PROMOTION_REPORT:
            return """# {{ title }} - Relatório de Promoção de Modelo

**Gerado em:** {{ generated_at.strftime('%Y-%m-%d %H:%M:%S') UTC

---

## Resumo

{{ summary }}

{% if experiment_runs %}

## Modelo Promovido

{% set best_run = experiment_runs|selectattr('status', 'equalto', 'FINISHED')|sort(attribute='metrics.val_accuracy', reverse=true)|first|default(experiment_runs[0]) %}
{% if best_run %}

### {{ best_run.name }}

**Run ID:** `{{ best_run.run_id }}`

**Métricas Finais:**
{% for metric_name, metric_value in best_run.metrics.items() %}
- **{{ metric_name }}:** {{ format_metric(metric_value) }}
{% endfor %}

**Hiperparâmetros:**
{% for param_name, param_value in best_run.params.items() %}
- **{{ param_name }}:** {{ param_value }}
{% endfor %}

{% endif %}
{% endif %}

{% if insights %}

## Justificativa

{% for insight in insights %}
{{ format_insight(insight) }}

{% endfor %}
{% endif %}

{% if recommendations %}

## Próximos Passos

{% for rec in recommendations %}
{{ loop.index }}. {{ rec }}
{% endfor %}

{% endif %}

---

**Aprovado para produção:** {{ metadata.get('approved_for_production', 'N/A') }}
**Aprovado por:** {{ metadata.get('approved_by', 'N/A') }}
**Data de aprovação:** {{ metadata.get('approval_date', 'N/A') }}
"""

        # Template para rollback_analysis
        elif doc_type == DocumentType.ROLLBACK_ANALYSIS:
            return """# {{ title }} - Análise de Rollback

**Gerado em:** {{ generated_at.strftime('%Y-%m-%d %H:%M:%S') UTC

---

## Resumo do Incidente

{{ summary }}

{% if experiment_runs %}

## Modeles Envolvidos

{% for run in experiment_runs %}
### {{ run.name }}

**Run ID:** `{{ run.run_id }}`
**Status:** {{ run.status }}

**Métricas:**
{% for metric_name, metric_value in run.metrics.items() %}
- **{{ metric_name }}:** {{ format_metric(metric_value) }}
{% endfor %}

---
{% endfor %}
{% endif %}

{% if insights %}

## Análise de Causa Raiz

{% for insight in insights %}
{{ format_insight(insight) }}

{% endfor %}
{% endif %}

{% if recommendations %}

## Ações Corretivas

{% for rec in recommendations %}
{{ loop.index }}. {{ rec }}
{% endfor %}

{% endif %}

---

**Motivo do Rollback:** {{ metadata.get('rollback_reason', 'N/A') }}
**Detectado por:** {{ metadata.get('detected_by', 'N/A') }}
**Tempo de degradação:** {{ metadata.get('degradation_duration', 'N/A') }}
"""

        # Fallback template
        else:
            return """# {{ title }}

**Gerado em:** {{ generated_at.strftime('%Y-%m-%d %H:%M:%S') UTC

---

## Resumo

{{ summary }}

{% if insights %}

## Insights

{% for insight in insights %}
### {{ insight.title }}

{{ insight.description }}

{% endfor %}
{% endif %}

{% if recommendations %}

## Recomendações

{% for rec in recommendations %}
{{ loop.index }}. {{ rec }}
{% endfor %}

{% endif %}

"""

    async def save_to_file(
        self,
        document: LearningDocument,
        content: str,
    ) -> str:
        """Salva o conteúdo Markdown em arquivo

        Args:
            document: Dados do documento
            content: Conteúdo Markdown

        Returns:
            Caminho do arquivo salvo
        """
        try:
            # Criar nome de arquivo
            safe_title = document.title.lower().replace(" ", "_").replace("/", "_")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{safe_title}.md"
            filepath = os.path.join(self._output_dir, filename)

            # Escrever arquivo
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info("Arquivo Markdown salvo", path=filepath)
            return filepath

        except Exception as e:
            logger.error("Erro ao salvar Markdown", error=str(e), exc_info=True)
            raise

    async def close(self) -> None:
        """Fecha recursos"""
        self._jinja_env = None
