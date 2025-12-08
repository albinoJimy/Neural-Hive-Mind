#!/usr/bin/env python3
"""
Pipeline MLflow para re-treinamento de modelos de especialistas com feedback humano.

Este script carrega dataset base, enriquece com feedback, treina modelo,
avalia performance e promove para produção se melhor que baseline.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple
import structlog
import pandas as pd
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score, recall_score, f1_score, accuracy_score, confusion_matrix
import mlflow
import mlflow.sklearn
from pymongo import MongoClient

logger = structlog.get_logger()


def parse_args():
    """Parse argumentos CLI."""
    parser = argparse.ArgumentParser(
        description="Treinar modelo de especialista com feedback humano"
    )
    parser.add_argument(
        '--specialist-type',
        type=str,
        required=True,
        help="Tipo do especialista"
    )
    parser.add_argument(
        '--feedback-count',
        type=int,
        default=0,
        help="Quantidade de feedbacks disponíveis (informativo)"
    )
    parser.add_argument(
        '--window-days',
        type=int,
        default=30,
        help="Janela de feedbacks a incluir"
    )
    parser.add_argument(
        '--min-feedback-quality',
        type=float,
        default=0.5,
        help="Rating mínimo para incluir feedback"
    )
    parser.add_argument(
        '--model-type',
        type=str,
        default='random_forest',
        choices=['random_forest', 'gradient_boosting', 'neural_network'],
        help="Tipo de modelo a treinar"
    )
    parser.add_argument(
        '--hyperparameter-tuning',
        type=str,
        default='false',
        choices=['true', 'false'],
        help="Habilitar tuning de hiperparâmetros"
    )
    parser.add_argument(
        '--promote-if-better',
        type=str,
        default='true',
        choices=['true', 'false'],
        help="Promover automaticamente se melhor que baseline"
    )

    return parser.parse_args()


def load_base_dataset(specialist_type: str, dataset_path_template: str) -> Tuple[pd.DataFrame, str]:
    """
    Carrega dataset base de treinamento.

    Args:
        specialist_type: Tipo do especialista
        dataset_path_template: Template do path (com {specialist_type})

    Returns:
        Tupla (DataFrame com features e labels, data_source)
        - data_source: 'synthetic' se usou dados sintéticos, ou path do arquivo real
    """
    dataset_path = dataset_path_template.format(specialist_type=specialist_type)

    logger.info(
        "Loading base dataset",
        specialist_type=specialist_type,
        path=dataset_path
    )

    # Verificar se arquivo existe
    if not os.path.exists(dataset_path):
        # Verificar se fallback para sintético está habilitado
        allow_synthetic = os.getenv('ALLOW_SYNTHETIC_FALLBACK', 'true').lower() == 'true'
        environment = os.getenv('ENVIRONMENT', 'development')

        if not allow_synthetic and environment == 'production':
            raise FileNotFoundError(
                f"Dataset não encontrado em {dataset_path} e ALLOW_SYNTHETIC_FALLBACK=false em production. "
                f"Configure o dataset real ou defina ALLOW_SYNTHETIC_FALLBACK=true."
            )

        logger.warning(
            "Base dataset not found - using synthetic data",
            path=dataset_path,
            environment=environment,
            allow_synthetic=allow_synthetic
        )
        # Criar dataset sintético para desenvolvimento
        df = create_synthetic_dataset(n_samples=1000)
        return df, 'synthetic'

    # Carregar Parquet
    df = pd.read_parquet(dataset_path)

    logger.info(
        "Base dataset loaded",
        size=len(df),
        columns=list(df.columns),
        data_source=dataset_path
    )

    return df, dataset_path


def create_synthetic_dataset(n_samples: int = 1000) -> pd.DataFrame:
    """
    Cria dataset sintético para desenvolvimento/teste.

    Args:
        n_samples: Número de amostras

    Returns:
        DataFrame com features sintéticas
    """
    logger.info("Creating synthetic dataset", n_samples=n_samples)

    np.random.seed(42)

    # 26 features simuladas
    data = {
        # Cognitive features
        'cognitive_complexity': np.random.uniform(0, 1, n_samples),
        'abstraction_level': np.random.uniform(0, 1, n_samples),
        'reasoning_depth': np.random.randint(1, 6, n_samples),

        # Opinion features
        'confidence_score': np.random.beta(5, 2, n_samples),
        'risk_score': np.random.beta(2, 5, n_samples),
        'priority': np.random.choice(['low', 'medium', 'high', 'critical'], n_samples),

        # Agreement features
        'consensus_agreement': np.random.choice([0, 1], n_samples, p=[0.3, 0.7]),
        'specialist_agreement_rate': np.random.uniform(0.5, 1, n_samples),

        # Features adicionais para completar 26
        **{f'feature_{i}': np.random.randn(n_samples) for i in range(18)}
    }

    df = pd.DataFrame(data)

    # Converter priority para numérico
    df['priority_numeric'] = df['priority'].map({
        'low': 0, 'medium': 1, 'high': 2, 'critical': 3
    })
    df = df.drop('priority', axis=1)

    # Label: consensus_agreement
    df['label'] = df['consensus_agreement']

    return df


def load_feedback_data(
    specialist_type: str,
    window_days: int,
    min_quality: float
) -> pd.DataFrame:
    """
    Carrega feedbacks do MongoDB e converte para features.

    Args:
        specialist_type: Tipo do especialista
        window_days: Janela de tempo
        min_quality: Rating mínimo

    Returns:
        DataFrame com features extraídas de feedback
    """
    try:
        mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
        client = MongoClient(mongodb_uri)
        db = client['neural_hive']

        cutoff_date = datetime.utcnow() - timedelta(days=window_days)

        # Query feedbacks
        feedbacks = list(db.specialist_feedback.find({
            'specialist_type': specialist_type,
            'submitted_at': {'$gte': cutoff_date},
            'human_rating': {'$gte': min_quality}
        }))

        logger.info(
            "Feedbacks loaded from MongoDB",
            specialist_type=specialist_type,
            count=len(feedbacks)
        )

        if not feedbacks:
            return pd.DataFrame()

        # Converter para DataFrame
        feedback_df = pd.DataFrame(feedbacks)

        # Para cada feedback, buscar opinião correspondente e extrair features
        opinions_collection = db.cognitive_ledger

        enriched_rows = []
        for _, feedback in feedback_df.iterrows():
            opinion = opinions_collection.find_one({'opinion_id': feedback['opinion_id']})

            if not opinion:
                continue

            # Extrair features da opinião
            features = extract_features_from_opinion(opinion)

            # Label baseado em concordância humana
            features['label'] = 1 if feedback['human_recommendation'] == opinion.get('recommendation') else 0

            enriched_rows.append(features)

        if not enriched_rows:
            return pd.DataFrame()

        feedback_features_df = pd.DataFrame(enriched_rows)

        logger.info(
            "Feedback features extracted",
            size=len(feedback_features_df)
        )

        return feedback_features_df

    except Exception as e:
        logger.error(
            "Failed to load feedback data",
            error=str(e)
        )
        return pd.DataFrame()


def extract_features_from_opinion(opinion: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrai features de uma opinião para treinamento.

    Args:
        opinion: Documento de opinião do MongoDB

    Returns:
        Dict com features
    """
    features = {}

    # Features cognitivas básicas
    cognitive_plan = opinion.get('cognitive_plan', {})
    features['cognitive_complexity'] = len(str(cognitive_plan).split())/ 1000.0
    features['abstraction_level'] = opinion.get('abstraction_level', 0.5)
    features['reasoning_depth'] = opinion.get('reasoning_depth', 3)

    # Features de opinião
    features['confidence_score'] = opinion.get('confidence_score', 0.5)
    features['risk_score'] = opinion.get('risk_score', 0.5)

    # Priority mapping
    priority_map = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
    features['priority_numeric'] = priority_map.get(opinion.get('priority', 'medium'), 1)

    # Features de consenso (se disponíveis)
    features['consensus_agreement'] = opinion.get('consensus_agreement', 0.7)
    features['specialist_agreement_rate'] = opinion.get('specialist_agreement_rate', 0.7)

    # Preencher features restantes com valores padrão
    for i in range(18):
        features[f'feature_{i}'] = np.random.randn()

    return features


