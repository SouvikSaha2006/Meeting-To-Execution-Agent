"""
Meeting-to-Execution Agent Backend Package
"""
import os
import sys
from dotenv import load_dotenv

_backend_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_backend_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

for _candidate in [
    os.path.join(_root_dir, ".env"),
    os.path.join(_backend_dir, ".env"),
    ".env",
]:
    if os.path.exists(_candidate):
        load_dotenv(_candidate)
        break
