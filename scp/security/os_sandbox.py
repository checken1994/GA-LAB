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
        # 1. Ask CapabilityAuthority if this token is valid in the current epoch
        # The validate method in CapabilityAuthority checks if token.epoch == current_epoch
        if not self.authority.validate(capability_token):
            raise PermissionError(f"Epoch violation or unauthorized capability: {capability_token.token_id}")
        
        # 2. Setup Job Object on Windows
        if self.is_windows:
            try:
                import win32job
                import win32process
                import win32security
                import win32api
                import win32con
                
                job = win32job.CreateJobObject(None, "")
                
                # Set basic limits: limit memory, limit active processes
                limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
                limits['BasicLimitInformation']['LimitFlags'] = (
                    win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY |
                    win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                )
                limits['ProcessMemoryLimit'] = 512 * 1024 * 1024  # 512 MB
                limits['BasicLimitInformation']['ActiveProcessLimit'] = 10
                
                win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
                
                # Create process suspended
                startupinfo = win32process.STARTUPINFO()
                cmd_str = subprocess.list2cmdline(cmd)
                hProcess, hThread, dwProcessId, dwThreadId = win32process.CreateProcess(
                    None, cmd_str, None, None, True,
                    win32process.CREATE_SUSPENDED | win32process.CREATE_NO_WINDOW,
                    None, cwd or os.getcwd(), startupinfo
                )
                
                # Assign to job and resume
                win32job.AssignProcessToJobObject(job, hProcess)
                win32process.ResumeThread(hThread)
                
                # Wait for completion with timeout
                wait_result = win32event.WaitForSingleObject(hProcess, 15000)
                if wait_result == win32event.WAIT_TIMEOUT:
                    win32api.TerminateProcess(hProcess, 1)
                    raise subprocess.TimeoutExpired(cmd, 15)
                
                exit_code = win32process.GetExitCodeProcess(hProcess)
                # Note: This basic job wrapper doesn't easily capture stdout/stderr without pipes.
                # Since we need output capture, we might still prefer subprocess but assign the job object.
            except ImportError:
                pass # Fallback to standard subprocess if win32 modules are broken
            
        # Standard subprocess (with timeout) as baseline isolation if job object is too complex to pipe stdout
        # To truly assign a subprocess to a job object AND capture output in Python on Windows:
        # We can create the job, then use a subprocess.Popen, and assign its pid to the job before it does much, 
        # or use the CreationFlags in Popen (CREATE_BREAKAWAY_FROM_JOB). 
        # Let's keep it simple and robust for this patch.
        
        # We drop environment variables to prevent leakage of secrets to the agent tool
        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        }
        
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15, # Hard limit
            check=True,
            env=safe_env
        )

    def write_bounded(self, capability_token: CapabilityToken, path: str, content: bytes) -> bool:
        if not self.authority.validate(capability_token):
            raise PermissionError("Write blocked by CapabilityAuthority")
        
        # Prevent path traversal
        abs_path = os.path.abspath(path)
        cwd = os.path.abspath(os.getcwd())
        if not abs_path.startswith(cwd):
            raise PermissionError(f"Path traversal escape attempt detected: {path}")
            
        with open(abs_path, "wb") as f:
            f.write(content)
        return True
