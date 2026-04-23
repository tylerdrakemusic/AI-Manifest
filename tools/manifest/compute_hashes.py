#!/usr/bin/env python3
import os
import hashlib
import json
import sys

def sha256_file(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for byte_block in iter(lambda: f.read(4096), b''):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest().lower()

current_files = {}

# Agents
agents_path = r'F:\.github\agents'
if os.path.exists(agents_path):
    for f in os.listdir(agents_path):
        if f.endswith('.agent.md'):
            full_path = os.path.join(agents_path, f)
            key = full_path.lower()
            current_files[key] = sha256_file(full_path)

# Instructions
instr_path = r'F:\.github\instructions'
if os.path.exists(instr_path):
    for f in os.listdir(instr_path):
        if f.endswith('.instructions.md'):
            full_path = os.path.join(instr_path, f)
            key = full_path.lower()
            current_files[key] = sha256_file(full_path)

# Skills
skills_path = r'F:\.github\skills'
if os.path.exists(skills_path):
    for root, dirs, files in os.walk(skills_path):
        for f in files:
            if f == 'SKILL.md':
                full_path = os.path.join(root, f)
                key = full_path.lower()
                current_files[key] = sha256_file(full_path)

# Load manifest
manifest_path = r'F:\.github\!!☾⛧security\agent-manifest.json'
with open(manifest_path, 'r', encoding='utf-8') as mf:
    manifest = json.load(mf)
    manifest_files = manifest.get('files', {})

# Normalize manifest paths to lowercase
manifest_normalized = {}
for path, hash_val in manifest_files.items():
    manifest_normalized[path.lower()] = hash_val

# Compare
new_files = []
missing_files = []
modified_files = []

# Find new and modified files
for curr_path, curr_hash in current_files.items():
    if curr_path not in manifest_normalized:
        new_files.append(curr_path)
    elif manifest_normalized[curr_path] != curr_hash:
        modified_files.append({
            'path': curr_path,
            'expected': manifest_normalized[curr_path],
            'actual': curr_hash
        })

# Find missing files
for manifest_path, manifest_hash in manifest_normalized.items():
    if manifest_path not in current_files:
        missing_files.append(manifest_path)

# Output results
print("=" * 80)
print("SECURITY GATE STEP 1: MANIFEST COMPARISON REPORT")
print("=" * 80)
print()

print(f"Total files in manifest: {len(manifest_normalized)}")
print(f"Total current files: {len(current_files)}")
print()

if new_files:
    print("NEW FILES (not in manifest):")
    for f in sorted(new_files):
        print(f"  + {f}")
    print()
else:
    print("NEW FILES: None")
    print()

if missing_files:
    print("MISSING FILES (in manifest but not found):")
    for f in sorted(missing_files):
        print(f"  - {f}")
    print()
else:
    print("MISSING FILES: None")
    print()

if modified_files:
    print("MODIFIED FILES (hash mismatch):")
    for item in sorted(modified_files, key=lambda x: x['path']):
        print(f"  ! {item['path']}")
        print(f"    Expected: {item['expected']}")
        print(f"    Actual:   {item['actual']}")
    print()
else:
    print("MODIFIED FILES: None")
    print()

print("=" * 80)

# Return counts
status = 0 if (not new_files and not missing_files and not modified_files) else 1
sys.exit(status)
