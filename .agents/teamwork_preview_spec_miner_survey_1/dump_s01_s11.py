import sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from tools.verify_scp_future_target import compose_future_target

manifest, target, errors = compose_future_target()

for sid in ["S01_EXECUTION_OS", "S04_INTERNET_SAFETY", "S05_EVIDENCE_SYSTEM", "S09_SELF_IMPROVEMENT", "S10_RISK_INTELLIGENCE", "S11_GOVERNANCE"]:
    s = target.get("core_systems", {}).get(sid)
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
