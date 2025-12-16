#!/usr/bin/env python3
"""
Scanner de imports para identificar dependências não utilizadas ou ausentes.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = ROOT_DIR / "services"

SPECIAL_IMPORTS = {
    "python-jose": "jose",
    "python-multipart": "multipart",
    "python-dotenv": "dotenv",
    "avro-python3": "avro",
    "scikit-learn": "sklearn",
    "openai-whisper": "whisper",
    "sentence-transformers": "sentence_transformers",
}

UNUSED_EXCLUSIONS = {
    "uvicorn",
    "gunicorn",
    "opentelemetry-instrumentation-fastapi",
    "opentelemetry-instrumentation-grpc",
    "opentelemetry-instrumentation-aiohttp-client",
}

MISSING_IGNORE = {
    "os",
    "sys",
    "pathlib",
    "json",
    "typing",
    "logging",
    "asyncio",
    "dataclasses",
    "uuid",
    "time",
}


def normalize(name: str) -> str:
    return name.lower().replace("_", "-")


def parse_requirements(path: Path) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    if not path.exists():
        return entries
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-r ") or line.startswith("--"):
            continue
        if line.startswith("-e "):
            entries.append({"package": line, "normalized": line, "spec": "editable"})
            continue
        line = line.split("#", 1)[0].strip()
        match = re.split(r"(==|>=|<=|~=|!=)", line, maxsplit=1)
        if not match:
            continue
        if len(match) == 1:
            name = match[0]
            spec = ""
        else:
            name = match[0]
            spec = "".join(match[1:]).strip()
        base_name = name.split("[", 1)[0]
        entries.append(
            {
                "package": name,
                "normalized": normalize(base_name),
                "spec": spec,
            }
        )
    return entries


def gather_imports(service_path: Path) -> Dict[str, Set[str]]:
    imports: Dict[str, Set[str]] = defaultdict(set)
    for py_file in service_path.rglob("*.py"):
        rel = py_file.relative_to(service_path)
        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    imports[top].add(str(rel))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    imports[top].add(str(rel))
    return imports


def map_import_to_package(imp: str) -> str:
    normalized = normalize(imp)
    for req, mapped in SPECIAL_IMPORTS.items():
        if normalize(mapped) == normalized:
            return normalize(req)
    return normalized


def scan_service(service_path: Path) -> Dict[str, object]:
    requirements = parse_requirements(service_path / "requirements.txt")
    imports = gather_imports(service_path)
    req_lookup = {entry["normalized"]: entry for entry in requirements}

    used = []
    unused = []
    missing = []

    # Agrupa imports por pacote normalizado.
    import_map: Dict[str, Set[str]] = defaultdict(set)
    for imp, files in imports.items():
        import_map[map_import_to_package(imp)].update(files)

    for normalized_name, entry in req_lookup.items():
        if normalized_name in import_map:
            used.append(
                {
                    "package": entry["package"],
                    "spec": entry["spec"],
                    "import_count": len(import_map[normalized_name]),
                    "files": sorted(import_map[normalized_name]),
                }
            )
        elif entry["package"] not in UNUSED_EXCLUSIONS:
            unused.append(
                {
                    "package": entry["package"],
                    "spec": entry["spec"],
                    "reason": "Nenhum import encontrado",
                }
            )

    inverse_lookup = {normalize(entry["package"]): entry for entry in requirements}

    for imp, files in imports.items():
        normalized_imp = map_import_to_package(imp)
        if normalized_imp in req_lookup or imp in MISSING_IGNORE:
            continue
        if normalize(imp) in inverse_lookup:
            continue
        missing.append(
            {
                "import": imp,
                "files": sorted(files),
                "reason": "Não listado em requirements",
            }
        )

    return {
        "requirements": requirements,
        "used": sorted(used, key=lambda x: x["package"]),
        "unused": sorted(unused, key=lambda x: x["package"]),
        "missing": sorted(missing, key=lambda x: x["import"]),
    }


def build_version_matrix(results: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, str]]:
    matrix: Dict[str, Dict[str, str]] = defaultdict(dict)
    for service, data in results.items():
        for dep in data["requirements"]:
            matrix[dep["normalized"]][service] = dep["spec"] or "unspecified"
    return matrix


def main() -> None:
    parser = argparse.ArgumentParser(description="Scanner de imports e requirements.")
    parser.add_argument("--output", type=Path, default=ROOT_DIR / "reports" / "unused-imports.json")
    parser.add_argument("--service", help="Audita apenas um serviço específico")
    parser.add_argument("--check-conflicts", action="store_true", help="Mostra conflitos de versões consolidadas")
    args = parser.parse_args()

    results: Dict[str, Dict[str, object]] = {}
    for service_dir in sorted(SERVICES_DIR.iterdir()):
        if not service_dir.is_dir():
            continue
        service_name = service_dir.name
        if args.service and service_name != args.service:
            continue
        req_file = service_dir / "requirements.txt"
        if not req_file.exists():
            continue
        results[service_name] = scan_service(service_dir)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"services": results, "version_matrix": build_version_matrix(results)}
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    if args.check_conflicts:
        matrix = payload["version_matrix"]
        conflicts = {
            pkg: specs
            for pkg, specs in matrix.items()
            if len(set(specs.values())) > 1
        }
        if conflicts:
            print("Conflitos de versões encontrados:")
            for pkg, specs in conflicts.items():
                versions = ", ".join(f"{svc}: {val}" for svc, val in sorted(specs.items()))
                print(f"- {pkg}: {versions}")
        else:
            print("Nenhum conflito encontrado.")


if __name__ == "__main__":
    sys.exit(main())
