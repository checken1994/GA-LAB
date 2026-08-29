import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scp.security.capability_epoch import CapabilityAuthority, CapabilityToken
from scp.security.os_sandbox import ProcessIsolationEnvironment

def main():
    auth = CapabilityAuthority(state_path="test_auth_state.json")
    token = auth.issue("test_subject")
    sandbox = ProcessIsolationEnvironment(auth)

    print("--- CHAOS TEST: SANDBOX ESCAPE ---")
    
    cmd = ['powershell', '-Command', 'echo $env:USERNAME; Get-Content C:\\Windows\\win.ini -TotalCount 3']
    
    try:
        result = sandbox.execute_bounded(token, cmd, cwd=os.getcwd())
        print(f"Return code: {result.returncode}")
        print(f"Stdout:\n{result.stdout}")
        
        if result.returncode == 0 and result.stdout.strip():
            print(">>> EXPLOIT SUCCESSFUL! Sandbox FAILED to block file system and env access.")
        else:
            print(">>> EXPLOIT FAILED. Sandbox blocked access.")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == '__main__':
    main()
