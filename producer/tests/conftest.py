"""Test setup for producer/.

producer/ is a flat script directory (no __init__.py, sibling modules
import each other directly, e.g. `from state import RedisState`) rather
than an installable package, matching how it's actually run in
production (`python main.py` from inside producer/). This puts the
directory on sys.path so tests can import those modules the same way,
without restructuring the package the Docker image already relies on.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
