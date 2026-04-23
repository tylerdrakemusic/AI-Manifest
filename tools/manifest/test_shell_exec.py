#!/usr/bin/env python3
"""
Test script to execute the update_manifest.py scripts and capture output.
"""
import subprocess
import sys
import os

os.chdir('F:\\')

# Test 1: Run without --verify
print("=" * 70)
print("EXECUTION TEST 1: update_manifest.py (without --verify)")
print("=" * 70)
result1 = subprocess.run(
    [r'C:\G\python.exe', r'F:\.github\!!☾⛧security\update_manifest.py'],
    capture_output=True,
    text=True,
    cwd=r'F:\\'
)
print("STDOUT:")
print(result1.stdout)
print("\nSTDERR:")
print(result1.stderr)
print(f"\nEXIT CODE: {result1.returncode}")

print("\n" + "=" * 70)
print("EXECUTION TEST 2: update_manifest.py --verify")
print("=" * 70)
result2 = subprocess.run(
    [r'C:\G\python.exe', r'F:\.github\!!☾⛧security\update_manifest.py', '--verify'],
    capture_output=True,
    text=True,
    cwd=r'F:\\'
)
print("STDOUT:")
print(result2.stdout)
print("\nSTDERR:")
print(result2.stderr)
print(f"\nEXIT CODE: {result2.returncode}")
