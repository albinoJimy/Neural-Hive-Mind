"""
Export utilities for insights.
Supports JSON, CSV, and text-based PDF export.
"""
from datetime import datetime
from typing import Dict, Any, List
import csv
import io

from ..models.insight_extended import InsightResponse


def export_to_json(insight: InsightResponse) -> str:
    """Export insight to JSON string."""
    import json
    return json.dumps(insight.dict(), indent=2, default=str)


def export_to_csv(insight: InsightResponse) -> str:
    """Export insight to CSV format."""
    output = io.StringIO()

    # Main metadata
    writer = csv.writer(output)
    writer.writerow(["Field", "Value"])
    writer.writerow(["Insight ID", insight.insight_id])
    writer.writerow(["Type", insight.analysis_type])
    writer.writerow(["Title", insight.title])
    writer.writerow(["Description", insight.description])
    writer.writerow(["Status", insight.status])
    writer.writerow(["Created At", insight.created_at.isoformat()])
    writer.writerow(["Source", insight.metadata.source])
    writer.writerow(["Created By", insight.metadata.created_by])
    writer.writerow(["Tags", ", ".join(insight.tags)])
    writer.writerow([])

    # Metrics
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Processing Time (ms)", insight.metrics.processing_time_ms])
    writer.writerow(["Confidence Score", insight.metrics.confidence_score])
    writer.writerow(["Data Points", insight.metrics.data_points])
    writer.writerow([])

    # Data (simplified)
    writer.writerow(["Data Key", "Data Value"])
    for key, value in insight.data.items():
        if isinstance(value, (str, int, float, bool)):
            writer.writerow([key, str(value)])
        elif isinstance(value, list):
            writer.writerow([key, f"[{len(value)} items]"])
        elif isinstance(value, dict):
            writer.writerow([key, f"[{len(value)} keys]"])
        else:
            writer.writerow([key, str(type(value).__name__)])

    return output.getvalue()


def export_to_pdf_text(insight: InsightResponse) -> bytes:
    """
    Export insight to text-based PDF format.
    Returns bytes that can be served as application/pdf.
    """
    lines = [
        "=" * 70,
        f"INSIGHT REPORT: {insight.title}",
        "=" * 70,
        "",
        f"ID: {insight.insight_id}",
        f"Type: {insight.analysis_type}",
        f"Status: {insight.status}",
        f"Created: {insight.created_at.isoformat()}",
        f"Source: {insight.metadata.source}",
        "",
        "-" * 70,
        "DESCRIPTION",
        "-" * 70,
        insight.description,
        "",
        "-" * 70,
        "METRICS",
        "-" * 70,
        f"Processing Time: {insight.metrics.processing_time_ms} ms",
        f"Confidence Score: {insight.metrics.confidence_score:.2%}",
        f"Data Points: {insight.metrics.data_points}",
        "",
        "-" * 70,
        "TAGS",
        "-" * 70,
    ]

    if insight.tags:
        lines.extend(insight.tags)
    else:
        lines.append("(none)")

    lines.extend([
        "",
        "-" * 70,
        "DATA",
        "-" * 70,
    ])

    for key, value in insight.data.items():
        if isinstance(value, (str, int, float, bool)):
            lines.append(f"{key}: {value}")
        elif isinstance(value, list):
            lines.append(f"{key}: [list with {len(value)} items]")
        elif isinstance(value, dict):
            lines.append(f"{key}: [dict with {len(value)} keys]")
        else:
            lines.append(f"{key}: ({type(value).__name__})")

    lines.extend([
        "",
        "-" * 70,
        f"Generated: {datetime.utcnow().isoformat()}",
        "Neural Hive Mind - Analyst Agents",
        "=" * 70,
    ])

    text_content = "\n".join(lines)

    # Return as bytes for PDF content-type
    # Note: This is plain text served as PDF - a simple approach that works
    # For real PDF generation with formatting, use reportlab
    return text_content.encode("utf-8")


def export_insight(insight: InsightResponse, format: str) -> tuple[str, bytes]:
    """
    Export insight in specified format.

    Args:
        insight: InsightResponse to export
        format: "json", "csv", or "pdf"

    Returns:
        Tuple of (media_type, content_bytes)
    """
    if format == "json":
        return "application/json", export_to_json(insight).encode("utf-8")
    elif format == "csv":
        return "text/csv", export_to_csv(insight).encode("utf-8")
    elif format == "pdf":
        return "application/pdf", export_to_pdf_text(insight)
    else:
        raise ValueError(f"Unsupported format: {format}")
