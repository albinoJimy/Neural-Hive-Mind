"""
Testes para Feature Computation Pipeline

Testa computação de 26 features: metadata, ontology, graph e embedding.
"""

import pytest
from src.services.computation import FeatureComputationPipeline
from src.models.feature import (
    MetadataFeatures,
    OntologyFeatures,
    GraphFeatures,
    EmbeddingFeatures,
    FeatureVector
)


@pytest.fixture
def computation_pipeline():
    """Instância do pipeline de computação"""
    return FeatureComputationPipeline(timeout_seconds=30)


@pytest.fixture
def minimal_cognitive_plan():
    """Plano cognitivo mínimo"""
    return {
        "plan_id": "test-plan-123",
        "priority": "high",
        "tasks": []
    }


@pytest.fixture
def full_cognitive_plan():
    """Plano cognitivo completo com todos os dados"""
    return {
        "plan_id": "test-plan-456",
        "priority": "critical",
        "risk_score": 0.7,
        "complexity_score": 0.8,
        "tasks": [
            {
                "task_id": "task-1",
                "type": "query",
                "estimated_duration_ms": 1000,
                "is_destructive": False,
                "complexity_factor": 0.5
            },
            {
                "task_id": "task-2",
                "type": "transform",
                "estimated_duration_ms": 2000,
                "is_destructive": True,
                "complexity_factor": 0.7
            },
            {
                "task_id": "task-3",
                "type": "validate",
                "estimated_duration_ms": 500,
                "is_destructive": False,
                "complexity_factor": 0.3
            }
        ],
        "ontology": {
            "domain_risk_weight": 0.6,
            "patterns": [
                {"quality": 0.8},
                {"quality": 0.9}
            ],
            "anti_patterns": [
                {"penalty": 0.2}
            ]
        },
        "dependency_graph": {
            "edges": [
                {"source": "task-1", "target": "task-2"},
                {"source": "task-2", "target": "task-3"}
            ],
            "critical_path_length": 3,
            "max_parallelism": 2,
            "num_levels": 3
        },
        "embeddings": {
            "tasks": [
                [0.1, 0.2, 0.3, 0.4],
                [0.5, 0.6, 0.7, 0.8],
                [0.2, 0.3, 0.4, 0.5]
            ]
        }
    }


class TestMetadataFeatures:
    """Testes para computação de features de metadados"""

    def test_compute_metadata_features_empty_plan(self, computation_pipeline, minimal_cognitive_plan):
        """Testa computação de metadados com plano vazio"""
        result = computation_pipeline.compute_metadata_features(minimal_cognitive_plan)

        assert isinstance(result, MetadataFeatures)
        assert result.num_tasks == 0
        assert result.priority_score == 0.75  # high priority

    def test_compute_metadata_features_with_tasks(self, computation_pipeline, full_cognitive_plan):
        """Testa computação de metadados com tarefas"""
        result = computation_pipeline.compute_metadata_features(full_cognitive_plan)

        assert result.num_tasks == 3
        assert result.total_duration_ms == 3500  # 1000 + 2000 + 500
        assert result.avg_duration_ms == pytest.approx(1166.67, rel=0.1)
        assert result.priority_score == 1.0  # critical priority
        assert result.risk_score == 0.7
        assert result.complexity_score == 0.8

    def test_priority_score_mapping(self, computation_pipeline, minimal_cognitive_plan):
        """Testa mapeamento de prioridade para score"""
        # low
        minimal_cognitive_plan["priority"] = "low"
        result = computation_pipeline.compute_metadata_features(minimal_cognitive_plan)
        assert result.priority_score == 0.25

        # medium
        minimal_cognitive_plan["priority"] = "medium"
        result = computation_pipeline.compute_metadata_features(minimal_cognitive_plan)
        assert result.priority_score == 0.5

        # high
        minimal_cognitive_plan["priority"] = "high"
        result = computation_pipeline.compute_metadata_features(minimal_cognitive_plan)
        assert result.priority_score == 0.75

        # critical
        minimal_cognitive_plan["priority"] = "critical"
        result = computation_pipeline.compute_metadata_features(minimal_cognitive_plan)
        assert result.priority_score == 1.0

    def test_risk_score_from_destructive_tasks(self, computation_pipeline):
        """Testa cálculo de risk_score baseado em tarefas destrutivas"""
        plan = {
            "priority": "medium",
            "tasks": [
                {"is_destructive": True},
                {"is_destructive": True},
                {"is_destructive": False}
            ]
        }

        result = computation_pipeline.compute_metadata_features(plan)
        assert result.risk_score == pytest.approx(0.667, rel=0.1)

    def test_complexity_score_from_task_types(self, computation_pipeline):
        """Testa cálculo de complexity_score baseado em tipos de tarefas"""
        plan = {
            "priority": "medium",
            "tasks": [
                {"type": "query"},
                {"type": "transform"},
                {"type": "validate"},
                {"type": "query"}  # tipo repetido
            ]
        }

        result = computation_pipeline.compute_metadata_features(plan)
        assert result.complexity_score == 0.3  # 3 tipos únicos / 10


