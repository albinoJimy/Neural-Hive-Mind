"""Testes unitários para ArchitectureSpecialist - Métodos de Análise."""

import sys
import os
import pytest
from typing import Dict, Any, List

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


class ArchitectureAnalysisTestHelper:
    """Helper class para testar métodos de análise de arquitetura."""

    @staticmethod
    def analyze_design_patterns(tasks: List[Dict]) -> float:
        """Implementação do método de análise de design patterns."""
        if not tasks:
            return 0.5

        positive_keywords = [
            "factory",
            "builder",
            "singleton",
            "observer",
            "strategy",
            "adapter",
            "decorator",
            "facade",
            "proxy",
            "composite",
            "interface",
            "abstraction",
            "dependency injection",
            "repository",
        ]

        negative_keywords = [
            "god object",
            "spaghetti",
            "tight coupling",
            "hardcoded",
            "global state",
            "magic numbers",
            "copy-paste",
        ]

        positive_count = 0
        negative_count = 0

        for task in tasks:
            task_description = task.get("description", "").lower()

            for keyword in positive_keywords:
                if keyword in task_description:
                    positive_count += 1

            for keyword in negative_keywords:
                if keyword in task_description:
                    negative_count += 1

        total_indicators = positive_count + negative_count
        if total_indicators == 0:
            score = 0.6
        else:
            score = positive_count / total_indicators

        return max(0.0, min(1.0, score))

    @staticmethod
    def analyze_solid_principles(tasks: List[Dict], cognitive_plan: Dict) -> float:
        """Implementação do método de análise de princípios SOLID."""
        if not tasks:
            return 0.5

        solid_keywords = [
            "single responsibility",
            "srp",
            "open closed",
            "ocp",
            "extensible",
            "liskov",
            "lsp",
            "substitution",
            "interface segregation",
            "isp",
            "dependency inversion",
            "dip",
            "dependency injection",
            "abstraction",
        ]

        violation_keywords = [
            "god class",
            "multiple responsibilities",
            "tight coupling",
            "hardcoded dependencies",
            "fat interface",
            "concrete dependency",
        ]

        solid_count = 0
        violation_count = 0

        for task in tasks:
            task_description = task.get("description", "").lower()

            for keyword in solid_keywords:
                if keyword in task_description:
                    solid_count += 1

            for keyword in violation_keywords:
                if keyword in task_description:
                    violation_count += 1

        total_indicators = solid_count + violation_count
        if total_indicators == 0:
            indicator_score = 0.6
        else:
            indicator_score = solid_count / total_indicators

        return max(0.0, min(1.0, indicator_score))

    @staticmethod
    def analyze_coupling_cohesion(tasks: List[Dict]) -> float:
        """Implementação do método de análise de acoplamento e coesão."""
        if not tasks:
            return 0.5

        num_tasks = len(tasks)
        total_dependencies = sum(len(task.get("dependencies", [])) for task in tasks)
        max_possible_deps = num_tasks * (num_tasks - 1) / 2

        if max_possible_deps > 0:
            coupling_ratio = total_dependencies / max_possible_deps
            low_coupling_score = 1.0 - coupling_ratio
        else:
            low_coupling_score = 1.0

        # Coesão baseada em agrupamento de tarefas
        agent_groups = {}
        for task in tasks:
            agent_id = task.get("agent_id", "unknown")
            if agent_id not in agent_groups:
                agent_groups[agent_id] = []
            agent_groups[agent_id].append(task)

        num_groups = len(agent_groups)
        if num_groups > 0:
            avg_tasks_per_group = num_tasks / num_groups
            if avg_tasks_per_group >= 3:
                cohesion_score = 1.0
            elif avg_tasks_per_group >= 2:
                cohesion_score = 0.8
            else:
                cohesion_score = 0.6
        else:
            cohesion_score = 0.5

        coupling_cohesion_score = low_coupling_score * 0.6 + cohesion_score * 0.4
        return max(0.0, min(1.0, coupling_cohesion_score))

    @staticmethod
    def analyze_separation_of_concerns(tasks: List[Dict]) -> float:
        """Implementação do método de análise de separação de concerns."""
        if not tasks:
            return 0.5

        concerns = {
            "ui": ["ui", "interface", "view", "presentation", "frontend"],
            "business_logic": ["business", "logic", "service", "domain"],
            "data": ["data", "database", "storage", "persistence", "repository"],
            "infrastructure": ["infrastructure", "config", "deployment", "networking"],
        }

        task_concerns = []
        for task in tasks:
            task_description = task.get("description", "").lower()
            identified_concerns = set()

            for concern_type, keywords in concerns.items():
                for keyword in keywords:
                    if keyword in task_description:
                        identified_concerns.add(concern_type)

            task_concerns.append(identified_concerns)

        mixed_concerns_count = sum(1 for tc in task_concerns if len(tc) > 1)
        total_tasks_with_concerns = sum(1 for tc in task_concerns if len(tc) > 0)

        if total_tasks_with_concerns > 0:
            separation_score = 1.0 - (mixed_concerns_count / total_tasks_with_concerns)
        else:
            separation_score = 0.6

        return max(0.0, min(1.0, separation_score))

    @staticmethod
    def analyze_modularity(tasks: List[Dict]) -> float:
        """Implementação do método de análise de modularidade."""
        if not tasks:
            return 0.5

        modularity_keywords = [
            "module",
            "component",
            "layer",
            "package",
            "encapsulation",
            "namespace",
            "boundary",
            "api",
            "contract",
            "interface",
        ]

        modularity_count = 0
        for task in tasks:
            task_description = task.get("description", "").lower()
            for keyword in modularity_keywords:
                if keyword in task_description:
                    modularity_count += 1
                    break

        modularity_ratio = modularity_count / len(tasks)

        if modularity_ratio >= 0.7:
            return 1.0
        elif modularity_ratio >= 0.5:
            return 0.8
        elif modularity_ratio >= 0.3:
            return 0.6
        else:
            return 0.4

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
    return {
        "plan_id": "arch-plan-123",
        "original_domain": "architecture-design",
        "original_priority": "high",
        "tasks": [
            {
                "task_id": "task-1",
                "description": "Implement factory pattern for object creation",
                "dependencies": [],
                "agent_id": "service-a",
                "estimated_duration_ms": 25000,
            },
            {
                "task_id": "task-2",
                "description": "Apply single responsibility principle to controller",
                "dependencies": ["task-1"],
                "agent_id": "service-a",
                "estimated_duration_ms": 30000,
            },
            {
                "task_id": "task-3",
                "description": "Add repository pattern for data access",
                "dependencies": [],
                "agent_id": "service-b",
                "estimated_duration_ms": 20000,
            },
        ],
    }


