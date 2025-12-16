#!/usr/bin/env python3
"""
Valida alinhamento de features entre treinamento e inferencia.

Este script verifica se:
1. FeatureExtractor gera features compativeis com o schema definido em feature_definitions.py
2. Datasets Parquet contem exatamente as features esperadas (sem extras, sem faltantes)

Nota: A validacao de modelos MLflow (signature, feature_schema.json) deve ser feita
separadamente via MLflow UI ou scripts dedicados apos o treinamento.
"""

import os
import sys
from pathlib import Path

# Configurar paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "libraries" / "python"))

import pandas as pd
from feature_store.feature_definitions import get_feature_names, get_feature_schema


def validate_feature_extractor():
    """Valida que FeatureExtractor gera features esperadas."""
    print("Validando FeatureExtractor...")

    try:
        from neural_hive_specialists.feature_extraction.feature_extractor import FeatureExtractor
    except ImportError as e:
        print(f"   Erro ao importar FeatureExtractor: {e}")
        return False

    # Criar plano dummy
    dummy_plan = {
        'plan_id': 'validation-test',
        'tasks': [
            {
                'task_id': '1',
                'task_type': 'analysis',
                'description': 'Test task for validation',
                'dependencies': [],
                'estimated_duration_ms': 1000
            }
        ],
        'original_domain': 'test-domain',
        'original_priority': 'normal',
        'risk_score': 0.5,
        'complexity_score': 0.5
    }

    # Extrair features
    try:
        extractor = FeatureExtractor()
        features = extractor.extract_features(dummy_plan)
        extracted_features = features.get('aggregated_features', {})
    except Exception as e:
        print(f"   Erro ao extrair features: {e}")
        return False

    # Comparar com schema esperado
    expected_features = set(get_feature_names())
    actual_features = set(extracted_features.keys())

    missing = expected_features - actual_features
    extra = actual_features - expected_features

    print(f"   Expected features: {len(expected_features)}")
    print(f"   Extracted features: {len(actual_features)}")

    if missing:
        print(f"   Missing features: {missing}")
    if extra:
        print(f"   Extra features: {extra}")

    if not missing and not extra:
        print("   FeatureExtractor alignment OK")
        return True
    else:
        print("   FeatureExtractor alignment FAILED")
        return False


def validate_dataset(dataset_path: str):
    """Valida schema de dataset Parquet."""
    print(f"\nValidando dataset: {dataset_path}")

    if not os.path.exists(dataset_path):
        print(f"   Dataset nao encontrado")
        return None  # Retorna None para indicar arquivo nao encontrado

    try:
        df = pd.read_parquet(dataset_path)

        expected_features = set(get_feature_names())
        actual_features = set(df.columns) - {'label'}

        missing = expected_features - actual_features
        extra = actual_features - expected_features

        print(f"   Samples: {len(df)}")
        print(f"   Expected features: {len(expected_features)}")
        print(f"   Actual features: {len(actual_features)}")

        if missing:
            print(f"   Missing features: {missing}")
        if extra:
            print(f"   Extra features: {extra}")

        if not missing and not extra:
            print("   Dataset schema OK")
            return True
        else:
            print("   Dataset schema FAILED")
            return False

    except Exception as e:
        print(f"   Error loading dataset: {e}")
        return False


def main():
    print("=" * 60)
    print("Feature Alignment Validation")
    print("=" * 60)

    # Validar FeatureExtractor
    extractor_ok = validate_feature_extractor()

    # Validar datasets
    specialists = ['technical', 'business', 'behavior', 'evolution', 'architecture']
    dataset_dir = os.getenv('DATASET_DIR', '/data/training')

    datasets_ok = True
    datasets_found = 0
    for specialist in specialists:
        dataset_path = f"{dataset_dir}/specialist_{specialist}_base.parquet"
        result = validate_dataset(dataset_path)
        if result is None:
            continue  # Arquivo nao encontrado, nao conta como falha
        datasets_found += 1
        if not result:
            datasets_ok = False

    print("\n" + "=" * 60)
    print("Resumo:")
    print(f"   FeatureExtractor: {'OK' if extractor_ok else 'FAILED'}")
    print(f"   Datasets encontrados: {datasets_found}/{len(specialists)}")
    if datasets_found > 0:
        print(f"   Datasets com schema valido: {'OK' if datasets_ok else 'FAILED'}")

    print("=" * 60)

    if extractor_ok and (datasets_found == 0 or datasets_ok):
        print("All validations PASSED")
        sys.exit(0)
    else:
        print("Some validations FAILED")
        sys.exit(1)


if __name__ == '__main__':
    main()
