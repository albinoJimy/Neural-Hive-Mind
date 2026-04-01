"""
Implementação do Evolution Specialist.

Analisa planos cognitivos sob perspectiva de evolução de software:
- Manutenibilidade (facilidade de manutenção)
- Escalabilidade (horizontal e vertical)
- Extensibilidade (facilidade de extensão)
- Modularidade (design modular)
- Tech debt futuro (prevenção de débito técnico)
- Longevidade (sustentabilidade a longo prazo)

Evolution Hooks (meta-learning):
- FingerprintExtractor: Extrai assinatura do plano
- PatternMatcher: Busca planos similares no histórico
- WeightAdapter: Ajusta pesos baseado em histórico de sucesso
"""

import sys
from typing import Any, Dict, List, Optional

import structlog

sys.path.insert(0, "/app/libraries/python")

from config import EvolutionSpecialistConfig

from neural_hive_specialists import BaseSpecialist

# Evolution Hooks imports (opcional, só se habilitado)
try:
    from neural_hive_specialists.evolution_hooks import (
        DEFAULT_WEIGHTS,
        FingerprintExtractor,
        PatternMatcher,
        PatternRegistry,
        SyncPatternRegistry,
        WeightAdapter,
    )

    EVOLUTION_HOOKS_AVAILABLE = True
except ImportError as e:
    logger = structlog.get_logger()
    logger.warning("Evolution hooks not available", error=str(e))
    EVOLUTION_HOOKS_AVAILABLE = False

logger = structlog.get_logger()


