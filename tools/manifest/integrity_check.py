#!/usr/bin/env python
import json
import hashlib
import os
import sys

# Read manifest
manifest_path = r'F:\.github\!!☾⛧security\agent-manifest.json'
with open(manifest_path, 'r', encoding='utf-8') as f:
    manifest = json.load(f)

# Extract expected files from manifest
expected_files = {}
if 'files' in manifest:
    for file_info in manifest['files']:
        expected_files[file_info['path']] = file_info.get('sha256', '')

# Function to compute SHA-256
def compute_sha256(filepath):
    sha256 = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        return f'ERROR: {str(e)}'

# Scan current files
base_paths = [
    r'F:\.github\agents',
    r'F:\.github\instructions',
    r'F:\.github\skills'
]

current_files = {}
for base in base_paths:
    if os.path.exists(base):
        for root, dirs, files in os.walk(base):
            for file in files:
                filepath = os.path.join(root, file)
                # Store relative path from F:\.github
                rel_path = os.path.relpath(filepath, r'F:\.github')
                sha256 = compute_sha256(filepath)
                current_files[rel_path] = sha256

# Compare
new_paths = []
missing_paths = []
modified_paths = []

# Check for new or modified files
for rel_path, current_hash in current_files.items():
    if rel_path not in expected_files:
        new_paths.append(rel_path)
    elif expected_files[rel_path] and expected_files[rel_path] != current_hash:
        modified_paths.append({
            'path': rel_path,
            'expected_hash': expected_files[rel_path],
            'actual_hash': current_hash
        })

# Check for missing files
for rel_path in expected_files:
    if rel_path not in current_files:
        missing_paths.append(rel_path)

# Print results
print('NEW PATHS:')
if new_paths:
    for p in sorted(new_paths):
        print(f'  {p}')
else:
    print('  (none)')

print('\nMISSING PATHS:')
if missing_paths:
    for p in sorted(missing_paths):
        print(f'  {p}')
else:
    print('  (none)')

print('\nMODIFIED PATHS:')
if modified_paths:
    for item in sorted(modified_paths, key=lambda x: x['path']):
        print(f'  {item["path"]}')
        print(f'    Expected: {item["expected_hash"]}')
        print(f'    Actual:   {item["actual_hash"]}')
else:
    print('  (none)')