def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    model_type: str,
    hyperparameter_tuning: bool
) -> Any:
    """
    Treina modelo baseado no tipo especificado.

    Args:
        X_train: Features de treinamento
        y_train: Labels de treinamento
        model_type: Tipo de modelo
        hyperparameter_tuning: Habilitar tuning

    Returns:
        Modelo treinado
    """
    logger.info(
        "Training model",
        model_type=model_type,
        n_samples=len(X_train),
        hyperparameter_tuning=hyperparameter_tuning
    )

    if model_type == 'random_forest':
        if hyperparameter_tuning:
            from sklearn.model_selection import GridSearchCV
            param_grid = {
                'n_estimators': [50, 100, 200],
                'max_depth': [5, 10, 20],
                'min_samples_split': [2, 5, 10]
            }
            base_model = RandomForestClassifier(random_state=42)
            model = GridSearchCV(base_model, param_grid, cv=3, n_jobs=-1)
        else:
            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42
            )

    elif model_type == 'gradient_boosting':
        if hyperparameter_tuning:
            from sklearn.model_selection import GridSearchCV
            param_grid = {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.1, 0.2],
                'max_depth': [3, 5, 7]
            }
            base_model = GradientBoostingClassifier(random_state=42)
            model = GridSearchCV(base_model, param_grid, cv=3, n_jobs=-1)
        else:
            model = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                random_state=42
            )

    elif model_type == 'neural_network':
        model = MLPClassifier(
            hidden_layer_sizes=(100, 50),
            max_iter=500,
            random_state=42
        )

    else:
        raise ValueError(f"Unknown model type: {model_type}")

    # Treinar
    model.fit(X_train, y_train)

    logger.info("Model training completed")

    return model


