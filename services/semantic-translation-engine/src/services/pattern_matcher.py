"""
Pattern Matcher - Detecta padrões complexos em intents

Analisa intermediate representation para identificar padrões conhecidos
que requerem decomposição em múltiplas subtasks coordenadas.
"""

import re
import structlog
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = structlog.get_logger()


@dataclass
class PatternMatch:
    """Resultado de match de padrão"""
    pattern_id: str
    pattern_name: str
    confidence: float
    template: Dict[str, Any]
    matched_criteria: Dict[str, Any] = field(default_factory=dict)


class PatternMatcher:
    """
    Detecta padrões complexos em intents usando biblioteca de templates.

    Analisa objectives, entities e keywords para identificar padrões
    conhecidos que requerem decomposição especial.
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        min_confidence_override: Optional[float] = None
    ):
        """
        Inicializa PatternMatcher com biblioteca de padrões.

        Args:
            config_path: Caminho para patterns.yaml (opcional)
            min_confidence_override: Sobrescreve min_confidence_threshold do YAML (opcional)
        """
        self.logger = structlog.get_logger().bind(component='pattern_matcher')
        self._patterns_data = self._load_patterns(config_path)
        self.patterns = self._patterns_data.get('patterns', {})
        self.config = self._patterns_data.get('matching_config', {
            'min_confidence_threshold': 0.7,
            'keyword_weight': 0.3,
            'objective_weight': 0.5,
            'entity_weight': 0.2,
            'max_patterns_returned': 3
        })

        # Sobrescrever min_confidence_threshold se fornecido via settings
        if min_confidence_override is not None:
            self.config['min_confidence_threshold'] = min_confidence_override
            self.logger.debug(
                'min_confidence_threshold sobrescrito via settings',
                original=self._patterns_data.get('matching_config', {}).get(
                    'min_confidence_threshold', 0.7
                ),
                override=min_confidence_override
            )

        self.logger.info(
            'Biblioteca de padrões carregada',
            num_patterns=len(self.patterns),
            config_path=config_path,
            min_confidence_threshold=self.config.get('min_confidence_threshold')
        )

    def _load_patterns(self, config_path: Optional[str] = None) -> Dict:
        """
        Carrega biblioteca de padrões do YAML.

        Args:
            config_path: Caminho customizado para patterns.yaml

        Returns:
            Dict com padrões e configurações
        """
        if config_path:
            path = Path(config_path)
        else:
            # Caminho padrão relativo ao arquivo atual
            path = Path(__file__).parent.parent.parent / 'config' / 'patterns.yaml'

        try:
            if not path.exists():
                self.logger.warning(
                    'Arquivo de padrões não encontrado',
                    path=str(path)
                )
                return {}

            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data:
                self.logger.warning('Arquivo de padrões vazio')
                return {}

            # Validar estrutura básica
            if 'patterns' not in data:
                self.logger.warning('Arquivo de padrões sem seção patterns')
                return {}

            return data

        except yaml.YAMLError as e:
            self.logger.error(
                'Erro ao parsear YAML de padrões',
                error=str(e),
                path=str(path)
            )
            return {}
        except Exception as e:
            self.logger.error(
                'Erro ao carregar padrões',
                error=str(e),
                path=str(path)
            )
            return {}

    def match(self, intermediate_repr: Dict[str, Any]) -> List[PatternMatch]:
        """
        Detecta padrões no intermediate representation.

        Args:
            intermediate_repr: Representação intermediária do intent

        Returns:
            Lista de PatternMatch ordenada por confiança (maior primeiro)
        """
        if not self.patterns:
            return []

        # Extrair dados do intermediate representation com tratamento de None
        raw_objectives = intermediate_repr.get('objectives') or []
        objectives = [
            obj.lower() for obj in raw_objectives if obj
        ]
        entities = intermediate_repr.get('entities') or []
        text = intermediate_repr.get('text') or intermediate_repr.get('original_text') or ''

        matches = []
        threshold = self.config.get('min_confidence_threshold', 0.7)

        for pattern_id, pattern in self.patterns.items():
            score, matched_criteria = self._calculate_match_score(
                pattern,
                objectives,
                entities,
                text
            )

            self.logger.debug(
                'Score de match calculado',
                pattern_id=pattern_id,
                score=score,
                threshold=threshold
            )

            if score >= threshold:
                matches.append(PatternMatch(
                    pattern_id=pattern_id,
                    pattern_name=pattern.get('name', pattern_id),
                    confidence=score,
                    template=pattern.get('template', {}),
                    matched_criteria=matched_criteria
                ))

        # Ordenar por confiança decrescente
        matches.sort(key=lambda m: m.confidence, reverse=True)

        # Limitar número de padrões retornados
        max_patterns = self.config.get('max_patterns_returned', 3)
        return matches[:max_patterns]

    def _calculate_match_score(
        self,
        pattern: Dict,
        objectives: List[str],
        entities: List[Dict],
        text: str
    ) -> tuple[float, Dict[str, Any]]:
        """
        Calcula score de match para um padrão.

        Combina scores de:
        - Objectives match (all_of, any_of)
        - Entities match (min_count, types)
        - Keywords match (presença no texto)

        Args:
            pattern: Definição do padrão
            objectives: Lista de objectives extraídos
            entities: Lista de entidades extraídas
            text: Texto original do intent

        Returns:
            Tupla (score entre 0.0 e 1.0, critérios matched)
        """
        criteria = pattern.get('match_criteria', {})
        matched_criteria = {}

        # Validação precoce: se min_count é definido e não há entidades suficientes,
        # retornar score 0.0 imediatamente para evitar falsos positivos
        entity_criteria = criteria.get('entities', {})
        min_count = entity_criteria.get('min_count', 0)
        if min_count > 0 and len(entities) < min_count:
            matched_criteria['entities'] = {
                'score': 0.0,
                'count': len(entities),
                'min_count_required': min_count,
                'reason': 'min_count não satisfeito'
            }
            return 0.0, matched_criteria

        # Calcular score de objectives
        obj_score = self._match_objectives(
            criteria.get('objectives', {}),
            objectives
        )
        matched_criteria['objectives'] = {
            'score': obj_score,
            'matched': objectives
        }

        # Se objectives é all_of e não satisfeito, retornar 0
        obj_criteria = criteria.get('objectives', {})
        if 'all_of' in obj_criteria and obj_score == 0:
            return 0.0, matched_criteria

        # Calcular score de entities
        ent_score = self._match_entities(
            criteria.get('entities', {}),
            entities
        )
        matched_criteria['entities'] = {
            'score': ent_score,
            'count': len(entities)
        }

        # Calcular score de keywords
        keywords = criteria.get('keywords', [])
        kw_score = self._match_keywords(keywords, text) if keywords else 1.0
        matched_criteria['keywords'] = {
            'score': kw_score,
            'text_sample': text[:100] if text else ''
        }

        # Combinar scores com pesos
        obj_weight = self.config.get('objective_weight', 0.5)
        ent_weight = self.config.get('entity_weight', 0.2)
        kw_weight = self.config.get('keyword_weight', 0.3)

        # Se não há keywords no critério, redistribuir peso
        if not keywords:
            total_weight = obj_weight + ent_weight
            obj_weight = obj_weight / total_weight if total_weight > 0 else 0.5
            ent_weight = ent_weight / total_weight if total_weight > 0 else 0.5
            kw_weight = 0
            final_score = (obj_score * obj_weight) + (ent_score * ent_weight)
        else:
            final_score = (
                (obj_score * obj_weight) +
                (ent_score * ent_weight) +
                (kw_score * kw_weight)
            )

        return final_score, matched_criteria

    def _match_objectives(
        self,
        criteria: Dict,
        objectives: List[str]
    ) -> float:
        """
        Calcula score de match de objectives.

        Args:
            criteria: Critérios de objectives (all_of, any_of)
            objectives: Lista de objectives do intent

        Returns:
            Score entre 0.0 e 1.0
        """
        if not criteria:
            return 1.0  # Sem critério = sempre match

        objectives_set = set(objectives)

        # all_of: todos devem estar presentes
        if 'all_of' in criteria:
            required = set(obj.lower() for obj in criteria['all_of'])
            if required.issubset(objectives_set):
                return 1.0
            return 0.0

        # any_of: pelo menos um deve estar presente
        if 'any_of' in criteria:
            any_of = set(obj.lower() for obj in criteria['any_of'])
            matched = objectives_set.intersection(any_of)
            if not any_of:
                return 1.0
            return len(matched) / len(any_of)

        return 1.0

    def _match_entities(
        self,
        criteria: Dict,
        entities: List[Dict]
    ) -> float:
        """
        Calcula score de match de entities.

        Args:
            criteria: Critérios de entities (min_count, types)
            entities: Lista de entidades do intent

        Returns:
            Score entre 0.0 e 1.0
        """
        if not criteria:
            return 1.0  # Sem critério = sempre match

        min_count = criteria.get('min_count', 0)
        expected_types = criteria.get('types', [])

        # Verificar min_count
        if len(entities) < min_count:
            return 0.0

        # Se não há tipos esperados, retornar 1.0 se min_count satisfeito
        if not expected_types:
            return 1.0

        # Verificar tipos
        expected_types_lower = set(t.lower() for t in expected_types)
        entity_types = set()

        for entity in entities:
            # Verificar canonical_type e original_type
            canonical = entity.get('canonical_type', '').lower()
            original = entity.get('original_type', '').lower()
            entity_type = entity.get('type', '').lower()

            if canonical:
                entity_types.add(canonical)
            if original:
                entity_types.add(original)
            if entity_type:
                entity_types.add(entity_type)

        matched_types = entity_types.intersection(expected_types_lower)

        if not expected_types_lower:
            return 1.0

        return len(matched_types) / len(expected_types_lower)

    def _match_keywords(
        self,
        keywords: List[str],
        text: str
    ) -> float:
        """
        Calcula score de match de keywords.

        Args:
            keywords: Lista de keywords esperadas
            text: Texto do intent

        Returns:
            Score entre 0.0 e 1.0
        """
        if not keywords:
            return 1.0

        if not text:
            return 0.0

        text_lower = text.lower()
        matched_count = 0

        for keyword in keywords:
            # Match de palavra completa (word boundary)
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            if re.search(pattern, text_lower):
                matched_count += 1

        return matched_count / len(keywords)

    def get_template(self, pattern_id: str) -> Optional[Dict]:
        """
        Retorna template de decomposição para padrão específico.

        Args:
            pattern_id: ID do padrão (ex: 'user_onboarding')

        Returns:
            Template dict ou None se não encontrado
        """
        pattern = self.patterns.get(pattern_id)
        if not pattern:
            return None
        return pattern.get('template')
