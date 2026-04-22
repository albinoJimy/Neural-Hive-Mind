"""
ReasoningExtractor - Extrator de fatores de raciocínio.

Stub - expandir em iteração futura.
"""

from typing import Any


class ReasoningExtractor:
    """Stub - expandir em iteração futura."""

    def extract_reasoning_factors(self, opinion: dict[str, Any]) -> list[str]:
        """Extrai fatores de raciocínio de uma opinião."""
        return []

    def extract_from_text(self, text: str) -> list[str]:
        """Extrai fatores de raciocínio de texto livre."""
        return []

    def extract(self, decision: dict[str, Any]) -> dict[str, Any]:
        """
        Extrai fatores de raciocínio de uma decisão.

        Args:
            decision: Dicionário com decisão incluindo reasoning_factors

        Returns:
            Dicionário com fatores extraídos
        """
        factors = decision.get("reasoning_factors", [])

        return {
            "factors": factors,
            "total_factors": len(factors),
            "decision_id": decision.get("decision_id", "unknown"),
        }

    def format_as_text(self, reasoning_data: dict[str, Any]) -> str:
        """
        Formata fatores de raciocínio como texto legível.

        Args:
            reasoning_data: Dicionário com fatores de raciocínio

        Returns:
            String formatada com os fatores
        """
        factors = reasoning_data.get("factors", [])

        if not factors:
            return "Nenhum fator de raciocínio identificado."

        lines = ["Fatores de Raciocínio:"]
        for factor in factors:
            factor_name = factor.get("factor", "unknown")
            impact = factor.get("impact", 0.0)
            lines.append(f"  - {factor_name}: impacto {impact:.2f}")

        return "\n".join(lines)
