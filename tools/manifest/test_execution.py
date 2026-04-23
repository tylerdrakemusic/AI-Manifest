print("Python is working")
import subprocess
import sys

# Try to execute the commands
try:
    print("\n" + "="*80)
    print("Attempting to execute commands...")
    print("="*80 + "\n")
    
    # Execute the runner script
    result = subprocess.run(
        [sys.executable, "F:\\exec_manifest_commands.py"],
        capture_output=False,
        text=True
    )
    print(f"\nRunner exit code: {result.returncode}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
