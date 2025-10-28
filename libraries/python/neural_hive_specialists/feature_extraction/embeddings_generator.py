"""
EmbeddingsGenerator: Gera embeddings semânticos de descrições de tarefas.

Usa modelos de linguagem pré-treinados (sentence-transformers) para gerar
representações vetoriais densas, substituindo análise de keywords.
"""

import numpy as np
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)


class EmbeddingsGenerator:
    """Gera embeddings semânticos de texto."""

    def __init__(self, model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2'):
        """
        Inicializa gerador de embeddings.

        Args:
            model_name: Nome do modelo sentence-transformers
        """
        self.model_name = model_name
        self.model = None
        self.embedding_dim = None  # Dimensão será determinada dinamicamente
        self._load_model()

    def _load_model(self):
        """Carrega modelo de embeddings e determina dimensão dinamicamente."""
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embeddings model", model_name=self.model_name)
            self.model = SentenceTransformer(self.model_name)

            # Determinar dimensão dinamicamente do modelo
            self.embedding_dim = self.model.get_sentence_embedding_dimension()

            logger.info(
                "Embeddings model loaded successfully",
                model_name=self.model_name,
                embedding_dim=self.embedding_dim
            )
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            self.model = None
            self.embedding_dim = 384  # Dimensão padrão como fallback
        except Exception as e:
            logger.error(
                "Failed to load embeddings model",
                error=str(e),
                model_name=self.model_name
            )
            self.model = None
            self.embedding_dim = 384  # Dimensão padrão como fallback

    def generate_task_embeddings(self, tasks: List[Dict[str, Any]]) -> np.ndarray:
        """
        Gera embeddings para descrições de tarefas.

        Args:
            tasks: Lista de tarefas do plano cognitivo

        Returns:
            Array numpy (num_tasks, embedding_dim)
        """
        if self.model is None:
            logger.warning(
                "Model not available, returning zero embeddings",
                embedding_dim=self.embedding_dim
            )
            return np.zeros((len(tasks), self.embedding_dim))

        descriptions = [task.get('description', '') for task in tasks]

        try:
            embeddings = self.model.encode(descriptions, convert_to_numpy=True)
            logger.debug("Task embeddings generated", shape=embeddings.shape)
            return embeddings
        except Exception as e:
            logger.error("Failed to generate embeddings", error=str(e))
            return np.zeros((len(tasks), self.embedding_dim))

    def generate_plan_embedding(self, tasks: List[Dict[str, Any]]) -> np.ndarray:
        """
        Gera embedding agregado do plano inteiro.

        Args:
            tasks: Lista de tarefas do plano cognitivo

        Returns:
            Array numpy (embedding_dim,) - média dos embeddings de tarefas
        """
        task_embeddings = self.generate_task_embeddings(tasks)

        # Agregar por média
        plan_embedding = np.mean(task_embeddings, axis=0)

        logger.debug("Plan embedding generated", shape=plan_embedding.shape)
        return plan_embedding

    def calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """
        Calcula similaridade semântica entre dois textos.

        Args:
            text1: Primeiro texto
            text2: Segundo texto

        Returns:
            Score de similaridade (0.0-1.0)
        """
        if self.model is None:
            return 0.0

        try:
            embeddings = self.model.encode([text1, text2], convert_to_numpy=True)
            # Similaridade cosseno
            similarity = np.dot(embeddings[0], embeddings[1]) / (
                np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
            )
            return float(similarity)
        except Exception as e:
            logger.error("Failed to calculate similarity", error=str(e))
            return 0.0

    def extract_statistical_features(self, embeddings: np.ndarray) -> Dict[str, float]:
        """
        Extrai features estatísticas de embeddings.

        Args:
            embeddings: Array de embeddings (num_samples, embedding_dim)

        Returns:
            Dicionário com features estatísticas
        """
        features = {
            'mean_norm': float(np.mean(np.linalg.norm(embeddings, axis=1))),
            'std_norm': float(np.std(np.linalg.norm(embeddings, axis=1))),
            'max_norm': float(np.max(np.linalg.norm(embeddings, axis=1))),
            'min_norm': float(np.min(np.linalg.norm(embeddings, axis=1))),
        }

        # Diversidade (distância média entre embeddings)
        if len(embeddings) > 1:
            pairwise_distances = []
            for i in range(len(embeddings)):
                for j in range(i+1, len(embeddings)):
                    dist = np.linalg.norm(embeddings[i] - embeddings[j])
                    pairwise_distances.append(dist)
            features['avg_diversity'] = float(np.mean(pairwise_distances))
        else:
            features['avg_diversity'] = 0.0

        return features
