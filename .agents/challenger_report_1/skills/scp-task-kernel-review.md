# SCP Task Kernel Review (Local Copy)
Source: c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md

Core Methodology:
- Verify Task Kernel state machine: valid transitions, preconditions/postconditions, atomic transition locking.
- Verify lease fencing, idempotency, event journal immutability, checkpointing before/after side effects, crash consistency.
- Challenge state graph: STATES vs ALLOWED_TRANSITIONS, orphan states, missing states.
