"""
GraphAnalyzer: Analisa grafos de dependências de tarefas.

Extrai features estruturadas do DAG de tarefas: métricas de centralidade,
caminhos críticos, paralelização potencial, complexidade ciclomática.
"""

import networkx as nx
from typing import Dict, List, Any, Tuple, Optional
import structlog

logger = structlog.get_logger(__name__)


class GraphAnalyzer:
    """Analisa estrutura de grafos de dependências de tarefas."""

    def __init__(self):
        self.graph: Optional[nx.DiGraph] = None

    def build_graph(self, tasks: List[Dict[str, Any]]) -> nx.DiGraph:
        """
        Constrói grafo direcionado de dependências.

        Args:
            tasks: Lista de tarefas do plano cognitivo

        Returns:
            NetworkX DiGraph
        """
        G = nx.DiGraph()

        # Adicionar nós
        for task in tasks:
            task_id = task["task_id"]
            G.add_node(
                task_id,
                task_type=task.get("task_type"),
                duration_ms=task.get("estimated_duration_ms", 0),
                description=task.get("description", ""),
            )

        # Adicionar arestas (dependências)
        for task in tasks:
            task_id = task["task_id"]
            for dep_id in task.get("dependencies", []):
                # Aresta de dependência para tarefa
                G.add_edge(dep_id, task_id)

        self.graph = G
        logger.debug(
            "Graph built", nodes=G.number_of_nodes(), edges=G.number_of_edges()
        )
        return G

    def extract_graph_features(self) -> Dict[str, Any]:
        """
        Extrai features estruturadas do grafo.

        Returns:
            Dicionário com features: centralidade, paralelização, complexidade
        """
        if self.graph is None:
            raise ValueError("Graph not built. Call build_graph() first.")

        G = self.graph
        features = {}

        # Métricas básicas
        features["num_nodes"] = G.number_of_nodes()
        features["num_edges"] = G.number_of_edges()
        features["density"] = nx.density(G)

        # Métricas de centralidade
        if G.number_of_nodes() > 0:
            in_degree_centrality = nx.in_degree_centrality(G)
            out_degree_centrality = nx.out_degree_centrality(G)

            features["avg_in_degree"] = sum(in_degree_centrality.values()) / len(
                in_degree_centrality
            )
            features["max_in_degree"] = max(in_degree_centrality.values())
            features["avg_out_degree"] = sum(out_degree_centrality.values()) / len(
                out_degree_centrality
            )
            features["max_out_degree"] = max(out_degree_centrality.values())

        # Caminho crítico (longest path)
        try:
            critical_path_length = nx.dag_longest_path_length(G)
            features["critical_path_length"] = critical_path_length
        except:
            features["critical_path_length"] = 0

        # Paralelização potencial (largura máxima)
        features["max_parallelism"] = self._calculate_max_parallelism(G)

        # Complexidade (número de níveis) - apenas para DAGs
        # Verificar se há ciclos primeiro
        try:
            if nx.is_directed_acyclic_graph(G):
                features["num_levels"] = len(list(nx.topological_generations(G)))
            else:
                logger.warning(
                    "Graph contains cycles, cannot compute topological levels"
                )
                features["num_levels"] = 0
                features["has_cycles"] = True
        except Exception as e:
            logger.error("Failed to compute num_levels", error=str(e))
            features["num_levels"] = 0

        # Acoplamento (média de dependências)
        total_deps = sum(dict(G.in_degree()).values())
        features["avg_coupling"] = (
            total_deps / G.number_of_nodes() if G.number_of_nodes() > 0 else 0
        )

        logger.debug("Graph features extracted", features=features)
        return features

    def _calculate_max_parallelism(self, G: nx.DiGraph) -> int:
        """
        Calcula número máximo de tarefas que podem executar em paralelo.

        Returns:
            Largura máxima do DAG
        """
        try:
            # Verificar se é DAG antes de calcular gerações topológicas
            if not nx.is_directed_acyclic_graph(G):
                logger.warning("Graph contains cycles, max_parallelism defaulting to 1")
                return 1

            generations = list(nx.topological_generations(G))
            max_width = max(len(gen) for gen in generations) if generations else 0
            return max_width
        except Exception as e:
            logger.error("Failed to calculate max_parallelism", error=str(e))
            return 1

    def identify_bottlenecks(self) -> List[str]:
        """
        Identifica tarefas que são gargalos (alta centralidade de intermediação).

        Returns:
            Lista de task_ids que são gargalos
        """
        if self.graph is None:
            return []

        betweenness = nx.betweenness_centrality(self.graph)
        # Considerar gargalo se betweenness > 0.5
        bottlenecks = [node for node, score in betweenness.items() if score > 0.5]

        if bottlenecks:
            logger.warning(
                "Bottlenecks identified", count=len(bottlenecks), task_ids=bottlenecks
            )

        return bottlenecks

    def calculate_complexity_score(self) -> float:
        """
        Calcula score de complexidade baseado em métricas de grafo.

        Returns:
            Score de complexidade (0.0-1.0)
        """
        features = self.extract_graph_features()

        # Normalizar métricas
        density_score = min(1.0, features["density"] * 2)  # Densidade alta = complexo
        coupling_score = min(
            1.0, features["avg_coupling"] / 3
        )  # Acoplamento alto = complexo
        levels_score = min(1.0, features["num_levels"] / 10)  # Muitos níveis = complexo

        # Média ponderada
        complexity = density_score * 0.3 + coupling_score * 0.4 + levels_score * 0.3

        logger.debug("Complexity calculated", complexity=complexity)
        return complexity
