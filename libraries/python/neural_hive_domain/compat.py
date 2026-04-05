"""
Polyfill de compatibilidade para Python 3.10.

Fornece StrEnum e datetime.UTC para Python 3.10,
compatíveis com as versões nativas do Python 3.11+.
"""

import sys
from datetime import timezone
from enum import Enum

PY311_PLUS = sys.version_info >= (3, 11)

if PY311_PLUS:
    from enum import StrEnum as _StrEnum
    from datetime import UTC as _UTC

    StrEnum = _StrEnum
    UTC = _UTC
else:
    class StrEnum(str, Enum):
        """Polyfill para StrEnum do Python 3.11+."""

        def __str__(self) -> str:
            return str(self.value)

        def __repr__(self) -> str:
            return f"<{self.__class__.__name__}.{self.name}: {self.value}>"

        def __hash__(self) -> int:
            return hash(str(self.value))

        def __eq__(self, other: object) -> bool:
            if isinstance(other, str):
                return str(self.value) == other
            return super().__eq__(other)

        @classmethod
        def _missing_(cls, value: object):
            if isinstance(value, str):
                for member in cls:
                    if member.value == value:
                        return member
            return None

    UTC = timezone.utc


__all__ = ['StrEnum', 'UTC', 'PY311_PLUS']
__version__ = '1.0.0'