class TestOntologyFeatures:
    """Testes para computação de features de ontologia"""

    def test_compute_ontology_features_full(self, computation_pipeline, full_cognitive_plan):
        """Testa computação completa de ontologia"""
        result = computation_pipeline.compute_ontology_features(full_cognitive_plan)

        assert isinstance(result, OntologyFeatures)
        assert result.domain_risk_weight == 0.6
        assert result.num_patterns_detected == 2
        assert result.num_anti_patterns_detected == 1
        assert result.total_anti_pattern_penalty == 0.2
        assert result.avg_pattern_quality == pytest.approx(0.85, rel=0.1)

    def test_compute_ontology_features_partial(self, computation_pipeline, full_cognitive_plan):
        """Testa computação parcial de ontologia"""
        plan = full_cognitive_plan.copy()
        plan["ontology"] = {"domain_risk_weight": 0.5}

        result = computation_pipeline.compute_ontology_features(plan)

        assert result.domain_risk_weight == 0.5
        assert result.num_patterns_detected is None

    def test_compute_ontology_features_no_ontology(self, computation_pipeline, minimal_cognitive_plan):
        """Testa quando não há dados de ontologia"""
        result = computation_pipeline.compute_ontology_features(minimal_cognitive_plan)
        assert result is None

    def test_avg_task_complexity_from_tasks(self, computation_pipeline):
        """Testa cálculo de avg_task_complexity das tarefas"""
        plan = {
            "tasks": [
                {"complexity_factor": 0.2},
                {"complexity_factor": 0.6},
                {"complexity_factor": 0.8}
            ]
        }

        result = computation_pipeline.compute_ontology_features(plan)
        assert result is not None
        assert result.avg_task_complexity_factor == pytest.approx(0.533, rel=0.1)


class TestGraphFeatures:
    """Testes para computação de features de grafo"""

    def test_compute_graph_features_full(self, computation_pipeline, full_cognitive_plan):
        """Testa computação completa de grafo"""
        result = computation_pipeline.compute_graph_features(full_cognitive_plan)

        assert isinstance(result, GraphFeatures)
        assert result.num_nodes == 3
        assert result.num_edges == 2
        # Density calculado como num_edges / (num_nodes * (num_nodes - 1) / 2) = 2 / 3 = 0.667
        assert result.density == pytest.approx(0.667, rel=0.1)
        assert result.critical_path_length == 3
        assert result.max_parallelism == 2
        assert result.num_levels == 3

    def test_compute_graph_features_from_tasks_only(self, computation_pipeline):
        """Testa computação de grafo apenas com tarefas"""
        plan = {
            "tasks": [
                {"task_id": "t1", "depends_on": []},
                {"task_id": "t2", "depends_on": ["t1"]},
                {"task_id": "t3", "depends_on": ["t1"]}
            ]
        }

        result = computation_pipeline.compute_graph_features(plan)

        assert result.num_nodes == 3
        assert result.num_edges is None  # sem dependency_graph
        assert result.max_parallelism == 1  # apenas t1 sem dependências
        # O cálculo de níveis agrupa tarefas no mesmo nível quando não dependem umas das outras
        # t1 está no nível 1, t2 e t3 (ambos dependem só de t1) estão no nível 2
        assert result.num_levels == 2  # t1 -> (t2, t3 no mesmo nível)

    def test_compute_graph_features_in_degrees(self, computation_pipeline, full_cognitive_plan):
        """Testa cálculo de graus de entrada"""
        result = computation_pipeline.compute_graph_features(full_cognitive_plan)

        # Edges: (task-1 -> task-2), (task-2 -> task-3)
        # in_degrees: task-2=1, task-3=1
        # avg_in_degree = (1 + 1) / 2 = 1.0 (só conta nós com arestas entrando)
        assert result.avg_in_degree == pytest.approx(1.0, rel=0.1)
        assert result.max_in_degree == 1

    def test_compute_graph_features_no_graph_data(self, computation_pipeline, minimal_cognitive_plan):
        """Testa quando não há dados de grafo"""
        result = computation_pipeline.compute_graph_features(minimal_cognitive_plan)
        assert result is None


