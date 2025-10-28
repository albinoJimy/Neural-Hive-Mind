"""
DAG Generator - Converts intermediate representation to task graph

Generates Directed Acyclic Graphs of executable tasks from parsed intents.
"""

import structlog
import networkx as nx
from typing import List, Dict, Any, Tuple

from src.models.cognitive_plan import TaskNode

logger = structlog.get_logger()


class DAGGenerator:
    """Generator of task DAGs from objectives and constraints"""

    def __init__(self):
        self.task_templates = self._load_task_templates()

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
            # Create main task
            main_task = self._create_task_from_objective(
                objective,
                task_id_counter,
                entities,
                constraints
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
        constraints: Dict
    ) -> TaskNode:
        """Create TaskNode from objective"""
        template = self.task_templates.get(objective, self.task_templates['query'])

        return TaskNode(
            task_id=f'task_{task_id}',
            task_type=template['type'],
            description=f'{objective.capitalize()} operation',
            dependencies=[],
            estimated_duration_ms=template['estimated_duration_ms'],
            required_capabilities=template['required_capabilities'],
            parameters={
                'objective': objective,
                'entities': entities,
                'constraints': constraints
            },
            metadata={}
        )

    def _generate_support_tasks(
        self,
        main_task: TaskNode,
        start_id: int,
        constraints: Dict
    ) -> List[TaskNode]:
        """Generate support tasks (validation, transformation)"""
        support_tasks = []

        # Add validation if high security level
        security_level = constraints.get('security_level', 'internal')
        if security_level in ['confidential', 'restricted']:
            validate_task = TaskNode(
                task_id=f'task_{start_id}',
                task_type='validate',
                description='Security validation',
                dependencies=[],
                estimated_duration_ms=300,
                required_capabilities=['security'],
                parameters={'validation_type': 'security'},
                metadata={}
            )
            support_tasks.append(validate_task)
            main_task.dependencies.append(validate_task.task_id)

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
