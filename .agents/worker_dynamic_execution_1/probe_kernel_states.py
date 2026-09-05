import sys
sys.path.insert(0, ".")
import tempfile
from pathlib import Path
from scp.task_kernel import TaskKernel, STATES, ALLOWED_TRANSITIONS

with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "kernel_probe.sqlite3"
    kernel = TaskKernel(db)
    
    # Check states definitions
    print("STATES count:", len(STATES))
    print("ALLOWED_TRANSITIONS keys count:", len(ALLOWED_TRANSITIONS))
    
    diff_keys = set(ALLOWED_TRANSITIONS.keys()) - STATES
    print("Keys in ALLOWED_TRANSITIONS but not in STATES:", diff_keys)
    
    all_dests = set().union(*ALLOWED_TRANSITIONS.values())
    diff_dests = all_dests - STATES
    print("Destinations in ALLOWED_TRANSITIONS but not in STATES:", diff_dests)
    
    # Live execution test of WAITING_APPROVAL
    task = kernel.create_task("test_approval_task", "operator", "Test Approval Transition", "R0")
    print("Initial task state:", task["state"])
    
    # 1. CREATED -> PLANNING
    p_task = kernel.transition("test_approval_task", "PLANNING", actor="planner", reason="planning")
    print("Transition to PLANNING:", p_task["state"])
    
    # 2. PLANNING -> WAITING_APPROVAL
    app_task = kernel.transition("test_approval_task", "WAITING_APPROVAL", actor="governance", reason="needs approval")
    print("Transition to WAITING_APPROVAL:", app_task["state"])
    
    # 3. Check what get_task returns
    current = kernel.get_task("test_approval_task")
    print("Current task state in DB:", current["state"])
    
    # 4. WAITING_APPROVAL -> READY
    r_task = kernel.transition("test_approval_task", "READY", actor="operator", reason="approved")
    print("Transition to READY:", r_task["state"])
    
    # 5. Check rebuild_projection on WAITING_APPROVAL
    # Let's create a task that ended at WAITING_APPROVAL and crash-recover it
    t2 = kernel.create_task("t2", "operator", "t2", "R0")
    kernel.transition("t2", "PLANNING", actor="p")
    kernel.transition("t2", "WAITING_APPROVAL", actor="g")
    
    # Direct DB corruption simulation or rebuild
    rebuilt = kernel.rebuild_projection("t2")
    print("Rebuilt projection for t2:", rebuilt["state"])
    
    # 6. Check recover_on_boot behavior on WAITING_APPROVAL
    rec_report = kernel.recover_on_boot(actor="boot_recovery")
    print("recover_on_boot report for WAITING_APPROVAL tasks:", rec_report)
    
    kernel.close()
