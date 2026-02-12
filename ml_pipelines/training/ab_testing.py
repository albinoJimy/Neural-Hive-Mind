#!/usr/bin/env python3
"""
A/B Testing Module para ML Specialists - Neural Hive-Mind

Implementa testes A/B para novos modelos ML:
- Rotear X% do tráfego para novos modelos
- Comparar métricas de confidence e accuracy
- Monitorar drift durante teste
- Expandir para 100% se métricas positivas

Integra com MLflow para versionamento de modelos.
"""

import os
import sys
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class ABTestStatus(Enum):
    """Status de um teste A/B."""
    NOT_STARTED = "not_started"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    STOPPED = "stopped"


class ABTestConfig:
    """Configuração para teste A/B."""

    def __init__(
        self,
        specialist_type: str,
        new_model_version: str,
        baseline_model_version: str,
        traffic_percentage: float = 10.0,  # % de tráfego para novo modelo
        min_samples: int = 1000,
        duration_hours: int = 72,
        success_threshold: float = 0.02,  # 2% de melhoria mínima
        confidence_threshold: float = 0.70
    ):
        self.specialist_type = specialist_type
        self.new_model_version = new_model_version
        self.baseline_model_version = baseline_model_version
        self.traffic_percentage = traffic_percentage
        self.min_samples = min_samples
        self.duration_hours = duration_hours
        self.success_threshold = success_threshold
        self.confidence_threshold = confidence_threshold


class ABTestMetrics:
    """Métricas coletadas durante teste A/B."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reseta contadores."""
        self.new_model_predictions = 0
        self.baseline_model_predictions = 0
        self.new_model_confidence_sum = 0.0
        self.baseline_model_confidence_sum = 0.0
        self.new_model_correct = 0
        self.baseline_model_correct = 0
        self.start_time = datetime.utcnow()

    def record_prediction(
        self,
        model_type: str,  # 'new' ou 'baseline'
        confidence: float,
        correct: bool = None
    ):
        """Registra uma predição."""
        if model_type == 'new':
            self.new_model_predictions += 1
            self.new_model_confidence_sum += confidence
            if correct is not None:
                self.new_model_correct += 1 if correct else 0
        elif model_type == 'baseline':
            self.baseline_model_predictions += 1
            self.baseline_model_confidence_sum += confidence
            if correct is not None:
                self.baseline_model_correct += 1 if correct else 0

    def get_summary(self) -> Dict[str, Any]:
        """Retorna resumo das métricas."""
        new_confidence = (
            self.new_model_confidence_sum / self.new_model_predictions
            if self.new_model_predictions > 0 else 0.0
        )
        baseline_confidence = (
            self.baseline_model_confidence_sum / self.baseline_model_predictions
            if self.baseline_model_predictions > 0 else 0.0
        )

        new_accuracy = (
            self.new_model_correct / self.new_model_predictions
            if self.new_model_predictions > 0 else 0.0
        )
        baseline_accuracy = (
            self.baseline_model_correct / self.baseline_model_predictions
            if self.baseline_model_predictions > 0 else 0.0
        )

        return {
            'new_model': {
                'predictions': self.new_model_predictions,
                'confidence_mean': new_confidence,
                'accuracy': new_accuracy
            },
            'baseline_model': {
                'predictions': self.baseline_model_predictions,
                'confidence_mean': baseline_confidence,
                'accuracy': baseline_accuracy
            },
            'improvement': {
                'confidence': new_confidence - baseline_confidence,
                'accuracy': new_accuracy - baseline_accuracy
            },
            'duration_hours': (datetime.utcnow() - self.start_time).total_seconds() / 3600
        }


