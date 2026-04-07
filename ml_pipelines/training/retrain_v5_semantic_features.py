#!/usr/bin/env python3
"""
Script de Retraining com Features Semânticas (v5)

Usa apenas samples com reasoning_factors semânticos completos (~46 samples).
Features semânticas: security, architecture, performance, quality, risk_patterns, complexity_evaluation
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

import pandas as pd
import numpy as np
from pymongo import MongoClient
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    accuracy_score,
    classification_report,
    confusion_matrix,
)
import pickle
import json

# Configurações
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin",
)
DB_NAME = "neural_hive"
SPECIALIST = "technical"
MIN_SAMPLES = 30

# Mapeamento de recomendações para labels
REC_TO_LABEL = {"approve": 1, "reject": 0, "review_required": 2, "conditional": 2}
LABEL_NAMES = {0: "reject", 1: "approve", 2: "review_required"}

# Features semânticas esperadas
SEMANTIC_FACTORS = [
    "semantic_security_analysis",
    "semantic_architecture_analysis",
    "semantic_performance_analysis",
    "semantic_quality_analysis",
    "risk_patterns",
    "complexity_evaluation",
]

print("=" * 70)
print(f"🤖 RETRAINING {SPECIALIST.upper()} - SEMANTIC FEATURES (v5)")
print("=" * 70)
print(f"MongoDB: mongodb.mongodb-cluster.svc.cluster.local:27017")
print(f"Min samples: {MIN_SAMPLES}")
print()

client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
db = client[DB_NAME]

# 1. Buscar dados com fatores semânticos
print("📊 Coletando dados com fatores semânticos...")
opinions_col = db["specialist_opinions"]
feedbacks_col = db["specialist_feedback"]

pipeline = [
    {"$match": {"specialist_type": SPECIALIST}},
    {
        "$lookup": {
            "from": "specialist_feedback",
            "localField": "opinion_id",
            "foreignField": "opinion_id",
            "as": "feedback",
        }
    },
    {"$match": {"feedback": {"$ne": []}}},
    {"$unwind": "$feedback"},
    {
        "$project": {
            "opinion_id": 1,
            "opinion": 1,
            "feedback.human_recommendation": 1,
            "feedback.reasoning_factors": 1,
        }
    },
]

results = list(opinions_col.aggregate(pipeline))
print(f"✅ {len(results)} amostras totais coletadas")

# 2. Filtrar samples com fatores semânticos
print("🔧 Filtrando samples com fatores semânticos...")
samples = []

for r in results:
    rec = r.get("feedback", {}).get("human_recommendation", "")
    label = REC_TO_LABEL.get(rec.lower())
    if label is None:
        continue

    reasoning_factors = r.get("feedback", {}).get("reasoning_factors", [])
    if not isinstance(reasoning_factors, list):
        continue

    # Verificar se tem pelo menos 1 fator semântico
    has_semantic = any(
        f.get("factor_name") in SEMANTIC_FACTORS for f in reasoning_factors if isinstance(f, dict)
    )

    if not has_semantic:
        continue

    opinion = r.get("opinion", {})

    # Features básicas
    basic_features = {
        "confidence": float(opinion.get("confidence_score", 0.5)),
        "risk": float(opinion.get("risk_score", 0.5)),
    }

    # Features semânticas ponderadas
    semantic_features = {}
    for f in reasoning_factors:
        if isinstance(f, dict):
            name = f.get("factor_name", "")
            score = float(f.get("score", 0.0))
            weight = float(f.get("weight", 0.0))

            # Nome simplificado
            simple_name = name.replace("semantic_", "").replace("_analysis", "")
            semantic_features[f"rf_{simple_name}"] = score * weight

    sample = {
        **basic_features,
        **semantic_features,
        "label": label,
        "opinion_id": r.get("opinion_id"),
    }
    samples.append(sample)

print(f"✅ {len(samples)} amostras com fatores semânticos")

# Criar DataFrame
df = pd.DataFrame(samples)

# Verificar features disponíveis
all_feature_cols = [c for c in df.columns if c.startswith("rf_") or c in ["confidence", "risk"]]
available_features = [f for f in all_feature_cols if df[f].notna().any()]

print(f"\n📊 Features disponíveis ({len(available_features)}):")
for feat in available_features:
    non_null = df[feat].notna().sum()
    pct = non_null / len(df) * 100
    mean_val = df[feat].mean()
    print(f"  {feat:30}: {non_null:3} ({pct:5.1f}%) - mean={mean_val:.4f}")

# Distribuição de labels
print(f"\n📈 Distribuição de labels:")
for label, name in LABEL_NAMES.items():
    count = (df["label"] == label).sum()
    pct = count / len(df) * 100 if len(df) > 0 else 0
    print(f"  {name:15}: {count:3} ({pct:5.1f}%)")

if len(df) < MIN_SAMPLES:
    print(f"\n❌ Amostras insuficientes ({len(df)} < {MIN_SAMPLES})")
    sys.exit(1)

# 3. Preparar dados de treinamento
X = df[available_features].fillna(0).values
y = df["label"].values

# Verificar variância das features
print("\n📊 Variância das features:")
variances = df[available_features].var()
for feat, var in variances.items():
    print(f"  {feat:30}: {var:.6f}")

# Features sem variância não ajudam
low_variance_features = [f for f in available_features if variances[f] < 0.0001]
if low_variance_features:
    print(f"\n⚠️ Features com baixa variância (<0.0001): {low_variance_features}")

# Split estratificado se possível
try:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )
    print("\n✅ Split estratificado realizado")
except ValueError as e:
    # Se não tiver samples suficientes de uma classe, fazer split normal
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    print(f"\n⚠️ Split normal (sem estratificação): {e}")

print(f"\n📈 Distribuição no split:")
for label, name in LABEL_NAMES.items():
    count_train = (y_train == label).sum()
    count_test = (y_test == label).sum()
    print(f"  {name:15}: Train {count_train:2} | Test {count_test:2}")

# 4. Treinar modelos
print(f"\n🤖 Treinando modelos...")
models = {
    "RandomForest": RandomForestClassifier(
        n_estimators=50, max_depth=8, min_samples_split=2, random_state=42, n_jobs=-1
    ),
    "GradientBoosting": GradientBoostingClassifier(
        n_estimators=50, max_depth=3, learning_rate=0.1, random_state=42
    ),
}

results = {}
for name, model in models.items():
    print(f"  Training {name}...")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    precision = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    recall = recall_score(y_test, y_pred, average="weighted", zero_division=0)
    f1 = f1_score(y_test, y_pred, average="weighted", zero_division=0)
    accuracy = accuracy_score(y_test, y_pred)

    results[name] = {
        "model": model,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "predictions": y_pred,
    }

    print(f"    F1: {f1:.4f}, Accuracy: {accuracy:.4f}")

# 5. Melhor modelo
best_model_name = max(results, key=lambda k: results[k]["f1"])
best_model = results[best_model_name]["model"]
best_predictions = results[best_model_name]["predictions"]

print(f"\n✅ Melhor modelo: {best_model_name}")
print(f"   F1-Score: {results[best_model_name]['f1']:.4f}")
print(f"   Accuracy: {results[best_model_name]['accuracy']:.4f}")

# 6. Feature importance
if hasattr(best_model, "feature_importances_"):
    importances = list(zip(available_features, best_model.feature_importances_))
    importances = sorted(importances, key=lambda x: -x[1])

    print(f"\n🔍 Feature Importance ({best_model_name}):")
    for feat, imp in importances:
        print(f"  {feat:30}: {imp:.4f}")

# 7. Classification report
print(f"\n📊 Classification Report ({best_model_name}):")
print(
    classification_report(
        y_test, best_predictions, target_names=[LABEL_NAMES[i] for i in range(3)], zero_division=0
    )
)

# 8. Salvar modelo
output_dir = Path(f"/tmp/ml_models/{SPECIALIST}")
output_dir.mkdir(parents=True, exist_ok=True)

model_path = output_dir / f"{SPECIALIST}_evaluator_v5_semantic.pkl"
with open(model_path, "wb") as f:
    pickle.dump(best_model, f)

# Salvar metadados
metadata = {
    "model_type": best_model_name,
    "schema_version": "5.0.0-semantic",
    "features": available_features,
    "feature_importance": {feat: float(imp) for feat, imp in importances},
    "feature_variances": {feat: float(variances[feat]) for feat in available_features},
    "metrics": {
        "precision": float(results[best_model_name]["precision"]),
        "recall": float(results[best_model_name]["recall"]),
        "f1": float(results[best_model_name]["f1"]),
        "accuracy": float(results[best_model_name]["accuracy"]),
    },
    "sample_count": len(df),
    "train_count": len(X_train),
    "test_count": len(X_test),
    "semantic_samples_only": True,
    "training_date": datetime.now(timezone.utc).isoformat(),
}

metadata_path = output_dir / f"{SPECIALIST}_metadata_v5.json"
with open(metadata_path, "w") as f:
    json.dump(metadata, f, indent=2)

print(f"\n✅ Modelo salvo em: {model_path}")
print(f"✅ Metadados salvo em: {metadata_path}")
print("=" * 70)

client.close()

print("\n🚀 Conclusão:")
print(f"Modelo treinado com {len(df)} samples que têm fatores semânticos.")
print("Features semânticas podem discriminar melhor que features básicas.")
print("Recomendação: coletar mais feedbacks com análise semântica completa.")
