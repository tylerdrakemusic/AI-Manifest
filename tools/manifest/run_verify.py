#!/usr/bin/env python3
"""Wrapper to run verify_manifest and print output."""

import subprocess
import sys

result = subprocess.run([sys.executable, r'F:\verify_manifest.py'], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
sys.exit(result.returncode)
