#!/usr/bin/env python3
"""
Script de Retraining v8 - Approval Model com Active Learning

Este script treina o modelo ML de aprovação usando feedbacks coletados
via Active Learning (balanced_dataset=True), resultando em um dataset
mais balanceado e melhor qualidade preditiva.

Versão: v8
Features: 30+ incluindo NLP + Active Learning metadata
Data: 2026-03-17
"""

import os
import sys
import pickle
import json
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from pymongo import MongoClient
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import (
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    confusion_matrix,
)
import warnings

warnings.filterwarnings("ignore")

# Configuração MongoDB
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin",
)
DATABASE = os.getenv("MONGODB_DATABASE", "neural_hive")
MODEL_OUTPUT_DIR = Path(
    os.getenv("MODEL_OUTPUT_DIR", Path(__file__).parent.parent.parent / "ml_models")
)
MODEL_VERSION = "v8"


def extract_nlp_features(nlp_dict):
    """Extrai features do dicionário nlp_features para dataframe"""
    if not nlp_dict or not isinstance(nlp_dict, dict):
        return {}

    features = {}

    # Domínios
    features["domain_security"] = float(nlp_dict.get("domain_security", 0.0))
    features["domain_performance"] = float(nlp_dict.get("domain_performance", 0.0))
    features["domain_database"] = float(nlp_dict.get("domain_database", 0.0))
    features["domain_devops"] = float(nlp_dict.get("domain_devops", 0.0))
    features["domain_testing"] = float(nlp_dict.get("domain_testing", 0.0))

    # Ações
    features["action_create"] = float(nlp_dict.get("action_create", 0.0))
    features["action_update"] = float(nlp_dict.get("action_update", 0.0))
    features["action_delete"] = float(nlp_dict.get("action_delete", 0.0))
    features["action_read"] = float(nlp_dict.get("action_read", 0.0))
    features["action_deploy"] = float(nlp_dict.get("action_deploy", 0.0))

    # Palavras-chave
    features["has_backup"] = float(nlp_dict.get("has_backup", 0.0))
    features["has_verification"] = float(nlp_dict.get("has_verification", 0.0))
    features["has_all"] = float(nlp_dict.get("has_all", 0.0))

    # Métricas de texto
    features["text_length_chars"] = int(nlp_dict.get("text_length_chars", 0))
    features["text_length_words"] = int(nlp_dict.get("text_length_words", 0))

    # Risco
    features["risk_high"] = float(nlp_dict.get("risk_high", 0.0))
    features["risk_medium"] = float(nlp_dict.get("risk_medium", 0.0))
    features["risk_low"] = float(nlp_dict.get("risk_low", 0.0))
    features["simple_risk_score"] = float(nlp_dict.get("simple_risk_score", 0.0))

    # Domínio e ação primários
    primary_domain = nlp_dict.get("primary_domain", "")
    for domain in ["security", "performance", "database", "devops", "testing"]:
        features[f"primary_domain_{domain}"] = 1.0 if primary_domain == domain else 0.0

    primary_action = nlp_dict.get("primary_action", "")
    for action in ["create", "update", "delete", "read", "deploy"]:
        features[f"primary_action_{action}"] = 1.0 if primary_action == action else 0.0

    return features


