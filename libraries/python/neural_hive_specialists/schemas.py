"""
Definições de schema para validação de planos cognitivos e opiniões.

Este módulo centraliza todos os schemas do sistema:
- Planos Cognitivos: TaskSchema, CognitivePlanSchema
- Opiniões do Ledger: OpinionDocumentV2, Opinion, ReasoningFactor, Mitigation
- Validação de compatibilidade de versão
- Detecção de ciclos em DAG para dependências de tarefas

Version: 1.0.0
"""

import collections
import re
from typing import Any, Dict, List, Optional, Tuple

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Import ledger schemas
from .ledger import (
    OpinionDocumentV2,
    Opinion,
    ReasoningFactor,
    Mitigation,
    SchemaVersionManager,
)

logger = structlog.get_logger(__name__)

# Rastreamento de versão do schema de planos cognitivos
SCHEMA_VERSION = "1.0.0"

# Versões de plano suportadas por padrão (pode ser sobrescrito pela config)
SUPPORTED_PLAN_VERSIONS = ["1.0.0"]

# Versão do schema de opinião (ledger)
OPINION_SCHEMA_VERSION = "2.0.0"

# JSON Schemas versionados para OpinionDocumentV2
OPINION_JSON_SCHEMAS = {
    "2.0.0": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "title": "OpinionDocumentV2",
        "description": "Schema JSON para documento de opinião versão 2.0.0",
        "required": [
            "schema_version",
            "opinion_id",
            "plan_id",
            "intent_id",
            "specialist_type",
            "specialist_version",
            "opinion",
            "correlation_id",
            "evaluated_at",
            "processing_time_ms",
            "buffered",
            "content_hash",
        ],
        "properties": {
            "schema_version": {
                "type": "string",
                "pattern": "^\\d+\\.\\d+\\.\\d+$",
                "description": "Versão do schema em formato semver",
            },
            "opinion_id": {
                "type": "string",
                "description": "ID único da opinião (UUID)",
            },
            "plan_id": {
                "type": "string",
                "description": "ID do plano cognitivo avaliado",
            },
            "intent_id": {"type": "string", "description": "ID da intenção original"},
            "specialist_type": {
                "type": "string",
                "description": "Tipo do especialista (technical, business, etc.)",
            },
            "specialist_version": {
                "type": "string",
                "description": "Versão do especialista",
            },
            "opinion": {
                "type": "object",
                "required": [
                    "confidence_score",
                    "risk_score",
                    "recommendation",
                    "reasoning_summary",
                ],
                "properties": {
                    "confidence_score": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                    "risk_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "recommendation": {
                        "type": "string",
                        "enum": ["approve", "reject", "review_required", "conditional"],
                    },
                    "reasoning_summary": {"type": "string"},
                    "reasoning_factors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["factor_name", "weight", "score"],
                            "properties": {
                                "factor_name": {"type": "string"},
                                "weight": {"type": "number"},
                                "score": {"type": "number"},
                                "details": {"type": "string"},
                            },
                        },
                    },
                    "explainability_token": {"type": "string"},
                    "explainability": {"type": "object"},
                    "mitigations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["mitigation_type", "description", "priority"],
                            "properties": {
                                "mitigation_type": {"type": "string"},
                                "description": {"type": "string"},
                                "priority": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high", "critical"],
                                },
                                "estimated_effort": {"type": "string"},
                            },
                        },
                    },
                    "metadata": {"type": "object"},
                },
            },
            "correlation_id": {"type": "string"},
            "trace_id": {"type": ["string", "null"]},
            "span_id": {"type": ["string", "null"]},
            "evaluated_at": {
                "type": "string",
                "format": "date-time",
                "description": "Timestamp UTC de avaliação",
            },
            "processing_time_ms": {
                "type": "integer",
                "minimum": 0,
                "description": "Tempo de processamento em milissegundos",
            },
            "buffered": {
                "type": "boolean",
                "description": "Se a opinião foi bufferizada",
            },
            "content_hash": {
                "type": "string",
                "description": "Hash SHA-256 do conteúdo",
            },
            "digital_signature": {
                "type": ["string", "null"],
                "description": "Assinatura digital RSA (opcional)",
            },
            "signature_algorithm": {
                "type": ["string", "null"],
                "description": "Algoritmo de assinatura (ex: RSA-SHA256)",
            },
        },
    }
}

