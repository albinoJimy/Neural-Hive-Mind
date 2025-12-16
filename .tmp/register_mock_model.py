#!/usr/bin/env python3
"""
Script para registrar modelo mock no MLflow para specialist-technical
"""
import mlflow
from mlflow.sklearn import log_model
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import make_classification
import os

# Configurar MLflow
MLFLOW_TRACKING_URI = os.getenv('MLFLOW_TRACKING_URI', 'http://mlflow.mlflow.svc.cluster.local:5000')
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

MODEL_NAME = "technical-evaluator"
EXPERIMENT_NAME = "technical-specialist-local"

print(f"🔧 Registrando modelo mock: {MODEL_NAME}")
print(f"📍 MLflow URI: {MLFLOW_TRACKING_URI}")

# Criar experiment se não existir
try:
    experiment = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
    if experiment is None:
        experiment_id = mlflow.create_experiment(EXPERIMENT_NAME)
        print(f"✅ Experiment criado: {EXPERIMENT_NAME} (ID: {experiment_id})")
    else:
        experiment_id = experiment.experiment_id
        print(f"✅ Experiment existente: {EXPERIMENT_NAME} (ID: {experiment_id})")
except Exception as e:
    print(f"⚠️ Erro ao criar experiment: {e}")
    experiment_id = "0"  # Default experiment

# Treinar modelo dummy
print("🏋️ Treinando modelo dummy...")
X, y = make_classification(n_samples=100, n_features=10, n_informative=5, random_state=42)
model = RandomForestClassifier(n_estimators=10, random_state=42)
model.fit(X, y)
print("✅ Modelo treinado")

# Registrar modelo no MLflow
print("📝 Registrando modelo no MLflow...")
with mlflow.start_run(experiment_id=experiment_id, run_name="mock-model-registration"):
    mlflow.log_param("model_type", "mock")
    mlflow.log_param("purpose", "e2e_testing")
    mlflow.log_metric("accuracy", 0.95)  # Mock metric

    # Log model
    log_model(
        sk_model=model,
        artifact_path="model",
        registered_model_name=MODEL_NAME
    )

    run_id = mlflow.active_run().info.run_id
    print(f"✅ Modelo registrado (run_id: {run_id})")

# Promover para Staging
print("🚀 Promovendo modelo para Staging...")
client = mlflow.tracking.MlflowClient()
versions = client.search_model_versions(f"name='{MODEL_NAME}'")

if versions:
    latest_version = max(versions, key=lambda v: int(v.version))
    client.transition_model_version_stage(
        name=MODEL_NAME,
        version=latest_version.version,
        stage="Staging"
    )
    print(f"✅ Modelo {MODEL_NAME} v{latest_version.version} promovido para Staging")
else:
    print("❌ Nenhuma versão encontrada para promover")

print("\n✅ Processo concluído!")