def evaluate_model(
    model: Any,
    X_val: pd.DataFrame,
    y_val: pd.Series
) -> Dict[str, float]:
    """
    Avalia modelo em dataset de validação.

    Args:
        model: Modelo treinado
        X_val: Features de validação
        y_val: Labels de validação

    Returns:
        Dict com métricas
    """
    y_pred = model.predict(X_val)

    metrics = {
        'precision': precision_score(y_val, y_pred, average='binary', zero_division=0),
        'recall': recall_score(y_val, y_pred, average='binary', zero_division=0),
        'f1': f1_score(y_val, y_pred, average='binary', zero_division=0),
        'accuracy': accuracy_score(y_val, y_pred)
    }

    logger.info(
        "Model evaluated",
        **metrics
    )

    return metrics


def get_baseline_model(specialist_type: str) -> Tuple[Any, Dict[str, float]]:
    """
    Busca modelo baseline atual em Production.

    Args:
        specialist_type: Tipo do especialista

    Returns:
        Tupla (modelo, métricas) ou (None, None)
    """
    try:
        model_name = f"{specialist_type}-evaluator"

        # Tentar carregar modelo de Production
        model_uri = f"models:/{model_name}/Production"
        model = mlflow.pyfunc.load_model(model_uri)

        # Buscar métricas do modelo
        client = mlflow.tracking.MlflowClient()
        versions = client.search_model_versions(f"name='{model_name}'")

        baseline_metrics = None
        for version in versions:
            if version.current_stage == 'Production':
                run = client.get_run(version.run_id)
                baseline_metrics = {
                    'precision': run.data.metrics.get('precision', 0.0),
                    'recall': run.data.metrics.get('recall', 0.0),
                    'f1': run.data.metrics.get('f1', 0.0)
                }
                break

        logger.info(
            "Baseline model loaded",
            model_name=model_name,
            metrics=baseline_metrics
        )

        return model, baseline_metrics

    except Exception as e:
        logger.warning(
            "No baseline model found",
            specialist_type=specialist_type,
            error=str(e)
        )
        return None, None


