import sys
from pathlib import Path
import json

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))

from tools.verify_scp_future_target import compose_future_target

manifest, target, errors = compose_future_target()

print("=== 34 GLOBAL INVARIANTS ===")
for inv in target.get("global_invariants", []):
    print(f"{inv['id']}: {inv['rule']}")

print("\n=== SPECIFIC SYSTEMS FOR 4 CORE INVARIANTS ===")
target_systems = [
    "S01_EXECUTION_OS",
    "S04_INTERNET_SAFETY",
    "S05_EVIDENCE_SYSTEM",
    "S09_SELF_IMPROVEMENT",
    "S10_RISK_INTELLIGENCE",
    "S11_GOVERNANCE",
    "S12_SELF_AWARENESS_AUDIT",
    "X01_IDENTITY_TRUST",
    "X05_DISASTER_RECOVERY",
]

for sid in target_systems:
    s = target.get("core_systems", {}).get(sid) or target.get("cross_cutting_systems", {}).get(sid)
    if not s:
        continue
    print(f"\n==========================================")
    print(f"SYSTEM: {sid} (Purpose: {s.get('purpose')})")
    print(f"Capabilities ({len(s.get('capabilities', []))}):")
    for c in s.get("capabilities", []):
        print(f"  - {c.get('id')} [Maturity: {c.get('target_maturity')}, Phase: {c.get('phase')}]")
    print(f"Cause-Effect Edges ({len(s.get('cause_effect_edges', []))}):")
    for e in s.get("cause_effect_edges", []):
        print(f"  - Edge ID: {e['id']}")
        print(f"    Covers: {e.get('covers_capabilities')}")
        print(f"    Cause: {e.get('cause')}")
        print(f"    Authority Path: {e.get('authority_path')}")
        print(f"    Effects: {e.get('effects')}")
        print(f"    Must NOT Effect: {e.get('must_not_effect')}")
        print(f"    Evidence Target: {e.get('evidence_target')}")
        print(f"    Gates: {e.get('gates')}")
    print(f"Forbidden Paths: {s.get('forbidden_paths')}")

print("\n=== SYSTEM DEPENDENCY GRAPH FORBIDDEN EDGES ===")
for fe in target.get("system_dependency_graph", {}).get("forbidden_edges", []):
    print(f"  - {fe}")
