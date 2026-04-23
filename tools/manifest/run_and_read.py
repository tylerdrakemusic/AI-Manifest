import subprocess
import json
from pathlib import Path

# Run the temporary script
print("Executing manifest operations...")
result = subprocess.run([r"C:\G\python.exe", r"F:\temp_run_manifest.py"], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

# Read the manifest
print("\n=== READING AGENT MANIFEST ===")
manifest_path = Path(r"F:\.github\!!☾⛧security\agent-manifest.json")
if manifest_path.exists():
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    print(f"Total files: {manifest['file_count']}")
    print(f"Generated at: {manifest['generated_at']}")
    
    # Find the agent-self-regen.instructions.md file
    target_file = r"f:\\.github\instructions\agent-self-regen.instructions.md"
    for file_path, file_hash in manifest['files'].items():
        if 'agent-self-regen.instructions.md' in file_path:
            print(f"\nFound file: {file_path}")
            print(f"Hash: {file_hash}")
            print(f"Hash length: {len(file_hash)} characters")
            print(f"Is valid 64-hex: {len(file_hash) == 64 and all(c in '0123456789abcdef' for c in file_hash.lower())}")
else:
    print("Manifest file not found!")
