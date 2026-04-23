import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Tuple

def sha256_file(filepath: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest().upper()

# Define watched directories
watched_dirs = [
    r'F:\.github\agents',
    r'F:\.github\instructions',
    r'F:\.github\skills'
]

# Collect all files from disk
disk_files: Dict[str, str] = {}
for watch_dir in watched_dirs:
    if os.path.exists(watch_dir):
        for root, dirs, files in os.walk(watch_dir):
            for file in files:
                full_path = os.path.join(root, file)
                file_hash = sha256_file(full_path)
                # Normalize path key (lowercase with backslashes)
                rel_path = full_path.lower()
                disk_files[rel_path] = file_hash

# Read manifest
manifest_path = r'F:\.github\!!☾⛧security\agent-manifest.json'
with open(manifest_path, 'r', encoding='utf-8') as f:
    manifest = json.load(f)

manifest_files = manifest.get('files', {})
# Normalize manifest keys to lowercase for comparison
manifest_normalized: Dict[str, str] = {k.lower(): v for k, v in manifest_files.items()}

# Find differences
new_files: Dict[str, str] = {}
missing_files: Dict[str, str] = {}
modified_files: Dict[str, Dict[str, str]] = {}

# Check for new files (in disk but not in manifest)
for disk_path, disk_hash in disk_files.items():
    if disk_path not in manifest_normalized:
        new_files[disk_path] = disk_hash

# Check for missing files (in manifest but not on disk)
for m_path, manifest_hash in manifest_normalized.items():
    if m_path not in disk_files:
        missing_files[m_path] = manifest_hash

# Check for modified files (different hashes)
for disk_path, disk_hash in disk_files.items():
    if disk_path in manifest_normalized:
        manifest_hash = manifest_normalized[disk_path]
        if disk_hash != manifest_hash.upper():
            modified_files[disk_path] = {
                'current': disk_hash,
                'manifest': manifest_hash.upper()
            }

# Define acceptable modified files (normalized to lowercase)
acceptable_modified = [
    r'f:\.github\agents\∞life-orchestrator.agent.md'.lower(),
    r'f:\.github\agents\❤music-orchestrator.agent.md'.lower(),
    r'f:\.github\agents\⟨ψ⟩quantum-orchestrator.agent.md'.lower(),
    r'f:\.github\agents\👁ai-manifest-orchestrator.agent.md'.lower(),
    r'f:\.github\agents\⊕workspace-overseer.agent.md'.lower(),
    r'f:\.github\agents\⊕workspace-ci.agent.md'.lower()
]

# Report findings
print("=" * 80)
print("SECURITY MANIFEST VERIFICATION REPORT")
print("=" * 80)
print()

print(f"Total files on disk: {len(disk_files)}")
print(f"Total files in manifest: {len(manifest_normalized)}")
print()

print("NEW FILES (on disk, not in manifest):")
if new_files:
    for path in sorted(new_files.keys()):
        hash_val = new_files[path]
        print(f"  ✗ {path}")
        print(f"    SHA-256: {hash_val}")
else:
    print("  None")
print()

print("MISSING FILES (in manifest, not on disk):")
if missing_files:
    for path in sorted(missing_files.keys()):
        print(f"  ✗ {path}")
else:
    print("  None")
print()

print("MODIFIED FILES (hash mismatch):")
if modified_files:
    for path in sorted(modified_files.keys()):
        is_acceptable = path in acceptable_modified
        status = "✓ ACCEPTABLE" if is_acceptable else "✗ UNEXPECTED"
        print(f"  {status}: {path}")
        print(f"    Current:  {modified_files[path]['current']}")
        print(f"    Manifest: {modified_files[path]['manifest']}")
else:
    print("  None")
print()

# Verification result
verification_passed = (
    len(new_files) == 0 and
    len(missing_files) == 0 and
    all(path in acceptable_modified for path in modified_files.keys())
)

print("=" * 80)
print(f"VERIFICATION RESULT: {'PASSED ✓' if verification_passed else 'FAILED ✗'}")
print("=" * 80)
print()

if verification_passed:
    print("Status: Safe to update manifest")
    print("- No NEW files detected")
    print("- No MISSING files detected")
    print(f"- {len(modified_files)} modified files are all acceptable")
else:
    print("Status: CANNOT update manifest - issues detected:")
    if new_files:
        print(f"  - {len(new_files)} NEW files found")
    if missing_files:
        print(f"  - {len(missing_files)} MISSING files found")
    if modified_files:
        unexpected = [p for p in modified_files.keys() if p not in acceptable_modified]
        if unexpected:
            print(f"  - {len(unexpected)} UNEXPECTED modified files found")

# Save analysis for next step
analysis = {
    'verification_passed': verification_passed,
    'new_files': new_files,
    'missing_files': missing_files,
    'modified_files': {k: v for k, v in modified_files.items()},
    'acceptable_modified': acceptable_modified,
    'disk_files': disk_files,
    'manifest_files': manifest_normalized
}

with open(r'F:\temp_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(analysis, f, indent=2)

exit(0 if verification_passed else 1)
