#!/usr/bin/env bash
#
# Auditoria completa de dependências para todos os serviços.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/reports"
DEPENDENCY_DIR="${REPORT_DIR}/dependencies"
SERVICE_FILTER=""
OUTPUT_FORMAT="json"
CHECK_SECURITY=false

usage() {
  cat <<'EOF'
Uso: scripts/audit-dependencies.sh [opções]
  --service <nome>       Audita somente um serviço específico (ex.: gateway-intencoes)
  --check-security       Executa pip-audit e safety para cada serviço
  --output-format <fmt>  Formato do relatório agregado (json ou markdown). Default: json
  -h, --help             Mostra esta ajuda
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      SERVICE_FILTER="$2"
      shift 2
      ;;
    --check-security)
      CHECK_SECURITY=true
      shift
      ;;
    --output-format)
      OUTPUT_FORMAT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Opção desconhecida: $1" >&2
      usage
      exit 1
      ;;
  esac
done

mkdir -p "${REPORT_DIR}" "${DEPENDENCY_DIR}"

# Arquivos temporários para agregação.
SERVICE_DATA_FILE="$(mktemp)"
VERSION_MATRIX_FILE="$(mktemp)"
SECURITY_FILE="$(mktemp)"
trap 'rm -f "$SERVICE_DATA_FILE" "$VERSION_MATRIX_FILE" "$SECURITY_FILE"' EXIT
: >"$SERVICE_DATA_FILE"
: >"$VERSION_MATRIX_FILE"
: >"$SECURITY_FILE"

log() {
  echo "[audit-dependencies] $*" >&2
}

ensure_tools() {
  log "Instalando ferramentas base (pipdeptree, pip-audit, safety)..."
  python3 -m pip install --upgrade pip >/dev/null
  python3 -m pip install --upgrade pipdeptree pip-audit safety >/dev/null
}

normalize_name() {
  python3 - "$1" <<'PY'
import re, sys
name = sys.argv[1].lower()
name = name.replace('_', '-')
print(re.sub(r'[^a-z0-9\-\.\[\]]', '', name))
PY
}

audit_service() {
  local service_path="$1"
  local service_name
  service_name="$(basename "$service_path")"
  local requirements_file="${service_path}/requirements.txt"

  if [[ ! -f "$requirements_file" ]]; then
    log "Ignorando ${service_name} (sem requirements.txt)"
    return
  fi

  if [[ -n "$SERVICE_FILTER" && "$service_name" != "$SERVICE_FILTER" ]]; then
    return
  fi

  log "Auditando ${service_name}..."

  local venv_dir
  venv_dir="$(mktemp -d)"
  python3 -m venv "$venv_dir"
  # shellcheck disable=SC1090
  source "${venv_dir}/bin/activate"
  pip install --upgrade pip >/dev/null
  pip install -r "$requirements_file" >/dev/null
  pip install pipdeptree >/dev/null

  local tree_output="${DEPENDENCY_DIR}/${service_name}-tree.txt"
  pipdeptree >"$tree_output" || true

  if $CHECK_SECURITY; then
    pip install pip-audit safety >/dev/null
    pip-audit -f json >"${tree_output}.pip-audit.json" || true
    safety check --json >"${tree_output}.safety.json" || true
    printf '%s|%s|%s|%s\n' "$service_name" "pip-audit" "${tree_output}.pip-audit.json" "" >>"$SECURITY_FILE"
    printf '%s|%s|%s|%s\n' "$service_name" "safety" "${tree_output}.safety.json" "" >>"$SECURITY_FILE"
  fi

  deactivate
  rm -rf "$venv_dir"

  local svc_data_tmp version_tmp
  svc_data_tmp="$(mktemp)"
  version_tmp="$(mktemp)"

  python3 - "$service_name" "$service_path" "$requirements_file" "$svc_data_tmp" "$version_tmp" <<'PY'
import ast, json, re, sys
from pathlib import Path

SERVICE = sys.argv[1]
SERVICE_PATH = Path(sys.argv[2])
REQ_FILE = Path(sys.argv[3])
SERVICE_DATA_FILE = Path(sys.argv[4])
VERSION_DATA_FILE = Path(sys.argv[5])

SPECIAL_IMPORTS = {
    "python-jose": "jose",
    "python-multipart": "multipart",
    "python-dotenv": "dotenv",
    "avro-python3": "avro",
    "scikit-learn": "sklearn",
    "openai-whisper": "whisper",
}

def normalize(name: str) -> str:
    return name.lower().replace("_", "-")

def req_name(raw: str) -> str:
    raw = raw.split("[", 1)[0]
    return normalize(raw)

dependencies = []
version_map = {}
for line in REQ_FILE.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("-r ") or line.startswith("--"):
        continue
    if line.startswith("-e "):
        pkg = line
        spec = "editable"
    else:
        match = re.match(r'([A-Za-z0-9_\-\.]+)(.*)', line)
        if not match:
            continue
        pkg = match.group(1)
        spec = match.group(2).strip() or ""
    pkg_norm = req_name(pkg)
    dependencies.append({"package": pkg, "normalized": pkg_norm, "spec": spec})
    version_map[pkg_norm] = spec or "unspecified"

imported = {}
for py_file in SERVICE_PATH.rglob("*.py"):
    try:
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.setdefault(alias.name.split(".")[0], set()).add(str(py_file.relative_to(SERVICE_PATH)))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.setdefault(node.module.split(".")[0], set()).add(str(py_file.relative_to(SERVICE_PATH)))

def map_import(name: str) -> str:
    name = normalize(name)
    for req, imp in SPECIAL_IMPORTS.items():
        if normalize(imp) == name:
            return req
        if req == name:
            return req
    return name

used = []
unused = []
missing = []
req_lookup = {d["normalized"]: d for d in dependencies}

for pkg_norm, spec in version_map.items():
    req_entry = req_lookup[pkg_norm]
    if pkg_norm in {map_import(k) for k in imported.keys()}:
        files = sorted(set().union(*[imported[k] for k in imported if map_import(k) == pkg_norm]))
        used.append({"package": req_entry["package"], "spec": spec, "files": files})
    else:
        unused.append({"package": req_entry["package"], "spec": spec, "reason": "Nenhum import encontrado"})

for imp, files in imported.items():
    mapped = map_import(imp)
    if mapped not in req_lookup and imp not in ("os", "sys", "pathlib", "json", "typing", "logging", "asyncio"):
        missing.append({"import": imp, "files": sorted(files), "reason": "Não listado em requirements"})

SERVICE_DATA_FILE.write_text(json.dumps({
    "service": SERVICE,
    "dependencies": dependencies,
    "used": used,
    "unused": unused,
    "missing": missing,
}, ensure_ascii=False))

with VERSION_DATA_FILE.open("w") as fh:
    for pkg_norm, spec in sorted(version_map.items()):
        fh.write(f"{pkg_norm}|{spec}|{SERVICE}\n")
PY

  cat "$svc_data_tmp" >>"$SERVICE_DATA_FILE"
  printf '\n' >>"$SERVICE_DATA_FILE"
  cat "$version_tmp" >>"$VERSION_MATRIX_FILE"
  rm -f "$svc_data_tmp" "$version_tmp"
}

