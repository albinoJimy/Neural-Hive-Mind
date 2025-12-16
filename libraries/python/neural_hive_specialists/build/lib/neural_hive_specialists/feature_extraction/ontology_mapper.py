"""
OntologyMapper: Mapeia planos cognitivos para ontologia estruturada.

Substitui heurísticas de string-match por mapeamento semântico estruturado
baseado em ontologias JSON carregadas de `/ontologies/`.
"""

import json
import os
from typing import Dict, List, Any, Optional
import structlog
from pathlib import Path

logger = structlog.get_logger(__name__)


class OntologyMapper:
    """Mapeia elementos de plano cognitivo para IDs de ontologia."""

    def __init__(self, ontology_path: Optional[str] = None, embeddings_generator=None):
        self.ontology_path = ontology_path or self._get_default_ontology_path()
        self.intents_taxonomy = self._load_taxonomy('intents_taxonomy.json')
        self.architecture_patterns = self._load_taxonomy('architecture_patterns.json')
        self.embeddings_generator = embeddings_generator
        self.semantic_similarity_threshold = 0.7  # Threshold configurável
        self._indicator_embeddings_cache = {}  # Cache para embeddings de indicadores
        logger.info("OntologyMapper initialized", ontology_path=self.ontology_path)

    def _get_default_ontology_path(self) -> str:
        """Retorna caminho padrão para ontologias."""
        # Assume ontologies/ na raiz do projeto
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent.parent.parent
        return str(project_root / 'ontologies')

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
        Calcula matches usando similaridade semântica.

        Args:
            task_descriptions: Descrições de tarefas
            indicators: Frases indicadoras do padrão

        Returns:
            Número de matches acima do threshold
        """
        if not self.embeddings_generator or not task_descriptions or not indicators:
            return 0

        matches = 0

        for desc in task_descriptions:
            # Calcular similaridade média entre descrição e todos os indicadores
            similarities = []

            for indicator in indicators:
                try:
                    similarity = self.embeddings_generator.calculate_semantic_similarity(desc, indicator)
                    similarities.append(similarity)
                except Exception as e:
                    logger.warning("Failed to calculate semantic similarity", error=str(e))
                    continue

            if similarities:
                avg_similarity = sum(similarities) / len(similarities)

                if avg_similarity >= self.semantic_similarity_threshold:
                    matches += 1

        logger.debug(
            "Semantic matches calculated",
            num_descriptions=len(task_descriptions),
            num_indicators=len(indicators),
            matches=matches,
            threshold=self.semantic_similarity_threshold
        )

        return matches

    def get_risk_patterns(self) -> Dict[str, Any]:
        """Retorna padrões de risco da taxonomia."""
        return self.intents_taxonomy.get('risk_patterns', {})