class TestEmbeddingFeatures:
    """Testes para computação de features de embeddings"""

    def test_compute_embedding_features_full(self, computation_pipeline, full_cognitive_plan):
        """Testa computação completa de embeddings"""
        result = computation_pipeline.compute_embedding_features(full_cognitive_plan)

        assert isinstance(result, EmbeddingFeatures)
        assert result.mean_norm > 0
        assert result.std_norm >= 0
        assert result.avg_diversity is not None

    def test_compute_embedding_features_norms(self, computation_pipeline):
        """Testa cálculo de normas de embeddings"""
        plan = {
            "embeddings": {
                "tasks": [
                    [0.3, 0.4],  # norm = 0.5
                    [0.6, 0.8]   # norm = 1.0
                ]
            }
        }

        result = computation_pipeline.compute_embedding_features(plan)

        assert result.mean_norm == 0.75
        assert result.std_norm == pytest.approx(0.25, rel=0.1)

    def test_compute_embedding_features_diversity(self, computation_pipeline):
        """Testa cálculo de diversidade entre embeddings"""
        plan = {
            "embeddings": {
                "tasks": [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0]
                ]
            }
        }

        result = computation_pipeline.compute_embedding_features(plan)

        # Embeddings ortogonais têm alta diversidade
        assert result.avg_diversity > 0.5

    def test_compute_embedding_features_no_embeddings(self, computation_pipeline, minimal_cognitive_plan):
        """Testa quando não há embeddings"""
        result = computation_pipeline.compute_embedding_features(minimal_cognitive_plan)
        assert result is None


class TestComputeAll:
    """Testes para computação completa de todas as features"""

    @pytest.mark.asyncio
    async def test_compute_all_features(self, computation_pipeline, full_cognitive_plan):
        """Testa computação de todas as features"""
        result = await computation_pipeline.compute_all("test-plan-456", full_cognitive_plan)

        assert isinstance(result, FeatureVector)
        assert result.plan_id == "test-plan-456"
        assert isinstance(result.metadata, MetadataFeatures)
        assert isinstance(result.ontology, OntologyFeatures)
        assert isinstance(result.graph, GraphFeatures)
        assert isinstance(result.embedding, EmbeddingFeatures)

    @pytest.mark.asyncio
    async def test_compute_all_with_minimal_plan(self, computation_pipeline, minimal_cognitive_plan):
        """Testa computação com plano mínimo"""
        result = await computation_pipeline.compute_all("test-plan-123", minimal_cognitive_plan)

        assert isinstance(result, FeatureVector)
        assert isinstance(result.metadata, MetadataFeatures)
        # Ontology, graph e embedding podem ser None

    @pytest.mark.asyncio
    async def test_compute_all_timeout(self, computation_pipeline):
        """Testa que timeout é configurável"""
        # Apenas verifica que o timeout pode ser configurado
        computation_pipeline.timeout_seconds = 5
        assert computation_pipeline.timeout_seconds == 5

        # Testa que computação simples completa rápido
        plan = {"tasks": [], "priority": "medium"}
        result = await computation_pipeline.compute_all("test", plan)
        assert result is not None


class TestDAGLevelsCalculation:
    """Testes para cálculo de níveis do DAG"""

    def test_calculate_dag_levels_simple(self, computation_pipeline):
        """Testa cálculo simples de níveis"""
        tasks = [
            {"task_id": "t1"},
            {"task_id": "t2", "depends_on": ["t1"]},
            {"task_id": "t3", "depends_on": ["t2"]}
        ]

        levels = computation_pipeline._calculate_dag_levels(tasks)

        assert len(levels) == 3
        assert "t1" in levels[0]
        assert "t2" in levels[1]
        assert "t3" in levels[2]

    def test_calculate_dag_levels_parallel(self, computation_pipeline):
        """Testa DAG com tarefas paralelas"""
        tasks = [
            {"task_id": "t1"},
            {"task_id": "t2", "depends_on": ["t1"]},
            {"task_id": "t3", "depends_on": ["t1"]}
        ]

        levels = computation_pipeline._calculate_dag_levels(tasks)

        assert len(levels) == 2
        assert "t1" in levels[0]
        assert "t2" in levels[1]
        assert "t3" in levels[1]

    def test_calculate_dag_levels_with_task_id_field(self, computation_pipeline):
        """Testa DAG com campo task_id"""
        tasks = [
            {"task_id": "task-1"},
            {"task_id": "task-2", "depends_on": ["task-1"]}
        ]

        levels = computation_pipeline._calculate_dag_levels(tasks)

        assert len(levels) == 2


class TestDiversityCalculation:
    """Testes para cálculo de diversidade de embeddings"""

    def test_diversity_identical_embeddings(self, computation_pipeline):
        """Testa diversidade de embeddings idênticos"""
        embeddings = [
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0]
        ]

        diversity = computation_pipeline._calculate_diversity(embeddings)

        # Embeddings idênticos têm diversidade 0
        assert diversity == pytest.approx(0.0, abs=0.01)

    def test_diversity_opposite_embeddings(self, computation_pipeline):
        """Testa diversidade de embeddings opostos"""
        embeddings = [
            [1.0, 0.0, 0.0],
            [-1.0, 0.0, 0.0]
        ]

        diversity = computation_pipeline._calculate_diversity(embeddings)

        # Embeddings opostos têm diversidade máxima (~1.0)
        assert diversity > 0.9
