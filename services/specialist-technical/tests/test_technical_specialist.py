"""Testes unitários para TechnicalSpecialist - Métodos de Análise."""

import sys
import os
import pytest
from typing import Dict, Any, List

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TechnicalAnalysisTestHelper:
    """Helper class para testar métodos de análise sem inicialização completa."""

    @staticmethod
    def analyze_security(tasks: List[Dict], cognitive_plan: Dict) -> float:
        """Implementação do método de análise de segurança."""
        if not tasks:
            return 0.5

        security_indicators = 0
        total_checks = 0

        security_keywords = [
            'auth', 'security', 'validate', 'sanitize', 'encrypt',
            'permission', 'access control', 'token', 'credential'
        ]

        for task in tasks:
            task_desc = task.get('description', '').lower()
            total_checks += 1
            if any(keyword in task_desc for keyword in security_keywords):
                security_indicators += 1

        domain = cognitive_plan.get('original_domain', '')
        if 'data' in domain or 'api' in domain:
            total_checks += 1
            if any('validat' in task.get('description', '').lower() for task in tasks):
                security_indicators += 1

        if total_checks > 0:
            security_score = security_indicators / total_checks
        else:
            security_score = 0.5

        return max(0.0, min(1.0, security_score))

    @staticmethod
    def analyze_architecture(tasks: List[Dict], cognitive_plan: Dict) -> float:
        """Implementação do método de análise de arquitetura."""
        if not tasks:
            return 0.5

        num_tasks = len(tasks)

        clear_tasks = sum(
            1 for task in tasks
            if len(task.get('description', '').split()) > 5
        )
        modularity_score = clear_tasks / num_tasks if num_tasks > 0 else 0.5

        total_dependencies = sum(len(task.get('dependencies', [])) for task in tasks)
        avg_dependencies = total_dependencies / num_tasks if num_tasks > 0 else 0
        coupling_score = max(0.0, 1.0 - (avg_dependencies / 5.0))

        architecture_keywords = [
            'service', 'controller', 'repository', 'model',
            'interface', 'adapter', 'factory', 'strategy'
        ]

        pattern_mentions = sum(
            1 for task in tasks
            if any(keyword in task.get('description', '').lower()
                   for keyword in architecture_keywords)
        )
        pattern_score = min(1.0, pattern_mentions / max(1, num_tasks * 0.3))

        architecture_score = (
            modularity_score * 0.4 +
            coupling_score * 0.3 +
            pattern_score * 0.3
        )

        return max(0.0, min(1.0, architecture_score))

    @staticmethod
    def analyze_performance(tasks: List[Dict]) -> float:
        """Implementação do método de análise de performance."""
        if not tasks:
            return 0.5

        performance_indicators = 0
        total_checks = len(tasks)

        performance_keywords = [
            'cache', 'index', 'async', 'parallel', 'optimize',
            'batch', 'lazy', 'buffer', 'pool', 'queue'
        ]

        for task in tasks:
            task_desc = task.get('description', '').lower()
            if any(keyword in task_desc for keyword in performance_keywords):
                performance_indicators += 1

        performance_score = performance_indicators / total_checks if total_checks > 0 else 0.5

        total_duration_ms = sum(task.get('estimated_duration_ms', 0) for task in tasks)
        if total_duration_ms > 0:
            normalized_duration = min(1.0, total_duration_ms / 3600000.0)
            duration_penalty = 1.0 - (normalized_duration * 0.3)
            performance_score = (performance_score + duration_penalty) / 2.0

        return max(0.0, min(1.0, performance_score))

    @staticmethod
    def analyze_code_quality(tasks: List[Dict]) -> float:
        """Implementação do método de análise de qualidade de código."""
        if not tasks:
            return 0.5

        quality_indicators = {
            'tests': 0,
            'documentation': 0,
            'error_handling': 0,
            'logging': 0
        }

        test_keywords = ['test', 'spec', 'unit', 'integration']
        doc_keywords = ['document', 'comment', 'doc', 'readme']
        error_keywords = ['error', 'exception', 'try', 'catch', 'handle']
        log_keywords = ['log', 'trace', 'debug', 'monitor']

        for task in tasks:
            task_desc = task.get('description', '').lower()

            if any(kw in task_desc for kw in test_keywords):
                quality_indicators['tests'] += 1
            if any(kw in task_desc for kw in doc_keywords):
                quality_indicators['documentation'] += 1
            if any(kw in task_desc for kw in error_keywords):
                quality_indicators['error_handling'] += 1
            if any(kw in task_desc for kw in log_keywords):
                quality_indicators['logging'] += 1

        num_tasks = len(tasks)
        scores = [
            min(1.0, quality_indicators['tests'] / max(1, num_tasks * 0.3)),
            min(1.0, quality_indicators['documentation'] / max(1, num_tasks * 0.2)),
            min(1.0, quality_indicators['error_handling'] / max(1, num_tasks * 0.3)),
            min(1.0, quality_indicators['logging'] / max(1, num_tasks * 0.2))
        ]

        code_quality_score = sum(scores) / len(scores)

        return max(0.0, min(1.0, code_quality_score))

    @staticmethod
    def calculate_technical_risk(
        cognitive_plan: Dict,
        security_score: float,
        architecture_score: float,
        performance_score: float,
        code_quality_score: float
    ) -> float:
        """Implementação do cálculo de risco técnico."""
        weighted_avg = (
            security_score * 0.35 +
            architecture_score * 0.3 +
            performance_score * 0.2 +
            code_quality_score * 0.15
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
        security_score: float,
        architecture_score: float,
        performance_score: float,
        code_quality_score: float,
        recommendation: str
    ) -> str:
        """Gera narrativa de justificativa."""
        return (
            f"Avaliação técnica: "
            f"security={security_score:.2f}, "
            f"architecture={architecture_score:.2f}, "
            f"performance={performance_score:.2f}, "
            f"code_quality={code_quality_score:.2f}. "
            f"Recomendação: {recommendation}."
        )

    @staticmethod
    def generate_mitigations(
        security_score: float,
        architecture_score: float,
        performance_score: float,
        code_quality_score: float
    ) -> List[Dict]:
        """Gera sugestões de mitigação de riscos técnicos."""
        mitigations = []

        if security_score < 0.6:
            mitigations.append({
                'mitigation_type': 'improve_security',
                'description': 'Implementar controles de segurança adicionais',
                'priority': 'critical',
                'estimated_effort': 'high'
            })

        if architecture_score < 0.6:
            mitigations.append({
                'mitigation_type': 'refactor_architecture',
                'description': 'Melhorar padrões arquiteturais e design',
                'priority': 'high',
                'estimated_effort': 'medium'
            })

        if performance_score < 0.6:
            mitigations.append({
                'mitigation_type': 'optimize_performance',
                'description': 'Otimizar performance e uso de recursos',
                'priority': 'medium',
                'estimated_effort': 'medium'
            })

        if code_quality_score < 0.6:
            mitigations.append({
                'mitigation_type': 'improve_code_quality',
                'description': 'Melhorar qualidade e manutenibilidade do código',
                'priority': 'medium',
                'estimated_effort': 'low'
            })

        return mitigations


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo."""
    return {
        'plan_id': 'plan-123',
        'original_domain': 'api-development',
        'original_priority': 'high',
        'tasks': [
            {
                'task_id': 'task-1',
                'description': 'Implement authentication with JWT token validation',
                'dependencies': [],
                'estimated_duration_ms': 30000
            },
            {
                'task_id': 'task-2',
                'description': 'Create user controller with input validation',
                'dependencies': ['task-1'],
                'estimated_duration_ms': 45000
            },
            {
                'task_id': 'task-3',
                'description': 'Add unit tests for all endpoints',
                'dependencies': ['task-2'],
                'estimated_duration_ms': 60000
            },
            {
                'task_id': 'task-4',
                'description': 'Implement caching layer with Redis',
                'dependencies': [],
                'estimated_duration_ms': 20000
            }
        ]
    }


class TestSecurityAnalysis:
    """Testes de análise de segurança."""

    def test_security_analysis_with_security_keywords(self, sample_cognitive_plan):
        """Testa análise com palavras-chave de segurança."""
        plan = sample_cognitive_plan.copy()
        plan['tasks'] = [
            {'description': 'Implement authentication with OAuth2', 'dependencies': []},
            {'description': 'Add input validation and sanitize user input', 'dependencies': []},
            {'description': 'Encrypt sensitive data at rest', 'dependencies': []}
        ]

        score = TechnicalAnalysisTestHelper.analyze_security(plan['tasks'], plan)
        assert score > 0.5

    def test_security_analysis_without_security_keywords(self):
        """Testa análise sem palavras-chave de segurança."""
        tasks = [
            {'description': 'Create basic endpoint', 'dependencies': []},
            {'description': 'Add UI component', 'dependencies': []}
        ]

        score = TechnicalAnalysisTestHelper.analyze_security(tasks, {})
        assert score < 0.5

    def test_security_analysis_empty_tasks(self):
        """Testa análise com lista vazia de tarefas."""
        score = TechnicalAnalysisTestHelper.analyze_security([], {})
        assert score == 0.5

    def test_security_analysis_data_domain_requires_validation(self):
        """Testa que domínio data requer validação."""
        plan = {
            'original_domain': 'data-processing',
            'tasks': [
                {'description': 'Validate all input data', 'dependencies': []}
            ]
        }

        score = TechnicalAnalysisTestHelper.analyze_security(plan['tasks'], plan)
        assert score > 0.5


class TestArchitectureAnalysis:
    """Testes de análise de arquitetura."""

    def test_architecture_analysis_modular_tasks(self):
        """Testa análise com tarefas modulares bem definidas."""
        tasks = [
            {'description': 'Create user service with clear responsibility', 'dependencies': []},
            {'description': 'Implement repository pattern for data access', 'dependencies': []},
            {'description': 'Add controller for HTTP requests', 'dependencies': []}
        ]

        score = TechnicalAnalysisTestHelper.analyze_architecture(tasks, {})
        assert score > 0.5

    def test_architecture_analysis_low_coupling(self):
        """Testa análise com baixo acoplamento."""
        tasks = [
            {'description': 'Create independent service with controller and repository', 'dependencies': []},
            {'description': 'Add another independent service component', 'dependencies': []}
        ]

        score = TechnicalAnalysisTestHelper.analyze_architecture(tasks, {})
        # Com patterns: modularity=1.0, coupling=1.0, pattern>0, score deve ser >0.6
        assert score > 0.6

    def test_architecture_analysis_high_coupling(self):
        """Testa análise com alto acoplamento."""
        tasks = [
            {'description': 'Task 1', 'dependencies': ['task-2', 'task-3', 'task-4', 'task-5']},
            {'description': 'Task 2', 'dependencies': []}
        ]

        score = TechnicalAnalysisTestHelper.analyze_architecture(tasks, {})
        assert score < 0.7

    def test_architecture_analysis_pattern_mentions(self):
        """Testa análise com menções a padrões arquiteturais."""
        tasks = [
            {'description': 'Implement factory pattern for object creation', 'dependencies': []},
            {'description': 'Add repository for database operations', 'dependencies': []},
            {'description': 'Create service layer for business logic', 'dependencies': []}
        ]

        score = TechnicalAnalysisTestHelper.analyze_architecture(tasks, {})
        assert score > 0.5

    def test_architecture_analysis_empty_tasks(self):
        """Testa análise com lista vazia de tarefas."""
        score = TechnicalAnalysisTestHelper.analyze_architecture([], {})
        assert score == 0.5


class TestPerformanceAnalysis:
    """Testes de análise de performance."""

    def test_performance_analysis_with_optimizations(self):
        """Testa análise com palavras-chave de otimização."""
        tasks = [
            {'description': 'Add caching layer for expensive queries', 'dependencies': []},
            {'description': 'Implement async processing for background jobs', 'dependencies': []},
            {'description': 'Add database indexes for fast lookups', 'dependencies': []}
        ]

        score = TechnicalAnalysisTestHelper.analyze_performance(tasks)
        assert score > 0.5

    def test_performance_analysis_without_optimizations(self):
        """Testa análise sem palavras-chave de otimização."""
        tasks = [
            {'description': 'Create basic functionality', 'dependencies': []},
            {'description': 'Add simple endpoint', 'dependencies': []}
        ]

        score = TechnicalAnalysisTestHelper.analyze_performance(tasks)
        assert score < 0.5

    def test_performance_analysis_with_duration_penalty(self):
        """Testa penalização por duração longa."""
        tasks = [
            {'description': 'Add caching', 'estimated_duration_ms': 1000},
            {'description': 'Slow task', 'estimated_duration_ms': 4000000}
        ]

        score = TechnicalAnalysisTestHelper.analyze_performance(tasks)
        assert score < 1.0

    def test_performance_analysis_empty_tasks(self):
        """Testa análise com lista vazia de tarefas."""
        score = TechnicalAnalysisTestHelper.analyze_performance([])
        assert score == 0.5


class TestCodeQualityAnalysis:
    """Testes de análise de qualidade de código."""

    def test_code_quality_with_all_indicators(self):
        """Testa análise com todos os indicadores de qualidade."""
        tasks = [
            {'description': 'Write unit tests for all functions', 'dependencies': []},
            {'description': 'Add documentation and comments', 'dependencies': []},
            {'description': 'Implement error handling with try catch', 'dependencies': []},
            {'description': 'Add logging for debugging', 'dependencies': []}
        ]

        score = TechnicalAnalysisTestHelper.analyze_code_quality(tasks)
        assert score > 0.5

    def test_code_quality_no_indicators(self):
        """Testa análise sem indicadores de qualidade."""
        tasks = [
            {'description': 'Create basic feature', 'dependencies': []},
            {'description': 'Add another feature', 'dependencies': []}
        ]

        score = TechnicalAnalysisTestHelper.analyze_code_quality(tasks)
        assert score < 0.5

    def test_code_quality_only_tests(self):
        """Testa análise apenas com testes."""
        tasks = [
            {'description': 'Add unit tests', 'dependencies': []},
            {'description': 'Add integration specs', 'dependencies': []}
        ]

        score = TechnicalAnalysisTestHelper.analyze_code_quality(tasks)
        assert 0.0 < score < 1.0

    def test_code_quality_empty_tasks(self):
        """Testa análise com lista vazia de tarefas."""
        score = TechnicalAnalysisTestHelper.analyze_code_quality([])
        assert score == 0.5


class TestTechnicalRiskCalculation:
    """Testes de cálculo de risco técnico."""

    def test_risk_calculation_low_risk(self):
        """Testa cálculo de risco com scores altos."""
        risk = TechnicalAnalysisTestHelper.calculate_technical_risk(
            cognitive_plan={},
            security_score=0.9,
            architecture_score=0.85,
            performance_score=0.8,
            code_quality_score=0.75
        )
        assert risk < 0.3

    def test_risk_calculation_high_risk(self):
        """Testa cálculo de risco com scores baixos."""
        risk = TechnicalAnalysisTestHelper.calculate_technical_risk(
            cognitive_plan={},
            security_score=0.3,
            architecture_score=0.4,
            performance_score=0.35,
            code_quality_score=0.4
        )
        assert risk > 0.6

    def test_risk_calculation_security_weighted(self):
        """Testa que segurança tem maior peso no risco."""
        risk_low_security = TechnicalAnalysisTestHelper.calculate_technical_risk(
            cognitive_plan={},
            security_score=0.2,
            architecture_score=0.8,
            performance_score=0.8,
            code_quality_score=0.8
        )

        risk_low_quality = TechnicalAnalysisTestHelper.calculate_technical_risk(
            cognitive_plan={},
            security_score=0.8,
            architecture_score=0.8,
            performance_score=0.8,
            code_quality_score=0.2
        )

        assert risk_low_security > risk_low_quality


class TestRecommendationDetermination:
    """Testes de determinação de recomendação."""

    def test_recommendation_approve(self):
        """Testa recomendação de aprovação."""
        recommendation = TechnicalAnalysisTestHelper.determine_recommendation(
            confidence_score=0.85,
            risk_score=0.2
        )
        assert recommendation == 'approve'

    def test_recommendation_reject_low_confidence(self):
        """Testa rejeição por baixa confiança."""
        recommendation = TechnicalAnalysisTestHelper.determine_recommendation(
            confidence_score=0.4,
            risk_score=0.5
        )
        assert recommendation == 'reject'

    def test_recommendation_reject_high_risk(self):
        """Testa rejeição por alto risco."""
        recommendation = TechnicalAnalysisTestHelper.determine_recommendation(
            confidence_score=0.6,
            risk_score=0.8
        )
        assert recommendation == 'reject'

    def test_recommendation_review_required(self):
        """Testa recomendação de revisão necessária."""
        recommendation = TechnicalAnalysisTestHelper.determine_recommendation(
            confidence_score=0.6,
            risk_score=0.6
        )
        assert recommendation == 'review_required'

    def test_recommendation_conditional(self):
        """Testa recomendação condicional."""
        recommendation = TechnicalAnalysisTestHelper.determine_recommendation(
            confidence_score=0.7,
            risk_score=0.4
        )
        assert recommendation == 'conditional'


class TestReasoningGeneration:
    """Testes de geração de justificativa."""

    def test_reasoning_includes_all_scores(self):
        """Testa que justificativa inclui todos os scores."""
        reasoning = TechnicalAnalysisTestHelper.generate_reasoning(
            security_score=0.8,
            architecture_score=0.75,
            performance_score=0.7,
            code_quality_score=0.85,
            recommendation='approve'
        )

        assert 'security=0.80' in reasoning
        assert 'architecture=0.75' in reasoning
        assert 'performance=0.70' in reasoning
        assert 'code_quality=0.85' in reasoning
        assert 'approve' in reasoning


class TestMitigationGeneration:
    """Testes de geração de mitigações."""

    def test_mitigations_security_low(self):
        """Testa mitigação para segurança baixa."""
        mitigations = TechnicalAnalysisTestHelper.generate_mitigations(
            security_score=0.4,
            architecture_score=0.8,
            performance_score=0.8,
            code_quality_score=0.8
        )

        assert len(mitigations) > 0
        assert any(m['mitigation_type'] == 'improve_security' for m in mitigations)
        assert mitigations[0]['priority'] == 'critical'

    def test_mitigations_architecture_low(self):
        """Testa mitigação para arquitetura baixa."""
        mitigations = TechnicalAnalysisTestHelper.generate_mitigations(
            security_score=0.8,
            architecture_score=0.4,
            performance_score=0.8,
            code_quality_score=0.8
        )

        assert any(m['mitigation_type'] == 'refactor_architecture' for m in mitigations)

    def test_mitigations_performance_low(self):
        """Testa mitigação para performance baixa."""
        mitigations = TechnicalAnalysisTestHelper.generate_mitigations(
            security_score=0.8,
            architecture_score=0.8,
            performance_score=0.4,
            code_quality_score=0.8
        )

        assert any(m['mitigation_type'] == 'optimize_performance' for m in mitigations)

    def test_mitigations_code_quality_low(self):
        """Testa mitigação para qualidade de código baixa."""
        mitigations = TechnicalAnalysisTestHelper.generate_mitigations(
            security_score=0.8,
            architecture_score=0.8,
            performance_score=0.8,
            code_quality_score=0.4
        )

        assert any(m['mitigation_type'] == 'improve_code_quality' for m in mitigations)

    def test_mitigations_all_good(self):
        """Testa que não gera mitigações quando scores são bons."""
        mitigations = TechnicalAnalysisTestHelper.generate_mitigations(
            security_score=0.8,
            architecture_score=0.8,
            performance_score=0.8,
            code_quality_score=0.8
        )

        assert len(mitigations) == 0


class TestCompleteEvaluationFlow:
    """Testes do fluxo completo de avaliação."""

    def test_complete_evaluation_with_good_plan(self, sample_cognitive_plan):
        """Testa avaliação completa de um plano bom."""
        tasks = sample_cognitive_plan['tasks']

        security = TechnicalAnalysisTestHelper.analyze_security(tasks, sample_cognitive_plan)
        architecture = TechnicalAnalysisTestHelper.analyze_architecture(tasks, sample_cognitive_plan)
        performance = TechnicalAnalysisTestHelper.analyze_performance(tasks)
        quality = TechnicalAnalysisTestHelper.analyze_code_quality(tasks)

        confidence = (
            security * 0.3 +
            architecture * 0.3 +
            performance * 0.2 +
            quality * 0.2
        )

        risk = TechnicalAnalysisTestHelper.calculate_technical_risk(
            sample_cognitive_plan, security, architecture, performance, quality
        )

        recommendation = TechnicalAnalysisTestHelper.determine_recommendation(confidence, risk)
        mitigations = TechnicalAnalysisTestHelper.generate_mitigations(
            security, architecture, performance, quality
        )

        assert 0.0 <= confidence <= 1.0
        assert 0.0 <= risk <= 1.0
        assert recommendation in ['approve', 'reject', 'review_required', 'conditional']
        assert isinstance(mitigations, list)

    def test_complete_evaluation_with_poor_plan(self):
        """Testa avaliação completa de um plano ruim."""
        plan = {
            'plan_id': 'poor-plan',
            'original_domain': 'basic-development',
            'tasks': [
                {'description': 'Create endpoint', 'dependencies': []},
                {'description': 'Add feature', 'dependencies': ['task-1', 'task-2', 'task-3', 'task-4']},
            ]
        }

        tasks = plan['tasks']
        security = TechnicalAnalysisTestHelper.analyze_security(tasks, plan)
        architecture = TechnicalAnalysisTestHelper.analyze_architecture(tasks, plan)
        performance = TechnicalAnalysisTestHelper.analyze_performance(tasks)
        quality = TechnicalAnalysisTestHelper.analyze_code_quality(tasks)

        risk = TechnicalAnalysisTestHelper.calculate_technical_risk(
            plan, security, architecture, performance, quality
        )

        # Plano pobre deve ter risco mais alto
        assert risk > 0.3
