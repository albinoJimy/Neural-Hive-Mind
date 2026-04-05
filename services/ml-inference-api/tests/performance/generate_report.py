#!/usr/bin/env python3
"""
Script para gerar relatório consolidado de testes de performance.

Executa todos os testes de performance e gera um relatório com:
- Latências (p50, p95, p99)
- Throughput
- Uso de memória
- Comparação com targets do spec

Uso:
    python generate_report.py [--output report.html] [--format html|text]
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Targets do spec ML-001-08
PERFORMANCE_TARGETS = {
    "latency_p50_max_ms": 50,
    "latency_p95_max_ms": 100,
    "latency_p99_max_ms": 200,
    "throughput_min_req_per_sec": 1000,
    "batch_efficiency_ratio": 10,
}


def run_pytest(json_file: Path) -> dict:
    """
    Executa pytest com saída JSON.

    Args:
        json_file: Caminho para arquivo de saída JSON

    Returns:
        Dicionário com resultados dos testes
    """
    cmd = [
        "pytest",
        "tests/performance/",
        "-v",
        "--tb=short",
        "--asyncio-mode=auto",
        "-m", "performance",
        "--json-report",
        f"--json-report-file={json_file}",
    ]

    print("Executando testes de performance...")
    print(f"Comando: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=Path(__file__).parent.parent.parent,
        capture_output=True,
        text=True,
    )

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def parse_json_report(json_file: Path) -> dict:
    """
    Parse relatório JSON do pytest-json-report.

    Args:
        json_file: Caminho para arquivo JSON

    Returns:
        Dados do relatório
    """
    try:
        with open(json_file) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def extract_metrics(report: dict) -> dict:
    """
    Extrai métricas do relatório de testes.

    Args:
        report: Relatório JSON do pytest

    Returns:
        Métricas extraídas
    """
    metrics = {
        "summary": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "duration": 0,
        },
        "tests": {},
        "targets_met": {},
        "targets_failed": {},
    }

    if not report:
        return metrics

    # Summary
    summary = report.get("summary", {})
    metrics["summary"]["total"] = summary.get("total", 0)
    metrics["summary"]["passed"] = summary.get("passed", 0)
    metrics["summary"]["failed"] = summary.get("failed", 0)
    metrics["summary"]["skipped"] = summary.get("skipped", 0)
    metrics["summary"]["duration"] = summary.get("duration", 0)

    # Extract individual test results
    tests = report.get("tests", [])
    for test in tests:
        test_name = test.get("name", "unknown")
        outcome = test.get("outcome", "unknown")
        duration = test.get("duration", 0)

        # Categorizar testes
        category = "other"
        if "latency" in test_name:
            category = "latency"
        elif "throughput" in test_name:
            category = "throughput"
        elif "concurrent" in test_name:
            category = "concurrent"
        elif "memory" in test_name:
            category = "memory"

        if category not in metrics["tests"]:
            metrics["tests"][category] = []

        metrics["tests"][category].append({
            "name": test_name,
            "outcome": outcome,
            "duration": duration,
        })

    # Verificar targets baseado nos nomes dos testes
    for test in tests:
        test_name = test.get("name", "")
        outcome = test.get("outcome", "unknown")

        # Inferir qual target está sendo testado
        target_key = None
        if "p50" in test_name and "latency" in test_name:
            target_key = "latency_p50_max_ms"
        elif "p99" in test_name and "latency" in test_name:
            target_key = "latency_p99_max_ms"
        elif "throughput" in test_name and "burst" in test_name:
            target_key = "throughput_min_req_per_sec"
        elif "efficiency" in test_name:
            target_key = "batch_efficiency_ratio"

        if target_key:
            if outcome == "passed":
                metrics["targets_met"][target_key] = PERFORMANCE_TARGETS[target_key]
            elif outcome == "failed":
                metrics["targets_failed"][target_key] = PERFORMANCE_TARGETS[target_key]

    return metrics


def generate_text_report(metrics: dict) -> str:
    """
    Gera relatório em formato texto.

    Args:
        metrics: Métricas extraídas

    Returns:
        Relatório formatado
    """
    lines = [
        "=" * 70,
        "RELATÓRIO DE PERFORMANCE - ML Inference API",
        f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
        "RESUMO",
        "-" * 70,
        f"  Total de testes:    {metrics['summary']['total']}",
        f"  Passou:             {metrics['summary']['passed']} ✓",
        f"  Falhou:             {metrics['summary']['failed']} ✗",
        f"  Pulado:             {metrics['summary']['skipped']}",
        f"  Duração:            {metrics['summary']['duration']:.2f}s",
        "",
        "TARGETS DO SPEC (ML-001-08)",
        "-" * 70,
    ]

    # Targets
    for target, value in PERFORMANCE_TARGETS.items():
        status = "✓" if target in metrics["targets_met"] else ("✗" if target in metrics["targets_failed"] else "?")
        lines.append(f"  {status} {target}: {value}")

    lines.extend([
        "",
        "DETALHAMENTO POR CATEGORIA",
        "-" * 70,
    ])

    # Por categoria
    for category, tests in metrics["tests"].items():
        lines.append(f"\n{category.upper()} ({len(tests)} testes)")

        passed = sum(1 for t in tests if t["outcome"] == "passed")
        lines.append(f"  Passou: {passed}/{len(tests)}")

        for test in tests[:5]:  # Mostrar até 5 por categoria
            status_symbol = "✓" if test["outcome"] == "passed" else ("✗" if test["outcome"] == "failed" else "-")
            lines.append(f"    {status_symbol} {test['name'][:60]} ({test['duration']:.3f}s)")

        if len(tests) > 5:
            lines.append(f"    ... e mais {len(tests) - 5} testes")

    lines.extend([
        "",
        "=" * 70,
        "Legenda: ✓ Passou  ✗ Falhou  - Pulado",
        "=" * 70,
    ])

    return "\n".join(lines)


def generate_html_report(metrics: dict) -> str:
    """
    Gera relatório em formato HTML.

    Args:
        metrics: Métricas extraídas

    Returns:
        HTML formatado
    """
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relatório Performance - ML Inference API</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
        }}
        .header p {{
            margin: 0;
            opacity: 0.9;
        }}
        .card {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}
        .metric {{
            text-align: center;
            padding: 15px;
            border-radius: 8px;
            background: #f8f9fa;
        }}
        .metric.passed {{
            background: #d4edda;
            color: #155724;
        }}
        .metric.failed {{
            background: #f8d7da;
            color: #721c24;
        }}
        .metric h3 {{
            margin: 0 0 5px 0;
            font-size: 2em;
        }}
        .metric p {{
            margin: 0;
            opacity: 0.8;
        }}
        .targets {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 10px;
        }}
        .target {{
            padding: 10px 15px;
            border-radius: 5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .target.met {{
            background: #d4edda;
            border-left: 4px solid #28a745;
        }}
        .target.failed {{
            background: #f8d7da;
            border-left: 4px solid #dc3545;
        }}
        .target.unknown {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
        }}
        .test-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .test-item {{
            padding: 10px;
            border-bottom: 1px solid #eee;
            display: flex;
            align-items: center;
        }}
        .test-item:last-child {{
            border-bottom: none;
        }}
        .status {{
            width: 20px;
            height: 20px;
            border-radius: 50%;
            margin-right: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
        }}
        .status.passed {{
            background: #28a745;
            color: white;
        }}
        .status.failed {{
            background: #dc3545;
            color: white;
        }}
        .status.skipped {{
            background: #ffc107;
            color: white;
        }}
        .test-name {{
            flex: 1;
            font-family: monospace;
            font-size: 14px;
        }}
        .test-duration {{
            color: #666;
            font-size: 14px;
        }}
        h2 {{
            margin-top: 0;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        .category {{
            margin-bottom: 30px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 Relatório de Performance</h1>
        <p>ML Inference API - Testes de Performance (ML-001-08)</p>
        <p>Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="card">
        <h2>📊 Resumo</h2>
        <div class="summary">
            <div class="metric">
                <h3>{metrics['summary']['total']}</h3>
                <p>Total de Testes</p>
            </div>
            <div class="metric {'passed' if metrics['summary']['failed'] == 0 else 'failed'}">
                <h3>{metrics['summary']['passed']}</h3>
                <p>Passou ✓</p>
            </div>
            <div class="metric failed">
                <h3>{metrics['summary']['failed']}</h3>
                <p>Falhou ✗</p>
            </div>
            <div class="metric">
                <h3>{metrics['summary']['skipped']}</h3>
                <p>Pulado</p>
            </div>
            <div class="metric">
                <h3>{metrics['summary']['duration']:.2f}s</h3>
                <p>Duração Total</p>
            </div>
        </div>
    </div>

    <div class="card">
        <h2>🎯 Targets do Spec (ML-001-08)</h2>
        <div class="targets">
"""

    # Adicionar targets
    for target, value in PERFORMANCE_TARGETS.items():
        if target in metrics["targets_met"]:
            status_class = "met"
            status_icon = "✓"
        elif target in metrics["targets_failed"]:
            status_class = "failed"
            status_icon = "✗"
        else:
            status_class = "unknown"
            status_icon = "?"

        target_label = target.replace("_", " ").title()
        html += f"""
            <div class="target {status_class}">
                <span>{status_icon} {target_label}</span>
                <strong>{value}</strong>
            </div>
"""

    html += """
        </div>
    </div>
"""

    # Adicionar testes por categoria
    for category, tests in metrics["tests"].items():
        passed = sum(1 for t in tests if t["outcome"] == "passed")
        failed = sum(1 for t in tests if t["outcome"] == "failed")
        skipped = sum(1 for t in tests if t["outcome"] == "skipped")

        html += f"""
    <div class="card">
        <h2>📈 {category.upper().replace('_', ' ')}</h2>
        <p>{passed} passou, {failed} falhou, {skipped} pulado</p>
        <ul class="test-list">
"""

        for test in tests:
            status_class = test["outcome"]
            status_symbol = {
                "passed": "✓",
                "failed": "✗",
                "skipped": "-",
            }.get(test["outcome"], "?")

            html += f"""
            <li class="test-item">
                <span class="status {status_class}">{status_symbol}</span>
                <span class="test-name">{test['name']}</span>
                <span class="test-duration">{test['duration']:.3f}s</span>
            </li>
"""

        html += """
        </ul>
    </div>
"""

    html += """
</body>
</html>
"""

    return html


def main() -> int:
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Gera relatório de testes de performance"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="performance_report.html",
        help="Arquivo de saída do relatório",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["html", "text"],
        default="html",
        help="Formato do relatório",
    )
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="Não executar os testes (usar arquivo JSON existente)",
    )

    args = parser.parse_args()

    # Caminho para arquivo JSON
    json_file = Path(args.output).with_suffix(".json")

    # Executar testes se solicitado
    if not args.no_run:
        result = run_pytest(json_file)
        if result["returncode"] != 0 and result["stderr"]:
            print("Warn: Testes falharam ou houve erros", file=sys.stderr)

    # Parse relatório
    report = parse_json_report(json_file)

    # Extrair métricas
    metrics = extract_metrics(report)

    # Gerar relatório
    if args.format == "html":
        content = generate_html_report(metrics)
    else:
        content = generate_text_report(metrics)

    # Escrever arquivo
    output_file = Path(args.output)
    output_file.write_text(content, encoding="utf-8")

    print(f"\n✓ Relatório gerado: {output_file.absolute()}")

    # Retornar código de erro baseado nos testes
    return 1 if metrics["summary"]["failed"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
