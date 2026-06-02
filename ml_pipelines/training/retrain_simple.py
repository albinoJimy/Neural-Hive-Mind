#!/usr/bin/env python3
"""
Script simplificado para retreino de especialistas ML com dados reais.

Contorna problemas de compatibilidade do sklearn e Pydantic v2
usando apenas as funções essenciais de coleta de dados e treinamento.
"""

import os
import sys
import asyncio
from pathlib import Path

# Adicionar paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "libraries" / "python"))

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    accuracy_score,
)
import mlflow
import mlflow.sklearn

# Importar RealDataCollector
try:
    from real_data_collector import RealDataCollector

    REAL_DATA_COLLECTOR_AVAILABLE = True
except ImportError:
    REAL_DATA_COLLECTOR_AVAILABLE = False
    print("WARNING: RealDataCollector not available")

# Configurações
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow.mlflow:5000")
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin",
)
MIN_SAMPLES = int(os.getenv("MIN_REAL_SAMPLES", "400"))
REAL_DATA_DAYS = int(os.getenv("REAL_DATA_DAYS", "60"))
SPECIALIST_TYPE = os.getenv("SPECIALIST_TYPE", "technical")

# Configurar MLflow
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow.set_experiment(f"{SPECIALIST_TYPE}-specialist")


def load_real_data(specialist_type: str) -> pd.DataFrame:
    """Carrega dados reais do MongoDB."""
    if not REAL_DATA_COLLECTOR_AVAILABLE:
        raise ImportError("RealDataCollector não disponível")

    print(f"Collecting real data for {specialist_type}...")
    print(f"  MongoDB: {MONGODB_URI.split('@')[1] if '@' in MONGODB_URI else 'localhost'}")
    print(f"  Min samples: {MIN_SAMPLES}")
    print(f"  Days: {REAL_DATA_DAYS}")

    async def collect():
        collector = RealDataCollector(mongodb_uri=MONGODB_URI, mongodb_database="neural_hive")

        df = await collector.collect_training_data(
            specialist_type=specialist_type,
            days=REAL_DATA_DAYS,
            min_samples=MIN_SAMPLES,
            min_feedback_rating=0.0,
        )

        # Validar
        dist_report = collector.validate_label_distribution(df, specialist_type)
        print(f"  Label distribution: {dist_report}")

        collector.close()
        return df

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(collect())


def prepare_features_and_labels(df: pd.DataFrame) -> tuple:
    """Prepara features e labels para treinamento."""
    # Colunas de features (todas exceto label e metadados)
    exclude_cols = {
        "label",
        "created_at",
        "feedback_id",
        "opinion_id",
        "submitted_at",
        "submitted_by",
        "trace_id",
        "specialist_type",
        "feedback_notes",
        "opinion_recommendation",
        "human_recommendation",
    }

    feature_cols = [col for col in df.columns if col not in exclude_cols]

    X = df[feature_cols].values
    y = df["label"].values

    print(f"  Features shape: {X.shape}")
    print(f"  Labels shape: {y.shape}")
    print(f"  Label distribution: {np.bincount(y.astype(int))}")

    return X, y, feature_cols


def train_model(X_train, y_train, X_val, y_val) -> RandomForestClassifier:
    """Treina modelo Random Forest."""
    print("Training Random Forest model...")

    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )

    model.fit(X_train, y_train)

    # Predições no validation set
    y_pred = model.predict(X_val)

    # Métricas
    precision = precision_score(y_val, y_pred, average="weighted", zero_division=0)
    recall = recall_score(y_val, y_pred, average="weighted", zero_division=0)
    f1 = f1_score(y_val, y_pred, average="weighted", zero_division=0)
    accuracy = accuracy_score(y_val, y_pred)

    print(f"  Validation Precision: {precision:.4f}")
    print(f"  Validation Recall: {recall:.4f}")
    print(f"  Validation F1: {f1:.4f}")
    print(f"  Validation Accuracy: {accuracy:.4f}")

    return model


def main():
    """Função principal de retreino."""
    print("=" * 50)
    print(f"ML Retraining with Real Data: {SPECIALIST_TYPE}")
    print("=" * 50)
    print()

    with mlflow.start_run() as run:
        print(f"MLflow run ID: {run.info.run_id}")

        # 1. Carregar dados
        df = load_real_data(SPECIALIST_TYPE)

        # 2. Splits temporais
        df = df.sort_values("created_at").reset_index(drop=True)
        n = len(df)
        train_end = int(n * 0.7)
        val_end = int(n * 0.85)

        df_train = df.iloc[:train_end]
        df_val = df.iloc[train_end:val_end]
        df_test = df.iloc[val_end:]

        print(f"Split sizes: train={len(df_train)}, val={len(df_val)}, test={len(df_test)}")
        print()

        # 3. Preparar features
        X_train, y_train, feature_names = prepare_features_and_labels(df_train)
        X_val, y_val, _ = prepare_features_and_labels(df_val)
        X_test, y_test, _ = prepare_features_and_labels(df_test)

        # 4. Treinar modelo
        model = train_model(X_train, y_train, X_val, y_val)

        # 5. Avaliar no test set
        y_test_pred = model.predict(X_test)
        test_precision = precision_score(y_test, y_test_pred, average="weighted", zero_division=0)
        test_recall = recall_score(y_test, y_test_pred, average="weighted", zero_division=0)
        test_f1 = f1_score(y_test, y_test_pred, average="weighted", zero_division=0)
        test_accuracy = accuracy_score(y_test, y_test_pred)

        print()
        print("Test Set Metrics:")
        print(f"  Precision: {test_precision:.4f}")
        print(f"  Recall: {test_recall:.4f}")
        print(f"  F1: {test_f1:.4f}")
        print(f"  Accuracy: {test_accuracy:.4f}")

        # 6. Log métricas no MLflow
        mlflow.log_params(
            {
                "specialist_type": SPECIALIST_TYPE,
                "n_samples": len(df),
                "n_train": len(df_train),
                "n_val": len(df_val),
                "n_test": len(df_test),
                "data_source": "real",
                "min_samples": MIN_SAMPLES,
                "real_data_days": REAL_DATA_DAYS,
            }
        )

        mlflow.log_metrics(
            {
                "test_precision": test_precision,
                "test_recall": test_recall,
                "test_f1": test_f1,
                "test_accuracy": test_accuracy,
                "train_precision": precision_score(
                    y_train, model.predict(X_train), average="weighted", zero_division=0
                ),
                "train_recall": recall_score(
                    y_train, model.predict(X_train), average="weighted", zero_division=0
                ),
            }
        )

        # 7. Feature importance
        if hasattr(model, "feature_importances_"):
            importances = dict(zip(feature_names, model.feature_importances_))
            top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:10]
            print()
            print("Top 10 Features:")
            for feat, imp in top_features:
                print(f"  {feat}: {imp:.4f}")

        # 8. Salvar modelo no MLflow
        model_name = f"{SPECIALIST_TYPE}-evaluator"
        mlflow.sklearn.log_model(model, "model", registered_model_name=model_name, signature=None)

        print()
        print(f"Model registered as: {model_name}")
        print("Version: (check MLflow UI)")

    print()
    print("=" * 50)
    print("Training completed successfully!")
    print("=" * 50)


if __name__ == "__main__":
    main()
