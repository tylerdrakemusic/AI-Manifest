#!/usr/bin/env python3
"""Temporary script to run update_manifest.py"""
import subprocess
import sys

print("=== RUNNING MANIFEST UPDATE ===")
print("Command: C:\\G\\python.exe F:\\.github\\!!☾⛧security\\update_manifest.py")
print()

result = subprocess.run([
    r"C:\G\python.exe",
    r"F:\.github\!!☾⛧security\update_manifest.py"
], capture_output=True, text=True)

print("STDOUT:")
print(result.stdout)
if result.stderr:
    print("STDERR:")
    print(result.stderr)
print(f"Return code: {result.returncode}")
print()

print("=== RUNNING MANIFEST VERIFY ===")
print("Command: C:\\G\\python.exe F:\\.github\\!!☾⛧security\\update_manifest.py --verify")
print()

result2 = subprocess.run([
    r"C:\G\python.exe",
    r"F:\.github\!!☾⛧security\update_manifest.py",
    "--verify"
], capture_output=True, text=True)

print("STDOUT:")
print(result2.stdout)
if result2.stderr:
    print("STDERR:")
    print(result2.stderr)
print(f"Return code: {result2.returncode}")
