"""Fingerprint extraction from CognitivePlan."""

import hashlib
from typing import Dict, Any, List

import structlog

from .models import Fingerprint, TaskCountRange, DurationRange

logger = structlog.get_logger()


class FingerprintExtractor:
    """Extrai fingerprint de um CognitivePlan para pattern matching."""

    def __init__(self):
        self.logger = logger

    def extract(self, cognitive_plan: Dict[str, Any]) -> Fingerprint:
        """
        Extrai fingerprint do plano cognitivo.

        Args:
            cognitive_plan: Plano no formato do CognitivePlan

        Returns:
            Fingerprint para matching
        """
        tasks = cognitive_plan.get("tasks", [])

        # Extrair campos básicos
        domain = cognitive_plan.get("original_domain", "unknown")
        priority = cognitive_plan.get("original_priority", "normal")

        # Task count range
        task_count_range = self._get_task_count_range(len(tasks))

        # Task tipos únicos
        task_types = self._extract_task_types(tasks)

        # Dependências
        avg_dependency_count = self._calculate_avg_dependencies(tasks)
        has_conditional_deps = self._has_conditional_dependencies(tasks)

        # Duração estimada
        estimated_duration_range = self._get_duration_range(tasks)

        # Complexity signature
        complexity_signature = self._generate_signature(
            domain, task_count_range, task_types, avg_dependency_count
        )

        self.logger.debug(
            "Extracted fingerprint",
            plan_id=cognitive_plan.get("plan_id"),
            domain=domain,
            task_count=len(tasks),
            signature=complexity_signature,
        )

        return Fingerprint(
            domain=domain,
            priority=priority,
            task_count_range=task_count_range,
            task_types=task_types,
            avg_dependency_count=avg_dependency_count,
            has_conditional_deps=has_conditional_deps,
            estimated_duration_range=estimated_duration_range,
            complexity_signature=complexity_signature,
        )

    def _get_task_count_range(self, count: int) -> TaskCountRange:
        """Determina range baseado na contagem de tarefas."""
        if count < 5:
            return TaskCountRange.SMALL
        elif count <= 20:
            return TaskCountRange.MEDIUM
        else:
            return TaskCountRange.LARGE

    def _extract_task_types(self, tasks: List[Dict]) -> List[str]:
        """Extrai tipos unicos de tarefas."""
        types_set = set()
        for task in tasks:
            task_type = task.get("task_type", "UNKNOWN")
            types_set.add(task_type)
        return sorted(list(types_set))

    def _calculate_avg_dependencies(self, tasks: List[Dict]) -> float:
        """Calcula media de dependencias por tarefa."""
        if not tasks:
            return 0.0

        total_deps = 0
        for task in tasks:
            deps = task.get("dependencies", [])
            total_deps += len(deps)

        return round(total_deps / len(tasks), 2)

    def _has_conditional_dependencies(self, tasks: List[Dict]) -> bool:
        """Verifica se ha dependencias condicionais."""
        for task in tasks:
            deps = task.get("dependencies", [])
            for dep in deps:
                if isinstance(dep, dict) and "condition" in dep:
                    return True
        return False

    def _get_duration_range(self, tasks: List[Dict]) -> DurationRange:
        """Determina range de duracao estimada."""
        total_ms = 0
        for task in tasks:
            total_ms += task.get("estimated_duration_ms", 0)

        if not tasks:
            avg_ms = 0
        else:
            avg_ms = total_ms / len(tasks)

        if avg_ms < 1000:
            return DurationRange.SHORT
        elif avg_ms <= 10000:
            return DurationRange.MEDIUM
        else:
            return DurationRange.LONG

    def _generate_signature(
        self,
        domain: str,
        task_count_range: TaskCountRange,
        task_types: List[str],
        avg_dependency_count: float,
    ) -> str:
        """
        Gera signature de complexidade para matching.

        Formato: {domain[0].upper()}-{task_count[0].upper()}-{hash}
        """
        # Hash dos tipos de tarefas
        types_str = ",".join(sorted(task_types))
        types_hash = hashlib.md5(types_str.encode()).hexdigest()[:4]

        # Prefixo baseado em domain e count
        prefix = f"{domain[0].upper()}-{task_count_range.value[0].upper()}-"

        return f"{prefix}{types_hash}"
