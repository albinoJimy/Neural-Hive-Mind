"""Modelos de dados para esquemas de banco de dados."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DataFieldType(str, Enum):
    """Tipo de dado para campos de modelo."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    TEXT = "text"
    JSON = "json"
    ENUM = "enum"
    REFERENCE = "reference"  # Chave estrangeira
    ARRAY = "array"


class ConstraintType(str, Enum):
    """Tipo de restrição."""

    PRIMARY_KEY = "primary_key"
    FOREIGN_KEY = "foreign_key"
    UNIQUE = "unique"
    NOT_NULL = "not_null"
    CHECK = "check"
    INDEX = "index"


class DataField(BaseModel):
    """Campo de um modelo de dados."""

    name: str = Field(..., description="Nome do campo")
    field_type: DataFieldType = Field(..., description="Tipo do campo")
    required: bool = Field(default=False, description="Se é obrigatório")
    unique: bool = Field(default=False, description="Se deve ser único")
    default_value: Optional[Any] = Field(None, description="Valor padrão")
    min_length: Optional[int] = Field(None, description="Comprimento mínimo")
    max_length: Optional[int] = Field(None, description="Comprimento máximo")
    min_value: Optional[float] = Field(None, description="Valor mínimo")
    max_value: Optional[float] = Field(None, description="Valor máximo")
    enum_values: Optional[List[str]] = Field(None, description="Valores possíveis (enum)")
    reference_to: Optional[str] = Field(None, description="Tabela/modelo referenciado")
    reference_field: Optional[str] = Field(None, description="Campo referenciado")
    description: Optional[str] = Field(None, description="Descrição do campo")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Index(BaseModel):
    """Índice de um modelo de dados."""

    name: str = Field(..., description="Nome do índice")
    fields: List[str] = Field(..., description="Campos do índice")
    unique: bool = Field(default=False, description="Se é único")
    index_type: str = Field(default="btree", description="Tipo do índice")


class DataModel(BaseModel):
    """Modelo de dados (entidade/tabela)."""

    id: str = Field(..., description="ID único do modelo")
    name: str = Field(..., description="Nome do modelo/tabela")
    description: Optional[str] = Field(None, description="Descrição do modelo")
    fields: List[DataField] = Field(default_factory=list, description="Campos do modelo")
    indexes: List[Index] = Field(default_factory=list, description="Índices do modelo")
    primary_key: List[str] = Field(default_factory=list, description="Chave primária")
    foreign_keys: Dict[str, str] = Field(
        default_factory=dict, description="Chaves estrangeiras (campo -> tabela)"
    )

    # Relacionamentos
    many_to_one: List[str] = Field(
        default_factory=list, description="Relacionamentos N:1 (nomes dos modelos)"
    )
    one_to_many: List[str] = Field(
        default_factory=list, description="Relacionamentos 1:N (nomes dos modelos)"
    )
    many_to_many: List[str] = Field(
        default_factory=list, description="Relacionamentos N:M (nomes dos modelos)"
    )

    metadata: Dict[str, Any] = Field(default_factory=dict)
    cognitive_plan_id: Optional[str] = Field(None)
    requirement_id: Optional[str] = Field(None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)

    def add_field(self, field: DataField) -> None:
        """Adiciona campo ao modelo."""
        self.fields.append(field)
        if field.required and field.name not in self.primary_key:
            # Adicionar NOT_NULL constraint implicitamente
            self.updated_at = datetime.utcnow()

    def add_index(self, index: Index) -> None:
        """Adiciona índice ao modelo."""
        self.indexes.append(index)
        self.updated_at = datetime.utcnow()


class EntityRelationship(BaseModel):
    """Relacionamento entre entidades."""

    from_entity: str = Field(..., alias="from", description="Entidade de origem")
    to_entity: str = Field(..., alias="to", description="Entidade de destino")
    relationship_type: str = Field(..., description="Tipo: one_to_one, one_to_many, many_to_many")
    cardinality: str = Field(..., description="Cardinalidade (ex: 1:N, N:M)")
    description: Optional[str] = Field(None, description="Descrição do relacionamento")


class DataSchema(BaseModel):
    """Esquema completo de dados para um sistema."""

    id: str = Field(..., description="ID único do esquema")
    name: str = Field(..., description="Nome do esquema")
    description: Optional[str] = Field(None)
    models: List[DataModel] = Field(default_factory=list)
    relationships: List[EntityRelationship] = Field(default_factory=list)
    cognitive_plan_id: Optional[str] = Field(None)
    requirement_id: Optional[str] = Field(None)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)

    def add_model(self, model: DataModel) -> None:
        """Adiciona modelo ao esquema."""
        self.models.append(model)
        self.updated_at = datetime.utcnow()

    def get_model_by_name(self, name: str) -> Optional[DataModel]:
        """Retorna modelo por nome."""
        for model in self.models:
            if model.name == name:
                return model
        return None
