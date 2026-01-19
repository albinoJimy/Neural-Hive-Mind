"""
Task Splitter - Decompoe tasks complexas em subtasks atomicas

Analisa complexidade de tasks e aplica splitting recursivo quando necessario.
Integra com PatternMatcher para usar templates de decomposicao conhecidos.
"""

import time
import structlog
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.config.settings import Settings
from src.models.cognitive_plan import TaskNode
from src.services.pattern_matcher import PatternMatcher, PatternMatch
from src.observability.metrics import (
    tasks_split_total,
    subtasks_generated_total,
    task_splitting_depth,
    task_complexity_score,
    task_splitting_duration_seconds
)

logger = structlog.get_logger()


@dataclass
class ComplexityAnalysis:
    """Resultado da analise de complexidade de uma task"""
    score: float  # 0.0 a 1.0
    should_split: bool
    factors: Dict[str, float]  # Fatores que contribuiram para o score
    reason: str  # Razao para splitting ou nao


class TaskSplitter:
    """
    Decompoe tasks complexas em subtasks atomicas usando splitting recursivo.

    Estrategias de splitting:
    1. Pattern-based: Usa templates do PatternMatcher quando padrao detectado
    2. Heuristic-based: Usa heuristicas de complexidade quando sem padrao

    Heuristicas de complexidade:
    - Comprimento da descricao (> 150 chars = complexo)
    - Numero de entidades (>= 2 = complexo)
    - Numero de dependencias (>= 3 = complexo)
    - Presenca de multiplos verbos de acao na descricao
    """

    def __init__(
        self,
        settings: Settings,
        pattern_matcher: Optional[PatternMatcher] = None
    ):
        """
        Inicializa TaskSplitter.

        Args:
            settings: Configuracoes da aplicacao
            pattern_matcher: PatternMatcher para splitting baseado em padroes (opcional)
        """
        self.settings = settings
        self.pattern_matcher = pattern_matcher
        self.logger = structlog.get_logger().bind(component='task_splitter')

        # Verbos de acao que indicam multiplas operacoes
        self.ACTION_VERBS = [
            'create', 'criar', 'update', 'atualizar', 'delete', 'deletar',
            'query', 'consultar', 'transform', 'transformar', 'validate', 'validar',
            'send', 'enviar', 'process', 'processar', 'generate', 'gerar'
        ]

    def split(
        self,
        task: TaskNode,
        intermediate_repr: Optional[Dict[str, Any]] = None,
        current_depth: int = 0
    ) -> List[TaskNode]:
        """
        Decompoe task complexa em subtasks atomicas recursivamente.

        Args:
            task: TaskNode a ser analisada e potencialmente dividida
            intermediate_repr: Representacao intermediaria do intent (para pattern matching)
            current_depth: Profundidade atual de recursao (0 = primeira chamada)

        Returns:
            Lista de TaskNode (task original se nao dividida, ou subtasks se dividida)

        Example:
            >>> splitter = TaskSplitter(settings, pattern_matcher)
            >>> subtasks = splitter.split(complex_task, intermediate_repr)
            >>> print(f"Geradas {len(subtasks)} subtasks")
        """
        start_time = time.time()

        # Early return se splitting desabilitado
        if not self.settings.task_splitting_enabled:
            self.logger.debug('Task splitting desabilitado', task_id=task.task_id)
            return [task]

        # Early return se max_depth atingido
        if current_depth >= self.settings.task_splitting_max_depth:
            self.logger.info(
                'Max depth atingido, nao dividindo task',
                task_id=task.task_id,
                current_depth=current_depth,
                max_depth=self.settings.task_splitting_max_depth
            )
            return [task]

        # Verificar se task deve ser dividida
        if not self.should_split(task):
            self.logger.debug('Task nao requer splitting', task_id=task.task_id)
            return [task]

        # Tentar splitting baseado em padrao primeiro
        if self.pattern_matcher and intermediate_repr:
            pattern_subtasks = self._split_by_pattern(task, intermediate_repr, current_depth)
            if pattern_subtasks:
                # Aplicar splitting recursivo nas subtasks geradas
                final_subtasks = self._apply_recursive_splitting(
                    pattern_subtasks,
                    intermediate_repr,
                    current_depth
                )
                duration = time.time() - start_time
                task_splitting_duration_seconds.labels(split_type='pattern_based').observe(duration)
                return final_subtasks

        # Fallback: splitting heuristico
        heuristic_subtasks = self._split_by_heuristics(task, current_depth)

        # Aplicar splitting recursivo nas subtasks geradas
        final_subtasks = self._apply_recursive_splitting(
            heuristic_subtasks,
            intermediate_repr,
            current_depth
        )

        duration = time.time() - start_time
        task_splitting_duration_seconds.labels(split_type='heuristic_based').observe(duration)

        return final_subtasks

    def should_split(self, task: TaskNode) -> bool:
        """
        Decide se task deve ser dividida baseado em analise de complexidade.

        Args:
            task: TaskNode a analisar

        Returns:
            True se task deve ser dividida, False caso contrario
        """
        analysis = self._analyze_complexity(task)

        # Registrar metrica de complexidade
        task_complexity_score.labels(task_type=task.task_type).observe(analysis.score)

        self.logger.info(
            'Analise de complexidade',
            task_id=task.task_id,
            complexity_score=analysis.score,
            should_split=analysis.should_split,
            reason=analysis.reason,
            factors=analysis.factors
        )

        return analysis.should_split

    def _analyze_complexity(self, task: TaskNode) -> ComplexityAnalysis:
        """
        Analisa complexidade de uma task usando multiplas heuristicas.

        Fatores considerados:
        - description_length: Comprimento da descricao (normalizado)
        - entity_count: Numero de entidades nos parametros
        - dependency_count: Numero de dependencias
        - action_verb_count: Numero de verbos de acao na descricao

        Args:
            task: TaskNode a analisar

        Returns:
            ComplexityAnalysis com score e decisao de splitting
        """
        factors = {}

        # Fator 1: Comprimento da descricao (peso 0.3)
        desc_length = len(task.description) if task.description else 0
        threshold = self.settings.task_splitting_description_length_threshold
        factors['description_length'] = min(desc_length / threshold, 1.0) * 0.3

        # Fator 2: Numero de entidades (peso 0.3)
        entities = task.parameters.get('entities', [])
        entity_count = len(entities) if isinstance(entities, list) else 0
        min_entities = self.settings.task_splitting_min_entities_for_split
        factors['entity_count'] = min(entity_count / max(min_entities, 1), 1.0) * 0.3

        # Fator 3: Numero de dependencias (peso 0.2)
        dep_count = len(task.dependencies)
        factors['dependency_count'] = min(dep_count / 3.0, 1.0) * 0.2

        # Fator 4: Multiplos verbos de acao (peso 0.2)
        description_lower = task.description.lower() if task.description else ''
        action_count = sum(1 for verb in self.ACTION_VERBS if verb in description_lower)
        factors['action_verb_count'] = min(action_count / 3.0, 1.0) * 0.2

        # Score agregado
        score = sum(factors.values())
        threshold = self.settings.task_splitting_complexity_threshold
        should_split = score >= threshold

        reason = (
            f"Score {score:.2f} >= threshold {threshold:.2f}"
            if should_split
            else f"Score {score:.2f} < threshold {threshold:.2f}"
        )

        return ComplexityAnalysis(
            score=score,
            should_split=should_split,
            factors=factors,
            reason=reason
        )

    def _split_by_pattern(
        self,
        task: TaskNode,
        intermediate_repr: Dict[str, Any],
        current_depth: int
    ) -> Optional[List[TaskNode]]:
        """
        Tenta dividir task usando template de padrao detectado.

        Args:
            task: TaskNode a dividir
            intermediate_repr: Representacao intermediaria para pattern matching
            current_depth: Profundidade atual de recursao

        Returns:
            Lista de subtasks se padrao detectado, None caso contrario
        """
        matches = self.pattern_matcher.match(intermediate_repr)

        if not matches:
            self.logger.debug('Nenhum padrao detectado', task_id=task.task_id)
            return None

        # Usar padrao com maior confianca
        best_match = matches[0]

        self.logger.info(
            'Padrao detectado para splitting',
            task_id=task.task_id,
            pattern_id=best_match.pattern_id,
            pattern_name=best_match.pattern_name,
            confidence=best_match.confidence
        )

        # Gerar subtasks do template
        subtasks = self._generate_subtasks_from_template(
            parent_task=task,
            template=best_match.template,
            current_depth=current_depth
        )

        # Registrar metricas
        tasks_split_total.labels(
            split_reason='pattern_match',
            depth_level=str(current_depth)
        ).inc()

        subtasks_generated_total.labels(
            parent_task_type=task.task_type
        ).inc(len(subtasks))

        task_splitting_depth.observe(current_depth + 1)

        return subtasks

    def _generate_subtasks_from_template(
        self,
        parent_task: TaskNode,
        template: Dict[str, Any],
        current_depth: int
    ) -> List[TaskNode]:
        """
        Gera subtasks a partir de template de padrao.

        Args:
            parent_task: Task pai que esta sendo dividida
            template: Template do padrao com subtasks
            current_depth: Profundidade atual

        Returns:
            Lista de TaskNode geradas do template
        """
        subtasks = []
        subtask_definitions = template.get('subtasks', [])

        for idx, subtask_def in enumerate(subtask_definitions):
            subtask_id = f"{parent_task.task_id}_sub{idx}"

            # Mapear dependencias do template para IDs reais
            template_deps = subtask_def.get('dependencies', [])
            real_deps = []
            for dep in template_deps:
                # Encontrar indice da subtask dependencia no template
                dep_idx = next(
                    (i for i, s in enumerate(subtask_definitions) if s['id'] == dep),
                    None
                )
                if dep_idx is not None:
                    real_deps.append(f"{parent_task.task_id}_sub{dep_idx}")

            subtask = TaskNode(
                task_id=subtask_id,
                task_type=subtask_def.get('type', 'query'),
                description=subtask_def.get('description', ''),
                dependencies=real_deps,
                estimated_duration_ms=subtask_def.get('estimated_duration_ms', 500),
                required_capabilities=subtask_def.get('required_capabilities', []),
                parameters=parent_task.parameters.copy(),
                metadata={
                    'parent_task_id': parent_task.task_id,
                    'split_depth': current_depth + 1,
                    'split_method': 'pattern_based',
                    'pattern_subtask_id': subtask_def['id']
                }
            )

            subtasks.append(subtask)

        self.logger.info(
            'Subtasks geradas do template',
            parent_task_id=parent_task.task_id,
            num_subtasks=len(subtasks),
            depth=current_depth + 1
        )

        return subtasks

    def _split_by_heuristics(
        self,
        task: TaskNode,
        current_depth: int
    ) -> List[TaskNode]:
        """
        Divide task usando heuristicas quando nenhum padrao detectado.

        Estrategia heuristica:
        - Divide task em: validation -> main_operation -> verification

        Args:
            task: TaskNode a dividir
            current_depth: Profundidade atual

        Returns:
            Lista de subtasks geradas heuristicamente
        """
        subtasks = []

        # Subtask 1: Validation
        validation_task = TaskNode(
            task_id=f"{task.task_id}_validate",
            task_type='validate',
            description=f"Validate preconditions for {task.task_type} operation",
            dependencies=[],
            estimated_duration_ms=300,
            required_capabilities=['read'],
            parameters=task.parameters.copy(),
            metadata={
                'parent_task_id': task.task_id,
                'split_depth': current_depth + 1,
                'split_method': 'heuristic_based',
                'subtask_role': 'validation'
            }
        )
        subtasks.append(validation_task)

        # Subtask 2: Main Operation
        main_task = TaskNode(
            task_id=f"{task.task_id}_main",
            task_type=task.task_type,
            description=task.description,
            dependencies=[validation_task.task_id],
            estimated_duration_ms=task.estimated_duration_ms or 1000,
            required_capabilities=task.required_capabilities,
            parameters=task.parameters.copy(),
            metadata={
                'parent_task_id': task.task_id,
                'split_depth': current_depth + 1,
                'split_method': 'heuristic_based',
                'subtask_role': 'main_operation'
            }
        )
        subtasks.append(main_task)

        # Subtask 3: Verification
        verification_task = TaskNode(
            task_id=f"{task.task_id}_verify",
            task_type='validate',
            description=f"Verify results of {task.task_type} operation",
            dependencies=[main_task.task_id],
            estimated_duration_ms=200,
            required_capabilities=['read'],
            parameters=task.parameters.copy(),
            metadata={
                'parent_task_id': task.task_id,
                'split_depth': current_depth + 1,
                'split_method': 'heuristic_based',
                'subtask_role': 'verification'
            }
        )
        subtasks.append(verification_task)

        # Registrar metricas
        tasks_split_total.labels(
            split_reason='heuristic',
            depth_level=str(current_depth)
        ).inc()

        subtasks_generated_total.labels(
            parent_task_type=task.task_type
        ).inc(len(subtasks))

        task_splitting_depth.observe(current_depth + 1)

        self.logger.info(
            'Subtasks geradas heuristicamente',
            parent_task_id=task.task_id,
            num_subtasks=len(subtasks),
            depth=current_depth + 1
        )

        return subtasks

    def _apply_recursive_splitting(
        self,
        subtasks: List[TaskNode],
        intermediate_repr: Optional[Dict[str, Any]],
        current_depth: int
    ) -> List[TaskNode]:
        """
        Aplica splitting recursivo nas subtasks geradas.

        Percorre cada subtask e aplica split() recursivamente se ainda for complexa.
        Respeita o limite task_splitting_max_depth.

        Args:
            subtasks: Lista de subtasks geradas pelo splitting inicial
            intermediate_repr: Representacao intermediaria do intent (para pattern matching)
            current_depth: Profundidade atual de recursao

        Returns:
            Lista final de subtasks, possivelmente expandida com sub-subtasks
        """
        final_subtasks = []
        next_depth = current_depth + 1

        for subtask in subtasks:
            # Tentar dividir recursivamente cada subtask
            # O metodo split() ja verifica max_depth internamente
            recursive_result = self.split(
                task=subtask,
                intermediate_repr=intermediate_repr,
                current_depth=next_depth
            )

            # Se a subtask foi dividida, adicionar suas sub-subtasks
            # Se nao foi dividida, adicionar a subtask original
            final_subtasks.extend(recursive_result)

        if len(final_subtasks) > len(subtasks):
            self.logger.info(
                'Splitting recursivo expandiu subtasks',
                original_count=len(subtasks),
                final_count=len(final_subtasks),
                depth=next_depth
            )

        return final_subtasks
