#!/usr/bin/env python3
"""
Script de Retraining com Features Básicas (v4)

Usa apenas features com boa cobertura (90%+ dos dados):
- confidence, risk (100%)
- rf_ml_confidence, rf_ml_risk (90.5%)

Objetivo: Criar modelo estável antes de ter mais dados semânticos.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

import pandas as pd
import numpy as np
from pymongo import MongoClient
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import precision_score, recall_score, f1_score, accuracy_score, classification_report, confusion_matrix
import pickle
import json

# Configurações
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin")
DB_NAME = "neural_hive"
SPECIALIST = "technical"
MIN_SAMPLES = 100
DAYS = 365

# Mapeamento de recomendações para labels
REC_TO_LABEL = {"approve": 1, "reject": 0, "review_required": 2, "conditional": 2}
LABEL_NAMES = {0: "reject", 1: "approve", 2: "review_required"}

print("=" * 70)
print(f"🤖 RETRAINING {SPECIALIST.upper()} - BASIC FEATURES (v4)")
print("=" * 70)
print(f"MongoDB: mongodb.mongodb-cluster.svc.cluster.local:27017")
print(f"Min samples: {MIN_SAMPLES}, Days: {DAYS}")
print()

client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
db = client[DB_NAME]

# 1. Buscar dados enriquecidos
print("📊 Coletando dados...")
opinions_col = db['specialist_opinions']
feedbacks_col = db['specialist_feedback']

pipeline = [
    {'$match': {'specialist_type': SPECIALIST}},
    {'$lookup': {
        'from': 'specialist_feedback',
        'localField': 'opinion_id',
        'foreignField': 'opinion_id',
        'as': 'feedback'
    }},
    {'$match': {'feedback': {'$ne': []}}},
    {'$unwind': '$feedback'},
    {'$project': {
        'opinion_id': 1,
        'plan_id': 1,
        'specialist_type': 1,
        'intent_id': 1,
        'trace_id': 1,
        'opinion': 1,
        'created_at': 1,
        'feedback.human_recommendation': 1,
        'feedback.human_rating': 1,
        'feedback.opinion_recommendation': 1,
        'feedback.opinion_confidence': 1,
        'feedback.opinion_risk': 1,
        'feedback.reasoning_factors': 1,
        'feedback.schema_version': 1,
    }}
]

results = list(opinions_col.aggregate(pipeline))
print(f"✅ {len(results)} amostras coletadas")
print()

# 2. Preparar features
print("🔧 Preparando features...")
samples = []

for r in results:
    rec = r.get('feedback', {}).get('human_recommendation', '')
    label = REC_TO_LABEL.get(rec.lower())
    if label is None:
        continue

    opinion = r.get('opinion', {})
    reasoning_factors = r.get('feedback', {}).get('reasoning_factors', [])

    # Features básicas da opinião
    basic_features = {
        'confidence': float(opinion.get('confidence_score', 0.5)),
        'risk': float(opinion.get('risk_score', 0.5)),
    }

    # Features de reasoning_factors (apenas ml_confidence e ml_risk com boa cobertura)
    # NOTA: Para ml_confidence/ml_risk, usamos apenas o score pois weight=0 nos dados migrados
    rf_ml_confidence = 0.0
    rf_ml_risk = 0.0

    if isinstance(reasoning_factors, list):
        for f in reasoning_factors:
            if isinstance(f, dict):
                name = f.get('factor_name', '')
                score = float(f.get('score', 0.0))
                weight = float(f.get('weight', 0.0))

                # Para fatores ML, usar score diretamente (weight é 0 nos dados migrados)
                if name == 'ml_confidence':
                    rf_ml_confidence = score if weight == 0 else score * weight
                elif name == 'ml_risk':
                    rf_ml_risk = score if weight == 0 else score * weight

    # Combinar
    sample = {
        **basic_features,
        'rf_ml_confidence': rf_ml_confidence,
        'rf_ml_risk': rf_ml_risk,
        'label': label,
        'opinion_id': r.get('opinion_id'),
        'created_at': r.get('created_at'),
    }
    samples.append(sample)

print(f"✅ {len(samples)} amostras preparadas")

# Criar DataFrame
df = pd.DataFrame(samples)
feature_cols = ['confidence', 'risk', 'rf_ml_confidence', 'rf_ml_risk']
print(f"📊 Features: {feature_cols}")
print()

# Mostrar estatísticas das features
print("📊 Estatísticas das features:")
for feat in feature_cols:
    non_null = df[feat].notna().sum()
    pct = non_null / len(df) * 100
    print(f"  {feat:20}: {non_null:3} ({pct:5.1f}%) - min={df[feat].min():.3f}, max={df[feat].max():.3f}, mean={df[feat].mean():.3f}")
print()

# 3. Preparar dados de treinamento
X = df[feature_cols].fillna(0).values
y = df['label'].values

# Split estratificado
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print(f"📈 Distribuição de labels:")
for label, name in LABEL_NAMES.items():
    count_train = (y_train == label).sum()
    count_test = (y_test == label).sum()
    pct_train = count_train / len(y_train) * 100
    pct_test = count_test / len(y_test) * 100
    print(f"  {name:15}: Train {count_train:3} ({pct_train:5.1f}%) | Test {count_test:3} ({pct_test:5.1f}%)")

# 4. Treinar modelos
print(f"\n🤖 Treinando modelos...")

# Calcular pesos de classe para balancear
from sklearn.utils.class_weight import compute_class_weight
class_weights = compute_class_weight('balanced', classes=np.unique(y_train), y=y_train)
class_weight_dict = {i: class_weights[i] for i in range(len(class_weights))}
print(f"  Class weights: {class_weight_dict}")

models = {
    'RandomForest': RandomForestClassifier(
        n_estimators=100, max_depth=10, min_samples_split=5,
        random_state=42, n_jobs=-1, class_weight='balanced'
    ),
    'GradientBoosting': GradientBoostingClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.1,
        random_state=42
    ),
}

results = {}
for name, model in models.items():
    print(f"  Training {name}...")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
    recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
    f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
    accuracy = accuracy_score(y_test, y_pred)

    results[name] = {
        'model': model,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'accuracy': accuracy,
        'predictions': y_pred
    }

    print(f"    F1: {f1:.4f}, Accuracy: {accuracy:.4f}")

# 5. Melhor modelo
best_model_name = max(results, key=lambda k: results[k]['f1'])
best_model = results[best_model_name]['model']
best_predictions = results[best_model_name]['predictions']

print(f"\n✅ Melhor modelo: {best_model_name}")
print(f"   F1-Score: {results[best_model_name]['f1']:.4f}")
print(f"   Accuracy: {results[best_model_name]['accuracy']:.4f}")

# 6. Feature importance
if hasattr(best_model, 'feature_importances_'):
    importances = list(zip(feature_cols, best_model.feature_importances_))
    importances = sorted(importances, key=lambda x: -x[1])

    print(f"\n🔍 Feature Importance ({best_model_name}):")
    for feat, imp in importances:
        print(f"  {feat:20}: {imp:.4f}")

# 7. Classification report detalhado
print(f"\n📊 Classification Report ({best_model_name}):")
print(classification_report(
    y_test, best_predictions,
    target_names=[LABEL_NAMES[i] for i in range(3)],
    zero_division=0
))

# 8. Matriz de confusão
cm = confusion_matrix(y_test, best_predictions)
print(f"\n📊 Confusion Matrix:")
print("              Predicted")
print("        Reject  Approve  Review")
for i, row in enumerate(cm):
    print(f"Actual {LABEL_NAMES[i]:7}: {row}")

# 9. Salvar modelo
output_dir = Path(f"/tmp/ml_models/{SPECIALIST}")
output_dir.mkdir(parents=True, exist_ok=True)

model_path = output_dir / f"{SPECIALIST}_evaluator_v4_basic.pkl"
with open(model_path, 'wb') as f:
    pickle.dump(best_model, f)

# Salvar metadados
metadata = {
    'model_type': best_model_name,
    'schema_version': '4.0.0-basic',
    'features': feature_cols,
    'feature_importance': {feat: float(imp) for feat, imp in importances},
    'metrics': {
        'precision': float(results[best_model_name]['precision']),
        'recall': float(results[best_model_name]['recall']),
        'f1': float(results[best_model_name]['f1']),
        'accuracy': float(results[best_model_name]['accuracy']),
    },
    'class_distribution': {
        'train': {LABEL_NAMES[i]: int((y_train == i).sum()) for i in range(3)},
        'test': {LABEL_NAMES[i]: int((y_test == i).sum()) for i in range(3)},
    },
    'class_weights': {LABEL_NAMES[i]: float(class_weights[i]) for i in range(len(class_weights))},
    'training_date': datetime.utcnow().isoformat(),
    'sample_count': len(df),
    'test_sample_count': len(X_test),
}

metadata_path = output_dir / f"{SPECIALIST}_metadata_v4.json"
with open(metadata_path, 'w') as f:
    json.dump(metadata, f, indent=2)

print(f"\n✅ Modelo salvo em: {model_path}")
print(f"✅ Metadados salvo em: {metadata_path}")
print("=" * 70)

client.close()

print("\n🚀 Next steps:")
print("1. Modelo treinado com features básicas (confiança estável)")
print("2. Para melhorar: coletar mais feedbacks com features semânticas")
print("3. Implementar captura de intent_raw_text no pipeline de feedback")
print("4. Executar retraining quando houver mais dados balanceados")
