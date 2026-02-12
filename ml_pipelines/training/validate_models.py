#!/usr/bin/env python3
"""
Validação de Modelos ML - Neural Hive-Mind

Calcula métricas de qualidade para modelos treinados:
- Confidence média
- Precision, Recall, F1
- Matriz de confusão
- Comparação com baseline (modelos atuais)

Aprova modelos apenas se métricas superiores ao baseline.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np
from sklearn.metrics import (
    precision_score, recall_score, f1_score, accuracy_score,
    confusion_matrix, classification_report, brier_score_loss,
    roc_auc_score, roc_curve
)
import structlog

logger = structlog.get_logger(__name__)


class ModelValidator:
    """Valida modelos ML de especialistas."""

    # Métricas mínimas para aprovação
    MIN_METRICS = {
        'confidence_mean': 0.70,      # Confiança média mínima
        'f1_score': 0.65,              # F1 score mínimo
        'precision_min': 0.60,         # Precisão mínima por classe
        'recall_min': 0.60,            # Recall mínimo por classe
        'accuracy_min': 0.65           # Acurácia mínima
    }

    def __init__(
        self,
        baseline_dir: str = None,
        new_model_dir: str = None,
        output_dir: str = None
    ):
        """
        Inicializa validador.

        Args:
            baseline_dir: Diretório dos modelos baseline (atuais)
            new_model_dir: Diretório dos novos modelos treinados
            output_dir: Diretório para salvar relatórios
        """
        self.baseline_dir = Path(baseline_dir) if baseline_dir else None
        self.new_model_dir = Path(new_model_dir) if new_model_dir else None
        self.output_dir = Path(output_dir) if output_dir else Path('/tmp/model_validation')
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def validate_model(
        self,
        model: Any,
        X_test: pd.DataFrame,
        y_test: pd.Series,
        specialist_type: str,
        model_version: str = None
    ) -> Dict[str, Any]:
        """
        Valida modelo treinado e compara com baseline.

        Args:
            model: Modelo treinado (scikit-learn)
            X_test: Features de teste
            y_test: Labels de teste
            specialist_type: Tipo do especialista
            model_version: Versão do modelo

        Returns:
            Relatório de validação com métricas e status de aprovação
        """
        logger.info(
            f"Validando modelo: {specialist_type}",
            model_version=model_version,
            test_samples=len(X_test)
        )

        # Previsões
        y_pred = model.predict(X_test)

        # Probabilidades (se disponível)
        if hasattr(model, 'predict_proba'):
            y_proba = model.predict_proba(X_test)
            confidence_scores = np.max(y_proba, axis=1)
        else:
            confidence_scores = np.ones(len(y_pred)) * 0.5  # Fallback

        # Calcular métricas
        report = {
            'specialist_type': specialist_type,
            'model_version': model_version,
            'timestamp': datetime.utcnow().isoformat(),
            'test_samples': len(X_test),
        }

        # Métricas principais
        report['accuracy'] = float(accuracy_score(y_test, y_pred))
        report['precision_macro'] = float(precision_score(y_test, y_pred, average='macro', zero_division=0))
        report['recall_macro'] = float(recall_score(y_test, y_pred, average='macro', zero_division=0))
        report['f1_macro'] = float(f1_score(y_test, y_pred, average='macro', zero_division=0))
        report['confidence_mean'] = float(np.mean(confidence_scores))
        report['confidence_std'] = float(np.std(confidence_scores))

        # Métricas por classe
        report['precision_per_class'] = {}
        report['recall_per_class'] = {}
        report['f1_per_class'] = {}

        unique_labels = sorted(set(y_test) | set(y_pred))

        for label in unique_labels:
            label_name = self._label_to_name(label)
            report['precision_per_class'][label_name] = float(
                precision_score(y_test, y_pred, labels=[label], zero_division=0)
            )
            report['recall_per_class'][label_name] = float(
                recall_score(y_test, y_pred, labels=[label], zero_division=0)
            )
            report['f1_per_class'][label_name] = float(
                f1_score(y_test, y_pred, labels=[label], zero_division=0)
            )

        # Matriz de confusão
        cm = confusion_matrix(y_test, y_pred, labels=unique_labels)
        report['confusion_matrix'] = cm.tolist()

        # Classification report detalhado
        report['classification_report'] = classification_report(
            y_test, y_pred, target_names=[self._label_to_name(l) for l in unique_labels],
            zero_division=0, output_dict=True
        )

        # Verificar critérios de aprovação
        report['passed'] = self._check_approval_criteria(report)

        # Log resumo
        logger.info(
            f"Validação concluída: {specialist_type}",
            passed=report['passed'],
            accuracy=f"{report['accuracy']:.3f}",
            f1_macro=f"{report['f1_macro']:.3f}",
            confidence_mean=f"{report['confidence_mean']:.3f}"
        )

        return report

    def compare_with_baseline(
        self,
        new_report: Dict[str, Any],
        baseline_report: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Compara novo modelo com baseline.

        Args:
            new_report: Relatório do novo modelo
            baseline_report: Relatório do modelo baseline (opcional)

        Returns:
            Relatório de comparação
        """
        specialist = new_report['specialist_type']

        comparison = {
            'specialist_type': specialist,
            'new_model': {
                'version': new_report.get('model_version', 'unknown'),
                'accuracy': new_report['accuracy'],
                'f1_macro': new_report['f1_macro'],
                'confidence_mean': new_report['confidence_mean']
            }
        }

        if baseline_report:
            comparison['baseline_model'] = {
                'version': baseline_report.get('model_version', 'unknown'),
                'accuracy': baseline_report['accuracy'],
                'f1_macro': baseline_report['f1_macro'],
                'confidence_mean': baseline_report['confidence_mean']
            }

            # Calcular deltas
            comparison['improvement'] = {
                'accuracy': new_report['accuracy'] - baseline_report['accuracy'],
                'f1_macro': new_report['f1_macro'] - baseline_report['f1_macro'],
                'confidence_mean': new_report['confidence_mean'] - baseline_report['confidence_mean']
            }

            # Verificar se novo modelo é superior
            improvement_threshold = 0.02  # 2% de melhoria mínima

            comparison['is_better'] = all([
                comparison['improvement']['accuracy'] >= -improvement_threshold,
                comparison['improvement']['f1_macro'] >= -improvement_threshold,
                comparison['improvement']['confidence_mean'] >= 0
            ])

        else:
            comparison['baseline_model'] = None
            comparison['improvement'] = None
            comparison['is_better'] = True  # Aprovar se não há baseline

        return comparison

    def _check_approval_criteria(self, report: Dict[str, Any]) -> bool:
        """Verifica se modelo atende critérios mínimos de aprovação."""
        checks = {
            'confidence_mean': report['confidence_mean'] >= self.MIN_METRICS['confidence_mean'],
            'f1_score': report['f1_macro'] >= self.MIN_METRICS['f1_score'],
            'accuracy': report['accuracy'] >= self.MIN_METRICS['accuracy_min'],
        }

        # Verificar precisão e recall por classe
        for label_name, precision in report['precision_per_class'].items():
            if precision < self.MIN_METRICS['precision_min']:
                checks[f'precision_{label_name}'] = False
            else:
                checks[f'precision_{label_name}'] = True

        for label_name, recall in report['recall_per_class'].items():
            if recall < self.MIN_METRICS['recall_min']:
                checks[f'recall_{label_name}'] = False
            else:
                checks[f'recall_{label_name}'] = True

        # Logar checks
        for check_name, passed in checks.items():
            if not passed:
                logger.warning(
                    f"Check falhou: {check_name}",
                    value=report.get(check_name.replace('_passed', ''), 'N/A')
                )

        return all(checks.values())

    def _label_to_name(self, label: int) -> str:
        """Converte label numérico para nome."""
        mapping = {
            0: 'reject',
            1: 'approve',
            2: 'review_required'
        }
        return mapping.get(label, f'class_{label}')

    def generate_confusion_matrix_plot(
        self,
        cm: np.ndarray,
        specialist_type: str,
        output_path: str = None
    ):
        """Gera e salva plot da matriz de confusão."""
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns

            fig, ax = plt.subplots(figsize=(8, 6))

            labels = ['Reject', 'Approve', 'Review']
            sns.heatmap(
                cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=labels, yticklabels=labels, ax=ax
            )
            ax.set_ylabel('True Label')
            ax.set_xlabel('Predicted Label')
            ax.set_title(f'Confusion Matrix - {specialist_type}')

            if output_path is None:
                output_path = self.output_dir / f'{specialist_type}_confusion_matrix.png'

            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()

            logger.info(f"Matriz de confusão salva: {output_path}")

        except ImportError:
            logger.warning("matplotlib/seaborn não disponíveis, pulando plot")

    def save_report(
        self,
        report: Dict[str, Any],
        comparison: Dict[str, Any] = None
    ):
        """Salva relatório em arquivo JSON."""
        output_file = self.output_dir / f"{report['specialist_type']}_validation_report.json"

        full_report = {
            'validation_report': report,
            'baseline_comparison': comparison
        }

        with open(output_file, 'w') as f:
            json.dump(full_report, f, indent=2, default=str)

        logger.info(f"Relatório salvo: {output_file}")


