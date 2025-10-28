"""
Implementação do Business Specialist.

Analisa planos cognitivos sob perspectiva de negócios:
- Workflows e processos
- KPIs e métricas de negócio
- Análise de custos
- Eficiência operacional
"""

import sys
from typing import Dict, Any, List
import structlog

sys.path.insert(0, '/app/libraries/python')

from neural_hive_specialists import BaseSpecialist
from config import BusinessSpecialistConfig

logger = structlog.get_logger()


class BusinessSpecialist(BaseSpecialist):
    """Especialista em análise de negócios, workflows, KPIs e custos."""

    def _get_specialist_type(self) -> str:
        """Retorna tipo do especialista."""
        return "business"

    def _load_model(self) -> Any:
        """Carrega modelo de análise de negócios do MLflow."""
        logger.info("Loading Business Specialist model")

        # Verificar se MLflow está disponível
        if self.mlflow_client is None:
            logger.warning("MLflow client not initialized - using heuristic-based evaluation")
            return None

        try:
            # Carregar modelo com fallback para cache expirado
            model = self.mlflow_client.load_model_with_fallback(
                self.config.mlflow_model_name,
                self.config.mlflow_model_stage
            )

            if model:
                # Buscar metadados do modelo para logging de versão
                metadata = self.mlflow_client.get_model_metadata(
                    self.config.mlflow_model_name,
                    self.config.mlflow_model_stage
                )

                logger.info(
                    "ML model loaded successfully",
                    model_name=self.config.mlflow_model_name,
                    stage=self.config.mlflow_model_stage,
                    version=metadata.get('version', 'unknown')
                )

            return model

        except Exception as e:
            # Fallback para heurísticas
            logger.warning(
                "ML model not available, using heuristics",
                error=str(e)
            )
            return None

    def _evaluate_plan_internal(
        self,
        cognitive_plan: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Avalia plano sob perspectiva de negócios.

        Args:
            cognitive_plan: Plano cognitivo a ser avaliado
            context: Contexto adicional da avaliação

        Returns:
            Dicionário com resultado da avaliação
        """
        logger.info(
            "Evaluating plan from business perspective",
            plan_id=cognitive_plan.get('plan_id'),
            domain=cognitive_plan.get('original_domain')
        )

        # Extrair informações do plano
        tasks = cognitive_plan.get('tasks', [])
        domain = cognitive_plan.get('original_domain')
        priority = cognitive_plan.get('original_priority', 'normal')

        # Análise de workflows
        workflow_score = self._analyze_workflow(tasks)

        # Análise de KPIs
        kpi_score = self._analyze_kpis(cognitive_plan, context)

        # Análise de custos
        cost_score = self._analyze_costs(tasks)

        # Calcular scores agregados
        confidence_score = (workflow_score + kpi_score + cost_score) / 3.0

        # Calcular risco de negócio
        risk_score = self._calculate_business_risk(
            cognitive_plan,
            workflow_score,
            kpi_score,
            cost_score
        )

        # Determinar recomendação
        recommendation = self._determine_recommendation(confidence_score, risk_score)

        # Gerar justificativa
        reasoning_summary = self._generate_reasoning(
            workflow_score,
            kpi_score,
            cost_score,
            recommendation
        )

        # Fatores de raciocínio estruturados
        reasoning_factors = [
            {
                'factor_name': 'workflow_efficiency',
                'weight': 0.4,
                'score': workflow_score,
                'description': 'Eficiência do workflow proposto baseado em complexidade e paralelização'
            },
            {
                'factor_name': 'kpi_alignment',
                'weight': 0.3,
                'score': kpi_score,
                'description': 'Alinhamento com KPIs estratégicos de negócio'
            },
            {
                'factor_name': 'cost_effectiveness',
                'weight': 0.3,
                'score': cost_score,
                'description': 'Custo-efetividade baseado em duração estimada e recursos'
            }
        ]

        # Sugestões de mitigação
        mitigations = self._generate_mitigations(workflow_score, kpi_score, cost_score)

        logger.info(
            "Business evaluation completed",
            plan_id=cognitive_plan.get('plan_id'),
            confidence_score=confidence_score,
            risk_score=risk_score,
            recommendation=recommendation
        )

        return {
            'confidence_score': confidence_score,
            'risk_score': risk_score,
            'recommendation': recommendation,
            'reasoning_summary': reasoning_summary,
            'reasoning_factors': reasoning_factors,
            'mitigations': mitigations,
            'metadata': {
                'workflow_score': workflow_score,
                'kpi_score': kpi_score,
                'cost_score': cost_score,
                'domain': domain,
                'priority': priority,
                'num_tasks': len(tasks)
            }
        }

    def _analyze_workflow(self, tasks: List[Dict]) -> float:
        """
        Analisa eficiência do workflow.

        Heurísticas:
        - Número de tarefas (muito complexo = score baixo)
        - Dependências (muitas dependências = score baixo)
        - Paralelização (mais paralelismo = score alto)

        Args:
            tasks: Lista de tarefas do plano

        Returns:
            Score de eficiência (0.0-1.0)
        """
        num_tasks = len(tasks)

        if num_tasks == 0:
            logger.warning("No tasks in plan")
            return 0.5

        # Penalizar complexidade excessiva (ideal: 5-15 tarefas)
        if num_tasks <= 5:
            complexity_penalty = 0.8  # Muito simples
        elif num_tasks <= 15:
            complexity_penalty = 1.0  # Ideal
        elif num_tasks <= 25:
            complexity_penalty = 0.7  # Complexo
        else:
            complexity_penalty = 0.5  # Muito complexo

        # Calcular paralelização
        total_dependencies = sum(len(task.get('dependencies', [])) for task in tasks)
        max_possible_deps = num_tasks * (num_tasks - 1) / 2

        if max_possible_deps > 0:
            dependency_ratio = total_dependencies / max_possible_deps
            parallelization_score = 1.0 - (dependency_ratio * 0.7)  # Penaliza dependências
        else:
            parallelization_score = 1.0

        # Score final
        workflow_score = (complexity_penalty * 0.6 + parallelization_score * 0.4)

        logger.debug(
            "Workflow analysis",
            num_tasks=num_tasks,
            total_dependencies=total_dependencies,
            complexity_penalty=complexity_penalty,
            parallelization_score=parallelization_score,
            workflow_score=workflow_score
        )

        return max(0.0, min(1.0, workflow_score))

    def _analyze_kpis(self, cognitive_plan: Dict, context: Dict) -> float:
        """
        Analisa alinhamento com KPIs de negócio.

        MVP: Heurística baseada em prioridade
        Futuro: Consultar Knowledge Graph para KPIs históricos

        Args:
            cognitive_plan: Plano cognitivo
            context: Contexto adicional

        Returns:
            Score de alinhamento (0.0-1.0)
        """
        priority = cognitive_plan.get('original_priority', 'normal')

        priority_map = {
            'low': 0.3,
            'normal': 0.6,
            'high': 0.8,
            'critical': 1.0
        }

        kpi_score = priority_map.get(priority, 0.6)

        logger.debug(
            "KPI analysis",
            priority=priority,
            kpi_score=kpi_score
        )

        return kpi_score

    def _analyze_costs(self, tasks: List[Dict]) -> float:
        """
        Analisa custo-efetividade.

        Estima custos baseado em:
        - Duração estimada das tarefas
        - Recursos necessários
        - Complexidade

        Args:
            tasks: Lista de tarefas

        Returns:
            Score de custo-efetividade (0.0-1.0)
        """
        if not tasks:
            return 0.5

        # Estimar duração total
        total_duration_ms = sum(task.get('estimated_duration_ms', 0) for task in tasks)

        # Normalizar (assumindo max 1 hora = 3600000 ms como razoável)
        normalized_duration = min(1.0, total_duration_ms / 3600000.0)

        # Inverter (menor duração = melhor score)
        cost_score = 1.0 - (normalized_duration * 0.7)  # Penaliza 70% do excesso

        logger.debug(
            "Cost analysis",
            total_duration_ms=total_duration_ms,
            normalized_duration=normalized_duration,
            cost_score=cost_score
        )

        return max(0.0, min(1.0, cost_score))

    def _calculate_business_risk(
        self,
        cognitive_plan: Dict,
        workflow_score: float,
        kpi_score: float,
        cost_score: float
    ) -> float:
        """
        Calcula risco de negócio.

        Risco aumenta com:
        - Baixo alinhamento com KPIs
        - Alto custo
        - Workflow ineficiente

        Args:
            cognitive_plan: Plano cognitivo
            workflow_score: Score de workflow
            kpi_score: Score de KPI
            cost_score: Score de custo

        Returns:
            Score de risco (0.0-1.0)
        """
        # Média ponderada invertida
        weighted_avg = (workflow_score * 0.3 + kpi_score * 0.4 + cost_score * 0.3)
        risk_score = 1.0 - weighted_avg

        logger.debug(
            "Business risk calculation",
            workflow_score=workflow_score,
            kpi_score=kpi_score,
            cost_score=cost_score,
            risk_score=risk_score
        )

        return max(0.0, min(1.0, risk_score))

    def _determine_recommendation(self, confidence_score: float, risk_score: float) -> str:
        """
        Determina recomendação baseada em scores.

        Args:
            confidence_score: Score de confiança
            risk_score: Score de risco

        Returns:
            Recomendação (approve, reject, review_required, conditional)
        """
        if confidence_score >= 0.8 and risk_score < 0.3:
            return 'approve'
        elif confidence_score < 0.5 or risk_score > 0.7:
            return 'reject'
        elif risk_score > 0.5:
            return 'review_required'
        else:
            return 'conditional'

    def _generate_reasoning(
        self,
        workflow_score: float,
        kpi_score: float,
        cost_score: float,
        recommendation: str
    ) -> str:
        """Gera narrativa de justificativa."""
        return (
            f"Avaliação de negócios: "
            f"workflow efficiency={workflow_score:.2f}, "
            f"KPI alignment={kpi_score:.2f}, "
            f"cost effectiveness={cost_score:.2f}. "
            f"Recomendação: {recommendation}."
        )

    def _generate_mitigations(
        self,
        workflow_score: float,
        kpi_score: float,
        cost_score: float
    ) -> List[Dict]:
        """Gera sugestões de mitigação de riscos."""
        mitigations = []

        if workflow_score < 0.6:
            mitigations.append({
                'mitigation_id': 'optimize_workflow',
                'description': 'Simplificar workflow reduzindo número de tarefas ou aumentando paralelização',
                'priority': 'high',
                'estimated_impact': 0.3,
                'required_actions': [
                    'Revisar dependências entre tarefas',
                    'Identificar tarefas redundantes',
                    'Considerar execução paralela'
                ]
            })

        if kpi_score < 0.6:
            mitigations.append({
                'mitigation_id': 'align_kpis',
                'description': 'Alinhar plano com KPIs estratégicos de negócio',
                'priority': 'medium',
                'estimated_impact': 0.2,
                'required_actions': [
                    'Consultar stakeholders de negócio',
                    'Revisar objetivos estratégicos',
                    'Ajustar prioridades'
                ]
            })

        if cost_score < 0.6:
            mitigations.append({
                'mitigation_id': 'reduce_costs',
                'description': 'Otimizar custos reduzindo duração ou recursos necessários',
                'priority': 'medium',
                'estimated_impact': 0.25,
                'required_actions': [
                    'Revisar estimativas de duração',
                    'Considerar alternativas mais eficientes',
                    'Avaliar trade-offs de performance'
                ]
            })

        return mitigations