class EvolutionSpecialist(BaseSpecialist):
    """Especialista em evolução de software, manutenibilidade e escalabilidade."""

    # Configuração padrão de pesos (sem meta-learning)
    DEFAULT_WEIGHTS = {
        "maintainability": 0.25,
        "scalability": 0.25,
        "extensibility": 0.20,
        "modularity": 0.15,
        "tech_debt_prevention": 0.15,
    }

    def __init__(self, config: Optional[EvolutionSpecialistConfig] = None):
        """
        Inicializa especialista.

        Args:
            config: Configuração do especialista
        """
        super().__init__(config or EvolutionSpecialistConfig())
        self._evolution_hooks_enabled = False
        self._fingerprint_extractor: Optional[FingerprintExtractor] = None
        self._pattern_matcher: Optional[PatternMatcher] = None
        self._weight_adapter: Optional[WeightAdapter] = None
        self._pattern_registry: Optional[SyncPatternRegistry] = None

        # Inicializar evolution hooks se disponível e habilitado
        self._init_evolution_hooks()

    def _get_specialist_type(self) -> str:
        """Retorna tipo do especialista."""
        return "evolution"

    def _init_evolution_hooks(self) -> None:
        """
        Inicializa componentes de evolution hooks.

        Só inicializa se:
        1. Evolution Hooks disponível (import OK)
        2. Config habilitado (evolution_hooks_enabled=True)
        3. Mongo client disponível
        """
        if not EVOLUTION_HOOKS_AVAILABLE:
            logger.info("Evolution hooks not available, using default weights")
            return

        if not getattr(self.config, "evolution_hooks_enabled", False):
            logger.info("Evolution hooks disabled in config")
            return

        # Verificar se temos mongo_client
        if not hasattr(self, "mongo_client") or self.mongo_client is None:
            logger.warning("Mongo client not available, evolution hooks disabled")
            return

        try:
            # Inicializar componentes
            self._fingerprint_extractor = FingerprintExtractor()
            self._pattern_registry = SyncPatternRegistry(
                self.mongo_client,
                database=getattr(self.config, "evolution_hooks_pattern_registry_db", "neural_hive"),
            )

            # PatternMatcher e WeightAdapter dependem do registry
            self._pattern_matcher = PatternMatcher(self.mongo_client)
            self._weight_adapter = WeightAdapter(
                self.mongo_client,
                min_similar_patterns=getattr(
                    self.config, "evolution_hooks_min_similar_patterns", 5
                ),
                max_adjustment=getattr(self.config, "evolution_hooks_max_adjustment", 0.05),
            )

            self._evolution_hooks_enabled = True
            logger.info(
                "Evolution hooks initialized",
                min_patterns=self.config.evolution_hooks_min_similar_patterns,
                max_adjustment=self.config.evolution_hooks_max_adjustment,
            )

        except Exception as e:
            logger.warning("Failed to initialize evolution hooks, using defaults", error=str(e))
            self._evolution_hooks_enabled = False

    async def _get_adaptive_weights(self, cognitive_plan: Dict[str, Any]) -> Dict[str, float]:
        """
        Obtém pesos adaptativos baseados em histórico.

        Args:
            cognitive_plan: Plano cognitivo para extrair fingerprint

        Returns:
            Dict com pesos (adaptados ou defaults)
        """
        if not self._evolution_hooks_enabled or self._fingerprint_extractor is None:
            logger.debug("Evolution hooks disabled, using default weights")
            return self.DEFAULT_WEIGHTS.copy()

        try:
            # Extrair fingerprint
            fingerprint = self._fingerprint_extractor.extract(cognitive_plan)

            # Buscar similares para logging
            similar = await self._pattern_matcher.find_similar(fingerprint)

            # Adaptar pesos
            adapted = await self._weight_adapter.adapt_weights(fingerprint)

            logger.debug(
                "Weight adaptation completed",
                plan_id=cognitive_plan.get("plan_id"),
                similar_count=len(similar),
                weights=adapted,
            )

            return adapted

        except Exception as e:
            logger.warning(
                "Weight adaptation failed, using defaults",
                error=str(e),
                plan_id=cognitive_plan.get("plan_id"),
            )
            return self.DEFAULT_WEIGHTS.copy()

    async def _store_evaluation_for_learning(
        self, plan_id: str, cognitive_plan: Dict[str, Any], evaluation_result: Dict[str, Any]
    ) -> None:
        """
        Armazena avaliação para aprendizado futuro.

        Args:
            plan_id: ID do plano
            cognitive_plan: Plano cognitivo completo
            evaluation_result: Resultado da avaliação
        """
        if not self._evolution_hooks_enabled or self._pattern_registry is None:
            return

        try:
            from neural_hive_specialists.evolution_hooks import EvolutionEvaluation

            # Extrair fingerprint
            fingerprint = self._fingerprint_extractor.extract(cognitive_plan)

            # Criar EvolutionEvaluation
            evolution_eval = EvolutionEvaluation(
                confidence_score=evaluation_result.get("confidence_score", 0.5),
                risk_score=evaluation_result.get("risk_score", 0.5),
                recommendation=evaluation_result.get("recommendation", "conditional"),
                weights_used=evaluation_result.get("adaptive_weights", self.DEFAULT_WEIGHTS),
                reasoning_factors=evaluation_result.get("reasoning_factors", []),
            )

            # Armazenar no registry
            pattern_id = self._pattern_registry.store_evaluation(
                plan_id=plan_id, fingerprint=fingerprint, evaluation=evolution_eval
            )

            logger.debug("Stored evaluation for learning", plan_id=plan_id, pattern_id=pattern_id)

        except Exception as e:
            logger.warning("Failed to store evaluation for learning", error=str(e), plan_id=plan_id)

    def _load_model(self) -> Any:
        """Carrega modelo de análise de evolução do MLflow."""
        logger.info("Loading Evolution Specialist model")

        # Tentar carregar modelo ML do MLflow
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
                self.config.mlflow_model_name, self.config.mlflow_model_stage
            )

            if model:
                metadata = self.mlflow_client.get_model_metadata(
                    self.config.mlflow_model_name, self.config.mlflow_model_stage
                )

                if not metadata:
                    logger.warning(
                        "No model metadata found for configured stage - using heuristics",
                        model_name=self.config.mlflow_model_name,
                        stage=self.config.mlflow_model_stage,
                    )
                    return None

                logger.info(
                    "ML model loaded successfully",
                    model_name=self.config.mlflow_model_name,
                    stage=self.config.mlflow_model_stage,
                    version=metadata.get("version", "unknown"),
                    stage_match=metadata.get("stage", self.config.mlflow_model_stage)
                    == self.config.mlflow_model_stage,
                )

            return model

        except Exception as e:
            # Fallback para heurísticas
            logger.warning("ML model not available, using heuristics", error=str(e))
            return None

    def _evaluate_plan_internal(
        self, cognitive_plan: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Avalia plano sob perspectiva de evolução.

        Args:
            cognitive_plan: Plano cognitivo a ser avaliado
            context: Contexto adicional da avaliação

        Returns:
            Dicionário com resultado da avaliação
        """
        logger.info(
            "Evaluating plan from evolution perspective",
            plan_id=cognitive_plan.get("plan_id"),
            domain=cognitive_plan.get("original_domain"),
            evolution_hooks_enabled=self._evolution_hooks_enabled,
        )

        # Extrair informações do plano
        tasks = cognitive_plan.get("tasks", [])
        domain = cognitive_plan.get("original_domain")
        priority = cognitive_plan.get("original_priority", "normal")
        plan_id = cognitive_plan.get("plan_id", "unknown")

        # Análise de manutenibilidade
        maintainability_score = self._analyze_maintainability(tasks, cognitive_plan)

        # Análise de escalabilidade
        scalability_score = self._analyze_scalability(tasks, cognitive_plan)

        # Análise de extensibilidade
        extensibility_score = self._analyze_extensibility(tasks, cognitive_plan)

        # Análise de modularidade
        modularity_score = self._analyze_modularity(tasks)

        # Análise de tech debt futuro
        tech_debt_score = self._analyze_tech_debt_risk(tasks, cognitive_plan)

        # Obter pesos adaptativos (ou defaults)
        # Nota: como este método é sync, usamos defaults aqui.
        # A adaptação async será feita em evaluate_plan() se necessário.
        adaptive_weights = self.DEFAULT_WEIGHTS.copy()

        # Se evolution hooks está habilitado, tentar usar pesos adaptativos
        if self._evolution_hooks_enabled and self._fingerprint_extractor:
            try:
                import asyncio

                # Tentar rodar async em contexto sync
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Já estamos em um loop async, usar defaults por agora
                    logger.debug("Running in async context, using default weights")
                else:
                    # Sem loop async, tentar rodar
                    adaptive_weights = asyncio.run(self._get_adaptive_weights(cognitive_plan))
            except Exception as e:
                logger.debug("Could not get adaptive weights, using defaults", error=str(e))

        # Calcular scores agregados usando pesos adaptativos
        confidence_score = (
            maintainability_score * adaptive_weights.get("maintainability", 0.25)
            + scalability_score * adaptive_weights.get("scalability", 0.25)
            + extensibility_score * adaptive_weights.get("extensibility", 0.20)
            + modularity_score * adaptive_weights.get("modularity", 0.15)
            + tech_debt_score * adaptive_weights.get("tech_debt_prevention", 0.15)
        )

        # Calcular risco de evolução
        risk_score = self._calculate_evolution_risk(
            maintainability_score,
            scalability_score,
            extensibility_score,
            modularity_score,
            tech_debt_score,
        )

        # Determinar recomendação
        recommendation = self._determine_recommendation(confidence_score, risk_score)

        # Gerar justificativa
        reasoning_summary = self._generate_reasoning(
            maintainability_score,
            scalability_score,
            extensibility_score,
            modularity_score,
            tech_debt_score,
            recommendation,
        )

        # Fatores de raciocínio estruturados (com pesos adaptativos)
        reasoning_factors = [
            {
                "factor_name": "maintainability",
                "weight": adaptive_weights.get("maintainability", 0.25),
                "score": maintainability_score,
                "description": "Facilidade de manutenção baseada em clareza, acoplamento e coesão",
            },
            {
                "factor_name": "scalability",
                "weight": adaptive_weights.get("scalability", 0.25),
                "score": scalability_score,
                "description": "Capacidade de escalar horizontal e verticalmente",
            },
            {
                "factor_name": "extensibility",
                "weight": adaptive_weights.get("extensibility", 0.20),
                "score": extensibility_score,
                "description": "Facilidade de adicionar novos recursos no futuro",
            },
            {
                "factor_name": "modularity",
                "weight": adaptive_weights.get("modularity", 0.15),
                "score": modularity_score,
                "description": "Design modular e separação de responsabilidades",
            },
            {
                "factor_name": "tech_debt_prevention",
                "weight": adaptive_weights.get("tech_debt_prevention", 0.15),
                "score": tech_debt_score,
                "description": "Prevenção de débito técnico futuro",
            },
        ]

        # Sugestões de mitigação
        mitigations = self._generate_mitigations(
            maintainability_score,
            scalability_score,
            extensibility_score,
            modularity_score,
            tech_debt_score,
        )

        logger.info(
            "Evolution evaluation completed",
            plan_id=plan_id,
            confidence_score=confidence_score,
            risk_score=risk_score,
            recommendation=recommendation,
            adaptive_weights=adaptive_weights if adaptive_weights != self.DEFAULT_WEIGHTS else None,
        )

        # Construir resultado
        result = {
            "confidence_score": confidence_score,
            "risk_score": risk_score,
            "recommendation": recommendation,
            "reasoning_summary": reasoning_summary,
            "reasoning_factors": reasoning_factors,
            "mitigations": mitigations,
            "metadata": {
                "maintainability_score": maintainability_score,
                "scalability_score": scalability_score,
                "extensibility_score": extensibility_score,
                "modularity_score": modularity_score,
                "tech_debt_score": tech_debt_score,
                "domain": domain,
                "priority": priority,
                "num_tasks": len(tasks),
                "evolution_hooks_enabled": self._evolution_hooks_enabled,
            },
        }

        # Adicionar pesos adaptativos ao resultado para metadados
        if adaptive_weights != self.DEFAULT_WEIGHTS:
            result["adaptive_weights"] = adaptive_weights
            result["metadata"]["weights_source"] = "adaptive"
        else:
            result["metadata"]["weights_source"] = "default"

        # Armazenar avaliação para aprendizado async (fire and forget)
        if self._evolution_hooks_enabled and self._pattern_registry:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Criar task mas não await
                    asyncio.create_task(
                        self._store_evaluation_for_learning(plan_id, cognitive_plan, result)
                    )
                else:
                    # Rodar async se não temos loop
                    asyncio.run(
                        self._store_evaluation_for_learning(plan_id, cognitive_plan, result)
                    )
            except Exception as e:
                logger.debug(
                    "Could not store evaluation for learning", error=str(e), plan_id=plan_id
                )

        return result

    def _analyze_maintainability(self, tasks: List[Dict], cognitive_plan: Dict) -> float:
        """
        Analisa manutenibilidade do plano.

        Heurísticas:
        - Complexidade ciclomática (menos branches = mais manutenível)
        - Acoplamento (menos dependências = mais manutenível)
        - Coesão (tarefas bem agrupadas = mais manutenível)
        - Clareza (tarefas com descrições claras = mais manutenível)

        Args:
            tasks: Lista de tarefas do plano
            cognitive_plan: Plano cognitivo completo

        Returns:
            Score de manutenibilidade (0.0-1.0)
        """
        num_tasks = len(tasks)

        if num_tasks == 0:
            logger.warning("No tasks in plan")
            return 0.5

        # Analisar complexidade (menos tarefas = mais manutenível, até certo ponto)
        if num_tasks <= 3:
            complexity_score = 0.7  # Muito simples, pode indicar falta de granularidade
        elif num_tasks <= 10:
            complexity_score = 1.0  # Ideal
        elif num_tasks <= 20:
            complexity_score = 0.8  # Razoável
        else:
            complexity_score = 0.5  # Muito complexo

        # Analisar acoplamento (baseado em dependências)
        total_dependencies = sum(len(task.get("dependencies", [])) for task in tasks)
        avg_dependencies = total_dependencies / num_tasks if num_tasks > 0 else 0

        if avg_dependencies <= 1:
            coupling_score = 1.0  # Baixo acoplamento
        elif avg_dependencies <= 2:
            coupling_score = 0.8  # Médio acoplamento
        else:
            coupling_score = 0.5  # Alto acoplamento

        # Analisar clareza (tarefas com nomes/tipos bem definidos)
        clear_tasks = sum(1 for task in tasks if task.get("name") and task.get("task_type"))
        clarity_score = clear_tasks / num_tasks if num_tasks > 0 else 0

        # Score final
        maintainability_score = complexity_score * 0.3 + coupling_score * 0.4 + clarity_score * 0.3

        logger.debug(
            "Maintainability analysis",
            num_tasks=num_tasks,
            complexity_score=complexity_score,
            coupling_score=coupling_score,
            clarity_score=clarity_score,
            maintainability_score=maintainability_score,
        )

        return max(0.0, min(1.0, maintainability_score))

    def _analyze_scalability(self, tasks: List[Dict], cognitive_plan: Dict) -> float:
        """
        Analisa escalabilidade do plano.

        Heurísticas:
        - Paralelização (mais tarefas paralelas = mais escalável)
        - Independência (menos dependências = mais escalável)
        - Stateless design (tarefas sem estado compartilhado = mais escalável)
        - Resource efficiency (menos recursos = mais escalável)

        Args:
            tasks: Lista de tarefas do plano
            cognitive_plan: Plano cognitivo completo

        Returns:
            Score de escalabilidade (0.0-1.0)
        """
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        # Calcular potencial de paralelização
        total_dependencies = sum(len(task.get("dependencies", [])) for task in tasks)
        max_possible_deps = num_tasks * (num_tasks - 1) / 2

        if max_possible_deps > 0:
            dependency_ratio = total_dependencies / max_possible_deps
            parallelization_potential = 1.0 - (dependency_ratio * 0.8)
        else:
            parallelization_potential = 1.0

        # Analisar eficiência de recursos (baseado em duração estimada)
        total_duration_ms = sum(task.get("estimated_duration_ms", 0) for task in tasks)
        avg_duration_ms = total_duration_ms / num_tasks if num_tasks > 0 else 0

        # Normalizar (1 segundo = 1000ms como ideal)
        if avg_duration_ms <= 1000:
            resource_efficiency = 1.0
        elif avg_duration_ms <= 5000:
            resource_efficiency = 0.8
        elif avg_duration_ms <= 10000:
            resource_efficiency = 0.6
        else:
            resource_efficiency = 0.4

        # Score final
        scalability_score = parallelization_potential * 0.6 + resource_efficiency * 0.4

        logger.debug(
            "Scalability analysis",
            num_tasks=num_tasks,
            parallelization_potential=parallelization_potential,
            resource_efficiency=resource_efficiency,
            scalability_score=scalability_score,
        )

        return max(0.0, min(1.0, scalability_score))

    def _analyze_extensibility(self, tasks: List[Dict], cognitive_plan: Dict) -> float:
        """
        Analisa extensibilidade do plano.

        Heurísticas:
        - Modularidade (tarefas bem separadas = mais extensível)
        - Abstração (uso de abstrações = mais extensível)
        - Flexibilidade (design que permite mudanças = mais extensível)

        Args:
            tasks: Lista de tarefas do plano
            cognitive_plan: Plano cognitivo completo

        Returns:
            Score de extensibilidade (0.0-1.0)
        """
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        # Analisar modularidade (baseado em tipos de tarefas)
        task_types = set(task.get("task_type", "unknown") for task in tasks)
        type_diversity = len(task_types) / num_tasks if num_tasks > 0 else 0

        # Diversidade moderada indica boa separação de responsabilidades
        if type_diversity >= 0.3 and type_diversity <= 0.6:
            modularity_score = 1.0
        elif type_diversity > 0.6:
            modularity_score = 0.8  # Muita diversidade pode indicar falta de coesão
        else:
            modularity_score = 0.6  # Pouca diversidade pode indicar acoplamento

        # Analisar flexibilidade (baseado em dependências condicionais)
        # Tarefas com poucas dependências hard-coded são mais flexíveis
        tasks_with_few_deps = sum(1 for task in tasks if len(task.get("dependencies", [])) <= 2)
        flexibility_score = tasks_with_few_deps / num_tasks if num_tasks > 0 else 0

        # Score final
        extensibility_score = modularity_score * 0.5 + flexibility_score * 0.5

        logger.debug(
            "Extensibility analysis",
            num_tasks=num_tasks,
            type_diversity=type_diversity,
            modularity_score=modularity_score,
            flexibility_score=flexibility_score,
            extensibility_score=extensibility_score,
        )

        return max(0.0, min(1.0, extensibility_score))

    def _analyze_modularity(self, tasks: List[Dict]) -> float:
        """
        Analisa modularidade do design.

        Heurísticas:
        - Separação de responsabilidades
        - Tamanho adequado dos módulos
        - Interfaces bem definidas

        Args:
            tasks: Lista de tarefas do plano

        Returns:
            Score de modularidade (0.0-1.0)
        """
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        # Analisar tamanho dos módulos (baseado em número de tarefas)
        if num_tasks <= 5:
            size_score = 0.7  # Pode ser muito pequeno
        elif num_tasks <= 15:
            size_score = 1.0  # Tamanho ideal
        elif num_tasks <= 25:
            size_score = 0.8  # Grande mas gerenciável
        else:
            size_score = 0.5  # Muito grande

        # Analisar separação de responsabilidades (baseado em tipos de tarefas)
        task_types = [task.get("task_type", "unknown") for task in tasks]
        unique_types = len(set(task_types))

        if unique_types >= 3 and unique_types <= 7:
            separation_score = 1.0  # Boa separação
        elif unique_types > 7:
            separation_score = 0.7  # Muitos tipos
        else:
            separation_score = 0.6  # Poucos tipos

        # Score final
        modularity_score = size_score * 0.5 + separation_score * 0.5

        logger.debug(
            "Modularity analysis",
            num_tasks=num_tasks,
            unique_types=unique_types,
            size_score=size_score,
            separation_score=separation_score,
            modularity_score=modularity_score,
        )

        return max(0.0, min(1.0, modularity_score))

    def _analyze_tech_debt_risk(self, tasks: List[Dict], cognitive_plan: Dict) -> float:
        """
        Analisa risco de tech debt futuro.

        Heurísticas:
        - Complexidade excessiva = alto risco
        - Falta de testes = alto risco
        - Alto acoplamento = alto risco
        - Falta de documentação = alto risco

        Args:
            tasks: Lista de tarefas do plano
            cognitive_plan: Plano cognitivo completo

        Returns:
            Score de prevenção de tech debt (0.0-1.0, quanto maior melhor)
        """
        num_tasks = len(tasks)

        if num_tasks == 0:
            return 0.5

        # Verificar se há tarefas de teste
        test_tasks = sum(
            1
            for task in tasks
            if "test" in (task.get("name") or "").lower() or task.get("task_type", "") == "testing"
        )
        test_coverage_score = min(1.0, test_tasks / max(1, num_tasks * 0.3))

        # Verificar complexidade (muitas tarefas = maior risco de tech debt)
        if num_tasks <= 10:
            complexity_risk = 1.0  # Baixo risco
        elif num_tasks <= 20:
            complexity_risk = 0.7  # Médio risco
        else:
            complexity_risk = 0.5  # Alto risco

        # Verificar acoplamento
        total_dependencies = sum(len(task.get("dependencies", [])) for task in tasks)
        avg_dependencies = total_dependencies / num_tasks if num_tasks > 0 else 0

        if avg_dependencies <= 1.5:
            coupling_risk = 1.0  # Baixo acoplamento
        elif avg_dependencies <= 3:
            coupling_risk = 0.7  # Médio acoplamento
        else:
            coupling_risk = 0.4  # Alto acoplamento

        # Score final (quanto maior, menor o risco de tech debt)
        tech_debt_prevention_score = (
            test_coverage_score * 0.4 + complexity_risk * 0.3 + coupling_risk * 0.3
        )

        logger.debug(
            "Tech debt risk analysis",
            num_tasks=num_tasks,
            test_tasks=test_tasks,
            test_coverage_score=test_coverage_score,
            complexity_risk=complexity_risk,
            coupling_risk=coupling_risk,
            tech_debt_prevention_score=tech_debt_prevention_score,
        )

        return max(0.0, min(1.0, tech_debt_prevention_score))

    def _calculate_evolution_risk(
        self,
        maintainability_score: float,
        scalability_score: float,
        extensibility_score: float,
        modularity_score: float,
        tech_debt_score: float,
    ) -> float:
        """
        Calcula risco de evolução geral.

        Risco aumenta com:
        - Baixa manutenibilidade
        - Baixa escalabilidade
        - Baixa extensibilidade
        - Baixa modularidade
        - Alto risco de tech debt

        Args:
            maintainability_score: Score de manutenibilidade
            scalability_score: Score de escalabilidade
            extensibility_score: Score de extensibilidade
            modularity_score: Score de modularidade
            tech_debt_score: Score de prevenção de tech debt

        Returns:
            Score de risco (0.0-1.0)
        """
        # Média ponderada invertida
        weighted_avg = (
            maintainability_score * 0.25
            + scalability_score * 0.25
            + extensibility_score * 0.20
            + modularity_score * 0.15
            + tech_debt_score * 0.15
        )
        risk_score = 1.0 - weighted_avg

        logger.debug(
            "Evolution risk calculation",
            maintainability_score=maintainability_score,
            scalability_score=scalability_score,
            extensibility_score=extensibility_score,
            modularity_score=modularity_score,
            tech_debt_score=tech_debt_score,
            risk_score=risk_score,
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
            return "approve"
        elif confidence_score < 0.5 or risk_score > 0.7:
            return "reject"
        elif risk_score > 0.5:
            return "review_required"
        else:
            return "conditional"

    def _generate_reasoning(
        self,
        maintainability_score: float,
        scalability_score: float,
        extensibility_score: float,
        modularity_score: float,
        tech_debt_score: float,
        recommendation: str,
    ) -> str:
        """Gera narrativa de justificativa."""
        return (
            f"Avaliação de evolução: "
            f"maintainability={maintainability_score:.2f}, "
            f"scalability={scalability_score:.2f}, "
            f"extensibility={extensibility_score:.2f}, "
            f"modularity={modularity_score:.2f}, "
            f"tech_debt_prevention={tech_debt_score:.2f}. "
            f"Recomendação: {recommendation}."
        )

    def _generate_mitigations(
        self,
        maintainability_score: float,
        scalability_score: float,
        extensibility_score: float,
        modularity_score: float,
        tech_debt_score: float,
    ) -> List[Dict]:
        """Gera sugestões de mitigação de riscos."""
        mitigations = []

        if maintainability_score < 0.6:
            mitigations.append(
                {
                    "mitigation_id": "improve_maintainability",
                    "description": "Melhorar manutenibilidade reduzindo complexidade e acoplamento",
                    "priority": "high",
                    "estimated_impact": 0.3,
                    "required_actions": [
                        "Simplificar tarefas complexas",
                        "Reduzir dependências entre módulos",
                        "Adicionar documentação clara",
                        "Aplicar princípios SOLID",
                    ],
                }
            )

        if scalability_score < 0.6:
            mitigations.append(
                {
                    "mitigation_id": "enhance_scalability",
                    "description": "Aumentar capacidade de escalabilidade horizontal e vertical",
                    "priority": "high",
                    "estimated_impact": 0.35,
                    "required_actions": [
                        "Aumentar paralelização de tarefas",
                        "Implementar design stateless",
                        "Otimizar uso de recursos",
                        "Considerar arquitetura distribuída",
                    ],
                }
            )

        if extensibility_score < 0.6:
            mitigations.append(
                {
                    "mitigation_id": "improve_extensibility",
                    "description": "Facilitar adição de novos recursos no futuro",
                    "priority": "medium",
                    "estimated_impact": 0.25,
                    "required_actions": [
                        "Aplicar padrões de design (Strategy, Factory, etc)",
                        "Usar abstrações e interfaces",
                        "Reduzir acoplamento entre componentes",
                        "Implementar dependency injection",
                    ],
                }
            )

        if modularity_score < 0.6:
            mitigations.append(
                {
                    "mitigation_id": "enhance_modularity",
                    "description": "Melhorar design modular e separação de responsabilidades",
                    "priority": "medium",
                    "estimated_impact": 0.2,
                    "required_actions": [
                        "Aplicar Single Responsibility Principle",
                        "Dividir módulos grandes em menores",
                        "Definir interfaces claras entre módulos",
                        "Agrupar funcionalidades relacionadas",
                    ],
                }
            )

        if tech_debt_score < 0.6:
            mitigations.append(
                {
                    "mitigation_id": "prevent_tech_debt",
                    "description": "Prevenir acúmulo de débito técnico futuro",
                    "priority": "high",
                    "estimated_impact": 0.4,
                    "required_actions": [
                        "Adicionar testes automatizados (unit, integration)",
                        "Implementar code reviews",
                        "Documentar decisões arquiteturais",
                        "Estabelecer métricas de qualidade de código",
                        "Planejar refatorações regulares",
                    ],
                }
            )

        return mitigations
