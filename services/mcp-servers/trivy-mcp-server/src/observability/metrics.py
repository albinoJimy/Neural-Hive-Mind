"""Métricas específicas do Trivy MCP Server."""

from prometheus_client import Counter, Histogram

# Métricas específicas de scan
TRIVY_SCANS_TOTAL = Counter(
    "trivy_scans_total",
    "Total de scans Trivy executados",
    ["scan_type", "status"]
)

TRIVY_SCAN_DURATION = Histogram(
    "trivy_scan_duration_seconds",
    "Duração dos scans Trivy em segundos",
    ["scan_type"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 180.0, 240.0, 300.0]
)

TRIVY_VULNERABILITIES_FOUND = Counter(
    "trivy_vulnerabilities_found_total",
    "Total de vulnerabilidades encontradas",
    ["severity"]
)


def setup_metrics() -> None:
    """Inicializa métricas (registra no registry default)."""
    pass


def record_scan(scan_type: str, status: str) -> None:
    """Registra um scan Trivy."""
    TRIVY_SCANS_TOTAL.labels(scan_type=scan_type, status=status).inc()


def record_scan_duration(scan_type: str, duration: float) -> None:
    """Registra a duração de um scan."""
    TRIVY_SCAN_DURATION.labels(scan_type=scan_type).observe(duration)


def record_vulnerabilities(severity: str, count: int) -> None:
    """Registra vulnerabilidades encontradas."""
    TRIVY_VULNERABILITIES_FOUND.labels(severity=severity).inc(count)
