"""
OntologyMapper: Mapeia planos cognitivos para ontologia estruturada.

Substitui heurísticas de string-match por mapeamento semântico estruturado
baseado em ontologias JSON carregadas de `/ontologies/`.
"""

import json
import os
from typing import Dict, List, Any, Optional
import numpy as np
import structlog
from pathlib import Path

logger = structlog.get_logger(__name__)


class OntologyMapper:
    """Mapeia elementos de plano cognitivo para IDs de ontologia."""

    def __init__(
        self,
        ontology_path: Optional[str] = None,
        embeddings_generator=None,
        semantic_similarity_threshold: float = 0.7
    ):
        if semantic_similarity_threshold < 0.0 or semantic_similarity_threshold > 1.0:
            logger.warning(
                "semantic_similarity_threshold fora do intervalo [0.0, 1.0], aplicando clamp",
                configured_value=semantic_similarity_threshold
            )
            semantic_similarity_threshold = max(0.0, min(1.0, semantic_similarity_threshold))

        self.ontology_path = ontology_path or self._get_default_ontology_path()
        self.intents_taxonomy = self._load_taxonomy('intents_taxonomy.json')
        self.architecture_patterns = self._load_taxonomy('architecture_patterns.json')
        self.embeddings_generator = embeddings_generator
        self.semantic_similarity_threshold = semantic_similarity_threshold
        self._indicator_embeddings_cache = {}

        # Pré-computar embeddings de indicadores
        self._precompute_indicator_embeddings()

        logger.info(
            "OntologyMapper initialized",
            ontology_path=self.ontology_path,
            semantic_similarity_threshold=self.semantic_similarity_threshold,
            cached_indicators=len(self._indicator_embeddings_cache)
        )

    def _get_default_ontology_path(self) -> str:
        """Retorna caminho padrão para ontologias."""
        env_path = os.getenv("ONTOLOGY_PATH")
        if env_path:
            logger.info("Using ontology path from environment", ontology_path=env_path)
            return env_path

        current_dir = Path(__file__).resolve().parent
        for parent in [current_dir] + list(current_dir.parents):
            candidate = parent / "ontologies"
            if candidate.is_dir():
                logger.info("Using discovered ontology path", ontology_path=str(candidate))
                return str(candidate)

        fallback = str(Path.cwd() / "ontologies")
        logger.warning(
            "Ontology path not found; using fallback",
            fallback_ontology_path=fallback
        )
        return fallback

    def _load_taxonomy(self, filename: str) -> Dict[str, Any]:
        """Carrega arquivo de taxonomia JSON."""
        filepath = os.path.join(self.ontology_path, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                taxonomy = json.load(f)
            logger.debug(f"Loaded taxonomy", filename=filename, version=taxonomy.get('version'))
            return taxonomy
        except FileNotFoundError:
            logger.warning(f"Taxonomy file not found", filepath=filepath)
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in taxonomy", filepath=filepath, error=str(e))
            return {}

    def _precompute_indicator_embeddings(self):
        """
        Pré-computa embeddings de todos os indicadores de padrões e anti-padrões.
        Armazena em _indicator_embeddings_cache para reutilização.
        """
        if not self.embeddings_generator:
            logger.debug("EmbeddingsGenerator não disponível, pulando pré-computação")
            return

        if not self.architecture_patterns:
            logger.warning(
                "Ontologies not loaded; cannot precompute indicator embeddings",
                ontology_path=self.ontology_path
            )
            return

        all_indicators = set()

        patterns = self.architecture_patterns.get('patterns', {})
        for pattern_data in patterns.values():
            indicators = pattern_data.get('indicators', [])
            all_indicators.update(indicators)

        anti_patterns = self.architecture_patterns.get('anti_patterns', {})
        for anti_data in anti_patterns.values():
            indicators = anti_data.get('indicators', [])
            all_indicators.update(indicators)

        if not all_indicators:
            logger.debug("Nenhum indicador encontrado para pré-computação")
            return

        indicators_list = sorted(list(all_indicators))

        logger.info(
            "Pré-computando embeddings de indicadores",
            num_indicators=len(indicators_list)
        )

        try:
            embeddings = self.embeddings_generator.get_embeddings(indicators_list)

            for indicator, embedding in zip(indicators_list, embeddings):
                self._indicator_embeddings_cache[indicator] = embedding

            logger.info(
                "Embeddings de indicadores pré-computados com sucesso",
                cached_count=len(self._indicator_embeddings_cache)
            )
        except Exception as e:
            logger.error(
                "Falha ao pré-computar embeddings de indicadores",
                error=str(e)
            )
    def map_domain_to_taxonomy(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Mapeia domínio do plano para entrada de taxonomia.

        Args:
            domain: Domínio original do plano (ex: 'security-analysis')

        Returns:
            Dicionário com id, description, risk_weight, subcategories
        """
        domains = self.intents_taxonomy.get('domains', {})
        if domain in domains:
            return domains[domain]

        logger.warning("Domain not found in taxonomy", domain=domain)
        return None

    def map_task_type_to_taxonomy(self, task_type: str) -> Optional[Dict[str, Any]]:
        """
        Mapeia tipo de tarefa para taxonomia.

        Args:
            task_type: Tipo da tarefa (ex: 'analysis', 'transformation')

        Returns:
            Dicionário com id, complexity_factor
        """
        task_types = self.intents_taxonomy.get('task_types', {})
        if task_type in task_types:
            return task_types[task_type]

        logger.warning("Task type not found in taxonomy", task_type=task_type)
        return None

    def detect_architecture_patterns(self, task_descriptions: List[str]) -> List[Dict[str, Any]]:
        """
        Detecta padrões arquiteturais em descrições de tarefas.

        Uma tarefa é considerada match quando a média das similaridades cosseno
        entre a descrição e todos os indicadores do padrão é >= semantic_similarity_threshold.
        Usa similaridade semântica se embeddings_generator disponível,
        caso contrário faz fallback para substring matching.

        Args:
            task_descriptions: Lista de descrições de tarefas

        Returns:
            Lista de padrões detectados com scores
        """
        patterns = self.architecture_patterns.get('patterns', {})
        detected = []

        for pattern_name, pattern_data in patterns.items():
            indicators = pattern_data.get('indicators', [])

            if self.embeddings_generator:
                # Usar similaridade semântica
                matches = self._calculate_semantic_matches(task_descriptions, indicators)
            else:
                # Fallback para substring matching
                matches = 0
                for desc in task_descriptions:
                    desc_lower = desc.lower()
                    if any(indicator in desc_lower for indicator in indicators):
                        matches += 1

            if matches > 0:
                confidence = min(1.0, matches / len(task_descriptions))
                detected.append({
                    'pattern_id': pattern_data['id'],
                    'pattern_name': pattern_name,
                    'confidence': confidence,
                    'quality_score': pattern_data['quality_score'],
                    'complexity_multiplier': pattern_data['complexity_multiplier']
                })

        logger.debug("Architecture patterns detected", count=len(detected))
        return detected

    def detect_anti_patterns(self, task_descriptions: List[str]) -> List[Dict[str, Any]]:
        """
        Detecta anti-padrões em descrições de tarefas.

        Uma tarefa é considerada match quando a média das similaridades cosseno
        entre a descrição e todos os indicadores do anti-padrão é >= semantic_similarity_threshold.
        Usa similaridade semântica se embeddings_generator disponível,
        caso contrário faz fallback para substring matching.

        Args:
            task_descriptions: Lista de descrições de tarefas

        Returns:
            Lista de anti-padrões detectados com penalidades
        """
        anti_patterns = self.architecture_patterns.get('anti_patterns', {})
        detected = []

        for anti_name, anti_data in anti_patterns.items():
            indicators = anti_data.get('indicators', [])

            if self.embeddings_generator:
                # Usar similaridade semântica
                matches = self._calculate_semantic_matches(task_descriptions, indicators)
            else:
                # Fallback para substring matching
                matches = 0
                for desc in task_descriptions:
                    desc_lower = desc.lower()
                    if any(indicator in desc_lower for indicator in indicators):
                        matches += 1

            if matches > 0:
                confidence = min(1.0, matches / len(task_descriptions))
                detected.append({
                    'anti_pattern_id': anti_data['id'],
                    'anti_pattern_name': anti_name,
                    'confidence': confidence,
                    'penalty': anti_data['penalty']
                })

        if detected:
            logger.warning("Anti-patterns detected", count=len(detected))
        return detected

    def _calculate_semantic_matches(self, task_descriptions: List[str], indicators: List[str]) -> int:
        """
        Calcula matches usando similaridade semântica com batch processing otimizado.

        Uma tarefa conta como match quando a média das similaridades cosseno
        com todos os indicadores for >= semantic_similarity_threshold.

        Args:
            task_descriptions: Descrições de tarefas
            indicators: Frases indicadoras do padrão

        Returns:
            Número de matches acima do threshold
        """
        if not self.embeddings_generator or not task_descriptions or not indicators:
            return 0

        try:
            task_embeddings = self.embeddings_generator.get_embeddings(task_descriptions)
            task_embeddings_array = np.array(task_embeddings)

            indicator_embeddings = []
            for indicator in indicators:
                if indicator in self._indicator_embeddings_cache:
                    indicator_embeddings.append(self._indicator_embeddings_cache[indicator])
                else:
                    logger.warning(
                        "Indicador não encontrado no cache, gerando sob demanda",
                        indicator=indicator
                    )
                    emb = self.embeddings_generator.get_embeddings([indicator])[0]
                    self._indicator_embeddings_cache[indicator] = emb
                    indicator_embeddings.append(emb)

            indicator_embeddings_array = np.array(indicator_embeddings)

            task_norms = np.linalg.norm(task_embeddings_array, axis=1, keepdims=True)
            indicator_norms = np.linalg.norm(indicator_embeddings_array, axis=1, keepdims=True)

            task_norms = np.where(task_norms == 0, 1, task_norms)
            indicator_norms = np.where(indicator_norms == 0, 1, indicator_norms)

            task_embeddings_normalized = task_embeddings_array / task_norms
            indicator_embeddings_normalized = indicator_embeddings_array / indicator_norms

            similarity_matrix = np.dot(task_embeddings_normalized, indicator_embeddings_normalized.T)

            avg_similarities = np.mean(similarity_matrix, axis=1)

            matches = int(np.sum(avg_similarities >= self.semantic_similarity_threshold))

            logger.debug(
                "Similaridades semânticas calculadas (batch)",
                num_descriptions=len(task_descriptions),
                num_indicators=len(indicators),
                matches=matches,
                threshold=self.semantic_similarity_threshold,
                avg_similarity=float(np.mean(avg_similarities)),
                max_similarity=float(np.max(avg_similarities))
            )

            return matches

        except Exception as e:
            logger.error(
                "Erro ao calcular similaridades semânticas",
                error=str(e),
                num_descriptions=len(task_descriptions),
                num_indicators=len(indicators)
            )
            return 0

    def get_risk_patterns(self) -> Dict[str, Any]:
        """Retorna padrões de risco da taxonomia."""
        return self.intents_taxonomy.get('risk_patterns', {})
