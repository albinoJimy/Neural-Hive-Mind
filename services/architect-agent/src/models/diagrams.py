"""Architecture diagram models."""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class DiagramType(str, Enum):
    """Tipos de diagramas suportados."""
    C4_CONTEXT = "c4_context"
    C4_CONTAINER = "c4_container"
    C4_COMPONENT = "c4_component"
    SEQUENCE = "sequence"
    DEPLOYMENT = "deployment"
    ENTITY_RELATIONSHIP = "er"


class Diagram(BaseModel):
    """Diagrama de arquitetura."""

    diagram_id: str
    type: DiagramType
    title: str
    mermaid_code: str
    svg_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
