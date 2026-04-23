"""
Run from repo root to print a sample positive prompt.
Usage:
  powershell> python .\print_prompt.py [qrandom|crandom]
Or set env BF_MODE=crandom
"""
import os
import sys
import importlib.util

# Ensure ty_py is on the path
ROOT = os.path.dirname(os.path.abspath(__file__))
ty_dir = os.path.join(ROOT, 'ty_py')
if ty_dir not in sys.path:
  sys.path.insert(0, ty_dir)

try:
  import ty_py.babeFeatures as bf  # relies on quantum_rt.py at repo root
except Exception:
  spec = importlib.util.spec_from_file_location('babeFeatures', os.path.join(ty_dir, 'babeFeatures.py'))
  bf = importlib.util.module_from_spec(spec)
  assert spec and spec.loader
  spec.loader.exec_module(bf)

mode = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get('BF_MODE', 'qrandom')).lower()
prompt = bf._build_random_positive_prompt(selector_mode=mode)
print(f"a beautiful woman {prompt}")
