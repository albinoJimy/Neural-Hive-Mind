"""
ShapCalculator - Feature Attribution para decisões de consenso.

Implementa Kernel SHAP simplificado para explicar contribuição de features
nas decisões multi-agente do Neural-Hive-Mind.

GAPS-04 Task 2
"""

import numpy as np
from typing import List, Dict, Any, Optional
from collections import defaultdict
import structlog

logger = structlog.get_logger(__name__)


class ShapCalculator:
    """
    Calculadora de valores SHAP para decisões de consenso.

    Usa abordagem simplificada do Kernel SHAP para explicar quanto
    cada feature (confidence, risk, seniority) contribuiu para a
    decisão final.
    """

    def __init__(self, n_background_samples: int = 10):
        """
        Inicializa o calculador SHAP.

        Args:
            n_background_samples: Número de amostras de fundo para Kernel SHAP
        """
        self.n_background_samples = n_background_samples

    def calculate_shap(
        self,
        decision_data: Dict[str, Any],
        features: List[str]
    ) -> Dict[str, Any]:
        """
        Calcula valores SHAP para uma decisão de consenso.

        Args:
            decision_data: Dados da decisão incluindo specialist_votes
            features: Lista de features para calcular atribuição

        Returns:
            Dicionário com feature_attribution e metadados
        """
        specialist_votes = decision_data.get('specialist_votes', [])

        if not specialist_votes:
            return {
                'feature_attribution': {f: 0.0 for f in features},
                'method': 'kernel_shap',
                'num_votes': 0
            }

        # Extrair valores das features dos votos
        feature_values = self._extract_feature_values(specialist_votes, features)

        # Calcular valor base (média das predições)
        base_value = self._calculate_base_value(feature_values, decision_data)

        # Calcular valores SHAP usando Kernel SHAP simplificado
        shap_values = self._calculate_kernel_shap(
            feature_values,
            base_value,
            decision_data
        )

        return {
            'feature_attribution': shap_values,
            'base_value': base_value,
            'method': 'kernel_shap',
            'num_votes': len(specialist_votes),
            'features_used': features
        }

    def _extract_feature_values(
        self,
        specialist_votes: List[Dict[str, Any]],
        features: List[str]
    ) -> Dict[str, List[float]]:
        """Extrai valores das features dos votos dos especialistas."""
        feature_values = defaultdict(list)

        for vote in specialist_votes:
            for feature in features:
                value = self._get_feature_value(vote, feature)
                if value is not None:
                    feature_values[feature].append(value)

        # Preencher features vazias com zeros
        for feature in features:
            if not feature_values[feature]:
                feature_values[feature] = [0.0]

        return dict(feature_values)

    def _get_feature_value(self, vote: Dict[str, Any], feature: str) -> Optional[float]:
        """Extrai valor de uma feature de um voto."""
        # Mapeamento de features para campos no voto
        feature_mapping = {
            'confidence': 'confidence_score',
            'risk': 'risk_score',
            'seniority_multiplier': 'seniority_multiplier'
        }

        field_name = feature_mapping.get(feature, feature)

        # Tentar obter do voto diretamente
        if field_name in vote:
            return float(vote[field_name])

        # Tentar obter do opinion se existir
        if 'opinion' in vote and field_name in vote['opinion']:
            return float(vote['opinion'][field_name])

        return None

    def _calculate_base_value(
        self,
        feature_values: Dict[str, List[float]],
        decision_data: Dict[str, Any]
    ) -> float:
        """
        Calcula valor base (média esperada sem conhecimento de features).

        Para simplificação, usa a média das predições baseadas apenas
        em confiança e risco base.
        """
        # Valor base aproximado como média de aprovação esperada
        # Baseado em confiança agregada se disponível
        if 'aggregated_confidence' in decision_data:
            conf = decision_data['aggregated_confidence']
            risk = decision_data.get('aggregated_risk', 0.5)
            # Aprovação esperada = (conf - risk) normalizado para [-1, 1]
            return (conf - risk) * 2 - 1

        return 0.0  # Neutro sem informação

    def _calculate_kernel_shap(
        self,
        feature_values: Dict[str, List[float]],
        base_value: float,
        decision_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Calcula valores SHAP usando Kernel SHAP simplificado.

        Implementação simplificada que estima contribuição marginal
        de cada feature para a decisão final.
        """
        shap_values = {}

        # Obter decisão final como valor numérico (-1 a 1)
        final_decision_num = self._decision_to_numeric(decision_data.get('final_decision', 'approve'))

        # Para cada feature, calcular contribuição marginal
        for feature, values in feature_values.items():
            avg_value = np.mean(values)

            # Contribuição baseada em quanto a feature desvia da média esperada
            # e como isso afeta a decisão

            if feature == 'confidence':
                # Alta confiança aumenta probabilidade de aprovação
                contribution = (avg_value - 0.5) * 1.5  # Confiança tem peso maior
            elif feature == 'risk':
                # Alto risco diminui probabilidade de aprovação (contribuição negativa)
                contribution = -(avg_value - 0.5) * 1.3
            elif feature == 'seniority_multiplier':
                # Senioridade aumenta peso da opinião
                contribution = (avg_value - 1.0) * 0.3  # Contribuição menor
            else:
                # Outras features com contribuição neutra
                contribution = (avg_value - 0.5) * 0.5

            # Normalizar contribuição para range razoável
            shap_values[feature] = max(-1.0, min(1.0, contribution))

        # Ajustar para que soma das contribuições + base ≈ decisão
        # (propriedade de consistência do SHAP)
        shap_sum = sum(shap_values.values())
        target = final_decision_num - base_value

        if abs(shap_sum) > 0.01:  # Evitar divisão por zero
            scaling_factor = target / shap_sum
            # Limitar fator de escala para evitar distorções extremas
            scaling_factor = max(0.1, min(10.0, scaling_factor))
            for feature in shap_values:
                shap_values[feature] *= scaling_factor

        return shap_values

    def _decision_to_numeric(self, decision: str) -> float:
        """
        Converte decisão textual para valor numérico.

        approve -> 1.0
        conditional -> 0.5
        review_required -> 0.0
        reject -> -1.0
        """
        decision_map = {
            'approve': 1.0,
            'approved': 1.0,
            'conditional': 0.5,
            'review_required': 0.0,
            'reject': -1.0,
            'rejected': -1.0,
            'needs_revision': -0.5
        }
        return decision_map.get(decision.lower(), 0.0)

    def batch_calculate_shap(
        self,
        decisions: List[Dict[str, Any]],
        features: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Calcula valores SHAP para um lote de decisões.

        Args:
            decisions: Lista de dados de decisão
            features: Lista de features para calcular atribuição

        Returns:
            Lista de resultados SHAP com decision_id preservado
        """
        results = []

        for decision in decisions:
            decision_id = decision.get('decision_id', 'unknown')

            shap_result = self.calculate_shap(decision, features)
            shap_result['decision_id'] = decision_id

            results.append(shap_result)

        return results

    def format_explanation(
        self,
        attribution: Dict[str, float],
        language: str = 'pt'
    ) -> str:
        """
        Formata atribuição SHAP como texto legível para humanos.

        Args:
            attribution: Dicionário de feature -> valor SHAP
            language: Idioma da explicação ('pt' ou 'en')

        Returns:
            Texto explicativo formatado
        """
        # Ordenar features por valor absoluto (maior contribuição primeiro)
        sorted_features = sorted(
            attribution.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        )

        if language == 'pt':
            explanation = "Principais fatores que influenciaram a decisão:\n"

            for feature, value in sorted_features[:5]:  # Top 5
                feature_name_pt = self._translate_feature_pt(feature)
                direction = "positivamente" if value > 0 else "negativamente"
                magnitude = abs(value)

                if magnitude > 0.3:
                    intensity = "fortemente"
                elif magnitude > 0.1:
                    intensity = "moderadamente"
                else:
                    intensity = "levemente"

                explanation += (
                    f"- {feature_name_pt} influenciou {intensity} {direction} "
                    f"(contribuição: {value:+.2f})\n"
                )
        else:
            explanation = "Key factors influencing the decision:\n"

            for feature, value in sorted_features[:5]:
                direction = "positively" if value > 0 else "negatively"
                magnitude = abs(value)

                if magnitude > 0.3:
                    intensity = "strongly"
                elif magnitude > 0.1:
                    intensity = "moderately"
                else:
                    intensity = "slightly"

                explanation += (
                    f"- {feature} influenced {intensity} {direction} "
                    f"(contribution: {value:+.2f})\n"
                )

        return explanation.strip()

    def _translate_feature_pt(self, feature: str) -> str:
        """Traduz nome de feature para português."""
        translations = {
            'confidence': 'Confiança',
            'risk': 'Risco',
            'seniority_multiplier': 'Senioridade',
            'base_value': 'Valor Base'
        }
        return translations.get(feature, feature)
