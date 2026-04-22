#!/usr/bin/env python3
"""Wrapper script para executar testes com PYTHONPATH correto."""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Run pytest
import pytest

sys.exit(pytest.main(sys.argv[1:]))
