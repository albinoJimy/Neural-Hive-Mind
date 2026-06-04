#!/usr/bin/env python3
"""
Script de Retrining com Features Enriquecidas (v3)

Este script treina modelos ML usando:
- Features existentes (confidence, risk)
- Features dos reasoning_factors (6 features ponderadas)
- Features NLP do texto da intenção (30+ features)

Total: ~40 features para predição de decisão humana
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pymongo import MongoClient
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    accuracy_score,
    classification_report,
)
import pickle

# Configurações
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin",
)
DB_NAME = "neural_hive"
SPECIALIST = "technical"
MIN_SAMPLES = 100
DAYS = 365

# Mapeamento de recomendações para labels
REC_TO_LABEL = {"approve": 1, "reject": 0, "review_required": 2, "conditional": 2}
LABEL_NAMES = {0: "reject", 1: "approve", 2: "review_required"}

print("=" * 70)
print(f"🤖 RETRAINING {SPECIALIST.upper()} WITH ENRICHED FEATURES (v3)")
print("=" * 70)
print("MongoDB: mongodb.mongodb-cluster.svc.cluster.local:27017")
print(f"Min samples: {MIN_SAMPLES}, Days: {DAYS}")
print()

client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
db = client[DB_NAME]

# 1. Buscar dados enriquecidos
print("📊 Coletando dados enriquecidos...")
opinions_col = db["specialist_opinions"]
feedbacks_col = db["specialist_feedback"]

# Pipeline para juntar opiniões com feedbacks enriquecidos
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
            "plan_id": 1,
            "specialist_type": 1,
            "intent_id": 1,
            "trace_id": 1,
            "opinion": 1,
            "created_at": 1,
            "feedback.human_recommendation": 1,
            "feedback.human_rating": 1,
            "feedback.opinion_recommendation": 1,
            "feedback.opinion_confidence": 1,
            "feedback.opinion_risk": 1,
            "feedback.reasoning_factors": 1,
            "feedback.nlp_features": 1,
            "feedback.schema_version": 1,
        }
    },
]

results = list(opinions_col.aggregate(pipeline))
print(f"✅ {len(results)} amostras coletadas")
print()

# 2. Preparar features
print("🔧 Preparando features...")
samples = []

for r in results:
    rec = r.get("feedback", {}).get("human_recommendation", "")
    label = REC_TO_LABEL.get(rec.lower())
    if label is None:
        continue

    opinion = r.get("opinion", {})
    reasoning_factors = r.get("feedback", {}).get("reasoning_factors", [])
    nlp_features = r.get("feedback", {}).get("nlp_features", {})

    # Features básicas da opinião
    basic_features = {
        "confidence": float(opinion.get("confidence_score", 0.5)),
        "risk": float(opinion.get("risk_score", 0.5)),
    }

    # Features de reasoning_factors (ponderadas)
    factor_features = {}
    if isinstance(reasoning_factors, list):
        for f in reasoning_factors:
            if isinstance(f, dict):
                name = f.get("factor_name", "").replace("semantic_", "").replace("_analysis", "")
                score = float(f.get("score", 0.0))
                weight = float(f.get("weight", 0.0))
                factor_features[f"rf_{name}"] = score * weight

    # Features NLP
    nlp_feature_names = [
        "text_length_chars",
        "text_length_words",
        "avg_word_length",
        "domain_security",
        "domain_performance",
        "domain_architecture",
        "domain_database",
        "domain_testing",
        "domain_devops",
        "has_url",
        "has_path",
        "has_email",
        "has_file_path",
        "technical_patterns_count",
        "action_create",
        "action_update",
        "action_delete",
        "action_read",
        "action_deploy",
        "sentiment_positive",
        "sentiment_negative",
        "urgency_high",
    ]
    nlp_feature_vals = {f"nlp_{k}": v for k, v in nlp_features.items() if k in nlp_feature_names}

    # Combinar todas
    sample = {
        **basic_features,
        **factor_features,
        **nlp_feature_vals,
        "label": label,
        "opinion_id": r.get("opinion_id"),
        "created_at": r.get("created_at"),
    }
    samples.append(sample)

print(f"✅ {len(samples)} amostras preparadas")

# Verificar quais features estão disponíveis
df = pd.DataFrame(samples)
feature_cols = [c for c in df.columns if c != "label" and c not in ["opinion_id", "created_at"]]
print(f"📊 Total de features: {len(feature_cols)}")
print()

# Mostrar features não nulas
non_null_counts = df[feature_cols].notna().sum()
non_null_counts = non_null_counts[non_null_counts > 0].sort_values(ascending=False)
print(f"📊 Features não-nulas ({len(non_null_counts)}):")
for feat, count in non_null_counts.head(15).items():
    pct = count / len(df) * 100
    print(f"  {feat:30}: {count:3} ({pct:5.1f}%)")

# Filtrar apenas features não-nulas
available_features = [f for f in feature_cols if df[f].notna().any()]
print(f"\n📊 Usando {len(available_features)} features para treinamento")

# 3. Preparar dados de treinamento - tratar NaN
X = df[available_features].fillna(0).values  # Preencher NaN com 0
y = df["label"].values

# Split estratificado
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print("\n📈 Distribuição de labels:")
for label, name in LABEL_NAMES.items():
    count_train = (y_train == label).sum()
    count_test = (y_test == label).sum()
    pct_train = count_train / len(y_train) * 100
    pct_test = count_test / len(y_test) * 100
    print(
        f"  {name:15}: Train {count_train:3} ({pct_train:5.1f}%) | Test {count_test:3} ({pct_test:5.1f}%)"
    )

# 4. Calcular pesos de amostra para balancear classes
from sklearn.utils.class_weight import compute_sample_weight

sample_weights = compute_sample_weight("balanced", y_train)

print("\n🤖 Treinando modelos...")
models = {
    "RandomForest": RandomForestClassifier(
        n_estimators=100,
        max_depth=15,
        min_samples_split=3,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
    ),
    "GradientBoosting": GradientBoostingClassifier(
        n_estimators=150, max_depth=5, learning_rate=0.1, random_state=42
    ),
}

results = {}
for name, model in models.items():
    print(f"  Training {name}...")
    if name == "GradientBoosting":
        model.fit(X_train, y_train, sample_weight=sample_weights)
    else:
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

    print(f"\n🔍 Top 15 Feature Importance ({best_model_name}):")
    for feat, imp in importances[:15]:
        print(f"  {feat:30}: {imp:.4f}")

# 7. Classification report detalhado
print(f"\n📊 Classification Report ({best_model_name}):")
print(
    classification_report(
        y_test, best_predictions, target_names=[LABEL_NAMES[i] for i in range(3)], zero_division=0
    )
)

# 8. Salvar modelo
output_dir = Path(f"/tmp/ml_models/{SPECIALIST}")
output_dir.mkdir(parents=True, exist_ok=True)

model_path = output_dir / f"{SPECIALIST}_evaluator_v3_enriched.pkl"
with open(model_path, "wb") as f:
    pickle.dump(best_model, f)

# Salvar metadados
metadata = {
    "model_type": best_model_name,
    "schema_version": "3.0.0-enriched",
    "features": available_features,
    "feature_importance": dict(importances),
    "metrics": {
        "precision": float(results[best_model_name]["precision"]),
        "recall": float(results[best_model_name]["recall"]),
        "f1": float(results[best_model_name]["f1"]),
        "accuracy": float(results[best_model_name]["accuracy"]),
    },
    "training_date": datetime.now(timezone.utc).isoformat(),
    "sample_count": len(df),
    "test_sample_count": len(X_test),
}

metadata_path = output_dir / f"{SPECIALIST}_metadata_v3.json"
import json

with open(metadata_path, "w") as f:
    json.dump(metadata, f, indent=2)

print(f"\n✅ Modelo salvo em: {model_path}")
print(f"✅ Metadados salvo em: {metadata_path}")
print("=" * 70)

client.close()

print("\n🚀 Next steps:")
print("1. Copiar modelo para storage persistente")
print("2. Registrar no MLflow (quando disponível)")
print("3. Restart dos pods dos especialistas")
print("4. Monitorar métricas em produção")
