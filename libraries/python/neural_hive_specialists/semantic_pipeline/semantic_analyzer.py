"""
SemanticAnalyzer: Análise semântica baseada em embeddings.

Substitui heurísticas de string-match por similaridade semântica usando
sentence-transformers. Calcula similaridade coseno entre descrições de tarefas
e conceitos de domínio.
"""

from typing import Dict, List, Any, Optional, TYPE_CHECKING
import numpy as np
import structlog

# Lazy imports para evitar carregar dependências pesadas no import do módulo
if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = structlog.get_logger(__name__)

def _get_sentence_transformer(model_name: str = 'all-MiniLM-L6-v2'):
    """Lazy load do SentenceTransformer."""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(model_name)
    except ImportError:
        logger.warning("sentence-transformers não instalado, SemanticAnalyzer não disponível")
        return None

_cosine_similarity_func = None

def cosine_similarity(X, Y=None):
    """Lazy load wrapper do cosine_similarity."""
    global _cosine_similarity_func
    if _cosine_similarity_func is None:
        from sklearn.metrics.pairwise import cosine_similarity as _cs
        _cosine_similarity_func = _cs
    return _cosine_similarity_func(X, Y)


class SemanticAnalyzer:
    """Análise semântica usando embeddings."""

    # Conceitos semânticos organizados por dimensão
    SECURITY_CONCEPTS = [
        "authentication and authorization mechanisms",
        "input validation and sanitization",
        "secure data encryption and protection",
        "access control and permissions",
        "security token and credential management",
        "protection against injection attacks",
        "secure API endpoints and interfaces",
    ]

    ARCHITECTURE_CONCEPTS = [
        "service-oriented architecture patterns",
        "layered architecture and separation of concerns",
        "microservices and distributed systems",
        "controller and repository patterns",
        "interface segregation and dependency injection",
        "factory and strategy design patterns",
        "modular components with low coupling",
    ]

    PERFORMANCE_CONCEPTS = [
        "caching strategies and optimization",
        "database query optimization and indexing",
        "asynchronous and parallel processing",
        "lazy loading and resource pooling",
        "batch processing and queuing",
        "memory buffering and efficient algorithms",
        "load balancing and scalability",
    ]

    CODE_QUALITY_CONCEPTS = [
        "unit testing and test coverage",
        "code documentation and comments",
        "error handling and exception management",
        "structured logging and monitoring",
        "code readability and maintainability",
        "refactoring and technical debt reduction",
    ]

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa analisador semântico.

        Args:
            config: Configuração com embeddings_model
        """
        self.config = config
        self.embeddings_model_name = config.get(
            "embeddings_model", "paraphrase-multilingual-MiniLM-L12-v2"
        )

        # Threshold de similaridade semântica (0.0-1.0)
        self.similarity_threshold = config.get("semantic_similarity_threshold", 0.4)

        # Lazy loading do modelo
        self._model: Optional[Any] = None

        # Cache de embeddings de conceitos
        self._concept_embeddings_cache: Dict[str, np.ndarray] = {}

        logger.info(
            "SemanticAnalyzer initialized",
            model=self.embeddings_model_name,
            threshold=self.similarity_threshold,
        )

    @property
    def model(self) -> Any:
        """Lazy initialization do modelo de embeddings."""
        if self._model is None:
            logger.info(
                "Loading sentence-transformers model", model=self.embeddings_model_name
            )
            self._model = _get_sentence_transformer(self.embeddings_model_name)
            if self._model is None:
                raise ImportError("sentence-transformers não está instalado")
        return self._model

    def analyze_security(self, tasks: List[Dict[str, Any]]) -> float:
        """
        Analisa aspectos de segurança usando similaridade semântica.

        Args:
            tasks: Lista de tarefas do plano cognitivo

        Returns:
            Score de segurança (0.0-1.0)
        """
        if not tasks:
            return 0.5

        try:
            # Extrair descrições de tarefas
            task_descriptions = [
                task.get("description", "") for task in tasks if task.get("description")
            ]

            if not task_descriptions:
                return 0.5

            # Obter embeddings de conceitos de segurança (cached)
            security_embeddings = self._get_concept_embeddings(
                self.SECURITY_CONCEPTS, "security"
            )

            # Obter embeddings das descrições
            task_embeddings = self.model.encode(
                task_descriptions, convert_to_numpy=True
            )

            # Calcular similaridade máxima de cada tarefa com conceitos de segurança
            similarities = cosine_similarity(task_embeddings, security_embeddings)

            # Para cada tarefa, pegar a similaridade máxima com qualquer conceito
            max_similarities = np.max(similarities, axis=1)

            # Contar tarefas com similaridade acima do threshold
            relevant_tasks = np.sum(max_similarities > self.similarity_threshold)

            # Score: proporção de tarefas relevantes para segurança
            security_score = relevant_tasks / len(task_descriptions)

            logger.debug(
                "Security semantic analysis",
                num_tasks=len(task_descriptions),
                relevant_tasks=int(relevant_tasks),
                avg_similarity=float(np.mean(max_similarities)),
                security_score=security_score,
            )

            return float(max(0.0, min(1.0, security_score)))

        except Exception as e:
            logger.error(
                "Failed to analyze security semantically", error=str(e), exc_info=True
            )
            return 0.5

    def analyze_architecture(self, tasks: List[Dict[str, Any]]) -> float:
        """
        Analisa padrões arquiteturais usando similaridade semântica.

        Args:
            tasks: Lista de tarefas

        Returns:
            Score de arquitetura (0.0-1.0)
        """
        if not tasks:
            return 0.5

        try:
            task_descriptions = [
                task.get("description", "") for task in tasks if task.get("description")
            ]

            if not task_descriptions:
                return 0.5

            architecture_embeddings = self._get_concept_embeddings(
                self.ARCHITECTURE_CONCEPTS, "architecture"
            )
            task_embeddings = self.model.encode(
                task_descriptions, convert_to_numpy=True
            )

            similarities = cosine_similarity(task_embeddings, architecture_embeddings)
            max_similarities = np.max(similarities, axis=1)

            relevant_tasks = np.sum(max_similarities > self.similarity_threshold)
            architecture_score = relevant_tasks / len(task_descriptions)

            logger.debug(
                "Architecture semantic analysis",
                num_tasks=len(task_descriptions),
                relevant_tasks=int(relevant_tasks),
                avg_similarity=float(np.mean(max_similarities)),
                architecture_score=architecture_score,
            )

            return float(max(0.0, min(1.0, architecture_score)))

        except Exception as e:
            logger.error(
                "Failed to analyze architecture semantically",
                error=str(e),
                exc_info=True,
            )
            return 0.5

    def analyze_performance(self, tasks: List[Dict[str, Any]]) -> float:
        """
        Analisa aspectos de performance usando similaridade semântica.

        Args:
            tasks: Lista de tarefas

        Returns:
            Score de performance (0.0-1.0)
        """
        if not tasks:
            return 0.5

        try:
            task_descriptions = [
                task.get("description", "") for task in tasks if task.get("description")
            ]

            if not task_descriptions:
                return 0.5

            performance_embeddings = self._get_concept_embeddings(
                self.PERFORMANCE_CONCEPTS, "performance"
            )
            task_embeddings = self.model.encode(
                task_descriptions, convert_to_numpy=True
            )

            similarities = cosine_similarity(task_embeddings, performance_embeddings)
            max_similarities = np.max(similarities, axis=1)

            relevant_tasks = np.sum(max_similarities > self.similarity_threshold)
            performance_score = relevant_tasks / len(task_descriptions)

            logger.debug(
                "Performance semantic analysis",
                num_tasks=len(task_descriptions),
                relevant_tasks=int(relevant_tasks),
                avg_similarity=float(np.mean(max_similarities)),
                performance_score=performance_score,
            )

            return float(max(0.0, min(1.0, performance_score)))

        except Exception as e:
            logger.error(
                "Failed to analyze performance semantically",
                error=str(e),
                exc_info=True,
            )
            return 0.5

    def analyze_code_quality(self, tasks: List[Dict[str, Any]]) -> float:
        """
        Analisa qualidade de código usando similaridade semântica.

        Args:
            tasks: Lista de tarefas

        Returns:
            Score de qualidade (0.0-1.0)
        """
        if not tasks:
            return 0.5

        try:
            task_descriptions = [
                task.get("description", "") for task in tasks if task.get("description")
            ]

            if not task_descriptions:
                return 0.5

            quality_embeddings = self._get_concept_embeddings(
                self.CODE_QUALITY_CONCEPTS, "code_quality"
            )
            task_embeddings = self.model.encode(
                task_descriptions, convert_to_numpy=True
            )

            similarities = cosine_similarity(task_embeddings, quality_embeddings)
            max_similarities = np.max(similarities, axis=1)

            relevant_tasks = np.sum(max_similarities > self.similarity_threshold)
            quality_score = relevant_tasks / len(task_descriptions)

            logger.debug(
                "Code quality semantic analysis",
                num_tasks=len(task_descriptions),
                relevant_tasks=int(relevant_tasks),
                avg_similarity=float(np.mean(max_similarities)),
                quality_score=quality_score,
            )

            return float(max(0.0, min(1.0, quality_score)))

        except Exception as e:
            logger.error(
                "Failed to analyze code quality semantically",
                error=str(e),
                exc_info=True,
            )
            return 0.5

    def _get_concept_embeddings(
        self, concepts: List[str], cache_key: str
    ) -> np.ndarray:
        """
        Obtém embeddings de conceitos (com cache).

        Args:
            concepts: Lista de conceitos
            cache_key: Chave do cache

        Returns:
            Array de embeddings
        """
        if cache_key not in self._concept_embeddings_cache:
            embeddings = self.model.encode(concepts, convert_to_numpy=True)
            self._concept_embeddings_cache[cache_key] = embeddings
            logger.debug(
                f"Cached {cache_key} concept embeddings", num_concepts=len(concepts)
            )

        return self._concept_embeddings_cache[cache_key]

    def compute_task_similarity(
        self, task_description: str, reference_concepts: List[str]
    ) -> float:
        """
        Computa similaridade de uma tarefa com conceitos de referência.

        Args:
            task_description: Descrição da tarefa
            reference_concepts: Conceitos de referência

        Returns:
            Similaridade máxima (0.0-1.0)
        """
        try:
            task_emb = self.model.encode([task_description], convert_to_numpy=True)
            concept_emb = self.model.encode(reference_concepts, convert_to_numpy=True)

            similarities = cosine_similarity(task_emb, concept_emb)
            max_similarity = float(np.max(similarities))

            return max_similarity

        except Exception as e:
            logger.error("Failed to compute task similarity", error=str(e))
            return 0.0
