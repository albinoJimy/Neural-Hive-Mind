"""
Coleta e análise de métricas de performance de builds.

Este módulo fornece funcionalidades para:
- Coletar métricas de builds (duração, tamanho, cache hits)
- Agregar métricas por linguagem, framework, plataforma
- Calcular estatísticas (média, mediana, percentis)
- Exportar métricas para formatos analisáveis
"""

import time
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import statistics
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class MetricType(Enum):
    """Tipos de métricas coletadas."""
    DURATION = "duration_seconds"
    SIZE = "size_bytes"
    CACHE_HIT = "cache_hit"
    SUCCESS_RATE = "success_rate"
    RESOURCE_USAGE = "resource_usage"


@dataclass
class BuildMetric:
    """Métrica individual de um build."""
    timestamp: str
    language: str
    framework: Optional[str]
    artifact_type: str
    platform: str
    builder_type: str  # "docker" ou "kaniko"
    success: bool
    duration_seconds: float
    size_bytes: Optional[int] = None
    cache_hit: bool = False
    multi_arch: bool = False
    platforms_count: int = 1
    has_error: bool = False
    error_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return asdict(self)


@dataclass
class MetricStats:
    """Estatísticas agregadas de métricas."""
    metric_type: str
    count: int
    mean: float
    median: float
    min: float
    max: float
    p95: float  # 95º percentil
    p99: float  # 99º percentil
    std_dev: float

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return asdict(self)


