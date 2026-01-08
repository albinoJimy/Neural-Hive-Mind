"""
Incremental Learner para Online Learning.

Implementa aprendizado incremental contínuo via partial_fit para algoritmos
suportados pelo scikit-learn, permitindo atualizações de modelo sem
retreinamento completo.
"""

import hashlib
import os
import pickle
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union
import structlog
import numpy as np
from sklearn.linear_model import SGDClassifier, PassiveAggressiveClassifier, Perceptron
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from prometheus_client import Counter, Histogram, Gauge
import joblib

from .config import OnlineLearningConfig

logger = structlog.get_logger(__name__)

# Métricas Prometheus
online_updates_total = Counter(
    'neural_hive_online_updates_total',
    'Total de atualizações online',
    ['specialist_type', 'status']
)
online_update_duration = Histogram(
    'neural_hive_online_update_duration_seconds',
    'Duração de atualizações online',
    ['specialist_type']
)
online_model_loss = Gauge(
    'neural_hive_online_model_loss',
    'Loss atual do modelo online',
    ['specialist_type']
)
online_model_updates_count = Gauge(
    'neural_hive_online_model_updates_count',
    'Número total de updates do modelo',
    ['specialist_type']
)
online_checkpoint_size_bytes = Gauge(
    'neural_hive_online_checkpoint_size_bytes',
    'Tamanho do último checkpoint em bytes',
    ['specialist_type']
)


class IncrementalLearnerError(Exception):
    """Exceção base para erros de incremental learning."""
    pass


class ModelNotInitializedError(IncrementalLearnerError):
    """Exceção quando modelo não está inicializado."""
    pass


class CheckpointError(IncrementalLearnerError):
    """Exceção para erros de checkpoint."""
    pass


