"""
Implementação do Architecture Specialist.

Analisa planos cognitivos sob perspectiva de arquitetura de software:
- Design patterns e anti-patterns
- Princípios SOLID
- Acoplamento e coesão
- Separation of concerns
- Layering e modularity
"""

import sys
from typing import Dict, Any, List
import structlog

sys.path.insert(0, '/app/libraries/python')

from neural_hive_specialists import BaseSpecialist
from config import ArchitectureSpecialistConfig

logger = structlog.get_logger()


class ArchitectureSpecialist(BaseSpecialist):
    """Especialista em arquitetura de software, design patterns e princípios SOLID."""

    def _get_specialist_type(self) -> str:
        """Retorna tipo do especialista."""
        return "architecture"

    def _load_model(self) -> Any:
        """Carrega modelo de análise arquitetural do MLflow."""
        logger.info("Loading Architecture Specialist model")

        # Tentar carregar modelo ML do MLflow
        # Verificar se MLflow está disponível
        if self.mlflow_client is None or not getattr(self.mlflow_client, '_enabled', False):
            logger.warning("MLflow not available - using heuristic-based evaluation")
            return None

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
        Avalia plano sob perspectiva arquitetural.

        Args:
            cognitive_plan: Plano cognitivo a ser avaliado
            context: Contexto adicional da avaliação

        Returns:
            Dicionário com resultado da avaliação
        """
        logger.info(
            "Evaluating plan from architecture perspective",
            plan_id=cognitive_plan.get('plan_id'),
            domain=cognitive_plan.get('original_domain')
        )

        # Extrair informações do plano
        tasks = cognitive_plan.get('tasks', [])
        domain = cognitive_plan.get('original_domain')
        priority = cognitive_plan.get('original_priority', 'normal')

        # Análise de design patterns
        design_pattern_score = self._analyze_design_patterns(tasks)

        # Análise SOLID
        solid_score = self._analyze_solid_principles(tasks, cognitive_plan)

        # Análise de acoplamento e coesão
        coupling_cohesion_score = self._analyze_coupling_cohesion(tasks)

        # Análise de separação de concerns
        separation_score = self._analyze_separation_of_concerns(tasks)

        # Análise de layering e modularidade
        modularity_score = self._analyze_modularity(tasks)

        # Calcular scores agregados
        confidence_score = (
            design_pattern_score * 0.25 +
            solid_score * 0.25 +
            coupling_cohesion_score * 0.20 +
            separation_score * 0.15 +
            modularity_score * 0.15
        )

        # Calcular risco arquitetural
        risk_score = self._calculate_architecture_risk(
            cognitive_plan,
            design_pattern_score,
            solid_score,
            coupling_cohesion_score,
            separation_score,
            modularity_score
        )

        # Determinar recomendação
        recommendation = self._determine_recommendation(confidence_score, risk_score)

        # Gerar justificativa
        reasoning_summary = self._generate_reasoning(
            design_pattern_score,
            solid_score,
            coupling_cohesion_score,
            separation_score,
            modularity_score,
            recommendation
        )

        # Fatores de raciocínio estruturados
        reasoning_factors = [
            {
                'factor_name': 'design_patterns',
                'weight': 0.25,
                'score': design_pattern_score,
                'description': 'Uso apropriado de design patterns e evitação de anti-patterns'
            },
            {
                'factor_name': 'solid_principles',
                'weight': 0.25,
                'score': solid_score,
                'description': 'Aderência aos princípios SOLID de design orientado a objetos'
            },
            {
                'factor_name': 'coupling_cohesion',
                'weight': 0.20,
                'score': coupling_cohesion_score,
                'description': 'Baixo acoplamento entre módulos e alta coesão interna'
            },
            {
                'factor_name': 'separation_of_concerns',
                'weight': 0.15,
                'score': separation_score,
                'description': 'Separação clara de responsabilidades e concerns'
            },
            {
                'factor_name': 'modularity',
                'weight': 0.15,
                'score': modularity_score,
                'description': 'Modularidade e organização em camadas bem definidas'
            }
        ]

        # Sugestões de mitigação
        mitigations = self._generate_mitigations(
            design_pattern_score,
            solid_score,
            coupling_cohesion_score,
            separation_score,
            modularity_score
        )

        logger.info(
            "Architecture evaluation completed",
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
                'design_pattern_score': design_pattern_score,
                'solid_score': solid_score,
                'coupling_cohesion_score': coupling_cohesion_score,
                'separation_score': separation_score,
                'modularity_score': modularity_score,
                'domain': domain,
                'priority': priority,
                'num_tasks': len(tasks)
            }
        }

    def _analyze_design_patterns(self, tasks: List[Dict]) -> float:
        """
        Analisa uso apropriado de design patterns.

        Heurísticas:
        - Presença de palavras-chave indicando patterns (factory, singleton, observer, etc.)
        - Ausência de anti-patterns (god object, spaghetti code, etc.)
        - Complexidade adequada para o problema

        Args:
            tasks: Lista de tarefas do plano

        Returns:
            Score de design patterns (0.0-1.0)
        """
        if not tasks:
            return 0.5

        # Palavras-chave positivas (design patterns)
        positive_keywords = [
            'factory', 'builder', 'singleton', 'observer', 'strategy',
            'adapter', 'decorator', 'facade', 'proxy', 'composite',
            'interface', 'abstraction', 'dependency injection', 'repository'
        ]

        # Palavras-chave negativas (anti-patterns)
        negative_keywords = [
            'god object', 'spaghetti', 'tight coupling', 'hardcoded',
            'global state', 'magic numbers', 'copy-paste'
        ]

        positive_count = 0
        negative_count = 0

        for task in tasks:
            task_description = task.get('description', '').lower()

            for keyword in positive_keywords:
                if keyword in task_description:
                    positive_count += 1

            for keyword in negative_keywords:
                if keyword in task_description:
                    negative_count += 1

        # Calcular score
        total_indicators = positive_count + negative_count
        if total_indicators == 0:
            score = 0.6  # Neutro
        else:
            score = positive_count / total_indicators

        logger.debug(
            "Design patterns analysis",
            positive_count=positive_count,
            negative_count=negative_count,
            score=score
        )

        return max(0.0, min(1.0, score))

    def _analyze_solid_principles(self, tasks: List[Dict], cognitive_plan: Dict) -> float:
        """
        Analisa aderência aos princípios SOLID.

        SOLID:
        - S: Single Responsibility Principle
        - O: Open/Closed Principle
        - L: Liskov Substitution Principle
        - I: Interface Segregation Principle
        - D: Dependency Inversion Principle

        Args:
            tasks: Lista de tarefas
            cognitive_plan: Plano cognitivo completo

        Returns:
            Score SOLID (0.0-1.0)
        """
        if not tasks:
            return 0.5

        # Palavras-chave indicando boa aderência SOLID
        solid_keywords = [
            'single responsibility', 'srp',
            'open closed', 'ocp', 'extensible',
            'liskov', 'lsp', 'substitution',
            'interface segregation', 'isp',
            'dependency inversion', 'dip', 'dependency injection',
            'abstraction', 'interface', 'separation'
        ]

        # Palavras-chave indicando violações SOLID
        violation_keywords = [
            'god class', 'multiple responsibilities',
            'tight coupling', 'hardcoded dependencies',
            'fat interface', 'concrete dependency'
        ]

        solid_count = 0
        violation_count = 0

        for task in tasks:
            task_description = task.get('description', '').lower()

            for keyword in solid_keywords:
                if keyword in task_description:
                    solid_count += 1

            for keyword in violation_keywords:
                if keyword in task_description:
                    violation_count += 1

        # Analisar número de responsabilidades por módulo
        # (heurística baseada em tarefas por componente)
        num_tasks = len(tasks)
        avg_responsibilities = num_tasks / max(1, len(set(t.get('agent_id', '') for t in tasks)))

        # Penalizar múltiplas responsabilidades
        if avg_responsibilities > 5:
            responsibility_penalty = 0.6
        elif avg_responsibilities > 3:
            responsibility_penalty = 0.8
        else:
            responsibility_penalty = 1.0

        # Calcular score
        total_indicators = solid_count + violation_count
        if total_indicators == 0:
            indicator_score = 0.6
        else:
            indicator_score = solid_count / total_indicators

        solid_score = (indicator_score * 0.7 + responsibility_penalty * 0.3)

        logger.debug(
            "SOLID analysis",
            solid_count=solid_count,
            violation_count=violation_count,
            avg_responsibilities=avg_responsibilities,
            solid_score=solid_score
        )

        return max(0.0, min(1.0, solid_score))

    def _analyze_coupling_cohesion(self, tasks: List[Dict]) -> float:
        """
        Analisa acoplamento e coesão.

        Objetivo: Baixo acoplamento (low coupling) e alta coesão (high cohesion)

        Args:
            tasks: Lista de tarefas

        Returns:
            Score de coupling/cohesion (0.0-1.0)
        """
        if not tasks:
            return 0.5

        num_tasks = len(tasks)

        # Calcular acoplamento (baseado em dependências)
        total_dependencies = sum(len(task.get('dependencies', [])) for task in tasks)
        max_possible_deps = num_tasks * (num_tasks - 1) / 2

        if max_possible_deps > 0:
            coupling_ratio = total_dependencies / max_possible_deps
            low_coupling_score = 1.0 - coupling_ratio  # Inverter: menos dependências = melhor
        else:
            coupling_ratio = 0.0  # Sem dependências possíveis
            low_coupling_score = 1.0

        # Penalizar acoplamento alto
        if coupling_ratio > self.config.coupling_threshold_high:
            low_coupling_score *= 0.5

        # Analisar coesão (tarefas relacionadas agrupadas)
        # Heurística: tarefas do mesmo agente tendem a ser coesas
        agent_groups = {}
        for task in tasks:
            agent_id = task.get('agent_id', 'unknown')
            if agent_id not in agent_groups:
                agent_groups[agent_id] = []
            agent_groups[agent_id].append(task)

        # Coesão alta = poucos grupos com muitas tarefas cada
        num_groups = len(agent_groups)
        if num_groups > 0:
            avg_tasks_per_group = num_tasks / num_groups
            if avg_tasks_per_group >= 3:
                cohesion_score = 1.0
            elif avg_tasks_per_group >= 2:
                cohesion_score = 0.8
            else:

        else:
            cohesion_score = 0.5

        # Score final: média ponderada
        coupling_cohesion_score = (low_coupling_score * 0.6 + cohesion_score * 0.4)

        logger.debug(
            "Coupling/Cohesion analysis",
            coupling_ratio=coupling_ratio,
            low_coupling_score=low_coupling_score,
            num_groups=num_groups,
            cohesion_score=cohesion_score,
            coupling_cohesion_score=coupling_cohesion_score
        )

        return max(0.0, min(1.0, coupling_cohesion_score))

    def _analyze_separation_of_concerns(self, tasks: List[Dict]) -> float:
        """
        Analisa separação de concerns.

        Verifica se diferentes aspectos (UI, lógica, dados, etc.) estão separados.

        Args:
            tasks: Lista de tarefas

        Returns:
            Score de separação (0.0-1.0)
        """
        if not tasks:
            return 0.5

        # Identificar concerns diferentes
        concerns = {
            'ui': ['ui', 'interface', 'view', 'presentation', 'frontend'],
            'business_logic': ['business', 'logic', 'service', 'domain'],
            'data': ['data', 'database', 'storage', 'persistence', 'repository'],
            'infrastructure': ['infrastructure', 'config', 'deployment', 'networking']
        }

        task_concerns = []
        for task in tasks:
            task_description = task.get('description', '').lower()
            identified_concerns = set()

            for concern_type, keywords in concerns.items():
                for keyword in keywords:
                    if keyword in task_description:
                        identified_concerns.add(concern_type)

            task_concerns.append(identified_concerns)

        # Verificar se concerns estão misturados (bad) ou separados (good)
        mixed_concerns_count = sum(1 for tc in task_concerns if len(tc) > 1)
        total_tasks_with_concerns = sum(1 for tc in task_concerns if len(tc) > 0)

        if total_tasks_with_concerns > 0:
            separation_score = 1.0 - (mixed_concerns_count / total_tasks_with_concerns)
        else:
            separation_score = 0.6  # Neutro se não detectamos concerns

        logger.debug(
            "Separation of concerns analysis",
            mixed_concerns_count=mixed_concerns_count,
            total_tasks_with_concerns=total_tasks_with_concerns,
            separation_score=separation_score
        )

        return max(0.0, min(1.0, separation_score))

    def _analyze_modularity(self, tasks: List[Dict]) -> float:
        """
        Analisa modularidade e organização em camadas.

        Verifica se o sistema está organizado em módulos bem definidos e camadas.

        Args:
            tasks: Lista de tarefas

        Returns:
            Score de modularidade (0.0-1.0)
        """
        if not tasks:
            return 0.5

        # Palavras-chave indicando boa modularidade
        modularity_keywords = [
            'module', 'component', 'layer', 'package',
            'encapsulation', 'namespace', 'boundary',
            'api', 'contract', 'interface'
        ]

        modularity_count = 0
        for task in tasks:
            task_description = task.get('description', '').lower()
            for keyword in modularity_keywords:
                if keyword in task_description:
                    modularity_count += 1
                    break  # Contar apenas uma vez por tarefa

        # Normalizar pelo número de tarefas
        modularity_ratio = modularity_count / len(tasks)

        # Score baseado em proporção de tarefas modulares
        if modularity_ratio >= 0.7:
            modularity_score = 1.0
        elif modularity_ratio >= 0.5:
            modularity_score = 0.8
        elif modularity_ratio >= 0.3:
            modularity_score = 0.6
        else:
            modularity_score = 0.4

        logger.debug(
            "Modularity analysis",
            modularity_count=modularity_count,
            total_tasks=len(tasks),
            modularity_ratio=modularity_ratio,
            modularity_score=modularity_score
        )

        return modularity_score

    def _calculate_architecture_risk(
        self,
        cognitive_plan: Dict,
        design_pattern_score: float,
        solid_score: float,
        coupling_cohesion_score: float,
        separation_score: float,
        modularity_score: float
    ) -> float:
        """
        Calcula risco arquitetural.

        Risco aumenta com:
        - Ausência de design patterns apropriados
        - Violações de princípios SOLID
        - Alto acoplamento ou baixa coesão
        - Mistura de concerns
        - Baixa modularidade

        Args:
            cognitive_plan: Plano cognitivo
            design_pattern_score: Score de design patterns
            solid_score: Score SOLID
            coupling_cohesion_score: Score de coupling/cohesion
            separation_score: Score de separação
            modularity_score: Score de modularidade

        Returns:
            Score de risco (0.0-1.0)
        """
        # Média ponderada invertida
        weighted_avg = (
            design_pattern_score * 0.25 +
            solid_score * 0.25 +
            coupling_cohesion_score * 0.20 +
            separation_score * 0.15 +
            modularity_score * 0.15
        )
        risk_score = 1.0 - weighted_avg

        logger.debug(
            "Architecture risk calculation",
            design_pattern_score=design_pattern_score,
            solid_score=solid_score,
            coupling_cohesion_score=coupling_cohesion_score,
            separation_score=separation_score,
            modularity_score=modularity_score,
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
        design_pattern_score: float,
        solid_score: float,
        coupling_cohesion_score: float,
        separation_score: float,
        modularity_score: float,
        recommendation: str
    ) -> str:
        """Gera narrativa de justificativa."""
        return (
            f"Avaliação arquitetural: "
            f"design patterns={design_pattern_score:.2f}, "
            f"SOLID={solid_score:.2f}, "
            f"coupling/cohesion={coupling_cohesion_score:.2f}, "
            f"separation of concerns={separation_score:.2f}, "
            f"modularity={modularity_score:.2f}. "
            f"Recomendação: {recommendation}."
        )

    def _generate_mitigations(
        self,
        design_pattern_score: float,
        solid_score: float,
        coupling_cohesion_score: float,
        separation_score: float,
        modularity_score: float
    ) -> List[Dict]:
        """Gera sugestões de mitigação de riscos arquiteturais."""
        mitigations = []

        if design_pattern_score < 0.6:
            mitigations.append({
                'mitigation_type': 'apply_design_patterns',
                'description': 'Aplicar design patterns apropriados e evitar anti-patterns',
                'priority': 'high',
                'estimated_effort': 'medium'
            })

        if solid_score < 0.6:
            mitigations.append({
                'mitigation_type': 'enforce_solid',
                'description': 'Melhorar aderência aos princípios SOLID',
                'priority': 'high',
                'estimated_effort': 'high'
            })

        if coupling_cohesion_score < 0.6:
            mitigations.append({
                'mitigation_type': 'reduce_coupling',
                'description': 'Reduzir acoplamento e aumentar coesão',
                'priority': 'medium',
                'estimated_effort': 'medium'
            })

        if separation_score < 0.6:
            mitigations.append({
                'mitigation_type': 'separate_concerns',
                'description': 'Separar concerns e responsabilidades',
                'priority': 'medium',
                'estimated_effort': 'medium'
            })

        if modularity_score < 0.6:
            mitigations.append({
                'mitigation_type': 'improve_modularity',
                'description': 'Melhorar modularidade e organização em camadas',
                'priority': 'medium',
                'estimated_effort': 'medium'
            })

        return mitigations
