#!/usr/bin/env python3
"""
Script de Retraining v7 - Approval Model

Este script treina o modelo ML de aprovação usando feedbacks coletados
com NLP features e salva o modelo para deploy.

Versão: v7
Features: 30+ incluindo NLP (domínios, ações, risco, etc.)
Data: 2026-03-16
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
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score, precision_score, recall_score
import warnings
warnings.filterwarnings('ignore')

# Configuração MongoDB
MONGO_URI = os.getenv(
    'MONGO_URI',
    'mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin'
)
DATABASE = os.getenv('MONGODB_DATABASE', 'neural_hive')
MODEL_OUTPUT_DIR = Path(os.getenv('MODEL_OUTPUT_DIR', Path(__file__).parent.parent.parent / 'ml_models'))
MODEL_VERSION_PREFIX = "v7"


def extract_nlp_features(nlp_dict):
    """Extrai features do dicionário nlp_features para dataframe"""
    if not nlp_dict or not isinstance(nlp_dict, dict):
        return {}

    features = {}

    # Domínios
    features['domain_security'] = float(nlp_dict.get('domain_security', 0.0))
    features['domain_performance'] = float(nlp_dict.get('domain_performance', 0.0))
    features['domain_database'] = float(nlp_dict.get('domain_database', 0.0))
    features['domain_devops'] = float(nlp_dict.get('domain_devops', 0.0))
    features['domain_testing'] = float(nlp_dict.get('domain_testing', 0.0))

    # Ações
    features['action_create'] = float(nlp_dict.get('action_create', 0.0))
    features['action_update'] = float(nlp_dict.get('action_update', 0.0))
    features['action_delete'] = float(nlp_dict.get('action_delete', 0.0))
    features['action_read'] = float(nlp_dict.get('action_read', 0.0))
    features['action_deploy'] = float(nlp_dict.get('action_deploy', 0.0))

    # Palavras-chave
    features['has_backup'] = float(nlp_dict.get('has_backup', 0.0))
    features['has_verification'] = float(nlp_dict.get('has_verification', 0.0))
    features['has_all'] = float(nlp_dict.get('has_all', 0.0))

    # Métricas de texto
    features['text_length_chars'] = int(nlp_dict.get('text_length_chars', 0))
    features['text_length_words'] = int(nlp_dict.get('text_length_words', 0))

    # Risco
    features['risk_high'] = float(nlp_dict.get('risk_high', 0.0))
    features['risk_medium'] = float(nlp_dict.get('risk_medium', 0.0))
    features['risk_low'] = float(nlp_dict.get('risk_low', 0.0))
    features['simple_risk_score'] = float(nlp_dict.get('simple_risk_score', 0.0))

    # Domínio e ação primários
    primary_domain = nlp_dict.get('primary_domain', '')
    for domain in ['security', 'performance', 'database', 'devops', 'testing']:
        features[f'primary_domain_{domain}'] = 1.0 if primary_domain == domain else 0.0

    primary_action = nlp_dict.get('primary_action', '')
    for action in ['create', 'update', 'delete', 'read', 'deploy']:
        features[f'primary_action_{action}'] = 1.0 if primary_action == action else 0.0

    return features


def load_feedback_data(min_samples: int = 20):
    """Carrega feedbacks do MongoDB com NLP features"""
    print("Carregando feedbacks do MongoDB...")

    client = MongoClient(MONGO_URI)
    db = client[DATABASE]

    # Buscar feedbacks com NLP features
    cursor = db['specialist_feedback'].find({
        'nlp_features': {'$exists': True, '$ne': {}},
        'final_decision': {'$exists': True, '$ne': None, '$ne': ''}
    })

    feedbacks = list(cursor)
    print(f"Encontrados: {len(feedbacks)} feedbacks válidos")

    if len(feedbacks) < min_samples:
        raise ValueError(f"Amostras insuficientes: {len(feedbacks)} < {min_samples}")

    return feedbacks


def prepare_dataframe(feedbacks):
    """Prepara dataframe para treinamento"""
    print("Preparando dataframe...")

    data = []
    for fb in feedbacks:
        nlp_features = extract_nlp_features(fb.get('nlp_features', {}))
        row = {
            'final_decision': fb.get('final_decision'),
            'specialist_confidence': float(fb.get('confidence_score', 0.5)),
            **nlp_features
        }
        data.append(row)

    df = pd.DataFrame(data)

    print(f"Dataframe shape: {df.shape}")
    print(f"Distribuicao de classes:")
    for decision, count in df['final_decision'].value_counts().items():
        print(f"  {decision}: {count}")

    return df


def get_next_version():
    """Determina a próxima versão do modelo"""
    client = MongoClient(MONGO_URI)
    db = client[DATABASE]

    # Buscar última versão treinada
    last_model = db['model_metadata'].find_one(
        {'type': 'approval_model'},
        sort=[('trained_at', -1)]
    )

    if last_model and last_model.get('version'):
        last_version = last_model['version']
        if last_version.startswith('v'):
            try:
                version_num = int(last_version[1:])
                return f"v{version_num + 1}"
            except ValueError:
                pass

    return MODEL_VERSION_PREFIX


def train_and_save_model(df, version: str):
    """Treina o modelo e salva em disco"""
    print()
    print("=" * 60)
    print("TREINANDO MODELO")
    print("=" * 60)

    # Separar features e target
    feature_cols = [col for col in df.columns if col != 'final_decision']
    X = df[feature_cols].fillna(0)
    y = df['final_decision']

    # Dividir em treino e teste
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    print(f"\nConjunto de treino: {X_train.shape}")
    print(f"Conjunto de teste: {X_test.shape}")

    # Treinar RandomForest
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=42,
        class_weight='balanced',
        min_samples_leaf=2
    )

    model.fit(X_train, y_train)

    # Avaliar
    y_pred = model.predict(X_test)

    f1 = f1_score(y_test, y_pred, average='weighted')
    precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
    recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)

    print(f"\nMétricas no conjunto de teste:")
    print(f"  F1-Score: {f1:.4f}")
    print(f"  Precision: {precision:.4f}")
    print(f"  Recall: {recall:.4f}")

    # Feature importances
    print(f"\nTop 10 Features:")
    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1][:10]

    for idx in indices:
        print(f"  {feature_cols[idx]}: {importances[idx]:.4f}")

    # Salvar modelo
    MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_OUTPUT_DIR / f"nhm_approval_model_{version}.pkl"

    model_data = {
        'model': model,
        'version': version,
        'trained_at': datetime.now().isoformat(),
        'features': feature_cols.tolist(),
        'metrics': {
            'f1_score': f1,
            'precision': precision,
            'recall': recall
        },
        'training_samples': len(df)
    }

    with open(model_path, 'wb') as f:
        pickle.dump(model_data, f)

    print(f"\nModelo salvo em: {model_path}")

    # Salvar metadata no MongoDB
    client = MongoClient(MONGO_URI)
    db = client[DATABASE]

    db['model_metadata'].update_one(
        {'type': 'approval_model', 'version': version},
        {'$set': {
            'type': 'approval_model',
            'version': version,
            'trained_at': datetime.now().isoformat(),
            'features': feature_cols.tolist(),
            'metrics': {
                'f1_score': f1,
                'precision': precision,
                'recall': recall
            },
            'training_samples': len(df)
        }},
        upsert=True
    )

    print(f"Metadata salvo no MongoDB")

    return model_data


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Retraining do Approval Model v7')
    parser.add_argument('--min-samples', type=int, default=20, help='Amostras mínimas')
    parser.add_argument('--version', type=str, default=None, help='Versão do modelo (auto se não especificado)')
    parser.add_argument('--dry-run', action='store_true', help='Apenas verificar dados')
    args = parser.parse_args()

    print("=" * 60)
    print("RETRAINING APPROVAL MODEL")
    print("=" * 60)
    print(f"Data: {datetime.now().isoformat()}")
    print()

    try:
        # Carregar dados
        feedbacks = load_feedback_data(args.min_samples)
        df = prepare_dataframe(feedbacks)

        if args.dry_run:
            print("\nDRY RUN - Dados válidos para treinamento")
            return 0

        # Determinar versão
        version = args.version or get_next_version()

        # Treinar e salvar
        model_data = train_and_save_model(df, version)

        print()
        print("=" * 60)
        print("RETRAINING CONCLUIDO")
        print("=" * 60)
        print(f"Versão: {version}")
        print(f"F1-Score: {model_data['metrics']['f1_score']:.4f}")
        print(f"Amostras: {model_data['training_samples']}")
        print()
        print("Para fazer deploy:")
        print(f"  1. Atualizar Dockerfile para copiar nhm_approval_model_{version}.pkl")
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
