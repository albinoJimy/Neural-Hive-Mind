"""
NarrativeGenerator: Gera narrativas semânticas baseadas em contribuições SHAP/LIME.

Transforma feature importances em texto legível em português para explicar
decisões do modelo de forma compreensível para stakeholders de negócio.
"""

from typing import Dict, List, Any
import structlog

logger = structlog.get_logger(__name__)


class NarrativeGenerator:
    """Gera narrativas explicativas em português."""

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa gerador de narrativas.

        Args:
            config: Configuração com templates personalizados (opcional)
        """
        self.config = config
        self.feature_templates = self._load_feature_templates()

        logger.info("NarrativeGenerator initialized")

    def _load_feature_templates(self) -> Dict[str, str]:
        """
        Carrega templates de descrição para features.

        Returns:
            Dicionário mapeando feature_name para template de descrição
        """
        return {
            # Metadata features
            "num_tasks": "o plano contém {value:.0f} tarefas",
            "priority_score": "a prioridade é {level}",
            "total_duration_ms": "a duração total estimada é {formatted_time}",
            "avg_duration_ms": "cada tarefa leva em média {formatted_time}",
            "risk_score": "o score de risco detectado é {level}",
            "complexity_score": "a complexidade avaliada é {level}",
            # Ontology features
            "domain_risk_weight": "o domínio apresenta risco {level}",
            "avg_task_complexity_factor": "as tarefas têm complexidade {level}",
            "num_patterns_detected": "{value:.0f} padrões arquiteturais foram identificados",
            "num_anti_patterns_detected": "{value:.0f} anti-padrões foram detectados",
            "avg_pattern_quality": "a qualidade dos padrões é {level}",
            "total_anti_pattern_penalty": "penalidades de anti-padrões totalizam {value:.2f}",
            # Graph features
            "num_nodes": "o grafo possui {value:.0f} nós",
            "num_edges": "há {value:.0f} dependências entre tarefas",
            "density": "a densidade do grafo é {level}",
            "avg_coupling": "o acoplamento médio é {level}",
            "max_parallelism": "até {value:.0f} tarefas podem executar em paralelo",
            "critical_path_length": "o caminho crítico tem {value:.0f} passos",
            "num_bottlenecks": "{value:.0f} gargalos foram identificados",
            "graph_complexity_score": "a complexidade do grafo é {level}",
            # Embedding features
            "mean_norm": "a norma média dos embeddings é {value:.2f}",
            "avg_diversity": "a diversidade semântica entre tarefas é {level}",
        }

    def generate_narrative(
        self,
        feature_importances: List[Dict[str, Any]],
        top_n: int = 5,
        explanation_type: str = "shap",
        reasoning_links: Dict[str, Dict[str, Any]] = None,
    ) -> str:
        """
        Gera narrativa explicativa baseada em importâncias.

        Args:
            feature_importances: Lista de importâncias (SHAP ou LIME)
            top_n: Número de features mais importantes para incluir
            explanation_type: Tipo de explicação ('shap' ou 'lime')
            reasoning_links: Mapeamento de features para reasoning_factors

        Returns:
            String com narrativa completa
        """
        if reasoning_links is None:
            reasoning_links = {}
        if not feature_importances:
            return "Não foi possível gerar explicação detalhada."

        # Separar contribuições positivas e negativas
        positive_features = [
            f for f in feature_importances if f["contribution"] == "positive"
        ]
        negative_features = [
            f for f in feature_importances if f["contribution"] == "negative"
        ]

        # Pegar top features de cada tipo
        top_positive = positive_features[: min(top_n, len(positive_features))]
        top_negative = negative_features[: min(top_n, len(negative_features))]

        # Construir narrativa
        narrative_parts = []

        # Introdução
        weight_key = "shap_value" if explanation_type == "shap" else "lime_weight"
        narrative_parts.append(
            f"A decisão foi baseada principalmente nos seguintes fatores:"
        )

        # Fatores positivos
        if top_positive:
            narrative_parts.append("\n\n**Fatores que aumentaram a confiança:**")
            for i, feature in enumerate(top_positive, 1):
                description = self._describe_feature(
                    feature, weight_key, reasoning_links
                )
                narrative_parts.append(f"\n{i}. {description}")

        # Fatores negativos
        if top_negative:
            narrative_parts.append("\n\n**Fatores que reduziram a confiança:**")
            for i, feature in enumerate(top_negative, 1):
                description = self._describe_feature(
                    feature, weight_key, reasoning_links
                )
                narrative_parts.append(f"\n{i}. {description}")

        # Conclusão
        total_importance = sum(f["importance"] for f in feature_importances[:top_n])
        confidence_level = self._interpret_confidence(total_importance)
        narrative_parts.append(
            f"\n\nGrau de confiança da explicação: {confidence_level}."
        )

        return "".join(narrative_parts)

    def _describe_feature(
        self,
        feature: Dict[str, Any],
        weight_key: str,
        reasoning_links: Dict[str, Dict[str, Any]] = None,
    ) -> str:
        """
        Gera descrição textual de uma feature.

        Args:
            feature: Dicionário com informações da feature
            weight_key: Chave para o peso ('shap_value' ou 'lime_weight')
            reasoning_links: Mapeamento de features para reasoning_factors

        Returns:
            String descritiva da feature
        """
        if reasoning_links is None:
            reasoning_links = {}

        feature_name = feature["feature_name"]
        feature_value = feature.get("feature_value", 0.0)
        weight = feature.get(weight_key, 0.0)

        # Obter template
        template = self.feature_templates.get(feature_name, "{name} = {value:.2f}")

        # Determinar nível qualitativo
        level = self._get_qualitative_level(feature_name, feature_value)

        # Formatar tempo se aplicável
        formatted_time = self._format_time_if_needed(feature_name, feature_value)

        # Preencher template
        description = template.format(
            value=feature_value,
            level=level,
            formatted_time=formatted_time,
            name=feature_name,
        )

        # Adicionar impacto
        impact = abs(weight)
        if impact > 0.3:
            impact_text = "forte impacto"
        elif impact > 0.15:
            impact_text = "impacto moderado"
        else:
            impact_text = "leve impacto"

        contribution = (
            "positiva" if feature["contribution"] == "positive" else "negativa"
        )

        base_description = f"**{description.capitalize()}** (contribuição {contribution}, {impact_text})"

        # Adicionar link para reasoning_factor se disponível
        if feature_name in reasoning_links:
            link = reasoning_links[feature_name]
            factor_name = link["factor_name"]
            factor_score = link["factor_score"]
            base_description += f" — vinculado ao fator de raciocínio '{factor_name}' (score: {factor_score:.2f})"

        return base_description

    def _get_qualitative_level(self, feature_name: str, value: float) -> str:
        """
        Converte valor numérico em descrição qualitativa.

        Args:
            feature_name: Nome da feature
            value: Valor numérico

        Returns:
            Descrição qualitativa
        """
        # Features com range 0-1 (scores, weights)
        if (
            "score" in feature_name
            or "weight" in feature_name
            or "density" in feature_name
        ):
            if value >= 0.8:
                return "muito alta"
            elif value >= 0.6:
                return "alta"
            elif value >= 0.4:
                return "moderada"
            elif value >= 0.2:
                return "baixa"
            else:
                return "muito baixa"

        # Features de contagem/quantidade
        if "num_" in feature_name or "count" in feature_name:
            if value >= 10:
                return "elevado"
            elif value >= 5:
                return "moderado"
            else:
                return "baixo"

        # Complexidade e acoplamento
        if "complexity" in feature_name or "coupling" in feature_name:
            if value >= 2.0:
                return "muito alta"
            elif value >= 1.5:
                return "alta"
            elif value >= 1.0:
                return "moderada"
            else:
                return "baixa"

        # Default
        return f"{value:.2f}"

    def _format_time_if_needed(self, feature_name: str, value: float) -> str:
        """
        Formata valores de tempo em formato legível.

        Args:
            feature_name: Nome da feature
            value: Valor em milissegundos

        Returns:
            String formatada ou vazia
        """
        if "_duration_ms" not in feature_name:
            return ""

        # Converter milissegundos para formato legível
        ms = value
        if ms < 1000:
            return f"{ms:.0f}ms"
        elif ms < 60000:
            return f"{ms/1000:.1f}s"
        elif ms < 3600000:
            return f"{ms/60000:.1f}min"
        else:
            return f"{ms/3600000:.1f}h"

    def _interpret_confidence(self, total_importance: float) -> str:
        """
        Interpreta score total de importância em nível de confiança.

        Args:
            total_importance: Soma das importâncias absolutas

        Returns:
            Nível de confiança textual
        """
        if total_importance >= 2.0:
            return "muito alto"
        elif total_importance >= 1.0:
            return "alto"
        elif total_importance >= 0.5:
            return "moderado"
        else:
            return "limitado"

    def generate_summary(
        self, feature_importances: List[Dict[str, Any]], explanation_type: str = "shap"
    ) -> str:
        """
        Gera resumo executivo de uma linha.

        Args:
            feature_importances: Lista de importâncias
            explanation_type: Tipo de explicação

        Returns:
            String com resumo executivo
        """
        if not feature_importances:
            return "Sem explicação disponível."

        # Pegar feature mais importante
        top_feature = feature_importances[0]
        feature_name = top_feature["feature_name"]

        # Determinar se é positivo ou negativo
        contribution = top_feature["contribution"]

        # Gerar descrição curta
        template = self.feature_templates.get(feature_name, "{name}")
        value = top_feature.get("feature_value", 0.0)
        level = self._get_qualitative_level(feature_name, value)

        description = template.format(
            value=value,
            level=level,
            formatted_time=self._format_time_if_needed(feature_name, value),
            name=feature_name,
        )

        if contribution == "positive":
            return f"Decisão influenciada principalmente porque {description}."
        else:
            return f"Decisão afetada negativamente porque {description}."
