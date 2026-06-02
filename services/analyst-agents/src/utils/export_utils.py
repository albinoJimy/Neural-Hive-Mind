"""
Export utilities for insights.
Supports JSON, CSV, and text-based PDF export.
"""

import csv
import io
from datetime import datetime, timezone

from ..models.insight_extended import InsightResponse


def export_to_json(insight: InsightResponse) -> str:
    """Export insight to JSON string."""
    import json

    # Support both Pydantic v1 and v2
    if hasattr(insight, "model_dump"):
        data = insight.model_dump()
    else:
        data = insight.dict()
    return json.dumps(data, indent=2, default=str)


def export_to_csv(insight: InsightResponse) -> str:
    """Export insight to CSV format."""
    output = io.StringIO()

    # Handle Pydantic v2 model_dump for accessing values
    if hasattr(insight, "model_dump"):
        data = insight.model_dump()
    else:
        data = insight.dict()

    # Main metadata
    writer = csv.writer(output)
    writer.writerow(["Field", "Value"])
    writer.writerow(["Insight ID", data.get("insight_id", "")])
    writer.writerow(["Type", data.get("analysis_type", "")])
    writer.writerow(["Title", data.get("title", "")])
    writer.writerow(["Description", data.get("description", "")])
    writer.writerow(["Status", data.get("status", "")])

    created_at = data.get("created_at")
    if created_at:
        writer.writerow(
            [
                "Created At",
                created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
            ]
        )

    metadata = data.get("metadata", {})
    if isinstance(metadata, dict):
        writer.writerow(["Source", metadata.get("source", "")])
        writer.writerow(["Created By", metadata.get("created_by", "")])
    else:
        writer.writerow(["Source", ""])
        writer.writerow(["Created By", ""])

    tags = data.get("tags", [])
    writer.writerow(["Tags", ", ".join(str(t) for t in tags)])
    writer.writerow([])

    # Metrics
    metrics = data.get("metrics", {})
    if isinstance(metrics, dict):
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Processing Time (ms)", metrics.get("processing_time_ms", "")])
        writer.writerow(["Confidence Score", metrics.get("confidence_score", "")])
        writer.writerow(["Data Points", metrics.get("data_points", "")])
    else:
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Processing Time (ms)", ""])
        writer.writerow(["Confidence Score", ""])
        writer.writerow(["Data Points", ""])
    writer.writerow([])

    # Data (simplified)
    insight_data = data.get("data", {})
    writer.writerow(["Data Key", "Data Value"])
    for key, value in insight_data.items():
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
    # Handle Pydantic v2 model_dump
    if hasattr(insight, "model_dump"):
        data = insight.model_dump()
    else:
        data = insight.dict()

    title = data.get("title", "")
    insight_id = data.get("insight_id", "")
    analysis_type = data.get("analysis_type", "")
    status = data.get("status", "")
    description = data.get("description", "")
    metrics = data.get("metrics", {})
    metadata = data.get("metadata", {})
    tags = data.get("tags", [])
    insight_data = data.get("data", {})

    created_at = data.get("created_at")
    created_str = (
        created_at.isoformat()
        if hasattr(created_at, "isoformat")
        else str(created_at)
        if created_at
        else ""
    )

    lines = [
        "=" * 70,
        f"INSIGHT REPORT: {title}",
        "=" * 70,
        "",
        f"ID: {insight_id}",
        f"Type: {analysis_type}",
        f"Status: {status}",
        f"Created: {created_str}",
        f"Source: {metadata.get('source', '') if isinstance(metadata, dict) else ''}",
        "",
        "-" * 70,
        "DESCRIPTION",
        "-" * 70,
        description,
        "",
        "-" * 70,
        "METRICS",
        "-" * 70,
        f"Processing Time: {metrics.get('processing_time_ms', 0) if isinstance(metrics, dict) else 0} ms",
        f"Confidence Score: {metrics.get('confidence_score', 0) if isinstance(metrics, dict) else 0:.2%}",
        f"Data Points: {metrics.get('data_points', 0) if isinstance(metrics, dict) else 0}",
        "",
        "-" * 70,
        "TAGS",
        "-" * 70,
    ]

    if tags:
        lines.extend(str(t) for t in tags)
    else:
        lines.append("(none)")

    lines.extend(
        [
            "",
            "-" * 70,
            "DATA",
            "-" * 70,
        ]
    )

    for key, value in insight_data.items():
        if isinstance(value, (str, int, float, bool)):
            lines.append(f"{key}: {value}")
        elif isinstance(value, list):
            lines.append(f"{key}: [list with {len(value)} items]")
        elif isinstance(value, dict):
            lines.append(f"{key}: [dict with {len(value)} keys]")
        else:
            lines.append(f"{key}: ({type(value).__name__})")

    lines.extend(
        [
            "",
            "-" * 70,
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "Neural Hive Mind - Analyst Agents",
            "=" * 70,
        ]
    )

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
