"""Modelos de dados para Critérios de Aceitação."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CriterionType(str, Enum):
    """Tipo de critério de aceitação."""

    FUNCTIONAL = "functional"
    PERFORMANCE = "performance"
    USABILITY = "usability"
    SECURITY = "security"
    COMPLIANCE = "compliance"


class CriterionStatus(str, Enum):
    """Status do critério."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AcceptanceCriterion(BaseModel):
    """Critério de aceitação individual."""

    id: str = Field(..., description="ID único do critério")
    user_story_id: Optional[str] = Field(None, description="ID da User Story relacionada")
    requirement_id: Optional[str] = Field(None, description="ID do Requisito relacionado")
    criterion_type: CriterionType = Field(
        default=CriterionType.FUNCTIONAL,
        description="Tipo do critério"
    )
    status: CriterionStatus = Field(
        default=CriterionStatus.PENDING,
        description="Status do critério"
    )

    statement: str = Field(
        ...,
        min_length=10,
        description="Declaração do critério no formato Given-When-Then"
    )
    given: Optional[str] = Field(None, description="Contexto inicial (Given)")
    when: Optional[str] = Field(None, description="Acção ou evento (When)")
    then: Optional[str] = Field(None, description="Resultado esperado (Then)")

    test_scenario: Optional[str] = Field(
        None,
        description="Cenário de teste associado"
    )
    automated: bool = Field(
        default=False,
        description="Se possui teste automatizado"
    )
    test_file: Optional[str] = Field(
        None,
        description="Caminho para o teste automatizado"
    )

    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)

    def get_gwt_format(self) -> str:
        """Retorna o critério no formato Given-When-Then."""
        parts = []
        if self.given:
            parts.append(f"Given {self.given}")
        if self.when:
            parts.append(f"When {self.when}")
        if self.then:
            parts.append(f"Then {self.then}")
        return "\n".join(parts) if parts else self.statement


class AcceptanceCriteriaSet(BaseModel):
    """Conjunto de critérios de aceitação."""

    id: str = Field(..., description="ID único do conjunto")
    parent_id: str = Field(..., description="ID da User Story ou Requisito")
    parent_type: str = Field(..., description="Tipo do pai (user_story ou requirement)")
    criteria: List[AcceptanceCriterion] = Field(default_factory=list)
    pass_rate: float = Field(default=0.0, description="Taxa de aprovação (0-1)")
    automated_count: int = Field(default=0, description="Critérios automatizados")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)

    def calculate_pass_rate(self) -> None:
        """Calcula taxa de aprovação."""
        if not self.criteria:
            self.pass_rate = 0.0
            return

        passed = sum(1 for c in self.criteria if c.status == CriterionStatus.PASSED)
        total = len(self.criteria)
        self.pass_rate = passed / total if total > 0 else 0.0

    def calculate_automated_count(self) -> None:
        """Conta critérios automatizados."""
        self.automated_count = sum(1 for c in self.criteria if c.automated)

    def add_criterion(self, criterion: AcceptanceCriterion) -> None:
        """Adiciona critério ao conjunto."""
        self.criteria.append(criterion)
        self.updated_at = datetime.utcnow()


class AcceptanceCriterionCreate(BaseModel):
    """DTO para criação de critério de aceitação."""

    user_story_id: Optional[str] = None
    requirement_id: Optional[str] = None
    criterion_type: CriterionType = CriterionType.FUNCTIONAL
    statement: str = Field(..., min_length=10)
    given: Optional[str] = None
    when: Optional[str] = None
    then: Optional[str] = None
    automated: bool = False