class IncrementalLearner:
    """
    Gerencia aprendizado incremental de modelos ML.

    Suporta algoritmos que implementam partial_fit:
    - SGDClassifier: Gradient descent estocástico
    - PassiveAggressiveClassifier: Para classificação online
    - Perceptron: Perceptron linear

    Funcionalidades:
    - Atualizações incrementais via partial_fit
    - Persistência de checkpoints
    - Métricas de convergência
    - Integração com FeedbackCollector
    """

    SUPPORTED_ALGORITHMS = {
        'sgd': SGDClassifier,
        'passive_aggressive': PassiveAggressiveClassifier,
        'perceptron': Perceptron
    }

    DEFAULT_ALGORITHM_PARAMS = {
        'sgd': {
            'loss': 'log_loss',
            'penalty': 'l2',
            'alpha': 0.0001,
            'learning_rate': 'adaptive',
            'eta0': 0.001,
            'warm_start': True,
            'random_state': 42
        },
        'passive_aggressive': {
            'C': 1.0,
            'fit_intercept': True,
            'warm_start': True,
            'random_state': 42
        },
        'perceptron': {
            'penalty': 'l2',
            'alpha': 0.0001,
            'warm_start': True,
            'random_state': 42
        }
    }

    def __init__(
        self,
        config: OnlineLearningConfig,
        specialist_type: str,
        classes: Optional[List[Any]] = None,
        feature_names: Optional[List[str]] = None
    ):
        """
        Inicializa IncrementalLearner.

        Args:
            config: Configuração de online learning
            specialist_type: Tipo do especialista
            classes: Classes possíveis para classificação
            feature_names: Nomes das features
        """
        self.config = config
        self.specialist_type = specialist_type
        self.classes = classes or ['approve', 'reject', 'review_required']
        self.feature_names = feature_names

        # Estado do modelo
        self._model: Optional[Union[SGDClassifier, PassiveAggressiveClassifier, Perceptron]] = None
        self._scaler: Optional[StandardScaler] = None
        self._is_fitted = False
        self._update_count = 0
        self._total_samples_seen = 0
        self._loss_history: List[float] = []
        self._gradient_norm_history: List[float] = []
        self._last_update_time: Optional[datetime] = None
        self._model_version = f"online-{uuid.uuid4().hex[:8]}"

        # Inicializar modelo
        self._initialize_model()

        logger.info(
            "incremental_learner_initialized",
            specialist_type=specialist_type,
            algorithm=config.incremental_algorithm,
            classes=self.classes,
            model_version=self._model_version
        )

    def _initialize_model(self):
        """Inicializa modelo incremental baseado na configuração."""
        algorithm = self.config.incremental_algorithm

        if algorithm not in self.SUPPORTED_ALGORITHMS:
            raise ValueError(
                f"Algoritmo '{algorithm}' não suportado. "
                f"Use: {list(self.SUPPORTED_ALGORITHMS.keys())}"
            )

        # Obter classe e parâmetros do algoritmo
        model_class = self.SUPPORTED_ALGORITHMS[algorithm]
        params = self.DEFAULT_ALGORITHM_PARAMS[algorithm].copy()

        # Aplicar learning rate da configuração para SGD
        if algorithm == 'sgd':
            params['eta0'] = self.config.learning_rate

        # Criar modelo
        self._model = model_class(**params)

        # Criar scaler para normalização
        self._scaler = StandardScaler()

        logger.info(
            "model_initialized",
            algorithm=algorithm,
            params=params,
            specialist_type=self.specialist_type
        )

    def _compute_loss(self, X: np.ndarray, y: np.ndarray) -> float:
        """
        Calcula loss do modelo nas amostras.

        Args:
            X: Features
            y: Labels

        Returns:
            Loss (log loss para classificação)
        """
        if not self._is_fitted:
            return float('inf')

        try:
            # Normalizar features
            X_scaled = self._scaler.transform(X)

            # Calcular probabilidades
            probas = self._model.predict_proba(X_scaled)

            # Log loss
            eps = 1e-15
            loss = 0.0
            for i, label in enumerate(y):
                class_idx = list(self.classes).index(label)
                prob = np.clip(probas[i, class_idx], eps, 1 - eps)
                loss -= np.log(prob)

            return loss / len(y)

        except Exception as e:
            logger.warning(
                "loss_computation_failed",
                error=str(e),
                specialist_type=self.specialist_type
            )
            return float('inf')

    def _compute_gradient_norm(self) -> float:
        """
        Estima norma do gradiente baseado nos coeficientes do modelo.

        Returns:
            Norma L2 dos coeficientes (proxy para gradient norm)
        """
        if not self._is_fitted or not hasattr(self._model, 'coef_'):
            return float('inf')

        try:
            coef = self._model.coef_
            return float(np.linalg.norm(coef))
        except Exception:
            return float('inf')

    def partial_fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Executa atualização incremental do modelo.

        Args:
            X: Features (shape: [n_samples, n_features])
            y: Labels (shape: [n_samples])
            sample_weight: Pesos das amostras (opcional)

        Returns:
            Dict com métricas de atualização:
            - update_count: Número total de updates
            - samples_in_batch: Amostras neste batch
            - total_samples_seen: Total de amostras processadas
            - loss_before: Loss antes do update
            - loss_after: Loss após update
            - loss_reduction: Redução de loss
            - gradient_norm: Norma do gradiente
            - duration_ms: Duração em milissegundos
        """
        start_time = time.time()

        try:
            # Validar inputs
            X = np.asarray(X)
            y = np.asarray(y)

            if X.shape[0] != y.shape[0]:
                raise ValueError(
                    f"X e y devem ter mesmo número de amostras: "
                    f"X.shape[0]={X.shape[0]}, y.shape[0]={y.shape[0]}"
                )

            if X.shape[0] == 0:
                raise ValueError("Batch vazio não é permitido")

            # Calcular loss antes do update
            loss_before = self._compute_loss(X, y) if self._is_fitted else float('inf')

            # Atualizar scaler incrementalmente
            if not self._is_fitted:
                # Primeiro batch - fit completo
                self._scaler.fit(X)
            else:
                # Atualização incremental do scaler
                self._scaler.partial_fit(X)

            # Normalizar features
            X_scaled = self._scaler.transform(X)

            # Executar partial_fit
            self._model.partial_fit(
                X_scaled,
                y,
                classes=self.classes,
                sample_weight=sample_weight
            )

            self._is_fitted = True
            self._update_count += 1
            self._total_samples_seen += len(y)
            self._last_update_time = datetime.utcnow()

            # Calcular loss após update
            loss_after = self._compute_loss(X, y)
            loss_reduction = loss_before - loss_after if loss_before != float('inf') else 0.0

            # Calcular gradient norm
            gradient_norm = self._compute_gradient_norm()

            # Atualizar histórico
            self._loss_history.append(loss_after)
            self._gradient_norm_history.append(gradient_norm)

            # Limitar tamanho do histórico
            max_history = 1000
            if len(self._loss_history) > max_history:
                self._loss_history = self._loss_history[-max_history:]
                self._gradient_norm_history = self._gradient_norm_history[-max_history:]

            duration_ms = (time.time() - start_time) * 1000

            # Emitir métricas Prometheus
            online_updates_total.labels(
                specialist_type=self.specialist_type,
                status='success'
            ).inc()
            online_update_duration.labels(
                specialist_type=self.specialist_type
            ).observe(duration_ms / 1000)
            online_model_loss.labels(
                specialist_type=self.specialist_type
            ).set(loss_after)
            online_model_updates_count.labels(
                specialist_type=self.specialist_type
            ).set(self._update_count)

            result = {
                'update_count': self._update_count,
                'samples_in_batch': len(y),
                'total_samples_seen': self._total_samples_seen,
                'loss_before': loss_before,
                'loss_after': loss_after,
                'loss_reduction': loss_reduction,
                'gradient_norm': gradient_norm,
                'duration_ms': duration_ms,
                'model_version': self._model_version,
                'timestamp': self._last_update_time.isoformat()
            }

            logger.info(
                "partial_fit_completed",
                specialist_type=self.specialist_type,
                **result
            )

            # Verificar se deve salvar checkpoint
            if self._update_count % self.config.checkpoint_interval_updates == 0:
                self._save_checkpoint_async()

            return result

        except Exception as e:
            online_updates_total.labels(
                specialist_type=self.specialist_type,
                status='failed'
            ).inc()

            logger.error(
                "partial_fit_failed",
                specialist_type=self.specialist_type,
                error=str(e),
                samples=len(y) if 'y' in locals() else 0
            )
            raise IncrementalLearnerError(f"Falha no partial_fit: {str(e)}") from e

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Executa predição com modelo online.

        Args:
            X: Features (shape: [n_samples, n_features])

        Returns:
            Predições (shape: [n_samples])
        """
        if not self._is_fitted:
            raise ModelNotInitializedError(
                "Modelo não está fitted. Execute partial_fit primeiro."
            )

        X = np.asarray(X)
        X_scaled = self._scaler.transform(X)
        return self._model.predict(X_scaled)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Executa predição de probabilidades.

        Args:
            X: Features (shape: [n_samples, n_features])

        Returns:
            Probabilidades (shape: [n_samples, n_classes])
        """
        if not self._is_fitted:
            raise ModelNotInitializedError(
                "Modelo não está fitted. Execute partial_fit primeiro."
            )

        X = np.asarray(X)
        X_scaled = self._scaler.transform(X)
        return self._model.predict_proba(X_scaled)

    def get_convergence_metrics(self) -> Dict[str, Any]:
        """
        Retorna métricas de convergência do modelo.

        Returns:
            Dict com métricas de convergência:
            - is_converging: Se modelo está convergindo
            - loss_trend: Tendência de loss (negativo = convergindo)
            - average_loss_reduction: Redução média de loss
            - current_loss: Loss atual
            - updates_since_improvement: Updates desde última melhoria
        """
        if len(self._loss_history) < 2:
            return {
                'is_converging': False,
                'loss_trend': 0.0,
                'average_loss_reduction': 0.0,
                'current_loss': self._loss_history[-1] if self._loss_history else float('inf'),
                'updates_since_improvement': 0
            }

        # Calcular tendência de loss (últimos 100 updates)
        recent_losses = self._loss_history[-100:]
        if len(recent_losses) >= 2:
            # Regressão linear simples para tendência
            x = np.arange(len(recent_losses))
            loss_trend = np.polyfit(x, recent_losses, 1)[0]
        else:
            loss_trend = 0.0

        # Calcular redução média
        reductions = []
        for i in range(1, len(recent_losses)):
            reductions.append(recent_losses[i-1] - recent_losses[i])
        avg_reduction = np.mean(reductions) if reductions else 0.0

        # Encontrar último improvement
        min_loss = min(recent_losses)
        updates_since_improvement = len(recent_losses) - recent_losses.index(min_loss) - 1

        return {
            'is_converging': loss_trend < 0,
            'loss_trend': float(loss_trend),
            'average_loss_reduction': float(avg_reduction),
            'current_loss': float(recent_losses[-1]),
            'updates_since_improvement': updates_since_improvement,
            'gradient_norm': self._gradient_norm_history[-1] if self._gradient_norm_history else float('inf')
        }

    def save_checkpoint(self, path: Optional[str] = None) -> str:
        """
        Salva checkpoint do modelo.

        Args:
            path: Caminho para salvar (opcional, usa config se não fornecido)

        Returns:
            Path do checkpoint salvo
        """
        if not self._is_fitted:
            raise ModelNotInitializedError(
                "Modelo não está fitted. Nada a salvar."
            )

        if path is None:
            os.makedirs(self.config.checkpoint_storage_path, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(
                self.config.checkpoint_storage_path,
                f"{self.specialist_type}_{self._model_version}_{timestamp}.pkl"
            )

        checkpoint = {
            'model': self._model,
            'scaler': self._scaler,
            'classes': self.classes,
            'feature_names': self.feature_names,
            'update_count': self._update_count,
            'total_samples_seen': self._total_samples_seen,
            'loss_history': self._loss_history[-100:],  # Últimos 100
            'model_version': self._model_version,
            'specialist_type': self.specialist_type,
            'algorithm': self.config.incremental_algorithm,
            'saved_at': datetime.utcnow().isoformat(),
            'config': {
                'learning_rate': self.config.learning_rate,
                'mini_batch_size': self.config.mini_batch_size
            }
        }

        # Calcular hash do modelo para integridade
        model_bytes = pickle.dumps(self._model)
        checkpoint['model_hash'] = hashlib.sha256(model_bytes).hexdigest()

        # Salvar checkpoint
        joblib.dump(checkpoint, path)

        # Verificar tamanho
        checkpoint_size = os.path.getsize(path)
        max_size = self.config.max_checkpoint_size_mb * 1024 * 1024

        if checkpoint_size > max_size:
            logger.warning(
                "checkpoint_exceeds_max_size",
                specialist_type=self.specialist_type,
                size_mb=checkpoint_size / (1024 * 1024),
                max_mb=self.config.max_checkpoint_size_mb
            )

        # Emitir métrica
        online_checkpoint_size_bytes.labels(
            specialist_type=self.specialist_type
        ).set(checkpoint_size)

        logger.info(
            "checkpoint_saved",
            specialist_type=self.specialist_type,
            path=path,
            size_bytes=checkpoint_size,
            update_count=self._update_count,
            model_hash=checkpoint['model_hash'][:16]
        )

        return path

    def _save_checkpoint_async(self):
        """Salva checkpoint de forma assíncrona."""
        try:
            self.save_checkpoint()
        except Exception as e:
            logger.error(
                "async_checkpoint_failed",
                specialist_type=self.specialist_type,
                error=str(e)
            )

    def load_checkpoint(self, path: str) -> Dict[str, Any]:
        """
        Carrega checkpoint do modelo.

        Args:
            path: Caminho do checkpoint

        Returns:
            Metadados do checkpoint carregado
        """
        if not os.path.exists(path):
            raise CheckpointError(f"Checkpoint não encontrado: {path}")

        try:
            checkpoint = joblib.load(path)

            # Verificar integridade
            model_bytes = pickle.dumps(checkpoint['model'])
            computed_hash = hashlib.sha256(model_bytes).hexdigest()

            if computed_hash != checkpoint.get('model_hash'):
                raise CheckpointError(
                    f"Hash do modelo não corresponde. "
                    f"Checkpoint pode estar corrompido."
                )

            # Restaurar estado
            self._model = checkpoint['model']
            self._scaler = checkpoint['scaler']
            self.classes = checkpoint['classes']
            self.feature_names = checkpoint.get('feature_names')
            self._update_count = checkpoint['update_count']
            self._total_samples_seen = checkpoint['total_samples_seen']
            self._loss_history = checkpoint.get('loss_history', [])
            self._model_version = checkpoint['model_version']
            self._is_fitted = True

            logger.info(
                "checkpoint_loaded",
                specialist_type=self.specialist_type,
                path=path,
                update_count=self._update_count,
                total_samples_seen=self._total_samples_seen,
                model_version=self._model_version
            )

            return {
                'model_version': self._model_version,
                'update_count': self._update_count,
                'total_samples_seen': self._total_samples_seen,
                'saved_at': checkpoint.get('saved_at'),
                'algorithm': checkpoint.get('algorithm')
            }

        except Exception as e:
            raise CheckpointError(f"Falha ao carregar checkpoint: {str(e)}") from e

    def get_model_state(self) -> Dict[str, Any]:
        """
        Retorna estado atual do modelo.

        Returns:
            Dict com estado do modelo
        """
        return {
            'is_fitted': self._is_fitted,
            'model_version': self._model_version,
            'update_count': self._update_count,
            'total_samples_seen': self._total_samples_seen,
            'last_update_time': self._last_update_time.isoformat() if self._last_update_time else None,
            'algorithm': self.config.incremental_algorithm,
            'classes': self.classes,
            'feature_count': len(self.feature_names) if self.feature_names else None,
            'convergence': self.get_convergence_metrics() if self._is_fitted else None
        }

    def reset(self):
        """Reinicializa modelo para estado inicial."""
        self._initialize_model()
        self._is_fitted = False
        self._update_count = 0
        self._total_samples_seen = 0
        self._loss_history = []
        self._gradient_norm_history = []
        self._last_update_time = None
        self._model_version = f"online-{uuid.uuid4().hex[:8]}"

        logger.info(
            "model_reset",
            specialist_type=self.specialist_type,
            new_version=self._model_version
        )

    @property
    def model(self):
        """Retorna modelo interno (somente leitura)."""
        return self._model

    @property
    def is_fitted(self) -> bool:
        """Retorna se modelo está fitted."""
        return self._is_fitted

    @property
    def update_count(self) -> int:
        """Retorna número de updates."""
        return self._update_count

    @property
    def model_version(self) -> str:
        """Retorna versão do modelo."""
        return self._model_version
