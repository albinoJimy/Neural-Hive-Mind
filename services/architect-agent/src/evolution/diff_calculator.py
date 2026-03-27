"""Calculador de diferenças entre versões de arquitetura."""

from typing import List

from src.models.evolution import ArchitectureDiff
from src.models.architecture import ArchitecturePlan


class DiffCalculator:
    """Calcula diferenças entre dois planos de arquitetura."""

    def calculate_diff(
        self, plan_old: ArchitecturePlan, plan_new: ArchitecturePlan
    ) -> ArchitectureDiff:
        """Calcula diferenças entre versões.

        Args:
            plan_old: Plano arquitetural antigo
            plan_new: Novo plano arquitetural

        Returns:
            ArchitectureDiff com mudanças detectadas
        """
        # Componentes
        old_components = {c.name for c in plan_old.components}
        new_components = {c.name for c in plan_new.components}

        additions = list(new_components - old_components)
        removals = list(old_components - new_components)

        modifications = []
        for comp in plan_new.components:
            if comp.name in old_components:
                old_comp = next(c for c in plan_old.components if c.name == comp.name)
                if comp.stack != old_comp.stack:
                    modifications.append(f"{comp.name}: stack {old_comp.stack} → {comp.stack}")

        # Verificar se requer migração
        requires_migration = self._check_migration_needed(plan_old, plan_new)

        return ArchitectureDiff(
            plan_id_old=plan_old.plan_id,
            plan_id_new=plan_new.plan_id,
            additions=additions,
            removals=removals,
            modifications=modifications,
            requires_migration=requires_migration
        )

    def _check_migration_needed(
        self, plan_old: ArchitecturePlan, plan_new: ArchitecturePlan
    ) -> bool:
        """Verifica se mudanças requerem migração de dados/infra."""
        # Mudança de tipo de arquitetura requer migração
        if plan_old.architecture_type != plan_new.architecture_type:
            return True

        # Adição/remoção de componentes com replicação
        old_replicas = {c.name: c.replicas for c in plan_old.components if c.replicas}
        new_replicas = {c.name: c.replicas for c in plan_new.components if c.replicas}
        if old_replicas != new_replicas:
            return True

        return False
