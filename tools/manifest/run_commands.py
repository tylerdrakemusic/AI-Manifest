import subprocess
import sys
import os

os.chdir("F:\\")

# Command 1
print("="*80)
print("COMMAND 1: C:\\G\\python.exe F:\\.github\\!!☾⛧security\\update_manifest.py")
print("="*80)
result1 = subprocess.run(
    ["C:\\G\\python.exe", "F:\\.github\\!!☾⛧security\\update_manifest.py"],
    capture_output=True,
    text=True,
    cwd="F:\\"
)
print("STDOUT:")
print(result1.stdout)
print("\nSTDERR:")
print(result1.stderr)
print(f"\nEXIT CODE: {result1.returncode}")

# Command 2
print("\n" + "="*80)
print("COMMAND 2: C:\\G\\python.exe F:\\.github\\!!☾⛧security\\update_manifest.py --verify")
print("="*80)
result2 = subprocess.run(
    ["C:\\G\\python.exe", "F:\\.github\\!!☾⛧security\\update_manifest.py", "--verify"],
    capture_output=True,
    text=True,
    cwd="F:\\"
)
print("STDOUT:")
print(result2.stdout)
print("\nSTDERR:")
print(result2.stderr)
print(f"\nEXIT CODE: {result2.returncode}")