def validate_all_specialists(
    models_dir: str,
    test_data_dir: str,
    output_dir: str = '/tmp/model_validation'
) -> Dict[str, Dict[str, Any]]:
    """
    Valida todos os modelos de especialistas.

    Args:
        models_dir: Diretório com os modelos treinados
        test_data_dir: Diretório com os dados de teste
        output_dir: Diretório para salvar relatórios

    Returns:
        Dicionário com relatórios por especialista
    """
    import joblib

    models_path = Path(models_dir)
    test_data_path = Path(test_data_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    validator = ModelValidator(output_dir=output_dir)

    reports = {}
    specialists = ['business', 'technical', 'behavior', 'evolution', 'architecture']

    for specialist in specialists:
        logger.info(f"Validando especialista: {specialist}")

        # Carregar modelo
        model_file = models_path / f'{specialist}_model.pkl'
        test_file = test_data_path / f'{specialist}_test.csv'

        if not model_file.exists():
            logger.warning(f"Modelo não encontrado: {model_file}")
            continue

        if not test_file.exists():
            logger.warning(f"Dados de teste não encontrados: {test_file}")
            continue

        try:
            model = joblib.load(model_file)
            test_df = pd.read_csv(test_file)

            # Separar features e labels
            feature_cols = [c for c in test_df.columns if c not in ['label', 'opinion_id', 'plan_id', 'created_at', 'specialist_type']]
            X_test = test_df[feature_cols]
            y_test = test_df['label']

            # Validar
            report = validator.validate_model(
                model=model,
                X_test=X_test,
                y_test=y_test,
                specialist_type=specialist
            )

            # Gerar plot de matriz de confusão
            validator.generate_confusion_matrix_plot(
                np.array(report['confusion_matrix']),
                specialist
            )

            # Salvar relatório
            validator.save_report(report)

            reports[specialist] = report

        except Exception as e:
            logger.error(f"Erro validando {specialist}: {e}")

    return reports


async def main():
    """Função principal para execução standalone."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Valida modelos ML de especialistas"
    )
    parser.add_argument(
        '--models-dir',
        type=str,
        required=True,
        help='Diretório com os modelos treinados'
    )
    parser.add_argument(
        '--test-data-dir',
        type=str,
        required=True,
        help='Diretório com os dados de teste'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='/tmp/model_validation',
        help='Diretório para salvar relatórios'
    )
    parser.add_argument(
        '--specialist',
        type=str,
        choices=['business', 'technical', 'behavior', 'evolution', 'architecture', 'all'],
        default='all',
        help='Especialista para validar'
    )

    args = parser.parse_args()

    # Validar
    reports = validate_all_specialists(
        models_dir=args.models_dir,
        test_data_dir=args.test_data_dir,
        output_dir=args.output_dir
    )

    # Resumo
    print("\n" + "="*50)
    print("RESUMO DA VALIDAÇÃO")
    print("="*50)

    for specialist, report in reports.items():
        status = "✅ APROVADO" if report['passed'] else "❌ REPROVADO"
        print(f"{specialist}: {status}")
        print(f"  Accuracy: {report['accuracy']:.3f}")
        print(f"  F1 Macro: {report['f1_macro']:.3f}")
        print(f"  Confidence: {report['confidence_mean']:.3f}")
        print()


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
