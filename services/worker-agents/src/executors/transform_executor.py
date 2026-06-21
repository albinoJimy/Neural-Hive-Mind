"""
Executor para task_type=TRANSFORM com suporte a múltiplas transformações de dados.

Suporta execução de transformações em:
- JSON (mapeamento, filtragem, agregação)
- CSV (parse e serialização)
- Agregação (group by, sum, count, avg)
- Formatação (data, números, strings)
"""

import contextlib
import csv as csv_lib
import io
import json
import time
from datetime import datetime
from typing import Any

import structlog

from neural_hive_observability import get_tracer

from .base_executor import BaseTaskExecutor

logger = structlog.get_logger()

# Campos de fallback usados quando o input_ref pede um campo ausente: o output do
# QueryExecutor expõe ``documents`` ou ``results`` consoante a fonte de dados.
_INPUT_REF_FALLBACK_FIELDS = ("documents", "results")


def _parse_input_ref(input_ref: str) -> tuple[tuple[str, str] | None, str | None]:
    """Faz parsing de ``${selector.output.<field>}`` em ``(selector, field)``.

    Returns:
        Tupla ``((selector, field), None)`` em sucesso, ou ``(None, reason)`` se o
        formato for inválido.
    """
    if not isinstance(input_ref, str) or not (
        input_ref.startswith("${") and input_ref.endswith("}")
    ):
        return None, f"input_ref com formato inválido: {input_ref!r}"

    parts = input_ref[2:-1].split(".")  # remove ${ ... }
    if len(parts) != 3 or parts[1] != "output":
        return None, f"input_ref não segue o formato '${{dep.output.<field>}}': {input_ref!r}"

    return (parts[0], parts[2]), None


def resolve_input_ref(input_ref: str, dependency_outputs: dict[str, Any]) -> tuple[Any, str | None]:
    """Resolve um ``input_ref`` contra os outputs das dependências (data-flow).

    Suporta dois formatos de referência:
    - genérico ``${dep.output.<field>}``: percorre todas as dependências e usa o
      primeiro output que tenha ``<field>`` (com fallback documents→results→output);
    - explícito ``${<dep_id>.output.<field>}``: resolve apenas contra a dependência
      indicada.

    Args:
        input_ref: Referência no formato ``${...}``.
        dependency_outputs: Mapa ``{dep_id → dep_output}`` injetado em runtime pelo
            execution_engine. Cada ``dep_output`` é tipicamente
            ``{"output": {"documents": [...], "count": N}}`` mas pode ser o output
            direto (sem chave ``output``).

    Returns:
        Tupla ``(valor, reason)``. ``reason`` é ``None`` em caso de sucesso; caso
        contrário descreve porque a resolução falhou (degradação real).
    """
    parsed, parse_reason = _parse_input_ref(input_ref)
    if parse_reason is not None:
        return None, parse_reason
    selector, field = parsed

    if not dependency_outputs:
        return None, "sem dependency_outputs (nenhuma dependência forneceu output)"

    if selector == "dep":
        # Genérico: primeiro output que tenha o campo (ou um fallback).
        candidates = list(dependency_outputs.values())
    else:
        dep_output = dependency_outputs.get(selector)
        if dep_output is None:
            return None, f"dependência '{selector}' não encontrada em dependency_outputs"
        candidates = [dep_output]

    for dep_output in candidates:
        # O output efetivo está em ``output`` (contrato normalizado); cai para o
        # próprio dep_output se ausente.
        inner = dep_output.get("output") if isinstance(dep_output, dict) else None
        if not isinstance(inner, dict):
            inner = dep_output if isinstance(dep_output, dict) else {}

        if field in inner:
            return inner[field], None
        # Fallback documents→results para tolerar input_ref genérico.
        for fb in _INPUT_REF_FALLBACK_FIELDS:
            if fb in inner:
                return inner[fb], None

    return None, f"campo '{field}' ausente em todos os outputs de dependência"


