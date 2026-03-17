"""
API Extensions - Endpoints extendidos para Explainability API.

Estende a API existente com novos endpoints e funcionalidades:
- GET /api/v1/explainability/{decision_id} com campos hierárquicos
- POST /api/v1/explainability/generate para geração sob demanda
- Suporte a múltiplos formatos (JSON, texto, HTML)

GAPS-04 Task 5
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class ExplainabilityAPIExtensions:
    """
    Extension methods para Explainability API.

    Esta classe fornece métodos que podem ser integrados ao
    main.py para estender a funcionalidade da API.
    """

    def __init__(
        self,
        mongodb_client,
        shap_calculator=None,
        quality_scorer=None,
        reasoning_extractor=None,
    ):
        """
        Inicializa as extensions.

        Args:
            mongodb_client: Cliente MongoDB para queries
            shap_calculator: ShapCalculator opcional para feature attribution
            quality_scorer: ExplanationQualityScorer opcional
            reasoning_extractor: ReasoningExtractor opcional
        """
        self.db = mongodb_client
        self.shap_calculator = shap_calculator
        self.quality_scorer = quality_scorer
        self.reasoning_extractor = reasoning_extractor

    async def get_explainability_by_decision_id(
        self, decision_id: str
    ) -> Dict[str, Any]:
        """
        Busca explicação por decision_id com campos extendidos.

        Args:
            decision_id: ID da decisão

        Returns:
            Dicionário com explicação completa incluindo campos hierárquicos
        """
        # Buscar explicação no MongoDB
        explanation = await self.db.explainability_ledger.find_one(
            {"decision_id": decision_id}
        )

        if not explanation:
            # Tentar buscar por token como fallback
            explanation = await self.db.explainability_ledger.find_one(
                {"explainability_token": decision_id}
            )

        if not explanation:
            return None

        # Remover _id do MongoDB
        explanation.pop("_id", None)

        # Adicionar campos de qualidade se não presentes
        if "explanation_quality" not in explanation and self.quality_scorer:
            explanation["explanation_quality"] = self.quality_scorer.score_explanation(
                explanation
            )

        return explanation

    async def generate_explanation(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gera nova explicação sob demanda.

        Args:
            request: Dicionário com parâmetros de geração
                - decision_id: ID da decisão (obrigatório)
                - format: 'json', 'text', ou 'html' (padrão: json)
                - include_shap: Se deve calcular SHAP (padrão: False)
                - include_reasoning_extraction: Se deve extrair reasoning (padrão: False)
                - include_quality_score: Se deve calcular qualidade (padrão: True)
                - specialist_votes: Lista de votos para cálculo SHAP
                - reasoning_text: Texto para extração de factores

        Returns:
            Dicionário com explicação gerada
        """
        decision_id = request.get("decision_id")
        output_format = request.get("format", "json")

        # Construir explicação base
        explanation = {
            "decision_id": decision_id,
            "generated_at": datetime.utcnow().isoformat(),
            "format": output_format,
        }

        # Calcular SHAP se solicitado
        if request.get("include_shap") and self.shap_calculator:
            specialist_votes = request.get("specialist_votes", [])
            if specialist_votes:
                decision_data = {
                    "specialist_votes": specialist_votes,
                    "final_decision": request.get("final_decision", "approve"),
                }
                shap_result = self.shap_calculator.calculate_shap(
                    decision_data,
                    features=["confidence", "risk", "seniority_multiplier"],
                )
                explanation["shap_values"] = shap_result["feature_attribution"]

        # Extrair reasoning factors se solicitado
        if request.get("include_reasoning_extraction") and self.reasoning_extractor:
            reasoning_text = request.get("reasoning_text", "")
            if reasoning_text:
                factors = self.reasoning_extractor.extract_and_categorize(
                    reasoning_text
                )
                explanation["reasoning_factors"] = factors["factors"]

        # Calcular score de qualidade
        if request.get("include_quality_score", True) and self.quality_scorer:
            # Usar dados da requisição ou defaults
            quality_input = request.get(
                "explanation",
                {
                    "final_decision": {
                        "decision": request.get("final_decision", "approve")
                    }
                },
            )
            quality_scores = self.quality_scorer.score_explanation(quality_input)
            explanation["explanation_quality"] = quality_scores

        # Gerar token único
        import uuid

        explanation["explainability_token"] = str(uuid.uuid4())

        # Formatar conforme solicitado
        if output_format == "text":
            return self._format_as_text(explanation)
        elif output_format == "html":
            return self._format_as_html(explanation)
        else:
            return explanation

    def format_explanation(
        self, explanation: Dict[str, Any], output_format: str
    ) -> Dict[str, Any]:
        """
        Formata explicação em diferentes formatos.

        Args:
            explanation: Dados da explicação
            output_format: 'json', 'text', ou 'html'

        Returns:
            Explicação formatada conforme especificado
        """
        if output_format == "text":
            return self._format_as_text(explanation)
        elif output_format == "html":
            return self._format_as_html(explanation)
        else:
            # JSON é o padrão - retorna dict
            return explanation

    def _format_as_text(self, explanation: Dict[str, Any]) -> Dict[str, Any]:
        """Formata explicação como texto narrativo."""
        narrative_lines = []
        narrative_lines.append("=== Explicação de Decisão ===\n")

        # Decision ID
        decision_id = explanation.get("decision_id", "N/A")
        narrative_lines.append(f"ID da Decisão: {decision_id}")

        # Decisão final
        if "final_decision" in explanation:
            final = explanation["final_decision"]
            narrative_lines.append(f"Decisão: {final.get('decision', 'N/A')}")

        narrative_lines.append("")

        # SHAP values se disponíveis
        if "shap_values" in explanation:
            narrative_lines.append("Atribuição de Features (SHAP):")
            for feature, value in explanation["shap_values"].items():
                direction = "positivamente" if value > 0 else "negativamente"
                narrative_lines.append(
                    f"  - {feature}: influencia {direction} ({value:+.2f})"
                )
            narrative_lines.append("")

        # Quality scores
        if "explanation_quality" in explanation:
            quality = explanation["explanation_quality"]
            narrative_lines.append("Qualidade da Explicação:")
            narrative_lines.append(
                f"  - Completude: {quality.get('completeness', 0):.2f}"
            )
            narrative_lines.append(f"  - Clareza: {quality.get('clarity', 0):.2f}")
            narrative_lines.append(
                f"  - Especificidade: {quality.get('specificity', 0):.2f}"
            )
            narrative_lines.append(f"  - Score Geral: {quality.get('overall', 0):.2f}")

        return {
            "format": "text",
            "narrative": "\n".join(narrative_lines),
            "raw_data": explanation,
        }

    def _format_as_html(self, explanation: Dict[str, Any]) -> Dict[str, Any]:
        """Formata explicação como HTML."""
        html_parts = []
        html_parts.append("<html><head><title>Explicação de Decisão</title>")
        html_parts.append("<style>")
        html_parts.append("body { font-family: Arial, sans-serif; margin: 20px; }")
        html_parts.append(".section { margin-bottom: 20px; }")
        html_parts.append(
            ".section h3 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; }"
        )
        html_parts.append(".metric { display: inline-block; margin-right: 20px; }")
        html_parts.append(".positive { color: #27ae60; }")
        html_parts.append(".negative { color: #e74c3c; }")
        html_parts.append("</style></head><body>")

        # Header
        html_parts.append("<h1>Explicação de Decisão</h1>")

        # Decision Info
        html_parts.append('<div class="section">')
        html_parts.append(
            f'<h3>ID da Decisão: {explanation.get("decision_id", "N/A")}</h3>'
        )
        html_parts.append(f'<p>Gerado em: {explanation.get("generated_at", "N/A")}</p>')
        html_parts.append("</div>")

        # SHAP Values
        if "shap_values" in explanation:
            html_parts.append('<div class="section">')
            html_parts.append("<h3>Atribuição de Features</h3>")
            for feature, value in explanation["shap_values"].items():
                css_class = "positive" if value > 0 else "negative"
                html_parts.append('<div class="metric">')
                html_parts.append(
                    f'<span class="{css_class}"><strong>{feature}:</strong> {value:+.2f}</span>'
                )
                html_parts.append("</div>")
            html_parts.append("</div>")

        # Quality Scores
        if "explanation_quality" in explanation:
            quality = explanation["explanation_quality"]
            html_parts.append('<div class="section">')
            html_parts.append("<h3>Métricas de Qualidade</h3>")
            html_parts.append(
                f'<p>Completude: {quality.get("completeness", 0):.2f}</p>'
            )
            html_parts.append(f'<p>Clareza: {quality.get("clarity", 0):.2f}</p>')
            html_parts.append(
                f'<p>Especificidade: {quality.get("specificity", 0):.2f}</p>'
            )
            html_parts.append(
                f'<p><strong>Score Geral: {quality.get("overall", 0):.2f}</strong></p>'
            )
            html_parts.append("</div>")

        html_parts.append("</body></html>")

        return {
            "format": "html",
            "html": "\n".join(html_parts),
            "raw_data": explanation,
        }


