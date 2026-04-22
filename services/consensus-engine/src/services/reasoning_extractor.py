"""
ReasoningExtractor - Extração e categorização de factores de reasoning.

Extrai factores-chave do texto de reasoning dos especialistas,
categorizando-os por domínio (técnico, negócio, segurança, compliance).

GAPS-04 Task 3
"""

import re
from collections import defaultdict
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ReasoningExtractor:
    """
    Extrator de factores de reasoning para explicações.

    Processa texto de reasoning de especialistas para extrair
    factores-chave, categorizá-los e gerar output estruturado.
    """

    # Palavras-chave por categoria
    CATEGORY_KEYWORDS = {
        "technical": [
            "arquitetura",
            "microserviço",
            "api",
            "rest",
            "kafka",
            "mongodb",
            "banco de dados",
            "código",
            "escalável",
            "performance",
            "latência",
            "throughput",
            "deploy",
            "pipeline",
            "ci/cd",
            "docker",
            "kubernetes",
            "backend",
            "frontend",
            "framework",
            "biblioteca",
            "algoritmo",
        ],
        "business": [
            "roi",
            "custo",
            "receita",
            "lucro",
            "investimento",
            "retorno",
            "negócio",
            "cliente",
            "mercado",
            "competitivo",
            "estratégia",
            "kpi",
            "métrica",
            "objetivo",
            "meta",
            "deadline",
            "prazo",
        ],
        "security": [
            "vulnerabilidade",
            "sql injection",
            "xss",
            "autenticação",
            "oauth",
            "criptografia",
            "ssl",
            "tls",
            "segurança",
            "ataque",
            "ameaça",
            "firewall",
            "permission",
            "role",
            "access",
            "injeção",
            "payload",
        ],
        "compliance": [
            "lgpd",
            "gdpr",
            "compliance",
            "auditoria",
            "regulação",
            "lei",
            "conformidade",
            "privacidade",
            "dpi",
            "anonimização",
            "consentimento",
            "gpdr",
            "sox",
            "iso",
            "norma",
            "regulamentação",
        ],
    }

    # Padrões regex para detecção de factores
    FACTOR_PATTERNS = [
        r"[A-Z][^.!?]*[.!?]",  # Frases completas começando com maiúscula
        r"[a-záàâãéèêíïóôõöúç]+(?:\s+[a-záàâãéèêíïóôõöúç]+){3,}",  # Sequências de palavras
    ]

    def __init__(self, max_factors: int = 10):
        """
        Inicializa o extrator.

        Args:
            max_factors: Número máximo de factores a extrair por texto
        """
        self.max_factors = max_factors

    def extract_factors(self, reasoning: str) -> dict[str, Any]:
        """
        Extrai factores-chave do texto de reasoning.

        Args:
            reasoning: Texto de reasoning do especialista

        Returns:
            Dicionário com lista de factores extraídos
        """
        if not reasoning or not reasoning.strip():
            return {"factors": [], "source_length": 0}

        # Dividir texto em sentenças/frases
        sentences = self._split_into_sentences(reasoning)

        # Extrair factores significativos
        factors = []
        for i, sentence in enumerate(sentences):
            if len(factors) >= self.max_factors:
                break

            # Ignorar sentenças muito curtas
            if len(sentence.strip()) < 10:
                continue

            factor = {
                "text": sentence.strip(),
                "position": i,
                "confidence": self._calculate_confidence(sentence),
            }

            factors.append(factor)

        return {
            "factors": factors,
            "source_length": len(reasoning),
            "num_sentences": len(sentences),
        }

    def _split_into_sentences(self, text: str) -> list[str]:
        """Divide texto em sentenças."""
        # Dividir por pontuação básica
        sentences = re.split(r"[.!?]+", text)

        # Limpar sentenças vazias
        sentences = [s.strip() for s in sentences if s.strip()]

        return sentences

    def _calculate_confidence(self, sentence: str) -> float:
        """
        Calcula confiança da extração baseada na qualidade da sentença.

        Sentenças mais longas e com palavras-chave conhecidas têm maior confiança.
        """
        # Base score em 0.5
        confidence = 0.5

        # Bônus por comprimento (até 50 caracteres)
        length = len(sentence)
        if 20 <= length <= 100:
            confidence += 0.2
        elif length > 100:
            confidence += 0.1

        # Bônus por conter palavras-chave conhecidas
        all_keywords = []
        for keywords in self.CATEGORY_KEYWORDS.values():
            all_keywords.extend(keywords)

        sentence_lower = sentence.lower()
        keyword_count = sum(1 for kw in all_keywords if kw.lower() in sentence_lower)

        if keyword_count > 0:
            confidence += min(0.3, keyword_count * 0.1)

        return min(1.0, confidence)

    def categorize_factor(self, factor_text: str) -> dict[str, Any]:
        """
        Categoriza um factor de reasoning.

        Args:
            factor_text: Texto do factor a categorizar

        Returns:
            Dicionário com categoria e confiança da categorização
        """
        # Contar matches por categoria
        category_scores = defaultdict(int)
        factor_lower = factor_text.lower()

        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in factor_lower:
                    category_scores[category] += 1

        # Encontrar categoria com maior score
        if category_scores:
            best_category = max(category_scores.items(), key=lambda x: x[1])
            confidence = min(1.0, best_category[1] * 0.3)
            return {
                "category": best_category[0],
                "confidence": confidence,
                "all_scores": dict(category_scores),
            }

        # Nenhuma categoria detectada
        return {"category": "general", "confidence": 0.0, "all_scores": {}}

    def generate_structured_output(
        self, factors_result: dict[str, Any], original_reasoning: str
    ) -> dict[str, Any]:
        """
        Gera output estruturado com categorias e citações.

        Args:
            factors_result: Resultado de extract_factors()
            original_reasoning: Texto original para citações

        Returns:
            Dicionário estruturado com factores categorizados
        """
        factors = factors_result.get("factors", [])

        structured_factors = []
        for factor in factors:
            # Categorizar o factor
            categorization = self.categorize_factor(factor["text"])

            # Encontrar citação (posição no texto original)
            citation = self._find_citation(factor["text"], original_reasoning)

            structured_factor = {
                "text": factor["text"],
                "category": categorization["category"],
                "category_confidence": categorization["confidence"],
                "extraction_confidence": factor["confidence"],
                "citation": citation,
                "position": factor["position"],
            }

            structured_factors.append(structured_factor)

        return {
            "factors": structured_factors,
            "total_factors": len(structured_factors),
            "categories": self._summarize_categories(structured_factors),
            "source_length": factors_result.get("source_length", 0),
        }

    def _find_citation(self, factor_text: str, original_text: str) -> dict[str, int]:
        """Encontra posição do factor no texto original."""
        start = original_text.find(factor_text)

        if start >= 0:
            end = start + len(factor_text)
            return {"start": start, "end": end, "found": True}

        return {"start": -1, "end": -1, "found": False}

    def _summarize_categories(self, structured_factors: list[dict]) -> dict[str, int]:
        """Resume contagem de factores por categoria."""
        category_count = defaultdict(int)

        for factor in structured_factors:
            category_count[factor["category"]] += 1

        return dict(category_count)

    def batch_extract(self, reasonings: list[str]) -> list[dict[str, Any]]:
        """
        Extrai factores de múltiplos textos de reasoning.

        Args:
            reasonings: Lista de textos de reasoning

        Returns:
            Lista de resultados estruturados
        """
        results = []

        for reasoning in reasonings:
            factors = self.extract_factors(reasoning)
            structured = self.generate_structured_output(factors, reasoning)
            results.append(structured)

        return results

    def extract_and_categorize(
        self, reasoning: str, include_general: bool = False
    ) -> dict[str, Any]:
        """
        Método conveniente que extrai e categoriza em uma chamada.

        Args:
            reasoning: Texto de reasoning
            include_general: Se deve incluir factores "general"

        Returns:
            Dicionário estruturado completo
        """
        factors = self.extract_factors(reasoning)
        structured = self.generate_structured_output(factors, reasoning)

        # Opcionalmente filtrar factores "general"
        if not include_general:
            structured["factors"] = [f for f in structured["factors"] if f["category"] != "general"]
            structured["total_factors"] = len(structured["factors"])

        return structured
