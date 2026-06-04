#!/usr/bin/env python3
"""
Script simplificado para retreino local sem dependência do MLflow API.

Treina modelo com dados reais e salva como arquivo pickle para registro manual posterior.
"""

import os
import sys
import asyncio
import pickle
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "libraries" / "python"))

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    accuracy_score,
)

# Importar RealDataCollector
try:
    from real_data_collector import RealDataCollector

    REAL_DATA_COLLECTOR_AVAILABLE = True
except ImportError:
    REAL_DATA_COLLECTOR_AVAILABLE = False
    print("WARNING: RealDataCollector not available")
    sys.exit(1)


# Configurações
# Use localhost se disponível (via port-forward), senão usa o URI do cluster
if os.path.exists("/.dockerenv"):
    # Dentro de um container cluster
    MONGODB_URI = os.getenv(
        "MONGODB_URI",
        "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin",
    )
else:
    # Local com port-forward
    MONGODB_URI = os.getenv(
        "MONGODB_URI", "mongodb://root:local_dev_password@localhost:27017/?authSource=admin"
    )

MIN_SAMPLES = int(os.getenv("MIN_REAL_SAMPLES", "400"))
REAL_DATA_DAYS = int(os.getenv("REAL_DATA_DAYS", "60"))
SPECIALIST_TYPE = os.getenv("SPECIALIST_TYPE", "technical")


def load_real_data(specialist_type: str) -> pd.DataFrame:
    """Carrega dados reais do MongoDB."""
    print(f"Collecting real data for {specialist_type}...")
    print(f"  Min samples: {MIN_SAMPLES}")
    print(f"  Days: {REAL_DATA_DAYS}")

    async def collect():
        collector = RealDataCollector(mongodb_uri=MONGODB_URI, mongodb_database="neural_hive")

        # Usar days=365 para pegar todas as opiniões que têm feedback
        # (Feedback foi coletado em 2026-02-08, mas opiniões têm created_at variados)
        df = await collector.collect_training_data(
            specialist_type=specialist_type,
            days=365,  # 1 ano para garantir que pegamos opiniões com feedback
            min_samples=MIN_SAMPLES,
            min_feedback_rating=0.0,
        )

        # Validar distribuição
        dist_report = collector.validate_label_distribution(df, specialist_type)
        print(f"  Label distribution: {dist_report}")

        collector.close()
        return df

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(collect())


def prepare_features_and_labels(df: pd.DataFrame) -> tuple:
    """Prepara features e labels para treinamento."""
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
    print(f"  Label distribution: {np.bincount(y.astype(int))}")

    return X, y, feature_cols


def train_and_evaluate(X_train, y_train, X_val, y_val, X_test, y_test, feature_names):
    """Treina modelo e avalia."""
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

    # Métricas
    y_train_pred = model.predict(X_train)
    y_val_pred = model.predict(X_val)
    y_test_pred = model.predict(X_test)

    train_precision = precision_score(y_train, y_train_pred, average="weighted", zero_division=0)
    train_recall = recall_score(y_train, y_train_pred, average="weighted", zero_division=0)
    train_f1 = f1_score(y_train, y_train_pred, average="weighted", zero_division=0)

    val_precision = precision_score(y_val, y_val_pred, average="weighted", zero_division=0)
    val_recall = recall_score(y_val, y_val_pred, average="weighted", zero_division=0)
    val_f1 = f1_score(y_val, y_val_pred, average="weighted", zero_division=0)

    test_precision = precision_score(y_test, y_test_pred, average="weighted", zero_division=0)
    test_recall = recall_score(y_test, y_test_pred, average="weighted", zero_division=0)
    test_f1 = f1_score(y_test, y_test_pred, average="weighted", zero_division=0)
    test_accuracy = accuracy_score(y_test, y_test_pred)

    metrics = {
        "train": {"precision": train_precision, "recall": train_recall, "f1": train_f1},
        "val": {"precision": val_precision, "recall": val_recall, "f1": val_f1},
        "test": {
            "precision": test_precision,
            "recall": test_recall,
            "f1": test_f1,
            "accuracy": test_accuracy,
        },
    }

    print()
    print("Metrics:")
    print(f"  Train - P: {train_precision:.4f}, R: {train_recall:.4f}, F1: {train_f1:.4f}")
    print(f"  Val   - P: {val_precision:.4f}, R: {val_recall:.4f}, F1: {val_f1:.4f}")
    print(
        f"  Test  - P: {test_precision:.4f}, R: {test_recall:.4f}, F1: {test_f1:.4f}, Acc: {test_accuracy:.4f}"
    )

    # Feature importance
    if hasattr(model, "feature_importances_"):
        importances = dict(zip(feature_names, model.feature_importances_))
        top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:10]
        print()
        print("Top 10 Features:")
        for feat, imp in top_features:
            print(f"  {feat}: {imp:.4f}")

    return model, metrics


def main():
    """Função principal."""
    print("=" * 60)
    print(f"Local ML Retraining with Real Data: {SPECIALIST_TYPE}")
    print("=" * 60)
    print()

    # 1. Carregar dados
    df = load_real_data(SPECIALIST_TYPE)
    print(f"Loaded {len(df)} samples")
    print()

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
    print()

    # 4. Treinar modelo
    model, metrics = train_and_evaluate(
        X_train, y_train, X_val, y_val, X_test, y_test, feature_names
    )

    # 5. Salvar modelo
    output_dir = Path(f"/tmp/ml_models/{SPECIALIST_TYPE}")
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = output_dir / f"{SPECIALIST_TYPE}_evaluator_real_data.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    print()
    print(f"Model saved to: {model_path}")

    # 6. Salvar métricas
    metrics_path = output_dir / f"{SPECIALIST_TYPE}_metrics.txt"
    with open(metrics_path, "w") as f:
        f.write(f"Model: {SPECIALIST_TYPE}-evaluator\n")
        f.write(f"Data: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Samples: {len(df)}\n")
        f.write("Data source: real (MongoDB)\n")
        f.write("\nMetrics:\n")
        for split, split_metrics in metrics.items():
            f.write(f"\n{split.capitalize()}:\n")
            for metric_name, value in split_metrics.items():
                f.write(f"  {metric_name}: {value:.4f}\n")

    print(f"Metrics saved to: {metrics_path}")

    print()
    print("=" * 60)
    print("Training completed successfully!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Copy model to persistent storage")
    print("2. Register model in MLflow (when API is accessible)")
    print("3. Restart specialist pods to load new model")


if __name__ == "__main__":
    main()
