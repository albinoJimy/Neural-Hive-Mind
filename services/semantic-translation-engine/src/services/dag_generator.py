"""
DAG Generator - Converte representação intermediária em grafo de tasks

Gera Directed Acyclic Graphs de tasks executáveis a partir de intents parseados.
Enriquece descrições de tasks com contexto de domínio para avaliação heurística.

Suporta decomposição avançada através de:
- PatternMatcher: detecta padrões complexos e aplica templates de decomposição
- TaskSplitter: divide tasks complexas em subtasks atômicas recursivamente
- Análise de dependências por entidades: identifica dependências write→read
- Detecção de conflitos write-write com estratégias de resolução
- Detecção de paralelismo: agrupa tasks independentes para execução concorrente
- Visualização de dependências em formato Mermaid
"""

import time
import difflib
import structlog
import networkx as nx
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional, Set, TYPE_CHECKING

from src.models.cognitive_plan import TaskNode
from src.services.description_validator import DescriptionQualityValidator, get_validator

if TYPE_CHECKING:
    from src.services.pattern_matcher import PatternMatcher, PatternMatch
    from src.services.task_splitter import TaskSplitter

from src.observability.metrics import (
    dag_generation_pattern_matches_total,
    dag_generation_parallel_groups_total,
    dag_generation_entity_dependencies_added,
    dag_generation_duration_seconds,
    dag_generation_conflicts_detected_total,
    dag_generation_conflicts_resolved_total,
    dag_generation_entity_matching_fuzzy_total,
    dag_generation_visualization_generated_total
)

logger = structlog.get_logger()


# Mapping of objectives to descriptive action verb phrases
OBJECTIVE_ACTION_VERBS: Dict[str, List[str]] = {
    'create': [
        "Create and initialize",
        "Provision resources for",
        "Set up configuration for",
        "Establish and configure",
    ],
    'update': [
        "Modify and validate",
        "Apply changes to",
        "Synchronize state of",
        "Update and verify",
    ],
    'query': [
        "Retrieve and filter",
        "Search and aggregate",
        "Fetch data from",
        "Query and extract",
    ],
    'validate': [
        "Verify integrity of",
        "Check compliance for",
        "Audit security of",
        "Validate constraints on",
    ],
    'transform': [
        "Process and convert",
        "Normalize and enrich",
        "Aggregate and compute",
        "Transform and format",
    ],
    'delete': [
        "Remove and clean up",
        "Decommission and archive",
        "Delete and audit",
    ],
    'deploy': [
        "Deploy and configure",
        "Provision and activate",
        "Release and monitor",
    ],
}

# Domain-specific context hints
DOMAIN_CONTEXT_HINTS: Dict[str, str] = {
    'security-analysis': "with authentication validation and access control audit",
    'architecture-review': "following microservice patterns and interface contracts",
    'performance-optimization': "using indexed queries and connection pooling strategies",
    'code-quality': "with comprehensive error handling and test coverage",
    'business-logic': "aligned with workflow policies and business KPI metrics",
}

# Security level hints
SECURITY_HINTS: Dict[str, str] = {
    'confidential': "with authentication and AES-256 encryption",
    'restricted': "with multi-factor authentication and end-to-end encryption",
    'internal': "with role-based access control",
    'public': "",
}

# Priority hints
PRIORITY_HINTS: Dict[str, str] = {
    'critical': "with optimized caching, indexing, and real-time monitoring",
    'high': "with performance optimization and caching",
    'normal': "",
    'low': "",
}

# QoS hints para semântica de entrega
QOS_HINTS: Dict[str, str] = {
    'exactly_once': "with idempotency guarantees, transaction rollback, and deduplication",
    'at_least_once': "with retry mechanism and redelivery support",
    'at_most_once': "with fire-and-forget delivery and best-effort processing",
}

# Risk band hints para indicar nível de risco
RISK_BAND_HINTS: Dict[str, str] = {
    'critical': "critical risk",
    'high': "high risk",
    'medium': "medium risk",
    'low': "low risk",
}

# Aliases de entidades para matching semântico
DEFAULT_ENTITY_ALIASES: Dict[str, Set[str]] = {
    'user': {'usuario', 'customer', 'client', 'pessoa', 'account'},
    'order': {'pedido', 'purchase', 'compra', 'transaction'},
    'product': {'produto', 'item', 'article', 'sku'},
    'payment': {'pagamento', 'charge', 'billing'},
}


