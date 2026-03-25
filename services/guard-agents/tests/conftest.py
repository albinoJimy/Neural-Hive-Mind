"""
Configuration file for pytest.

Fixes import path for the src module.
"""
import sys
from pathlib import Path

# Add the parent directory to sys.path so we can import src
# This allows tests to run with 'from src.xxx import yyy'
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
