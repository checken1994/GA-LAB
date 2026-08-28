import os
import subprocess
from typing import List

class OSSandbox:
    """
    OS-Level isolation wrapper.
    In a true production environment, this delegates to Seccomp (Linux) or Job Objects (Windows).
    For the research candidate, this acts as the conceptual boundary enforcing Capability Epoch checks
    before any raw OS syscall.
    """
    
    def __init__(self, authority):
        self.authority = authority
    
    def execute_bounded(self, capability_token: str, cmd: List[str], cwd: str = None) -> subprocess.CompletedProcess:
        # 1. Ask CapabilityAuthority if this token is valid in the current epoch
        if not self.authority.validate(capability_token):
            raise PermissionError(f"Epoch violation or unauthorized capability: {capability_token}")
        
        # 2. Strict constraints on execution
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15, # Hard limit
            check=True
        )

    def write_bounded(self, capability_token: str, path: str, content: bytes) -> bool:
        if not self.authority.validate(capability_token):
            raise PermissionError("Write blocked by CapabilityAuthority")
        
        # Prevent path traversal
        if ".." in path or not path.startswith(os.getcwd()):
            raise PermissionError("Path traversal escape attempt detected")
            
        with open(path, "wb") as f:
            f.write(content)
        return True

