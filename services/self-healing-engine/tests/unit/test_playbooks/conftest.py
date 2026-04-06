"""
Conftest local para testes de playbooks.
Herda configurações do conftest principal.
"""

import sys
from pathlib import Path

# Adicionar diretório src ao path Python
_current_dir = Path(__file__).resolve()
_project_root = _current_dir.parents[3]  # Vai para services/self-healing-engine
_src_path = _project_root / "src"

if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))