class BuildMetricsCollector:
    """
    Coletor de métricas de performance de builds.

    Funcionalidades:
    - Registrar métricas de builds individuais
    - Calcular estatísticas agregadas
    - Exportar métricas para JSON/CSV
    - Comparar performance entre builds
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Inicializa o coletor de métricas.

        Args:
            storage_path: Caminho para armazenar métricas persistidas
        """
        self.metrics: List[BuildMetric] = []
        self.storage_path = storage_path or "metrics/build_metrics.jsonl"
        self._load_metrics()

    def _load_metrics(self):
        """Carrega métricas persistidas do arquivo."""
        try:
            path = Path(self.storage_path)
            if path.exists():
                with open(path, "r") as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            self.metrics.append(BuildMetric(**data))
                logger.info(
                    "metrics_loaded",
                    count=len(self.metrics),
                    path=self.storage_path
                )
        except Exception as e:
            logger.warning("metrics_load_failed", error=str(e))

    def record_build(
        self,
        language: str,
        framework: Optional[str],
        artifact_type: str,
        platform: str,
        builder_type: str,
        success: bool,
        duration_seconds: float,
        size_bytes: Optional[int] = None,
        cache_hit: bool = False,
        platforms: Optional[List[str]] = None,
        error_type: Optional[str] = None,
    ) -> BuildMetric:
        """
        Registra uma métrica de build.

        Args:
            language: Linguagem do código (python, nodejs, etc)
            framework: Framework usado (fastapi, express, etc)
            artifact_type: Tipo de artefato (microservice, lambda, etc)
            platform: Plataforma de build (linux/amd64, etc)
            builder_type: Tipo de builder (docker, kaniko)
            success: Se o build foi bem-sucedido
            duration_seconds: Duração do build em segundos
            size_bytes: Tamanho da imagem em bytes
            cache_hit: Se o cache foi utilizado
            platforms: Lista de plataformas (para multi-arch)
            error_type: Tipo de erro (se houver)

        Returns:
            BuildMetric registrada
        """
        metric = BuildMetric(
            timestamp=datetime.utcnow().isoformat(),
            language=language,
            framework=framework,
            artifact_type=artifact_type,
            platform=platform,
            builder_type=builder_type,
            success=success,
            duration_seconds=duration_seconds,
            size_bytes=size_bytes,
            cache_hit=cache_hit,
            multi_arch=len(platforms) > 1 if platforms else False,
            platforms_count=len(platforms) if platforms else 1,
            has_error=not success,
            error_type=error_type,
        )

        self.metrics.append(metric)
        self._save_metric(metric)

        logger.info(
            "build_metric_recorded",
            language=language,
            framework=framework,
            duration=duration_seconds,
            success=success,
        )

        return metric

    def _save_metric(self, metric: BuildMetric):
        """Persiste uma métrica individual no arquivo."""
        try:
            path = Path(self.storage_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "a") as f:
                f.write(json.dumps(metric.to_dict()) + "\n")
        except Exception as e:
            logger.warning("metric_save_failed", error=str(e))

    def get_stats(
        self,
        metric_type: MetricType = MetricType.DURATION,
        group_by: Optional[str] = None,
        filter_by: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, MetricStats]:
        """
        Calcula estatísticas agregadas.

        Args:
            metric_type: Tipo de métrica para analisar
            group_by: Campo para agrupar (language, framework, builder_type, etc)
            filter_by: Filtros para aplicar (ex: {"language": "python"})

        Returns:
            Dicionário com estatísticas por grupo
        """
        # Filtrar métricas
        filtered = self._filter_metrics(filter_by)

        # Agrupar
        groups = self._group_metrics(filtered, group_by) if group_by else {"all": filtered}

        # Calcular estatísticas para cada grupo
        stats = {}
        for group_name, group_metrics in groups.items():
            values = self._extract_metric_values(group_metrics, metric_type)
            if values:
                stats[group_name] = self._calculate_stats(values, metric_type)

        return stats

    def _filter_metrics(self, filters: Optional[Dict[str, Any]]) -> List[BuildMetric]:
        """Filtra métricas baseado em critérios."""
        if not filters:
            return self.metrics

        filtered = []
        for metric in self.metrics:
            match = True
            for key, value in filters.items():
                metric_value = getattr(metric, key, None)
                if metric_value != value:
                    match = False
                    break
            if match:
                filtered.append(metric)

        return filtered

    def _group_metrics(self, metrics: List[BuildMetric], group_by: str) -> Dict[str, List[BuildMetric]]:
        """Agrupa métricas por um campo."""
        groups = {}
        for metric in metrics:
            group_value = getattr(metric, group_by, "unknown")
            if group_value not in groups:
                groups[group_value] = []
            groups[group_value].append(metric)
        return groups

    def _extract_metric_values(self, metrics: List[BuildMetric], metric_type: MetricType) -> List[float]:
        """Extrai valores numéricos baseado no tipo de métrica."""
        values = []
        for metric in metrics:
            if metric_type == MetricType.DURATION:
                values.append(metric.duration_seconds)
            elif metric_type == MetricType.SIZE:
                if metric.size_bytes:
                    values.append(metric.size_bytes)
            elif metric_type == MetricType.CACHE_HIT:
                values.append(1.0 if metric.cache_hit else 0.0)
            elif metric_type == MetricType.SUCCESS_RATE:
                values.append(1.0 if metric.success else 0.0)
        return values

    def _calculate_stats(self, values: List[float], metric_type: MetricType) -> MetricStats:
        """Calcula estatísticas descritivas."""
        sorted_values = sorted(values)
        n = len(sorted_values)

        return MetricStats(
            metric_type=metric_type.value,
            count=n,
            mean=statistics.mean(sorted_values),
            median=statistics.median(sorted_values),
            min=min(sorted_values),
            max=max(sorted_values),
            p95=self._percentile(sorted_values, 95),
            p99=self._percentile(sorted_values, 99),
            std_dev=statistics.stdev(sorted_values) if n > 1 else 0.0,
        )

    def _percentile(self, sorted_values: List[float], p: int) -> float:
        """Calcula percentil."""
        n = len(sorted_values)
        if n == 0:
            return 0.0
        k = (n - 1) * p / 100
        f = int(k)
        c = k - f
        if f + 1 < n:
            return sorted_values[f] + c * (sorted_values[f + 1] - sorted_values[f])
        return sorted_values[f]

    def compare_performance(
        self,
        metric_type: MetricType = MetricType.DURATION,
        dimension: str = "language",
    ) -> Dict[str, Dict[str, float]]:
        """
        Compara performance entre grupos.

        Args:
            metric_type: Tipo de métrica para comparar
            dimension: Dimensão para comparar (language, framework, etc)

        Returns:
            Dicionário com médias por grupo
        """
        stats = self.get_stats(metric_type=metric_type, group_by=dimension)
        comparison = {}

        for group_name, group_stats in stats.items():
            comparison[group_name] = {
                "mean": group_stats.mean,
                "median": group_stats.median,
                "count": group_stats.count,
            }

        # Ordenar por média
        sorted_comparison = dict(
            sorted(comparison.items(), key=lambda x: x[1]["mean"])
        )

        return sorted_comparison

    def get_performance_report(self) -> Dict[str, Any]:
        """
        Gera relatório completo de performance.

        Returns:
            Dicionário com relatório estruturado
        """
        total_builds = len(self.metrics)
        successful_builds = sum(1 for m in self.metrics if m.success)
        failed_builds = total_builds - successful_builds

        # Estatísticas por linguagem
        language_duration = self.compare_performance(
            metric_type=MetricType.DURATION,
            dimension="language"
        )

        # Estatísticas por builder
        builder_duration = self.compare_performance(
            metric_type=MetricType.DURATION,
            dimension="builder_type"
        )

        # Cache hit rate por linguagem
        cache_stats = self.get_stats(
            metric_type=MetricType.CACHE_HIT,
            group_by="language"
        )

        # Tamanho médio por linguagem
        size_stats = self.get_stats(
            metric_type=MetricType.SIZE,
            group_by="language"
        )

        # Multi-arch impact
        single_arch = [m for m in self.metrics if not m.multi_arch]
        multi_arch = [m for m in self.metrics if m.multi_arch]

        single_arch_duration = statistics.mean([m.duration_seconds for m in single_arch]) if single_arch else 0
        multi_arch_duration = statistics.mean([m.duration_seconds for m in multi_arch]) if multi_arch else 0
        multi_arch_overhead = ((multi_arch_duration / single_arch_duration) - 1) * 100 if single_arch_duration > 0 else 0

        return {
            "summary": {
                "total_builds": total_builds,
                "successful_builds": successful_builds,
                "failed_builds": failed_builds,
                "success_rate": successful_builds / total_builds if total_builds > 0 else 0,
            },
            "duration_by_language": language_duration,
            "duration_by_builder": builder_duration,
            "cache_hit_rate_by_language": {
                k: round(v.mean * 100, 1) for k, v in cache_stats.items()
            },
            "size_by_language_bytes": {
                k: round(v.mean, 0) for k, v in size_stats.items()
            },
            "multi_arch_impact": {
                "single_arch_avg_duration": round(single_arch_duration, 2),
                "multi_arch_avg_duration": round(multi_arch_duration, 2),
                "multi_arch_overhead_percent": round(multi_arch_overhead, 1),
                "single_arch_count": len(single_arch),
                "multi_arch_count": len(multi_arch),
            },
            "generated_at": datetime.utcnow().isoformat(),
        }

    def export_metrics(self, output_path: str, format: str = "json"):
        """
        Exporta métricas para arquivo.

        Args:
            output_path: Caminho do arquivo de saída
            format: Formato de exportação (json, csv)
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            with open(path, "w") as f:
                json.dump([m.to_dict() for m in self.metrics], f, indent=2)
        elif format == "jsonl":
            with open(path, "w") as f:
                for metric in self.metrics:
                    f.write(json.dumps(metric.to_dict()) + "\n")
        elif format == "csv":
            import csv
            with open(path, "w", newline="") as f:
                if self.metrics:
                    writer = csv.DictWriter(f, fieldnames=self.metrics[0].to_dict().keys())
                    writer.writeheader()
                    for metric in self.metrics:
                        writer.writerow(metric.to_dict())

        logger.info("metrics_exported", path=output_path, format=format, count=len(self.metrics))

    def get_slowest_builds(self, n: int = 10) -> List[Dict[str, Any]]:
        """
        Retorna os N builds mais lentos.

        Args:
            n: Número de builds a retornar

        Returns:
            Lista dos builds mais lentos
        """
        sorted_by_duration = sorted(
            self.metrics,
            key=lambda m: m.duration_seconds,
            reverse=True
        )

        return [
            {
                "timestamp": m.timestamp,
                "language": m.language,
                "framework": m.framework,
                "duration_seconds": m.duration_seconds,
                "platform": m.platform,
                "builder_type": m.builder_type,
                "success": m.success,
            }
            for m in sorted_by_duration[:n]
        ]

    def get_error_summary(self) -> Dict[str, Any]:
        """
        Resumo de erros de build.

        Returns:
            Dicionário com análise de erros
        """
        failed_metrics = [m for m in self.metrics if not success_checker(m)]

        error_types = {}
        for metric in failed_metrics:
            error_type = metric.error_type or "unknown"
            error_types[error_type] = error_types.get(error_type, 0) + 1

        errors_by_language = {}
        for metric in failed_metrics:
            lang = metric.language
            if lang not in errors_by_language:
                errors_by_language[lang] = {"count": 0, "errors": []}
            errors_by_language[lang]["count"] += 1
            errors_by_language[lang]["errors"].append(metric.error_type or "unknown")

        return {
            "total_errors": len(failed_metrics),
            "error_types": error_types,
            "errors_by_language": errors_by_language,
        }


def success_checker(metric: BuildMetric) -> bool:
    """Verifica se uma métrica indica sucesso."""
    return metric.success and not metric.has_error


# Instância global do coletor
_global_collector: Optional[BuildMetricsCollector] = None


def get_metrics_collector() -> BuildMetricsCollector:
    """Retorna a instância global do coletor de métricas."""
    global _global_collector
    if _global_collector is None:
        _global_collector = BuildMetricsCollector()
    return _global_collector
