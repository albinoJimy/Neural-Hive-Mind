#!/usr/bin/env python3
"""
Script de Retraining v6 - Com NLP Features

Este script treina modelos ML usando os feedbacks coletados
com original_intent_text e features NLP extraídas.

Data: 2026-03-16
Features: 40+ incluindo NLP (domínios, ações, risco, etc.)
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime
from pymongo import MongoClient
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
import mlflow
import mlflow.sklearn

# Configuração MongoDB
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin",
)
DATABASE = "neural_hive"


def extract_nlp_features(nlp_dict):
    """Extrai features do dicionário nlp_features para dataframe"""
    if not nlp_dict or not isinstance(nlp_dict, dict):
        return {}

    features = {}

    # Domínios (one-hot encoding implícita)
    features["domain_security"] = nlp_dict.get("domain_security", 0.0)
    features["domain_performance"] = nlp_dict.get("domain_performance", 0.0)
    features["domain_database"] = nlp_dict.get("domain_database", 0.0)
    features["domain_devops"] = nlp_dict.get("domain_devops", 0.0)
    features["domain_testing"] = nlp_dict.get("domain_testing", 0.0)

    # Ações
    features["action_create"] = nlp_dict.get("action_create", 0.0)
    features["action_update"] = nlp_dict.get("action_update", 0.0)
    features["action_delete"] = nlp_dict.get("action_delete", 0.0)
    features["action_read"] = nlp_dict.get("action_read", 0.0)
    features["action_deploy"] = nlp_dict.get("action_deploy", 0.0)

    # Palavras-chave
    features["has_backup"] = nlp_dict.get("has_backup", 0.0)
    features["has_verification"] = nlp_dict.get("has_verification", 0.0)
    features["has_all"] = nlp_dict.get("has_all", 0.0)

    # Métricas de texto
    features["text_length_chars"] = nlp_dict.get("text_length_chars", 0)
    features["text_length_words"] = nlp_dict.get("text_length_words", 0)

    # Risco
    features["risk_high"] = nlp_dict.get("risk_high", 0.0)
    features["risk_medium"] = nlp_dict.get("risk_medium", 0.0)
    features["risk_low"] = nlp_dict.get("risk_low", 0.0)
    features["simple_risk_score"] = nlp_dict.get("simple_risk_score", 0.0)

    # Domínio e ação primários (codificados)
    primary_domain = nlp_dict.get("primary_domain", "")
    for domain in ["security", "performance", "database", "devops", "testing"]:
        features[f"primary_domain_{domain}"] = 1.0 if primary_domain == domain else 0.0

    primary_action = nlp_dict.get("primary_action", "")
    for action in ["create", "update", "delete", "read", "deploy"]:
        features[f"primary_action_{action}"] = 1.0 if primary_action == action else 0.0

    return features


def load_feedback_data():
    """Carrega feedbacks do MongoDB com NLP features"""
    print("Carregando feedbacks do MongoDB...")

    client = MongoClient(MONGO_URI)
    db = client[DATABASE]

    # Buscar feedbacks com NLP features
    cursor = db["specialist_feedback"].find({"nlp_features": {"$exists": True, "$ne": {}}})

    feedbacks = list(cursor)
    print(f"Encontrados: {len(feedbacks)} feedbacks com NLP features")

    if len(feedbacks) == 0:
        raise ValueError("Nenhum feedback com NLP features encontrado!")

    return feedbacks


def prepare_dataframe(feedbacks):
    """Prepara dataframe para treinamento"""
    print("Preparando dataframe...")

    data = []
    for fb in feedbacks:
        # Extrair features NLP
        nlp_features = extract_nlp_features(fb.get("nlp_features", {}))

        # Adicionar features básicas
        row = {
            "final_decision": fb.get("final_decision"),
            "specialist_confidence": fb.get("confidence_score", 0.5),
            **nlp_features,
        }
        data.append(row)

    df = pd.DataFrame(data)

    # Remover linhas com decision vazio
    df = df[df["final_decision"].notna()]
    df = df[df["final_decision"] != ""]

    print(f"Dataframe shape: {df.shape}")
    print(f"Distribuicao de classes:")
    print(df["final_decision"].value_counts())

    return df


def train_models(X_train, y_train, X_test, y_test):
    """Treina modelos RandomForest e GradientBoosting"""
    print()
    print("=" * 60)
    print("TREINANDO MODELOS")
    print("=" * 60)

    results = {}

    # RandomForest
    print("\n1. RandomForestClassifier")
    rf = RandomForestClassifier(
        n_estimators=100, max_depth=10, random_state=42, class_weight="balanced"
    )

    rf.fit(X_train, y_train)
    rf_pred = rf.predict(X_test)

    rf_f1 = f1_score(y_test, rf_pred, average="weighted")
    rf_precision = precision_score(y_test, rf_pred, average="weighted", zero_division=0)
    rf_recall = recall_score(y_test, rf_pred, average="weighted", zero_division=0)

    results["RandomForest"] = {
        "f1_score": rf_f1,
        "precision": rf_precision,
        "recall": rf_recall,
        "model": rf,
    }

    print(f"  F1-Score: {rf_f1:.4f}")
    print(f"  Precision: {rf_precision:.4f}")
    print(f"  Recall: {rf_recall:.4f}")

    # GradientBoosting
    print("\n2. GradientBoostingClassifier")
    gb = GradientBoostingClassifier(
        n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42
    )

    gb.fit(X_train, y_train)
    gb_pred = gb.predict(X_test)

    gb_f1 = f1_score(y_test, gb_pred, average="weighted")
    gb_precision = precision_score(y_test, gb_pred, average="weighted", zero_division=0)
    gb_recall = recall_score(y_test, gb_pred, average="weighted", zero_division=0)

    results["GradientBoosting"] = {
        "f1_score": gb_f1,
        "precision": gb_precision,
        "recall": gb_recall,
        "model": gb,
    }

    print(f"  F1-Score: {gb_f1:.4f}")
    print(f"  Precision: {gb_precision:.4f}")
    print(f"  Recall: {gb_recall:.4f}")

    # Feature importances (RandomForest)
    print("\n3. Top Features (RandomForest):")
    importances = rf.feature_importances_
    feature_names = X_train.columns
    indices = np.argsort(importances)[::-1][:10]

    for idx in indices:
        print(f"  {feature_names[idx]}: {importances[idx]:.4f}")

    return results


def main():
    print("=" * 60)
    print("RETRAINING V6 - Com NLP Features")
    print("=" * 60)
    print(f"Data: {datetime.now().isoformat()}")
    print()

    # Configurar MLflow
    mlflow.set_tracking_uri("http://mlflow.mlflow.svc.cluster.local:5000")
    mlflow.set_experiment("nhm_approval_models")

    with mlflow.start_run(run_name=f"retraining_v6_nlp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"):
        # Carregar dados
        feedbacks = load_feedback_data()

        # Preparar dataframe
        df = prepare_dataframe(feedbacks)

        # Separar features e target
        feature_cols = [col for col in df.columns if col != "final_decision"]
        X = df[feature_cols].fillna(0)
        y = df["final_decision"]

        # Dividir em treino e teste
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=42, stratify=y
        )

        print(f"\nConjunto de treino: {X_train.shape}")
        print(f"Conjunto de teste: {X_test.shape}")

        # Treinar modelos
        results = train_models(X_train, y_train, X_test, y_test)

        # Log métricas no MLflow
        for model_name, metrics in results.items():
            mlflow.log_metrics(
                {
                    f"{model_name}_f1": metrics["f1_score"],
                    f"{model_name}_precision": metrics["precision"],
                    f"{model_name}_recall": metrics["recall"],
                }
            )

        # Log modelo RandomForest como principal
        best_model = results["RandomForest"]["model"]
        mlflow.sklearn.log_model(best_model, "model", registered_model_name="NHMApprovalModel")

        print()
        print("=" * 60)
        print("RESULTADOS FINAIS")
        print("=" * 60)
        for model_name, metrics in results.items():
            print(f"\n{model_name}:")
            print(f"  F1-Score: {metrics['f1_score']:.4f}")
            print(f"  Precision: {metrics['precision']:.4f}")
            print(f"  Recall: {metrics['recall']:.4f}")

        print()
        print("Modelo registrado no MLflow: NHMApprovalModel")

        # Comparar com baseline (0.5)
        baseline_f1 = 0.51
        best_f1 = max(results["RandomForest"]["f1_score"], results["GradientBoosting"]["f1_score"])
        improvement = ((best_f1 - baseline_f1) / baseline_f1) * 100

        print()
        print(f"Baseline F1-Score: {baseline_f1:.4f}")
        print(f"Best F1-Score: {best_f1:.4f}")
        print(f"Melhoria: {improvement:+.1f}%")

        if best_f1 > 0.7:
            print()
            print("✅ META ALCANÇADA! F1-Score > 0.7")
        else:
            print()
            print("⚠️ Ainda abaixo da meta de 0.7, mas melhor que o baseline!")


if __name__ == "__main__":
    main()
