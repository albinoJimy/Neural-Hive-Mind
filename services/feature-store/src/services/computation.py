"""
Feature Computation Pipeline

Computa 26 features a partir de Cognitive Plans:
- 6 Metadata features
- 6 Ontology features
- 11 Graph features
- 3 Embedding features
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from src.models.feature import (
    EmbeddingFeatures,
    FeatureVector,
    GraphFeatures,
    MetadataFeatures,
    OntologyFeatures,
)

logger = structlog.get_logger()


class FeatureComputationPipeline:
    """Pipeline para computação de features"""

    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    async def compute_all(self, plan_id: str, cognitive_plan: dict[str, Any]) -> FeatureVector:
        """
        Computa todas as features para um plano

        Args:
            plan_id: ID do plano
            cognitive_plan: Dados do plano cognitivo

        Returns:
            FeatureVector com todas as features computadas
        """
        start_time = datetime.now(timezone.utc)

        try:
            # Executa computação com timeout
            result = await asyncio.wait_for(
                self._compute_features_async(plan_id, cognitive_plan), timeout=self.timeout_seconds
            )

            elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.info("Features computadas com sucesso", plan_id=plan_id, elapsed_ms=elapsed_ms)

            return result

        except asyncio.TimeoutError:
            logger.error("Timeout na computação de features", plan_id=plan_id)
            raise
        except Exception as e:
            logger.error("Erro na computação de features", plan_id=plan_id, error=str(e))
            raise

    async def _compute_features_async(
        self, plan_id: str, cognitive_plan: dict[str, Any]
    ) -> FeatureVector:
        """Executa computação de features de forma assíncrona"""

        # Computa features em paralelo usando wrapper async
        async def compute_metadata():
            return self.compute_metadata_features(cognitive_plan)

        async def compute_ontology():
            return self.compute_ontology_features(cognitive_plan)

        async def compute_graph():
            return self.compute_graph_features(cognitive_plan)

        async def compute_embedding():
            return self.compute_embedding_features(cognitive_plan)

        metadata, ontology, graph, embedding = await asyncio.gather(
            compute_metadata(),
            compute_ontology(),
            compute_graph(),
            compute_embedding(),
            return_exceptions=True,
        )

        # Trata exceções
        if isinstance(metadata, Exception):
            logger.error("Erro ao computar metadata features", error=str(metadata))
            metadata = None
        if isinstance(ontology, Exception):
            logger.warning("Erro ao computar ontology features", error=str(ontology))
            ontology = None
        if isinstance(graph, Exception):
            logger.warning("Erro ao computar graph features", error=str(graph))
            graph = None
        if isinstance(embedding, Exception):
            logger.warning("Erro ao computar embedding features", error=str(embedding))
            embedding = None

        return FeatureVector(
            plan_id=plan_id,
            metadata=metadata or self._default_metadata(),
            ontology=ontology,
            graph=graph,
            embedding=embedding,
        )

    def compute_metadata_features(self, cognitive_plan: dict[str, Any]) -> MetadataFeatures:
        """
        Computa features de metadados (6 features)

        Args:
            cognitive_plan: Plano cognitivo

        Returns:
            MetadataFeatures
        """
        tasks = cognitive_plan.get("tasks", [])

        # num_tasks: Número de tarefas
        num_tasks = len(tasks)

        # priority_score: Score de prioridade normalizado (0-1)
        priority_map = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}
        raw_priority = cognitive_plan.get("priority", "medium").lower()
        priority_score = priority_map.get(raw_priority, 0.5)

        # total_duration_ms: Soma das durações estimadas
        total_duration_ms = 0.0
        for task in tasks:
            duration = task.get("estimated_duration_ms", 0) or task.get("duration_ms", 0)
            if duration:
                total_duration_ms += duration

        # avg_duration_ms: Duração média por tarefa
        avg_duration_ms = (
            (total_duration_ms / num_tasks if num_tasks > 0 else 0.0)
            if total_duration_ms > 0
            else None
        )

        # risk_score: Score de risco do plano
        risk_score = cognitive_plan.get("risk_score")
        if risk_score is None:
            # Calcula a partir das tarefas destrutivas
            destructive_count = sum(1 for t in tasks if t.get("is_destructive", False))
            risk_score = min(1.0, destructive_count / max(num_tasks, 1))

        # complexity_score: Baseado em tipos de tarefas
        complexity_score = cognitive_plan.get("complexity_score")
        if complexity_score is None:
            # Calcula baseado na diversidade de tipos
            task_types = set(t.get("type", "unknown") for t in tasks)
            complexity_score = min(1.0, len(task_types) / 10)

        return MetadataFeatures(
            num_tasks=num_tasks,
            priority_score=priority_score,
            total_duration_ms=total_duration_ms or None,
            avg_duration_ms=avg_duration_ms,
            risk_score=risk_score,
            complexity_score=complexity_score,
        )

    def compute_ontology_features(
        self, cognitive_plan: dict[str, Any]
    ) -> Optional[OntologyFeatures]:
        """
        Computa features de ontologia (6 features)

        Args:
            cognitive_plan: Plano cognitivo

        Returns:
            OntologyFeatures ou None se dados insuficientes
        """
        ontology_data = cognitive_plan.get("ontology", {})

        # domain_risk_weight: Peso de risco do domínio
        domain_risk_weight = ontology_data.get("domain_risk_weight")

        # avg_task_complexity_factor: Fator médio de complexidade
        tasks = cognitive_plan.get("tasks", [])
        avg_task_complexity_factor = None
        if tasks:
            complexity_factors = [t.get("complexity_factor", 0.5) or 0.5 for t in tasks]
            avg_task_complexity_factor = sum(complexity_factors) / len(complexity_factors)
        else:
            avg_task_complexity_factor = ontology_data.get("avg_task_complexity_factor")

        # num_patterns_detected: Padrões arquiteturais
        patterns = ontology_data.get("patterns", [])
        num_patterns_detected = len(patterns) if patterns else None

        # num_anti_patterns_detected: Anti-padrões
        anti_patterns = ontology_data.get("anti_patterns", [])
        num_anti_patterns_detected = len(anti_patterns) if anti_patterns else None

        # avg_pattern_quality: Qualidade média dos padrões
        if patterns:
            qualities = [p.get("quality", 0.5) for p in patterns if "quality" in p]
            avg_pattern_quality = sum(qualities) / len(qualities) if qualities else None
        else:
            avg_pattern_quality = None

        # total_anti_pattern_penalty: Penalidade total
        if anti_patterns:
            total_anti_pattern_penalty = sum(ap.get("penalty", 0.1) for ap in anti_patterns)
        else:
            total_anti_pattern_penalty = None

        # Se não há dados de ontologia ou tarefas, retorna None
        if not ontology_data and not tasks:
            return None

        return OntologyFeatures(
            domain_risk_weight=domain_risk_weight,
            avg_task_complexity_factor=avg_task_complexity_factor,
            num_patterns_detected=num_patterns_detected,
            num_anti_patterns_detected=num_anti_patterns_detected,
            avg_pattern_quality=avg_pattern_quality,
            total_anti_pattern_penalty=total_anti_pattern_penalty,
        )

        # num_patterns_detected: Padrões arquiteturais
        patterns = ontology_data.get("patterns", [])
        num_patterns_detected = len(patterns) if patterns else None

        # num_anti_patterns_detected: Anti-padrões
        anti_patterns = ontology_data.get("anti_patterns", [])
        num_anti_patterns_detected = len(anti_patterns) if anti_patterns else None

        # avg_pattern_quality: Qualidade média dos padrões
        if patterns:
            qualities = [p.get("quality", 0.5) for p in patterns if "quality" in p]
            avg_pattern_quality = sum(qualities) / len(qualities) if qualities else None
        else:
            avg_pattern_quality = None

        # total_anti_pattern_penalty: Penalidade total
        if anti_patterns:
            total_anti_pattern_penalty = sum(ap.get("penalty", 0.1) for ap in anti_patterns)
        else:
            total_anti_pattern_penalty = None

        return OntologyFeatures(
            domain_risk_weight=domain_risk_weight,
            avg_task_complexity_factor=avg_task_complexity_factor,
            num_patterns_detected=num_patterns_detected,
            num_anti_patterns_detected=num_anti_patterns_detected,
            avg_pattern_quality=avg_pattern_quality,
            total_anti_pattern_penalty=total_anti_pattern_penalty,
        )

    def compute_graph_features(self, cognitive_plan: dict[str, Any]) -> Optional[GraphFeatures]:
        """
        Computa features de grafo (11 features)

        Args:
            cognitive_plan: Plano cognitivo

        Returns:
            GraphFeatures ou None se dados insuficientes
        """
        graph_data = cognitive_plan.get("dependency_graph", {})
        tasks = cognitive_plan.get("tasks", [])

        if not graph_data and not tasks:
            return None

        # num_nodes: Número de nós (tarefas)
        num_nodes = len(tasks)

        # num_edges: Número de arestas (dependências)
        edges = graph_data.get("edges", [])
        num_edges = len(edges) if edges else None

        # density: Densidade do grafo
        density = None
        if num_nodes and num_edges is not None:
            max_edges = (num_nodes * (num_nodes - 1)) / 2
            density = num_edges / max_edges if max_edges > 0 else 0.0

        # Graus (in_degree)
        in_degrees = defaultdict(int)
        for edge in edges:
            target = edge.get("target")
            if target:
                in_degrees[target] += 1

        # avg_in_degree: Grau médio
        avg_in_degree = None
        if in_degrees:
            avg_in_degree = sum(in_degrees.values()) / len(in_degrees)

        # max_in_degree: Grau máximo
        max_in_degree = max(in_degrees.values()) if in_degrees else None

        # critical_path_length: Caminho crítico
        critical_path_length = graph_data.get("critical_path_length")

        # max_parallelism: Paralelismo máximo
        max_parallelism = graph_data.get("max_parallelism")
        if max_parallelism is None and tasks:
            # Estima baseado em tarefas sem dependências
            no_deps = sum(1 for t in tasks if not t.get("depends_on"))
            max_parallelism = no_deps if no_deps > 0 else None

        # num_levels: Níveis do DAG
        num_levels = graph_data.get("num_levels")
        if num_levels is None and tasks:
            # Calcula baseado em profundidade de dependências
            levels = self._calculate_dag_levels(tasks)
            num_levels = len(levels) if levels else None

        # avg_coupling: Acoplamento médio
        avg_coupling = None
        if num_edges is not None and num_nodes > 0:
            avg_coupling = (num_edges * 2) / num_nodes

        # num_bottlenecks: Gargalos (nós com alto in_degree)
        num_bottlenecks = None
        if in_degrees:
            bottleneck_threshold = max(in_degrees.values()) * 0.7 if in_degrees else 0
            num_bottlenecks = sum(
                1 for degree in in_degrees.values() if degree >= bottleneck_threshold
            )

        # graph_complexity_score: Score de complexidade
        graph_complexity_score = None
        if all(v is not None for v in [num_nodes, num_edges, density]):
            # Normaliza e combina métricas
            node_factor = min(1.0, num_nodes / 100)
            edge_factor = min(1.0, (num_edges or 0) / 200)
            density_factor = density or 0.0
            graph_complexity_score = (node_factor + edge_factor + density_factor) / 3

        return GraphFeatures(
            num_nodes=num_nodes,
            num_edges=num_edges,
            density=density,
            avg_in_degree=avg_in_degree,
            max_in_degree=max_in_degree,
            critical_path_length=critical_path_length,
            max_parallelism=max_parallelism,
            num_levels=num_levels,
            avg_coupling=avg_coupling,
            num_bottlenecks=num_bottlenecks,
            graph_complexity_score=graph_complexity_score,
        )

    def compute_embedding_features(
        self, cognitive_plan: dict[str, Any]
    ) -> Optional[EmbeddingFeatures]:
        """
        Computa features de embeddings (3 features)

        Args:
            cognitive_plan: Plano cognitivo

        Returns:
            EmbeddingFeatures ou None se dados insuficientes
        """
        embeddings_data = cognitive_plan.get("embeddings", {})
        task_embeddings = embeddings_data.get("tasks", [])

        if not task_embeddings:
            return None

        # Calcula normas dos embeddings
        norms = []
        for emb in task_embeddings:
            if isinstance(emb, list) and len(emb) > 0:
                norm = sum(x**2 for x in emb) ** 0.5
                norms.append(norm)

        if not norms:
            return None

        # mean_norm: Norma média
        mean_norm = sum(norms) / len(norms)

        # std_norm: Desvio padrão da norma
        if len(norms) > 1:
            mean = mean_norm
            variance = sum((n - mean) ** 2 for n in norms) / len(norms)
            std_norm = variance**0.5
        else:
            std_norm = 0.0

        # avg_diversity: Diversidade média (similaridade cosseno)
        avg_diversity = self._calculate_diversity(task_embeddings)

        return EmbeddingFeatures(
            mean_norm=mean_norm, std_norm=std_norm, avg_diversity=avg_diversity
        )

    def _calculate_dag_levels(self, tasks: list[dict[str, Any]]) -> list[list[str]]:
        """Calcula níveis do DAG baseado em dependências"""
        task_ids = {t.get("task_id") or t.get("id") for t in tasks}
        levels = []

        remaining = set(task_ids)
        processed = set()

        while remaining:
            # Tarefas sem dependências pendentes
            current_level = [
                tid
                for tid in remaining
                if all(
                    dep not in remaining or dep in processed
                    for dep in self._get_task_deps(tid, tasks)
                )
            ]

            if not current_level:
                break  # Ciclo detectado

            levels.append(current_level)
            processed.update(current_level)
            remaining -= set(current_level)

        return levels

    def _get_task_deps(self, task_id: str, tasks: list[dict[str, Any]]) -> list[str]:
        """Obtém dependências de uma tarefa"""
        for task in tasks:
            tid = task.get("task_id") or task.get("id")
            if tid == task_id:
                return task.get("depends_on", []) or []
        return []

    def _calculate_diversity(self, embeddings: list[list[float]]) -> Optional[float]:
        """Calcula diversidade média entre embeddings"""
        if len(embeddings) < 2:
            return None

        diversities = []
        for i, emb1 in enumerate(embeddings):
            for emb2 in embeddings[i + 1 :]:
                # Similaridade cosseno
                dot = sum(a * b for a, b in zip(emb1, emb2))
                norm1 = sum(a**2 for a in emb1) ** 0.5
                norm2 = sum(b**2 for b in emb2) ** 0.5

                if norm1 > 0 and norm2 > 0:
                    similarity = dot / (norm1 * norm2)
                    diversities.append(1.0 - similarity)  # Diversidade = 1 - similaridade

        return sum(diversities) / len(diversities) if diversities else None

    def _default_metadata(self) -> MetadataFeatures:
        """Retorna metadata features padrão"""
        return MetadataFeatures(
            num_tasks=0,
            priority_score=0.5,
            total_duration_ms=None,
            avg_duration_ms=None,
            risk_score=None,
            complexity_score=None,
        )


def get_computation_pipeline(timeout_seconds: int = 30) -> FeatureComputationPipeline:
    """Factory para FeatureComputationPipeline"""
    return FeatureComputationPipeline(timeout_seconds=timeout_seconds)
