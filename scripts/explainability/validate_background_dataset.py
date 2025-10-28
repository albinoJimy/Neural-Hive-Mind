#!/usr/bin/env python3
"""
Valida background dataset SHAP.

Verifica:
- Formato Parquet válido
- Número mínimo de amostras
- Ausência de NaN/Inf
- Variância adequada em features
- Distribuição de valores
- Correlação entre features

Uso:
    python validate_background_dataset.py \
        --dataset-path /data/shap_background.parquet \
        --min-samples 50 \
        --min-variance 0.001
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import structlog
from typing import Dict, List, Tuple

logger = structlog.get_logger()


def load_dataset(dataset_path: str) -> pd.DataFrame:
    """Carrega dataset Parquet."""
    logger.info("Loading dataset", path=dataset_path)

    try:
        df = pd.read_parquet(dataset_path)
        logger.info(
            "Dataset loaded",
            shape=df.shape,
            columns=list(df.columns)
        )
        return df
    except Exception as e:
        logger.error("Failed to load dataset", error=str(e))
        raise


def check_sample_count(df: pd.DataFrame, min_samples: int) -> Tuple[bool, str]:
    """Verifica número mínimo de amostras."""
    num_samples = len(df)

    if num_samples < min_samples:
        return False, f"Insufficient samples: {num_samples} < {min_samples}"

    return True, f"Sample count OK: {num_samples} >= {min_samples}"


def check_missing_values(df: pd.DataFrame) -> Tuple[bool, str]:
    """Verifica valores ausentes (NaN/Inf)."""
    nan_count = df.isna().sum().sum()
    inf_count = np.isinf(df.select_dtypes(include=[np.number])).sum().sum()

    if nan_count > 0:
        return False, f"Dataset contains {nan_count} NaN values"

    if inf_count > 0:
        return False, f"Dataset contains {inf_count} Inf values"

    return True, "No missing or infinite values"


def check_feature_variance(df: pd.DataFrame, min_variance: float) -> Tuple[bool, str]:
    """Verifica variância mínima em features."""
    low_variance_features = []

    for col in df.select_dtypes(include=[np.number]).columns:
        variance = df[col].var()
        if variance < min_variance:
            low_variance_features.append((col, variance))

    if low_variance_features:
        features_str = ', '.join([f"{col}({var:.6f})" for col, var in low_variance_features])
        return False, f"Low variance features: {features_str}"

    return True, "All features have adequate variance"


def check_feature_distributions(df: pd.DataFrame) -> Tuple[bool, str]:
    """Verifica distribuições de features."""
    issues = []

    for col in df.select_dtypes(include=[np.number]).columns:
        # Verificar se feature é constante
        if df[col].nunique() == 1:
            issues.append(f"{col} is constant")

        # Verificar outliers extremos (> 10 desvios padrão)
        mean = df[col].mean()
        std = df[col].std()
        if std > 0:
            outliers = df[(df[col] - mean).abs() > 10 * std]
            if len(outliers) > 0:
                issues.append(f"{col} has {len(outliers)} extreme outliers")

    if issues:
        return False, f"Distribution issues: {'; '.join(issues)}"

    return True, "Feature distributions are reasonable"


def check_feature_correlations(df: pd.DataFrame, max_correlation: float = 0.95) -> Tuple[bool, str]:
    """Verifica correlações altas entre features."""
    numeric_df = df.select_dtypes(include=[np.number])
    corr_matrix = numeric_df.corr().abs()

    # Remover diagonal
    np.fill_diagonal(corr_matrix.values, 0)

    # Encontrar correlações altas
    high_corr_pairs = []
    for i in range(len(corr_matrix.columns)):
        for j in range(i + 1, len(corr_matrix.columns)):
            if corr_matrix.iloc[i, j] > max_correlation:
                high_corr_pairs.append(
                    (corr_matrix.columns[i], corr_matrix.columns[j], corr_matrix.iloc[i, j])
                )

    if high_corr_pairs:
        pairs_str = ', '.join([f"{f1}-{f2}({corr:.3f})" for f1, f2, corr in high_corr_pairs[:5]])
        return False, f"High correlations detected: {pairs_str}"

    return True, "No high correlations between features"


def generate_statistics_report(df: pd.DataFrame) -> Dict:
    """Gera relatório estatístico do dataset."""
    logger.info("Generating statistics report")

    numeric_df = df.select_dtypes(include=[np.number])

    report = {
        'num_samples': len(df),
        'num_features': len(df.columns),
        'num_numeric_features': len(numeric_df.columns),
        'memory_usage_mb': df.memory_usage(deep=True).sum() / (1024 * 1024),
        'feature_statistics': {}
    }

    # Estatísticas por feature
    for col in numeric_df.columns:
        report['feature_statistics'][col] = {
            'mean': float(numeric_df[col].mean()),
            'std': float(numeric_df[col].std()),
            'min': float(numeric_df[col].min()),
            'max': float(numeric_df[col].max()),
            'median': float(numeric_df[col].median()),
            'variance': float(numeric_df[col].var()),
            'nunique': int(numeric_df[col].nunique())
        }

    return report


def print_report(report: Dict):
    """Imprime relatório formatado."""
    print("\n" + "="*80)
    print("BACKGROUND DATASET STATISTICS REPORT")
    print("="*80)

    print(f"\nDataset Overview:")
    print(f"  Samples: {report['num_samples']}")
    print(f"  Features: {report['num_features']} ({report['num_numeric_features']} numeric)")
    print(f"  Memory Usage: {report['memory_usage_mb']:.2f} MB")

    print(f"\nTop 10 Features by Variance:")
    features_by_var = sorted(
        report['feature_statistics'].items(),
        key=lambda x: x[1]['variance'],
        reverse=True
    )[:10]

    for feature, stats in features_by_var:
        print(f"  {feature:30s} | var={stats['variance']:.6f} | mean={stats['mean']:.3f} | std={stats['std']:.3f}")

    print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(
        description='Validate SHAP background dataset'
    )
    parser.add_argument(
        '--dataset-path',
        required=True,
        help='Path to background dataset (Parquet)'
    )
    parser.add_argument(
        '--min-samples',
        type=int,
        default=50,
        help='Minimum number of samples required'
    )
    parser.add_argument(
        '--min-variance',
        type=float,
        default=0.001,
        help='Minimum variance required for features'
    )
    parser.add_argument(
        '--max-correlation',
        type=float,
        default=0.95,
        help='Maximum correlation allowed between features'
    )
    parser.add_argument(
        '--output-report',
        help='Path to save JSON report (optional)'
    )

    args = parser.parse_args()

    # Configurar logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer()
        ]
    )

    try:
        # Carregar dataset
        df = load_dataset(args.dataset_path)

        # Executar validações
        validations = [
            ("Sample Count", check_sample_count(df, args.min_samples)),
            ("Missing Values", check_missing_values(df)),
            ("Feature Variance", check_feature_variance(df, args.min_variance)),
            ("Feature Distributions", check_feature_distributions(df)),
            ("Feature Correlations", check_feature_correlations(df, args.max_correlation))
        ]

        # Imprimir resultados
        print("\n" + "="*80)
        print("VALIDATION RESULTS")
        print("="*80)

        all_passed = True
        for check_name, (passed, message) in validations:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"{status:8s} | {check_name:25s} | {message}")
            if not passed:
                all_passed = False

        print("="*80)

        # Gerar relatório estatístico
        report = generate_statistics_report(df)
        print_report(report)

        # Salvar relatório JSON se solicitado
        if args.output_report:
            import json
            with open(args.output_report, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info("Report saved", path=args.output_report)

        # Exit code
        if all_passed:
            logger.info("✓ All validations passed")
            sys.exit(0)
        else:
            logger.error("✗ Some validations failed")
            sys.exit(1)

    except Exception as e:
        logger.error("Validation failed", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
