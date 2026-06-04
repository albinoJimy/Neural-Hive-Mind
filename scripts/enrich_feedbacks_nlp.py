#!/usr/bin/env python3
"""
Script simplificado para enriquecer feedbacks com features NLP básicas
Sem dependências complexas (networkx, etc.)
"""

import re
from datetime import datetime, timezone


def extract_basic_nlp_features(text):
    """Extrai features NLP básicas do texto"""
    if not text:
        return {}

    features = {
        # Domínios
        "domain_security": (
            1.0
            if re.search(
                r"\b(security|ssl|tls|authentication|authorization|password|login)\b", text, re.I
            )
            else 0.0
        ),
        "domain_performance": (
            1.0
            if re.search(r"\b(performance|optimize|index|cache|speed|latency|query)\b", text, re.I)
            else 0.0
        ),
        "domain_database": (
            1.0
            if re.search(r"\b(database|db|sql|mongo|query|table|schema|migration)\b", text, re.I)
            else 0.0
        ),
        "domain_devops": (
            1.0
            if re.search(
                r"\b(deploy|container|docker|kubernetes|ci/cd|pipeline|build)\b", text, re.I
            )
            else 0.0
        ),
        "domain_testing": (
            1.0
            if re.search(r"\b(test|testing|unit|integration|e2e|coverage)\b", text, re.I)
            else 0.0
        ),
        # Ações
        "action_create": 1.0 if re.search(r"\b(create|add|insert|new|make)\b", text, re.I) else 0.0,
        "action_update": (
            1.0 if re.search(r"\b(update|modify|change|edit|alter)\b", text, re.I) else 0.0
        ),
        "action_delete": (
            1.0 if re.search(r"\b(delete|drop|remove|destroy|clean)\b", text, re.I) else 0.0
        ),
        "action_read": (
            1.0 if re.search(r"\b(get|fetch|select|read|query|find)\b", text, re.I) else 0.0
        ),
        "action_deploy": (
            1.0 if re.search(r"\b(deploy|release|publish|ship)\b", text, re.I) else 0.0
        ),
        # Palavras-chave de risco
        "has_backup": 1.0 if re.search(r"\bbackup|save|preserve|restore\b", text, re.I) else 0.0,
        "has_verification": (
            1.0 if re.search(r"\bverify|validation|check|confirm|test\b", text, re.I) else 0.0
        ),
        "has_all": (
            1.0 if re.search(r"\ball\b.*\b(users|records|data|tables)\b", text, re.I) else 0.0
        ),
        # Métricas de texto
        "text_length_chars": len(text),
        "text_length_words": len(text.split()),
        "has_number": 1.0 if re.search(r"\d+", text) else 0.0,
        # Sentimento/risco simples baseado em palavras
        "risk_high": (
            1.0 if re.search(r"\b(delete|drop|destroy|remove|disable)\b", text, re.I) else 0.0
        ),
        "risk_medium": 1.0 if re.search(r"\b(update|change|modify|alter)\b", text, re.I) else 0.0,
        "risk_low": (
            1.0 if re.search(r"\b(create|add|verify|check|test|backup)\b", text, re.I) else 0.0
        ),
    }

    # Determinar domínio primário
    domain_scores = {
        "security": features["domain_security"],
        "performance": features["domain_performance"],
        "database": features["domain_database"],
        "devops": features["domain_devops"],
        "testing": features["domain_testing"],
    }
    primary_domain = max(domain_scores, key=domain_scores.get)
    features["primary_domain"] = primary_domain

    # Determinar ação primária
    action_scores = {
        "create": features["action_create"],
        "update": features["action_update"],
        "delete": features["action_delete"],
        "read": features["action_read"],
        "deploy": features["action_deploy"],
    }
    primary_action = max(action_scores, key=action_scores.get)
    features["primary_action"] = primary_action

    # Score de risco simples (baseado em palavras perigosas)
    dangerous_keywords = ["delete", "drop", "destroy", "remove", "disable", "without", "all"]
    dangerous_count = sum(1 for kw in dangerous_keywords if kw in text.lower())
    features["simple_risk_score"] = min(1.0, dangerous_count * 0.3)

    return features


if __name__ == "__main__":
    import sys
    from pymongo import MongoClient

    # Conectar ao MongoDB
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Modo teste
        test_texts = [
            "Create new user with email verification",
            "Delete all records from users table",
            "Add index to email column",
            "Remove SSL validation",
        ]
        for text in test_texts:
            feats = extract_basic_nlp_features(text)
            print(f"Text: {text}")
            print(f"  Primary: {feats['primary_domain']} / {feats['primary_action']}")
            print(f"  Risk: {feats['simple_risk_score']:.2f}")
            print()
    else:
        # Modo produção - enriquecer feedbacks
        client = MongoClient(
            "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin"
        )
        db = client["neural_hive"]

        # Buscar feedbacks sem NLP features
        feedbacks = list(
            db["specialist_feedback"].find(
                {
                    "intent_raw_text": {"$exists": True, "$ne": None},
                    "nlp_features": {"$exists": False},
                }
            )
        )

        print(f"Found {len(feedbacks)} feedbacks to enrich")

        enriched = 0
        for feedback in feedbacks:
            try:
                text = feedback.get("intent_raw_text", "")
                nlp_features = extract_basic_nlp_features(text)

                db["specialist_feedback"].update_one(
                    {"feedback_id": feedback["feedback_id"]},
                    {
                        "$set": {
                            "nlp_features": nlp_features,
                            "enriched_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )
                enriched += 1
                print(
                    f"{enriched}. {feedback['feedback_id'][:8]}... | {nlp_features['primary_domain']}/{nlp_features['primary_action']} | risk={nlp_features['simple_risk_score']:.2f}"
                )
            except Exception as e:
                print(f"Error: {e}")

        print("")
        print(f"Enriched: {enriched}/{len(feedbacks)}")
