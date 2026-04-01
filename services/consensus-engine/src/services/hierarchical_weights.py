"""
Calculadora de pesos hierárquicos para especialistas.

Combina feromônios, senioridade e domínio para calcular
o peso final de cada especialista no processo de consenso.
"""

from typing import Dict, List, Optional

import structlog

# Mock UnifiedDomain para contornar dependência de Python >=3.11
try:
    from neural_hive_domain import UnifiedDomain
except ImportError:
    from enum import Enum

    class UnifiedDomain(str, Enum):
        BUSINESS = "BUSINESS"
        TECHNICAL = "TECHNICAL"
        SECURITY = "SECURITY"
        INFRASTRUCTURE = "INFRASTRUCTURE"
        BEHAVIOR = "BEHAVIOR"
        OPERATIONAL = "OPERATIONAL"
        COMPLIANCE = "COMPLIANCE"
        ARCHITECTURE = "ARCHITECTURE"


from src.models.seniority import (
    SENIORITY_MULTIPLIERS,
    SeniorityLevel,
    parse_seniority_level,
)

logger = structlog.get_logger()


class HierarchicalWeightCalculator:
    """
    Calcula pesos hierárquicos baseados em senioridade de especialistas.

    Multiplicadores aplicados:
    - Feromônio: peso dinâmico baseado em histórico
    - Senioridade: multiplicador fixo por nível (0.5 a 2.0)
    - Domínio: peso do especialista no domínio da intenção
    """

    # Peso padrão quando nenhum domínio específico configurado
    DEFAULT_DOMAIN_WEIGHT = 0.2

    def __init__(self, config):
        """
        Inicializa calculadora de pesos hierárquicos.

        Args:
            config: Configuração do Consensus Engine
        """
        self.config = config
        self.multipliers = SENIORITY_MULTIPLIERS
        self.domain_weights = getattr(config, "domain_specialist_weights", {})

    def calculate_hierarchical_weight(
        self,
        specialist_type: str,
        domain: UnifiedDomain,
        pheromone_weight: float,
        seniority: Optional[SeniorityLevel] = None,
    ) -> float:
        """
        Calcula peso final hierárquico para um especialista.

        Fórmula:
            weight_raw = pheromone_weight × seniority_multiplier × domain_weight
            weight_final = min(1.0, weight_raw / 2.0)  # Normalizar

        Args:
            specialist_type: Tipo do especialista (ex: 'business', 'technical')
            domain: Domínio da intenção
            pheromone_weight: Peso baseado em feromônios (0.0 - 1.0)
            seniority: Nível de senioridade (se None, usa config padrão)

        Returns:
            Peso final calculado (0.0 - 1.0)
        """
        # Se feature flag desabilitado, retornar peso normalizado do feromônio
        if not getattr(self.config, "enable_hierarchical_consensus", True):
            return pheromone_weight

        # Determinar senioridade
        if seniority is None:
            seniority_str = self.config.specialist_seniority.get(
                specialist_type, "mid_level"  # Padrão
            )
            seniority = parse_seniority_level(seniority_str)

        # Obter multiplicador de senioridade
        seniority_multiplier = self.multipliers[seniority]

        # Obter peso de domínio
        domain_key = f"{specialist_type}_{domain.value}"
        domain_weight = self.domain_weights.get(domain_key, self.DEFAULT_DOMAIN_WEIGHT)

        # Calcular peso bruto
        raw_weight = pheromone_weight * seniority_multiplier * domain_weight

        # Normalizar para [0, 1] (máximo teórico é 1.0 × 2.0 × 1.0 = 2.0)
        normalized_weight = min(1.0, raw_weight / 2.0)

        logger.debug(
            "hierarchical_weight_calculated",
            specialist_type=specialist_type,
            domain=domain.value,
            pheromone_weight=pheromone_weight,
            seniority=seniority.value,
            seniority_multiplier=seniority_multiplier,
            domain_weight=domain_weight,
            final_weight=normalized_weight,
        )

        return normalized_weight

    def calculate_batch_weights(
        self,
        specialist_opinions: List[Dict[str, any]],
        domain: UnifiedDomain,
        base_pheromone_weights: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Calcula pesos para múltiplos especialistas em lote.

        Args:
            specialist_opinions: Lista de opiniões dos especialistas
            domain: Domínio da intenção
            base_pheromone_weights: Pesos base de feromônio por tipo

        Returns:
            Dicionário {specialist_type: weight}
        """
        weights = {}

        for opinion in specialist_opinions:
            specialist_type = opinion["specialist_type"]
            pheromone_weight = base_pheromone_weights.get(specialist_type, 0.2)

            # Usar senioridade individual se fornecida na opinião
            seniority = None
            if "seniority_level" in opinion:
                seniority = parse_seniority_level(opinion["seniority_level"])

            weight = self.calculate_hierarchical_weight(
                specialist_type=specialist_type,
                domain=domain,
                pheromone_weight=pheromone_weight,
                seniority=seniority,
            )

            weights[specialist_type] = weight

        return weights
