import subprocess
import sys

result = subprocess.run([r"C:\G\python.exe", r"F:\regen_manifest_temp.py"], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr, file=sys.stderr)
sys.exit(result.returncode)
