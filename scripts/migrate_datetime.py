#!/usr/bin/env python3
"""
Script para migrar datetime.utcnow() para datetime.now(timezone.utc).

Uso: python scripts/migrate_datetime.py [--dry-run] [caminho...]

Exemplo: python scripts/migrate_datetime.py services/approval-service
"""

import argparse
import re
import sys
from pathlib import Path


def check_imports(content: str) -> tuple[bool, bool]:
    """Verifica se datetime e timezone já estão importados."""
    has_datetime = bool(re.search(r"from datetime import .*datetime", content))
    has_timezone = bool(re.search(r"from datetime import .*timezone", content))
    return has_datetime, has_timezone


def add_timezone_import(content: str) -> tuple[str, bool]:
    """Adiciona timezone aos imports de datetime."""
    # Padrões de import de datetime
    patterns = [
        (r"from datetime import datetime", "from datetime import datetime, timezone"),
        (
            r"from datetime import (\w+(?:, \w+)*)",
            lambda m: f"from datetime import {m.group(1)}, timezone"
            if "timezone" not in m.group(1)
            else None,
        ),
        (r"import datetime", None),  # Não modifica import datetime.*
    ]

    for pattern, replacement in patterns:
        if replacement is None:
            continue
        if callable(replacement):
            match = re.search(pattern, content)
            if match:
                new_import = replacement(match)
                if new_import:
                    content = re.sub(pattern, new_import, content, count=1)
                    return content, True
        else:
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content, count=1)
                return content, True

    # Se não encontrou padrão conhecido, tenta adicionar import
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "from datetime import" in line and "timezone" not in line:
            lines[i] = line.rstrip() + ", timezone"
            return "\n".join(lines), True

    return content, False


def migrate_utcnow(content: str) -> tuple[str, int]:
    """Substitui datetime.utcnow() por datetime.now(timezone.utc)."""
    # Padrão para datetime.utcnow()
    pattern = r"datetime\.utcnow\(\)"

    matches = list(re.finditer(pattern, content))
    count = len(matches)

    # Substitui de trás para frente para manter as posições corretas
    for match in reversed(matches):
        start, end = match.span()
        content = content[:start] + "datetime.now(timezone.utc)" + content[end:]

    return content, count


def migrate_utc_constant(content: str) -> tuple[str, int]:
    """Substitui datetime.UTC por timezone.utc (Python 3.11+ -> 3.10)."""
    pattern = r"datetime\.UTC"
    matches = list(re.finditer(pattern, content))
    count = len(matches)

    for match in reversed(matches):
        start, end = match.span()
        content = content[:start] + "timezone.utc" + content[end:]

    return content, count


def migrate_file(filepath: Path, dry_run: bool = False) -> dict:
    """Migra um único arquivo."""
    result = {
        "file": str(filepath),
        "utcnow_count": 0,
        "utc_count": 0,
        "added_import": False,
        "modified": False,
    }

    try:
        content = filepath.read_text(encoding="utf-8")

        # Verifica se precisa migrar
        if "datetime.utcnow()" not in content and "datetime.UTC" not in content:
            return result

        original_content = content

        # Migra datetime.UTC primeiro
        content, utc_count = migrate_utc_constant(content)
        result["utc_count"] = utc_count

        # Migra datetime.utcnow()
        content, utcnow_count = migrate_utcnow(content)
        result["utcnow_count"] = utcnow_count

        # Adiciona import timezone se necessário
        if utcnow_count > 0:
            has_dt, has_tz = check_imports(content)
            if has_dt and not has_tz:
                content, added = add_timezone_import(content)
                result["added_import"] = added

        result["modified"] = content != original_content

        if result["modified"] and not dry_run:
            filepath.write_text(content, encoding="utf-8")

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Migra datetime.utcnow() para datetime.now(timezone.utc)"
    )
    parser.add_argument("paths", nargs="+", help="Caminhos para migrar")
    parser.add_argument(
        "--dry-run", action="store_true", help="Mostra mudanças sem modificar arquivos"
    )
    args = parser.parse_args()

    paths = [Path(p) for p in args.paths]

    # Encontra todos os arquivos Python
    py_files = []
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            py_files.append(path)
        elif path.is_dir():
            py_files.extend(path.rglob("*.py"))

    print(f"🔍 Verificando {len(py_files)} arquivos Python...")

    results = []
    total_utcnow = 0
    total_utc = 0
    total_modified = 0

    for filepath in py_files:
        result = migrate_file(filepath, dry_run=args.dry_run)
        if result.get("utcnow_count", 0) > 0 or result.get("utc_count", 0) > 0:
            results.append(result)
            total_utcnow += result.get("utcnow_count", 0)
            total_utc += result.get("utc_count", 0)
            if result.get("modified", False):
                total_modified += 1

    # Relatório
    print("\n📊 Resumo:")
    print(f"   datetime.utcnow() encontrado: {total_utcnow}")
    print(f"   datetime.UTC encontrado: {total_utc}")
    print(f"   Arquivos modificados: {total_modified}")

    if args.dry_run and total_modified > 0:
        print("\n⚠️  Modo DRY-RUN: Nenhum arquivo foi modificado.")
        print("   Execute sem --dry-run para aplicar as mudanças.")

    if results:
        print("\n📝 Arquivos com mudanças:")
        for r in results:
            status = "✓" if r.get("modified", False) else "→"
            print(f"   {status} {r['file']}")
            if r.get("utcnow_count", 0) > 0:
                print(
                    f"      datetime.utcnow() → datetime.now(timezone.utc) ({r['utcnow_count']}x)"
                )
            if r.get("utc_count", 0) > 0:
                print(f"      datetime.UTC → timezone.utc ({r['utc_count']}x)")
            if r.get("added_import", False):
                print("      + import timezone")

    return 0


if __name__ == "__main__":
    sys.exit(main())