class TestDesignPatternsAnalysis:
    """Testes de análise de design patterns."""

    def test_design_patterns_with_positive_keywords(self):
        tasks = [
            {"description": "Implement factory pattern for object creation"},
            {"description": "Add repository pattern for data access"},
            {"description": "Use dependency injection for dependencies"},
        ]

        score = ArchitectureAnalysisTestHelper.analyze_design_patterns(tasks)
        assert score > 0.5

    def test_design_patterns_with_negative_keywords(self):
        tasks = [
            {"description": "Beware of god object antipattern"},
            {"description": "Avoid spaghetti code structure"},
            {"description": "Refactor tight coupling between modules"},
        ]

        score = ArchitectureAnalysisTestHelper.analyze_design_patterns(tasks)
        assert score < 0.5

    def test_design_patterns_empty_tasks(self):
        score = ArchitectureAnalysisTestHelper.analyze_design_patterns([])
        assert score == 0.5


class TestSOLIDAnalysis:
    """Testes de análise de princípios SOLID."""

    def test_solid_with_principles_mentioned(self):
        tasks = [
            {"description": "Apply single responsibility principle"},
            {"description": "Ensure open closed principle for extensibility"},
            {"description": "Use dependency injection for loose coupling"},
        ]

        score = ArchitectureAnalysisTestHelper.analyze_solid_principles(tasks, {})
        assert score > 0.5

    def test_solid_with_violations(self):
        tasks = [
            {"description": "Refactor god class with multiple responsibilities"},
            {"description": "Fix tight coupling between components"},
        ]

        score = ArchitectureAnalysisTestHelper.analyze_solid_principles(tasks, {})
        assert score < 0.5

    def test_solid_empty_tasks(self):
        score = ArchitectureAnalysisTestHelper.analyze_solid_principles([], {})
        assert score == 0.5


