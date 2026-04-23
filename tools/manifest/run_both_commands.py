#!/usr/bin/env python3
import subprocess
import sys

print("=" * 70)
print("COMMAND 1: C:\\G\\python.exe F:\\.github\\!!☾⛧security\\update_manifest.py")
print("=" * 70)

result1 = subprocess.run(
    [r"C:\G\python.exe", r"F:\.github\!!☾⛧security\update_manifest.py"],
    capture_output=True,
    text=True
)

print("STDOUT:")
print(result1.stdout)
if result1.stderr:
    print("STDERR:")
    print(result1.stderr)
print(f"Exit Code: {result1.returncode}")

print("\n" + "=" * 70)
print("COMMAND 2: C:\\G\\python.exe F:\\.github\\!!☾⛧security\\update_manifest.py --verify")
print("=" * 70)

result2 = subprocess.run(
    [r"C:\G\python.exe", r"F:\.github\!!☾⛧security\update_manifest.py", "--verify"],
    capture_output=True,
    text=True
)

print("STDOUT:")
print(result2.stdout)
if result2.stderr:
    print("STDERR:")
    print(result2.stderr)
print(f"Exit Code: {result2.returncode}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Command 1 Exit Status: {result1.returncode}")
print(f"Command 2 Exit Status: {result2.returncode}")
