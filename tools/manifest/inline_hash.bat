@echo off
REM Create inline Python to compute hashes
(
echo import hashlib
echo from pathlib import Path
echo files = [
echo     r"F:\.github\agents\⊕workspace-hygiene.agent.md",
echo     r"F:\.github\instructions\agent-self-regen.instructions.md"
echo ]
echo for f in files:
echo     p = Path(f^)
echo     if p.exists(^):
echo         h = hashlib.sha256(p.read_bytes(^)^).hexdigest(^)
echo         print(f"{f}|{h}^"^)
) > F:\temp_hash_script.py

REM Run it
C:\G\python.exe F:\temp_hash_script.py > F:\hash_output.txt 2>&1
type F:\hash_output.txt
