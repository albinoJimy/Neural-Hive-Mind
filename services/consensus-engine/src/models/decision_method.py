"""
Modelo de metodo de decisao do especialista (GAPS-03 SPECIALIST-002).

Define como um especialista chegou a sua decisao: ML, heuristica ou hibrido.
Permite auditoria e analise da composicao das decisoes do consenso.
"""

from enum import Enum
from typing import Any


class DecisionMethod(str, Enum):
    """Metodo de decisao utilizado pelo especialista.

    - ML: Decisao baseada em modelos de Machine Learning
    - HEURISTIC: Decisao baseada em regras/heuristicas
    - HYBRID: Combinacao de ML e heuristica
    """

    ML = "ml"
    HEURISTIC = "heuristic"
    HYBRID = "hybrid"


def infer_decision_method(opinion: dict[str, Any]) -> DecisionMethod:
    """Infere o metodo de decisao baseado nos campos da opiniao.

    Args:
        opinion: Dicionario contendo a opiniao do especialista com campos
                 como 'ml_confidence', 'model_version', 'heuristic_confidence', etc.

    Returns:
        DecisionMethod: Metodo inferido (ML, HEURISTIC ou HYBRID)

    Examples:
        >>> infer_decision_method({"ml_confidence": 0.8})
        <DecisionMethod.ML: 'ml'>

        >>> infer_decision_method({"heuristic_confidence": 0.7})
        <DecisionMethod.HEURISTIC: 'heuristic'>

        >>> infer_decision_method({"ml_confidence": 0.8, "heuristic_confidence": 0.7})
        <DecisionMethod.HYBRID: 'hybrid'>

        >>> infer_decision_method({"confidence_score": 0.5})
        <DecisionMethod.HEURISTIC: 'heuristic'>
    """
    if not opinion or not isinstance(opinion, dict):
        return DecisionMethod.HEURISTIC

    # Campos que indicam uso de ML
    ml_indicators = [
        "ml_confidence",
        "model_version",
        "ml_model_id",
        "ml_model_name",
        "ml_prediction",
        "ml_probability",
        "ml_features",
        "inference_result",
    ]

    # Campos que indicam uso de heuristica
    heuristic_indicators = [
        "heuristic_confidence",
        "rule_id",
        "rule_name",
        "heuristic_score",
        "rule_based_decision",
        "heuristic_result",
    ]

    has_ml_fields = any(field in opinion for field in ml_indicators)
    has_heuristic_fields = any(field in opinion for field in heuristic_indicators)

    if has_ml_fields and has_heuristic_fields:
        return DecisionMethod.HYBRID
    if has_ml_fields:
        return DecisionMethod.ML
    # Padrao: heuristica (fallback seguro para auditoria)
    return DecisionMethod.HEURISTIC


def get_method_description(method: DecisionMethod) -> str:
    """Retorna descricao legivel do metodo de decisao.

    Args:
        method: Metodo de decisao

    Returns:
        Descricao em portugues do metodo
    """
    descriptions = {
        DecisionMethod.ML: "Decisao baseada em modelo de Machine Learning",
        DecisionMethod.HEURISTIC: "Decisao baseada em regras/heuristicas",
        DecisionMethod.HYBRID: "Decisao combinada (ML + heuristica)",
    }
    return descriptions.get(method, "Metodo desconhecido")
