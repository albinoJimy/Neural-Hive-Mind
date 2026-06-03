#!/usr/bin/env python3
"""
Exemplo de uso do NLPFeatureExtractor para enriquecer feedbacks.

Este script demonstra como extrair features NLP do texto da intenção
e usá-las para melhorar a precisão dos modelos ML.
"""

import sys
from pathlib import Path

# Adicionar path para imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from feature_extraction.nlp_feature_extractor import NLPFeatureExtractor


def main():
    """Demonstra extração de features NLP."""
    extractor = NLPFeatureExtractor(enable_sentiment=True)

    print("=" * 60)
    print("EXEMPLO: Extração de Features NLP de Intenções")
    print("=" * 60)
    print()

    # Exemplo 1: Intenção de segurança
    intent1 = "Fix authentication bug - users cannot login with JWT tokens"
    print(f"Intenção 1: {intent1}")
    print()

    features1 = extractor.extract_features(intent1)
    print("Features extraídas:")
    print("  Domínios:")
    print(f"    security: {features1['domain_security']}")
    print(f"    performance: {features1['domain_performance']}")
    print(f"    primary_domain: {features1['primary_domain']}")
    print("  Ações:")
    print(f"    create: {features1['action_create']}")
    print(f"    update: {features1['action_update']}")
    print(f"    primary_action: {features1['primary_action']}")
    print()

    # Exemplo 2: Intenção de performance
    intent2 = "Optimize slow database query causing API timeout, add cache and indexes"
    print(f"Intenção 2: {intent2}")
    print()

    features2 = extractor.extract_features(intent2)
    print("Features extraídas:")
    print("  Domínios:")
    print(f"    performance: {features2['domain_performance']}")
    print(f"    database: {features2['domain_database']}")
    print(f"    primary_domain: {features2['primary_domain']}")
    print("  Sentimento:")
    print(f"    negative: {features2['sentiment_negative']}")
    print(f"    urgency_high: {features2['urgency_high']}")
    print()

    # Exemplo 3: Intenção composta (devops)
    intent3 = """
    Deploy microservice to kubernetes using docker and helm charts.
    Set up CI/CD pipeline with github actions for automated testing.
    Configure ingress with SSL/TLS encryption.
    """
    print("Intenção 3: DevOps Deployment")
    print()

    features3 = extractor.extract_features(intent3)
    print("Features extraídas:")
    print("  Domínios:")
    print(f"    devops: {features3['domain_devops']}")
    print(f"    security: {features3['domain_security']}")
    print(f"    primary_domain: {features3['primary_domain']}")
    print("  Ações:")
    print(f"    deploy: {features3['action_deploy']}")
    print(f"    primary_action: {features3['primary_action']}")
    print("  Padrões técnicos:")
    print(f"    has_url: {features3['has_url']}")
    print(f"    technical_patterns_count: {features3['technical_patterns_count']}")
    print()

    # Exemplo de como usar no feedback
    print("=" * 60)
    print("COMO USAR NO FEEDBACK")
    print("=" * 60)
    print()

    print(
        """
from feedback.feedback_collector import FeedbackCollector
from feature_extraction.nlp_feature_extractor import get_nlp_extractor

collector = FeedbackCollector(config)
nlp = get_nlp_extractor()

# Coletar feedback com features NLP
feedback_data = {
    "opinion_id": "123",
    "human_recommendation": "approve",
    "human_rating": 0.9,
    "submitted_by": "user@example.com",
    "intent_raw_text": intent1,  # Importante: texto da intenção
}

# Enriquecer com features NLP
feedback_data = collector.enrich_with_nlp_features(
    feedback_data,
    intent_text=intent1
)

# Salvar feedback
feedback_id = collector.submit_feedback(feedback_data)
print(f"Feedback salvo: {feedback_id}")
print(f"NLP features: {feedback_data.get('nlp_features', {})}")
    """
    )

    print("=" * 60)
    print(f"Total de features extraídas: {len(extractor.get_feature_names())}")
    print("=" * 60)


if __name__ == "__main__":
    main()