def should_promote_model(
    new_metrics: Dict[str, float],
    baseline_metrics: Dict[str, float],
    precision_threshold: float = 0.75,
    recall_threshold: float = 0.70,
    f1_threshold: float = 0.72,
    improvement_threshold: float = None
) -> bool:
    """
    Determina se modelo deve ser promovido.

    Args:
        new_metrics: Métricas do novo modelo
        baseline_metrics: Métricas do baseline
        precision_threshold: Precision mínima
        recall_threshold: Recall mínimo
        f1_threshold: F1 score mínimo
        improvement_threshold: Melhoria mínima sobre baseline (default: env MODEL_IMPROVEMENT_THRESHOLD ou 0.05)

    Returns:
        True se deve promover
    """
    # Carregar improvement_threshold de env var se não fornecido
    if improvement_threshold is None:
        improvement_threshold = float(os.getenv('MODEL_IMPROVEMENT_THRESHOLD', '0.05'))

    logger.info(
        "Checking promotion criteria",
        precision_threshold=precision_threshold,
        recall_threshold=recall_threshold,
        f1_threshold=f1_threshold,
        improvement_threshold=improvement_threshold
    )

    # Verificar thresholds absolutos
    if new_metrics['precision'] < precision_threshold:
        logger.info(
            "Model not promoted - precision below threshold",
            precision=new_metrics['precision'],
            threshold=precision_threshold
        )
        return False

    if new_metrics['recall'] < recall_threshold:
        logger.info(
            "Model not promoted - recall below threshold",
            recall=new_metrics['recall'],
            threshold=recall_threshold
        )
        return False

    if new_metrics['f1'] < f1_threshold:
        logger.info(
            "Model not promoted - F1 score below threshold",
            f1=new_metrics['f1'],
            threshold=f1_threshold
        )
        return False

    # Se não há baseline, promover
    if not baseline_metrics:
        logger.info("No baseline - promoting new model")
        return True

    # Comparar com baseline (novo deve ser improvement_threshold% melhor)
    precision_improvement = new_metrics['precision'] - baseline_metrics['precision']

    if precision_improvement >= improvement_threshold:
        logger.info(
            "Model promoted - significant improvement",
            precision_improvement=precision_improvement,
            improvement_threshold=improvement_threshold
        )
        return True

    logger.info(
        "Model not promoted - insufficient improvement",
        precision_improvement=precision_improvement,
        required=improvement_threshold
    )
    return False