class TransformExecutor(BaseTaskExecutor):
    """Executor para task_type=TRANSFORM com suporte a múltiplas transformações.

    Nota: O task_type é case-insensitive no registry. Tickets com task_type 'transform',
    'TRANSFORM', 'Transform', etc. serão corretamente roteados para este executor.
    """

    def get_task_type(self) -> str:
        # Retorna uppercase - registry normaliza para uppercase na busca
        return "TRANSFORM"

    def validate_ticket(self, ticket: dict[str, Any]) -> None:
        """
        Valida ticket TRANSFORM e parâmetros obrigatórios.

        Args:
            ticket: Ticket de execução

        Raises:
            ValidationError: Se parâmetros obrigatórios estiverem faltando
        """
        # Chamar validação base
        super().validate_ticket(ticket)

        # Validar parâmetros específicos de TRANSFORM
        ticket_id = ticket.get("ticket_id")
        parameters = ticket.get("parameters", {})

        # input_data NÃO é obrigatório: numa pipeline multi-task ele é fornecido por
        # data flow (output da task anterior). Quando ausente (task raiz ou sem
        # dependências com output), a transformação faz no-op gracioso em vez de
        # falhar o plano inteiro.
        _ = (ticket_id, parameters)

    def __init__(
        self,
        config,
        vault_client=None,
        code_forge_client=None,
        metrics=None,
        mongodb_client=None,
        redis_client=None,
    ):
        """
        Inicializa TransformExecutor com clientes de fontes de dados.

        Args:
            config: Configurações do worker agent
            vault_client: Cliente Vault para secrets
            code_forge_client: Cliente Code Forge para geração de código
            metrics: Objeto de métricas Prometheus
            mongodb_client: Cliente MongoDB para dados
            redis_client: Cliente Redis para cache
        """
        super().__init__(
            config, vault_client=vault_client, code_forge_client=code_forge_client, metrics=metrics
        )
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client

    async def execute(self, ticket: dict[str, Any]) -> dict[str, Any]:
        """
        Executar tarefa TRANSFORM com dispatch baseado em transform_type.

        Args:
            ticket: Ticket de execução com parâmetros

        Returns:
            Resultado da transformação
        """
        self.validate_ticket(ticket)

        ticket_id = ticket.get("ticket_id")
        parameters = ticket.get("parameters", {})
        transform_type = parameters.get("transform_type", "json")

        tracer = get_tracer()
        span_context = tracer.start_as_current_span("task_execution") if tracer else None
        with span_context as span:
            if span:
                span.set_attribute("neural.hive.task_id", ticket_id)
                span.set_attribute("neural.hive.task_type", self.get_task_type())
                span.set_attribute("neural.hive.executor", self.__class__.__name__)
                span.set_attribute("neural.hive.transform_type", transform_type)

            self.log_execution(
                ticket_id,
                "transform_execution_started",
                transform_type=transform_type,
                parameters=parameters,
            )

            try:
                start_time = time.monotonic()

                # Dispatch baseado em transform_type
                if transform_type == "json":
                    result = await self._execute_json_transform(ticket_id, parameters, span)
                elif transform_type == "csv":
                    result = await self._execute_csv_transform(ticket_id, parameters, span)
                elif transform_type == "aggregate":
                    result = await self._execute_aggregate_transform(ticket_id, parameters, span)
                elif transform_type == "format":
                    result = await self._execute_format_transform(ticket_id, parameters, span)
                elif transform_type == "mongodb_query_transform":
                    result = await self._execute_mongodb_transform(ticket_id, parameters, span)
                elif transform_type == "filter":
                    result = await self._execute_filter_transform(ticket_id, parameters, span)
                else:
                    raise ValueError(f"Unsupported transform_type: {transform_type}")

                elapsed_seconds = time.monotonic() - start_time

                # Registrar métricas de duração
                if self.metrics and hasattr(self.metrics, "transform_duration_seconds"):
                    self.metrics.transform_duration_seconds.labels(
                        transform_type=transform_type
                    ).observe(elapsed_seconds)

                # Registrar métricas de sucesso
                if self.metrics and hasattr(self.metrics, "transform_executed_total"):
                    status = "success" if result.get("success") else "failed"
                    self.metrics.transform_executed_total.labels(
                        status=status, transform_type=transform_type
                    ).inc()

                if span:
                    span.set_attribute(
                        "neural.hive.execution_status",
                        "success" if result.get("success") else "failed",
                    )
                    span.set_attribute("neural.hive.duration_seconds", elapsed_seconds)

                return result

            except Exception as e:
                self.log_execution(
                    ticket_id,
                    "transform_execution_failed",
                    level="error",
                    transform_type=transform_type,
                    error=str(e),
                )

                if self.metrics and hasattr(self.metrics, "transform_executed_total"):
                    self.metrics.transform_executed_total.labels(
                        status="failed", transform_type=transform_type
                    ).inc()

                return {
                    "success": False,
                    "output": None,
                    "metadata": {
                        "executor": "TransformExecutor",
                        "transform_type": transform_type,
                        "error": str(e),
                    },
                    "logs": [f"Transform execution failed: {e!s}"],
                }

    async def _execute_json_transform(
        self, ticket_id: str, parameters: dict[str, Any], span
    ) -> dict[str, Any]:
        """Executa transformação em JSON."""
        try:
            # Data-flow semântico (Task 7): resolve input_data via input_ref quando
            # ausente. Devolve (input_data, degraded_result) — se degraded_result
            # não for None, é uma degradação real e deve ser retornada tal-e-qual.
            input_data, degraded_result = self._resolve_json_input(ticket_id, parameters)
            if degraded_result is not None:
                return degraded_result

            if input_data is None:
                # Sem input E sem input_ref (task standalone): no-op gracioso para
                # não abortar o plano multi-task. A task fica COMPLETED sem transformar.
                # NOTA: uma lista vazia ([]) resolvida via input_ref (query devolveu
                # 0 documentos) NÃO é no-op — é dado real e segue para as operations.
                self.log_execution(ticket_id, "json_transform_noop_no_input")
                return self._success_result(
                    {"transformed_data": None, "noop": True},
                    "JSON transform no-op: sem input_data (nenhuma dependência forneceu output)",
                )

            operations = parameters.get("operations", [])
            if not operations:
                # Se nenhuma operação especificada, apenas validar JSON
                if isinstance(input_data, str):
                    json.loads(input_data)  # Validate JSON
                    return self._success_result(
                        {"validated": True, "input_type": "json_string"},
                        input_data[:200] + "..." if len(input_data) > 200 else input_data,
                    )

            result = self._apply_json_operations(input_data, operations)

            self.log_execution(
                ticket_id, "json_transform_completed", operations_count=len(operations)
            )

            return {
                "success": True,
                "output": {"transformed_data": result},
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "json",
                    "operations_applied": len(operations),
                },
                "logs": [
                    f"JSON transform completed with {len(operations)} operations",
                    "Transform completed successfully",
                ],
            }

        except Exception as e:
            self.log_execution(ticket_id, "json_transform_failed", level="error", error=str(e))
            return {
                "success": False,
                "output": None,
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "json",
                    "error": str(e),
                },
                "logs": [f"JSON transform failed: {e!s}"],
            }

    async def _execute_csv_transform(
        self, ticket_id: str, parameters: dict[str, Any], span
    ) -> dict[str, Any]:
        """Executa parse/transform de CSV."""
        try:
            csv_data = parameters.get("csv_data")
            if not csv_data:
                raise ValueError("Missing 'csv_data' parameter for CSV transform")

            delimiter = parameters.get("delimiter", ",")
            output_format = parameters.get("output_format", "json")

            # Parse CSV
            reader = csv_lib.DictReader(io.StringIO(csv_data), delimiter=delimiter)
            rows = list(reader)

            if output_format == "json":
                result = {"rows": rows, "count": len(rows)}
            elif output_format == "list":
                result = rows
            else:
                raise ValueError(f"Unsupported output_format: {output_format}")

            self.log_execution(
                ticket_id,
                "csv_transform_completed",
                rows_count=len(rows),
                output_format=output_format,
            )

            return {
                "success": True,
                "output": result,
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "csv",
                    "rows_count": len(rows),
                    "delimiter": delimiter,
                },
                "logs": [
                    f"CSV transform completed with {len(rows)} rows",
                    f"Delimiter: {delimiter}",
                    "Transform completed successfully",
                ],
            }

        except Exception as e:
            self.log_execution(ticket_id, "csv_transform_failed", level="error", error=str(e))
            return {
                "success": False,
                "output": None,
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "csv",
                    "error": str(e),
                },
                "logs": [f"CSV transform failed: {e!s}"],
            }

    async def _execute_aggregate_transform(
        self, ticket_id: str, parameters: dict[str, Any], span
    ) -> dict[str, Any]:
        """Executa agregação de dados."""
        try:
            data = parameters.get("data")
            if not data:
                raise ValueError("Missing 'data' parameter for aggregate transform")

            group_by = parameters.get("group_by", [])
            operations = parameters.get("operations", [])

            if not isinstance(data, list):
                raise ValueError("'data' parameter must be a list for aggregation")

            # Group data
            groups = {}
            for item in data:
                key = (
                    tuple(str(item.get(field, "")) for field in group_by)
                    if group_by
                    else ("default",)
                )
                if key not in groups:
                    groups[key] = []
                groups[key].append(item)

            # Apply operations per group
            result = []
            for key, items in groups.items():
                group_result = {"_group": key if len(key) > 1 else key[0]}

                for operation in operations:
                    op_type = operation.get("op")
                    field = operation.get("field")
                    alias = operation.get("alias", field)

                    if op_type == "count":
                        group_result[alias] = len(items)
                    elif op_type == "sum":
                        group_result[alias] = sum(float(item.get(field, 0)) for item in items)
                    elif op_type == "avg":
                        group_result[alias] = sum(
                            float(item.get(field, 0)) for item in items
                        ) / len(items)
                    elif op_type == "min":
                        group_result[alias] = min(item.get(field) for item in items)
                    elif op_type == "max":
                        group_result[alias] = max(item.get(field) for item in items)
                    elif op_type == "first":
                        group_result[alias] = items[0].get(field) if items else None
                    elif op_type == "last":
                        group_result[alias] = items[-1].get(field) if items else None

                result.append(group_result)

            self.log_execution(
                ticket_id,
                "aggregate_transform_completed",
                groups_count=len(groups),
                operations_count=len(operations),
            )

            return {
                "success": True,
                "output": {"aggregated_data": result},
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "aggregate",
                    "groups_count": len(groups),
                    "operations_count": len(operations),
                },
                "logs": [
                    f"Aggregate transform completed with {len(groups)} groups",
                    f"{len(operations)} operations applied",
                    "Transform completed successfully",
                ],
            }

        except Exception as e:
            self.log_execution(ticket_id, "aggregate_transform_failed", level="error", error=str(e))
            return {
                "success": False,
                "output": None,
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "aggregate",
                    "error": str(e),
                },
                "logs": [f"Aggregate transform failed: {e!s}"],
            }

    async def _execute_format_transform(
        self, ticket_id: str, parameters: dict[str, Any], span
    ) -> dict[str, Any]:
        """Executa formatação de dados."""
        try:
            data = parameters.get("data")
            if not data:
                raise ValueError("Missing 'data' parameter for format transform")

            format_rules = parameters.get("format_rules", [])
            result = data

            for rule in format_rules:
                field = rule.get("field")
                rule_type = rule.get("type")
                value = rule.get("value")

                # Apply format to nested fields using dot notation
                def apply_format(obj, field_parts, format_rule):
                    if len(field_parts) == 1:
                        field_name = field_parts[0]
                        old_value = obj.get(field_name)
                        new_value = old_value

                        if rule_type == "date":
                            if old_value:
                                try:
                                    if isinstance(old_value, (int, float)):
                                        # Unix timestamp to date
                                        if old_value > 1000000000000:  # milliseconds
                                            dt = datetime.utcfromtimestamp(old_value / 1000)
                                        else:
                                            dt = datetime.utcfromtimestamp(old_value)
                                        new_value = dt.strftime(value)
                                except Exception:
                                    pass
                            obj[field_name] = new_value
                        elif rule_type == "number":
                            if old_value is not None:
                                with contextlib.suppress(BaseException):
                                    obj[field_name] = float(old_value)
                        elif rule_type == "string":
                            obj[field_name] = str(old_value)
                        elif rule_type == "uppercase":
                            obj[field_name] = str(old_value).upper() if old_value else old_value
                        elif rule_type == "lowercase":
                            obj[field_name] = str(old_value).lower() if old_value else old_value
                        elif rule_type == "trim":
                            obj[field_name] = str(old_value).strip() if old_value else old_value
                    # Nested field
                    elif field_name in obj and isinstance(obj[field_name], dict):
                        apply_format(obj[field_name], field_parts[1:], format_rule)

                apply_format(result, field.split("."), rule)

            self.log_execution(
                ticket_id, "format_transform_completed", rules_count=len(format_rules)
            )

            return {
                "success": True,
                "output": {"formatted_data": result},
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "format",
                    "rules_count": len(format_rules),
                },
                "logs": [
                    f"Format transform completed with {len(format_rules)} rules",
                    "Transform completed successfully",
                ],
            }

        except Exception as e:
            self.log_execution(ticket_id, "format_transform_failed", level="error", error=str(e))
            return {
                "success": False,
                "output": None,
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "format",
                    "error": str(e),
                },
                "logs": [f"Format transform failed: {e!s}"],
            }

    async def _execute_mongodb_transform(
        self, ticket_id: str, parameters: dict[str, Any], span
    ) -> dict[str, Any]:
        """Executa transformação em dados MongoDB."""
        if not self.mongodb_client:
            return self._error_result("MongoDB client not available", "mongodb")

        # Nota: Validacao de .db removida para evitar erro de Motor 3.x
        # Motor 3.x proibe verificacao de truthiness em objetos Database
        # Acessamos diretamente via client[db_name] para evitar o problema

        try:
            collection_name = parameters.get("collection")
            if not collection_name:
                raise ValueError("Missing 'collection' parameter for MongoDB transform")

            pipeline = parameters.get("pipeline", [])
            if not pipeline:
                raise ValueError("Missing 'pipeline' parameter for MongoDB transform")

            # Obter coleção - acessar via client para evitar issues com Motor 3.x
            db_name = self.mongodb_client.config.mongodb_database
            db = self.mongodb_client.client[db_name]
            collection = db[collection_name]
            cursor = collection.aggregate(pipeline)
            results = await cursor.to_list(length=1000)

            # Serializar documentos
            serialized_results = [self._serialize_doc(doc) for doc in results]

            self.log_execution(
                ticket_id,
                "mongodb_transform_completed",
                collection=collection_name,
                result_count=len(serialized_results),
            )

            return {
                "success": True,
                "output": {
                    "transformed_data": serialized_results,
                    "count": len(serialized_results),
                },
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "mongodb_query_transform",
                    "collection": collection_name,
                },
                "logs": [
                    f"MongoDB transform completed on {collection_name}",
                    f"Pipeline returned {len(serialized_results)} results",
                    "Transform completed successfully",
                ],
            }

        except Exception as e:
            self.log_execution(ticket_id, "mongodb_transform_failed", level="error", error=str(e))
            return {
                "success": False,
                "output": None,
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "mongodb_query_transform",
                    "error": str(e),
                },
                "logs": [f"MongoDB transform failed: {e!s}"],
            }

    async def _execute_filter_transform(
        self, ticket_id: str, parameters: dict[str, Any], span
    ) -> dict[str, Any]:
        """Executa filtragem de dados."""
        try:
            data = parameters.get("data")
            if not data:
                raise ValueError("Missing 'data' parameter for filter transform")

            filters = parameters.get("filters", [])
            if not filters:
                raise ValueError("Missing 'filters' parameter for filter transform")

            if not isinstance(data, list):
                raise ValueError("'data' parameter must be a list for filtering")

            # Apply filters
            result = data
            for filter_rule in filters:
                field = filter_rule.get("field")
                operator = filter_rule.get("operator", "eq")
                value = filter_rule.get("value")

                if operator == "eq":
                    result = [item for item in result if item.get(field) == value]
                elif operator == "ne":
                    result = [item for item in result if item.get(field) != value]
                elif operator == "gt":
                    result = [item for item in result if item.get(field, 0) > value]
                elif operator == "lt":
                    result = [item for item in result if item.get(field, 0) < value]
                elif operator == "gte":
                    result = [item for item in result if item.get(field, 0) >= value]
                elif operator == "lte":
                    result = [item for item in result if item.get(field, 0) <= value]
                elif operator == "in":
                    result = [item for item in result if item.get(field) in value]
                elif operator == "contains":
                    result = [item for item in result if value in item.get(field, "")]
                elif operator == "exists":
                    result = [item for item in result if item.get(field) is not None]
                elif operator == "regex":
                    import re

                    pattern = value
                    result = [
                        item for item in result if re.search(pattern, str(item.get(field, "")))
                    ]
                else:
                    raise ValueError(f"Unsupported filter operator: {operator}")

            self.log_execution(
                ticket_id,
                "filter_transform_completed",
                input_count=len(data),
                output_count=len(result),
                filters_count=len(filters),
            )

            return {
                "success": True,
                "output": {"filtered_data": result, "count": len(result)},
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "filter",
                    "input_count": len(data),
                    "output_count": len(result),
                },
                "logs": [
                    f"Filter transform completed: {len(data)} -> {len(result)} records",
                    f"{len(filters)} filters applied",
                    "Transform completed successfully",
                ],
            }

        except Exception as e:
            self.log_execution(ticket_id, "filter_transform_failed", level="error", error=str(e))
            return {
                "success": False,
                "output": None,
                "metadata": {
                    "executor": "TransformExecutor",
                    "transform_type": "filter",
                    "error": str(e),
                },
                "logs": [f"Filter transform failed: {e!s}"],
            }

    def _apply_map(self, data: Any, operation: dict) -> Any:
        """Aplica operação de map."""
        field = operation.get("field")
        mapping = operation.get("mapping", {})
        new_data = []

        if isinstance(data, list):
            for item in data:
                new_item = dict(item) if isinstance(item, dict) else {}
                if field in item:
                    value = item.get(field)
                    new_value = mapping.get(value, value)
                    new_item[field] = new_value
                new_data.append(new_item)
            return new_data
        return data

    def _apply_filter(self, data: Any, operation: dict) -> Any:
        """Aplica operação de filter."""
        field = operation.get("field")
        operator = operation.get("operator", "eq")
        value = operation.get("value")

        if isinstance(data, list):
            if operator == "eq":
                return [item for item in data if item.get(field) == value]
            if operator == "ne":
                return [item for item in data if item.get(field) != value]
            if operator == "gt":
                return [item for item in data if item.get(field, 0) > value]
            if operator == "lt":
                return [item for item in data if item.get(field, 0) < value]
            if operator == "in":
                return [item for item in data if item.get(field) in value]
        return data

    def _apply_aggregate(self, data: Any, operation: dict) -> Any:
        """Aplica operação de aggregate."""
        # Simplificada - implementação completa em _execute_aggregate_transform
        return data

    def _rename_keys(self, data: Any, operation: dict) -> Any:
        """Renomeia chaves em objetos."""
        mapping = operation.get("mapping", {})
        if isinstance(data, list):
            return [{mapping.get(k, k): v for k, v in item.items()} for item in data]
        return data

    def _select_keys(self, data: Any, operation: dict) -> Any:
        """Seleciona chaves específicas."""
        keys = operation.get("keys", [])
        if isinstance(data, list):
            return [{k: v for k, v in item.items() if k in keys} for item in data]
        return data

    def _sort(self, data: Any, operation: dict) -> Any:
        """Ordena dados."""
        field = operation.get("field")
        reverse = operation.get("reverse", False)
        if isinstance(data, list):
            return sorted(data, key=lambda x: x.get(field, ""), reverse=reverse)
        return data

    def _apply_json_operations(self, input_data: Any, operations: list[dict]) -> Any:
        """Aplica em sequência as operations json sobre ``input_data``.

        Dispatch por tabela (em vez de if/elif) para manter a complexidade baixa.

        Raises:
            ValueError: Se uma operation tiver um ``type`` não suportado.
        """
        dispatch = {
            "map": self._apply_map,
            "filter": self._apply_filter,
            "aggregate": self._apply_aggregate,
            "rename_keys": self._rename_keys,
            "select_keys": self._select_keys,
            "sort": self._sort,
            "count": self._count,
        }
        result = input_data
        for operation in operations:
            op_type = operation.get("type")
            handler = dispatch.get(op_type)
            if handler is None:
                raise ValueError(f"Unsupported operation type: {op_type}")
            result = handler(result, operation)
        return result

    def _count(self, data: Any, operation: dict) -> Any:
        """Conta elementos de uma lista (operação schema-agnóstica).

        Deriva um output não-trivial de qualquer lista de documentos sem depender
        do schema concreto. ``alias`` permite renomear a chave de saída.
        """
        alias = operation.get("alias", "count")
        if isinstance(data, list):
            return {alias: len(data)}
        if isinstance(data, dict):
            # Defensivo: se ainda é o envelope do QueryExecutor, contar os
            # documentos (não as chaves do envelope).
            for key in (*_INPUT_REF_FALLBACK_FIELDS, "data", "items"):
                if isinstance(data.get(key), list):
                    return {alias: len(data[key])}
            return {alias: len(data)}
        return {alias: 0 if data is None else 1}

    def _serialize_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Serializa documento MongoDB para JSON."""
        if "_id" in doc:
            doc = dict(doc)
            doc["_id"] = str(doc["_id"])
        return doc

    def _success_result(self, output_data: Any, message: str | None = None) -> dict[str, Any]:
        """Retorna resultado de sucesso padronizado.

        ``message`` é uma mensagem de log opcional (legível) que descreve o
        resultado; é acrescentada à lista de logs. Não confundir com metadata:
        os call-sites passam sempre uma string descritiva.
        """
        base_metadata = {"executor": "TransformExecutor", "success": True}

        logs = ["Transform completed successfully"]
        if message:
            logs.insert(0, message)

        return {
            "success": True,
            "output": output_data,
            "metadata": base_metadata,
            "logs": logs,
        }

    def _resolve_json_input(
        self, ticket_id: str, parameters: dict[str, Any]
    ) -> tuple[Any, dict[str, Any] | None]:
        """Resolve o ``input_data`` de uma transform json (Task 7).

        Quando ``input_data`` está vazio mas existe ``input_ref``, resolve-o contra
        os ``dependency_outputs`` injetados em runtime. Retorna ``(input_data,
        degraded_result)``: se a resolução falhar, ``degraded_result`` é um
        resultado honesto marcado (real_path_unavailable) e ``input_data`` é None.
        """
        input_data = parameters.get("input_data")
        input_ref = parameters.get("input_ref")
        dependency_outputs = parameters.get("dependency_outputs") or {}

        # input_ref tem PRECEDÊNCIA: é a diretiva explícita de data-flow que navega
        # até ao campo certo (ex.: documents). O execution_engine pré-injeta em
        # input_data o ENVELOPE da dependência ({documents, count}); operar sobre o
        # envelope contaria as chaves, não os documentos. Por isso, havendo
        # input_ref, resolvemo-lo primeiro contra dependency_outputs.
        if input_ref:
            resolved, reason = resolve_input_ref(input_ref, dependency_outputs)
            if reason is None:
                return resolved, None
            # input_ref não resolveu: tentar desembrulhar o envelope já em input_data
            # (fallback resiliente) antes de degradar.
            unwrapped = self._unwrap_envelope(input_data)
            if unwrapped is not None:
                return unwrapped, None
            # Degradação REAL: input_ref existe e não há dados a montante.
            return None, self._input_ref_degraded_result(ticket_id, input_ref, reason)

        # Sem input_ref: usa input_data direto, desembrulhando se for um envelope
        # {documents/results} (compatível com o output do QueryExecutor).
        return self._unwrap_envelope(input_data), None

    @staticmethod
    def _unwrap_envelope(value: Any) -> Any:
        """Desembrulha o envelope do QueryExecutor para a lista de documentos.

        Se ``value`` é um dict com uma chave de lista conhecida
        (documents/results/data/items), devolve essa lista; caso contrário devolve
        ``value`` inalterado (lista direta, string JSON, None, etc.).
        """
        if isinstance(value, dict):
            for key in (*_INPUT_REF_FALLBACK_FIELDS, "data", "items"):
                if isinstance(value.get(key), list):
                    return value[key]
        return value

    def _input_ref_degraded_result(
        self, ticket_id: str, input_ref: str, reason: str
    ) -> dict[str, Any]:
        """Resultado honesto quando um ``input_ref`` não resolve (degradação real).

        Marca a métrica ``real_path_unavailable_total`` e devolve ``success=False``
        com ``real_path_unavailable: True`` — nunca um transform "completo"
        silencioso (§5.4 Caminho Real First-Class).
        """
        self.log_execution(
            ticket_id,
            "transform_input_ref_unresolved",
            level="warning",
            degraded=True,
            input_ref=input_ref,
            reason=reason,
        )
        if self.metrics and hasattr(self.metrics, "real_path_unavailable_total"):
            self.metrics.real_path_unavailable_total.labels(
                executor="TransformExecutor", task_type="TRANSFORM"
            ).inc()
        return {
            "success": False,
            "output": {"transformed_data": None, "input_ref": input_ref},
            "metadata": {
                "executor": "TransformExecutor",
                "transform_type": "json",
                "simulated": False,
                "real_path_unavailable": True,
                "reason": reason,
            },
            "logs": [
                f"JSON transform degradado: input_ref '{input_ref}' não resolve",
                reason,
                "Ticket marcado como FAILED (sem transform simulado)",
            ],
        }

    def _error_result(self, message: str, transform_type: str) -> dict[str, Any]:
        """Retorna resultado de erro padronizado."""
        return {
            "success": False,
            "output": None,
            "metadata": {
                "executor": "TransformExecutor",
                "transform_type": transform_type,
                "error": message,
            },
            "logs": [message],
        }
