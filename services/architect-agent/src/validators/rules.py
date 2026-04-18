"""Regras de validação de arquitetura (SOLID)."""

from enum import Enum
from typing import Any


class SOLIDPrinciple(str, Enum):
    """Princípios SOLID para validação."""

    SRP = "srp"  # Single Responsibility
    OCP = "ocp"  # Open/Closed
    LSP = "lsp"  # Liskov Substitution
    ISP = "isp"  # Interface Segregation
    DIP = "dip"  # Dependency Inversion


class ArchitecturalRules:
    """Validador de regras arquiteturais SOLID."""

    @staticmethod
    def check_srp(class_info: dict[str, Any]) -> dict[str, Any] | None:
        """Single Responsibility: classe com muitas responsabilidades."""
        methods = class_info.get("methods", [])
        if isinstance(methods, list) and len(methods) > 15:
            return {
                "type": SOLIDPrinciple.SRP.value,
                "severity": "high",
                "location": class_info.get("file", "unknown"),
                "description": f"Classe {class_info.get('name')} com {len(methods)} métodos",
                "suggestion": "Considerar dividir em classes menores",
            }
        return None

    @staticmethod
    def check_ocp(class_info: dict[str, Any]) -> dict[str, Any] | None:
        """Open/Closed: muitos condicionais tipo-dependent."""
        if_statements = class_info.get("if_statements", 0)
        switch_statements = class_info.get("switch_statements", 0)
        if if_statements > 10 or switch_statements > 5:
            return {
                "type": SOLIDPrinciple.OCP.value,
                "severity": "medium",
                "location": class_info.get("file", "unknown"),
                "description": f"Alto acoplamento com condicionais ({if_statements} ifs, {switch_statements} switches)",
                "suggestion": "Usar polimorfismo/strategy pattern",
            }
        return None

    @staticmethod
    def check_lsp(insights: dict[str, Any]) -> list[dict[str, Any]]:
        """Liskov: detecta override problemático."""
        violations: list[dict[str, Any]] = []
        for inheritance in insights.get("inheritance", []):
            if inheritance.get("overrides_method_without_calling_super"):
                violations.append(
                    {
                        "type": SOLIDPrinciple.LSP.value,
                        "severity": "medium",
                        "location": inheritance.get("file", "unknown"),
                        "description": f"Override sem chamar super() em {inheritance.get('method')}",
                        "suggestion": "Garantir compatibilidade com classe base",
                    }
                )
        return violations

    @staticmethod
    def check_isp(insights: dict[str, Any]) -> list[dict[str, Any]]:
        """Interface Segregation: interfaces com muitos métodos."""
        violations: list[dict[str, Any]] = []
        for interface in insights.get("interfaces", []):
            if interface.get("method_count", 0) > 10:
                violations.append(
                    {
                        "type": SOLIDPrinciple.ISP.value,
                        "severity": "medium",
                        "location": interface.get("file", "unknown"),
                        "description": f"Interface {interface.get('name')} com {interface.get('method_count')} métodos",
                        "suggestion": "Dividir em interfaces específicas",
                    }
                )
        return violations

    @staticmethod
    def check_dip(insights: dict[str, Any]) -> list[dict[str, Any]]:
        """Dependency Inversion: dependência de concretas."""
        violations: list[dict[str, Any]] = []
        for dependency in insights.get("dependencies", []):
            if dependency.get("is_concrete") and not dependency.get("is_interface"):
                violations.append(
                    {
                        "type": SOLIDPrinciple.DIP.value,
                        "severity": "low",
                        "location": dependency.get("file", "unknown"),
                        "description": f"Dependência direta de classe concreta {dependency.get('name')}",
                        "suggestion": "Usar injeção de dependência com interfaces",
                    }
                )
        return violations

    @classmethod
    def validate_all(
        cls, patterns: list[dict[str, Any]], insights: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Executa todas as validações SOLID."""
        violations: list[dict[str, Any]] = []

        # SRP e OCP por classe
        for pattern in patterns:
            if pattern.get("type") == "class":
                if v := cls.check_srp(pattern):
                    violations.append(v)
                if v := cls.check_ocp(pattern):
                    violations.append(v)

        # LSP, ISP, DIP dos insights
        violations.extend(cls.check_lsp(insights))
        violations.extend(cls.check_isp(insights))
        violations.extend(cls.check_dip(insights))

        return violations