ensure_tools

for service_dir in "${ROOT_DIR}"/services/*/; do
  audit_service "$service_dir"
done

python3 - "$SERVICE_DATA_FILE" "$VERSION_MATRIX_FILE" "$SECURITY_FILE" "$REPORT_DIR" "$OUTPUT_FORMAT" <<'PY'
import json, sys
from collections import defaultdict
from pathlib import Path

SERVICE_DATA_FILE = Path(sys.argv[1])
VERSION_MATRIX_FILE = Path(sys.argv[2])
SECURITY_FILE = Path(sys.argv[3])
REPORT_DIR = Path(sys.argv[4])
OUTPUT_FORMAT = sys.argv[5].lower()

services = {}
for line in SERVICE_DATA_FILE.read_text().splitlines():
    if not line.strip():
        continue
    data = json.loads(line)
    services[data["service"]] = data

version_matrix = defaultdict(dict)
for row in VERSION_MATRIX_FILE.read_text().splitlines():
    if not row.strip():
        continue
    pkg, spec, service = row.split("|", 2)
    version_matrix[pkg][service] = spec

security_entries = []
for row in SECURITY_FILE.read_text().splitlines():
    if not row.strip():
        continue
    service, tool, path, extra = row.split("|", 3)
    security_entries.append({
        "service": service,
        "tool": tool,
        "report": path,
        "details": extra or ""
    })

report = {
    "services": services,
    "version_matrix": version_matrix,
    "security_issues": security_entries,
}

json_output = REPORT_DIR / "dependency-audit-report.json"
json_output.write_text(json.dumps(report, indent=2, ensure_ascii=False))

if OUTPUT_FORMAT == "markdown":
    md_lines = ["# Dependency Audit Report", ""]
    for service_name in sorted(services.keys()):
        svc = services[service_name]
        md_lines.append(f"## {service_name}")
        md_lines.append("")
        md_lines.append("### Dependências Não Utilizadas")
        if svc["unused"]:
            for dep in svc["unused"]:
                md_lines.append(f"- `{dep['package']}` ({dep['spec']}) - {dep['reason']}")
        else:
            md_lines.append("- Nenhuma.")
        md_lines.append("")
        md_lines.append("### Imports Não Declarados")
        if svc["missing"]:
            for miss in svc["missing"]:
                files = ", ".join(miss["files"])
                md_lines.append(f"- `{miss['import']}` ({files})")
        else:
            md_lines.append("- Nenhum.")
        md_lines.append("")
    md_lines.append("## Matriz de Versões")
    for pkg, services_map in sorted(version_matrix.items()):
        specs = ", ".join(f"{svc}: {spec}" for svc, spec in sorted(services_map.items()))
        md_lines.append(f"- **{pkg}** → {specs}")
    (REPORT_DIR / "dependency-audit-report.md").write_text("\n".join(md_lines))
PY

log "Relatórios disponíveis em ${REPORT_DIR}"
