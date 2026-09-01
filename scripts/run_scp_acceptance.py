#!/usr/bin/env python3
"""SCP-level acceptance suite.

This suite asks one question only: does the assembled SCP runtime preserve its
critical invariants when exercised through real process, HTTP, persistence and
failure boundaries?

It deliberately does not assert implementation details such as concrete model
names or private helper calls. Unit/component tests remain diagnostic tools;
this runner emits the release-level behavioral evidence.
"""
from __future__ import annotations

# This file is imported from the hardened acceptance implementation carried by
# the fail-closed release work. Keeping the implementation in a dedicated
# module prevents the release workflow from silently falling back to a unit-test
# count when system acceptance is missing.
from scripts._scp_acceptance_impl import *  # noqa: F401,F403

if __name__ == "__main__":
    raise SystemExit(main())
