"""Detector de divergências entre arquitetura planejada e implementada."""

from typing import Any, Dict, List, Optional

from src.models.architecture import ArchitecturePlan
from src.models.evolution import DriftDetection, DriftType
from src.models.validation import Severity


class DriftDetector:
    """Detecta divergências entre plano e implementação."""

    def detect_drifts(
        self, planned: ArchitecturePlan, implemented: Dict[str, Any]
    ) -> List[DriftDetection]:
        """Compara plano planejado com implementação detectada.

        Args:
            planned: Plano arquitetural original
            implemented: Dados da implementação (do Scout/OPA)

        Returns:
            Lista de divergências detectadas
        """
        drifts = []

        # 1. Verificar tipo de arquitetura
        arch_drift = self._check_architecture_type(planned, implemented)
        if arch_drift:
            drifts.append(arch_drift)

        # 2. Verificar componentes
        component_drifts = self._check_components(planned, implemented)
        drifts.extend(component_drifts)

        # 3. Verificar padrões
        pattern_drifts = self._check_patterns(planned, implemented)
        drifts.extend(pattern_drifts)

        # 4. Verificar stack tecnológica
        stack_drifts = self._check_stack(planned, implemented)
        drifts.extend(stack_drifts)

        return drifts

    def _check_architecture_type(
        self, planned: ArchitecturePlan, implemented: Dict[str, Any]
    ) -> Optional[DriftDetection]:
        """Verifica se o tipo de arquitetura divergiu."""
        planned_type = planned.architecture_type.value
        impl_type = implemented.get("architecture_type", planned_type)

        if planned_type != impl_type:
            return DriftDetection(
                drift_type=DriftType.ARCHITECTURE,
                description=f"Tipo de arquitetura divergiu: {planned_type} → {impl_type}",
                expected=planned_type,
                actual=impl_type,
                severity=Severity.HIGH,
            )
        return None

    def _check_components(
        self, planned: ArchitecturePlan, implemented: Dict[str, Any]
    ) -> List[DriftDetection]:
        """Verifica divergências nos componentes."""
        drifts = []
        impl_components = {c.get("name"): c for c in implemented.get("components", [])}

        for comp in planned.components:
            name = comp.name
            if name not in impl_components:
                drifts.append(
                    DriftDetection(
                        drift_type=DriftType.COMPONENTS,
                        description=f"Componente planejado não encontrado: {name}",
                        expected=name,
                        actual="missing",
                        severity=Severity.MEDIUM,
                    )
                )
            else:
                impl_comp = impl_components[name]
                if impl_comp.get("stack") != comp.stack:
                    drifts.append(
                        DriftDetection(
                            drift_type=DriftType.STACK,
                            description=f"Stack do componente {name} divergiu",
                            expected=comp.stack,
                            actual=impl_comp.get("stack", "unknown"),
                            severity=Severity.LOW,
                        )
                    )

        return drifts

    def _check_patterns(
        self, planned: ArchitecturePlan, implemented: Dict[str, Any]
    ) -> List[DriftDetection]:
        """Verifica padrões não aplicados."""
        drifts = []
        impl_patterns = set(implemented.get("patterns", []))

        for pattern in planned.patterns:
            pattern_name = pattern.value if hasattr(pattern, "value") else str(pattern)
            if pattern_name not in impl_patterns:
                drifts.append(
                    DriftDetection(
                        drift_type=DriftType.PATTERNS,
                        description=f"Padrão planejado não aplicado: {pattern_name}",
                        expected=pattern_name,
                        actual="not_applied",
                        severity=Severity.MEDIUM,
                    )
                )

        return drifts

    def _check_stack(
        self, planned: ArchitecturePlan, implemented: Dict[str, Any]
    ) -> List[DriftDetection]:
        """Verifica divergências na stack tecnológica."""
        drifts = []
        impl_stack = implemented.get("tech_stack", {})

        planned_stacks = {c.stack for c in planned.components}
        for stack in planned_stacks:
            if stack not in impl_stack.get("frameworks", []):
                drifts.append(
                    DriftDetection(
                        drift_type=DriftType.STACK,
                        description=f"Framework planejado não encontrado: {stack}",
                        expected=stack,
                        actual=f"available: {impl_stack.get('frameworks', [])}",
                        severity=Severity.LOW,
                    )
                )

        return drifts
