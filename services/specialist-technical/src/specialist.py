"""
Implementação do Technical Specialist.

Analisa planos cognitivos sob perspectiva técnica:
- Análise de segurança
- Padrões de arquitetura
- Performance e otimização
- Qualidade de código
- Débito técnico
"""

import sys
from typing import Dict, Any, List
import structlog

sys.path.insert(0, '/app/libraries/python')

from neural_hive_specialists import BaseSpecialist
from config import TechnicalSpecialistConfig

logger = structlog.get_logger()


class TechnicalSpecialist(BaseSpecialist):
    """Especialista em análise técnica, segurança, arquitetura e performance."""

    def _get_specialist_type(self) -> str:
        """Retorna tipo do especialista."""
        return "technical"

    def _load_model(self) -> Any:
        """Carrega modelo de análise técnica do MLflow."""
        logger.info("Loading Technical Specialist model")

        # Verificar se MLflow está disponível
        mlflow_enabled = False
        if self.mlflow_client is None:
            logger.warning("MLflow not available - using heuristic-based evaluation")
            return None
        if hasattr(self.mlflow_client, "is_enabled"):
            mlflow_enabled = self.mlflow_client.is_enabled()
        else:
            mlflow_enabled = getattr(self.mlflow_client, "_enabled", False)

        if not mlflow_enabled:
            logger.warning("MLflow not available - using heuristic-based evaluation")
            return None

        try:
            # Carregar modelo com fallback para cache expirado
            model = self.mlflow_client.load_model_with_fallback(
                self.config.mlflow_model_name,
                self.config.mlflow_model_stage
            )

            if model:
                metadata = self.mlflow_client.get_model_metadata(
                    self.config.mlflow_model_name,
                    self.config.mlflow_model_stage
                )

                if not metadata:
                    logger.warning(
                        "No model metadata found for configured stage - using heuristics",
                        model_name=self.config.mlflow_model_name,
                        stage=self.config.mlflow_model_stage
                    )
                    return None

                logger.info(
                    "ML model loaded successfully",
                    model_name=self.config.mlflow_model_name,
                    stage=self.config.mlflow_model_stage,
                    version=metadata.get('version', 'unknown'),
                    stage_match=metadata.get('stage', self.config.mlflow_model_stage) == self.config.mlflow_model_stage
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
        Avalia plano sob perspectiva técnica.

        Args:
            cognitive_plan: Plano cognitivo a ser avaliado
            context: Contexto adicional da avaliação

        Returns:
            Dicionário com resultado da avaliação
        """
        logger.info(
            "Evaluating plan from technical perspective",
            plan_id=cognitive_plan.get('plan_id'),
            domain=cognitive_plan.get('original_domain')
        )

        # Extrair informações do plano
        tasks = cognitive_plan.get('tasks', [])
        domain = cognitive_plan.get('original_domain')
        priority = cognitive_plan.get('original_priority', 'normal')

        # Análise de segurança
        security_score = self._analyze_security(tasks, cognitive_plan)

        # Análise de arquitetura
        architecture_score = self._analyze_architecture(tasks, cognitive_plan)

        # Análise de performance
        performance_score = self._analyze_performance(tasks)

        # Análise de qualidade de código
        code_quality_score = self._analyze_code_quality(tasks)

        # Calcular scores agregados
        confidence_score = (
            security_score * 0.3 +
            architecture_score * 0.3 +
            performance_score * 0.2 +
            code_quality_score * 0.2
        )

        # Calcular risco técnico
        risk_score = self._calculate_technical_risk(
            cognitive_plan,
            security_score,
            architecture_score,
            performance_score,
            code_quality_score
        )

        # Determinar recomendação
        recommendation = self._determine_recommendation(confidence_score, risk_score)

        # Gerar justificativa
        reasoning_summary = self._generate_reasoning(
            security_score,
            architecture_score,
            performance_score,
            code_quality_score,
            recommendation
        )

        # Fatores de raciocínio estruturados
        reasoning_factors = [
            {
                'factor_name': 'security_analysis',
                'weight': 0.3,
                'score': security_score,
                'description': 'Análise de vulnerabilidades e práticas de segurança'
            },
            {
                'factor_name': 'architecture_patterns',
                'weight': 0.3,
                'score': architecture_score,
                'description': 'Conformidade com padrões arquiteturais e design'
            },
            {
                'factor_name': 'performance_optimization',
                'weight': 0.2,
                'score': performance_score,
                'description': 'Otimização de performance e eficiência de recursos'
            },
            {
                'factor_name': 'code_quality',
                'weight': 0.2,
                'score': code_quality_score,
                'description': 'Qualidade e manutenibilidade do código'
            }
        ]

        # Sugestões de mitigação
        mitigations = self._generate_mitigations(
            security_score,
            architecture_score,
            performance_score,
            code_quality_score
        )

        logger.info(
            "Technical evaluation completed",
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
                'security_score': security_score,
                'architecture_score': architecture_score,
                'performance_score': performance_score,
                'code_quality_score': code_quality_score,
                'domain': domain,
                'priority': priority,
                'num_tasks': len(tasks)
            }
        }

    def _analyze_security(self, tasks: List[Dict], cognitive_plan: Dict) -> float:
        """
        Analisa aspectos de segurança do plano.

        Heurísticas:
        - Presença de validação de entrada
        - Uso de autenticação/autorização
        - Tratamento de dados sensíveis
        - Exposição de APIs/endpoints

        Args:
            tasks: Lista de tarefas do plano
            cognitive_plan: Plano cognitivo completo

        Returns:
            Score de segurança (0.0-1.0)
        """
        if not tasks:
            return 0.5

        security_indicators = 0
        total_checks = 0

        # Verificar menções de segurança nas descrições
        security_keywords = [
            'auth', 'security', 'validate', 'sanitize', 'encrypt',
            'permission', 'access control', 'token', 'credential'
        ]

        for task in tasks:
            task_desc = task.get('description', '').lower()

            # Check 1: Presença de práticas de segurança
            total_checks += 1
            if any(keyword in task_desc for keyword in security_keywords):
                security_indicators += 1

        # Check 2: Planos que lidam com dados devem ter validação
        domain = cognitive_plan.get('original_domain', '')
        if 'data' in domain or 'api' in domain:
            total_checks += 1
            if any('validat' in task.get('description', '').lower() for task in tasks):
                security_indicators += 1

        # Calcular score
        if total_checks > 0:
            security_score = security_indicators / total_checks
        else:
            security_score = 0.5  # Neutro se não há verificações

        logger.debug(
            "Security analysis",
            security_indicators=security_indicators,
            total_checks=total_checks,
            security_score=security_score
        )

        return max(0.0, min(1.0, security_score))

    def _analyze_architecture(self, tasks: List[Dict], cognitive_plan: Dict) -> float:
        """
        Analisa padrões arquiteturais e design.

        Heurísticas:
        - Separação de responsabilidades
        - Modularidade
        - Acoplamento
        - Princípios SOLID

        Args:
            tasks: Lista de tarefas
            cognitive_plan: Plano cognitivo completo

        Returns:
            Score de arquitetura (0.0-1.0)
        """
        if not tasks:
            return 0.5

        num_tasks = len(tasks)

        # Check 1: Modularidade (tarefas com responsabilidades claras)
        # Penalizar tarefas muito grandes ou vagas
        clear_tasks = sum(
            1 for task in tasks
            if len(task.get('description', '').split()) > 5
        )
        modularity_score = clear_tasks / num_tasks if num_tasks > 0 else 0.5

        # Check 2: Baixo acoplamento (poucas dependências)
        total_dependencies = sum(len(task.get('dependencies', [])) for task in tasks)
        avg_dependencies = total_dependencies / num_tasks if num_tasks > 0 else 0

        # Ideal: até 2 dependências por tarefa
        coupling_score = max(0.0, 1.0 - (avg_dependencies / 5.0))

        # Check 3: Presença de padrões arquiteturais
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

        # Score agregado
        architecture_score = (
            modularity_score * 0.4 +
            coupling_score * 0.3 +
            pattern_score * 0.3
        )

        logger.debug(
            "Architecture analysis",
            num_tasks=num_tasks,
            modularity_score=modularity_score,
            coupling_score=coupling_score,
            pattern_score=pattern_score,
            architecture_score=architecture_score
        )

        return max(0.0, min(1.0, architecture_score))

    def _analyze_performance(self, tasks: List[Dict]) -> float:
        """
        Analisa aspectos de performance.

        Heurísticas:
        - Uso de cache
        - Otimização de queries
        - Processamento assíncrono
        - Uso de índices

        Args:
            tasks: Lista de tarefas

        Returns:
            Score de performance (0.0-1.0)
        """
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

        # Ajustar baseado em duração estimada
        total_duration_ms = sum(task.get('estimated_duration_ms', 0) for task in tasks)
        if total_duration_ms > 0:
            # Penalizar planos muito lentos
            normalized_duration = min(1.0, total_duration_ms / 3600000.0)  # 1 hora
            duration_penalty = 1.0 - (normalized_duration * 0.3)
            performance_score = (performance_score + duration_penalty) / 2.0

        logger.debug(
            "Performance analysis",
            performance_indicators=performance_indicators,
            total_checks=total_checks,
            performance_score=performance_score
        )

        return max(0.0, min(1.0, performance_score))

    def _analyze_code_quality(self, tasks: List[Dict]) -> float:
        """
        Analisa qualidade de código esperada.

        Heurísticas:
        - Testes mencionados
        - Documentação
        - Tratamento de erros
        - Logging

        Args:
            tasks: Lista de tarefas

        Returns:
            Score de qualidade (0.0-1.0)
        """
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

        # Calcular score agregado
        num_tasks = len(tasks)
        scores = [
            min(1.0, quality_indicators['tests'] / max(1, num_tasks * 0.3)),
            min(1.0, quality_indicators['documentation'] / max(1, num_tasks * 0.2)),
            min(1.0, quality_indicators['error_handling'] / max(1, num_tasks * 0.3)),
            min(1.0, quality_indicators['logging'] / max(1, num_tasks * 0.2))
        ]

        code_quality_score = sum(scores) / len(scores)

        logger.debug(
            "Code quality analysis",
            quality_indicators=quality_indicators,
            code_quality_score=code_quality_score
        )

        return max(0.0, min(1.0, code_quality_score))

    def _calculate_technical_risk(
        self,
        cognitive_plan: Dict,
        security_score: float,
        architecture_score: float,
        performance_score: float,
        code_quality_score: float
    ) -> float:
        """
        Calcula risco técnico.

        Risco aumenta com:
        - Baixa segurança (peso maior)
        - Arquitetura fraca
        - Performance ruim
        - Baixa qualidade de código

        Args:
            cognitive_plan: Plano cognitivo
            security_score: Score de segurança
            architecture_score: Score de arquitetura
            performance_score: Score de performance
            code_quality_score: Score de qualidade

        Returns:
            Score de risco (0.0-1.0)
        """
        # Média ponderada invertida (segurança tem peso maior)
        weighted_avg = (
            security_score * 0.35 +
            architecture_score * 0.3 +
            performance_score * 0.2 +
            code_quality_score * 0.15
        )
        risk_score = 1.0 - weighted_avg

        logger.debug(
            "Technical risk calculation",
            security_score=security_score,
            architecture_score=architecture_score,
            performance_score=performance_score,
            code_quality_score=code_quality_score,
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

    def _generate_mitigations(
        self,
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
