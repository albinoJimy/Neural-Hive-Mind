"""
Approval Predictor - Carrega e usa o modelo v6 para predições de aprovação

Este módulo fornece uma interface para carregar o modelo ML treinado
e fazer predições sobre aprovação de planos cognitivos.

Usage:
    from ml_pipelines.inference.approval_predictor import ApprovalPredictor

    predictor = ApprovalPredictor()
    result = predictor.predict_from_text("Create new user with email verification")
    print(result['decision'])  # approve, reject, review_required
    print(result['confidence'])  # 0.0 - 1.0
"""

import os
import pickle
from typing import Dict, Any, List, Optional
from pathlib import Path
import re


class ApprovalPredictor:
    """
    Predictor para aprovação de planos usando modelo ML com NLP features.

    Versões disponíveis:
    - v6: 50 amostras, F1-Score 1.0000 (possível overfit)
    - v7: 75 amostras, F1-Score 0.9120 (melhor generalização)

    O predictor carrega automaticamente o modelo mais recente disponível.
    """

    MODEL_PATH = Path(__file__).parent.parent.parent / "ml_models" / "nhm_approval_model.pkl"

    def __init__(self, model_path: Optional[Path] = None):
        """
        Inicializa o predictor carregando o modelo.

        Args:
            model_path: Caminho alternativo para o arquivo do modelo
        """
        self.model_path = model_path or self.MODEL_PATH
        self.model_data = None
        self.model = None
        self._load_model()

    def _load_model(self) -> None:
        """Carrega o modelo do arquivo pickle."""
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Modelo não encontrado em {self.model_path}. " "Execute o treinamento primeiro."
            )

        with open(self.model_path, "rb") as f:
            self.model_data = pickle.load(f)
            self.model = self.model_data["model"]

    def extract_nlp_features(self, text: str) -> Dict[str, float]:
        """
        Extrai features NLP do texto da intenção.

        Args:
            text: Texto da intenção

        Returns:
            Dicionário com 30 features NLP
        """
        if not text:
            return {}

        # Domínios
        domain_keywords = {
            "security": r"\b(security|ssl|tls|authentication|authorization|password|login)\b",
            "performance": r"\b(performance|optimize|index|cache|speed|latency|query)\b",
            "database": r"\b(database|db|sql|mongo|query|table|schema|migration)\b",
            "devops": r"\b(deploy|container|docker|kubernetes|ci/cd|pipeline|build)\b",
            "testing": r"\b(test|testing|unit|integration|e2e|coverage)\b",
        }

        domains = {}
        for domain, pattern in domain_keywords.items():
            domains[f"domain_{domain}"] = 1.0 if re.search(pattern, text, re.I) else 0.0

        # Ações
        action_keywords = {
            "create": r"\b(create|add|insert|new|make)\b",
            "update": r"\b(update|modify|change|edit|alter)\b",
            "delete": r"\b(delete|drop|remove|destroy|clean)\b",
            "read": r"\b(get|fetch|select|read|query|find)\b",
            "deploy": r"\b(deploy|release|publish|ship)\b",
        }

        actions = {}
        for action, pattern in action_keywords.items():
            actions[f"action_{action}"] = 1.0 if re.search(pattern, text, re.I) else 0.0

        # Palavras-chave de risco
        features = {
            "has_backup": (
                1.0 if re.search(r"\bbackup|save|preserve|restore\b", text, re.I) else 0.0
            ),
            "has_verification": (
                1.0 if re.search(r"\bverify|validation|check|confirm|test\b", text, re.I) else 0.0
            ),
            "has_all": (
                1.0 if re.search(r"\ball\b.*\b(users|records|data|tables)\b", text, re.I) else 0.0
            ),
            # Métricas de texto
            "text_length_chars": len(text),
            "text_length_words": len(text.split()),
            # Risco
            "risk_high": (
                1.0 if re.search(r"\b(delete|drop|destroy|remove|disable)\b", text, re.I) else 0.0
            ),
            "risk_medium": (
                1.0 if re.search(r"\b(update|change|modify|alter)\b", text, re.I) else 0.0
            ),
            "risk_low": (
                1.0 if re.search(r"\b(create|add|verify|check|test|backup)\b", text, re.I) else 0.0
            ),
        }

        # Score de risco simples
        dangerous_keywords = ["delete", "drop", "destroy", "remove", "disable", "without", "all"]
        dangerous_count = sum(1 for kw in dangerous_keywords if kw in text.lower())
        features["simple_risk_score"] = min(1.0, dangerous_count * 0.3)

        # Domínio primário
        domain_scores = {k.replace("domain_", ""): v for k, v in domains.items()}
        primary_domain = max(domain_scores, key=domain_scores.get) if domain_scores else ""
        for domain in ["security", "performance", "database", "devops", "testing"]:
            features[f"primary_domain_{domain}"] = 1.0 if primary_domain == domain else 0.0

        # Ação primária
        action_scores = {k.replace("action_", ""): v for k, v in actions.items()}
        primary_action = max(action_scores, key=action_scores.get) if action_scores else ""
        for action in ["create", "update", "delete", "read", "deploy"]:
            features[f"primary_action_{action}"] = 1.0 if primary_action == action else 0.0

        # Combinar todas as features
        return {**domains, **actions, **features}

    def predict_from_text(self, text: str, specialist_confidence: float = 0.5) -> Dict[str, Any]:
        """
        Faz predição a partir do texto da intenção.

        Args:
            text: Texto da intenção
            specialist_confidence: Confiança do especialista (0.0-1.0)

        Returns:
            Dicionário com:
                - decision: 'approve', 'reject', ou 'review_required'
                - confidence: Confiança da predição (0.0-1.0)
                - probabilities: Probabilidades para cada classe
        """
        if not self.model:
            raise RuntimeError("Modelo não carregado")

        # Extrair features NLP
        nlp_features = self.extract_nlp_features(text)

        # Preparar features na ordem correta
        feature_order = [
            "specialist_confidence",
            "domain_security",
            "domain_performance",
            "domain_database",
            "domain_devops",
            "domain_testing",
            "action_create",
            "action_update",
            "action_delete",
            "action_read",
            "action_deploy",
            "has_backup",
            "has_verification",
            "has_all",
            "text_length_chars",
            "text_length_words",
            "risk_high",
            "risk_medium",
            "risk_low",
            "simple_risk_score",
            "primary_domain_security",
            "primary_domain_performance",
            "primary_domain_database",
            "primary_domain_devops",
            "primary_domain_testing",
            "primary_action_create",
            "primary_action_update",
            "primary_action_delete",
            "primary_action_read",
            "primary_action_deploy",
        ]

        features = [[nlp_features.get(f, 0.0) for f in feature_order]]
        features[0][0] = specialist_confidence  # Override specialist_confidence

        # Predizer
        decision = self.model.predict(features)[0]

        # Obter probabilidades se disponível
        probabilities = {}
        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba(features)[0]
            for cls, prob in zip(self.model.classes_, probs):
                probabilities[cls] = float(prob)
            confidence = max(probs)
        else:
            confidence = 0.5

        return {
            "decision": decision,
            "confidence": confidence,
            "probabilities": probabilities,
            "model_version": self.model_data.get("version", "unknown"),
        }

    def predict_from_nlp_features(
        self, nlp_features: Dict[str, float], specialist_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        Faz predição a partir de features NLP já extraídas.

        Args:
            nlp_features: Dicionário com features NLP
            specialist_confidence: Confiança do especialista (0.0-1.0)

        Returns:
            Dicionário com decision, confidence, probabilities
        """
        if not self.model:
            raise RuntimeError("Modelo não carregado")

        feature_order = [
            "specialist_confidence",
            "domain_security",
            "domain_performance",
            "domain_database",
            "domain_devops",
            "domain_testing",
            "action_create",
            "action_update",
            "action_delete",
            "action_read",
            "action_deploy",
            "has_backup",
            "has_verification",
            "has_all",
            "text_length_chars",
            "text_length_words",
            "risk_high",
            "risk_medium",
            "risk_low",
            "simple_risk_score",
            "primary_domain_security",
            "primary_domain_performance",
            "primary_domain_database",
            "primary_domain_devops",
            "primary_domain_testing",
            "primary_action_create",
            "primary_action_update",
            "primary_action_delete",
            "primary_action_read",
            "primary_action_deploy",
        ]

        features = [[nlp_features.get(f, 0.0) for f in feature_order]]
        features[0][0] = specialist_confidence

        decision = self.model.predict(features)[0]

        probabilities = {}
        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba(features)[0]
            for cls, prob in zip(self.model.classes_, probs):
                probabilities[cls] = float(prob)
            confidence = max(probs)
        else:
            confidence = 0.5

        return {
            "decision": decision,
            "confidence": confidence,
            "probabilities": probabilities,
            "model_version": self.model_data.get("version", "unknown"),
        }

    def get_model_info(self) -> Dict[str, Any]:
        """Retorna informações sobre o modelo carregado."""
        if not self.model_data:
            return {}

        return {
            "version": self.model_data.get("version"),
            "trained_at": self.model_data.get("trained_at"),
            "features": self.model_data.get("features", []),
            "metrics": self.model_data.get("metrics", {}),
            "training_samples": self.model_data.get("training_samples"),
        }


# Singleton para uso na aplicação
_predictor_instance: Optional[ApprovalPredictor] = None


def get_predictor() -> ApprovalPredictor:
    """Retorna instância singleton do predictor."""
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = ApprovalPredictor()
    return _predictor_instance


if __name__ == "__main__":
    # Teste do predictor
    predictor = ApprovalPredictor()

    print("=" * 60)
    print("Approval Predictor v6 - Teste")
    print("=" * 60)
    print()

    test_intentions = [
        "Create new user with email verification and password hashing",
        "Delete all records from users table without backup",
        "Add index to email column for query performance",
        "Remove SSL certificate validation to speed up requests",
        "Enable two-factor authentication for all users",
    ]

    for text in test_intentions:
        result = predictor.predict_from_text(text)
        print(f"Text: {text[:50]}...")
        print(f"  Decision: {result['decision']}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print()