# Avro Schemas versionados para OpinionDocumentV2
OPINION_AVRO_SCHEMAS = {
    "2.0.0": {
        "type": "record",
        "name": "OpinionDocumentV2",
        "namespace": "neural_hive.ledger",
        "doc": "Schema Avro para documento de opinião versão 2.0.0",
        "fields": [
            {"name": "schema_version", "type": "string", "doc": "Versão do schema"},
            {"name": "opinion_id", "type": "string", "doc": "ID único da opinião"},
            {"name": "plan_id", "type": "string", "doc": "ID do plano cognitivo"},
            {"name": "intent_id", "type": "string", "doc": "ID da intenção original"},
            {
                "name": "specialist_type",
                "type": "string",
                "doc": "Tipo do especialista",
            },
            {
                "name": "specialist_version",
                "type": "string",
                "doc": "Versão do especialista",
            },
            {
                "name": "opinion",
                "type": {
                    "type": "record",
                    "name": "Opinion",
                    "fields": [
                        {"name": "confidence_score", "type": "double"},
                        {"name": "risk_score", "type": "double"},
                        {"name": "recommendation", "type": "string"},
                        {"name": "reasoning_summary", "type": "string"},
                        {
                            "name": "reasoning_factors",
                            "type": {
                                "type": "array",
                                "items": {
                                    "type": "record",
                                    "name": "ReasoningFactor",
                                    "fields": [
                                        {"name": "factor_name", "type": "string"},
                                        {"name": "weight", "type": "double"},
                                        {"name": "score", "type": "double"},
                                        {
                                            "name": "details",
                                            "type": ["null", "string"],
                                            "default": None,
                                        },
                                    ],
                                },
                            },
                        },
                        {"name": "explainability_token", "type": "string"},
                        {"name": "explainability", "type": "string"},
                        {
                            "name": "mitigations",
                            "type": {
                                "type": "array",
                                "items": {
                                    "type": "record",
                                    "name": "Mitigation",
                                    "fields": [
                                        {"name": "mitigation_type", "type": "string"},
                                        {"name": "description", "type": "string"},
                                        {"name": "priority", "type": "string"},
                                        {
                                            "name": "estimated_effort",
                                            "type": ["null", "string"],
                                            "default": None,
                                        },
                                    ],
                                },
                            },
                        },
                        {"name": "metadata", "type": "string"},
                    ],
                },
            },
            {"name": "correlation_id", "type": "string"},
            {"name": "trace_id", "type": ["null", "string"], "default": None},
            {"name": "span_id", "type": ["null", "string"], "default": None},
            {"name": "evaluated_at", "type": "string", "doc": "Timestamp ISO 8601"},
            {"name": "processing_time_ms", "type": "int"},
            {"name": "buffered", "type": "boolean"},
            {"name": "content_hash", "type": "string"},
            {"name": "digital_signature", "type": ["null", "string"], "default": None},
            {
                "name": "signature_algorithm",
                "type": ["null", "string"],
                "default": None,
            },
        ],
    }
}


def get_opinion_json_schema(
    version: str = OPINION_SCHEMA_VERSION,
) -> Optional[Dict[str, Any]]:
    """
    Retorna o JSON Schema para uma versão específica de OpinionDocumentV2.

    Args:
        version: Versão do schema (default: versão atual)

    Returns:
        JSON Schema como dict, ou None se versão não encontrada
    """
    return OPINION_JSON_SCHEMAS.get(version)


def get_opinion_avro_schema(
    version: str = OPINION_SCHEMA_VERSION,
) -> Optional[Dict[str, Any]]:
    """
    Retorna o Avro Schema para uma versão específica de OpinionDocumentV2.

    Args:
        version: Versão do schema (default: versão atual)

    Returns:
        Avro Schema como dict, ou None se versão não encontrada
    """
    return OPINION_AVRO_SCHEMAS.get(version)


class PlanValidationError(ValueError):
    """Exceção base para erros de validação de plano cognitivo."""

    pass


class PlanVersionIncompatibleError(PlanValidationError):
    """Levantada quando a versão do plano não é suportada pelo especialista."""

    pass


class TaskDependencyError(PlanValidationError):
    """Levantada quando dependências de tarefas são inválidas (referências faltando, ciclos, etc)."""

    pass


