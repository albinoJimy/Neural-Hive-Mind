"""
FeatureExtractor: Orquestra extração de features estruturadas de planos cognitivos.

Substitui heurísticas de string-match por pipeline de features baseado em:
- Ontologia semântica (OntologyMapper)
- Análise de grafos (GraphAnalyzer)
- Embeddings de linguagem (EmbeddingsGenerator)

Gera feature vector padronizado para inferência de modelos ML.
"""

import numpy as np
import time
from typing import Dict, List, Any, Optional, TYPE_CHECKING
import structlog

from .ontology_mapper import OntologyMapper
from .graph_analyzer import GraphAnalyzer
from .embeddings_generator import EmbeddingsGenerator
from neural_hive_domain import UnifiedDomain

if TYPE_CHECKING:
    from ..metrics import SpecialistMetrics

logger = structlog.get_logger(__name__)


class FeatureExtractor:
    """Extrai features estruturadas de planos cognitivos para ML."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, metrics: Optional["SpecialistMetrics"] = None):
        """
        Inicializa extrator de features.

        Args:
            config: Configuração opcional (ontology_path, embeddings_model)
            metrics: Métricas Prometheus opcionais para instrumentação
        """
        self.config = config or {}
        self.metrics = metrics

        # Inicializar componentes
        # Inicializar embeddings generator primeiro
        self.embeddings_generator = EmbeddingsGenerator(
            model_name=self.config.get('embeddings_model', 'paraphrase-multilingual-MiniLM-L12-v2'),
            cache_size=self.config.get('embedding_cache_size', 1000),
            batch_size=self.config.get('embedding_batch_size', 32),
            metrics=metrics,
            cache_ttl_seconds=self.config.get('embedding_cache_ttl_seconds'),
            cache_enabled=self.config.get('embedding_cache_enabled', True)
        )

        # Passar embeddings_generator para OntologyMapper para usar similaridade semântica
        self.ontology_mapper = OntologyMapper(
            ontology_path=self.config.get('ontology_path'),
            embeddings_generator=self.embeddings_generator,
            semantic_similarity_threshold=self.config.get('semantic_similarity_threshold', 0.7)
        )

        self.graph_analyzer = GraphAnalyzer()

        logger.info("FeatureExtractor initialized", config=self.config)

    def extract_features(self, cognitive_plan: Dict[str, Any], include_embeddings: bool = True) -> Dict[str, Any]:
        """
        Extrai features estruturadas do plano cognitivo.

        Args:
            cognitive_plan: Plano cognitivo validado
            include_embeddings: Se False, pula extração de embeddings

        Returns:
            Dicionário com features categorizadas:
            - metadata_features: Features de metadados
            - ontology_features: Features de ontologia
            - graph_features: Features de grafo
            - embedding_features: Features de embeddings
            - aggregated_features: Features agregadas para modelo
        """
        start_time = time.time()
        logger.info(
            "Extracting features from cognitive plan",
            plan_id=cognitive_plan.get('plan_id')
        )

        tasks = cognitive_plan.get('tasks', [])
        domain = cognitive_plan.get('original_domain')
        priority = cognitive_plan.get('original_priority', 'normal')

        # 1. Features de metadados
        metadata_features = self._extract_metadata_features(cognitive_plan)

        # 2. Features de ontologia
        ontology_features = self._extract_ontology_features(domain, tasks)

        # 3. Features de grafo
        graph_features = self._extract_graph_features(tasks)

        # 4. Features de embeddings
        if include_embeddings:
            embedding_features = self._extract_embedding_features(tasks)
        else:
            embedding_features = {}
            logger.debug("Skipping embedding extraction", plan_id=cognitive_plan.get('plan_id'))

        # 5. Agregar features para modelo
        aggregated_features = self._aggregate_features(
            metadata_features,
            ontology_features,
            graph_features,
            embedding_features
        )

        logger.info(
            "Feature extraction completed",
            plan_id=cognitive_plan.get('plan_id'),
            num_features=len(aggregated_features)
        )
        try:
            if self.metrics:
                self.metrics.observe_feature_extraction_duration(time.time() - start_time)
        except Exception as e:
            logger.warning("feature_extraction_metrics_failed", error=str(e))

        return {
            'metadata_features': metadata_features,
            'ontology_features': ontology_features,
            'graph_features': graph_features,
            'embedding_features': embedding_features,
            'aggregated_features': aggregated_features
        }

    def _extract_metadata_features(self, cognitive_plan: Dict[str, Any]) -> Dict[str, Any]:
        """Extrai features de metadados básicos."""
        import random
        tasks = cognitive_plan.get('tasks', [])

        # Mapear prioridade para numérico com variação para evitar valores estáticos
        # Isso melhora a diversidade do dataset de treinamento
        priority_map = {'low': 0.25, 'normal': 0.5, 'high': 0.75, 'critical': 1.0}
        base_priority = priority_map.get(cognitive_plan.get('original_priority', 'normal'), 0.5)

        # Adicionar jitter de ±0.1 para criar variação nos dados de treinamento
        # Mantém dentro dos limites [0.0, 1.0]
        jitter = random.uniform(-0.1, 0.1)
        priority_score = max(0.0, min(1.0, base_priority + jitter))

        # Calcular duração total
        total_duration_ms = sum(task.get('estimated_duration_ms', 0) for task in tasks)

        features = {
            'num_tasks': len(tasks),
            'priority_score': priority_score,
            'total_duration_ms': total_duration_ms,
            'avg_duration_ms': total_duration_ms / len(tasks) if tasks else 0,
            'has_risk_score': 1.0 if cognitive_plan.get('risk_score') is not None else 0.0,
            'risk_score': cognitive_plan.get('risk_score', 0.5),
            'complexity_score': cognitive_plan.get('complexity_score', 0.5)
        }

        return features

    def _extract_ontology_features(self, domain: str, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extrai features baseadas em ontologia."""
        # Mapear domínio para UnifiedDomain diretamente
        unified_domain = self.ontology_mapper.map_domain_to_unified_domain(domain)

        # Obter metadados da taxonomia para outras features
        taxonomy_entry = self.ontology_mapper.get_taxonomy_entry(domain)

        features = {
            'domain_id': taxonomy_entry['id'] if taxonomy_entry else 'UNKNOWN',
            'domain_risk_weight': taxonomy_entry.get('risk_weight', 0.5) if taxonomy_entry else 0.5,
            'unified_domain': unified_domain,
            'unified_domain_value': unified_domain.value if unified_domain else 'UNKNOWN'
        }

        if unified_domain:
            logger.debug(
                "Domain mapped to UnifiedDomain",
                original_domain=domain,
                unified_domain=unified_domain.value
            )

        # Mapear tipos de tarefa
        task_type_scores = []
        for task in tasks:
            task_type = task.get('task_type', '')
            task_mapping = self.ontology_mapper.map_task_type_to_taxonomy(task_type)
            if task_mapping:
                task_type_scores.append(task_mapping.get('complexity_factor', 1.0))

        features['avg_task_complexity_factor'] = np.mean(task_type_scores) if task_type_scores else 1.0

        # Detectar padrões arquiteturais
        task_descriptions = [task.get('description', '') for task in tasks]
        patterns = self.ontology_mapper.detect_architecture_patterns(task_descriptions)
        anti_patterns = self.ontology_mapper.detect_anti_patterns(task_descriptions)

        features['num_patterns_detected'] = len(patterns)
        features['num_anti_patterns_detected'] = len(anti_patterns)
        features['avg_pattern_quality'] = np.mean([p['quality_score'] for p in patterns]) if patterns else 0.5
        features['total_anti_pattern_penalty'] = sum([ap['penalty'] for ap in anti_patterns])

        return features

    def _extract_graph_features(self, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extrai features de análise de grafo."""
        # Construir grafo
        self.graph_analyzer.build_graph(tasks)

        # Extrair features de grafo
        graph_features = self.graph_analyzer.extract_graph_features()

        # Identificar gargalos
        bottlenecks = self.graph_analyzer.identify_bottlenecks()
        graph_features['num_bottlenecks'] = len(bottlenecks)
        graph_features['has_bottlenecks'] = 1.0 if bottlenecks else 0.0

        # Calcular complexidade
        graph_features['graph_complexity_score'] = self.graph_analyzer.calculate_complexity_score()

        return graph_features

    def _extract_embedding_features(self, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extrai features de embeddings semânticos."""
        # Gerar embeddings de tarefas
        task_embeddings = self.embeddings_generator.generate_task_embeddings(tasks)

        # Gerar embedding agregado do plano
        plan_embedding = self.embeddings_generator.generate_plan_embedding(tasks)

        # Extrair features estatísticas
        statistical_features = self.embeddings_generator.extract_statistical_features(task_embeddings)

        features = {
            'task_embeddings': task_embeddings,  # Array numpy
            'plan_embedding': plan_embedding,    # Array numpy
            **statistical_features
        }

        return features

    def _aggregate_features(self, *feature_dicts) -> Dict[str, Any]:
        """
        Agrega features de diferentes fontes em vetor único.

        Args:
            *feature_dicts: Dicionários de features

        Returns:
            Dicionário com features agregadas (apenas valores numéricos)
        """
        aggregated = {}

        for feature_dict in feature_dicts:
            for key, value in feature_dict.items():
                # Incluir apenas features numéricas (excluir arrays e strings)
                if isinstance(value, (int, float, np.integer, np.floating)):
                    aggregated[key] = float(value)

        return aggregated

    def get_feature_vector(self, cognitive_plan: Dict[str, Any], include_embeddings: bool = True) -> np.ndarray:
        """
        Retorna vetor de features para inferência de modelo.

        Args:
            cognitive_plan: Plano cognitivo validado
            include_embeddings: Se False, pula extração de embeddings

        Returns:
            Array numpy com features agregadas
        """
        features = self.extract_features(cognitive_plan, include_embeddings=include_embeddings)
        aggregated = features['aggregated_features']

        # Ordenar features por chave para consistência
        sorted_keys = sorted(aggregated.keys())
        feature_vector = np.array([aggregated[key] for key in sorted_keys])

        logger.debug(
            "Feature vector generated",
            shape=feature_vector.shape,
            features=sorted_keys
        )

        return feature_vector

    def get_feature_names(self, include_embeddings: bool = True) -> List[str]:
        """
        Retorna nomes das features no vetor.

        Args:
            include_embeddings: Se False, pula extração de embeddings

        Returns:
            Lista ordenada de nomes de features
        """
        # Extrair de um plano dummy para obter nomes
        dummy_plan = {
            'plan_id': 'dummy',
            'tasks': [{'task_id': '1', 'task_type': 'analysis', 'description': 'test', 'dependencies': []}],
            'original_domain': 'test',
            'original_priority': 'normal'
        }

        features = self.extract_features(dummy_plan, include_embeddings=include_embeddings)
        aggregated = features['aggregated_features']

        return sorted(aggregated.keys())
