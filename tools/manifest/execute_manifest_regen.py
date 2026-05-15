#!/usr/bin/env python3
"""Execute the manifest regeneration and capture output"""
import sys
import io
from pathlib import Path

# Add the script directory to path
sys.path.insert(0, r"F:")

# Capture output
old_stdout = sys.stdout
sys.stdout = output_buffer = io.StringIO()

try:
    # Import and run the regeneration script
    exec(Path(r"F:\final_regen_manifest.py").read_text(encoding="utf-8"))  # nosec B102 — Bootstrap exec of fixed internal script path; no user-controlled input
    
    # Get the output
    output = output_buffer.getvalue()
    
finally:
    # Restore stdout
    sys.stdout = old_stdout
    
# Print the captured output
print(output)

# Verify the manifest was written
manifest_path = Path(r"f:\.github\!!☾⛧security\agent-manifest.json")
if manifest_path.exists():
    import json
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print(f"\n✅ VERIFICATION: Manifest file exists with {manifest['file_count']} entries")
else:
    print(f"\n❌ ERROR: Manifest file was not written!")
    sys.exit(1)
