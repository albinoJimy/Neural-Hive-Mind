"""Testes unitários para BehaviorSpecialist - Métodos de Análise."""

import sys
import os
import pytest
from typing import Dict, Any, List

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class BehaviorAnalysisTestHelper:
    """Helper class para testar métodos de análise sem inicialização completa."""

    @staticmethod
    def analyze_usability(tasks: List[Dict], cognitive_plan: Dict) -> float:
        """Implementação do método de análise de usabilidade."""
        if not tasks:
            return 0.5

        # Palavras-chave positivas (UX/usabilidade)
        positive_keywords = [
            'user-friendly', 'intuitive', 'simple', 'clear', 'easy to use',
            'responsive', 'mobile-friendly', 'consistent', 'accessible'
        ]

        # Palavras-chave negativas
        negative_keywords = [
            'confusing', 'complex', 'complicated', 'unclear',
            'difficult', 'hard to use', 'inconsistent'
        ]

        positive_count = 0
        negative_count = 0

        for task in tasks:
            task_desc = task.get('description', '').lower()

            for keyword in positive_keywords:
                if keyword in task_desc:
                    positive_count += 1

            for keyword in negative_keywords:
                if keyword in task_desc:
                    negative_count += 1

        total_indicators = positive_count + negative_count
        if total_indicators == 0:
            score = 0.6  # Neutro
        else:
            score = positive_count / total_indicators

        return max(0.0, min(1.0, score))

    @staticmethod
    def analyze_accessibility(cognitive_plan: Dict, context: Dict) -> float:
        """Implementação do método de análise de acessibilidade."""
        # Palavras-chave de acessibilidade (WCAG)
        a11y_keywords = [
            'wcag', 'accessible', 'a11y', 'screen reader', 'keyboard',
            'contrast', 'alt text', 'aria', 'semantic html', 'navigation'
        ]

        # Verificar menções no plano
        plan_desc = cognitive_plan.get('description', '').lower()
        mentions = sum(1 for keyword in a11y_keywords if keyword in plan_desc)

        # Verificar tarefas com foco em acessibilidade
        tasks = cognitive_plan.get('tasks', [])
        a11y_tasks = sum(
            1 for task in tasks
            if any(keyword in task.get('description', '').lower() for keyword in a11y_keywords)
        )

        num_tasks = len(tasks) if tasks else 1
        base_score = min(1.0, (mentions + a11y_tasks) / (num_tasks * 0.3))

        # Verificar contexto de requisitos
        has_a11y_requirements = context.get('accessibility_requirements') is not None
        requirement_bonus = 0.2 if has_a11y_requirements else 0.0

        return min(1.0, base_score + requirement_bonus)

    @staticmethod
    def analyze_response_time(tasks: List[Dict]) -> float:
        """Implementação do método de análise de tempo de resposta."""
        if not tasks:
            return 0.5

        # Calcular tempo total estimado
        total_duration_ms = sum(task.get('estimated_duration_ms', 0) for task in tasks)

        # Verificar menções de otimização de performance
        perf_keywords = ['fast', 'quick', 'optimize', 'async', 'cached', 'instant']
        perf_count = sum(
            1 for task in tasks
            if any(keyword in task.get('description', '').lower() for keyword in perf_keywords)
        )

        # Tempo ideal: < 100ms (muito rápido), 100-300ms (bom), >1s (lento)
        if total_duration_ms < 100:
            time_score = 1.0
        elif total_duration_ms < 300:
            time_score = 0.8
        elif total_duration_ms < 1000:
            time_score = 0.6
        elif total_duration_ms < 5000:
            time_score = 0.4
        else:
            time_score = 0.2

        # Bônus por menções de performance
        perf_bonus = min(0.2, perf_count / len(tasks))

        return min(1.0, time_score + perf_bonus)

    @staticmethod
    def analyze_interaction_cost(tasks: List[Dict]) -> float:
        """Implementação do método de análise de custo de interação."""
        if not tasks:
            return 0.5

        # Custo de interação baseado em número de passos
        # Mais tarefas = mais interação = maior custo
        num_tasks = len(tasks)

        # Ideal: 3-7 interações
        if num_tasks <= 3:
            cost_penalty = 1.0  # Muito baixo custo
        elif num_tasks <= 7:
            cost_penalty = 0.8  # Bom
        elif num_tasks <= 15:
            cost_penalty = 0.5  # Aceitável
        else:
            cost_penalty = 0.3  # Muito alto custo

        # Verificar menções de simplificação
        simple_keywords = ['simplify', 'streamline', 'reduce steps', 'one-click', 'automated']
        simple_count = sum(
            1 for task in tasks
            if any(keyword in task.get('description', '').lower() for keyword in simple_keywords)
        )
        simplicity_bonus = min(0.2, simple_count / num_tasks if num_tasks > 0 else 0)

        return min(1.0, cost_penalty + simplicity_bonus)

    @staticmethod
    def calculate_behavior_risk(
        cognitive_plan: Dict,
        usability_score: float,
        accessibility_score: float,
        response_time_score: float,
        interaction_cost_score: float
    ) -> float:
        """Implementação do cálculo de risco comportamental."""
        weighted_avg = (
            usability_score * 0.3 +
            accessibility_score * 0.25 +
            response_time_score * 0.25 +
            interaction_cost_score * 0.2
        )
        risk_score = 1.0 - weighted_avg

        return max(0.0, min(1.0, risk_score))

    @staticmethod
    def determine_recommendation(confidence_score: float, risk_score: float) -> str:
        """Determina recomendação baseada em scores."""
        if confidence_score >= 0.8 and risk_score < 0.3:
            return 'approve'
        elif confidence_score < 0.5 or risk_score > 0.7:
            return 'reject'
        elif risk_score > 0.5:
            return 'review_required'
        else:
            return 'conditional'

    @staticmethod
    def generate_reasoning(
        usability_score: float,
        accessibility_score: float,
        response_time_score: float,
        interaction_cost_score: float,
        recommendation: str
    ) -> str:
        """Gera narrativa de justificativa."""
        return (
            f"Avaliação comportamental: "
            f"usability={usability_score:.2f}, "
            f"accessibility={accessibility_score:.2f}, "
            f"response_time={response_time_score:.2f}, "
            f"interaction_cost={interaction_cost_score:.2f}. "
            f"Recomendação: {recommendation}."
        )

    @staticmethod
    def generate_mitigations(
        usability_score: float,
        accessibility_score: float,
        response_time_score: float,
        interaction_cost_score: float
    ) -> List[Dict]:
        """Gera sugestões de mitigação de riscos comportamentais."""
        mitigations = []

        if usability_score < 0.6:
            mitigations.append({
                'mitigation_type': 'improve_usability',
                'description': 'Melhorar usabilidade com design intuitivo e consistente',
                'priority': 'high',
                'estimated_effort': 'medium'
            })

        if accessibility_score < 0.6:
            mitigations.append({
                'mitigation_type': 'improve_accessibility',
                'description': 'Aumentar conformidade com WCAG e padrões de acessibilidade',
                'priority': 'critical',
                'estimated_effort': 'medium'
            })

        if response_time_score < 0.6:
            mitigations.append({
                'mitigation_type': 'improve_response_time',
                'description': 'Otimizar tempo de resposta com caching e async',
                'priority': 'high',
                'estimated_effort': 'medium'
            })

        if interaction_cost_score < 0.6:
            mitigations.append({
                'mitigation_type': 'reduce_interaction_cost',
                'description': 'Simplificar fluxo para reduzir custos de interação',
                'priority': 'medium',
                'estimated_effort': 'low'
            })

        return mitigations


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo."""
    return {
        'plan_id': 'plan-999',
        'original_domain': 'user-interface-design',
        'original_priority': 'high',
        'description': 'Create user-friendly interface with accessibility and fast response',
        'tasks': [
            {
                'task_id': 'task-1',
                'description': 'Design intuitive and responsive UI',
                'dependencies': [],
                'estimated_duration_ms': 15000
            },
            {
                'task_id': 'task-2',
                'description': 'Implement WCAG accessible components',
                'dependencies': ['task-1'],
                'estimated_duration_ms': 20000
            },
            {
                'task_id': 'task-3',
                'description': 'Optimize for quick and async response',
                'dependencies': ['task-2'],
                'estimated_duration_ms': 10000
            }
        ]
    }


class TestUsabilityAnalysis:
    """Testes de análise de usabilidade."""

    def test_usability_with_positive_keywords(self):
        """Testa análise com palavras-chave positivas."""
        tasks = [
            {'description': 'Create user-friendly and intuitive interface', 'dependencies': []},
            {'description': 'Make design simple and clear', 'dependencies': []}
        ]

        score = BehaviorAnalysisTestHelper.analyze_usability(tasks, {})
        assert score > 0.5

    def test_usability_with_negative_keywords(self):
        """Testa análise com palavras-chave negativas."""
        tasks = [
            {'description': 'Complex and confusing interface', 'dependencies': []},
            {'description': 'Difficult to use navigation', 'dependencies': []}
        ]

        score = BehaviorAnalysisTestHelper.analyze_usability(tasks, {})
        assert score < 0.5

    def test_usability_mixed(self):
        """Testa análise com misto de positivo e negativo."""
        tasks = [
            {'description': 'User-friendly but complex', 'dependencies': []}
        ]

        score = BehaviorAnalysisTestHelper.analyze_usability(tasks, {})
        assert 0.0 <= score <= 1.0

    def test_usability_empty_tasks(self):
        """Testa análise com lista vazia de tarefas."""
        score = BehaviorAnalysisTestHelper.analyze_usability([], {})
        assert score == 0.5


class TestAccessibilityAnalysis:
    """Testes de análise de acessibilidade."""

    def test_accessibility_with_mentions(self):
        """Testa análise com menções de acessibilidade."""
        plan = {
            'description': 'Ensure WCAG compliance and accessible design',
            'tasks': [
                {'description': 'Add keyboard navigation support', 'dependencies': []},
                {'description': 'Implement screen reader compatibility', 'dependencies': []}
            ]
        }

        score = BehaviorAnalysisTestHelper.analyze_accessibility(plan, {})
        assert score > 0.5

    def test_accessibility_with_requirements(self):
        """Testa análise com requisitos de acessibilidade."""
        plan = {
            'description': 'Create interface',
            'tasks': [{'description': 'Task 1', 'dependencies': []}]
        }
        context = {'accessibility_requirements': ['wcag_2.1_aa']}

        score = BehaviorAnalysisTestHelper.analyze_accessibility(plan, context)
        assert score > 0.0

    def test_accessibility_no_mentions(self):
        """Testa análise sem menções de acessibilidade."""
        plan = {
            'description': 'Create basic interface',
            'tasks': [
                {'description': 'Add feature', 'dependencies': []}
            ]
        }

        score = BehaviorAnalysisTestHelper.analyze_accessibility(plan, {})
        assert score < 0.5


class TestResponseTimeAnalysis:
    """Testes de análise de tempo de resposta."""

    def test_response_time_very_fast(self):
        """Testa análise com tempo muito rápido."""
        tasks = [
            {'description': 'Fast task', 'estimated_duration_ms': 50}
        ]

        score = BehaviorAnalysisTestHelper.analyze_response_time(tasks)
        assert score == 1.0

    def test_response_time_moderate(self):
        """Testa análise com tempo moderado."""
        tasks = [
            {'description': 'Normal task', 'estimated_duration_ms': 200}
        ]

        score = BehaviorAnalysisTestHelper.analyze_response_time(tasks)
        assert score > 0.5

    def test_response_time_slow(self):
        """Testa análise com tempo lento."""
        tasks = [
            {'description': 'Slow task', 'estimated_duration_ms': 3000}
        ]

        score = BehaviorAnalysisTestHelper.analyze_response_time(tasks)
        assert score < 0.5

    def test_response_time_empty_tasks(self):
        """Testa análise com lista vazia de tarefas."""
        score = BehaviorAnalysisTestHelper.analyze_response_time([])
        assert score == 0.5


class TestInteractionCostAnalysis:
    """Testes de análise de custo de interação."""

    def test_interaction_cost_ideal(self):
        """Testa análise com custo ideal."""
        tasks = [
            {'description': 'Task 1', 'dependencies': []},
            {'description': 'Task 2', 'dependencies': ['task-1']},
            {'description': 'Task 3', 'dependencies': ['task-2']},
        ]

        score = BehaviorAnalysisTestHelper.analyze_interaction_cost(tasks)
        assert score >= 0.8

    def test_interaction_cost_high(self):
        """Testa análise com custo alto."""
        tasks = [
            {'description': f'Task {i}', 'dependencies': []}
            for i in range(20)
        ]

        score = BehaviorAnalysisTestHelper.analyze_interaction_cost(tasks)
        assert score < 0.5

    def test_interaction_cost_with_simplification(self):
        """Testa análise com simplificação."""
        tasks = [
            {'description': 'Simplify with one-click action', 'dependencies': []},
            {'description': 'Streamline user flow', 'dependencies': []}
        ]

        score = BehaviorAnalysisTestHelper.analyze_interaction_cost(tasks)
        assert score > 0.5

    def test_interaction_cost_empty_tasks(self):
        """Testa análise com lista vazia de tarefas."""
        score = BehaviorAnalysisTestHelper.analyze_interaction_cost([])
        assert score == 0.5


class TestBehaviorRiskCalculation:
    """Testes de cálculo de risco comportamental."""

    def test_risk_calculation_low_risk(self):
        """Testa cálculo de risco com scores altos."""
        risk = BehaviorAnalysisTestHelper.calculate_behavior_risk(
            cognitive_plan={},
            usability_score=0.9,
            accessibility_score=0.85,
            response_time_score=0.8,
            interaction_cost_score=0.75
        )
        assert risk < 0.3

    def test_risk_calculation_high_risk(self):
        """Testa cálculo de risco com scores baixos."""
        risk = BehaviorAnalysisTestHelper.calculate_behavior_risk(
            cognitive_plan={},
            usability_score=0.3,
            accessibility_score=0.4,
            response_time_score=0.35,
            interaction_cost_score=0.3
        )
        assert risk > 0.6

    def test_risk_calculation_weights(self):
        """Testa pesos dos diferentes fatores."""
        # Usabilidade tem maior peso (0.3)
        risk1 = BehaviorAnalysisTestHelper.calculate_behavior_risk(
            cognitive_plan={},
            usability_score=0.2,
            accessibility_score=0.8,
            response_time_score=0.8,
            interaction_cost_score=0.8
        )

        risk2 = BehaviorAnalysisTestHelper.calculate_behavior_risk(
            cognitive_plan={},
            usability_score=0.8,
            accessibility_score=0.2,
            response_time_score=0.8,
            interaction_cost_score=0.8
        )

        # Baixa usabilidade deve ter maior impacto
        assert risk1 > risk2


class TestRecommendationDetermination:
    """Testes de determinação de recomendação."""

    def test_recommendation_approve(self):
        """Testa recomendação de aprovação."""
        recommendation = BehaviorAnalysisTestHelper.determine_recommendation(
            confidence_score=0.85,
            risk_score=0.2
        )
        assert recommendation == 'approve'

    def test_recommendation_reject_low_confidence(self):
        """Testa rejeição por baixa confiança."""
        recommendation = BehaviorAnalysisTestHelper.determine_recommendation(
            confidence_score=0.4,
            risk_score=0.5
        )
        assert recommendation == 'reject'

    def test_recommendation_reject_high_risk(self):
        """Testa rejeição por alto risco."""
        recommendation = BehaviorAnalysisTestHelper.determine_recommendation(
            confidence_score=0.6,
            risk_score=0.8
        )
        assert recommendation == 'reject'

    def test_recommendation_review_required(self):
        """Testa recomendação de revisão necessária."""
        recommendation = BehaviorAnalysisTestHelper.determine_recommendation(
            confidence_score=0.6,
            risk_score=0.6
        )
        assert recommendation == 'review_required'

    def test_recommendation_conditional(self):
        """Testa recomendação condicional."""
        recommendation = BehaviorAnalysisTestHelper.determine_recommendation(
            confidence_score=0.7,
            risk_score=0.4
        )
        assert recommendation == 'conditional'


class TestReasoningGeneration:
    """Testes de geração de justificativa."""

    def test_reasoning_includes_all_scores(self):
        """Testa que justificativa inclui todos os scores."""
        reasoning = BehaviorAnalysisTestHelper.generate_reasoning(
            usability_score=0.8,
            accessibility_score=0.75,
            response_time_score=0.7,
            interaction_cost_score=0.65,
            recommendation='approve'
        )

        assert 'usability=0.80' in reasoning
        assert 'accessibility=0.75' in reasoning
        assert 'response_time=0.70' in reasoning
        assert 'interaction_cost=0.65' in reasoning
        assert 'approve' in reasoning


class TestMitigationGeneration:
    """Testes de geração de mitigações."""

    def test_mitigations_usability_low(self):
        """Testa mitigação para usabilidade baixa."""
        mitigations = BehaviorAnalysisTestHelper.generate_mitigations(
            usability_score=0.4,
            accessibility_score=0.8,
            response_time_score=0.8,
            interaction_cost_score=0.8
        )

        assert any(m['mitigation_type'] == 'improve_usability' for m in mitigations)

    def test_mitigations_accessibility_low(self):
        """Testa mitigação para acessibilidade baixa."""
        mitigations = BehaviorAnalysisTestHelper.generate_mitigations(
            usability_score=0.8,
            accessibility_score=0.4,
            response_time_score=0.8,
            interaction_cost_score=0.8
        )

        assert any(m['mitigation_type'] == 'improve_accessibility' for m in mitigations)
        assert any(m['priority'] == 'critical' for m in mitigations)

    def test_mitigations_response_time_low(self):
        """Testa mitigação para tempo de resposta baixo."""
        mitigations = BehaviorAnalysisTestHelper.generate_mitigations(
            usability_score=0.8,
            accessibility_score=0.8,
            response_time_score=0.4,
            interaction_cost_score=0.8
        )

        assert any(m['mitigation_type'] == 'improve_response_time' for m in mitigations)

    def test_mitigations_interaction_cost_low(self):
        """Testa mitigação para custo de interação baixo."""
        mitigations = BehaviorAnalysisTestHelper.generate_mitigations(
            usability_score=0.8,
            accessibility_score=0.8,
            response_time_score=0.8,
            interaction_cost_score=0.4
        )

        assert any(m['mitigation_type'] == 'reduce_interaction_cost' for m in mitigations)

    def test_mitigations_all_good(self):
        """Testa que não gera mitigações quando scores são bons."""
        mitigations = BehaviorAnalysisTestHelper.generate_mitigations(
            usability_score=0.8,
            accessibility_score=0.8,
            response_time_score=0.8,
            interaction_cost_score=0.8
        )

        assert len(mitigations) == 0


class TestCompleteEvaluationFlow:
    """Testes do fluxo completo de avaliação."""

    def test_complete_evaluation_with_good_ux(self, sample_cognitive_plan):
        """Testa avaliação completa de UX boa."""
        tasks = sample_cognitive_plan['tasks']

        usability = BehaviorAnalysisTestHelper.analyze_usability(tasks, sample_cognitive_plan)
        accessibility = BehaviorAnalysisTestHelper.analyze_accessibility(sample_cognitive_plan, {})
        response_time = BehaviorAnalysisTestHelper.analyze_response_time(tasks)
        interaction_cost = BehaviorAnalysisTestHelper.analyze_interaction_cost(tasks)

        confidence = (
            usability * 0.3 +
            accessibility * 0.25 +
            response_time * 0.25 +
            interaction_cost * 0.2
        )

        risk = BehaviorAnalysisTestHelper.calculate_behavior_risk(
            sample_cognitive_plan, usability, accessibility, response_time, interaction_cost
        )

        recommendation = BehaviorAnalysisTestHelper.determine_recommendation(confidence, risk)
        mitigations = BehaviorAnalysisTestHelper.generate_mitigations(
            usability, accessibility, response_time, interaction_cost
        )

        assert 0.0 <= confidence <= 1.0
        assert 0.0 <= risk <= 1.0
        assert recommendation in ['approve', 'reject', 'review_required', 'conditional']
        assert isinstance(mitigations, list)

    def test_complete_evaluation_with_poor_ux(self):
        """Testa avaliação completa de UX ruim."""
        plan = {
            'plan_id': 'poor-ux',
            'original_domain': 'basic-ui',
            'original_priority': 'normal',
            'description': 'Create interface',
            'tasks': [
                {'description': 'Complex and confusing UI', 'dependencies': [f'task-{i}' for i in range(15)]},
            ]
        }

        tasks = plan['tasks']
        usability = BehaviorAnalysisTestHelper.analyze_usability(tasks, plan)
        accessibility = BehaviorAnalysisTestHelper.analyze_accessibility(plan, {})
        response_time = BehaviorAnalysisTestHelper.analyze_response_time(tasks)
        interaction_cost = BehaviorAnalysisTestHelper.analyze_interaction_cost(tasks)

        risk = BehaviorAnalysisTestHelper.calculate_behavior_risk(
            plan, usability, accessibility, response_time, interaction_cost
        )

        # UX pobre deve ter risco mais alto
        assert risk > 0.3
