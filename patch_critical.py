import os
import re

# 1. Fix ast_scan.py
ast_path = r"scp/autofix/runner_phases/ast_scan.py"
with open(ast_path, "r", encoding="utf-8") as f:
    ast_content = f.read()

# Replace the literal `n with \n or just standard formatting
ast_content = ast_content.replace("\"scp/task_kernel.py\",`n    \"scp/security/capability_epoch.py\",", "\"scp/task_kernel.py\",\n    \"scp/security/capability_epoch.py\",")
with open(ast_path, "w", encoding="utf-8") as f:
    f.write(ast_content)

# 2. Fix task_kernel.py
kernel_path = r"scp/task_kernel.py"
with open(kernel_path, "r", encoding="utf-8") as f:
    k_content = f.read()

# Change string comparison to Enum, and fix the exception swallowing
fix_code = """                    from scp.meta.why_gate import get_why_gate, WhyDecision
                    why_res = get_why_gate().gate(
                        action_type="kernel_transition",
                        action_desc=f"Transition {task_id} from {old} to {to_state} by {actor}",
                        context=reason
                    )
                    if why_res.decision == WhyDecision.REJECT:
                        raise InvalidTransition(f"WHY Gate REJECTED this kernel transition: {why_res.falsification_reason}")
                    # Nếu ALLOW hoặc UPHOLD, cứ tiếp tục
                except InvalidTransition:
                    raise  # RE-RAISE so the transition is actually blocked
                except Exception as why_err:
                    raise InvalidTransition(f"WHY Gate crashed, fail-closed: {why_err}")"""

# Replace the old block
old_block = """                    from scp.meta.why_gate import get_why_gate
                    why_res = get_why_gate().gate(
                        action_type="kernel_transition",
                        action_desc=f"Transition {task_id} from {old} to {to_state} by {actor}",
                        context=reason
                    )
                    if why_res.decision == "REJECT":
                        raise InvalidTransition(f"WHY Gate REJECTED this kernel transition: {why_res.falsification_reason}")
                    # N?u ALLOW ho?c UPHOLD, c? ti?p t?c
                except Exception as why_err:
                    pass # Fallback n?u WhyGate l?i c?u h?nh"""

# Wait, the exact text has encoding mojibake: "N?u ALLOW ho?c UPHOLD"
# I will use Regex instead of exact string replacement.
pattern = r"from scp\.meta\.why_gate import get_why_gate[\s\S]*?pass\s*# Fallback.*?"
k_content = re.sub(pattern, fix_code, k_content)

with open(kernel_path, "w", encoding="utf-8") as f:
    f.write(k_content)
