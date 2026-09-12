#!/usr/bin/env python3
"""Minimal verification that local imports work without cross-repo dependencies."""

from __future__ import annotations

import sys
from pathlib import Path

# Add current directory to path for import resolution
sys.path.insert(0, str(Path.cwd()))

# Test the imports that the test files use
try:
    from src.utils.diagram_budgets import DiagramCategory
    print("✓ DiagramCategory imported successfully from local src.utils")
    print(f"  - DiagramCategory.OVERVIEW = {DiagramCategory.OVERVIEW}")
    print(f"  - DiagramCategory.DETAIL = {DiagramCategory.DETAIL}")
    print(f"  - DiagramCategory.DATABASE_SCHEMA = {DiagramCategory.DATABASE_SCHEMA}")
    print(f"  - DiagramCategory.TECHNOLOGY_STACK = {DiagramCategory.TECHNOLOGY_STACK}")
    print("\n✓ All local imports working correctly")
    sys.exit(0)
except Exception as e:
    print(f"✗ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
