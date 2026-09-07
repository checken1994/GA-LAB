"""Root pytest configuration and fixtures for SCP test suite.

Ensures required environment variables (such as SCP_CAPABILITY_SECRET)
are safely defaulted for automated test collection while preserving
fail-closed semantics if intentionally unset during explicit tests.
"""

from __future__ import annotations

import os

# Default capability secret for automated test collection and suites (GAP-09).
# Test cases verifying fail-closed behavior when unset will explicitly remove
# or monkeypatch this variable in subprocesses or isolated scopes.
os.environ.setdefault(
    "SCP_CAPABILITY_SECRET",
    "test-capability-secret-for-automated-suites-only-32bytes",
)
