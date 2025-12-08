"""
DAG Generator - Converts intermediate representation to task graph

Generates Directed Acyclic Graphs of executable tasks from parsed intents.
Enriches task descriptions with domain context for improved heuristic evaluation.
"""

import structlog
import networkx as nx
from typing import List, Dict, Any, Tuple, Optional

from src.models.cognitive_plan import TaskNode
from src.services.description_validator import DescriptionQualityValidator, get_validator

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


class DAGGenerator:
    """Generator of task DAGs from objectives and constraints"""

    def __init__(self):
        self.task_templates = self._load_task_templates()
        self.description_validator = get_validator()
        self._action_verb_index = 0  # For rotating action verbs

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

    def generate(self, intermediate_repr: Dict[str, Any]) -> Tuple[List[TaskNode], List[str]]:
        """
        Generate DAG of tasks

        Args:
            intermediate_repr: Parsed intent representation

        Returns:
            Tuple of (tasks, execution_order)
        """
        objectives = intermediate_repr.get('objectives', [])
        entities = intermediate_repr.get('entities', [])
        constraints = intermediate_repr.get('constraints', {})

        # Create NetworkX graph
        G = nx.DiGraph()

        # Generate tasks
        tasks = []
        task_id_counter = 0

        for objective in objectives:
            # Create main task with enriched description
            main_task = self._create_task_from_objective(
                objective,
                task_id_counter,
                entities,
                constraints,
                intermediate_repr
            )
            tasks.append(main_task)
            G.add_node(main_task.task_id, task=main_task)
            task_id_counter += 1

            # Add support tasks (validation, transformation)
            support_tasks = self._generate_support_tasks(
                main_task,
                task_id_counter,
                constraints
            )

            for support_task in support_tasks:
                tasks.append(support_task)
                G.add_node(support_task.task_id, task=support_task)

                # Add dependency (support -> main)
                G.add_edge(support_task.task_id, main_task.task_id)

                task_id_counter += 1

        # Add inter-task dependencies
        self._add_inter_task_dependencies(G, tasks, objectives)

        # Validate DAG is acyclic
        if not nx.is_directed_acyclic_graph(G):
            cycles = list(nx.simple_cycles(G))
            logger.error('Cycles detected in DAG', cycles=cycles)
            raise ValueError(f'DAG contains cycles: {cycles}')

        # Generate topological execution order
        execution_order = list(nx.topological_sort(G))

        # Calculate total duration
        total_duration = self._calculate_critical_path(G, tasks)

        logger.info(
            'DAG gerado',
            num_tasks=len(tasks),
            execution_order=execution_order,
            estimated_duration_ms=total_duration
        )

        return tasks, execution_order

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
