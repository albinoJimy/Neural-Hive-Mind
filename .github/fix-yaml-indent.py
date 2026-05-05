#!/usr/bin/env python3
"""Fix YAML indentation in GitHub workflows - simple version."""

from pathlib import Path

WORKFLOWS_DIR = Path(__file__).parent / "workflows"


def fix_runs_on_indent(content: str) -> str:
    """Fix runs-on over-indented from 8 to 4 spaces."""
    lines = content.split('\n')
    fixed = []

    for i, line in enumerate(lines):
        # Check if this line has over-indented runs-on
        # Pattern: 8 spaces followed by 'runs-on:'
        if line.startswith('        runs-on:'):
            # Check if previous line is job name or name at 4 spaces
            if i > 0 and lines[i-1].startswith('    '):
                # Reduce indentation from 8 to 4 spaces
                fixed.append('    runs-on:' + line[14:])
            else:
                fixed.append(line)
        else:
            fixed.append(line)

    return '\n'.join(fixed)


def main():
    """Fix all workflow files."""
    fixed_count = 0
    for file in WORKFLOWS_DIR.glob("*.yml"):
        if file.name.endswith((".disabled", "_example", "_runner-select")):
            continue

        content = file.read_text()

        # Check if file has the problem
        if '        runs-on:' in content:
            new_content = fix_runs_on_indent(content)
            if new_content != content:
                file.write_text(new_content)
                print(f"Fixed {file.name}")
                fixed_count += 1

    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