class TaskSchema(BaseModel):
    """
    Schema para tarefa individual dentro de um plano cognitivo.

    Valida estrutura da tarefa incluindo dependências, capacidades e metadados.
    """

    model_config = ConfigDict(extra="allow")

    task_id: str = Field(..., description="Identificador único da tarefa")
    task_type: str = Field(
        ..., description="Tipo da tarefa (ex: 'analysis', 'transformation')"
    )
    name: Optional[str] = Field(None, description="Nome legível da tarefa")
    description: str = Field(..., description="Descrição da tarefa")
    dependencies: List[str] = Field(
        default_factory=list,
        description="Lista de IDs de tarefas das quais esta tarefa depende",
    )
    estimated_duration_ms: Optional[int] = Field(
        None, description="Tempo estimado de execução em milissegundos"
    )
    required_capabilities: List[str] = Field(
        default_factory=list, description="Capacidades de especialista requeridas"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Parâmetros específicos da tarefa"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Metadados adicionais da tarefa"
    )

    @field_validator("task_id", "task_type", "description")
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        """Garante que campos de string obrigatórios não estejam vazios."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} deve ser uma string não vazia")
        return v.strip()

    @field_validator("estimated_duration_ms")
    @classmethod
    def validate_duration(cls, v: Optional[int]) -> Optional[int]:
        """Garante que duração não seja negativa se fornecida."""
        if v is not None and v < 0:
            raise ValueError("estimated_duration_ms deve ser >= 0")
        return v

    @field_validator("dependencies")
    @classmethod
    def validate_no_self_reference(cls, v: List[str], info) -> List[str]:
        """Garante que tarefa não dependa de si mesma."""
        # Nota: Não podemos verificar task_id aqui pois não está disponível no field validator
        # Verificação de auto-referência ocorre no validador de nível de plano
        return v


class CognitivePlanSchema(BaseModel):
    """
    Schema para plano cognitivo completo do Semantic Translation Engine.

    Valida estrutura do plano, dependências de tarefas, ordem de execução e compatibilidade de versão.
    Realiza detecção de ciclos em DAG para garantir grafo de execução válido.
    """

    model_config = ConfigDict(extra="allow")

    plan_id: str = Field(..., description="Identificador único do plano")
    version: str = Field(
        ..., description="Versão do plano em formato semver (ex: '1.0.0')"
    )
    intent_id: str = Field(..., description="Identificador da intenção original")
    correlation_id: Optional[str] = Field(
        None, description="ID de correlação para rastreamento distribuído"
    )
    trace_id: Optional[str] = Field(None, description="ID de trace OpenTelemetry")
    span_id: Optional[str] = Field(None, description="ID de span OpenTelemetry")
    tasks: List[TaskSchema] = Field(..., description="Lista de tarefas no plano")
    execution_order: Optional[List[str]] = Field(
        None, description="Ordem explícita de execução das tarefas"
    )
    original_domain: str = Field(..., description="Domínio original da intenção")
    original_priority: str = Field(
        ..., description="Nível de prioridade: low, normal, high, critical"
    )
    original_security_level: Optional[str] = Field(
        None, description="Classificação de nível de segurança"
    )
    risk_score: Optional[float] = Field(
        None, description="Pontuação de avaliação de risco (0.0-1.0)"
    )
    risk_band: Optional[str] = Field(
        None, description="Classificação de faixa de risco"
    )
    complexity_score: Optional[float] = Field(
        None, description="Pontuação de avaliação de complexidade"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Metadados adicionais do plano"
    )

    @field_validator("plan_id", "intent_id", "original_domain")
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        """Garante que campos de string obrigatórios não estejam vazios."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} deve ser uma string não vazia")
        return v.strip()

    @field_validator("version")
    @classmethod
    def validate_semver_format(cls, v: str) -> str:
        """Valida que a versão segue formato semver (major.minor.patch)."""
        semver_pattern = r"^\d+\.\d+\.\d+$"
        if not re.match(semver_pattern, v):
            raise ValueError(
                f"version deve estar em formato semver (ex: '1.0.0'), recebido: {v}"
            )
        return v

    @field_validator("tasks")
    @classmethod
    def validate_has_tasks(cls, v: List[TaskSchema]) -> List[TaskSchema]:
        """Garante que o plano tem pelo menos uma tarefa."""
        if not v or len(v) == 0:
            raise ValueError("Plano deve conter pelo menos uma tarefa")
        return v

    @field_validator("original_priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Garante que prioridade é um dos valores válidos."""
        valid_priorities = {"low", "normal", "high", "critical"}
        if v.lower() not in valid_priorities:
            raise ValueError(
                f"original_priority deve ser um de {valid_priorities}, recebido: {v}"
            )
        return v.lower()

    @field_validator("risk_score")
    @classmethod
    def validate_risk_score(cls, v: Optional[float]) -> Optional[float]:
        """Garante que pontuação de risco está entre 0.0 e 1.0 se fornecida."""
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError(f"risk_score deve estar entre 0.0 e 1.0, recebido: {v}")
        return v

    @field_validator("complexity_score")
    @classmethod
    def validate_complexity_score(cls, v: Optional[float]) -> Optional[float]:
        """Garante que pontuação de complexidade não é negativa se fornecida."""
        if v is not None and v < 0.0:
            raise ValueError(f"complexity_score deve ser >= 0.0, recebido: {v}")
        return v

    @model_validator(mode="after")
    def validate_task_dependencies(self) -> "CognitivePlanSchema":
        """
        Valida dependências de tarefas:
        - Todos os IDs de tarefa devem ser únicos
        - Todos os IDs de dependência devem referenciar tarefas existentes
        - Sem auto-referências
        - Sem dependências circulares (DAG deve ser acíclico)
        """
        if not self.tasks:
            return self

        # Constrói conjunto de IDs de tarefas para busca rápida
        task_ids = {task.task_id for task in self.tasks}

        # Valida unicidade de task_id
        all_task_ids = [task.task_id for task in self.tasks]
        duplicates = [
            task_id
            for task_id, count in collections.Counter(all_task_ids).items()
            if count > 1
        ]
        if duplicates:
            raise TaskDependencyError(f"IDs de tarefa duplicados: {duplicates}")

        # Valida dependências de cada tarefa
        for task in self.tasks:
            # Verifica auto-referência
            if task.task_id in task.dependencies:
                raise TaskDependencyError(
                    f"Tarefa '{task.task_id}' não pode depender de si mesma"
                )

            # Verifica que todas as dependências existem
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    raise TaskDependencyError(
                        f"Tarefa '{task.task_id}' depende de tarefa inexistente '{dep_id}'"
                    )

        # Verifica ciclos usando detecção baseada em DFS
        try:
            self._detect_cycles()
        except TaskDependencyError as e:
            raise e

        return self

    def _detect_cycles(self) -> None:
        """
        Detecta ciclos no grafo de dependências de tarefas usando DFS.

        Raises:
            TaskDependencyError: Se um ciclo for detectado no grafo de dependências
        """
        # Tenta usar networkx se disponível (mais robusto)
        try:
            import networkx as nx

            # Constrói grafo direcionado
            G = nx.DiGraph()
            for task in self.tasks:
                G.add_node(task.task_id)
                for dep_id in task.dependencies:
                    # Aresta da dependência para a tarefa (dep deve completar antes da tarefa)
                    G.add_edge(dep_id, task.task_id)

            # Verifica ciclos
            if not nx.is_directed_acyclic_graph(G):
                cycles = list(nx.simple_cycles(G))
                cycle_str = ", ".join([" -> ".join(cycle) for cycle in cycles[:3]])
                raise TaskDependencyError(
                    f"Dependências circulares detectadas no grafo de tarefas. "
                    f"Exemplos de ciclos: {cycle_str}"
                )

            logger.debug(
                "Grafo de dependências de tarefas validado (networkx)",
                num_tasks=len(self.tasks),
                num_edges=G.number_of_edges(),
            )

        except ImportError:
            # Fallback para detecção de ciclos baseada em DFS
            logger.debug(
                "NetworkX não disponível, usando detecção de ciclos alternativa"
            )
            self._detect_cycles_dfs()

    def _detect_cycles_dfs(self) -> None:
        """
        Detecção de ciclos baseada em DFS alternativa sem networkx.

        Raises:
            TaskDependencyError: Se um ciclo for detectado
        """
        # Constrói lista de adjacências (task_id -> lista de task_ids dependentes)
        graph: Dict[str, List[str]] = {task.task_id: [] for task in self.tasks}
        for task in self.tasks:
            for dep_id in task.dependencies:
                # Aresta da dependência para a tarefa
                graph[dep_id].append(task.task_id)

        # DFS com marcação de cor: branco (não visitado), cinza (visitando), preto (concluído)
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {task_id: WHITE for task_id in graph}

        def dfs(node: str, path: List[str]) -> None:
            """Visita DFS com detecção de ciclo."""
            if color[node] == GRAY:
                # Encontrou aresta de retorno - ciclo detectado
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                raise TaskDependencyError(
                    f"Dependência circular detectada: {' -> '.join(cycle)}"
                )

            if color[node] == BLACK:
                # Já processado
                return

            color[node] = GRAY
            path.append(node)

            for neighbor in graph[node]:
                dfs(neighbor, path)

            path.pop()
            color[node] = BLACK

        # Visita todos os nós
        for task_id in graph:
            if color[task_id] == WHITE:
                dfs(task_id, [])

        logger.debug(
            "Grafo de dependências de tarefas validado (DFS)", num_tasks=len(self.tasks)
        )

    @model_validator(mode="after")
    def validate_execution_order(self) -> "CognitivePlanSchema":
        """
        Valida execution_order se fornecido:
        - Sem IDs duplicados em execution_order
        - Todos os IDs de tarefas devem aparecer em execution_order
        - Todos os IDs em execution_order devem referenciar tarefas existentes
        """
        if self.execution_order is None:
            return self

        # Verifica duplicatas em execution_order
        duplicates = [
            task_id
            for task_id, count in collections.Counter(self.execution_order).items()
            if count > 1
        ]
        if duplicates:
            raise ValueError(f"execution_order contém IDs duplicados: {duplicates}")

        task_ids = {task.task_id for task in self.tasks}
        execution_ids = set(self.execution_order)

        # Verifica que todas as tarefas estão na ordem de execução
        missing_from_order = task_ids - execution_ids
        if missing_from_order:
            raise ValueError(
                f"execution_order está faltando IDs de tarefas: {missing_from_order}"
            )

        # Verifica que todos os IDs na ordem de execução existem
        extra_in_order = execution_ids - task_ids
        if extra_in_order:
            raise ValueError(
                f"execution_order contém IDs de tarefas inexistentes: {extra_in_order}"
            )

        return self


# Funções auxiliares para validação de versão


def parse_semver(version: str) -> Tuple[int, int, int]:
    """
    Analisa string de versão semver em tupla (major, minor, patch).

    Args:
        version: String de versão no formato "major.minor.patch"

    Returns:
        Tupla de (major, minor, patch) como inteiros

    Raises:
        ValueError: Se o formato da versão for inválido
    """
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Formato semver inválido: {version}")

    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        return (major, minor, patch)
    except ValueError as e:
        raise ValueError(f"Formato semver inválido: {version}") from e


def validate_plan_version(plan_version: str, supported_versions: List[str]) -> bool:
    """
    Verifica se a versão do plano está na lista de versões suportadas.

    Args:
        plan_version: Versão do plano cognitivo
        supported_versions: Lista de versões suportadas pelo especialista

    Returns:
        True se a versão é suportada, False caso contrário
    """
    return plan_version in supported_versions


def is_version_compatible(
    plan_version: str, supported_versions: List[str]
) -> Tuple[bool, str]:
    """
    Verifica se a versão do plano é compatível com as versões suportadas pelo especialista.

    Realiza correspondência exata de versão. Melhorias futuras podem suportar
    correspondência de intervalo de versão semântica (ex: "^1.0.0" corresponde a "1.x.x").

    Args:
        plan_version: Versão do plano cognitivo
        supported_versions: Lista de versões suportadas pelo especialista

    Returns:
        Tupla de (is_compatible, error_message)
        - is_compatible: True se a versão é suportada
        - error_message: String vazia se compatível, descrição do erro caso contrário
    """
    if not supported_versions:
        return (False, "Nenhuma versão suportada configurada")

    if not plan_version:
        return (False, "Versão do plano está vazia")

    # Valida formato semver
    try:
        parse_semver(plan_version)
    except ValueError as e:
        return (False, f"Formato de versão do plano inválido: {e}")

    # Valida formato das versões suportadas
    for sv in supported_versions:
        try:
            parse_semver(sv)
        except ValueError as e:
            logger.warning(
                "Formato de versão suportada inválido", version=sv, error=str(e)
            )
            return (False, f"Formato de versão suportada inválido '{sv}': {e}")

    # Verifica correspondência exata
    if validate_plan_version(plan_version, supported_versions):
        return (True, "")

    # Não compatível
    return (
        False,
        f"Versão do plano '{plan_version}' não está nas versões suportadas: {supported_versions}",
    )
