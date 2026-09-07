# Project: SCP (Agent OS) Remediation GAP-05, GAP-06, GAP-08, GAP-09

## Architecture
- `scp/kernel_storage.py`: Storage abstraction layer for TaskKernel. SQLite backend with WAL mode and OCC. Replaced placebo RLock with pure SQLite WAL concurrency + OCC. Added SPOF docstring warning and fail-closed `SCP_STORAGE_BACKEND` guard.
- `scp/core/capability_token.py`: Capability token definition, generation (`issue()`), and validation (`validate()`). Must fail closed without fallback secret (`MissingSecretError`), and sign/verify tokens using HMAC-SHA256 (`InvalidTokenSignatureError`).
- `.env.example`: Environment variable specification for `SCP_CAPABILITY_SECRET`.
- `tests/`: Pytest test suite, fixtures, and regression test suites.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | GAP-05 | Verify absence of placebo RLock in scp/kernel_storage.py and multi-process OCC | M1 | ORIGINAL_REQUEST § R1 |
| 2 | GAP-06 | make_storage() SPOF docstring warning and SCP_STORAGE_BACKEND guard | M1 | ORIGINAL_REQUEST § R2 |
| 3 | GAP-09 | Remove hardcoded fallback secret in scp/core/capability_token.py; raise MissingSecretError fail-closed; update .env.example & test fixtures | M2 | ORIGINAL_REQUEST § R4 |
| 4 | GAP-08 | CapabilityToken HMAC-SHA256 signing in issue(); verification in validate(); InvalidTokenSignatureError fail-closed; reject unsigned/tampered tokens | M3 | ORIGINAL_REQUEST § R3 |
| 5 | Adversarial & Regression | Adversarial penetration testing (token forgery, secret bypass, env injection) and full regression (pytest >= 482 PASS, exit 0; t00_meta_audit PASS) | M4 | ORIGINAL_REQUEST Acceptance Criteria |
| 6 | Sentinel Handoff | Deliver comprehensive handoff to .agents/sentinel_4/handoff.md with HEAD_SHA, TREE_HASH, evidence links | M5 | ORIGINAL_REQUEST § Handoff |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: GAP-05 & GAP-06 Verification | Verify absence of RLock in scp/ and verify make_storage() SPOF docstring & SCP_STORAGE_BACKEND guard via pytest | none | DONE |
| 2 | M2: GAP-09 Secret Fail-Closed | Remove fallback secret, raise MissingSecretError, update .env.example, update test fixtures | M1 | DONE |
| 3 | M3: GAP-08 HMAC Signing & Validation | Implement HMAC-SHA256 signature generation and verification in capability_token.py; fail-closed on invalid/missing signature | M2 | DONE |
| 4 | M4: Adversarial & Regression Gate | Run token forgery and secret bypass probes; verify >= 482 pytest tests PASS; verify python tools/t00_meta_audit.py | M3 | DONE |
| 5 | M5: Final Delivery | Write handoff report to sentinel_4/handoff.md and report to Sentinel | M4 | IN_PROGRESS |

## Interface Contracts
### `scp/kernel_storage.py`
- `make_storage(db_path: str | Path, backend: str | None = None) -> SQLiteKernelStorage`:
  - Docstring includes:
    ```
    WARNING: SQLite is a Single Point of Failure (SPOF) in distributed deployments.
    It does not support cross-node replication or active-active clustering.
    For high availability or multi-node production setups, a distributed storage backend is required.
    ```
  - Backend resolution: checks `backend` parameter or `os.environ.get("SCP_STORAGE_BACKEND", "sqlite")`.
  - Normalizes with `.strip().lower()`. If in `("sqlite", "")`, returns `SQLiteKernelStorage(db_path)`.
  - Otherwise raises `NotImplementedError(f"Unsupported storage backend '{backend}'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.")`.

### `scp/core/capability_token.py`
- `MissingSecretError(RuntimeError)`: Raised if `SCP_CAPABILITY_SECRET` is not set or empty. No fallback secret allowed.
- `InvalidTokenSignatureError(ValueError)`: Raised if token signature is missing, invalid, or forged.
- `CapabilityToken.signature: str`: HMAC-SHA256 hex digest of the canonical token payload.
- `CapabilityToken.issue(...) -> CapabilityToken`: Computes HMAC-SHA256 using `SCP_CAPABILITY_SECRET`.
- `CapabilityToken.validate(...) -> None`: Verifies HMAC-SHA256 using constant-time comparison (`hmac.compare_digest`). Rejects unsigned or tampered tokens with `InvalidTokenSignatureError`.

## Code Layout
- `scp/kernel_storage.py`: Storage implementation and factory.
- `scp/core/capability_token.py`: Capability token data structures and cryptographic verification.
- `.env.example`: Template for environment variables.
- `tests/conftest.py` / test fixtures: Inject `SCP_CAPABILITY_SECRET` for testing.
- `tests/T04_kernel/test_kernel_storage.py`: Kernel storage tests.
- `tests/T02_capability/`: Capability token tests.