def load_feedback_data(
    min_samples: int = 20, balanced_only: bool = True, include_unlabeled: bool = False
):
    """
    Carrega feedbacks do MongoDB com NLP features.

    Args:
        min_samples: Amostras mínimas exigidas
        balanced_only: Se True, filtra apenas balanced_dataset=True
        include_unlabeled: Se True, inclui feedbacks sem balanced_dataset marcado
    """
    print("Carregando feedbacks do MongoDB...")

    client = MongoClient(MONGO_URI)
    db = client[DATABASE]

    # Query base para feedbacks com NLP features
    query = {
        "nlp_features": {"$exists": True, "$ne": {}},
        "final_decision": {"$exists": True, "$ne": None, "$ne": ""},
    }

    if balanced_only:
        query["balanced_dataset"] = True
        print("Filtro: balanced_dataset=True (Active Learning)")
    elif not include_unlabeled:
        # Se não for balanced_only, inclui ambos
        print("Filtro: todos os feedbacks com NLP features")

    cursor = db["specialist_feedback"].find(query)

    feedbacks = list(cursor)
    print(f"Encontrados: {len(feedbacks)} feedbacks válidos")

    # Estatísticas de balanceamento
    if feedbacks:
        balanced_count = sum(1 for f in feedbacks if f.get("balanced_dataset"))
        auto_count = len(feedbacks) - balanced_count
        print(f"  Balanceados (AL): {balanced_count}")
        print(f"  Automáticos: {auto_count}")

        # Distribuição por classe
        class_dist = {}
        for fb in feedbacks:
            decision = fb.get("final_decision", "unknown")
            class_dist[decision] = class_dist.get(decision, 0) + 1
        print(f"  Distribuição de classes:")
        for decision, count in sorted(class_dist.items()):
            pct = count / len(feedbacks) * 100
            print(f"    {decision}: {count} ({pct:.1f}%)")

    if len(feedbacks) < min_samples:
        raise ValueError(f"Amostras insuficientes: {len(feedbacks)} < {min_samples}")

    return feedbacks


def prepare_dataframe(feedbacks):
    """Prepara dataframe para treinamento"""
    print("\nPreparando dataframe...")

    data = []
    for fb in feedbacks:
        nlp_features = extract_nlp_features(fb.get("nlp_features", {}))

        # Features adicionais do Active Learning
        information_value = fb.get("information_value", 0.5)

        row = {
            "final_decision": fb.get("final_decision"),
            "specialist_confidence": float(fb.get("confidence_score", 0.5)),
            "human_rating": float(fb.get("human_rating", 0.5)),
            "information_value": float(information_value),
            "from_active_learning": 1.0 if fb.get("balanced_dataset") else 0.0,
            **nlp_features,
        }
        data.append(row)

    df = pd.DataFrame(data)

    print(f"Dataframe shape: {df.shape}")
    print(f"Features totais: {len(df.columns) - 1}")  # -1 para final_decision

    return df


def train_model(X_train, y_train, model_type: str = "random_forest"):
    """
    Treina o modelo especificado.

    Args:
        X_train: Features de treino
        y_train: Target de treino
        model_type: 'random_forest' ou 'gradient_boosting'
    """
    if model_type == "gradient_boosting":
        model = GradientBoostingClassifier(
            n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42, min_samples_leaf=2
        )
    else:
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            class_weight="balanced",
            min_samples_leaf=2,
        )

    model.fit(X_train, y_train)
    return model


def evaluate_model(model, X_test, y_test, feature_cols):
    """Avalia o modelo e retorna métricas detalhadas"""
    y_pred = model.predict(X_test)

    # Métricas gerais
    f1 = f1_score(y_test, y_pred, average="weighted")
    precision = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    recall = recall_score(y_test, y_pred, average="weighted", zero_division=0)

    # Métricas por classe
    report = classification_report(y_test, y_pred, zero_division=0)

    # Matriz de confusão
    cm = confusion_matrix(y_test, y_pred, labels=model.classes_)

    # Feature importances
    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1]

    return {
        "f1_score": f1,
        "precision": precision,
        "recall": recall,
        "classification_report": report,
        "confusion_matrix": cm,
        "feature_importances": {
            "features": [feature_cols[i] for i in indices],
            "values": importances[indices].tolist(),
        },
    }


