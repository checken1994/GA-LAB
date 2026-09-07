import sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from tools.verify_scp_future_target import compose_future_target

manifest, target, errors = compose_future_target()
s = target["core_systems"]["S01_EXECUTION_OS"]
print("SYSTEM: S01_EXECUTION_OS")
print(f"Purpose: {s.get('purpose')}")
print("Capabilities:", len(s.get("capabilities", [])))
for c in s.get("capabilities", []):
    print(f"  {c.get('id')} [{c.get('target_maturity')}, {c.get('phase')}]")
print("Edges:", len(s.get("cause_effect_edges", [])))
for e in s.get("cause_effect_edges", []):
    print(f"  Edge {e['id']}:")
    print(f"    Covers: {e.get('covers_capabilities')}")
    print(f"    Cause: {e.get('cause')}")
    print(f"    Authority Path: {e.get('authority_path')}")
    print(f"    Effects: {e.get('effects')}")
    print(f"    Must NOT Effect: {e.get('must_not_effect')}")
    print(f"    Evidence Target: {e.get('evidence_target')}")
    print(f"    Gates: {e.get('gates')}")
print("Forbidden Paths:", s.get("forbidden_paths"))
