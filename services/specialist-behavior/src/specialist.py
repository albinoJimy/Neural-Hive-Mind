"""
Implementação do Behavior Specialist.

Analisa planos cognitivos sob perspectiva comportamental:
- UX patterns e usabilidade
- Acessibilidade (WCAG)
- Experiência do usuário
- Tempos de resposta
- Custo de interação
"""

import sys
from typing import Dict, Any, List
import structlog

sys.path.insert(0, '/app/libraries/python')

from neural_hive_specialists import BaseSpecialist
from config import BehaviorSpecialistConfig

logger = structlog.get_logger()


class BehaviorSpecialist(BaseSpecialist):
    """Especialista em análise comportamental, UX e acessibilidade."""

    def _get_specialist_type(self) -> str:
        """Retorna tipo do especialista."""
        return "behavior"

    def _load_model(self) -> Any:
        """Carrega modelo de análise comportamental do MLflow."""
        logger.info("Loading Behavior Specialist model")

        # Verificar se MLflow está disponível
        if self.mlflow_client is None or not getattr(self.mlflow_client, '_enabled', False):
            logger.warning("MLflow not available - using heuristic-based evaluation")
            return None

        # Tentar carregar modelo ML do MLflow
        try:
            model = self.mlflow_client.load_model(
                self.config.mlflow_model_name,
                self.config.mlflow_model_stage
            )

            logger.info(
                "ML model loaded successfully",
                model_name=self.config.mlflow_model_name,
                stage=self.config.mlflow_model_stage
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
        Avalia plano sob perspectiva comportamental e UX.

        Args:
            cognitive_plan: Plano cognitivo a ser avaliado
            context: Contexto adicional da avaliação

        Returns:
            Dicionário com resultado da avaliação
        """
        logger.info(
            "Evaluating plan from behavioral perspective",
            plan_id=cognitive_plan.get('plan_id'),
            domain=cognitive_plan.get('original_domain')
        )

        # Extrair informações do plano
        tasks = cognitive_plan.get('tasks', [])
        domain = cognitive_plan.get('original_domain')
        priority = cognitive_plan.get('original_priority', 'normal')

        # Análise de usabilidade
        usability_score = self._analyze_usability(tasks, cognitive_plan)

        # Análise de acessibilidade
        accessibility_score = self._analyze_accessibility(cognitive_plan, context)

        # Análise de tempo de resposta
        response_time_score = self._analyze_response_time(tasks)

        # Análise de custo de interação
        interaction_cost_score = self._analyze_interaction_cost(tasks)

        # Calcular scores agregados
        confidence_score = (
            usability_score * 0.35 +
            accessibility_score * 0.25 +
            response_time_score * 0.25 +
            interaction_cost_score * 0.15
        )

        # Calcular risco comportamental
        risk_score = self._calculate_behavioral_risk(
            cognitive_plan,
            usability_score,
            accessibility_score,
            response_time_score,
            interaction_cost_score
        )

        # Determinar recomendação
        recommendation = self._determine_recommendation(confidence_score, risk_score)

        # Gerar justificativa
        reasoning_summary = self._generate_reasoning(
            usability_score,
            accessibility_score,
            response_time_score,
            interaction_cost_score,
            recommendation
        )

        # Fatores de raciocínio estruturados
        reasoning_factors = [
            {
                'factor_name': 'usability',
                'weight': 0.35,
                'score': usability_score,
                'description': 'Facilidade de uso e intuitividade da interface proposta'
            },
            {
                'factor_name': 'accessibility',
                'weight': 0.25,
                'score': accessibility_score,
                'description': 'Conformidade com WCAG e acessibilidade para todos os usuários'
            },
            {
                'factor_name': 'response_time',
                'weight': 0.25,
                'score': response_time_score,
                'description': 'Tempos de resposta percebidos pelo usuário'
            },
            {
                'factor_name': 'interaction_cost',
                'weight': 0.15,
                'score': interaction_cost_score,
                'description': 'Esforço cognitivo e físico requerido do usuário'
            }
        ]

        # Sugestões de mitigação
        mitigations = self._generate_mitigations(
            usability_score,
            accessibility_score,
            response_time_score,
            interaction_cost_score
        )

        logger.info(
            "Behavioral evaluation completed",
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
                'usability_score': usability_score,
                'accessibility_score': accessibility_score,
                'response_time_score': response_time_score,
                'interaction_cost_score': interaction_cost_score,
                'domain': domain,
                'priority': priority,
                'num_tasks': len(tasks)
            }
        }

    def _analyze_usability(self, tasks: List[Dict], cognitive_plan: Dict) -> float:
        """
        Analisa usabilidade da interface/fluxo.

        Heurísticas:
        - Número de passos para completar tarefa (menos = melhor)
        - Clareza de feedback ao usuário
        - Prevenção de erros
        - Consistência

        Args:
            tasks: Lista de tarefas do plano
            cognitive_plan: Plano cognitivo completo

        Returns:
            Score de usabilidade (0.0-1.0)
        """
        num_tasks = len(tasks)

        if num_tasks == 0:
            logger.warning("No tasks in plan")
            return 0.5

        # Penalizar muitos passos (ideal: 3-7 passos para usuário)
        if num_tasks <= 3:
            steps_score = 0.9
        elif num_tasks <= 7:
            steps_score = 1.0
        elif num_tasks <= 12:
            steps_score = 0.7
        else:
            steps_score = 0.5  # Muito complexo para usuário

        # Avaliar feedback (estimativa baseada em duração)
        feedback_score = self._estimate_feedback_quality(tasks)

        # Score final
        usability_score = (steps_score * 0.6 + feedback_score * 0.4)

        logger.debug(
            "Usability analysis",
            num_tasks=num_tasks,
            steps_score=steps_score,
            feedback_score=feedback_score,
            usability_score=usability_score
        )

        return max(0.0, min(1.0, usability_score))

    def _estimate_feedback_quality(self, tasks: List[Dict]) -> float:
        """Estima qualidade do feedback baseado em tempos de resposta."""
        if not tasks:
            return 0.5

        # Assumir que tarefas rápidas fornecem melhor feedback
        avg_duration = sum(task.get('estimated_duration_ms', 0) for task in tasks) / len(tasks)

        # < 100ms = excelente, < 300ms = bom, < 1000ms = aceitável, > 1000ms = ruim
        if avg_duration < 100:
            return 1.0
        elif avg_duration < 300:
            return 0.9
        elif avg_duration < 1000:
            return 0.7
        else:
            return 0.5

    def _analyze_accessibility(self, cognitive_plan: Dict, context: Dict) -> float:
        """
        Analisa conformidade com acessibilidade (WCAG).

        MVP: Heurísticas básicas
        Futuro: Análise detalhada de WCAG 2.1 Level AA

        Args:
            cognitive_plan: Plano cognitivo
            context: Contexto adicional

        Returns:
            Score de acessibilidade (0.0-1.0)
        """
        # Verificar se há menção a acessibilidade no contexto
        context_mentions_a11y = any(
            keyword in str(context).lower()
            for keyword in ['accessibility', 'wcag', 'aria', 'screen reader', 'keyboard']
        )

        # Verificar domínio do plano
        domain = cognitive_plan.get('original_domain', '')
        ui_related = any(
            keyword in domain.lower()
            for keyword in ['ui', 'interface', 'frontend', 'view', 'form']
        )

        # Score base
        if context_mentions_a11y:
            accessibility_score = 0.9  # Boa consideração
        elif ui_related:
            accessibility_score = 0.6  # Deveria considerar
        else:
            accessibility_score = 0.7  # Neutro para domínios não-UI

        logger.debug(
            "Accessibility analysis",
            context_mentions_a11y=context_mentions_a11y,
            ui_related=ui_related,
            accessibility_score=accessibility_score
        )

        return accessibility_score

    def _analyze_response_time(self, tasks: List[Dict]) -> float:
        """
        Analisa tempos de resposta percebidos.

        Baseado em limites de percepção humana:
        - < 100ms: instantâneo
        - < 300ms: rápido
        - < 1000ms: aceitável
        - > 1000ms: lento

        Args:
            tasks: Lista de tarefas

        Returns:
            Score de tempo de resposta (0.0-1.0)
        """
        if not tasks:
            return 0.5

        # Calcular tempo máximo de resposta percebido
        max_duration = max(task.get('estimated_duration_ms', 0) for task in tasks)

        # Normalizar baseado em thresholds de percepção
        if max_duration < 100:
            response_time_score = 1.0
        elif max_duration < 300:
            response_time_score = 0.9
        elif max_duration < 1000:
            response_time_score = 0.7
        elif max_duration < 3000:
            response_time_score = 0.5
        else:
            response_time_score = 0.3

        logger.debug(
            "Response time analysis",
            max_duration_ms=max_duration,
            response_time_score=response_time_score
        )

        return response_time_score

    def _analyze_interaction_cost(self, tasks: List[Dict]) -> float:
        """
        Analisa custo de interação (esforço cognitivo e físico).

        Baseado em:
        - Número de interações
        - Complexidade de cada interação
        - Mudanças de contexto

        Args:
            tasks: Lista de tarefas

        Returns:
            Score de custo de interação (0.0-1.0)
        """
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        # Calcular custo baseado em número de tarefas
        # Assumir que cada tarefa requer pelo menos uma interação do usuário
        if num_tasks <= 3:
            interaction_cost = 0.2  # Baixo
        elif num_tasks <= 7:
            interaction_cost = 0.4  # Médio
        elif num_tasks <= 12:
            interaction_cost = 0.7  # Alto
        else:
            interaction_cost = 0.9  # Muito alto

        # Inverter (menor custo = melhor score)
        interaction_cost_score = 1.0 - interaction_cost

        logger.debug(
            "Interaction cost analysis",
            num_tasks=num_tasks,
            interaction_cost=interaction_cost,
            interaction_cost_score=interaction_cost_score
        )

        return max(0.0, min(1.0, interaction_cost_score))

    def _calculate_behavioral_risk(
        self,
        cognitive_plan: Dict,
        usability_score: float,
        accessibility_score: float,
        response_time_score: float,
        interaction_cost_score: float
    ) -> float:
        """
        Calcula risco comportamental.

        Risco aumenta com:
        - Baixa usabilidade
        - Problemas de acessibilidade
        - Tempos de resposta lentos
        - Alto custo de interação

        Args:
            cognitive_plan: Plano cognitivo
            usability_score: Score de usabilidade
            accessibility_score: Score de acessibilidade
            response_time_score: Score de tempo de resposta
            interaction_cost_score: Score de custo de interação

        Returns:
            Score de risco (0.0-1.0)
        """
        # Média ponderada invertida
        weighted_avg = (
            usability_score * 0.35 +
            accessibility_score * 0.25 +
            response_time_score * 0.25 +
            interaction_cost_score * 0.15
        )
        risk_score = 1.0 - weighted_avg

        logger.debug(
            "Behavioral risk calculation",
            usability_score=usability_score,
            accessibility_score=accessibility_score,
            response_time_score=response_time_score,
            interaction_cost_score=interaction_cost_score,
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

    def _generate_mitigations(
        self,
        usability_score: float,
        accessibility_score: float,
        response_time_score: float,
        interaction_cost_score: float
    ) -> List[Dict]:
        """Gera sugestões de mitigação de riscos."""
        mitigations = []

        if usability_score < 0.6:
            mitigations.append({
                'mitigation_type': 'improve_usability',
                'description': 'Melhorar usabilidade simplificando fluxo e fornecendo feedback claro',
                'priority': 'high',
                'estimated_effort': 'medium'
            })

        if accessibility_score < 0.6:
            mitigations.append({
                'mitigation_type': 'ensure_accessibility',
                'description': 'Garantir acessibilidade conforme WCAG 2.1 Level AA',
                'priority': 'high',
                'estimated_effort': 'medium'
            })

        if response_time_score < 0.6:
            mitigations.append({
                'mitigation_type': 'optimize_response_time',
                'description': 'Otimizar tempos de resposta para melhor percepção do usuário',
                'priority': 'medium',
                'estimated_effort': 'low'
            })

        if interaction_cost_score < 0.6:
            mitigations.append({
                'mitigation_type': 'reduce_interaction_cost',
                'description': 'Reduzir esforço cognitivo e físico do usuário',
                'priority': 'medium',
                'estimated_effort': 'low'
            })

        return mitigations