@dataclass
class ConflictInfo:
    """
    Informações sobre conflito detectado entre tasks.

    Conflitos ocorrem quando duas tasks escrevem na mesma entidade
    sem dependência explícita entre elas.
    """
    task_a_id: str
    task_b_id: str
    shared_entities: List[str]
    conflict_type: str  # 'write-write', 'concurrent-update'
    severity: str  # 'critical', 'high', 'medium', 'low'
    resolution_strategy: Optional[str] = None
    resolved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class DAGGenerator:
    """
    Gerador de DAGs de tasks a partir de objectives e constraints.

    Suporta dois modos de operação:
    - Modo legado: gera tasks apenas com heurísticas simples
    - Modo avançado: usa PatternMatcher e TaskSplitter para decomposição inteligente

    Args:
        pattern_matcher: PatternMatcher para detecção de padrões complexos (opcional)
        task_splitter: TaskSplitter para divisão de tasks complexas (opcional)

    Example:
        >>> from src.services.pattern_matcher import PatternMatcher
        >>> from src.services.task_splitter import TaskSplitter
        >>> pattern_matcher = PatternMatcher()
        >>> task_splitter = TaskSplitter(settings, pattern_matcher)
        >>> dag_gen = DAGGenerator(pattern_matcher=pattern_matcher, task_splitter=task_splitter)
        >>> tasks, order = dag_gen.generate(intermediate_repr)
    """

    def __init__(
        self,
        pattern_matcher: Optional['PatternMatcher'] = None,
        task_splitter: Optional['TaskSplitter'] = None,
        entity_matching_fuzzy_enabled: bool = True,
        entity_matching_fuzzy_threshold: float = 0.85,
        entity_matching_use_canonical_types: bool = True,
        entity_aliases: Optional[Dict[str, Set[str]]] = None,
        conflict_resolution_strategy: str = 'sequential'
    ):
        self.task_templates = self._load_task_templates()
        self.description_validator = get_validator()
        self._action_verb_index = 0  # Para rotação de verbos de ação

        # Componentes de decomposição avançada (opcionais)
        self.pattern_matcher = pattern_matcher
        self.task_splitter = task_splitter

        # Configurações de entity matching
        self.entity_matching_fuzzy_enabled = entity_matching_fuzzy_enabled
        self.entity_matching_fuzzy_threshold = entity_matching_fuzzy_threshold
        self.entity_matching_use_canonical_types = entity_matching_use_canonical_types
        self.entity_aliases = entity_aliases or DEFAULT_ENTITY_ALIASES

        # Estratégia de resolução de conflitos: 'sequential', 'priority_based', 'notify'
        self.conflict_resolution_strategy = conflict_resolution_strategy

        # Log indicando modo de operação
        logger.info(
            'DAGGenerator inicializado',
            pattern_matching_enabled=pattern_matcher is not None,
            task_splitting_enabled=task_splitter is not None,
            entity_matching_fuzzy_enabled=entity_matching_fuzzy_enabled,
            conflict_resolution_strategy=conflict_resolution_strategy
        )

    def _load_task_templates(self) -> Dict[str, Dict]:
        """Load known task templates"""
        # MVP: Hardcoded templates
        # Future: Load from Knowledge Graph
        return {
            'create': {
                'type': 'create',
                'estimated_duration_ms': 1000,
                'required_capabilities': ['write']
            },
            'update': {
                'type': 'update',
                'estimated_duration_ms': 800,
                'required_capabilities': ['write']
            },
            'query': {
                'type': 'query',
                'estimated_duration_ms': 500,
                'required_capabilities': ['read']
            },
            'validate': {
                'type': 'validate',
                'estimated_duration_ms': 300,
                'required_capabilities': ['read']
            },
            'transform': {
                'type': 'transform',
                'estimated_duration_ms': 600,
                'required_capabilities': ['compute']
            }
        }

    def _extract_entity_identifiers(self, entity: Dict) -> Set[str]:
        """
        Extrai todos os identificadores possíveis para uma entidade.

        Normaliza e extrai múltiplos campos que podem identificar a entidade,
        incluindo aliases configurados para matching semântico.

        Args:
            entity: Dicionário com dados da entidade

        Returns:
            Set de identificadores normalizados
        """
        identifiers: Set[str] = set()

        # Extrair de campos comuns
        for field in ['name', 'value', 'type', 'canonical_type', 'entity_type']:
            if field in entity and entity[field]:
                normalized = str(entity[field]).lower().strip()
                # Remover caracteres especiais exceto underscore
                normalized = ''.join(
                    c for c in normalized
                    if c.isalnum() or c == '_'
                )
                if normalized:
                    identifiers.add(normalized)

        # Adicionar aliases se configurado
        if self.entity_aliases:
            for identifier in list(identifiers):
                # Verificar se o identificador é um alias conhecido
                for canonical, aliases in self.entity_aliases.items():
                    if identifier == canonical or identifier in aliases:
                        identifiers.add(canonical)
                        identifiers.update(aliases)

        return identifiers

    def _entities_match(
        self,
        entity_a: Dict,
        entity_b: Dict
    ) -> Tuple[bool, float, str]:
        """
        Verifica se duas entidades fazem match.

        Usa matching exato primeiro, depois fuzzy se habilitado.
        Suporta tipos canônicos para matching semântico.

        Args:
            entity_a: Primeira entidade
            entity_b: Segunda entidade

        Returns:
            Tupla (match_found, confidence, match_type)
        """
        ids_a = self._extract_entity_identifiers(entity_a)
        ids_b = self._extract_entity_identifiers(entity_b)

        # Match exato (interseção não vazia)
        exact_matches = ids_a & ids_b
        if exact_matches:
            return True, 1.0, 'exact'

        # Fuzzy matching se habilitado
        if self.entity_matching_fuzzy_enabled:
            for id_a in ids_a:
                for id_b in ids_b:
                    ratio = difflib.SequenceMatcher(None, id_a, id_b).ratio()
                    if ratio >= self.entity_matching_fuzzy_threshold:
                        dag_generation_entity_matching_fuzzy_total.inc()
                        return True, ratio, 'fuzzy'

        # Matching por tipo canônico se habilitado
        if self.entity_matching_use_canonical_types:
            type_a = entity_a.get('type', entity_a.get('entity_type', ''))
            type_b = entity_b.get('type', entity_b.get('entity_type', ''))

            if type_a and type_b:
                # Verificar se são do mesmo tipo canônico
                type_a_lower = str(type_a).lower()
                type_b_lower = str(type_b).lower()

                # Match se um contém o outro (ex: user_profile contém user)
                if type_a_lower in type_b_lower or type_b_lower in type_a_lower:
                    return True, 0.8, 'canonical_type'

        return False, 0.0, 'none'

    def _classify_conflict_severity(
        self,
        task_a_type: str,
        task_b_type: str
    ) -> str:
        """
        Classifica a severidade de um conflito write-write.

        Args:
            task_a_type: Tipo da primeira task
            task_b_type: Tipo da segunda task

        Returns:
            Severidade: 'critical', 'high', 'medium', 'low'
        """
        # delete-delete é crítico (pode causar integridade referencial)
        if task_a_type == 'delete' and task_b_type == 'delete':
            return 'critical'

        # delete com qualquer outro write é alto
        if 'delete' in (task_a_type, task_b_type):
            return 'high'

        # update-update é médio (pode causar race condition)
        if task_a_type == 'update' and task_b_type == 'update':
            return 'medium'

        # create-create é baixo (duplicação, mas recuperável)
        if task_a_type == 'create' and task_b_type == 'create':
            return 'low'

        # Outros casos
        return 'medium'

    def generate(self, intermediate_repr: Dict[str, Any]) -> Tuple[List[TaskNode], List[str]]:
        """
        Gera DAG de tasks com suporte a decomposição avançada.

        Fluxo de geração:
        1. Extrair objectives, entities, constraints
        2. Tentar pattern matching (se disponível)
        3. Se pattern match: usar _generate_from_pattern()
        4. Se não: loop sobre objectives com task splitting
        5. Gerar support tasks
        6. Adicionar dependências heurísticas
        7. Adicionar dependências por entidades
        8. Detectar paralelismo
        9. Validar DAG acíclico
        10. Gerar ordem topológica
        11. Calcular critical path

        Args:
            intermediate_repr: Representação intermediária do intent parseado

        Returns:
            Tuple de (tasks, execution_order)
        """
        start_time = time.time()
        decomposition_type = 'legacy'

        objectives = intermediate_repr.get('objectives', [])
        entities = intermediate_repr.get('entities', [])
        constraints = intermediate_repr.get('constraints', {})

        # Criar grafo NetworkX
        G = nx.DiGraph()

        # Gerar tasks
        tasks = []
        task_id_counter = 0

        # Passo 1: Tentar pattern matching (se disponível)
        pattern_tasks = None
        if self.pattern_matcher:
            pattern_matches = self.pattern_matcher.match(intermediate_repr)

            if pattern_matches:
                best_match = pattern_matches[0]
                logger.info(
                    'Padrão detectado para decomposição',
                    pattern_id=best_match.pattern_id,
                    pattern_name=best_match.pattern_name,
                    confidence=best_match.confidence
                )

                # Gerar tasks a partir do template do padrão
                pattern_tasks, task_id_counter = self._generate_from_pattern(
                    pattern_match=best_match,
                    entities=entities,
                    constraints=constraints,
                    intermediate_repr=intermediate_repr,
                    task_id_counter=task_id_counter
                )

                if pattern_tasks:
                    decomposition_type = 'pattern'
                    tasks.extend(pattern_tasks)
                    for task in pattern_tasks:
                        G.add_node(task.task_id, task=task)

                    # Adicionar arestas para dependências das pattern tasks
                    for task in pattern_tasks:
                        for dep_id in task.dependencies:
                            if dep_id in G:
                                G.add_edge(dep_id, task.task_id)

                    # Registrar métrica de pattern match
                    dag_generation_pattern_matches_total.labels(
                        pattern_id=best_match.pattern_id
                    ).inc()

        # Passo 2: Se não houve pattern match, usar fluxo baseado em objectives
        if not pattern_tasks:
            for objective in objectives:
                # Criar main task com descrição enriquecida
                main_task = self._create_task_from_objective(
                    objective,
                    task_id_counter,
                    entities,
                    constraints,
                    intermediate_repr
                )
                task_id_counter += 1

                # Passo 3: Aplicar task splitting (se disponível)
                if self.task_splitter and self.task_splitter.should_split(main_task):
                    decomposition_type = 'heuristic'
                    subtasks = self.task_splitter.split(
                        main_task,
                        intermediate_repr,
                        current_depth=0
                    )

                    logger.info(
                        'Task dividida em subtasks',
                        original_task_id=main_task.task_id,
                        num_subtasks=len(subtasks)
                    )

                    # Adicionar subtasks ao invés da task original
                    for subtask in subtasks:
                        tasks.append(subtask)
                        G.add_node(subtask.task_id, task=subtask)
                        # Ajustar task_id_counter se necessário
                        subtask_num = subtask.task_id.split('_')[-1]
                        if subtask_num.isdigit():
                            task_id_counter = max(task_id_counter, int(subtask_num) + 1)

                    # Adicionar arestas para dependências das subtasks
                    for subtask in subtasks:
                        for dep_id in subtask.dependencies:
                            if dep_id in G:
                                G.add_edge(dep_id, subtask.task_id)

                    # Encontrar subtask principal (main_operation) para associar support tasks
                    main_operation_subtask = next(
                        (s for s in subtasks if s.metadata and s.metadata.get('subtask_role') == 'main_operation'),
                        None
                    )

                    # Gerar support tasks associadas à subtask principal
                    if main_operation_subtask:
                        support_tasks = self._generate_support_tasks(
                            main_operation_subtask,
                            task_id_counter,
                            constraints
                        )

                        for support_task in support_tasks:
                            tasks.append(support_task)
                            G.add_node(support_task.task_id, task=support_task)
                            # Associar support task à subtask principal
                            G.add_edge(support_task.task_id, main_operation_subtask.task_id)
                            task_id_counter += 1
                else:
                    # Task não foi dividida, adicionar normalmente
                    tasks.append(main_task)
                    G.add_node(main_task.task_id, task=main_task)

                    # Adicionar support tasks para task não dividida
                    support_tasks = self._generate_support_tasks(
                        main_task,
                        task_id_counter,
                        constraints
                    )

                    for support_task in support_tasks:
                        tasks.append(support_task)
                        G.add_node(support_task.task_id, task=support_task)
                        # Adicionar dependência (support -> main)
                        G.add_edge(support_task.task_id, main_task.task_id)
                        task_id_counter += 1

        # Passo 4: Adicionar dependências inter-task (heurísticas)
        self._add_inter_task_dependencies(G, tasks, objectives)

        # Passo 5: Adicionar dependências baseadas em entidades e detectar conflitos
        entity_deps_added, conflicts = self._analyze_entity_dependencies(G, tasks)

        # Passo 6: Validar DAG é acíclico
        if not nx.is_directed_acyclic_graph(G):
            cycles = list(nx.simple_cycles(G))
            logger.error('Ciclos detectados no DAG', cycles=cycles)
            raise ValueError(f'DAG contém ciclos: {cycles}')

        # Passo 7: Detectar paralelismo
        parallel_groups = self._detect_parallel_tasks(G, tasks)

        # Registrar métrica de grupos paralelos
        dag_generation_parallel_groups_total.observe(len(parallel_groups))

        # Passo 8: Gerar ordem de execução topológica
        execution_order = list(nx.topological_sort(G))

        # Passo 9: Calcular duração total (critical path)
        total_duration = self._calculate_critical_path(G, tasks)

        # Passo 10: Gerar visualização de dependências (se há conflitos ou DEBUG)
        visualization = None
        import os
        debug_enabled = os.environ.get('NEURAL_HIVE_DEBUG', '').lower() in ('true', '1', 'yes')
        if conflicts or debug_enabled:
            visualization = self._generate_dependency_visualization(G, tasks, conflicts)
            dag_generation_visualization_generated_total.labels(format='mermaid').inc()

        # Armazenar conflitos nos metadados das tasks envolvidas
        if conflicts:
            for task in tasks:
                task_conflicts = [
                    {
                        'task_a': c.task_a_id,
                        'task_b': c.task_b_id,
                        'entities': c.shared_entities,
                        'severity': c.severity,
                        'resolved': c.resolved
                    }
                    for c in conflicts
                    if task.task_id in (c.task_a_id, c.task_b_id)
                ]
                if task_conflicts:
                    if task.metadata is None:
                        task.metadata = {}
                    task.metadata['conflicts_in_dag'] = task_conflicts

        # Armazenar visualização apenas na primeira task (evita redundância)
        if visualization and tasks:
            first_task = tasks[0]
            if first_task.metadata is None:
                first_task.metadata = {}
            first_task.metadata['dependency_visualization'] = visualization

        # Registrar tempo de geração
        generation_duration = time.time() - start_time

        # Registrar métrica de duração por tipo de decomposição
        dag_generation_duration_seconds.labels(
            decomposition_type=decomposition_type
        ).observe(generation_duration)

        logger.info(
            'DAG gerado',
            num_tasks=len(tasks),
            execution_order=execution_order,
            estimated_duration_ms=total_duration,
            generation_duration_seconds=generation_duration,
            decomposition_type=decomposition_type,
            num_parallel_groups=len(parallel_groups),
            entity_dependencies_added=entity_deps_added,
            conflicts_detected=len(conflicts),
            conflicts_resolved=sum(1 for c in conflicts if c.resolved)
        )

        return tasks, execution_order

    def _generate_from_pattern(
        self,
        pattern_match: 'PatternMatch',
        entities: List[Dict],
        constraints: Dict,
        intermediate_repr: Dict[str, Any],
        task_id_counter: int
    ) -> Tuple[List[TaskNode], int]:
        """
        Gera tasks a partir de template de padrão detectado.

        Args:
            pattern_match: PatternMatch com template de decomposição
            entities: Lista de entidades extraídas
            constraints: Restrições do intent
            intermediate_repr: Representação intermediária completa
            task_id_counter: Contador atual de task IDs

        Returns:
            Tupla (lista de TaskNodes, contador atualizado)
        """
        template = pattern_match.template
        subtask_definitions = template.get('subtasks', [])

        if not subtask_definitions:
            logger.warning(
                'Template de padrão sem subtasks',
                pattern_id=pattern_match.pattern_id
            )
            return [], task_id_counter

        tasks = []
        id_mapping = {}  # Mapear IDs simbólicos para IDs reais

        for subtask_def in subtask_definitions:
            symbolic_id = subtask_def.get('id', f'subtask_{task_id_counter}')
            real_task_id = f'task_{task_id_counter}'
            id_mapping[symbolic_id] = real_task_id

            # Mapear dependências do template para IDs reais
            template_deps = subtask_def.get('dependencies', [])
            real_deps = [id_mapping.get(dep, dep) for dep in template_deps if dep in id_mapping]

            # Construir descrição enriquecida
            description = self._build_enriched_description(
                objective=subtask_def.get('type', 'query'),
                entities=entities,
                constraints=constraints,
                intermediate_repr=intermediate_repr
            )

            # Sobrescrever com descrição do template se disponível
            if subtask_def.get('description'):
                description = subtask_def['description']

            task = TaskNode(
                task_id=real_task_id,
                task_type=subtask_def.get('type', 'query'),
                description=description,
                dependencies=real_deps,
                estimated_duration_ms=subtask_def.get('estimated_duration_ms', 500),
                required_capabilities=subtask_def.get('required_capabilities', []),
                parameters={
                    'entities': entities,
                    'constraints': constraints,
                    'pattern_subtask_id': symbolic_id
                },
                metadata={
                    'pattern_id': pattern_match.pattern_id,
                    'pattern_name': pattern_match.pattern_name,
                    'from_pattern': True,
                    'pattern_confidence': pattern_match.confidence
                }
            )

            tasks.append(task)
            task_id_counter += 1

        logger.info(
            'Tasks geradas do template de padrão',
            pattern_id=pattern_match.pattern_id,
            num_tasks=len(tasks)
        )

        return tasks, task_id_counter

    def _analyze_entity_dependencies(
        self,
        G: nx.DiGraph,
        tasks: List[TaskNode]
    ) -> Tuple[int, List[ConflictInfo]]:
        """
        Analisa dependências baseadas em entidades compartilhadas e detecta conflitos.

        Regras:
        - Write (create/update/delete) antes de Read (query) na mesma entidade
        - Writes na mesma entidade seguem ordem temporal (create → update → delete)
        - Detecta conflitos write-write quando tasks sem dependência operam na mesma entidade
        - Aplica estratégia de resolução de conflitos configurada

        Args:
            G: Grafo NetworkX do DAG
            tasks: Lista de TaskNodes

        Returns:
            Tupla (dependencies_added, conflicts_detected)
        """
        # Construir mapa de entidades por task usando matching avançado
        entity_map: Dict[str, List[Dict]] = {}
        entity_names_map: Dict[str, Set[str]] = {}
        task_map: Dict[str, TaskNode] = {}

        for task in tasks:
            task_map[task.task_id] = task
            entities = task.parameters.get('entities', [])
            entity_map[task.task_id] = entities

            # Extrair identificadores normalizados para matching rápido
            entity_names = set()
            for entity in entities:
                identifiers = self._extract_entity_identifiers(entity)
                entity_names.update(identifiers)
            entity_names_map[task.task_id] = entity_names

        # Tipos de operação write vs read
        write_types = {'create', 'update', 'delete'}
        read_types = {'query', 'validate'}

        # Ordem temporal de writes
        write_order = {'create': 1, 'update': 2, 'delete': 3}

        dependencies_added = 0
        conflicts_detected: List[ConflictInfo] = []

        # Rastrear arestas adicionadas nesta análise para rollback seguro de ciclos
        edges_added_in_analysis: List[Tuple[str, str]] = []

        # Analisar pares de tasks
        task_ids = list(entity_map.keys())
        for i, task_a_id in enumerate(task_ids):
            for task_b_id in task_ids[i + 1:]:
                entities_a = entity_map.get(task_a_id, [])
                entities_b = entity_map.get(task_b_id, [])
                names_a = entity_names_map.get(task_a_id, set())
                names_b = entity_names_map.get(task_b_id, set())

                # Verificar entidades compartilhadas (matching rápido por nomes)
                shared_names = names_a & names_b
                if not shared_names:
                    # Tentar matching avançado se fuzzy OU canonical_types habilitado
                    # (Comment 2 fix: _entities_match faz tanto fuzzy quanto canonical)
                    if self.entity_matching_fuzzy_enabled or self.entity_matching_use_canonical_types:
                        for ent_a in entities_a:
                            for ent_b in entities_b:
                                match, _, _ = self._entities_match(ent_a, ent_b)
                                if match:
                                    # Adicionar nome para tracking
                                    name_a = ent_a.get('name', ent_a.get('value', 'entity'))
                                    shared_names.add(str(name_a).lower())
                                    break
                            if shared_names:
                                break

                if not shared_names:
                    continue

                task_a = task_map[task_a_id]
                task_b = task_map[task_b_id]

                # Determinar ordem baseada em tipo de operação
                type_a = task_a.task_type
                type_b = task_b.task_type

                # Write antes de Read
                if type_a in write_types and type_b in read_types:
                    if not G.has_edge(task_a_id, task_b_id):
                        G.add_edge(task_a_id, task_b_id)
                        edges_added_in_analysis.append((task_a_id, task_b_id))
                        if task_a_id not in task_b.dependencies:
                            task_b.dependencies.append(task_a_id)
                        dependencies_added += 1

                elif type_b in write_types and type_a in read_types:
                    if not G.has_edge(task_b_id, task_a_id):
                        G.add_edge(task_b_id, task_a_id)
                        edges_added_in_analysis.append((task_b_id, task_a_id))
                        if task_b_id not in task_a.dependencies:
                            task_a.dependencies.append(task_b_id)
                        dependencies_added += 1

                # Ordem temporal de writes E detecção de conflitos
                elif type_a in write_types and type_b in write_types:
                    order_a = write_order.get(type_a, 0)
                    order_b = write_order.get(type_b, 0)

                    # Se tipos diferentes de write, ordenar temporalmente
                    if order_a != order_b:
                        if order_a < order_b:
                            if not G.has_edge(task_a_id, task_b_id):
                                G.add_edge(task_a_id, task_b_id)
                                edges_added_in_analysis.append((task_a_id, task_b_id))
                                if task_a_id not in task_b.dependencies:
                                    task_b.dependencies.append(task_a_id)
                                dependencies_added += 1
                        else:
                            if not G.has_edge(task_b_id, task_a_id):
                                G.add_edge(task_b_id, task_a_id)
                                edges_added_in_analysis.append((task_b_id, task_a_id))
                                if task_b_id not in task_a.dependencies:
                                    task_a.dependencies.append(task_b_id)
                                dependencies_added += 1
                    else:
                        # Mesmo tipo de write: CONFLITO DETECTADO
                        # Verificar se já existe dependência (não é conflito)
                        has_dependency = (
                            G.has_edge(task_a_id, task_b_id) or
                            G.has_edge(task_b_id, task_a_id)
                        )

                        if not has_dependency:
                            severity = self._classify_conflict_severity(type_a, type_b)
                            conflict = ConflictInfo(
                                task_a_id=task_a_id,
                                task_b_id=task_b_id,
                                shared_entities=list(shared_names),
                                conflict_type='write-write',
                                severity=severity,
                                metadata={
                                    'task_a_type': type_a,
                                    'task_b_type': type_b
                                }
                            )

                            # Registrar métrica de conflito
                            dag_generation_conflicts_detected_total.labels(
                                conflict_type='write-write',
                                severity=severity
                            ).inc()

                            # Aplicar estratégia de resolução
                            resolved = self._resolve_conflict(
                                G, task_a, task_b, conflict
                            )

                            if resolved:
                                conflict.resolved = True
                                dependencies_added += 1

                            conflicts_detected.append(conflict)

                            logger.warning(
                                'Conflito write-write detectado',
                                task_a_id=task_a_id,
                                task_b_id=task_b_id,
                                shared_entities=list(shared_names),
                                severity=severity,
                                resolution_strategy=conflict.resolution_strategy,
                                resolved=conflict.resolved
                            )

        # Verificar se não criou ciclos
        if dependencies_added > 0:
            while not nx.is_directed_acyclic_graph(G):
                cycles = list(nx.simple_cycles(G))
                if not cycles:
                    break

                cycle = cycles[0]
                cycle_edges = set()
                for i in range(len(cycle)):
                    source = cycle[i]
                    target = cycle[(i + 1) % len(cycle)]
                    cycle_edges.add((source, target))

                # Encontrar aresta do ciclo que foi adicionada nesta análise
                edge_to_remove = None
                for edge in reversed(edges_added_in_analysis):
                    if edge in cycle_edges:
                        edge_to_remove = edge
                        break

                if edge_to_remove:
                    source, target = edge_to_remove
                    G.remove_edge(source, target)
                    edges_added_in_analysis.remove(edge_to_remove)
                    dependencies_added -= 1

                    # Também remover do TaskNode.dependencies
                    target_task = task_map.get(target)
                    if target_task and source in target_task.dependencies:
                        target_task.dependencies.remove(source)

                    logger.warning(
                        'Ciclo detectado, removendo dependência adicionada na análise',
                        removed_edge=f'{source} -> {target}',
                        cycle=cycle
                    )
                else:
                    # Nenhuma aresta do ciclo foi adicionada nesta análise
                    # Não podemos remover arestas que não adicionamos
                    logger.error(
                        'Ciclo detectado mas nenhuma aresta pode ser removida',
                        cycle=cycle,
                        edges_added=edges_added_in_analysis
                    )
                    break

        if dependencies_added > 0:
            # Registrar métrica de dependências adicionadas
            dag_generation_entity_dependencies_added.inc(dependencies_added)

            logger.info(
                'Dependências adicionadas por análise de entidades',
                dependencies_added=dependencies_added,
                conflicts_detected=len(conflicts_detected),
                conflicts_resolved=sum(1 for c in conflicts_detected if c.resolved)
            )

        return dependencies_added, conflicts_detected

    def _resolve_conflict(
        self,
        G: nx.DiGraph,
        task_a: TaskNode,
        task_b: TaskNode,
        conflict: ConflictInfo
    ) -> bool:
        """
        Aplica estratégia de resolução de conflito.

        Estratégias:
        - 'sequential': Ordena por task_id (determinístico)
        - 'priority_based': Usa prioridade das constraints
        - 'notify': Apenas loga warning sem resolver

        Args:
            G: Grafo NetworkX do DAG
            task_a: Primeira task em conflito
            task_b: Segunda task em conflito
            conflict: Informações do conflito

        Returns:
            True se conflito foi resolvido com dependência adicionada
        """
        strategy = self.conflict_resolution_strategy

        if strategy == 'sequential':
            # Ordenar por task_id (ordem determinística)
            if task_a.task_id < task_b.task_id:
                first_task, second_task = task_a, task_b
            else:
                first_task, second_task = task_b, task_a

            # Adicionar dependência: first → second
            if not G.has_edge(first_task.task_id, second_task.task_id):
                G.add_edge(first_task.task_id, second_task.task_id)
                if first_task.task_id not in second_task.dependencies:
                    second_task.dependencies.append(first_task.task_id)

                conflict.resolution_strategy = 'sequential'
                dag_generation_conflicts_resolved_total.labels(
                    resolution_strategy='sequential'
                ).inc()
                return True

        elif strategy == 'priority_based':
            # Usar prioridade das constraints
            priority_order = {'critical': 1, 'high': 2, 'normal': 3, 'low': 4}

            priority_a = task_a.parameters.get('constraints', {}).get('priority', 'normal')
            priority_b = task_b.parameters.get('constraints', {}).get('priority', 'normal')

            order_a = priority_order.get(priority_a, 3)
            order_b = priority_order.get(priority_b, 3)

            # Maior prioridade (menor número) primeiro
            if order_a <= order_b:
                first_task, second_task = task_a, task_b
            else:
                first_task, second_task = task_b, task_a

            if not G.has_edge(first_task.task_id, second_task.task_id):
                G.add_edge(first_task.task_id, second_task.task_id)
                if first_task.task_id not in second_task.dependencies:
                    second_task.dependencies.append(first_task.task_id)

                conflict.resolution_strategy = 'priority_based'
                dag_generation_conflicts_resolved_total.labels(
                    resolution_strategy='priority_based'
                ).inc()
                return True

        elif strategy == 'notify':
            # Apenas notificar, não resolver
            conflict.resolution_strategy = 'notify'
            logger.warning(
                'Conflito requer revisão manual',
                task_a_id=task_a.task_id,
                task_b_id=task_b.task_id,
                severity=conflict.severity
            )
            return False

        return False

    def _detect_parallel_tasks(
        self,
        G: nx.DiGraph,
        tasks: List[TaskNode]
    ) -> Dict[str, List[str]]:
        """
        Detecta tasks que podem executar em paralelo.

        Identifica grupos de tasks no mesmo nível do DAG que não têm
        dependências entre si e podem ser executadas concorrentemente.

        Args:
            G: Grafo NetworkX do DAG
            tasks: Lista de TaskNodes

        Returns:
            Dicionário {parallel_group_id: [task_ids]}
        """
        parallel_groups: Dict[str, List[str]] = {}
        task_map = {task.task_id: task for task in tasks}

        # Usar BFS para identificar níveis do DAG
        # Nível 0: tasks sem dependências (raízes)
        in_degrees = dict(G.in_degree())
        roots = [node for node, degree in in_degrees.items() if degree == 0]

        if not roots:
            return parallel_groups

        # Processar nível por nível
        current_level = roots
        level_num = 0

        while current_level:
            # Tasks no mesmo nível sem dependências entre si podem ser paralelas
            if len(current_level) > 1:
                group_id = f'parallel_group_{level_num}'
                parallel_groups[group_id] = current_level.copy()

                # Adicionar metadata de paralelismo às tasks
                for task_id in current_level:
                    if task_id in task_map:
                        if task_map[task_id].metadata is None:
                            task_map[task_id].metadata = {}
                        task_map[task_id].metadata['parallel_group'] = group_id
                        task_map[task_id].metadata['parallel_level'] = level_num

            # Encontrar próximo nível (sucessores das tasks atuais)
            next_level = set()
            for node in current_level:
                for successor in G.successors(node):
                    # Verificar se todas as dependências do successor foram processadas
                    predecessors = set(G.predecessors(successor))
                    processed = set(task_id for task_id in parallel_groups.get(f'parallel_group_{level_num}', []))
                    for prev_level in range(level_num):
                        processed.update(parallel_groups.get(f'parallel_group_{prev_level}', []))

                    # Adicionar ao próximo nível se todas as dependências foram processadas
                    if predecessors.issubset(processed | set(current_level)):
                        next_level.add(successor)

            current_level = list(next_level)
            level_num += 1

        if parallel_groups:
            logger.info(
                'Grupos paralelos detectados',
                num_groups=len(parallel_groups),
                total_parallelizable_tasks=sum(len(g) for g in parallel_groups.values())
            )

        return parallel_groups

    def _create_task_from_objective(
        self,
        objective: str,
        task_id: int,
        entities: List[Dict],
        constraints: Dict,
        intermediate_repr: Optional[Dict[str, Any]] = None
    ) -> TaskNode:
        """
        Create TaskNode from objective with enriched description.

        The description is enriched with:
        - Domain context from intermediate_repr
        - Security level hints
        - Priority-based optimization hints
        - Entity type summaries
        """
        template = self.task_templates.get(objective, self.task_templates['query'])

        # Extrair qos e risk_band para enriquecimento
        qos = constraints.get('qos')
        risk_band = intermediate_repr.get('risk_band') if intermediate_repr else None
        if not risk_band:
            risk_band = constraints.get('risk_band')

        # Build enriched description
        description = self._build_enriched_description(
            objective=objective,
            entities=entities,
            constraints=constraints,
            intermediate_repr=intermediate_repr,
            qos=qos,
            risk_band=risk_band
        )

        # Validate description quality
        domain = intermediate_repr.get('domain', 'code-quality') if intermediate_repr else 'code-quality'
        security_level = constraints.get('security_level', 'internal')
        qos = constraints.get('qos')

        quality = self.description_validator.validate_description(
            description=description,
            domain=domain,
            security_level=security_level,
            qos=qos
        )

        if quality['score'] < 0.6:
            logger.warning(
                "low_quality_task_description",
                task_id=f'task_{task_id}',
                score=quality['score'],
                issues=quality['issues'],
                original_description=description
            )
            # Auto-improve if score is very low
            if quality['score'] < 0.4:
                description = self.description_validator.suggest_improvements(
                    description=description,
                    context={
                        'domain': domain,
                        'security_level': security_level,
                        'priority': constraints.get('priority', 'normal'),
                        'entities': entities,
                        'qos': qos
                    }
                )
                logger.info(
                    "description_auto_improved",
                    task_id=f'task_{task_id}',
                    improved_description=description
                )

        return TaskNode(
            task_id=f'task_{task_id}',
            task_type=template['type'],
            description=description,
            dependencies=[],
            estimated_duration_ms=template['estimated_duration_ms'],
            required_capabilities=template['required_capabilities'],
            parameters={
                'objective': objective,
                'entities': entities,
                'constraints': constraints
            },
            metadata={
                'description_quality_score': quality['score'],
                'domain': domain,
                'security_level': security_level
            }
        )

    def _build_enriched_description(
        self,
        objective: str,
        entities: List[Dict],
        constraints: Dict,
        intermediate_repr: Optional[Dict[str, Any]] = None,
        qos: Optional[str] = None,
        risk_band: Optional[str] = None
    ) -> str:
        """
        Build an enriched task description with domain context.

        Structure: "[Action verb] [entity context] [security hints] [qos hints] [domain hints] ([metadata])"

        Args:
            objective: Objetivo da tarefa (create, update, query, etc.)
            entities: Lista de entidades envolvidas
            constraints: Restrições (security_level, priority, qos, etc.)
            intermediate_repr: Representação intermediária com domain e risk_band
            qos: Semântica de QoS (exactly_once, at_least_once, at_most_once)
            risk_band: Banda de risco (low, medium, high, critical)

        Example: "Create and initialize user profile with authentication and AES-256 encryption
                  with idempotency guarantees following microservice patterns
                  (security-analysis, confidential, high priority, high risk)"
        """
        parts = []

        # 1. Action verb phrase (rotate through options for variety)
        action_verbs = OBJECTIVE_ACTION_VERBS.get(objective, [f"{objective.capitalize()} and process"])
        verb_idx = self._action_verb_index % len(action_verbs)
        self._action_verb_index += 1
        action_phrase = action_verbs[verb_idx]
        parts.append(action_phrase)

        # 2. Entity context
        entity_summary = self._summarize_entities(entities)
        if entity_summary:
            parts.append(entity_summary)
        else:
            parts.append("data resources")

        # 3. Security hints (for confidential/restricted)
        security_level = constraints.get('security_level', 'internal')
        security_hint = SECURITY_HINTS.get(security_level, '')
        if security_hint:
            parts.append(security_hint)

        # 4. Priority hints (for high/critical)
        priority = constraints.get('priority', 'normal')
        priority_hint = PRIORITY_HINTS.get(priority, '')
        if priority_hint:
            parts.append(priority_hint)

        # 5. QoS hints (quando especificado)
        if qos:
            qos_hint = QOS_HINTS.get(qos, '')
            if qos_hint:
                parts.append(qos_hint)

        # 6. Domain context hints
        domain = intermediate_repr.get('domain', 'code-quality') if intermediate_repr else 'code-quality'
        domain_hint = DOMAIN_CONTEXT_HINTS.get(domain, '')
        if domain_hint:
            parts.append(domain_hint)

        # 7. Metadata suffix (incluindo risk_band quando disponível)
        metadata_parts = [domain]
        if security_level and security_level != 'internal':
            metadata_parts.append(security_level)
        if priority and priority != 'normal':
            metadata_parts.append(f"{priority} priority")
        else:
            metadata_parts.append("normal priority")

        # Adicionar risk_band ao metadata quando disponível
        if risk_band:
            risk_hint = RISK_BAND_HINTS.get(risk_band, '')
            if risk_hint:
                metadata_parts.append(risk_hint)

        metadata_suffix = f"({', '.join(metadata_parts)})"

        # Join all parts
        description = ' '.join(parts) + ' ' + metadata_suffix

        return description

    def _summarize_entities(self, entities: List[Dict]) -> str:
        """
        Summarize entities into a readable context string.

        Returns strings like:
        - "user profile and authentication data"
        - "order transaction records"
        - "API endpoint configuration"
        """
        if not entities:
            return ""

        # Extract entity types and values
        entity_types = []
        entity_values = []

        for entity in entities[:3]:  # Limit to first 3 for brevity
            e_type = entity.get('type', entity.get('entity_type', ''))
            e_value = entity.get('value', entity.get('name', ''))

            if e_type:
                entity_types.append(e_type.lower().replace('_', ' '))
            if e_value and isinstance(e_value, str):
                entity_values.append(e_value.lower().replace('_', ' '))

        # Build summary
        if entity_values and entity_types:
            primary_value = entity_values[0]
            primary_type = entity_types[0]
            return f"{primary_value} {primary_type} data"
        elif entity_types:
            return f"{', '.join(entity_types[:2])} data"
        elif entity_values:
            return f"{entity_values[0]} resources"

        return ""

    def _generate_support_tasks(
        self,
        main_task: TaskNode,
        start_id: int,
        constraints: Dict
    ) -> List[TaskNode]:
        """
        Generate support tasks (validation, transformation, monitoring).

        Support tasks are enriched with specific descriptions based on:
        - Security level requirements
        - Priority level requirements
        - Main task type context
        """
        support_tasks = []
        current_id = start_id

        security_level = constraints.get('security_level', 'internal')
        priority = constraints.get('priority', 'normal')

        # Add validation task for high security levels
        if security_level in ['confidential', 'restricted']:
            # Build enriched security validation description
            security_desc = (
                f"Verify security compliance and audit access controls for {main_task.task_type} operation "
                f"with authentication validation and permission verification "
                f"({security_level} data, requires encryption audit)"
            )

            validate_task = TaskNode(
                task_id=f'task_{current_id}',
                task_type='validate',
                description=security_desc,
                dependencies=[],
                estimated_duration_ms=300,
                required_capabilities=['security'],
                parameters={
                    'validation_type': 'security',
                    'security_level': security_level,
                    'main_task_id': main_task.task_id
                },
                metadata={
                    'support_task_type': 'security_validation',
                    'security_level': security_level
                }
            )
            support_tasks.append(validate_task)
            main_task.dependencies.append(validate_task.task_id)
            current_id += 1

            # Add audit logging task for restricted data
            if security_level == 'restricted':
                audit_desc = (
                    f"Log audit trail with encryption for compliance and regulatory requirements "
                    f"tracking all access to {main_task.task_type} operation with tamper-proof logging "
                    f"(restricted data, requires audit retention)"
                )

                audit_task = TaskNode(
                    task_id=f'task_{current_id}',
                    task_type='validate',
                    description=audit_desc,
                    dependencies=[],
                    estimated_duration_ms=200,
                    required_capabilities=['logging', 'security'],
                    parameters={
                        'validation_type': 'audit_logging',
                        'security_level': security_level,
                        'main_task_id': main_task.task_id
                    },
                    metadata={
                        'support_task_type': 'audit_logging',
                        'security_level': security_level
                    }
                )
                support_tasks.append(audit_task)
                current_id += 1

        # Add monitoring task for critical priority
        if priority == 'critical':
            monitoring_desc = (
                f"Monitor execution metrics and alert on anomalies for {main_task.task_type} operation "
                f"with real-time performance tracking and SLA compliance verification "
                f"(critical priority, requires immediate alerting)"
            )

            monitor_task = TaskNode(
                task_id=f'task_{current_id}',
                task_type='validate',
                description=monitoring_desc,
                dependencies=[],
                estimated_duration_ms=150,
                required_capabilities=['monitoring', 'alerting'],
                parameters={
                    'validation_type': 'monitoring',
                    'priority': priority,
                    'main_task_id': main_task.task_id
                },
                metadata={
                    'support_task_type': 'performance_monitoring',
                    'priority': priority
                }
            )
            support_tasks.append(monitor_task)

        return support_tasks

    def _add_inter_task_dependencies(
        self,
        G: nx.DiGraph,
        tasks: List[TaskNode],
        objectives: List[str]
    ):
        """Add dependencies between main tasks"""
        # Simple heuristic: create -> update -> query
        task_by_type = {
            task.task_type: task
            for task in tasks
            if task.task_type in objectives
        }

        if 'create' in task_by_type and 'update' in task_by_type:
            G.add_edge(
                task_by_type['create'].task_id,
                task_by_type['update'].task_id
            )
            task_by_type['update'].dependencies.append(
                task_by_type['create'].task_id
            )

        if 'update' in task_by_type and 'query' in task_by_type:
            G.add_edge(
                task_by_type['update'].task_id,
                task_by_type['query'].task_id
            )
            task_by_type['query'].dependencies.append(
                task_by_type['update'].task_id
            )

    def _calculate_critical_path(
        self,
        G: nx.DiGraph,
        tasks: List[TaskNode]
    ) -> int:
        """Calculate critical path (total duration)"""
        task_durations = {
            task.task_id: task.estimated_duration_ms or 0
            for task in tasks
        }

        try:
            longest_path = nx.dag_longest_path(
                G,
                weight=lambda u, v, d: task_durations.get(v, 0)
            )
            total_duration = sum(
                task_durations.get(task_id, 0)
                for task_id in longest_path
            )
            return total_duration
        except:
            # Fallback: sum all durations
            return sum(task_durations.values())

    def _generate_dependency_visualization(
        self,
        G: nx.DiGraph,
        tasks: List[TaskNode],
        conflicts: List[ConflictInfo]
    ) -> Dict[str, Any]:
        """
        Gera visualização das dependências em formato Mermaid e matriz.

        Args:
            G: Grafo NetworkX do DAG
            tasks: Lista de TaskNodes
            conflicts: Lista de conflitos detectados

        Returns:
            Dicionário com mermaid_diagram, dependency_matrix, conflict_report
        """
        task_map = {t.task_id: t for t in tasks}

        # Gerar diagrama Mermaid
        mermaid_lines = ['graph TD']

        # Cores por tipo de task
        type_colors = {
            'create': '#90EE90',  # light green
            'update': '#FFD700',  # gold
            'delete': '#FF6B6B',  # light red
            'query': '#87CEEB',   # light blue
            'validate': '#DDA0DD',  # plum
            'transform': '#F0E68C'  # khaki
        }

        # Adicionar nós
        for task in tasks:
            # Extrair entidades para label
            entities = task.parameters.get('entities', [])
            entity_names = [
                str(e.get('name', e.get('value', '')))[:15]
                for e in entities[:2]
            ]
            entity_label = ', '.join(entity_names) if entity_names else 'no entities'

            # Truncar descrição
            desc = task.description[:30] + '...' if len(task.description) > 30 else task.description
            desc = desc.replace('"', "'")

            label = f'{task.task_id}["{task.task_type}: {desc}<br/>entities: {entity_label}"]'
            mermaid_lines.append(f'    {label}')

        # Adicionar arestas
        conflict_edges = set()
        for conflict in conflicts:
            if conflict.resolved:
                # Aresta de resolução de conflito
                conflict_edges.add((conflict.task_a_id, conflict.task_b_id))
                conflict_edges.add((conflict.task_b_id, conflict.task_a_id))

        for edge in G.edges():
            source, target = edge
            if (source, target) in conflict_edges:
                # Aresta de conflito resolvido (estilo diferenciado)
                mermaid_lines.append(f'    {source} -.->|conflict resolved| {target}')
            else:
                # Aresta normal
                mermaid_lines.append(f'    {source} --> {target}')

        # Adicionar estilos de cor
        for task in tasks:
            color = type_colors.get(task.task_type, '#FFFFFF')
            mermaid_lines.append(f'    style {task.task_id} fill:{color}')

        mermaid_diagram = '\n'.join(mermaid_lines)

        # Gerar matriz de dependências
        task_ids = [t.task_id for t in tasks]
        matrix = {}
        for task_id in task_ids:
            matrix[task_id] = {}
            for other_id in task_ids:
                if G.has_edge(task_id, other_id):
                    # Classificar tipo de dependência
                    if (task_id, other_id) in conflict_edges:
                        matrix[task_id][other_id] = 'conflict_resolved'
                    else:
                        matrix[task_id][other_id] = 'dependency'
                else:
                    matrix[task_id][other_id] = 'none'

        # Gerar relatório de conflitos
        conflict_report = self._generate_conflict_report(conflicts)

        return {
            'mermaid_diagram': mermaid_diagram,
            'dependency_matrix': matrix,
            'conflict_report': conflict_report
        }

    def _generate_conflict_report(
        self,
        conflicts: List[ConflictInfo]
    ) -> Dict[str, Any]:
        """
        Gera relatório legível de conflitos detectados.

        Args:
            conflicts: Lista de conflitos

        Returns:
            Dicionário com summary, details, recommendations
        """
        if not conflicts:
            return {
                'summary': 'Nenhum conflito detectado',
                'total_conflicts': 0,
                'resolved': 0,
                'pending': 0,
                'details': [],
                'recommendations': []
            }

        resolved = sum(1 for c in conflicts if c.resolved)
        pending = len(conflicts) - resolved

        details = []
        recommendations = []

        for conflict in conflicts:
            detail = {
                'task_a': conflict.task_a_id,
                'task_b': conflict.task_b_id,
                'entities': conflict.shared_entities,
                'type': conflict.conflict_type,
                'severity': conflict.severity,
                'resolved': conflict.resolved,
                'resolution_strategy': conflict.resolution_strategy
            }
            details.append(detail)

            if not conflict.resolved:
                if conflict.severity == 'critical':
                    recommendations.append(
                        f'CRÍTICO: Revisar manualmente conflito entre {conflict.task_a_id} '
                        f'e {conflict.task_b_id} em entidades {conflict.shared_entities}'
                    )
                elif conflict.severity == 'high':
                    recommendations.append(
                        f'ALTO: Considerar adicionar dependência explícita entre '
                        f'{conflict.task_a_id} e {conflict.task_b_id}'
                    )

        severity_counts = {}
        for conflict in conflicts:
            severity_counts[conflict.severity] = severity_counts.get(conflict.severity, 0) + 1

        return {
            'summary': f'{len(conflicts)} conflito(s) detectado(s), {resolved} resolvido(s)',
            'total_conflicts': len(conflicts),
            'resolved': resolved,
            'pending': pending,
            'by_severity': severity_counts,
            'details': details,
            'recommendations': recommendations
        }

    def _generate_dependency_matrix(
        self,
        G: nx.DiGraph,
        tasks: List[TaskNode]
    ) -> List[Dict[str, Any]]:
        """
        Gera matriz de dependências em formato CSV/JSON.

        Args:
            G: Grafo NetworkX do DAG
            tasks: Lista de TaskNodes

        Returns:
            Lista de dicionários representando linhas da matriz
        """
        task_map = {t.task_id: t for t in tasks}
        rows = []

        for task in tasks:
            row = {
                'task_id': task.task_id,
                'task_type': task.task_type,
                'dependencies': task.dependencies.copy(),
                'dependents': list(G.successors(task.task_id)),
                'entities': [
                    e.get('name', e.get('value', 'unknown'))
                    for e in task.parameters.get('entities', [])
                ],
                'in_degree': G.in_degree(task.task_id),
                'out_degree': G.out_degree(task.task_id)
            }
            rows.append(row)

        dag_generation_visualization_generated_total.labels(format='matrix').inc()
        return rows
