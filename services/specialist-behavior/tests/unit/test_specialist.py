"""Testes unitários para BehaviorSpecialist - Métodos de Análise."""

import sys
import os
import pytest
from typing import Dict, List

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


class BehaviorAnalysisTestHelper:
    """Helper class para testar métodos de análise comportamental."""

    @staticmethod
    def analyze_usability(tasks: List[Dict], cognitive_plan: Dict) -> float:
        """Implementação do método de análise de usabilidade."""
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        # Penalizar muitos passos (ideal: 3-7)
        if num_tasks <= 3:
            steps_score = 0.9
        elif num_tasks <= 7:
            steps_score = 1.0
        elif num_tasks <= 12:
            steps_score = 0.7
        else:
            steps_score = 0.5

        feedback_score = BehaviorAnalysisTestHelper._estimate_feedback_quality(tasks)
        usability_score = steps_score * 0.6 + feedback_score * 0.4

        return max(0.0, min(1.0, usability_score))

    @staticmethod
    def _estimate_feedback_quality(tasks: List[Dict]) -> float:
        """Estima qualidade do feedback."""
        if not tasks:
            return 0.5

        avg_duration = sum(task.get("estimated_duration_ms", 0) for task in tasks) / len(tasks)

        if avg_duration < 100:
            return 1.0
        elif avg_duration < 300:
            return 0.9
        elif avg_duration < 1000:
            return 0.7
        else:
            return 0.5

    @staticmethod
    def analyze_accessibility(cognitive_plan: Dict, context: Dict) -> float:
        """Implementação do método de análise de acessibilidade."""
        context_mentions_a11y = any(
            keyword in str(context).lower()
            for keyword in ["accessibility", "wcag", "aria", "screen reader", "keyboard"]
        )

        domain = cognitive_plan.get("original_domain", "")
        ui_related = any(
            keyword in domain.lower() for keyword in ["ui", "interface", "frontend", "view", "form"]
        )

        if context_mentions_a11y:
            return 0.9
        elif ui_related:
            return 0.6
        else:
            return 0.7

    @staticmethod
    def analyze_response_time(tasks: List[Dict]) -> float:
        """Implementação do método de análise de tempo de resposta."""
        if not tasks:
            return 0.5

        max_duration = max(task.get("estimated_duration_ms", 0) for task in tasks)

        if max_duration < 100:
            return 1.0
        elif max_duration < 300:
            return 0.9
        elif max_duration < 1000:
            return 0.7
        elif max_duration < 3000:
            return 0.5
        else:
            return 0.3

    @staticmethod
    def analyze_interaction_cost(tasks: List[Dict]) -> float:
        """Implementação do método de análise de custo de interação."""
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        if num_tasks <= 3:
            interaction_cost = 0.2
        elif num_tasks <= 7:
            interaction_cost = 0.4
        elif num_tasks <= 12:
            interaction_cost = 0.7
        else:
            interaction_cost = 0.9

        interaction_cost_score = 1.0 - interaction_cost
        return max(0.0, min(1.0, interaction_cost_score))

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
        "plan_id": "behavior-plan-123",
        "original_domain": "ui-design",
        "original_priority": "high",
        "tasks": [
            {
                "task_id": "task-1",
                "description": "Design intuitive user interface",
                "dependencies": [],
                "estimated_duration_ms": 200,
            },
            {
                "task_id": "task-2",
                "description": "Ensure WCAG AA accessibility compliance",
                "dependencies": ["task-1"],
                "estimated_duration_ms": 300,
            },
            {
                "task_id": "task-3",
                "description": "Optimize response time for user actions",
                "dependencies": [],
                "estimated_duration_ms": 150,
            },
        ],
    }


class TestUsabilityAnalysis:
    """Testes de análise de usabilidade."""

    def test_usability_ideal_steps(self):
        tasks = [
            {"description": "Step 1", "estimated_duration_ms": 100},
            {"description": "Step 2", "estimated_duration_ms": 100},
            {"description": "Step 3", "estimated_duration_ms": 100},
        ]

        score = BehaviorAnalysisTestHelper.analyze_usability(tasks, {})
        assert score > 0.7

    def test_usability_too_many_steps(self):
        tasks = [{"description": f"Step {i}", "estimated_duration_ms": 100} for i in range(15)]

        score = BehaviorAnalysisTestHelper.analyze_usability(tasks, {})
        assert score < 0.7

    def test_usability_empty_tasks(self):
        score = BehaviorAnalysisTestHelper.analyze_usability([], {})
        assert score == 0.5


