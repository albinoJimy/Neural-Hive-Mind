#!/usr/bin/env python3
"""
Script auxiliar para corrigir linhas longas em Python.
Focado em casos comuns que podem ser corrigidos automaticamente.
"""

import re
import sys
from pathlib import Path


def fix_long_urls(content: str) -> str:
    """Divide URLs longas em múltiplas linhas."""
    # URLs em f-strings
    pattern = r'f"([^"]{100,})"'

    def replace_url(match):
        url = match.group(1)
        if "?" in url:
            base, query = url.split("?", 1)
            # Dividir parâmetros
            params = query.split("&")
            if len(params) > 2:
                result = f'f"{base}?"\\\n'
                params_lines = []
                for i, param in enumerate(params):
                    if i == 0:
                        params_lines.append(f'    f"{param}"')
                    else:
                        params_lines.append(f'    f"&{param}"')
                result += '" + \n'.join(params_lines)
                return result
        return match.group(0)

    return re.sub(pattern, replace_url, content)


def fix_long_string_concat(content: str) -> str:
    """Divide concatenações de strings longas."""
    # Strings concatenadas com +
    pattern = r'("[^"]{80,}")\s*\+\s*("[^"]+")'

    def replace_concat(match):
        # Não modificar - pode mudar comportamento
        return match.group(0)

    return re.sub(pattern, replace_concat, content)


def fix_long_dict_definitions(content: str) -> str:
    """Divide definições de dicionários longos."""
    # Dicts longos em uma linha — não implementar, muito arriscado
    return content


def process_file(filepath: Path) -> int:
    """Processa um arquivo Python."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return 0

    original = content
    content = fix_long_urls(content)

    changes = len(content) - len(original)
    if changes != 0:
        filepath.write_text(content, encoding="utf-8")
        return 1
    return 0


def main():
    if len(sys.argv) < 2:
        print("Uso: python fix-long-lines.py <arquivo_ou_diretorio>")
        sys.exit(1)

    path = Path(sys.argv[1])
    files_changed = 0

    if path.is_file():
        files_changed = process_file(path)
    elif path.is_dir():
        for py_file in path.rglob("*.py"):
            files_changed += process_file(py_file)

    print(f"Arquivos modificados: {files_changed}")


if __name__ == "__main__":
    main()
