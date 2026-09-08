# SCP Task Kernel Review
Core Invariants:
1. Task identity: ID, owner, deadline, version, risk profile
2. State machine: Valid transitions, preconditions, atomic lock
3. Event journal: Append-only, sequence increment, hash chain
4. Lease: TTL, heartbeat, fencing, actor verification
5. Recovery: Retry budget, unknown state routing, no blind retry