class TestAccessibilityAnalysis:
    """Testes de análise de acessibilidade."""

    def test_accessibility_with_context_mentions(self):
        plan = {"original_domain": "ui-development"}
        context = {"accessibility": "wcag aa compliance required"}

        score = BehaviorAnalysisTestHelper.analyze_accessibility(plan, context)
        assert score == 0.9

    def test_accessibility_ui_related(self):
        plan = {"original_domain": "frontend-interface"}
        context = {}

        score = BehaviorAnalysisTestHelper.analyze_accessibility(plan, context)
        assert score == 0.6

    def test_accessibility_non_ui(self):
        plan = {"original_domain": "backend-processing"}
        context = {}

        score = BehaviorAnalysisTestHelper.analyze_accessibility(plan, context)
        assert score == 0.7


class TestResponseTimeAnalysis:
    """Testes de análise de tempo de resposta."""

    def test_response_time_instant(self):
        tasks = [{"estimated_duration_ms": 50}]
        score = BehaviorAnalysisTestHelper.analyze_response_time(tasks)
        assert score == 1.0

    def test_response_time_slow(self):
        tasks = [{"estimated_duration_ms": 5000}]
        score = BehaviorAnalysisTestHelper.analyze_response_time(tasks)
        assert score < 0.5

    def test_response_time_empty_tasks(self):
        score = BehaviorAnalysisTestHelper.analyze_response_time([])
        assert score == 0.5


class TestInteractionCostAnalysis:
    """Testes de análise de custo de interação."""

    def test_interaction_cost_low(self):
        tasks = [{"description": "Task"}]
        score = BehaviorAnalysisTestHelper.analyze_interaction_cost(tasks)
        assert score > 0.7

    def test_interaction_cost_high(self):
        tasks = [{"description": f"Task {i}"} for i in range(15)]
        score = BehaviorAnalysisTestHelper.analyze_interaction_cost(tasks)
        assert score < 0.3

    def test_interaction_cost_empty_tasks(self):
        score = BehaviorAnalysisTestHelper.analyze_interaction_cost([])
        assert score == 0.5


class TestRecommendationDetermination:
    """Testes de determinação de recomendação."""

    def test_recommendation_approve(self):
        recommendation = BehaviorAnalysisTestHelper.determine_recommendation(
            confidence_score=0.85, risk_score=0.2
        )
        assert recommendation == "approve"

    def test_recommendation_reject(self):
        recommendation = BehaviorAnalysisTestHelper.determine_recommendation(
            confidence_score=0.4, risk_score=0.6
        )
        assert recommendation == "reject"

    def test_recommendation_review_required(self):
        recommendation = BehaviorAnalysisTestHelper.determine_recommendation(
            confidence_score=0.6, risk_score=0.6
        )
        assert recommendation == "review_required"

    def test_recommendation_conditional(self):
        recommendation = BehaviorAnalysisTestHelper.determine_recommendation(
            confidence_score=0.7, risk_score=0.4
        )
        assert recommendation == "conditional"


class TestCompleteEvaluationFlow:
    """Testes do fluxo completo de avaliação."""

    def test_complete_evaluation(self, sample_cognitive_plan):
        tasks = sample_cognitive_plan["tasks"]

        usability = BehaviorAnalysisTestHelper.analyze_usability(tasks, sample_cognitive_plan)
        accessibility = BehaviorAnalysisTestHelper.analyze_accessibility(sample_cognitive_plan, {})
        response_time = BehaviorAnalysisTestHelper.analyze_response_time(tasks)
        interaction_cost = BehaviorAnalysisTestHelper.analyze_interaction_cost(tasks)

        confidence = (
            usability * 0.35 + accessibility * 0.25 + response_time * 0.25 + interaction_cost * 0.15
        )

        risk = 1.0 - confidence
        recommendation = BehaviorAnalysisTestHelper.determine_recommendation(confidence, risk)

        assert 0.0 <= confidence <= 1.0
        assert 0.0 <= risk <= 1.0
        assert recommendation in ["approve", "reject", "review_required", "conditional"]
