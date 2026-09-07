import sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from tools.verify_scp_future_target import compose_future_target

manifest, target, errors = compose_future_target()
test_arch = target.get("test_architecture", {})
print("=== 12 TEST GATES (T00 - T11) ===")
for gid, g in sorted(test_arch.items()):
    print(f"Gate {gid}: {g.get('name')}")
    print(f"  Focus: {g.get('focus')}")
    print(f"  Obligations: {g.get('obligations')}")
