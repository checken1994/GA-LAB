# SCP Reality Verifier
Evidence hierarchy:
A — Static (file, route, schema, pattern or assertion exists)
B — Integration (some modules/processes connect together)
C — End-to-end (real task goes through planner, policy, tool, verifier, audit and artifact)
D — Recovery proof (Level C + crash/timeout/restart/unknown-state handled correctly)

Rules:
- Never trust model assertions or static presence alone.
- Physical execution and inspection of actual runtime state (e.g. SQLite tables) is mandatory.
- Pass within scope != completed or production ready.