def main():
    """Ponto de entrada principal."""
    args = parse_args()

    print(f"🤖 Neural Hive - Model Retraining Pipeline")
    print(f"   Specialist: {args.specialist_type}")
    print(f"   Model type: {args.model_type}")
    print(f"   Feedback count: {args.feedback_count}")
    print()

    # Configurar MLflow
    mlflow.set_tracking_uri(os.getenv('MLFLOW_TRACKING_URI', 'http://mlflow:5000'))
    experiment_name = f"{args.specialist_type}-specialist"
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run():
        # Log parâmetros
        mlflow.log_param('specialist_type', args.specialist_type)
        mlflow.log_param('model_type', args.model_type)
        mlflow.log_param('feedback_count', args.feedback_count)
        mlflow.log_param('window_days', args.window_days)
        mlflow.log_param('min_feedback_quality', args.min_feedback_quality)

        # 1. Carregar dataset base
        dataset_path_template = os.getenv(
            'TRAINING_DATASET_PATH',
            '/data/training/specialist_{specialist_type}_base.parquet'
        )
        df_base, data_source = load_base_dataset(args.specialist_type, dataset_path_template)
        mlflow.log_metric('base_dataset_size', len(df_base))

        # Logar data_source para rastreabilidade
        mlflow.log_param('data_source', data_source)
        mlflow.set_tag('data_source_type', 'synthetic' if data_source == 'synthetic' else 'real')

        if data_source == 'synthetic':
            print(f"⚠️  Using SYNTHETIC dataset for training")
            print(f"   Set TRAINING_DATASET_PATH to use real data")
        else:
            print(f"📁 Using REAL dataset: {data_source}")

        # 2. Carregar feedbacks
        df_feedback = load_feedback_data(
            args.specialist_type,
            args.window_days,
            args.min_feedback_quality
        )
        mlflow.log_metric('feedback_dataset_size', len(df_feedback))

        # 3. Enriquecer dataset
        if len(df_feedback) > 0:
            df_enriched = pd.concat([df_base, df_feedback], ignore_index=True)
        else:
            df_enriched = df_base

        mlflow.log_metric('total_dataset_size', len(df_enriched))

        print(f"📊 Dataset sizes:")
        print(f"   Base: {len(df_base)}")
        print(f"   Feedback: {len(df_feedback)}")
        print(f"   Total: {len(df_enriched)}")
        print()

        # 4. Split dataset
        X = df_enriched.drop('label', axis=1)
        y = df_enriched['label']

        X_train, X_temp, y_train, y_temp = train_test_split(
            X, y, test_size=0.3, random_state=42
        )
        X_val, X_test, y_val, y_test = train_test_split(
            X_temp, y_temp, test_size=0.33, random_state=42
        )

        print(f"📈 Splits:")
        print(f"   Train: {len(X_train)}")
        print(f"   Validation: {len(X_val)}")
        print(f"   Test: {len(X_test)}")
        print()

        # 5. Treinar modelo
        print(f"🔧 Training {args.model_type} model...")
        model = train_model(
            X_train, y_train,
            args.model_type,
            args.hyperparameter_tuning == 'true'
        )

        # 6. Avaliar modelo
        print(f"📊 Evaluating model...")
        metrics = evaluate_model(model, X_val, y_val)

        # Log métricas
        for metric_name, value in metrics.items():
            mlflow.log_metric(metric_name, value)

        print(f"   Precision: {metrics['precision']:.3f}")
        print(f"   Recall: {metrics['recall']:.3f}")
        print(f"   F1: {metrics['f1']:.3f}")
        print()

        # 7. Registrar modelo usando mlflow.sklearn.log_model para garantir flavor correto
        print(f"💾 Registering model...")
        model_name = f"{args.specialist_type}-evaluator"

        # Usar mlflow.sklearn.log_model para criar artifact com flavor sklearn/pyfunc
        # Isso garante que MLmodel seja criado e o modelo possa ser carregado via mlflow.pyfunc.load_model
        try:
            mlflow.sklearn.log_model(
                sk_model=model,
                artifact_path="model",
                registered_model_name=model_name
            )
            print(f"   ✅ Model registered as {model_name} with sklearn flavor")
        except Exception as e:
            logger.warning(f"Could not register model with sklearn flavor: {e}")
            # Fallback: logar modelo sem registrar no Model Registry
            mlflow.sklearn.log_model(
                sk_model=model,
                artifact_path="model"
            )
            print(f"   ⚠️  Model logged but not registered in Model Registry")
            print(f"   💡 You can manually register using mlflow.register_model()")

        run_id = mlflow.active_run().info.run_id
        model_uri = f"runs:/{run_id}/model"

        # 8. Comparar com baseline e promover
        if args.promote_if_better == 'true':
            print(f"🔍 Checking if model should be promoted...")

            baseline_model, baseline_metrics = get_baseline_model(args.specialist_type)

            if should_promote_model(metrics, baseline_metrics or {}):
                print(f"✅ Promoting model to Production...")

                client = mlflow.tracking.MlflowClient()
                run_id = mlflow.active_run().info.run_id

                # Buscar version do modelo recém-registrado
                versions = client.search_model_versions(f"name='{model_name}'")
                latest_version = max([int(v.version) for v in versions])

                # Arquivar versões anteriores em Production (Comment 5 - alinhado com Job e promote_model.py)
                archived_versions = []
                for v in versions:
                    if v.current_stage == 'Production':
                        client.transition_model_version_stage(
                            name=model_name,
                            version=v.version,
                            stage='Archived',
                            archive_existing_versions=False
                        )
                        archived_versions.append(v.version)
                        print(f"   📦 Archived previous version v{v.version}")

                # Promover para Production
                client.transition_model_version_stage(
                    name=model_name,
                    version=latest_version,
                    stage="Production",
                    archive_existing_versions=False  # Já arquivamos manualmente
                )

                mlflow.log_param('promoted', 'true')
                mlflow.log_param('archived_versions', str(archived_versions))
                print(f"   Model version {latest_version} promoted to Production")
                if archived_versions:
                    print(f"   📋 Archived versions: {archived_versions}")
            else:
                print(f"ℹ️  Model kept in Staging - performance below threshold")
                mlflow.log_param('promoted', 'false')

        print()
        print(f"✅ Retraining pipeline completed")
        print(f"   Run ID: {mlflow.active_run().info.run_id}")


if __name__ == '__main__':
    main()
