"""Root conftest — adds the backend directory to sys.path so that
``import app.*`` works from any test file without installing the package.
"""
import sys
from pathlib import Path

# Insert backend/ at the front of sys.path
sys.path.insert(0, str(Path(__file__).parent))