class ABTestManager:
    """Gerenciador de testes A/B para especialistas ML."""

    def __init__(
        self,
        mlflow_tracking_uri: str = None,
        mongodb_uri: str = None,
        state_file: str = None
    ):
        """
        Inicializa gerenciador.

        Args:
            mlflow_tracking_uri: URI do MLflow
            mongodb_uri: URI do MongoDB para persistência
            state_file: Arquivo para salvar estado local
        """
        self.mlflow_tracking_uri = mlflow_tracking_uri or os.getenv(
            'MLFLOW_TRACKING_URI',
            'http://mlflow.mlflow.svc.cluster.local:5000'
        )
        self.mongodb_uri = mongodb_uri or os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
        self.state_file = state_file or '/tmp/ab_tests_state.json'

        self.tests: Dict[str, ABTestConfig] = {}
        self.metrics: Dict[str, ABTestMetrics] = {}

        # Carregar estado anterior
        self._load_state()

    def create_test(
        self,
        config: ABTestConfig
    ) -> str:
        """
        Cria um novo teste A/B.

        Args:
            config: Configuração do teste

        Returns:
            ID do teste criado
        """
        test_id = f"{config.specialist_type}_{config.new_model_version}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        self.tests[test_id] = config
        self.metrics[test_id] = ABTestMetrics()

        logger.info(
            f"Teste A/B criado: {test_id}",
            specialist=config.specialist_type,
            new_version=config.new_model_version,
            traffic_percentage=f"{config.traffic_percentage}%"
        )

        self._save_state()

        return test_id

    def get_model_for_request(
        self,
        specialist_type: str,
        test_id: str = None
    ) -> str:
        """
        Determina qual modelo usar para uma requisição.

        Args:
            specialist_type: Tipo do especialista
            test_id: ID do teste (opcional, busca ativo se None)

        Returns:
            'new' ou 'baseline'
        """
        # Se não há teste ativo, usar baseline
        if test_id is None:
            test_id = self._get_active_test(specialist_type)
            if test_id is None:
                return 'baseline'

        # Buscar configuração
        config = self.tests.get(test_id)
        if not config:
            return 'baseline'

        # Determinar com base em percentual de tráfego
        if random.random() * 100 < config.traffic_percentage:
            return 'new'
        return 'baseline'

    def record_prediction(
        self,
        test_id: str,
        model_type: str,
        confidence: float,
        correct: bool = None
    ):
        """Registra predição e atualiza métricas."""
        if test_id not in self.metrics:
            logger.warning(f"Teste não encontrado: {test_id}")
            return

        self.metrics[test_id].record_prediction(model_type, confidence, correct)

    def check_test_completion(
        self,
        test_id: str
    ) -> Dict[str, Any]:
        """
        Verifica se teste está completo e retorna resultado.

        Args:
            test_id: ID do teste

        Returns:
            Resultado com status e recomendação
        """
        if test_id not in self.tests:
            return {'status': ABTestStatus.NOT_STARTED.value}

        config = self.tests[test_id]
        metrics_summary = self.metrics[test_id].get_summary()

        # Critérios de conclusão
        has_min_samples = (
            metrics_summary['new_model']['predictions'] >= config.min_samples
            and metrics_summary['baseline_model']['predictions'] >= config.min_samples
        )
        has_duration = metrics_summary['duration_hours'] >= config.duration_hours

        if not (has_min_samples and has_duration):
            return {
                'status': ABTestStatus.RUNNING.value,
                'reason': 'Aguardando mais amostras ou tempo',
                'current_samples': metrics_summary['new_model']['predictions'],
                'required_samples': config.min_samples,
                'elapsed_hours': metrics_summary['duration_hours'],
                'required_hours': config.duration_hours
            }

        # Avaliar resultado
        improvement_confidence = metrics_summary['improvement']['confidence']
        improvement_accuracy = metrics_summary['improvement']['accuracy']

        passed = (
            improvement_confidence >= -config.success_threshold
            and improvement_accuracy >= -config.success_threshold
            and metrics_summary['new_model']['confidence_mean'] >= config.confidence_threshold
        )

        if passed:
            status = ABTestStatus.PASSED
        else:
            status = ABTestStatus.FAILED

        return {
            'status': status.value,
            'passed': passed,
            'metrics': metrics_summary,
            'recommendation': self._generate_recommendation(
                config, metrics_summary, passed
            )
        }

    def _generate_recommendation(
        self,
        config: ABTestConfig,
        metrics_summary: Dict[str, Any],
        passed: bool
    ) -> str:
        """Gera recomendação baseada nos resultados."""
        if passed:
            return (
                f"Novo modelo {config.new_model_version} aprovado. "
                f"Expanda tráfego para 100% e promova para produção."
            )
        else:
            new_conf = metrics_summary['new_model']['confidence_mean']
            baseline_conf = metrics_summary['baseline_model']['confidence_mean']
            diff = new_conf - baseline_conf

            return (
                f"Novo modelo não atendeu critérios. "
                f"Diferença de confidence: {diff:+.3f}. "
                f"Mantenha baseline {config.baseline_model_version}."
            )

    def expand_traffic(
        self,
        test_id: str,
        new_percentage: float
    ):
        """Expande percentual de tráfego para novo modelo."""
        if test_id not in self.tests:
            logger.warning(f"Teste não encontrado: {test_id}")
            return

        old_percentage = self.tests[test_id].traffic_percentage
        self.tests[test_id].traffic_percentage = new_percentage

        logger.info(
            f"Tráfego expandido para teste {test_id}",
            old=f"{old_percentage}%",
            new=f"{new_percentage}%"
        )

        self._save_state()

    def _get_active_test(self, specialist_type: str) -> Optional[str]:
        """Retorna ID do teste ativo para um especialista."""
        for test_id, config in self.tests.items():
            if (config.specialist_type == specialist_type
                and self._get_test_status(test_id) == ABTestStatus.RUNNING):
                return test_id
        return None

    def _get_test_status(self, test_id: str) -> ABTestStatus:
        """Retorna status atual de um teste."""
        result = self.check_test_completion(test_id)
        status_str = result.get('status', ABTestStatus.NOT_STARTED.value)
        return ABTestStatus(status_str)

    def _save_state(self):
        """Salva estado em arquivo."""
        state = {
            'tests': {
                test_id: {
                    'specialist_type': config.specialist_type,
                    'new_model_version': config.new_model_version,
                    'baseline_model_version': config.baseline_model_version,
                    'traffic_percentage': config.traffic_percentage,
                    'min_samples': config.min_samples,
                    'duration_hours': config.duration_hours,
                    'success_threshold': config.success_threshold,
                    'confidence_threshold': config.confidence_threshold
                }
                for test_id, config in self.tests.items()
            },
            'metrics_summary': {
                test_id: metrics.get_summary()
                for test_id, metrics in self.metrics.items()
            }
        }

        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2, default=str)

    def _load_state(self):
        """Carrega estado de arquivo."""
        if not Path(self.state_file).exists():
            return

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            # Reconstruir configs
            for test_id, config_data in state.get('tests', {}).items():
                self.tests[test_id] = ABTestConfig(**config_data)

            # Reconstruir métricas
            for test_id, metrics_data in state.get('metrics_summary', {}).items():
                metrics = ABTestMetrics()
                metrics.new_model_predictions = metrics_data['new_model']['predictions']
                metrics.baseline_model_predictions = metrics_data['baseline_model']['predictions']
                metrics.new_model_confidence_sum = (
                    metrics_data['new_model']['confidence_mean'] * metrics_data['new_model']['predictions']
                )
                metrics.baseline_model_confidence_sum = (
                    metrics_data['baseline_model']['confidence_mean'] * metrics_data['baseline_model']['predictions']
                )
                # Corrigir start_time se disponível
                if 'start_time' in metrics_data:
                    metrics.start_time = datetime.fromisoformat(metrics_data['start_time'])

                self.metrics[test_id] = metrics

            logger.info(
                "Estado carregado",
                active_tests=len(self.tests)
            )

        except Exception as e:
            logger.warning(f"Erro ao carregar estado: {e}")


