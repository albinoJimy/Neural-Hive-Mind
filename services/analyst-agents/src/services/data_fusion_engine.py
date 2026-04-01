"""
Data Fusion Engine para Analyst Agents.

Funde dados de múltiplas fontes (MongoDB, PostgreSQL, ClickHouse, Neo4j)
em uma visão consolidada para análise.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

from ..models.query_request import QueryRequest

logger = structlog.get_logger(__name__)


class ConflictResolution(str, Enum):
    """Estratégias para resolução de conflitos."""

    KEEP_FIRST = "keep_first"
    KEEP_LAST = "keep_last"
    MERGE = "merge"
    HIGHEST_CONFIDENCE = "highest_confidence"
    LOWEST_CONFIDENCE = "lowest_confidence"


class AggregatedResult:
    """Resultado de agregação multi-source."""

    def __init__(
        self,
        query_id: str,
        sources: List[str],
        results: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.query_id = query_id
        self.sources = sources
        self.results = results
        self.metadata = metadata or {}
        self.fused_data = None
        self.conflicts = []
        self.warnings = []

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "query_id": self.query_id,
            "sources": self.sources,
            "results": self.results,
            "fused_data": self.fused_data,
            "conflicts": self.conflicts,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


class DataFusionEngine:
    """
    Motor de fusão de dados de múltiplas fontes.

    Normaliza esquemas, alinha temporalmente e resolve conflitos
    entre dados de diferentes fontes.
    """

    def __init__(
        self,
        conflict_resolution: ConflictResolution = ConflictResolution.HIGHEST_CONFIDENCE,
    ):
        self.conflict_resolution = conflict_resolution
        self.logger = logger

    async def fuse_sources(
        self,
        query_request: QueryRequest,
        source_results: Dict[str, Any],
    ) -> AggregatedResult:
        """
        Funde dados de múltiplas fontes.

        Args:
            query_request: Query request original
            source_results: Resultados por fonte

        Returns:
            AggregatedResult com dados fundidos
        """
        query_id = query_request.query_id
        sources = list(source_results.keys())

        self.logger.info(
            "data_fusion_started",
            query_id=query_id,
            sources=sources,
        )

        # Passo 1: Normalizar esquemas
        normalized = await self._normalize_schemas(source_results)

        # Passo 2: Alinhar temporalmente
        aligned = await self._align_temporal(normalized, query_request)

        # Passo 3: Fundir dados
        fused = await self._join_sources(aligned)

        # Passo 4: Resolver conflitos
        resolved = await self._resolve_conflicts(fused)

        # Passo 5: Enriquecer com contexto
        enriched = await self._enrich_with_context(resolved, query_request)

        # Criar resultado agregado
        result = AggregatedResult(
            query_id=query_id,
            sources=sources,
            results=source_results,
        )
        result.fused_data = enriched

        self.logger.info(
            "data_fusion_completed",
            query_id=query_id,
            sources_count=len(sources),
        )

        return result

    async def _normalize_schemas(self, source_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normaliza esquemas de diferentes fontes.

        Args:
            source_results: Resultados brutos por fonte

        Returns:
            Dicionário com esquemas normalizados
        """
        normalized = {}

        for source, data in source_results.items():
            if isinstance(data, dict) and "error" in data:
                normalized[source] = data
                continue

            try:
                if source == "mongodb":
                    normalized[source] = self._normalize_mongodb(data)
                elif source == "postgresql":
                    normalized[source] = self._normalize_postgresql(data)
                elif source == "clickhouse":
                    normalized[source] = self._normalize_clickhouse(data)
                elif source == "neo4j":
                    normalized[source] = self._normalize_neo4j(data)
                else:
                    normalized[source] = self._normalize_generic(data)
            except Exception as e:
                self.logger.warning("schema_normalization_failed", source=source, error=str(e))
                normalized[source] = {"error": str(e), "raw": data}

        return normalized

    def _normalize_mongodb(self, data: Any) -> Dict[str, Any]:
        """Normaliza dados do MongoDB."""
        if isinstance(data, list):
            return {
                "type": "list",
                "items": data,
                "count": len(data),
                "source": "mongodb",
            }
        elif isinstance(data, dict):
            return {
                "type": "document",
                "data": data,
                "source": "mongodb",
            }
        return {"raw": data, "source": "mongodb"}

    def _normalize_postgresql(self, data: Any) -> Dict[str, Any]:
        """Normaliza dados do PostgreSQL."""
        if isinstance(data, list):
            return {
                "type": "table",
                "rows": data,
                "count": len(data),
                "source": "postgresql",
            }
        elif isinstance(data, dict):
            return {
                "type": "row",
                "data": data,
                "source": "postgresql",
            }
        return {"raw": data, "source": "postgresql"}

    def _normalize_clickhouse(self, data: Any) -> Dict[str, Any]:
        """Normaliza dados do ClickHouse."""
        if isinstance(data, list):
            return {
                "type": "timeseries",
                "points": data,
                "count": len(data),
                "source": "clickhouse",
            }
        elif isinstance(data, dict):
            return {
                "type": "aggregated",
                "data": data,
                "source": "clickhouse",
            }
        return {"raw": data, "source": "clickhouse"}

    def _normalize_neo4j(self, data: Any) -> Dict[str, Any]:
        """Normaliza dados do Neo4j."""
        if isinstance(data, list):
            return {
                "type": "graph",
                "nodes": data,
                "count": len(data),
                "source": "neo4j",
            }
        elif isinstance(data, dict):
            return {
                "type": "path",
                "data": data,
                "source": "neo4j",
            }
        return {"raw": data, "source": "neo4j"}

    def _normalize_generic(self, data: Any) -> Dict[str, Any]:
        """Normaliza dados genéricos."""
        return {
            "type": "generic",
            "data": data,
            "source": "unknown",
        }

    async def _align_temporal(
        self,
        normalized: Dict[str, Any],
        query_request: QueryRequest,
    ) -> Dict[str, Any]:
        """
        Alinha dados temporalmente.

        Args:
            normalized: Dados normalizados
            query_request: Query request com janela temporal

        Returns:
            Dados alinhados temporalmente
        """
        time_window = query_request.time_window

        if not time_window:
            return normalized

        aligned = {}

        for source, data in normalized.items():
            try:
                # Filtrar por janela temporal se houver campo de timestamp
                if "items" in data or "rows" in data or "points" in data:
                    items_key = (
                        "items" if "items" in data else ("rows" if "rows" in data else "points")
                    )

                    filtered_items = []
                    for item in data[items_key]:
                        if self._is_in_time_window(item, time_window):
                            filtered_items.append(item)

                    aligned[source] = {**data, items_key: filtered_items}
                else:
                    aligned[source] = data
            except Exception as e:
                self.logger.warning("temporal_alignment_failed", source=source, error=str(e))
                aligned[source] = data

        return aligned

    def _is_in_time_window(
        self,
        item: Dict[str, Any],
        time_window: Dict[str, datetime],
    ) -> bool:
        """Verifica se item está na janela temporal."""
        # Tentar encontrar timestamp em campos comuns
        timestamp_fields = ["timestamp", "created_at", "updated_at", "executed_at", "time", "date"]

        for field in timestamp_fields:
            if field in item:
                try:
                    item_time = item[field]
                    if isinstance(item_time, str):
                        item_time = datetime.fromisoformat(item_time.replace("Z", "+00:00"))

                    if time_window.get("start") and item_time < time_window["start"]:
                        return False
                    if time_window.get("end") and item_time > time_window["end"]:
                        return False
                except (ValueError, TypeError):
                    pass

        return True  # Se não encontrar timestamp, assume que está na janela

    async def _join_sources(self, aligned: Dict[str, Any]) -> Dict[str, Any]:
        """
        Junta dados de múltiplas fontes.

        Args:
            aligned: Dados alinhados temporalmente

        Returns:
            Dados unidos
        """
        joined = {
            "sources": list(aligned.keys()),
            "by_source": aligned,
            "merged_metrics": {},
            "correlations": {},
        }

        # Extrair métricas comuns
        all_metrics = set()
        source_metrics = {}

        for source, data in aligned.items():
            if isinstance(data, dict) and "error" not in data:
                metrics = self._extract_metrics(data)
                source_metrics[source] = metrics
                all_metrics.update(metrics.keys())

        # Fundir métricas por nome
        for metric in all_metrics:
            values = {}
            for source, metrics in source_metrics.items():
                if metric in metrics:
                    values[source] = metrics[metric]

            if len(values) > 1:
                joined["merged_metrics"][metric] = values

        return joined

    def _extract_metrics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extrai métricas de dados normalizados."""
        metrics = {}

        # Se for lista de itens, extrair campos numéricos
        items_key = None
        for key in ["items", "rows", "points"]:
            if key in data:
                items_key = key
                break

        if items_key:
            for item in data[items_key]:
                if isinstance(item, dict):
                    for key, value in item.items():
                        if isinstance(value, (int, float)) and not key.endswith("_id"):
                            if key not in metrics:
                                metrics[key] = []
                            metrics[key].append(value)
        elif isinstance(data.get("data"), dict):
            # Item único
            for key, value in data["data"].items():
                if isinstance(value, (int, float)) and not key.endswith("_id"):
                    metrics[key] = [value]

        # Calcular agregações
        for key, values in metrics.items():
            if values:
                metrics[key] = {
                    "count": len(values),
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                }

        return metrics

    async def _resolve_conflicts(self, fused: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve conflitos entre fontes.

        Args:
            fused: Dados fundidos com possíveis conflitos

        Returns:
            Dados com conflitos resolvidos
        """
        resolved = {**fused}
        resolved_resolutions = {}

        for metric, source_values in fused.get("merged_metrics", {}).items():
            if len(source_values) > 1:
                # Conflito detectado - múltiplas fontes com mesma métrica
                resolution = self._resolve_metric_conflict(metric, source_values)
                resolved_resolutions[metric] = resolution

        resolved["resolved_metrics"] = resolved_resolutions

        return resolved

    def _resolve_metric_conflict(
        self, metric: str, source_values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Resolve conflito para uma métrica específica.

        Args:
            metric: Nome da métrica
            source_values: Valores por fonte

        Returns:
            Valor resolvido com metadata
        """
        if self.conflict_resolution == ConflictResolution.HIGHEST_CONFIDENCE:
            # Escolher fonte com maior confiança
            priority = ["postgresql", "mongodb", "clickhouse", "neo4j"]
            for source in priority:
                if source in source_values:
                    return {
                        "value": source_values[source],
                        "source": source,
                        "resolution": "highest_confidence",
                    }
        elif self.conflict_resolution == ConflictResolution.KEEP_FIRST:
            first_source = list(source_values.keys())[0]
            return {
                "value": source_values[first_source],
                "source": first_source,
                "resolution": "keep_first",
            }
        elif self.conflict_resolution == ConflictResolution.MERGE:
            # Calcular média dos valores
            if all(isinstance(v.get("avg"), (int, float)) for v in source_values.values()):
                avg_values = [v["avg"] for v in source_values.values()]
                return {
                    "value": sum(avg_values) / len(avg_values),
                    "sources": list(source_values.keys()),
                    "resolution": "merged_avg",
                }

        # Fallback: primeira fonte
        first_source = list(source_values.keys())[0]
        return {
            "value": source_values[first_source],
            "source": first_source,
            "resolution": "fallback",
        }

    async def _enrich_with_context(
        self,
        resolved: Dict[str, Any],
        query_request: QueryRequest,
    ) -> Dict[str, Any]:
        """
        Enriquece dados com contexto adicional.

        Args:
            resolved: Dados com conflitos resolvidos
            query_request: Query request original

        Returns:
            Dados enriquecidos
        """
        enriched = {**resolved}

        # Adicionar metadata de fusão
        enriched["fusion_metadata"] = {
            "fused_at": datetime.now(timezone.utc).isoformat(),
            "sources_count": len(resolved.get("sources", [])),
            "metrics_count": len(resolved.get("resolved_metrics", {})),
            "conflict_resolution": self.conflict_resolution.value,
        }

        # Adicionar contexto da query
        enriched["query_context"] = {
            "query_id": query_request.query_id,
            "plan_id": query_request.plan_id,
            "analyst_types": query_request.analyst_types,
        }

        return enriched

    async def get_correlation(
        self,
        source_results: Dict[str, Any],
        metric_x: str,
        metric_y: str,
    ) -> Optional[float]:
        """
        Calcula correlação entre duas métricas across sources.

        Args:
            source_results: Resultados por fonte
            metric_x: Nome da métrica X
            metric_y: Nome da métrica Y

        Returns:
            Coeficiente de correlação ou None
        """
        try:
            # Coletar pares de valores de todas as fontes
            x_values = []
            y_values = []

            for source, data in source_results.items():
                normalized = await self._normalize_schemas({source: data})
                metrics = self._extract_metrics(normalized.get(source, {}))

                if metric_x in metrics and metric_y in metrics:
                    x_val = metrics[metric_x].get("avg")
                    y_val = metrics[metric_y].get("avg")

                    if isinstance(x_val, (int, float)) and isinstance(y_val, (int, float)):
                        x_values.append(x_val)
                        y_values.append(y_val)

            if len(x_values) < 2:
                return None

            # Calcular correlação de Pearson
            n = len(x_values)
            sum_x = sum(x_values)
            sum_y = sum(y_values)
            sum_xy = sum(x * y for x, y in zip(x_values, y_values))
            sum_x2 = sum(x**2 for x in x_values)
            sum_y2 = sum(y**2 for y in y_values)

            numerator = n * sum_xy - sum_x * sum_y
            denominator = ((n * sum_x2 - sum_x**2) * (n * sum_y2 - sum_y**2)) ** 0.5

            if denominator == 0:
                return None

            correlation = numerator / denominator
            return max(-1, min(1, correlation))  # Limitar a [-1, 1]

        except Exception as e:
            self.logger.error(
                "correlation_calculation_failed", metric_x=metric_x, metric_y=metric_y, error=str(e)
            )
            return None
