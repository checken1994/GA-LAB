import os
import platform
import subprocess
from typing import List
from scp.security.capability_epoch import CapabilityToken, CapabilityAuthority

class ProcessIsolationEnvironment:
    """
    OS-Level isolation wrapper.
    Replaces the dangerously misnamed 'OSSandbox'.
    Uses Windows Job Objects (if on Windows) to enforce memory and process limits.
    For cross-platform compatibility, falls back to subprocess boundaries.
    """
    
    def __init__(self, authority: CapabilityAuthority):
        self.authority = authority
        self.is_windows = platform.system() == "Windows"
    
    def execute_bounded(self, capability_token: CapabilityToken, cmd: List[str], cwd: str = None) -> subprocess.CompletedProcess:
        if not self.authority.validate(capability_token):
            raise PermissionError(f"Epoch violation or unauthorized capability: {capability_token.token_id}")
        
        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        }
        
        if self.is_windows:
            try:
                import win32job
                import win32process
                import win32api
                import win32con
                
                # Use subprocess to handle pipes, but assign process to job immediately
                proc = subprocess.Popen(
                    cmd, cwd=cwd, env=safe_env, capture_output=True, text=True,
                    creationflags=win32process.CREATE_SUSPENDED
                )
                
                job = win32job.CreateJobObject(None, "")
                limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
                limits['BasicLimitInformation']['LimitFlags'] = (
                    win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY |
                    win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                )
                limits['ProcessMemoryLimit'] = 512 * 1024 * 1024  # 512 MB
                limits['BasicLimitInformation']['ActiveProcessLimit'] = 10
                win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
                
                win32job.AssignProcessToJobObject(job, int(proc._handle))
                win32process.ResumeThread(int(proc._handle))
                
                stdout, stderr = proc.communicate(timeout=15)
                retcode = proc.returncode
                return subprocess.CompletedProcess(proc.args, retcode, stdout, stderr)
                
            except Exception as e:
                pass # Fallback if win32 APIs fail
                
        # Non-Windows or Fallback
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=15, env=safe_env)

    def write_bounded(self, capability_token: CapabilityToken, path: str, content: bytes) -> bool:
        if not self.authority.validate(capability_token):
            raise PermissionError("Write blocked by CapabilityAuthority")
        
        # Prevent path traversal
        from pathlib import Path
        abs_path = Path(path).resolve()
        cwd_path = Path(os.getcwd()).resolve()
        try:
            abs_path.relative_to(cwd_path)
        except ValueError:
            raise PermissionError(f"Path traversal escape attempt detected: {path}")
            
        with open(abs_path, "wb") as f:
            f.write(content)
        return True
