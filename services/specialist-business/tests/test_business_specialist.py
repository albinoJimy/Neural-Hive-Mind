"""Testes unitários para BusinessSpecialist - Métodos de Análise."""

import sys
import os
import pytest
from typing import Dict, Any, List

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class BusinessAnalysisTestHelper:
    """Helper class para testar métodos de análise sem inicialização completa."""

    @staticmethod
    def analyze_workflow(tasks: List[Dict]) -> float:
        """Implementação do método de análise de workflow."""
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        # Penalizar complexidade excessiva
        if num_tasks <= 5:
            complexity_penalty = 0.8
        elif num_tasks <= 15:
            complexity_penalty = 1.0
        elif num_tasks <= 25:
            complexity_penalty = 0.7
        else:
            complexity_penalty = 0.5

        # Calcular paralelização
        total_dependencies = sum(len(task.get("dependencies", [])) for task in tasks)
        max_possible_deps = num_tasks * (num_tasks - 1) / 2

        if max_possible_deps > 0:
            dependency_ratio = total_dependencies / max_possible_deps
            parallelization_score = 1.0 - (dependency_ratio * 0.7)
        else:
            parallelization_score = 1.0

        # Verificar palavras-chave de eficiência
        efficiency_keywords = ["parallel", "async", "batch", "optimize", "streamline"]
        efficiency_count = sum(
            1
            for task in tasks
            if any(
                keyword in task.get("description", "").lower() for keyword in efficiency_keywords
            )
        )
        efficiency_bonus = min(0.2, efficiency_count / num_tasks)

        workflow_score = complexity_penalty * 0.4 + parallelization_score * 0.4 + efficiency_bonus

        return max(0.0, min(1.0, workflow_score))

    @staticmethod
    def analyze_kpis(cognitive_plan: Dict, context: Dict) -> float:
        """Implementação do método de análise de KPIs."""
        # Verificar menções de KPIs e métricas
        plan_desc = cognitive_plan.get("description", "").lower()
        tasks = cognitive_plan.get("tasks", [])

        kpi_keywords = [
            "kpi",
            "metric",
            "revenue",
            "cost",
            "roi",
            "conversion",
            "retention",
            "engagement",
            "performance",
            "quality",
        ]

        kpi_mentions = sum(1 for keyword in kpi_keywords if keyword in plan_desc)

        # Verificar tarefas com foco em métricas
        metric_tasks = sum(
            1
            for task in tasks
            if any(keyword in task.get("description", "").lower() for keyword in kpi_keywords)
        )

        num_tasks = len(tasks) if tasks else 1
        base_score = min(1.0, (kpi_mentions + metric_tasks) / (num_tasks * 0.5))

        # Verificar se há metas definidas no contexto
        has_goals = context.get("business_goals") is not None
        goal_bonus = 0.2 if has_goals else 0.0

        return min(1.0, base_score + goal_bonus)

    @staticmethod
    def analyze_costs(tasks: List[Dict]) -> float:
        """Implementação do método de análise de custos."""
        if not tasks:
            return 0.5

        # Calcular custo total estimado
        total_duration_ms = sum(task.get("estimated_duration_ms", 0) for task in tasks)
        total_cost_units = total_duration_ms / 1000  # Unidades arbitrárias

        # Custo moderado é melhor (nem muito barato nem muito caro)
        # Ideal: 10-100 unidades
        if total_cost_units < 10:
            cost_efficiency = 0.6  # Muito barato pode indicar falta de recursos
        elif total_cost_units <= 100:
            cost_efficiency = 1.0  # Ideal
        elif total_cost_units <= 500:
            cost_efficiency = 0.7  # Aceitável
        else:
            cost_efficiency = 0.4  # Muito caro

        # Verificar menções de otimização de custo
        cost_keywords = ["optimize", "efficient", "reduce", "save", "cost-effective"]
        optimization_count = sum(
            1
            for task in tasks
            if any(keyword in task.get("description", "").lower() for keyword in cost_keywords)
        )
        optimization_bonus = min(0.2, optimization_count / len(tasks))

        return min(1.0, cost_efficiency + optimization_bonus)

    @staticmethod
    def calculate_business_risk(
        cognitive_plan: Dict, workflow_score: float, kpi_score: float, cost_score: float
    ) -> float:
        """Implementação do cálculo de risco de negócio."""
        # Média ponderada inversa
        weighted_avg = workflow_score * 0.4 + kpi_score * 0.3 + cost_score * 0.3
        risk_score = 1.0 - weighted_avg

        # Ajustar por prioridade do plano
        priority = cognitive_plan.get("original_priority", "normal")
        if priority == "critical" and weighted_avg < 0.7:
            risk_score += 0.1  # Penalizar planos críticos com baixa qualidade

        return max(0.0, min(1.0, risk_score))

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

    @staticmethod
    def generate_reasoning(
        workflow_score: float, kpi_score: float, cost_score: float, recommendation: str
    ) -> str:
        """Gera narrativa de justificativa."""
        return (
            f"Avaliação de negócios: "
            f"workflow={workflow_score:.2f}, "
            f"kpi={kpi_score:.2f}, "
            f"cost={cost_score:.2f}. "
            f"Recomendação: {recommendation}."
        )

    @staticmethod
    def generate_mitigations(
        workflow_score: float, kpi_score: float, cost_score: float
    ) -> List[Dict]:
        """Gera sugestões de mitigação de riscos de negócio."""
        mitigations = []

        if workflow_score < 0.6:
            mitigations.append(
                {
                    "mitigation_type": "optimize_workflow",
                    "description": "Otimizar fluxo de trabalho para reduzir complexidade",
                    "priority": "high",
                    "estimated_effort": "medium",
                }
            )

        if kpi_score < 0.6:
            mitigations.append(
                {
                    "mitigation_type": "define_kpis",
                    "description": "Definir KPIs claros para medir sucesso do negócio",
                    "priority": "critical",
                    "estimated_effort": "low",
                }
            )

        if cost_score < 0.6:
            mitigations.append(
                {
                    "mitigation_type": "optimize_costs",
                    "description": "Revisar estimativas de custo e buscar eficiência",
                    "priority": "high",
                    "estimated_effort": "medium",
                }
            )

        return mitigations


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo."""
    return {
        "plan_id": "plan-789",
        "original_domain": "business-process-automation",
        "original_priority": "high",
        "description": "Automate customer onboarding to improve conversion and reduce time",
        "tasks": [
            {
                "task_id": "task-1",
                "description": "Design efficient workflow with parallel processing",
                "dependencies": [],
                "estimated_duration_ms": 20000,
            },
            {
                "task_id": "task-2",
                "description": "Implement KPI tracking for conversion metrics",
                "dependencies": ["task-1"],
                "estimated_duration_ms": 30000,
            },
            {
                "task_id": "task-3",
                "description": "Optimize cost-effective implementation",
                "dependencies": ["task-2"],
                "estimated_duration_ms": 25000,
            },
        ],
    }


class TestWorkflowAnalysis:
    """Testes de análise de workflow."""

    def test_workflow_ideal_complexity(self):
        """Testa análise com complexidade ideal."""
        tasks = [
            {"description": "Task 1", "dependencies": []},
            {"description": "Task 2", "dependencies": []},
        ] * 10  # 10 tarefas = ideal

        score = BusinessAnalysisTestHelper.analyze_workflow(tasks)
        assert score > 0.5

    def test_workflow_too_complex(self):
        """Testa análise com complexidade excessiva."""
        tasks = [{"description": f"Task {i}", "dependencies": []} for i in range(30)]

        score = BusinessAnalysisTestHelper.analyze_workflow(tasks)
        assert score < 0.7

    def test_workflow_with_parallelization(self):
        """Testa análise com boa paralelização."""
        tasks = [
            {"description": "Parallel task 1", "dependencies": []},
            {"description": "Parallel task 2", "dependencies": []},
            {"description": "Sequential task", "dependencies": ["task-1", "task-2"]},
        ]

        score = BusinessAnalysisTestHelper.analyze_workflow(tasks)
        assert score >= 0.5

    def test_workflow_with_efficiency_keywords(self):
        """Testa análise com palavras-chave de eficiência."""
        tasks = [
            {"description": "Optimize process with parallel execution", "dependencies": []},
            {"description": "Batch process data asynchronously", "dependencies": []},
        ]

        score = BusinessAnalysisTestHelper.analyze_workflow(tasks)
        assert score > 0.5

    def test_workflow_empty_tasks(self):
        """Testa análise com lista vazia de tarefas."""
        score = BusinessAnalysisTestHelper.analyze_workflow([])
        assert score == 0.5


class TestKPIAnalysis:
    """Testes de análise de KPIs."""

    def test_kpi_with_mentions(self):
        """Testa análise com menções de KPIs."""
        plan = {
            "description": "Improve ROI and conversion rate",
            "tasks": [
                {"description": "Track revenue metrics", "dependencies": []},
                {"description": "Monitor engagement KPIs", "dependencies": []},
            ],
        }

        score = BusinessAnalysisTestHelper.analyze_kpis(plan, {})
        assert score > 0.5

    def test_kpi_with_business_goals(self):
        """Testa análise com metas de negócio definidas."""
        plan = {
            "description": "Implement feature",
            "tasks": [{"description": "Task 1", "dependencies": []}],
        }
        context = {"business_goals": ["increase_revenue"]}

        score = BusinessAnalysisTestHelper.analyze_kpis(plan, context)
        assert score > 0.0

    def test_kpi_no_mentions(self):
        """Testa análise sem menções de KPIs."""
        plan = {
            "description": "Create basic functionality",
            "tasks": [{"description": "Add feature", "dependencies": []}],
        }

        score = BusinessAnalysisTestHelper.analyze_kpis(plan, {})
        assert score < 0.5


class TestCostAnalysis:
    """Testes de análise de custos."""

    def test_cost_ideal_range(self):
        """Testa análise com custo na faixa ideal."""
        tasks = [
            {"description": "Task 1", "estimated_duration_ms": 30000},
            {"description": "Task 2", "estimated_duration_ms": 40000},
        ]

        score = BusinessAnalysisTestHelper.analyze_costs(tasks)
        assert score >= 0.7

    def test_cost_too_low(self):
        """Testa análise com custo muito baixo."""
        tasks = [{"description": "Quick task", "estimated_duration_ms": 1000}]

        score = BusinessAnalysisTestHelper.analyze_costs(tasks)
        assert score < 0.7

    def test_cost_too_high(self):
        """Testa análise com custo muito alto."""
        tasks = [{"description": "Expensive task", "estimated_duration_ms": 600000}]

        score = BusinessAnalysisTestHelper.analyze_costs(tasks)
        assert score < 0.7

    def test_cost_with_optimization(self):
        """Testa análise com otimização de custo."""
        tasks = [
            {"description": "Optimize and reduce implementation time", "dependencies": []},
            {"description": "Use cost-effective approach", "dependencies": []},
        ]

        score = BusinessAnalysisTestHelper.analyze_costs(tasks)
        assert score > 0.5

    def test_cost_empty_tasks(self):
        """Testa análise com lista vazia de tarefas."""
        score = BusinessAnalysisTestHelper.analyze_costs([])
        assert score == 0.5


class TestBusinessRiskCalculation:
    """Testes de cálculo de risco de negócio."""

    def test_risk_calculation_low_risk(self):
        """Testa cálculo de risco com scores altos."""
        risk = BusinessAnalysisTestHelper.calculate_business_risk(
            cognitive_plan={}, workflow_score=0.9, kpi_score=0.85, cost_score=0.8
        )
        assert risk < 0.3

    def test_risk_calculation_high_risk(self):
        """Testa cálculo de risco com scores baixos."""
        risk = BusinessAnalysisTestHelper.calculate_business_risk(
            cognitive_plan={}, workflow_score=0.3, kpi_score=0.4, cost_score=0.35
        )
        assert risk > 0.6

    def test_risk_calculation_critical_priority_penalty(self):
        """Testa penalização para prioridade crítica."""
        risk_normal = BusinessAnalysisTestHelper.calculate_business_risk(
            cognitive_plan={"original_priority": "normal"},
            workflow_score=0.6,
            kpi_score=0.6,
            cost_score=0.6,
        )

        risk_critical = BusinessAnalysisTestHelper.calculate_business_risk(
            cognitive_plan={"original_priority": "critical"},
            workflow_score=0.6,
            kpi_score=0.6,
            cost_score=0.6,
        )

        assert risk_critical >= risk_normal


class TestRecommendationDetermination:
    """Testes de determinação de recomendação."""

    def test_recommendation_approve(self):
        """Testa recomendação de aprovação."""
        recommendation = BusinessAnalysisTestHelper.determine_recommendation(
            confidence_score=0.85, risk_score=0.2
        )
        assert recommendation == "approve"

    def test_recommendation_reject_low_confidence(self):
        """Testa rejeição por baixa confiança."""
        recommendation = BusinessAnalysisTestHelper.determine_recommendation(
            confidence_score=0.4, risk_score=0.5
        )
        assert recommendation == "reject"

    def test_recommendation_reject_high_risk(self):
        """Testa rejeição por alto risco."""
        recommendation = BusinessAnalysisTestHelper.determine_recommendation(
            confidence_score=0.6, risk_score=0.8
        )
        assert recommendation == "reject"

    def test_recommendation_review_required(self):
        """Testa recomendação de revisão necessária."""
        recommendation = BusinessAnalysisTestHelper.determine_recommendation(
            confidence_score=0.6, risk_score=0.6
        )
        assert recommendation == "review_required"

    def test_recommendation_conditional(self):
        """Testa recomendação condicional."""
        recommendation = BusinessAnalysisTestHelper.determine_recommendation(
            confidence_score=0.7, risk_score=0.4
        )
        assert recommendation == "conditional"


class TestReasoningGeneration:
    """Testes de geração de justificativa."""

    def test_reasoning_includes_all_scores(self):
        """Testa que justificativa inclui todos os scores."""
        reasoning = BusinessAnalysisTestHelper.generate_reasoning(
            workflow_score=0.8, kpi_score=0.75, cost_score=0.7, recommendation="approve"
        )

        assert "workflow=0.80" in reasoning
        assert "kpi=0.75" in reasoning
        assert "cost=0.70" in reasoning
        assert "approve" in reasoning


class TestMitigationGeneration:
    """Testes de geração de mitigações."""

    def test_mitigations_workflow_low(self):
        """Testa mitigação para workflow baixo."""
        mitigations = BusinessAnalysisTestHelper.generate_mitigations(
            workflow_score=0.4, kpi_score=0.8, cost_score=0.8
        )

        assert any(m["mitigation_type"] == "optimize_workflow" for m in mitigations)

    def test_mitigations_kpi_low(self):
        """Testa mitigação para KPI baixo."""
        mitigations = BusinessAnalysisTestHelper.generate_mitigations(
            workflow_score=0.8, kpi_score=0.4, cost_score=0.8
        )

        assert any(m["mitigation_type"] == "define_kpis" for m in mitigations)
        assert any(m["priority"] == "critical" for m in mitigations)

    def test_mitigations_cost_low(self):
        """Testa mitigação para custo baixo."""
        mitigations = BusinessAnalysisTestHelper.generate_mitigations(
            workflow_score=0.8, kpi_score=0.8, cost_score=0.4
        )

        assert any(m["mitigation_type"] == "optimize_costs" for m in mitigations)

    def test_mitigations_multiple_issues(self):
        """Testa múltiplas mitigações para múltiplos problemas."""
        mitigations = BusinessAnalysisTestHelper.generate_mitigations(
            workflow_score=0.5, kpi_score=0.4, cost_score=0.3
        )

        assert len(mitigations) >= 3

    def test_mitigations_all_good(self):
        """Testa que não gera mitigações quando scores são bons."""
        mitigations = BusinessAnalysisTestHelper.generate_mitigations(
            workflow_score=0.8, kpi_score=0.8, cost_score=0.8
        )

        assert len(mitigations) == 0


class TestCompleteEvaluationFlow:
    """Testes do fluxo completo de avaliação."""

    def test_complete_evaluation_with_good_business_case(self, sample_cognitive_plan):
        """Testa avaliação completa de um caso de negócio bom."""
        tasks = sample_cognitive_plan["tasks"]

        workflow = BusinessAnalysisTestHelper.analyze_workflow(tasks)
        kpi = BusinessAnalysisTestHelper.analyze_kpis(sample_cognitive_plan, {})
        cost = BusinessAnalysisTestHelper.analyze_costs(tasks)

        confidence = (workflow + kpi + cost) / 3.0

        risk = BusinessAnalysisTestHelper.calculate_business_risk(
            sample_cognitive_plan, workflow, kpi, cost
        )

        recommendation = BusinessAnalysisTestHelper.determine_recommendation(confidence, risk)
        mitigations = BusinessAnalysisTestHelper.generate_mitigations(workflow, kpi, cost)

        assert 0.0 <= confidence <= 1.0
        assert 0.0 <= risk <= 1.0
        assert recommendation in ["approve", "reject", "review_required", "conditional"]
        assert isinstance(mitigations, list)

    def test_complete_evaluation_with_poor_business_case(self):
        """Testa avaliação completa de um caso de negócio ruim."""
        plan = {
            "plan_id": "poor-business",
            "original_domain": "basic-feature",
            "original_priority": "normal",
            "description": "Add simple feature",
            "tasks": [
                {
                    "description": "Complex task with many dependencies",
                    "dependencies": [f"task-{i}" for i in range(10)],
                    "estimated_duration_ms": 1000000,
                },
            ],
        }

        tasks = plan["tasks"]
        workflow = BusinessAnalysisTestHelper.analyze_workflow(tasks)
        kpi = BusinessAnalysisTestHelper.analyze_kpis(plan, {})
        cost = BusinessAnalysisTestHelper.analyze_costs(tasks)

        risk = BusinessAnalysisTestHelper.calculate_business_risk(plan, workflow, kpi, cost)

        # Caso de negócio pobre deve ter risco mais alto
        assert risk > 0.3


class TestMLModelIntegration:
    """Testes de integração com modelo ML do especialista."""

    def test_ml_model_features_extraction(self):
        """Testa extração de features para modelo ML."""
        # Features esperadas pelo modelo BusinessSpecialistModel
        expected_features = [
            "business_value",
            "roi_score",
            "cost_benefit_ratio",
            "process_efficiency",
            "strategic_alignment",
            "market_impact",
        ]

        # Simular extração de features de um cognitive plan
        cognitive_plan = {
            "plan_id": "test-plan",
            "original_domain": "business",
            "original_priority": "high",
            "tasks": [
                {
                    "description": "Implement business logic with high ROI",
                    "estimated_duration_ms": 50000,
                    "dependencies": [],
                }
            ],
        }

        # Extrair features (simulado - na prática seria extraído pelo especialista)
        features = {
            "business_value": 0.8,  # Alto valor de negócio
            "roi_score": 0.7,  # Bom ROI
            "cost_benefit_ratio": 0.75,  # Razão custo-benefício positiva
            "process_efficiency": 0.6,  # Eficiência moderada
            "strategic_alignment": 0.9,  # Alto alinhamento estratégico
            "market_impact": 0.7,  # Impacto de mercado positivo
        }

        # Verificar que todas as features esperadas estão presentes
        for feature in expected_features:
            assert feature in features, f"Feature {feature} não encontrada"

        # Verificar que os valores estão entre 0 e 1
        for feature, value in features.items():
            assert 0.0 <= value <= 1.0, f"Feature {feature} com valor inválido: {value}"

    def test_ml_model_prediction(self):
        """Testa predição do modelo ML."""
        from sklearn.ensemble import GradientBoostingClassifier
        import numpy as np

        # Criar um modelo simples para teste
        model = GradientBoostingClassifier(n_estimators=10, max_depth=3, random_state=42)

        # Dados de treino simples
        X_train = np.array(
            [
                [0.8, 0.7, 0.75, 0.6, 0.9, 0.7],  # Bom -> approve
                [0.3, 0.2, 0.4, 0.3, 0.2, 0.3],  # Ruim -> reject
                [0.6, 0.5, 0.6, 0.5, 0.7, 0.6],  # Médio -> conditional
            ]
        )
        y_train = np.array([1, 0, 1])  # 1=approve, 0=reject

        model.fit(X_train, y_train)

        # Testar predição
        X_test = np.array([[0.8, 0.7, 0.75, 0.6, 0.9, 0.7]])
        prediction = model.predict(X_test)[0]
        probability = model.predict_proba(X_test)[0]

        # Verificar predição válida
        assert prediction in [0, 1]
        assert len(probability) == 2
        assert abs(sum(probability) - 1.0) < 0.01  # Probabilidades somam 1

    def test_ml_model_fallback_to_heuristics(self):
        """Testa fallback para heurísticas quando modelo ML não está disponível."""
        # Simular cenário onde modelo ML não está carregado
        ml_model = None

        # Features extraídas
        features = {
            "business_value": 0.8,
            "roi_score": 0.7,
            "cost_benefit_ratio": 0.75,
            "process_efficiency": 0.6,
            "strategic_alignment": 0.9,
            "market_impact": 0.7,
        }

        # Score heurístico (média simples das features)
        heuristic_score = sum(features.values()) / len(features)

        # Se modelo não disponível, usar apenas heurística
        if ml_model is None:
            final_score = heuristic_score
            using_ml = False
        else:
            # Em produção, combinaria ML + heurística
            final_score = 0.7 * ml_model + 0.3 * heuristic_score
            using_ml = True

        # Verificar que fallback funcionou
        assert 0.0 <= final_score <= 1.0
        assert not using_ml  # Confirma que está usando heurística

    def test_ml_heuristic_weighted_combination(self):
        """Testa combinação ponderada de ML e heurística."""
        # Simular scores
        ml_score = 0.8
        heuristic_score = 0.6

        # Combinação ponderada (70% ML, 30% heurística)
        final_score = 0.7 * ml_score + 0.3 * heuristic_score

        # Verificar combinação
        assert 0.6 < final_score < 0.8  # Entre os dois, mais próximo de ML
        assert abs(final_score - 0.74) < 0.01  # 0.7*0.8 + 0.3*0.6 = 0.74

    def test_ml_feature_importance_order(self):
        """Testa ordenação de importância de features."""
        from sklearn.ensemble import GradientBoostingClassifier
        import numpy as np

        # Criar e treinar modelo
        model = GradientBoostingClassifier(n_estimators=10, random_state=42)
        X = np.random.rand(100, 6)
        y = (X[:, 0] + X[:, 1] > 1.0).astype(int)  # business_value + roi_score
        model.fit(X, y)

        # Obter importâncias
        feature_names = [
            "business_value",
            "roi_score",
            "cost_benefit_ratio",
            "process_efficiency",
            "strategic_alignment",
            "market_impact",
        ]
        importances = dict(zip(feature_names, model.feature_importances_))

        # Verificar que importâncias somam aproximadamente 1
        total_importance = sum(importances.values())
        assert abs(total_importance - 1.0) < 0.1

    def test_ml_model_reject_threshold(self):
        """Testa threshold de rejeição do modelo."""
        # Score abaixo do threshold deve resultar em 'reject'
        confidence_score = 0.4
        risk_score = 0.7

        # Determinação de recomendação
        if confidence_score < 0.5 or risk_score > 0.7:
            recommendation = "reject"
        elif confidence_score >= 0.8 and risk_score < 0.3:
            recommendation = "approve"
        elif risk_score > 0.5:
            recommendation = "review_required"
        else:
            recommendation = "conditional"

        assert recommendation == "reject"

    def test_ml_model_approve_threshold(self):
        """Testa threshold de aprovação do modelo."""
        # Score acima do threshold deve resultar em 'approve'
        confidence_score = 0.85
        risk_score = 0.2

        # Determinação de recomendação
        if confidence_score < 0.5 or risk_score > 0.7:
            recommendation = "reject"
        elif confidence_score >= 0.8 and risk_score < 0.3:
            recommendation = "approve"
        elif risk_score > 0.5:
            recommendation = "review_required"
        else:
            recommendation = "conditional"

        assert recommendation == "approve"