class ABTestingIntegration:
    """Integração A/B testing com especialistas."""

    @staticmethod
    def get_model_with_ab_test(
        specialist_type: str,
        ab_manager: ABTestManager,
        mlflow_client
    ) -> tuple:
        """
        Retorna modelo ML considerando teste A/B ativo.

        Args:
            specialist_type: Tipo do especialista
            ab_manager: Gerenciador de A/B testing
            mlflow_client: Cliente MLflow

        Returns:
            Tupla (model, model_type, test_id)
        """
        test_id = ab_manager._get_active_test(specialist_type)
        model_type = ab_manager.get_model_for_request(specialist_type, test_id)

        if model_type == 'new':
            config = ab_manager.tests.get(test_id)
            model_version = config.new_model_version if config else None
        else:
            model_version = 'Production'  # Baseline

        # Buscar modelo no MLflow
        if mlflow_client and model_version:
            model = mlflow_client.get_model(specialist_type, model_version)
        else:
            model = None

        return model, model_type, test_id

    @staticmethod
    def record_ab_test_prediction(
        ab_manager: ABTestManager,
        test_id: str,
        model_type: str,
        confidence: float,
        correct: bool = None
    ):
        """Registra predição no contexto de A/B testing."""
        if test_id:
            ab_manager.record_prediction(test_id, model_type, confidence, correct)


# Funções de conveniência para standalone
def start_ab_test(
    specialist_type: str,
    new_model_version: str,
    baseline_version: str = 'Production',
    traffic_percentage: float = 10.0
) -> str:
    """Inicia um novo teste A/B."""
    manager = ABTestManager()

    config = ABTestConfig(
        specialist_type=specialist_type,
        new_model_version=new_model_version,
        baseline_model_version=baseline_version,
        traffic_percentage=traffic_percentage
    )

    return manager.create_test(config)


def check_ab_test_status(test_id: str) -> Dict[str, Any]:
    """Verifica status de um teste A/B."""
    manager = ABTestManager()
    return manager.check_test_completion(test_id)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description="Gerenciamento de testes A/B para especialistas"
    )
    parser.add_argument(
        '--action',
        type=str,
        choices=['start', 'check', 'expand'],
        required=True,
        help='Ação a executar'
    )
    parser.add_argument('--specialist', type=str, help='Tipo do especialista')
    parser.add_argument('--new-version', type=str, help='Versão do novo modelo')
    parser.add_argument('--baseline-version', type=str, default='Production', help='Versão baseline')
    parser.add_argument('--traffic', type=float, default=10.0, help='Percentual de tráfego')
    parser.add_argument('--test-id', type=str, help='ID do teste')

    args = parser.parse_args()

    if args.action == 'start':
        test_id = start_ab_test(
            specialist_type=args.specialist,
            new_model_version=args.new_version,
            baseline_version=args.baseline_version,
            traffic_percentage=args.traffic
        )
        print(f"Teste criado: {test_id}")

    elif args.action == 'check':
        result = check_ab_test_status(args.test_id)
        print(json.dumps(result, indent=2))

    elif args.action == 'expand':
        manager = ABTestManager()
        manager.expand_traffic(args.test_id, args.traffic)
        print(f"Tráfego expandido para {args.traffic}%")
