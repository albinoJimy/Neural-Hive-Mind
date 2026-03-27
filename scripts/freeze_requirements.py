#!/usr/bin/env python3
"""
Script para fazer pinning de dependências Python.
Converte ranges (>=, ~=, >) para versões exatas (==).

Uso:
    python scripts/freeze_requirements.py [--check|--apply]

    --check: Apenas verifica se há ranges nos requirements
    --apply: Aplica o pinning, criando requirements.frozen
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def find_requirements_files(services_dir: str = "services") -> List[Path]:
    """Encontra todos os arquivos requirements*.txt."""
    services_path = Path(services_dir)
    files = []

    for req_file in services_path.rglob("requirements*.txt"):
        # Skip dev, test, e frozen files
        if any(x in req_file.name for x in ["dev", "test", "frozen"]):
            continue
        # Skip mlruns (artefatos de ML)
        if "mlruns" in str(req_file):
            continue
        files.append(req_file)

    return sorted(files)


def extract_packages_with_ranges(content: str) -> List[Tuple[str, str]]:
    """Extrai packages que têm ranges (>=, ~=, >, <)."""
    packages = []
    lines = content.split("\n")

    for line in lines:
        line = line.strip()
        # Skip comments e empty lines
        if not line or line.startswith("#"):
            continue

        # Check for ranges
        for operator in [">=", "~=", ">", "<"]:
            if operator in line:
                # Extract package name
                pkg_name = line.split(operator)[0].strip()
                packages.append((pkg_name, line))
                break

    return packages


def get_installed_version(package: str) -> str:
    """Obtém a versão instalada de um package usando pip show."""
    try:
        result = subprocess.run(
            ["pip", "show", package],
            capture_output=True,
            text=True,
            check=True
        )
        for line in result.stdout.split("\n"):
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
    except subprocess.CalledProcessError:
        pass
    return None


def freeze_ranges(content: str, versions_map: Dict[str, str]) -> str:
    """Substitui ranges por versões exatas."""
    lines = content.split("\n")
    result = []

    for line in lines:
        original = line
        stripped = line.strip()

        # Skip comments e empty lines
        if not stripped or stripped.startswith("#"):
            result.append(line)
            continue

        # Check for ranges
        modified = False
        for operator in [">=", "~=", ">", "<"]:
            if operator in stripped and not stripped.startswith("#"):
                pkg_name = stripped.split(operator)[0].strip()

                # Check for inline comment
                comment = ""
                if " #" in stripped:
                    parts = stripped.split(" #", 1)
                    pkg_base = parts[0]
                    comment = f" # {parts[1]}"
                else:
                    pkg_base = stripped
                    comment = ""

                pkg_name_only = pkg_name.split(operator)[0].strip()

                if pkg_name_only in versions_map:
                    version = versions_map[pkg_name_only]
                    # Preserve indentation
                    indent = len(line) - len(line.lstrip())
                    new_line = " " * indent + f"{pkg_name_only}=={version}{comment}"
                    result.append(new_line)
                    modified = True
                    break

        if not modified:
            result.append(line)

    return "\n".join(result)


def check_ranges(files: List[Path]) -> int:
    """Apenas verifica se há ranges nos requirements."""
    total_ranges = 0

    for req_file in files:
        try:
            content = req_file.read_text()
            packages = extract_packages_with_ranges(content)
            if packages:
                print(f"{req_file}: {len(packages)} packages with ranges")
                for pkg, line in packages:
                    print(f"  - {line}")
                total_ranges += len(packages)
        except Exception as e:
            print(f"Error reading {req_file}: {e}")

    if total_ranges == 0:
        print("✓ No ranges found in requirements files!")
        return 0
    else:
        print(f"\nTotal: {total_ranges} packages with ranges")
        return 1


def apply_pinning(files: List[Path], dry_run: bool = False) -> None:
    """Aplica o pinning criando arquivos .frozen."""
    # Collect all packages to install
    all_packages = set()

    for req_file in files:
        try:
            content = req_file.read_text()
            packages = extract_packages_with_ranges(content)
            for pkg_name, _ in packages:
                # Remove version specs for installation
                all_packages.add(pkg_name.split(">=")[0].split("~=")[0].split(">")[0].split("<")[0].strip())
        except Exception as e:
            print(f"Error reading {req_file}: {e}")

    if not all_packages:
        print("No packages with ranges found!")
        return

    print(f"Installing {len(all_packages)} packages to resolve versions...")
    print(f"Packages: {', '.join(sorted(all_packages)[:10])}{'...' if len(all_packages) > 10 else ''}")

    # Install packages to get versions
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade"] + list(all_packages),
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error installing packages: {e}")
        return

    # Get installed versions
    versions_map = {}
    for pkg in sorted(all_packages):
        version = get_installed_version(pkg)
        if version:
            versions_map[pkg] = version
            print(f"  {pkg} -> {version}")

    # Create .frozen files
    for req_file in files:
        try:
            content = req_file.read_text()
            packages = extract_packages_with_ranges(content)

            if not packages:
                continue

            frozen_content = freeze_ranges(content, versions_map)
            frozen_file = req_file.with_suffix(".txt.frozen")

            if dry_run:
                print(f"\nWould create: {frozen_file}")
                print(f"Original packages with ranges: {len(packages)}")
            else:
                frozen_file.write_text(frozen_content)
                print(f"Created: {frozen_file}")
        except Exception as e:
            print(f"Error processing {req_file}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Freeze Python requirements")
    parser.add_argument("--check", action="store_true", help="Check for ranges only")
    parser.add_argument("--apply", action="store_true", help="Apply pinning")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--services-dir", default="services", help="Services directory")

    args = parser.parse_args()

    if not args.check and not args.apply:
        parser.print_help()
        return 1

    files = find_requirements_files(args.services_dir)
    print(f"Found {len(files)} requirements files\n")

    if args.check:
        return check_ranges(files)

    if args.apply:
        apply_pinning(files, args.dry_run)
        return 0


if __name__ == "__main__":
    sys.exit(main())