def train_and_save_model(df, version: str, model_type: str = "random_forest"):
    """Treina o modelo e salva em disco"""
    print()
    print("=" * 60)
    print(f"TREINANDO MODELO ({model_type})")
    print("=" * 60)

    # Separar features e target
    feature_cols = [col for col in df.columns if col != "final_decision"]
    X = df[feature_cols].fillna(0)
    y = df["final_decision"]

    # Dividir em treino e teste
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    print(f"\nConjunto de treino: {X_train.shape}")
    print(f"Conjunto de teste: {X_test.shape}")

    # Distribuição no treino
    print(f"\nDistribuição no treino:")
    for decision, count in y_train.value_counts().items():
        print(f"  {decision}: {count}")

    # Treinar
    model = train_model(X_train, y_train, model_type)

    # Avaliar
    metrics = evaluate_model(model, X_test, y_test, feature_cols)

    print(f"\nMétricas no conjunto de teste:")
    print(f"  F1-Score: {metrics['f1_score']:.4f}")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  Recall: {metrics['recall']:.4f}")

    print(f"\nRelatório por classe:")
    print(metrics["classification_report"])

    print(f"\nTop 10 Features:")
    for i, (feat, imp) in enumerate(
        zip(
            metrics["feature_importances"]["features"][:10],
            metrics["feature_importances"]["values"][:10],
        )
    ):
        print(f"  {i+1}. {feat}: {imp:.4f}")

    # Salvar modelo
    MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_OUTPUT_DIR / f"nhm_approval_model_{version}.pkl"

    model_data = {
        "model": model,
        "version": version,
        "model_type": model_type,
        "trained_at": datetime.now().isoformat(),
        "features": feature_cols,
        "metrics": {
            "f1_score": metrics["f1_score"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
        },
        "training_samples": len(df),
        "class_distribution": y_train.value_counts().to_dict(),
        "feature_importances": metrics["feature_importances"],
    }

    with open(model_path, "wb") as f:
        pickle.dump(model_data, f)

    print(f"\nModelo salvo em: {model_path}")

    # Salvar metadata no MongoDB
    client = MongoClient(MONGO_URI)
    db = client[DATABASE]

    db["model_metadata"].update_one(
        {"type": "approval_model", "version": version},
        {
            "$set": {
                "type": "approval_model",
                "version": version,
                "model_type": model_type,
                "trained_at": datetime.now().isoformat(),
                "features": feature_cols,
                "metrics": {
                    "f1_score": metrics["f1_score"],
                    "precision": metrics["precision"],
                    "recall": metrics["recall"],
                },
                "training_samples": len(df),
                "class_distribution": y_train.value_counts().to_dict(),
                "balanced_dataset_used": True,
            }
        },
        upsert=True,
    )

    print(f"Metadata salvo no MongoDB")

    return model_data


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Retraining do Approval Model v8 (Active Learning)"
    )
    parser.add_argument(
        "--min-samples", type=int, default=10, help="Amostras mínimas (default: 10)"
    )
    parser.add_argument(
        "--model-type",
        type=str,
        default="random_forest",
        choices=["random_forest", "gradient_boosting"],
        help="Tipo de modelo (default: random_forest)",
    )
    parser.add_argument(
        "--balanced-only",
        action="store_true",
        default=True,
        help="Usar apenas balanced_dataset=True (default: True)",
    )
    parser.add_argument(
        "--all-data", action="store_true", help="Usar todos os dados, ignorando filtro balanced"
    )
    parser.add_argument("--dry-run", action="store_true", help="Apenas verificar dados")
    args = parser.parse_args()

    print("=" * 60)
    print("RETRAINING APPROVAL MODEL V8 (ACTIVE LEARNING)")
    print("=" * 60)
    print(f"Data: {datetime.now().isoformat()}")
    print()

    try:
        # Carregar dados
        balanced_only = args.balanced_only and not args.all_data
        feedbacks = load_feedback_data(args.min_samples, balanced_only=balanced_only)
        df = prepare_dataframe(feedbacks)

        if args.dry_run:
            print("\nDRY RUN - Dados válidos para treinamento")
            print(f"Amostras disponíveis: {len(df)}")
            return 0

        # Treinar e salvar
        model_data = train_and_save_model(df, MODEL_VERSION, args.model_type)

        print()
        print("=" * 60)
        print("RETRAINING CONCLUIDO")
        print("=" * 60)
        print(f"Versão: {MODEL_VERSION}")
        print(f"Modelo: {args.model_type}")
        print(f"F1-Score: {model_data['metrics']['f1_score']:.4f}")
        print(f"Amostras: {model_data['training_samples']}")
        print(f"Dataset balanceado: SIM")
        print()
        print("Para fazer deploy:")
        print(f"  1. Atualizar Dockerfile para copiar nhm_approval_model_{MODEL_VERSION}.pkl")
        print("  2. Commit e push para acionar CI/CD")

        return 0

    except ValueError as e:
        print(f"\nERRO: {e}")
        return 1
    except Exception as e:
        print(f"\nERRO: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