# Funções auxiliares para integração com FastAPI


def setup_extensions(
    app,
    mongodb_client,
    shap_calculator=None,
    quality_scorer=None,
    reasoning_extractor=None,
):
    """
    Configura endpoints extendidos na aplicação FastAPI.

    Args:
        app: Instância do FastAPI
        mongodb_client: Cliente MongoDB
        shap_calculator: ShapCalculator opcional
        quality_scorer: ExplanationQualityScorer opcional
        reasoning_extractor: ReasoningExtractor opcional
    """
    extensions = ExplainabilityAPIExtensions(
        mongodb_client=mongodb_client,
        shap_calculator=shap_calculator,
        quality_scorer=quality_scorer,
        reasoning_extractor=reasoning_extractor,
    )

    # Endpoint extendido GET /api/v1/explainability/{decision_id}
    @app.get("/api/v1/explainability/{decision_id}/extended")
    async def get_explanation_extended(decision_id: str):
        """Busca explicação extendida por decision_id."""
        explanation = await extensions.get_explainability_by_decision_id(decision_id)

        if not explanation:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=404,
                detail=f"Explanation not found for decision_id: {decision_id}",
            )

        return explanation

    # Endpoint POST /api/v1/explainability/generate
    @app.post("/api/v1/explainability/generate")
    async def generate_explanation_endpoint(request: Dict[str, Any]):
        """Gera nova explicação sob demanda."""
        from pydantic import BaseModel

        class GenerateRequest(BaseModel):
            decision_id: str
            format: str = "json"
            include_shap: bool = False
            include_reasoning_extraction: bool = False
            include_quality_score: bool = True
            specialist_votes: Optional[List[Dict]] = None
            reasoning_text: Optional[str] = None
            final_decision: Optional[str] = None

            class Config:
                extra = "allow"

        # Nota: Em produção, usar o modelo Pydantic corretamente
        # Por ora, processamos diretamente para simplicidade
        explanation = await extensions.generate_explanation(request)

        return explanation

    return extensions
