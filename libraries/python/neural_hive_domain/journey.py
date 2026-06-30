"""Journey definitions for the Neural Hive Mind routing layer.

This module provides the shared :class:`Journey` enum and the
:class:`JourneyDecision` model used to route a cognitive plan through the
correct downstream flow (plan-only, orchestration, build, migration).

The journey is decided early (at the STE, alongside the workflow type) and
propagated through the ``cognitive_plan``; nothing downstream re-derives it.
See ADR-0011 and ``docs/specs/2026-06-23-journey-router/``.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Journey(str, Enum):
    """Journey types for routing a cognitive plan downstream.

    Inherits from ``str`` and ``Enum`` for JSON serialization compatibility
    and Pydantic model integration (same pattern as ``UnifiedDomain``).

    Journeys:
        J1_PLAN_ONLY: Planning only; no execution downstream.
        J2_ORCHESTRATE: Orchestration of an existing workflow.
        J3_BUILD: Build/generation flow (fluxo G).
        J4_MIGRATE: Migration / ingestion flow.
        UNKNOWN: No strong signal; anti-verde-falso (requires validation).
    """

    J1_PLAN_ONLY = "J1_PLAN_ONLY"
    J2_ORCHESTRATE = "J2_ORCHESTRATE"
    J3_BUILD = "J3_BUILD"
    J4_MIGRATE = "J4_MIGRATE"
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:
        """Return the string value of the journey."""
        return self.value


class JourneyDecision(BaseModel):
    """The outcome of classifying a cognitive plan into a Journey.

    Attributes:
        journey: The resolved journey.
        journey_id: Stable identifier (UUID) for this journey decision.
        confidence: Classification confidence in [0.0, 1.0].
        reasoning: Human-readable explanation of the decision.
        classification_method: Provenance of the decision
            (``structured_signal`` | ``llm`` | ``no_match``).
    """

    # use_enum_values: serializa o enum como string (consistente p/ Kafka/Avro/Mongo).
    model_config = ConfigDict(use_enum_values=True)

    journey: Journey
    journey_id: str
    # confidence validada em [0,1] — falha explícita em vez de aceitar inválido
    # (anti-verde-falso, padrão do projeto).
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    # contrato fechado: só os métodos conhecidos (espelha UnifiedDomain via tipo).
    classification_method: Literal["structured_signal", "llm", "no_match"]
