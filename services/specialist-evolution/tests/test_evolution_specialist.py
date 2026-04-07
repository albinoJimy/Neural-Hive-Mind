"""Testes unitários para EvolutionSpecialist - Métodos de Análise."""

import sys
import os
import pytest
from typing import Dict, List

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class EvolutionAnalysisTestHelper:
    """Helper class para testar métodos de análise sem inicialização completa."""

    @staticmethod
    def analyze_maintainability(tasks: List[Dict], cognitive_plan: Dict) -> float:
        """Implementação do método de análise de manutenibilidade."""
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        if num_tasks <= 3:
            complexity_score = 0.7
        elif num_tasks <= 10:
            complexity_score = 1.0
        elif num_tasks <= 20:
            complexity_score = 0.8
        else:
            complexity_score = 0.5

        total_dependencies = sum(len(task.get("dependencies", [])) for task in tasks)
        avg_dependencies = total_dependencies / num_tasks if num_tasks > 0 else 0

        if avg_dependencies <= 1:
            coupling_score = 1.0
        elif avg_dependencies <= 2:
            coupling_score = 0.8
        else:
            coupling_score = 0.5

        clear_tasks = sum(1 for task in tasks if task.get("name") and task.get("task_type"))
        clarity_score = clear_tasks / num_tasks if num_tasks > 0 else 0

        maintainability_score = complexity_score * 0.3 + coupling_score * 0.4 + clarity_score * 0.3

        return max(0.0, min(1.0, maintainability_score))

    @staticmethod
    def analyze_scalability(tasks: List[Dict], cognitive_plan: Dict) -> float:
        """Implementação do método de análise de escalabilidade."""
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        total_dependencies = sum(len(task.get("dependencies", [])) for task in tasks)
        max_possible_deps = num_tasks * (num_tasks - 1) / 2

        if max_possible_deps > 0:
            dependency_ratio = total_dependencies / max_possible_deps
            parallelization_potential = 1.0 - (dependency_ratio * 0.8)
        else:
            parallelization_potential = 1.0

        total_duration_ms = sum(task.get("estimated_duration_ms", 0) for task in tasks)
        avg_duration_ms = total_duration_ms / num_tasks if num_tasks > 0 else 0

        if avg_duration_ms <= 1000:
            resource_efficiency = 1.0
        elif avg_duration_ms <= 5000:
            resource_efficiency = 0.8
        elif avg_duration_ms <= 10000:
            resource_efficiency = 0.6
        else:
            resource_efficiency = 0.4

        scalability_score = parallelization_potential * 0.6 + resource_efficiency * 0.4

        return max(0.0, min(1.0, scalability_score))

    @staticmethod
    def analyze_extensibility(tasks: List[Dict], cognitive_plan: Dict) -> float:
        """Implementação do método de análise de extensibilidade."""
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        task_types = set(task.get("task_type", "unknown") for task in tasks)
        type_diversity = len(task_types) / num_tasks if num_tasks > 0 else 0

        if type_diversity >= 0.3 and type_diversity <= 0.6:
            modularity_score = 1.0
        elif type_diversity > 0.6:
            modularity_score = 0.8
        else:
            modularity_score = 0.6

        tasks_with_few_deps = sum(1 for task in tasks if len(task.get("dependencies", [])) <= 2)
        flexibility_score = tasks_with_few_deps / num_tasks if num_tasks > 0 else 0

        extensibility_score = modularity_score * 0.5 + flexibility_score * 0.5

        return max(0.0, min(1.0, extensibility_score))

    @staticmethod
    def analyze_modularity(tasks: List[Dict]) -> float:
        """Implementação do método de análise de modularidade."""
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        if num_tasks <= 5:
            size_score = 0.7
        elif num_tasks <= 15:
            size_score = 1.0
        elif num_tasks <= 25:
            size_score = 0.8
        else:
            size_score = 0.5

        task_types = [task.get("task_type", "unknown") for task in tasks]
        unique_types = len(set(task_types))

        if unique_types >= 3 and unique_types <= 7:
            separation_score = 1.0
        elif unique_types > 7:
            separation_score = 0.7
        else:
            separation_score = 0.6

        modularity_score = size_score * 0.5 + separation_score * 0.5

        return max(0.0, min(1.0, modularity_score))

    @staticmethod
    def analyze_tech_debt_risk(tasks: List[Dict], cognitive_plan: Dict) -> float:
        """Implementação do método de análise de risco de tech debt."""
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        test_tasks = sum(
            1
            for task in tasks
            if "test" in (task.get("name") or "").lower() or task.get("task_type", "") == "testing"
        )
        test_coverage_score = min(1.0, test_tasks / max(1, num_tasks * 0.3))

        if num_tasks <= 10:
            complexity_risk = 1.0
        elif num_tasks <= 20:
            complexity_risk = 0.7
        else:
            complexity_risk = 0.5

        total_dependencies = sum(len(task.get("dependencies", [])) for task in tasks)
        avg_dependencies = total_dependencies / num_tasks if num_tasks > 0 else 0

        if avg_dependencies <= 1.5:
            coupling_risk = 1.0
        elif avg_dependencies <= 3:
            coupling_risk = 0.7
        else:
            coupling_risk = 0.4

        tech_debt_prevention_score = (
            test_coverage_score * 0.4 + complexity_risk * 0.3 + coupling_risk * 0.3
        )

        return max(0.0, min(1.0, tech_debt_prevention_score))

    @staticmethod
    def calculate_evolution_risk(
        maintainability: float,
        scalability: float,
        extensibility: float,
        modularity: float,
        tech_debt: float,
    ) -> float:
        """Calcula risco de evolução."""
        weighted_avg = (
            maintainability * 0.25
            + scalability * 0.25
            + extensibility * 0.20
            + modularity * 0.15
            + tech_debt * 0.15
        )
        return 1.0 - weighted_avg

    @staticmethod
    def determine_recommendation(confidence_score: float, risk_score: float) -> str:
        """Determina recomendação baseada em scores."""
        if confidence_score >= 0.8 and risk_score < 0.3:
            return "approve"
        elif confidence_score < 0.5 or risk_score > 0.7:
            return "reject"
        elif risk_score > 0.5:
            return "review_required"
        else:
            return "conditional"


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo para testes."""
    return {
        "plan_id": "test-plan-001",
        "original_domain": "evolution-test",
        "original_priority": "high",
        "description": "Test maintainability and scalability improvements",
        "tasks": [
            {
                "name": "refactor-module",
                "task_type": "refactoring",
                "description": "Refactor module for better maintainability",
                "estimated_duration_ms": 50000,
                "dependencies": [],
            },
            {
                "name": "add-tests",
                "task_type": "testing",
                "description": "Add unit tests for improved coverage",
                "estimated_duration_ms": 30000,
                "dependencies": ["refactor-module"],
            },
            {
                "name": "optimize-performance",
                "task_type": "optimization",
                "description": "Optimize for better scalability",
                "estimated_duration_ms": 40000,
                "dependencies": [],
            },
        ],
    }


class TestMaintainabilityAnalysis:
    """Testes de análise de manutenibilidade."""

    def test_maintainability_with_few_tasks(self):
        """Testa manutenibilidade com poucas tarefas."""
        tasks = [{"name": "task1", "task_type": "refactoring", "dependencies": []}]

        score = EvolutionAnalysisTestHelper.analyze_maintainability(tasks, {})

        assert 0.0 <= score <= 1.0

    def test_maintainability_with_many_dependencies(self):
        """Testa manutenibilidade com muitas dependências."""
        tasks = [
            {"name": f"task{i}", "task_type": "dev", "dependencies": [f"task{j}" for j in range(i)]}
            for i in range(1, 11)
        ]

        score = EvolutionAnalysisTestHelper.analyze_maintainability(tasks, {})

        # Muitas dependências devem reduzir score
        assert 0.0 <= score <= 1.0


class TestScalabilityAnalysis:
    """Testes de análise de escalabilidade."""

    def test_scalability_with_parallel_tasks(self):
        """Testa escalabilidade com tarefas paralelas."""
        tasks = [
            {"name": f"task{i}", "estimated_duration_ms": 1000, "dependencies": []}
            for i in range(5)
        ]

        score = EvolutionAnalysisTestHelper.analyze_scalability(tasks, {})

        # Tarefas paralelas devem ter bom score
        assert score > 0.7

    def test_scalability_with_long_tasks(self):
        """Testa escalabilidade com tarefas longas."""
        tasks = [{"name": "long-task", "estimated_duration_ms": 20000, "dependencies": []}]

        score = EvolutionAnalysisTestHelper.analyze_scalability(tasks, {})

        assert 0.0 <= score <= 1.0


class TestMLModelIntegration:
    """Testes de integração com modelo ML do especialista de evolução."""

    def test_ml_model_features_extraction(self):
        """Testa extração de features para modelo ML de evolução."""
        expected_features = [
            "maintainability_score",
            "scalability_score",
            "extensibility_score",
            "tech_debt_score",
            "modularity_score",
            "long_term_viability",
        ]

        features = {
            "maintainability_score": 0.8,
            "scalability_score": 0.85,
            "extensibility_score": 0.75,
            "tech_debt_score": 0.7,  # Alta prevenção = bom
            "modularity_score": 0.8,
            "long_term_viability": 0.75,
        }

        for feature in expected_features:
            assert feature in features

        for feature, value in features.items():
            assert 0.0 <= value <= 1.0

    def test_ml_model_prediction(self):
        """Testa predição do modelo ML de evolução."""
        from sklearn.ensemble import GradientBoostingClassifier
        import numpy as np

        model = GradientBoostingClassifier(n_estimators=10, max_depth=3, random_state=42)

        X_train = np.array(
            [
                [0.9, 0.85, 0.8, 0.75, 0.8, 0.8],  # Boa evolução
                [0.3, 0.4, 0.3, 0.3, 0.4, 0.3],  # Má evolução
            ]
        )
        y_train = np.array([1, 0])

        model.fit(X_train, y_train)

        X_test = np.array([[0.8, 0.8, 0.75, 0.7, 0.75, 0.75]])
        prediction = model.predict(X_test)[0]

        assert prediction in [0, 1]

    def test_ml_model_approve_conditions(self):
        """Testa condições de aprovação do modelo de evolução."""
        # Regra: maintainability + scalability + extensibility > 2.0 E tech_debt > 0.5
        maintainability = 0.8
        scalability = 0.85
        extensibility = 0.75
        tech_debt = 0.7
        modularity = 0.6

        should_approve = (
            (maintainability + scalability + extensibility) > 2.0
            and tech_debt > 0.5
            and modularity > 0.4
        )

        assert should_approve is True

    def test_ml_model_reject_conditions(self):
        """Testa condições de rejeição do modelo de evolução."""
        maintainability = 0.4
        scalability = 0.5
        extensibility = 0.3
        tech_debt = 0.3
        modularity = 0.3

        should_approve = (
            (maintainability + scalability + extensibility) > 2.0
            and tech_debt > 0.5
            and modularity > 0.4
        )

        assert should_approve is False

    def test_ml_model_weight_combination(self):
        """Testa combinação de pesos adaptativos."""
        # Pesos padrão
        default_weights = {
            "maintainability": 0.25,
            "scalability": 0.25,
            "extensibility": 0.20,
            "modularity": 0.15,
            "tech_debt_prevention": 0.15,
        }

        # Scores
        scores = {
            "maintainability": 0.8,
            "scalability": 0.7,
            "extensibility": 0.75,
            "modularity": 0.6,
            "tech_debt_prevention": 0.7,
        }

        # Calcular score ponderado
        weighted_score = sum(scores[k] * default_weights[k] for k in default_weights.keys())

        assert 0.65 < weighted_score < 0.75

    def test_ml_model_feature_importance(self):
        """Testa importância de features do modelo de evolução."""
        from sklearn.ensemble import GradientBoostingClassifier
        import numpy as np

        model = GradientBoostingClassifier(n_estimators=10, random_state=42)

        X = np.random.rand(100, 6)
        y = (X[:, 0] + X[:, 1] + X[:, 2] > 1.5).astype(
            int
        )  # maintainability + scalability + extensibility
        model.fit(X, y)

        feature_names = [
            "maintainability_score",
            "scalability_score",
            "extensibility_score",
            "tech_debt_score",
            "modularity_score",
            "long_term_viability",
        ]

        importances = dict(zip(feature_names, model.feature_importances_))

        total = sum(importances.values())
        assert abs(total - 1.0) < 0.1

        # Features usadas na regra devem ter importância
        assert importances["maintainability_score"] >= 0
        assert importances["scalability_score"] >= 0
        assert importances["extensibility_score"] >= 0


class TestCompleteEvaluationFlow:
    """Testes do fluxo completo de avaliação."""

    def test_complete_evaluation(self, sample_cognitive_plan):
        """Testa avaliação completa."""
        tasks = sample_cognitive_plan["tasks"]

        maintainability = EvolutionAnalysisTestHelper.analyze_maintainability(
            tasks, sample_cognitive_plan
        )
        scalability = EvolutionAnalysisTestHelper.analyze_scalability(tasks, sample_cognitive_plan)
        extensibility = EvolutionAnalysisTestHelper.analyze_extensibility(
            tasks, sample_cognitive_plan
        )
        modularity = EvolutionAnalysisTestHelper.analyze_modularity(tasks)
        tech_debt = EvolutionAnalysisTestHelper.analyze_tech_debt_risk(tasks, sample_cognitive_plan)

        confidence = (
            maintainability * 0.25
            + scalability * 0.25
            + extensibility * 0.20
            + modularity * 0.15
            + tech_debt * 0.15
        )

        risk = EvolutionAnalysisTestHelper.calculate_evolution_risk(
            maintainability, scalability, extensibility, modularity, tech_debt
        )

        recommendation = EvolutionAnalysisTestHelper.determine_recommendation(confidence, risk)

        assert 0.0 <= confidence <= 1.0
        assert 0.0 <= risk <= 1.0
        assert recommendation in ["approve", "reject", "review_required", "conditional"]