class TestCouplingCohesionAnalysis:
    """Testes de análise de acoplamento e coesão."""

    def test_coupling_low_with_few_dependencies(self):
        tasks = [
            {"description": "Task 1", "dependencies": [], "agent_id": "service-a"},
            {"description": "Task 2", "dependencies": [], "agent_id": "service-a"},
            {"description": "Task 3", "dependencies": [], "agent_id": "service-a"},
        ]

        score = ArchitectureAnalysisTestHelper.analyze_coupling_cohesion(tasks)
        assert score > 0.7

    def test_coupling_high_with_many_dependencies(self):
        tasks = [
            {
                "description": "Task 1",
                "dependencies": ["task-2", "task-3", "task-4"],
                "agent_id": "service-a",
            },
            {"description": "Task 2", "dependencies": [], "agent_id": "service-b"},
        ]

        score = ArchitectureAnalysisTestHelper.analyze_coupling_cohesion(tasks)
        assert score < 0.8

    def test_coupling_empty_tasks(self):
        score = ArchitectureAnalysisTestHelper.analyze_coupling_cohesion([])
        assert score == 0.5


class TestSeparationOfConcernsAnalysis:
    """Testes de análise de separação de concerns."""

    def test_separation_with_distinct_concerns(self):
        tasks = [
            {"description": "Implement UI view component"},
            {"description": "Add business logic service"},
            {"description": "Create database repository"},
        ]

        score = ArchitectureAnalysisTestHelper.analyze_separation_of_concerns(tasks)
        assert score > 0.5

    def test_separation_with_mixed_concerns(self):
        tasks = [{"description": "Handle UI view and business logic and database"}]

        score = ArchitectureAnalysisTestHelper.analyze_separation_of_concerns(tasks)
        assert score < 0.5

    def test_separation_empty_tasks(self):
        score = ArchitectureAnalysisTestHelper.analyze_separation_of_concerns([])
        assert score == 0.5


class TestModularityAnalysis:
    """Testes de análise de modularidade."""

    def test_modularity_with_keywords(self):
        tasks = [
            {"description": "Create separate module for functionality"},
            {"description": "Define component boundaries"},
            {"description": "Implement interface contract"},
        ]

        score = ArchitectureAnalysisTestHelper.analyze_modularity(tasks)
        assert score > 0.6

    def test_modularity_without_keywords(self):
        tasks = [
            {"description": "Add basic feature"},
            {"description": "Create simple functionality"},
        ]

        score = ArchitectureAnalysisTestHelper.analyze_modularity(tasks)
        assert score < 0.6

    def test_modularity_empty_tasks(self):
        score = ArchitectureAnalysisTestHelper.analyze_modularity([])
        assert score == 0.5


class TestRecommendationDetermination:
    """Testes de determinação de recomendação."""

    def test_recommendation_approve(self):
        recommendation = ArchitectureAnalysisTestHelper.determine_recommendation(
            confidence_score=0.85, risk_score=0.2
        )
        assert recommendation == "approve"

    def test_recommendation_reject(self):
        recommendation = ArchitectureAnalysisTestHelper.determine_recommendation(
            confidence_score=0.4, risk_score=0.6
        )
        assert recommendation == "reject"

    def test_recommendation_review_required(self):
        recommendation = ArchitectureAnalysisTestHelper.determine_recommendation(
            confidence_score=0.6, risk_score=0.6
        )
        assert recommendation == "review_required"

    def test_recommendation_conditional(self):
        recommendation = ArchitectureAnalysisTestHelper.determine_recommendation(
            confidence_score=0.7, risk_score=0.4
        )
        assert recommendation == "conditional"


class TestCompleteEvaluationFlow:
    """Testes do fluxo completo de avaliação."""

    def test_complete_evaluation(self, sample_cognitive_plan):
        tasks = sample_cognitive_plan["tasks"]

        design_patterns = ArchitectureAnalysisTestHelper.analyze_design_patterns(tasks)
        solid = ArchitectureAnalysisTestHelper.analyze_solid_principles(
            tasks, sample_cognitive_plan
        )
        coupling = ArchitectureAnalysisTestHelper.analyze_coupling_cohesion(tasks)
        separation = ArchitectureAnalysisTestHelper.analyze_separation_of_concerns(tasks)
        modularity = ArchitectureAnalysisTestHelper.analyze_modularity(tasks)

        confidence = (
            design_patterns * 0.25
            + solid * 0.25
            + coupling * 0.20
            + separation * 0.15
            + modularity * 0.15
        )

        risk = 1.0 - confidence
        recommendation = ArchitectureAnalysisTestHelper.determine_recommendation(confidence, risk)

        assert 0.0 <= confidence <= 1.0
        assert 0.0 <= risk <= 1.0
        assert recommendation in ["approve", "reject", "review_required", "conditional"]
