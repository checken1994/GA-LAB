'\nSCP Auto-Fix Engine — autonomous bug fixing with tiered autonomy.\n\nFlow:\n  1. Deep audit detects bug → BugReport\n  2. Classifier assigns tier\n  3. Engine acts based on tier:\n     - Tier 1: fix immediately, no report\n     - Tier 2: fix immediately, log to audit trail\n     - Tier 3: request permission, WAIT (do not fix until approved)\n     - Tier 4: fix immediately (attack mode, restraints only), log + flag for post-hoc review\n\nThe engine uses code_evolution_agent._apply_fix() for the actual patching\n(search-replace markers + ast.parse verification), but ONLY for approved tiers.\n\n[SAFETY] The engine NEVER:\n  - Auto-applies a relaxation (loosens security) — always Tier 3\n  - Auto-applies a verdict threshold change — always Tier 3\n  - Skips the permission gate for logic bugs\n  - Fixes more than MAX_FIXES_PER_CYCLE per audit cycle (rate limit)\n'

from __future__ import annotations

import json

import logging

import os

import threading

import time

from pathlib import Path

from scp.autofix.classifier import BugClassifier, BugReport, BugTier

from scp.autofix.permission import PermissionGate

logger = logging.getLogger('scp.autofix')

MAX_FIXES_PER_CYCLE = 200

MAX_TIER4_PER_HOUR = 20

COOLDOWN_SAME_BUG_SECONDS = 3600

CYCLE_RESET_SECONDS = 3600

MAX_TIER3_AUTO_PER_HOUR = 5

TIER3_AUTO_TIMEOUT_SECONDS = 3600

class Tier3AutoConfig:
    """Centralized config for Tier-3 auto-approve — SCP understands the permission.

    DNA SCP #4 (Constitution KILL) — Tier-3 = logic bugs, mặc định human approval.
    DNA SCP #7 (AutoFix safe) — 6 safety guards even when auto-approve ON.
    DNA SCP #8 (KB accumulation) — audit trail lưu lại mọi auto-approve decisions.

    User cấp quyền qua:
      1. .env file: SCP_AUTO_APPROVE_TIER3=1 (persistent, reload on restart)
      2. API: POST /v105/autofix/tier3-auto/{enabled} (runtime, không cần restart)
      3. PowerShell: $env:SCP_AUTO_APPROVE_TIER3 = "1" (session only)

    SCP HIỂU quyền bằng cách:
      - Log startup: "[TIER3-AUTO] Permission GRANTED by .env (SCP_AUTO_APPROVE_TIER3=1)"
      - Log startup: "[TIER3-AUTO] Permission DENIED (default, .env not set or =0)"
      - Audit log: mỗi auto-approve → data/tier3_auto_audit.jsonl
      - Stats endpoint: /v105/autofix/stats trả về tier3_auto_enabled + reasons
    """

    def __init__(self):
        self._audit_log = Path('data/tier3_auto_audit.jsonl')
        self._audit_log.parent.mkdir(parents=True, exist_ok=True)

    def is_enabled(self) -> bool:
        """Check if Tier-3 auto-approve is enabled (with logging)."""
        val = os.environ.get('SCP_AUTO_APPROVE_TIER3', '0')
        enabled = val == '1'
        return enabled

    def get_permission_source(self) -> str:
        """Identify WHERE the permission came from."""
        if 'SCP_AUTO_APPROVE_TIER3' not in os.environ:
            return 'default (not set — human approval required)'
        val = os.environ.get('SCP_AUTO_APPROVE_TIER3', '0')
        if val == '1':
            return '.env file (SCP_AUTO_APPROVE_TIER3=1 — auto-approve GRANTED)'
        return '.env file (SCP_AUTO_APPROVE_TIER3=0 — human approval required)'

    def log_startup_permission(self):
        """Log at startup: SCP understands whether permission is granted."""
        source = self.get_permission_source()
        if self.is_enabled():
            logger.warning(f'[TIER3-AUTO] ⚠️  Permission GRANTED — Tier-3 auto-approve ENABLED\n  Source: {source}\n  Safety guards active: 1h timeout, 5/hour limit, no relaxation,\n  no BareExceptPass, cooldown 1h per bug\n  Audit log: {self._audit_log}')
        else:
            logger.info(f'[TIER3-AUTO] Permission NOT granted — human approval required\n  Source: {source}\n  To enable: set SCP_AUTO_APPROVE_TIER3=1 in .env + restart\n  Or runtime: POST /v105/autofix/tier3-auto/1 (no restart needed)')

    def audit_auto_approve(self, bug: BugReport, reason: str):
        """Audit trail: record every auto-approve decision."""
        import json
        import time as _time
        entry = {'timestamp': _time.time(), 'action': 'auto_approve', 'file': bug.file, 'line': bug.line, 'bug_type': bug.bug_type, 'reason': reason, 'permission_source': self.get_permission_source()}
        try:
            with open(self._audit_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.debug(f'[TIER3-AUTO] audit log write failed: {e}')

_tier3_config: Tier3AutoConfig | None = None

def get_tier3_config() -> Tier3AutoConfig:
    """Get singleton Tier3AutoConfig."""
    global _tier3_config
    if _tier3_config is None:
        _tier3_config = Tier3AutoConfig()
    return _tier3_config

TIER3_AUTO_AUDIT_LOG = 'tier3_auto_audit.jsonl'

_autofix_engine: AutoFixEngine | None = None

_autofix_lock = threading.Lock()

def get_autofix_engine(data_dir: str='data') -> AutoFixEngine:
    """Get the singleton AutoFixEngine instance.

    [EXEC-1 A1] Returns the SAME engine instance across all calls so that:
      - attack_mode toggle persists across requests
      - rate limits (_fixes_this_cycle, _tier4_timestamps) actually apply
      - cooldown (_recent_fixes) prevents re-fixing same bug
      - permission_gate._pending is shared (no race between handlers)
    """
    global _autofix_engine
    if _autofix_engine is None:
        with _autofix_lock:
            if _autofix_engine is None:
                _autofix_engine = AutoFixEngine(data_dir=data_dir)
                logger.info('[AutoFix] Singleton engine initialized')
    return _autofix_engine

def reset_autofix_engine() -> None:
    """Reset the singleton (for tests / explicit re-init)."""
    global _autofix_engine
    with _autofix_lock:
        _autofix_engine = None

try:
    from scp.autofix.engine_extensions import inject_v2_extensions as _inject_v2
    _inject_v2(AutoFixEngine)
    logger.info('[R7-Full] IMP-6 (rollback token) + IMP-9 (dry-run) injected into AutoFixEngine')
except ImportError as _v2_imp_err:
    logger.warning(f'[R7-Full] engine_extensions.py unavailable — IMP-6/IMP-9 disabled: {_v2_imp_err}')
except Exception as _v2_inj_err:
    logger.warning(f'[R7-Full] v2 extension injection failed (non-fatal): {_v2_inj_err}')

from .engine_parts.autofixengine import AutoFixEngine
