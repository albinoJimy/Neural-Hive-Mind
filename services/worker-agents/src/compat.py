"""
Polyfill de compatibilidade para Python 3.10.

Fornece StrEnum, datetime.UTC e outros recursos do Python 3.11+ que não existem
em versões anteriores.
"""

import sys
from datetime import timezone
from enum import Enum
from typing import TypeVar

# Detectar versão do Python
PY311_PLUS = sys.version_info >= (3, 11)

if PY311_PLUS:
    # Python 3.11+: usar StrEnum nativo
    from enum import StrEnum as _StrEnum  # type: ignore

    StrEnum = _StrEnum
    # Python 3.11+: usar UTC nativo
    from datetime import UTC as _UTC  # type: ignore

    UTC = _UTC
else:
    # Python 3.10: polyfill para StrEnum
    class StrEnum(str, Enum):  # type: ignore[misc]
        """
        Polyfill para StrEnum do Python 3.11+.

        StrEnum é uma classe Enum onde os membros são também strings
        e são comparados usando semântica de string.
        """

        def __str__(self) -> str:
            return str(self.value)

        def __repr__(self) -> str:
            return f"<{self.__class__.__name__}.{self.name}: {self.value}>"

        # Hash baseado no valor string para permitir uso como dict key
        def __hash__(self) -> int:
            return hash(str(self.value))

        # Comparação com strings funciona corretamente porque herdamos de str
        def __eq__(self, other: object) -> bool:
            if isinstance(other, str):
                return str(self.value) == other
            return super().__eq__(other)

        @classmethod
        def _missing_(cls, value: object) -> "StrEnum | None":
            """Tenta encontrar um membro pelo valor string."""
            if isinstance(value, str):
                for member in cls:
                    if member.value == value:
                        return member
            return None

    # Python 3.10: polyfill para UTC (alias para timezone.utc)
    UTC = timezone.utc


__all__ = ["StrEnum", "UTC", "PY311_PLUS"]
