# Scope: GAP-07 HandsExecutor Self-Granting Authority Fix

## Architecture
- `scp/hands/hands_executor.py`: PEP execution component. Must NOT issue tokens. Missing token must fail closed.
- `scp/security/capability_epoch.py`: Capability token validation logic. Validate subject/action match.
- `scp/api/routes/hands_routes.py`: API layer. Accepts `capabilityToken` and passes to bridge/executor.
- `scp/hands/task_kernel_bridge.py`: Task kernel bridge. Passes `capability_token` downstream to executor.
- `scp/hands/planner.py`: Hands planner. Passes `capability_token` downstream to executor.
- `tests/`: Update callers/tests that call `HandsExecutor.execute()` or bridge without a token so they supply a valid token issued by authority.

## Bug Inventory
| # | Issue | Description | File | Target Invariant |
|---|---|---|---|---|
| 1 | GAP-01 | Self-granting fallback in `execute` and `rollback` | `scp/hands/hands_executor.py` (~111, ~326) | INV-AUTH-01, FA-05 |
| 2 | GAP-02 | Scope-blind validation in `validate` | `scp/security/capability_epoch.py` (~108-114) | INV-AUTH-02 |
| 3 | GAP-03 | Parameter dropping at protocol boundaries | `hands_routes.py`, `task_kernel_bridge.py`, `planner.py` | INV-AUTH-03, INV-AUTH-04 |
| 4 | GAP-04 | Tests omitting token pass due to self-granting | `tests/` | Anti-Placebo, FA-01 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| 1 | GAP-07 | Eradicate self-granting, enforce subject validation, thread token across callers, migrate tests | None | IN_PROGRESS |

## Interface Contracts
### `HandsExecutor.execute`
- `execute(action: str, params: dict | None = None, capability_level: int = 0, approved: bool = False, dry_run: bool = False, capability_token: CapabilityToken | None = None) -> dict[str, Any]`
- Precondition: `capability_token` is NOT None. If None, return `{"success": False, "action": action, "error": "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)", "verification": {"passed": False}}`.
- Precondition: `capability_token` must validate against authority with subject/action matching `hands:{action}`.

### `HandsExecutor.rollback`
- `rollback(checkpoint_id: str, capability_token: CapabilityToken | None = None) -> dict[str, Any]`
- Precondition: `capability_token` is NOT None. If None, return `{"success": False, "action": "rollback", "error": "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)", "verification": {"passed": False}}`.
- Precondition: `capability_token` must validate against authority with subject matching `hands:rollback`.

### `CapabilityAuthority.validate`
- `validate(token: CapabilityToken, required_subject: str | None = None) -> bool`
- Check epoch, revocation, and ensure `token.subject == required_subject` (if required_subject is provided).

### `HandsActionRequest` & `HandsRollbackRequest`
- Accept `capabilityToken: str | None = None` (or dict/token representation as appropriate).

### `TaskKernelHandsBridge.execute` & `rollback`
- Accept `capability_token` parameter and forward to `executor.execute` / `executor.rollback`.

### `HandsPlanner.run_plan`
- Accept `capability_token` or use plan token and forward to executor.

## Code Layout
- Implementation: `scp/hands/hands_executor.py`, `scp/security/capability_epoch.py`, `scp/api/routes/hands_routes.py`, `scp/hands/task_kernel_bridge.py`, `scp/hands/planner.py`
- Tests: `tests/`
- Probe: `tools/probes/probe_hands_authority_flaws.py`
