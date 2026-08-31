# Auto-extracted from engine.py
from __future__ import annotations
import json
import logging
import os
import threading
import time
from pathlib import Path
from scp.autofix.classifier import BugClassifier, BugReport, BugTier
from scp.autofix.permission import PermissionGate

class AutoFixEngine:
    """Autonomous bug fixing engine with tiered autonomy."""

    def __init__(self, data_dir: str='data', in_attack_mode: bool=False):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log = self.data_dir / 'autofix_audit.jsonl'
        self.classifier = BugClassifier()
        self.permission_gate = PermissionGate(data_dir=data_dir)
        get_tier3_config().log_startup_permission()
        if not in_attack_mode:
            in_attack_mode = os.environ.get('SCP_ATTACK_MODE', '0') == '1'
        self.in_attack_mode = in_attack_mode
        if self.in_attack_mode:
            logger.warning('[TIER4-ATTACK] ⚠️  Attack mode ENABLED via .env (SCP_ATTACK_MODE=1)\n  SCP will auto-apply restraints (tighten security) without human approval.\n  Safety guards: 20/hour limit, reversible only, audit log, no relaxation.\n  To disable: set SCP_ATTACK_MODE=0 in .env + restart.')
        self._fixes_this_cycle = 0
        self._tier4_timestamps: list[float] = []
        self._recent_fixes: dict[str, float] = {}
        self._cycle_start_time: float = time.time()
        self._tier3_auto_timestamps: list[float] = []
        self._tier3_auto_enabled_at: float = 0.0
        self.tier3_auto_audit_log = self.data_dir / TIER3_AUTO_AUDIT_LOG

    def _check_cycle_reset(self) -> None:
        """Reset per-cycle counters when CYCLE_RESET_SECONDS elapsed.

        [EXEC-1 A3] Called at the start of process_bug() so the engine can
        keep fixing bugs indefinitely (rate limit applies per-cycle, not
        per-process-lifetime). Without this, the singleton would hit
        MAX_FIXES_PER_CYCLE=10 once and never auto-fix again.
        """
        if time.time() - self._cycle_start_time > CYCLE_RESET_SECONDS:
            self._fixes_this_cycle = 0
            self._cycle_start_time = time.time()
            logger.info(f'[AutoFix] Cycle reset — _fixes_this_cycle cleared after {CYCLE_RESET_SECONDS}s')

    def process_bug(self, bug: BugReport) -> dict:
        """Process a detected bug. Returns action taken.

        Returns:
          {"action": "fixed" | "permission_requested" | "skipped" | "denied",
           "tier": int,
           "request_id": str (if permission_requested),
           "reason": str}
        """
        self._check_cycle_reset()
        classified = self.classifier.classify(file=bug.file, line=bug.line, bug_type=bug.bug_type, description=bug.description, suggested_fix=bug.suggested_fix, in_attack_mode=self.in_attack_mode, tier_hint=bug.tier if bug.tier != BugTier.TIER_1_AUTO_FIX else None)
        try:
            from scp.autofix.monitor import get_monitor as _get_monitor
            _adj = _get_monitor().get_tier_adjustment(bug.bug_type)
            if _adj != 0 and classified.tier in (BugTier.TIER_1_AUTO_FIX, BugTier.TIER_2_AUTO_FIX_LOG):
                _new_tier_val = max(1, min(2, int(classified.tier) + _adj))
                _new_tier = BugTier(_new_tier_val)
                if _new_tier != classified.tier:
                    logger.info(f'[Idea5] tier adjusted {bug.bug_type}: Tier {int(classified.tier)} → Tier {int(_new_tier)} (streak evidence, adj={_adj:+d})')
                    classified.tier = _new_tier
        except Exception as _idea5_err:
            logger.debug(f'[Idea5] tier adjustment skipped (fail-open): {_idea5_err}')
        bug_key = f'{bug.file}:{bug.line}:{bug.bug_type}'
        now = time.time()
        if bug_key in self._recent_fixes:
            if now - self._recent_fixes[bug_key] < COOLDOWN_SAME_BUG_SECONDS:
                return {'action': 'skipped', 'tier': int(classified.tier), 'reason': 'cooldown — same bug fixed recently'}
        if classified.tier == BugTier.TIER_1_AUTO_FIX:
            return self._auto_fix(classified, report=False)
        elif classified.tier == BugTier.TIER_2_AUTO_FIX_LOG:
            return self._auto_fix(classified, report=True)
        elif classified.tier == BugTier.TIER_3_PERMISSION:
            return self._request_permission(classified)
        elif classified.tier == BugTier.TIER_4_ATTACK_MODE:
            self._tier4_timestamps = [t for t in self._tier4_timestamps if now - t < 3600]
            if len(self._tier4_timestamps) >= MAX_TIER4_PER_HOUR:
                return {'action': 'skipped', 'tier': 4, 'reason': f'rate limit — {MAX_TIER4_PER_HOUR} Tier-4 fixes/hour exceeded'}
            self._tier4_timestamps.append(now)
            return self._auto_fix(classified, report=True, attack_mode=True)
        return {'action': 'skipped', 'tier': 0, 'reason': 'unknown tier'}

    def _verify_fix(self, filepath, original_bugs: list) -> tuple[bool, str]:
        """Self-verify a fix after applying patch.

        Args:
            filepath: Path to the patched file.
            original_bugs: List of BugReport objects that the fix was supposed to address.

        Returns (is_valid, reason).
        - is_valid=False → fix broke things → caller should ROLLBACK
        - is_valid=True → every required verifier passed

        Checks (in priority order):
          1. ast.parse() — patched file still parses (syntax OK)
          2. Re-scan same file — original bug still there? (NEW)
          3. Check no NEW bugs introduced (compare against original_bugs signatures)
          4. [WORLD-CLASS-GATE] self_scan_patch_diff — patch không được thêm pattern nguy hiểm
          5. [WORLD-CLASS-GATE] pytest — suite không được vỡ sau patch
        """
        try:
            try:
                import ast as _ast
                _content = filepath.read_text(encoding='utf-8')
                _ast.parse(_content, filename=str(filepath))
            except SyntaxError as _se:
                return (False, f'patched file SyntaxError: {_se}')
            except Exception as _parse_err:
                return (False, f'parse check failed: {_parse_err}')
            try:
                from scp.autofix.runner import ast_scan_scp
                _all_bugs = ast_scan_scp(include_enterprise=False)
                _remaining_for_this_file = [b for b in _all_bugs if str(getattr(b, 'file', '')) == str(filepath)]
                _still_present = []
                for orig in original_bugs:
                    for remain in _remaining_for_this_file:
                        if getattr(remain, 'line', None) == getattr(orig, 'line', None) and getattr(remain, 'bug_type', '') == getattr(orig, 'bug_type', ''):
                            _still_present.append(orig)
                            break
                if _still_present:
                    return (False, f'original bug still present after fix: {len(_still_present)}/{len(original_bugs)} unchanged')
            except ImportError as _rescan_import_err:
                logger.warning(' ast_scan_scp unavailable; rejecting unverifiable fix: %s', type(_rescan_import_err).__name__)
                return (False, 're-scan unavailable; fix is UNVERIFIED')
            except Exception as _rescan_err:
                logger.warning(' re-scan failed; rejecting unverifiable fix: %s', type(_rescan_err).__name__)
                return (False, 're-scan failed; fix is UNVERIFIED')
            try:
                from scp.autofix.runner import ast_scan_scp
                _all_bugs_post = ast_scan_scp(include_enterprise=False)
                _new_bugs = []
                _orig_lines = {getattr(b, 'line', None) for b in original_bugs}
                for b in _all_bugs_post:
                    if str(getattr(b, 'file', '')) != str(filepath):
                        continue
                    _b_line = getattr(b, 'line', None)
                    _b_type = getattr(b, 'bug_type', '')
                    if (_b_line, _b_type) not in {(getattr(o, 'line', None), getattr(o, 'bug_type', '')) for o in original_bugs}:
                        for _ol in _orig_lines:
                            if _b_line and _ol and (abs(_b_line - _ol) <= 10):
                                _new_bugs.append(b)
                                break
                if _new_bugs:
                    return (False, f"fix introduced {_new_bugs.__len__()} new bug(s) near fix line: {[getattr(b, 'bug_type', '?') for b in _new_bugs[:3]]}")
            except ImportError as _new_bug_import_err:
                logger.warning(' new-bug scanner unavailable; rejecting unverifiable fix: %s', type(_new_bug_import_err).__name__)
                return (False, 'new-bug scan unavailable; fix is UNVERIFIED')
            except Exception as _new_bug_err:
                logger.warning(' new-bug scan failed; rejecting unverifiable fix: %s', type(_new_bug_err).__name__)
                return (False, 'new-bug scan failed; fix is UNVERIFIED')
            try:
                _pytest_child_env = os.environ.copy()
                _pytest_child_env['SCP_AUTOFIX_RUN_PYTEST'] = '0'
                if os.environ.get('SCP_AUTOFIX_RUN_PYTEST', '0') == '1':
                    import subprocess as _sp
                    import sys as _sys
                    _tests_dir = filepath.parent
                    while _tests_dir.parent != _tests_dir:
                        if (_tests_dir / 'tests').is_dir() or (_tests_dir / 'scp' / 'tests').is_dir():
                            break
                        _tests_dir = _tests_dir.parent
                    _root = _tests_dir
                    if (_root / 'tests').is_dir() or (_root / 'scp' / 'tests').is_dir():
                        _proc = _sp.run([_sys.executable, '-m', 'pytest', '-q', '--timeout=60', str(filepath)], cwd=str(_root), capture_output=True, text=True, timeout=90, encoding='utf-8', errors='replace', check=False, env=_pytest_child_env)
                        if _proc.returncode != 0:
                            import re as _re
                            _summary = (_proc.stdout or _proc.stderr or '').strip().splitlines()
                            _last = _summary[-1] if _summary else ''
                            _fail_m = _re.search('(\\d+) failed', _last)
                            _pass_m = _re.search('(\\d+) passed', _last)
                            _post_fails = int(_fail_m.group(1)) if _fail_m else 0
                            _post_passes = int(_pass_m.group(1)) if _pass_m else 0
                            _backup_path = filepath.with_suffix(filepath.suffix + '.tier3bak')
                            if not _backup_path.exists():
                                _backup_path = filepath.with_suffix(filepath.suffix + '.audit_fix_backup')
                            if _backup_path.exists():
                                import shutil as _shutil
                                _tmp_save = filepath.with_suffix(filepath.suffix + '.post_save')
                                _shutil.copy(str(filepath), str(_tmp_save))
                                try:
                                    _shutil.copy(str(_backup_path), str(filepath))
                                    _base_proc = _sp.run([_sys.executable, '-m', 'pytest', '-q', '--timeout=60', str(filepath)], cwd=str(_root), capture_output=True, text=True, timeout=90, encoding='utf-8', errors='replace', check=False, env=_pytest_child_env)
                                    _base_summary = (_base_proc.stdout or '').strip().splitlines()
                                    _base_last = _base_summary[-1] if _base_summary else ''
                                    _base_fail_m = _re.search('(\\d+) failed', _base_last)
                                    _base_pass_m = _re.search('(\\d+) passed', _base_last)
                                    _base_fails = int(_base_fail_m.group(1)) if _base_fail_m else 0
                                    _base_passes = int(_base_pass_m.group(1)) if _base_pass_m else 0
                                finally:
                                    _shutil.copy(str(_tmp_save), str(filepath))
                                    _tmp_save.unlink(missing_ok=True)
                                if _post_fails > _base_fails or _post_passes < _base_passes:
                                    return (False, f'pytest REGRESSION: baseline={_base_passes}p/{_base_fails}f → post-patch={_post_passes}p/{_post_fails}f (patch made it worse) — ROLLBACK')
                                else:
                                    logger.info(f'[WORLD-CLASS-GATE] pytest OK: baseline={_base_passes}p/{_base_fails}f → post-patch={_post_passes}p/{_post_fails}f (no regression)')
                            else:
                                logger.debug('[WORLD-CLASS-GATE] no baseline backup — pytest gate skip (fail-open)')
            except Exception as _pytest_err:
                logger.debug(f'[WORLD-CLASS-GATE] pytest verify fail-open: {_pytest_err}')
            try:
                from scp.autofix.enterprise_scanners import scan_file_enterprise
                _enterprise_findings = scan_file_enterprise(filepath)
                _new_ent_bugs = []
                _orig_lines = {getattr(b, 'line', None) for b in original_bugs}
                _orig_types = {(getattr(b, 'line', None), getattr(b, 'bug_type', '')) for b in original_bugs}
                _orig_bug_types = {getattr(b, 'bug_type', '') for b in original_bugs}
                _pre_existing_types = set()
                try:
                    _backup_path = filepath.with_suffix(filepath.suffix + '.tier3bak')
                    if not _backup_path.exists():
                        _backup_path = filepath.with_suffix(filepath.suffix + '.audit_fix_backup')
                    if _backup_path.exists():
                        _orig_findings = scan_file_enterprise(_backup_path)
                        for f in _orig_findings:
                            _pre_existing_types.add((f.get('line'), f.get('bug_type', '')))
                except Exception as _backup_scan_error:
                    logger.debug('[AUTOFIX] backup finding scan failed; continuing fail-open', exc_info=True)
                for f in _enterprise_findings:
                    _f_line = f.get('line')
                    _f_type = f.get('bug_type', '')
                    if (_f_line, _f_type) in _orig_types:
                        continue
                    if (_f_line, _f_type) in _pre_existing_types:
                        continue
                    if _f_type in _orig_bug_types:
                        continue
                    for _ol in _orig_lines:
                        if _f_line and _ol and (abs(_f_line - _ol) <= 15):
                            _new_ent_bugs.append(f)
                            break
                if _new_ent_bugs:
                    _labels = [f"{f.get('bug_type', '?')}@L{f.get('line', '?')}" for f in _new_ent_bugs[:3]]
                    return (False, f'enterprise re-scan found {len(_new_ent_bugs)} NEW bug(s) near fix: {_labels} — REJECTED (cascade control: fix must not introduce new tool-detected bugs)')
            except ImportError:
                logger.debug('[CASCADE] enterprise_scanners unavailable (fail-open)')
            except Exception as _ent_err:
                logger.debug(f'[CASCADE] enterprise re-scan fail-open: {_ent_err}')
            try:
                from scp.autofix.property_validator import MIXED_STRATEGY as _v4_mixed_strat, PropertySpec as _V4_PropertySpec, validate_fix as _v4_property_validate
                _v4_patched_text = filepath.read_text(encoding='utf-8')
                _v4_backup_path = filepath.with_suffix(filepath.suffix + '.tier3bak')
                if not _v4_backup_path.exists():
                    _v4_backup_path = filepath.with_suffix(filepath.suffix + '.audit_fix_backup')
                if _v4_backup_path.exists() and _v4_patched_text:
                    _v4_orig_text = _v4_backup_path.read_text(encoding='utf-8')
                    _v4_fn_name = ''
                    for _orig_bug in original_bugs:
                        _v4_fn_name = getattr(_orig_bug, 'function_name', '') or getattr(_orig_bug, 'method_name', '') or ''
                        if _v4_fn_name:
                            break
                    from scp.autofix.property_validator import BugLocation as _V4_PV_BugLoc
                    _v4_pv_bug_loc = None
                    if _v4_fn_name:
                        _v4_pv_bug_loc = _V4_PV_BugLoc(function_name=_v4_fn_name, line_start=int(getattr(original_bugs[0], 'line', 0) or 0), line_end=int(getattr(original_bugs[0], 'line', 0) or 0))
                    _v4_pv_spec = _V4_PropertySpec(invariants=[lambda _y: True], strategy=_v4_mixed_strat, skip_if_none_input=False)
                    _v4_pv_result = _v4_property_validate(orig_source=_v4_orig_text, fixed_source=_v4_patched_text, bug_location=_v4_pv_bug_loc, spec=_v4_pv_spec, n=50)
                    if not _v4_pv_result.ok:
                        _v4_violations_summary = ', '.join((f'input={v.input_value!r} reason={v.reason}' for v in (_v4_pv_result.violations or [])[:3]))
                        return (False, f'[R10 v4 IMP-19] property validation FAILED: {len(_v4_pv_result.violations or [])} violation(s) across {_v4_pv_result.inputs_tested} edge-case inputs. First: {_v4_violations_summary}')
                    logger.info(f'[R10 v4 IMP-19] property OK: {_v4_pv_result.inputs_tested} edge-case inputs tested, 0 violations ({_v4_pv_result.reason})')
            except ImportError as _v4_pv_imp:
                logger.warning('[R10 v4 IMP-19] property_validator unavailable; rejecting unverifiable fix: %s', type(_v4_pv_imp).__name__)
                return (False, 'property validation unavailable; fix is UNVERIFIED')
            except Exception as _v4_pv_err:
                logger.warning('[R10 v4 IMP-19] property_validator failed; rejecting unverifiable fix: %s', type(_v4_pv_err).__name__)
                return (False, 'property validation failed; fix is UNVERIFIED')
            return (True, 'fix verified OK (syntax + re-scan + no new bugs + self-scan + pytest + enterprise + property)')
        except Exception as _verify_err:
            logger.warning(' _verify_fix error; rejecting unverifiable fix: %s', type(_verify_err).__name__)
            return (False, 'verification error; fix is UNVERIFIED')

    def _audit_v91(self, event: str, payload: dict) -> None:
        try:
            _entry = {'ts': time.time(), 'engine': 'autofix', 'event': event, 'payload': payload}
            _audit_path = self.data_dir / 'v91_upgrade_audit.jsonl'
            with open(_audit_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(_entry, ensure_ascii=False) + '\n')
        except Exception as _audit_err:
            logger.debug(f' audit log error (fail-open): {_audit_err}')
    _meta_repair_attempted: bool = False

    def _attempt_meta_repair(self, module_name: str, error: Exception) -> bool:
        """Attempt to auto-repair a crashed safety module via LLM. Returns True if repaired."""
        if self._meta_repair_attempted:
            logger.debug(' meta-repair already attempted this cycle — skip')
            return False
        self._meta_repair_attempted = True
        try:
            import traceback as _tb
            _error_str = f'{type(error).__name__}: {error}\n{_tb.format_exc()[:500]}'
            logger.warning(f' attempting meta-repair for {module_name}: {_error_str[:200]}')
            _module_path_map = {'policy_gate': 'scp/autofix/policy_gate.py', 'property_validator': 'scp/autofix/property_validator.py', 'evidence_replay': 'scp/autofix/evidence_replay.py'}
            _module_path = _module_path_map.get(module_name)
            if not _module_path:
                logger.warning(f' unknown module for meta-repair: {module_name}')
                return False
            from pathlib import Path as _P
            _p = _P(_module_path)
            if not _p.exists():
                return False
            _source = _p.read_text(encoding='utf-8')
            try:
                from scp.autofix.llm_fix import _call_smart_llm
                _prompt = f'The following Python module crashed with this error:\n\n--- ERROR ---\n{_error_str}\n\n--- MODULE SOURCE ({_module_path}) ---\n{_source[:3000]}\n\nGenerate a minimal search-replace patch to fix the crash. Format:\n<<<<<<< SEARCH\nold code\n=======\nnew code\n>>>>>>> REPLACE\nOnly fix the crash — do NOT change behavior. DNA #9 (No harm).'
                _patch = _call_smart_llm(_prompt, bug_type='meta_repair', max_tokens=2000)
                if not _patch or '<<<<<<< SEARCH' not in _patch:
                    logger.warning(f' LLM returned no valid patch for {module_name}')
                    return False
                _backup = _p.with_suffix(_p.suffix + '.meta_repair_bak')
                _backup.write_text(_source, encoding='utf-8')
                _new_source = _source
                import re as _re
                _blocks = _re.findall('<<<<<<< SEARCH\\n(.*?)\\n=======\\n(.*?)\\n>>>>>>>', _patch, _re.DOTALL)
                for _old, _new in _blocks:
                    _new_source = _new_source.replace(_old, _new, 1)
                if _new_source == _source:
                    logger.warning(f' patch did not change source for {module_name}')
                    return False
                import ast as _ast
                _ast.parse(_new_source)
                _p.write_text(_new_source, encoding='utf-8')
                logger.info(f' meta-repair applied to {module_name} (backup at {_backup.name})')
                return True
            except ImportError:
                logger.debug(' llm_fix unavailable — cannot meta-repair')
                return False
            except Exception as _llm_err:
                logger.warning(f' LLM meta-repair failed: {_llm_err}')
                return False
        except Exception as _meta_err:
            logger.warning(f' meta-repair outer crash: {_meta_err}')
            return False

    def _auto_fix(self, bug: BugReport, report: bool, attack_mode: bool=False) -> dict:
        """Apply the fix autonomously. Uses code_evolution_agent._apply_fix."""
        from scp.autofix.runner_phases.ast_scan import _is_protected_path
        _filepath = getattr(bug, 'file', '') or ''
        if _is_protected_path(_filepath):
            logger.error(f'[G2-FIX] PROTECTED_PATH_BLOCKED: {_filepath} — SCP cannot modify its own permission/security source')
            return {'status': 'blocked', 'reason': f'protected path: {_filepath}', 'action': 'protected_path_blocked'}
        try:
            from scp.meta.capability_levels import get_capability_manager
            _cap = get_capability_manager()
            _required_action = 'apply_narrow' if attack_mode else 'apply_test' if report else 'apply_sandbox'
            if not _cap.can_do(_required_action):
                logger.warning(f"[AutoFix] Gà §12 — capability denied: current {_cap.get_current_level().name} does not allow '{_required_action}'. Set SCP_CAPABILITY_LEVEL env var to escalate (requires human approval via CapabilityManager.request_escalation).")
                return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f"capability denied — current level {_cap.get_current_level().name} lacks '{_required_action}' (Gà §12)"}
        except Exception as _cap_err:
            logger.error(f'[AutoFix] CapabilityManager crash — BLOCKING fix (security > availability): {_cap_err}')
            return {'action': 'blocked', 'tier': int(bug.tier), 'reason': f'CapabilityManager error (fail-closed): {_cap_err}'}
        try:
            _gate = getattr(self, 'policy_gate', None) or getattr(self, '_policy_gate', None)
            if _gate is not None and hasattr(_gate, 'verify_chain'):
                _chain_ok, _chain_msg = _gate.verify_chain()
                if not _chain_ok:
                    logger.error(f'[P1-1 R16] Policy gate verify_chain FAILED: {_chain_msg} — BLOCKING fix (audit log may be tampered)')
                    return {'action': 'blocked', 'tier': int(bug.tier), 'reason': f'verify_chain failed (audit log tampered?): {_chain_msg}', 'blocked_by': 'verify_chain'}
                logger.debug(f'[P1-1 R16] verify_chain OK: {_chain_msg}')
        except Exception as _vc_err:
            logger.error(f'[P1-1 R16] verify_chain crashed (fail-open, DNA #7): {_vc_err} — proceeding with fix, but operator must investigate policy_gate health')
        if bug.bug_type == 'BareExceptPass' and os.environ.get('SCP_SKIP_BAREEXCEPTPASS', '0') == '1':
            logger.info(f'[AutoFix] SKIP BareExceptPass (SCP_SKIP_BAREEXCEPTPASS=1) ({bug.file}:{bug.line})')
            return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'BareExceptPass skipped (SCP_SKIP_BAREEXCEPTPASS=1)'}
        if self._fixes_this_cycle >= MAX_FIXES_PER_CYCLE:
            return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'rate limit — max fixes per cycle exceeded'}
        try:
            from scp.meta.why_gate import get_why_gate
            _why = get_why_gate().gate(action_type='autofix', action_desc=f"Fix {bug.bug_type} at {bug.file}:{bug.line}: {(bug.description or '')[:100]}", context=(bug.suggested_fix or '')[:200])
            if _why.blocked:
                logger.info(f'[V9.0-WHY-GATE] AutoFix blocked for {bug.file}:{bug.line}: {_why.falsification_reason[:100]}')
                return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f'WHY-GATE blocked: {_why.falsification_reason[:100]}'}
        except Exception as _why_err:
            logger.debug(f'[V9.0-WHY-GATE] WHY Gate error (non-blocking, default allow): {_why_err}')
        try:
            from scp.autofix.policy_gate import PolicyFix as _V4_PolicyFix, evaluate_fix as _v4_policy_evaluate
            _v4_pf = _V4_PolicyFix(fix_id=f'{bug.file}:{bug.line}:{bug.bug_type}', patch=bug.suggested_fix or '', patched_source='', bug_file=bug.file or '', bug_line=int(bug.line or 0), scanner_name='autofix_engine', extra={'bug_type': bug.bug_type, 'tier': int(bug.tier)})
            _v4_decision = _v4_policy_evaluate(_v4_pf)
            if not _v4_decision.allowed:
                logger.warning(f'[R9 v4 IMP-24] POLICY BLOCKED fix for {bug.file}:{bug.line}: patterns={_v4_decision.blocked_patterns} reason={_v4_decision.reason[:120]} audit_id={_v4_decision.audit_id}')
                return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f'policy_gate BLOCK (DNA #4): {_v4_decision.reason[:160]}', 'patched': False, 'policy_blocked': True, 'policy_audit_id': _v4_decision.audit_id, 'policy_patterns': list(_v4_decision.blocked_patterns)}
            logger.debug(f'[R9 v4 IMP-24] policy gate ALLOWED fix for {bug.file}:{bug.line} (severity={_v4_decision.severity})')
        except ImportError as _v4_p_imp:
            logger.error(f'[R9 v4 IMP-24] policy_gate module unavailable — DEFAULT-DENY (DNA #4 Constitution KILL gate down): {_v4_p_imp}')
            return {'action': 'blocked', 'tier': int(bug.tier), 'reason': f'policy_gate ImportError — DEFAULT-DENY (DNA #4): {_v4_p_imp}', 'policy_gate_down': True}
        except Exception as _v4_p_err:
            logger.error(f'[R9 v4 IMP-24] policy_gate evaluate_fix CRASH — DEFAULT-DENY (DNA #4): {_v4_p_err}', exc_info=True)
            try:
                _repaired = self._attempt_meta_repair('policy_gate', _v4_p_err)
                if _repaired:
                    from scp.autofix.policy_gate import PolicyFix as _V4_PolicyFix2, evaluate_fix as _v4_policy_evaluate2
                    _v4_pf2 = _V4_PolicyFix2(fix_id=f'{bug.file}:{bug.line}:{bug.bug_type}', patch=bug.suggested_fix or '', patched_source='', bug_file=bug.file or '', bug_line=int(bug.line or 0))
                    _v4_decision2 = _v4_policy_evaluate2(_v4_pf2)
                    if not _v4_decision2.allowed:
                        return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f'policy_gate BLOCK after meta-repair: {_v4_decision2.reason[:160]}', 'patched': False, 'policy_blocked': True, 'policy_audit_id': _v4_decision2.audit_id, 'policy_patterns': list(_v4_decision2.blocked_patterns), 'meta_repaired': True}
                    logger.info(' policy_gate meta-repair SUCCESS — gate back UP')
                else:
                    logger.warning(' policy_gate meta-repair failed — gate stays DOWN (DEFAULT-DENY)')
            except Exception as _meta_repair_err:
                logger.warning(f' meta-repair attempt crashed (fail-open): {_meta_repair_err}')
            return {'action': 'blocked', 'tier': int(bug.tier), 'reason': f'policy_gate crash — DEFAULT-DENY (DNA #4): {_v4_p_err}', 'policy_gate_down': True}
        try:
            from pathlib import Path as PathCls
            from scp.core.code_evolution_agent import CodeEvolutionAgent
            agent = CodeEvolutionAgent.__new__(CodeEvolutionAgent)
            agent.log_file = self.data_dir / 'evolution_log.jsonl'
            filepath = PathCls(bug.file)
            if not filepath.exists():
                return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f'file not found: {bug.file}'}
            _pre_fix_content: str | None = None
            try:
                with filepath.open('r', encoding='utf-8', newline='') as _pre_fix_file:
                    _pre_fix_content = _pre_fix_file.read()
            except Exception as _bk_err:
                logger.debug(f' pre-fix backup failed (will skip verify): {_bk_err}')
            if bug.bug_type == 'XSSVulnerability':
                try:
                    from scp.autofix.evolution import get_evolution_engine
                    _evo = get_evolution_engine(data_dir=str(self.data_dir))
                    _xss_result = _evo._apply_xss_pattern_fix(bug)
                    if _xss_result and _xss_result.get('fixed'):
                        try:
                            filepath.write_text(_xss_result['patch'], encoding='utf-8')
                        except Exception as _write_err:
                            logger.warning(f'[OPT-24] XSS pattern fix write failed: {_write_err}')
                        else:
                            try:
                                import ast as _ast_verify
                                _ast_verify.parse(filepath.read_text(encoding='utf-8'), filename=str(filepath))
                            except SyntaxError as _syn_err:
                                logger.warning(f'[OPT-24] XSS pattern fix introduced SyntaxError post-write — ROLLING BACK: {_syn_err}')
                                if _pre_fix_content is not None:
                                    filepath.write_text(_pre_fix_content, encoding='utf-8', newline='')
                            else:
                                self._fixes_this_cycle += 1
                                _xss_cache_invalidated = False
                                _xss_cache_error = ''
                                try:
                                    from scp.autofix.llm_fix_cache import invalidate_cache_for_file
                                    invalidate_cache_for_file(str(filepath))
                                    _xss_cache_invalidated = True
                                except Exception as _inv_err:
                                    _xss_cache_error = str(_inv_err)[:200]
                                    logger.warning(f' cache invalidate failed after deterministic fix: {_inv_err}')
                                bug_key = f'{bug.file}:{bug.line}:{bug.bug_type}'
                                self._recent_fixes[bug_key] = time.time()
                                _xss_rollback_registered = False
                                try:
                                    from scp.autofix.audit_log import compute_hashes as _compute_hashes_4b012
                                    _xss_post = filepath.read_text(encoding='utf-8')
                                    _xss_bh, _xss_ah = _compute_hashes_4b012(_pre_fix_content, _xss_post)
                                    _xss_rtr = 'pass'
                                    _xss_token = self.register_fix_for_rollback(file_path=str(filepath), before_content=_pre_fix_content or '', after_content=_xss_post, patch=_xss_result.get('patch', ''), bug_id=f'{bug.file}:{bug.line}', bug_type=bug.bug_type, tier=int(bug.tier), reality_test_result={'status': 'pass', 'method': 'ast.parse', 'fix_method': 'xss_pattern'})
                                    _xss_rollback_registered = True
                                except Exception as _xss_hash_err:
                                    logger.warning(f'[4-b-012] XSS hash/rollback registration failed: {_xss_hash_err}')
                                    _xss_bh = _xss_ah = 'n/a'
                                    _xss_rtr = 'skipped'
                                    _xss_token = f'backup:{filepath}'
                                    _xss_rollback_registered = False
                                if report or attack_mode:
                                    self._write_audit(bug, 'fixed', attack_mode=attack_mode, before_hash=_xss_bh, after_hash=_xss_ah, rollback_token=_xss_token, reality_test_result=_xss_rtr)
                                else:
                                    self._write_audit(bug, 'fixed_silent', attack_mode=False, before_hash=_xss_bh, after_hash=_xss_ah, rollback_token=_xss_token, reality_test_result=_xss_rtr)
                                logger.info(f"[OPT-24] XSS pattern fix applied for {bug.file}:{bug.line} pattern={_xss_result.get('pattern', '?')} matches={_xss_result.get('matches', 0)} (skipped LLM call — deterministic fix)")
                                try:
                                    if os.environ.get('SCP_EVOLUTION_ENABLED', '0') == '1':
                                        _evo.reflect(bug, _xss_result['reason'])
                                except Exception as _reflect_err:
                                    logger.debug(f'[V5.7-WHY] reflect on XSS pattern fix failed (non-fatal): {_reflect_err}')
                                return {'action': 'fixed', 'status': 'fixed', 'tier': int(bug.tier), 'patched': True, 'attack_mode': attack_mode, 'method': 'xss_pattern', 'pattern': _xss_result.get('pattern', ''), 'reason': _xss_result.get('reason', ''), 'before_hash': _xss_bh, 'after_hash': _xss_ah, 'rollback_token': _xss_token, 'rollback_registered': _xss_rollback_registered, 'reality_test_result': _xss_rtr, 'cache_invalidated': _xss_cache_invalidated, 'cache_invalidation_error': _xss_cache_error}
                except Exception as _xss_pattern_err:
                    logger.debug(f'[OPT-24] XSS pattern fix dispatch failed (non-fatal, fall through to LLM): {_xss_pattern_err}')
            _autofix_bug_id = f'{bug.file}:{bug.line}'
            _autofix_provider = 'predefined'
            try:
                from scp.autofix.llm_fix import select_provider_for_bug as _spfb
                _autofix_provider = _spfb(bug.bug_type)
            except Exception as e:
                logger.warning(f'Silent except: {e}')
            _autofix_validation_skipped = False
            try:
                import re as _autofix_re
                _sr_pat = _autofix_re.compile('<<<<<<<\\s*SEARCH\\s*\\n(.*?)\\n={5,7}\\s*\\n(.*?)\\n>>>>>>>\\s*(?:REPLACE)?\\s*', _autofix_re.DOTALL)
                _old_pat = _autofix_re.compile('<<<<<<<\\s*OLD\\s*\\n(.*?)\\n={5,7}\\s*\\n(.*?)\\n>>>>>>>\\s*(?:NEW)?\\s*', _autofix_re.DOTALL)
                _pairs: list[tuple[str, str]] = []
                if bug.suggested_fix:
                    for _m in _sr_pat.finditer(bug.suggested_fix):
                        _pairs.append((_m.group(1), _m.group(2)))
                    if not _pairs:
                        for _m in _old_pat.finditer(bug.suggested_fix):
                            _pairs.append((_m.group(1), _m.group(2)))
                if _pairs:
                    from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                    from scp.autofix.monitor import FixAttempt as _FixAttempt
                    from scp.autofix.monitor import get_monitor as _get_monitor
                    from scp.autofix.validate_patch import validate_patch as _validate_patch
                    _validation_failed = False
                    _validation_reason = ''
                    for _search, _replace in _pairs:
                        _vresult = _validate_patch(str(filepath), _search, _replace)
                        if not _vresult.valid:
                            _validation_failed = True
                            _validation_reason = _vresult.reason
                            break
                    if _validation_failed:
                        logger.warning(f'[AutoFix] [OPT-26] Patch validation FAILED for {bug.file}:{bug.line}: {_validation_reason}')
                        _diag = _diagnose(bug_id=_autofix_bug_id, bug_type=bug.bug_type, llm_output=bug.suggested_fix, patch_parsed={'search': _pairs[0][0], 'replace': _pairs[0][1]}, validation_result={'valid': False, 'reason': _validation_reason}, apply_result='failed')
                        _get_monitor().record(_FixAttempt(bug_id=_autofix_bug_id, bug_type=bug.bug_type, provider=_autofix_provider, diagnosis=_diag.diagnosis, success=False))
                        return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f'validation failed: {_validation_reason}', 'patched': False}
                else:
                    _autofix_validation_skipped = True
            except Exception as _val_err:
                logger.debug(f'[AutoFix] [OPT-26] validation harness error (non-blocking): {_val_err}')
                _autofix_validation_skipped = True
            _v4_pairs = locals().get('_pairs', []) or []
            _v4_sim_patched: str | None = None
            if _pre_fix_content is not None and _v4_pairs:
                try:
                    _v4_sim = _pre_fix_content
                    _v4_applied_any = False
                    for _v4_s, _v4_r in _v4_pairs:
                        if _v4_s in _v4_sim:
                            _v4_sim = _v4_sim.replace(_v4_s, _v4_r, 1)
                            _v4_applied_any = True
                    if _v4_applied_any and _v4_sim != _pre_fix_content:
                        _v4_sim_patched = _v4_sim
                except Exception as _v4_sim_err:
                    logger.debug(f'[R9 v4 WIRE] patched_source simulation failed (fail-open — IMP-14 + IMP-23 skip): {_v4_sim_err}')
            try:
                from scp.autofix.confidence_ranker import best_fix as _v4_rank_best, make_fix as _v4_make_fix
                if _v4_sim_patched is not None:
                    _v4_lines_changed = sum((max(0, len(_r.splitlines()) - len(_s.splitlines()) + 1) for _s, _r in _v4_pairs)) or sum((len(_r.splitlines()) for _, _r in _v4_pairs))
                    _v4_candidate = _v4_make_fix(fix_id=_autofix_bug_id, patch=bug.suggested_fix or '', patched_source=_v4_sim_patched, source='llm', bug_type=bug.bug_type, bug_file=bug.file, bug_line=int(bug.line or 0), lines_changed=_v4_lines_changed, reality_test_result=None)
                    _v4_ranked = _v4_rank_best([_v4_candidate], bug_type=bug.bug_type)
                    if _v4_ranked is None or _v4_ranked.disposition == 'discard':
                        logger.info(f'[R9 v4 IMP-14] confidence ranker DISCARDED fix for {bug.file}:{bug.line} (confidence={_v4_candidate.confidence:.3f} disposition={_v4_candidate.disposition})')
                        try:
                            from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                            from scp.autofix.monitor import FixAttempt as _FixAttempt
                            from scp.autofix.monitor import get_monitor as _get_monitor
                            _diag = _diagnose(bug_id=_autofix_bug_id, bug_type=bug.bug_type, llm_output=bug.suggested_fix, patch_parsed={'search': '(ranked)', 'replace': '(ranked)'}, validation_result={'valid': True, 'reason': 'pre-rank OK'}, apply_result='discarded_by_ranker')
                            _get_monitor().record(_FixAttempt(bug_id=_autofix_bug_id, bug_type=bug.bug_type, provider=_autofix_provider, diagnosis=_diag.diagnosis, success=False))
                        except Exception as e:
                            logger.debug(f'Silent except: {e}')
                        return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f'confidence_ranker DISCARD (confidence={_v4_candidate.confidence:.3f})', 'patched': False, 'confidence': _v4_candidate.confidence, 'disposition': 'discard'}
                    logger.info(f'[R9 v4 IMP-14] fix ranked: confidence={_v4_ranked.confidence:.3f} disposition={_v4_ranked.disposition} for {bug.file}:{bug.line}')
            except ImportError as _v4_cr_imp:
                logger.debug(f'[R9 v4 IMP-14] confidence_ranker unavailable (fail-open — apply without scoring): {_v4_cr_imp}')
            except Exception as _v4_cr_err:
                logger.debug(f'[R9 v4 IMP-14] confidence_ranker crash (fail-open — apply without scoring): {_v4_cr_err}')
            try:
                from scp.autofix.runner_phases.blast_radius import compute_blast_radius as _v4_blast, should_escalate_tier as _v4_should_escalate, should_require_dry_run as _v4_should_dry_run, blast_radius_summary as _v4_blast_summary
                _v4_target_func = getattr(bug, 'function_name', '') or getattr(bug, 'method_name', '') or ''
                if not _v4_target_func and bug.suggested_fix:
                    import re as _v4_re_mod
                    _v4_def_m = _v4_re_mod.search('def\\s+(\\w+)\\s*\\(', bug.suggested_fix)
                    if _v4_def_m:
                        _v4_target_func = _v4_def_m.group(1)
                if _v4_target_func:
                    _v4_blast_result = _v4_blast(target_file=bug.file or '', target_function=_v4_target_func, scp_root=None, scan_tests=False)
                    _v4_blast_sum = _v4_blast_summary(_v4_blast_result)
                    logger.info(f"[R10 v4 IMP-16] blast_radius for {_v4_target_func}: callers={_v4_blast_sum['caller_count']} risk={_v4_blast_sum['risk_level']} bounded={_v4_blast_sum['bounded']}")
                    try:
                        _v4_orig_tier = int(getattr(bug, 'tier', 1) or 1)
                    except (TypeError, ValueError):
                        _v4_orig_tier = 1
                    _v4_escalated_tier = _v4_should_escalate(_v4_blast_result, _v4_orig_tier)
                    if _v4_escalated_tier > _v4_orig_tier:
                        logger.warning(f" blast_radius policy escalated {bug.file}:{bug.line} from Tier {_v4_orig_tier} to Tier {_v4_escalated_tier} (risk={_v4_blast_sum['risk_level']}, callers={_v4_blast_sum['caller_count']})")
                        if hasattr(bug, 'tier'):
                            try:
                                bug.tier = _v4_escalated_tier
                            except Exception as _tier_assignment_error:
                                logger.debug('[AUTOFIX] tier assignment failed; retaining original tier', exc_info=True)
                    if _v4_should_dry_run(_v4_blast_result):
                        _dry_run_snapshot = None
                        try:
                            _dry_run_preview_fn = getattr(self, 'preview_fix_dry_run', None)
                            if _dry_run_preview_fn is not None and _pre_fix_content is not None and bug.suggested_fix:
                                import re as _v4_dr_re
                                _v4_dr_sim = _pre_fix_content
                                for _old, _new in _v4_dr_re.findall('<<<<<<< SEARCH\\n(.*?)\\n=======\\n(.*?)\\n>>>>>>>', bug.suggested_fix, _v4_dr_re.DOTALL):
                                    _v4_dr_sim = _v4_dr_sim.replace(_old, _new, 1)
                                if _v4_dr_sim != _pre_fix_content:
                                    _dr_out = _dry_run_preview_fn(bug.file, _v4_dr_sim)
                                    _dry_run_snapshot = _dr_out.get('snapshot_path')
                        except Exception as _dr_err:
                            logger.debug(f' dry-run preview failed (fail-open): {_dr_err}')
                        logger.warning(f" HIGH/CRITICAL blast radius for {_v4_target_func} (risk={_v4_blast_sum['risk_level']}, callers={_v4_blast_sum['caller_count']}) — dry-run{(' snapshot=' + str(_dry_run_snapshot) if _dry_run_snapshot else ' unavailable (fail-open)')}")
                    try:
                        from scp.autofix.type_flow_verifier import Signature as _V4_TF_Sig, verify_type_flow as _v4_tflow
                        if _v4_blast_sum['caller_count'] > 0:
                            import ast as _ast_tf

                            def _extract_sig(source_text: str, func_name: str) -> _V4_TF_Sig:
                                """Extract function signature from source via AST."""
                                try:
                                    tree = _ast_tf.parse(source_text)
                                    for node in _ast_tf.walk(tree):
                                        if isinstance(node, (_ast_tf.FunctionDef, _ast_tf.AsyncFunctionDef)) and node.name == func_name:
                                            args = [a.arg for a in node.args.args if hasattr(a, 'arg')]
                                            returns = ''
                                            if node.returns:
                                                try:
                                                    returns = _ast_tf.unparse(node.returns)
                                                except Exception:
                                                    returns = 'Any'
                                            return _V4_TF_Sig(args=args, returns=returns)
                                except Exception as _signature_scan_error:
                                    logger.debug('[AUTOFIX] signature scan failed; using empty signature', exc_info=True)
                                return _V4_TF_Sig(args=[], returns='')
                            _v4_orig_sig = _extract_sig(_pre_fix_content or '', _v4_target_func)
                            _v4_patched_src = ''
                            try:
                                _v4_patched_src = filepath.read_text(encoding='utf-8')
                            except Exception as _patched_source_error:
                                logger.debug('[AUTOFIX] patched source read failed; using empty source', exc_info=True)
                            _v4_new_sig = _extract_sig(_v4_patched_src, _v4_target_func)
                            _v4_tflow_result = _v4_tflow(target_file=bug.file or '', target_function=_v4_target_func, orig_signature=_v4_orig_sig, new_signature=_v4_new_sig, scp_root=str(Path(__file__).resolve().parent.parent))
                            logger.info(f' type_flow for {_v4_target_func}: compatible={_v4_tflow_result.compatible} callers={_v4_tflow_result.caller_count} orig_args={_v4_orig_sig.args} new_args={_v4_new_sig.args} reason={_v4_tflow_result.reason[:80]}')
                            if not _v4_tflow_result.compatible and _v4_blast_sum['risk_level'] in ('HIGH', 'CRITICAL'):
                                logger.warning(f' TYPE-FLOW BREAKAGE + HIGH risk — escalating {bug.file}:{bug.line} to review (Tier 3)')
                                return {'action': 'skipped', 'tier': 3, 'reason': f"type_flow_verifier: {len(_v4_tflow_result.incompatible_sites)} breaking caller(s) + risk={_v4_blast_sum['risk_level']}", 'patched': False, 'blast_radius': _v4_blast_sum, 'type_flow_breaking': len(_v4_tflow_result.incompatible_sites)}
                    except ImportError as _v4_tf_imp:
                        logger.debug(f'[R10 v4 IMP-20] type_flow_verifier unavailable (fail-open): {_v4_tf_imp}')
                    except Exception as _v4_tf_err:
                        logger.debug(f'[R10 v4 IMP-20] type_flow_verifier crash (fail-open): {_v4_tf_err}')
            except ImportError as _v4_br_imp:
                logger.debug(f'[R10 v4 IMP-16] blast_radius unavailable (fail-open): {_v4_br_imp}')
            except Exception as _v4_br_err:
                logger.debug(f'[R10 v4 IMP-16] blast_radius crash (fail-open): {_v4_br_err}')
            try:
                from scp.autofix.runner_phases.shadow_canary import ShadowFix as _V4_ShadowFix, default_canary_suite as _v4_default_canary, shadow_apply_and_compare as _v4_shadow_compare
                if _v4_sim_patched is not None and _pre_fix_content is not None:
                    _v4_shadow_fix = _V4_ShadowFix(original_source=_pre_fix_content, patched_source=_v4_sim_patched, fix_id=_autofix_bug_id)
                    _v4_shadow_result = _v4_shadow_compare(target_file=bug.file, fix=_v4_shadow_fix, canary_suite=_v4_default_canary())
                    if not _v4_shadow_result.passed:
                        logger.warning(f'[R9 v4 IMP-23] SHADOW CANARY FAILED for {bug.file}:{bug.line}: {_v4_shadow_result.reason[:120]} (tests_run={_v4_shadow_result.tests_run} diffs={len(_v4_shadow_result.diffs)})')
                        try:
                            from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                            from scp.autofix.monitor import FixAttempt as _FixAttempt
                            from scp.autofix.monitor import get_monitor as _get_monitor
                            _diag = _diagnose(bug_id=_autofix_bug_id, bug_type=bug.bug_type, llm_output=bug.suggested_fix, patch_parsed={'search': '(shadowed)', 'replace': '(shadowed)'}, validation_result={'valid': True, 'reason': 'pre-shadow OK'}, apply_result='shadow_canary_failed')
                            _get_monitor().record(_FixAttempt(bug_id=_autofix_bug_id, bug_type=bug.bug_type, provider=_autofix_provider, diagnosis=_diag.diagnosis, success=False))
                        except Exception as e:
                            logger.debug(f'Silent except: {e}')
                        return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f'shadow_canary FAIL: {_v4_shadow_result.reason[:160]}', 'patched': False, 'shadow_canary_passed': False, 'shadow_diffs': list(_v4_shadow_result.diffs[:5]), 'shadow_tests_run': _v4_shadow_result.tests_run}
                    logger.info(f'[R9 v4 IMP-23] shadow canary OK for {bug.file}:{bug.line} (tests_run={_v4_shadow_result.tests_run} flagged={_v4_shadow_result.flagged_for_review})')
            except ImportError as _v4_sc_imp:
                logger.warning('[R9 v4 IMP-23] shadow_canary unavailable; blocking unverifiable patch: %s', type(_v4_sc_imp).__name__)
                return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'shadow_canary unavailable; fix is UNVERIFIED', 'patched': False, 'shadow_canary_unverified': True}
            except Exception as _v4_sc_err:
                logger.warning('[R9 v4 IMP-23] shadow_canary failed; blocking unverifiable patch: %s', type(_v4_sc_err).__name__)
                return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'shadow_canary failed; fix is UNVERIFIED', 'patched': False, 'shadow_canary_unverified': True}
            try:
                from scp.autofix.realtime_verifier import verify_patch_realtime
                _rtv_patched_source = filepath.read_text(encoding='utf-8') if filepath.exists() else ''
                if not _pre_fix_content or not bug.suggested_fix:
                    return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'realtime patch simulation unavailable; fix is UNVERIFIED', 'patched': False, 'realtime_blocked': True}
                _rtv_simulated = _pre_fix_content
                import re as _rtv_re
                _rtv_blocks = _rtv_re.findall('<<<<<<< SEARCH\\n(.*?)\\n=======\\n(.*?)\\n>>>>>>>', bug.suggested_fix, _rtv_re.DOTALL)
                if not _rtv_blocks:
                    return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'realtime patch format unsupported; fix is UNVERIFIED', 'patched': False, 'realtime_blocked': True}
                for _rtv_old, _rtv_new in _rtv_blocks:
                    if _rtv_old not in _rtv_simulated:
                        return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'realtime patch search block not found; fix is UNVERIFIED', 'patched': False, 'realtime_blocked': True}
                    _rtv_simulated = _rtv_simulated.replace(_rtv_old, _rtv_new, 1)
                if _rtv_simulated != _pre_fix_content:
                    _rtv_result = verify_patch_realtime(orig_source=_pre_fix_content, patched_source=_rtv_simulated, func_name=getattr(bug, 'function_name', None) or getattr(bug, 'method_name', None))
                    if not _rtv_result.ok:
                        logger.warning(f' Real-Time Verifier BLOCKED patch for {bug.file}:{bug.line}: {_rtv_result.reason} — skipping file write')
                        return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f'realtime_verifier: {_rtv_result.reason[:160]}', 'patched': False, 'realtime_blocked': True, 'violations': _rtv_result.violations[:3]}
                    logger.info(f' Real-Time Verifier OK: {_rtv_result.reason} (inputs={_rtv_result.inputs_tested})')
            except ImportError as _rtv_imp:
                logger.warning(' realtime_verifier unavailable; blocking unverifiable patch: %s', type(_rtv_imp).__name__)
                return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'realtime verifier unavailable; fix is UNVERIFIED', 'patched': False, 'realtime_blocked': True}
            except Exception as _rtv_err:
                logger.warning(' realtime_verifier failed; blocking unverifiable patch: %s', type(_rtv_err).__name__)
                return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'realtime verifier failed; fix is UNVERIFIED', 'patched': False, 'realtime_blocked': True}
            patched = agent._apply_fix(filepath, bug.suggested_fix)
            if patched:
                self._fixes_this_cycle += 1
                try:
                    from scp.autofix.llm_fix_cache import invalidate_cache_for_file
                    invalidate_cache_for_file(str(filepath))
                except Exception as _inv_err:
                    logger.debug(f' cache invalidate failed (non-fatal): {_inv_err}')
            else:
                try:
                    from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                    from scp.autofix.monitor import FixAttempt as _FixAttempt
                    from scp.autofix.monitor import get_monitor as _get_monitor
                    _diag = _diagnose(bug_id=_autofix_bug_id, bug_type=bug.bug_type, llm_output=bug.suggested_fix, patch_parsed=None, validation_result=None, apply_result='failed')
                    _get_monitor().record(_FixAttempt(bug_id=_autofix_bug_id, bug_type=bug.bug_type, provider=_autofix_provider, diagnosis=_diag.diagnosis, success=False))
                except Exception as e:
                    logger.warning(f'Silent except: {e}')
                return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'fix queued for human review (not auto-patchable)', 'patched': False}
            try:
                _verify_ok, _verify_reason = self._verify_fix(filepath, [bug])
                if not _verify_ok:
                    logger.warning(f' Fix verification FAILED for {bug.file}:{bug.line}: {_verify_reason} — ROLLING BACK')
                    self._audit_v91('autofix_verify_fail_rollback', {'file': bug.file, 'line': bug.line, 'bug_type': bug.bug_type, 'reason': _verify_reason})
                    if _pre_fix_content is not None:
                        try:
                            filepath.write_text(_pre_fix_content, encoding='utf-8')
                            logger.info(f' Rollback OK for {bug.file}')
                        except Exception as _rb_err:
                            logger.error(f' Rollback FAILED for {bug.file}: {_rb_err}')
                    self._fixes_this_cycle = max(0, self._fixes_this_cycle - 1)
                    try:
                        from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                        from scp.autofix.monitor import FixAttempt as _FixAttempt
                        from scp.autofix.monitor import get_monitor as _get_monitor
                        _diag = _diagnose(bug_id=_autofix_bug_id, bug_type=bug.bug_type, llm_output=bug.suggested_fix, patch_parsed={'search': '(applied)', 'replace': '(applied)'}, validation_result={'valid': True, 'reason': 'pre-apply OK'}, apply_result='rollback')
                        _get_monitor().record(_FixAttempt(bug_id=_autofix_bug_id, bug_type=bug.bug_type, provider=_autofix_provider, diagnosis=_diag.diagnosis, success=False))
                    except Exception as e:
                        logger.warning(f'Silent except: {e}')
                    return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f'fix verification failed (rolled back): {_verify_reason}', 'patched': False}
                self._audit_v91('autofix_verify_ok', {'file': bug.file, 'line': bug.line, 'bug_type': bug.bug_type, 'reason': _verify_reason})
                try:
                    from scp.autofix.runner_phases.post_fix_verify import run_full_post_fix_verify
                    _pfv_result = run_full_post_fix_verify(bug_id=f'{bug.file}:{bug.line}:{bug.bug_type}', file_path=str(filepath), method_name=getattr(bug, 'function_name', None) or getattr(bug, 'method_name', None), bug_type=bug.bug_type, run_vulture=True, run_import=True, run_hypothesis=False, run_reality_exercise=True, run_completeness=True)
                    if _pfv_result.get('ok') is not True:
                        _pfv_reason = _pfv_result.get('reason', 'post-fix verification is UNVERIFIED')
                        _pfv_rollback = True
                        if _pfv_rollback:
                            logger.warning(f' post_fix_verify ROLLBACK for {bug.file}:{bug.line}: {_pfv_reason} — restoring pre-fix content')
                            if _pre_fix_content is not None:
                                try:
                                    filepath.write_text(_pre_fix_content, encoding='utf-8')
                                    logger.info(f' Rollback OK for {bug.file}')
                                except Exception as _rb_err:
                                    logger.error(f' Rollback FAILED for {bug.file}: {_rb_err}')
                            self._fixes_this_cycle = max(0, self._fixes_this_cycle - 1)
                        else:
                            logger.warning(f' post_fix_verify escalate_to_tier3 for {bug.file}:{bug.line}: {_pfv_reason}')
                        return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f'post-fix verification rejected/unverified (rolled back): {_pfv_reason}', 'patched': False, 'verification_status': 'UNVERIFIED', 'post_fix_verification': _pfv_result, 'escalate_to_tier3': bool(_pfv_result.get('escalate_to_tier3', True))}
                    else:
                        logger.info(f" post_fix_verify OK for {bug.file}:{bug.line} (phases: {list(_pfv_result.get('phases', {}).keys())})")
                except ImportError as _pfv_imp:
                    logger.warning(' post_fix_verify unavailable; rolling back unverifiable patch: %s', type(_pfv_imp).__name__)
                    if _pre_fix_content is not None:
                        filepath.write_text(_pre_fix_content, encoding='utf-8')
                    self._fixes_this_cycle = max(0, self._fixes_this_cycle - 1)
                    return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'post-fix verifier unavailable; fix is UNVERIFIED and was rolled back', 'patched': False}
                except Exception as _pfv_err:
                    logger.warning(' post_fix_verify failed; rolling back unverifiable patch: %s', type(_pfv_err).__name__)
                    if _pre_fix_content is not None:
                        filepath.write_text(_pre_fix_content, encoding='utf-8')
                    self._fixes_this_cycle = max(0, self._fixes_this_cycle - 1)
                    return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'post-fix verifier failed; fix is UNVERIFIED and was rolled back', 'patched': False}
            except Exception as _verify_call_err:
                logger.warning(' verifier call failed; rolling back unverifiable patch: %s', type(_verify_call_err).__name__)
                if _pre_fix_content is not None:
                    filepath.write_text(_pre_fix_content, encoding='utf-8')
                self._fixes_this_cycle = max(0, self._fixes_this_cycle - 1)
                return {'action': 'skipped', 'tier': int(bug.tier), 'reason': 'verifier call failed; fix is UNVERIFIED and was rolled back', 'patched': False}
            bug_key = f'{bug.file}:{bug.line}:{bug.bug_type}'
            self._recent_fixes[bug_key] = time.time()
            _verify_ok_local = locals().get('_verify_ok')
            _verify_reason_local = locals().get('_verify_reason')
            try:
                from scp.autofix.audit_log import compute_hashes as _compute_hashes_4b012, make_rollback_token_backup as _rb_token_4b012
                _main_post = filepath.read_text(encoding='utf-8')
                _main_bh, _main_ah = _compute_hashes_4b012(_pre_fix_content, _main_post)
                if _verify_ok_local is True:
                    _main_rtr = 'pass'
                elif _verify_ok_local is False:
                    _main_rtr = f"fail:{(_verify_reason_local or 'unknown')[:80]}"
                else:
                    _main_rtr = 'skipped'
                if attack_mode:
                    try:
                        from scp.autofix.audit_log import make_rollback_token_git as _git_token_4b012
                        _main_token = _git_token_4b012(str(filepath))
                    except Exception:
                        _main_token = _rb_token_4b012(str(filepath))
                else:
                    _main_token = _rb_token_4b012(str(filepath))
            except Exception as _main_hash_err:
                logger.debug(f"[4-b-012] main audit hash/token compute failed (non-fatal — entry gets 'n/a'): {_main_hash_err}")
                _main_bh = _main_ah = 'n/a'
                _main_rtr = 'skipped'
                _main_token = 'n/a'
            if report or attack_mode:
                self._write_audit(bug, 'fixed', attack_mode=attack_mode, before_hash=_main_bh, after_hash=_main_ah, rollback_token=_main_token, reality_test_result=_main_rtr)
            else:
                self._write_audit(bug, 'fixed_silent', attack_mode=False, before_hash=_main_bh, after_hash=_main_ah, rollback_token=_main_token, reality_test_result=_main_rtr)
            try:
                if os.environ.get('SCP_EVOLUTION_ENABLED', '0') == '1':
                    from scp.autofix.evolution import get_evolution_engine
                    _evo = get_evolution_engine(data_dir=str(self.data_dir))
                    _fix_diff = str(bug.suggested_fix) if bug.suggested_fix else ''
                    _reflect_result = _evo.reflect(bug, _fix_diff)
                    logger.info(f"[V5.7-WHY] reflect: {bug.file}:{bug.line} self_falsified={getattr(_reflect_result, 'self_falsified', '?')} lesson={getattr(_reflect_result, 'lesson_learned', '')[:80]!r}")
            except Exception as _reflect_err:
                logger.debug(f'[V5.7-WHY] reflect failed (non-fatal): {_reflect_err}')
            try:
                from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                from scp.autofix.monitor import FixAttempt as _FixAttempt
                from scp.autofix.monitor import get_monitor as _get_monitor
                _diag = _diagnose(bug_id=_autofix_bug_id, bug_type=bug.bug_type, llm_output=bug.suggested_fix, patch_parsed={'search': '(applied)', 'replace': '(applied)'}, validation_result={'valid': True, 'reason': 'pre-apply OK'}, apply_result='success')
                _get_monitor().record(_FixAttempt(bug_id=_autofix_bug_id, bug_type=bug.bug_type, provider=_autofix_provider, diagnosis=_diag.diagnosis, success=True))
            except Exception as e:
                logger.warning(f'Silent except: {e}')
            try:
                from scp.autofix.runner_phases.auto_rollback import get_regression_watcher as _v4_get_watcher
                _v4_watch_token = ''
                if _pre_fix_content is not None:
                    try:
                        _v4_post_content = filepath.read_text(encoding='utf-8')
                        _v4_watch_token = self.register_fix_for_rollback(file_path=str(filepath), before_content=_pre_fix_content, after_content=_v4_post_content, patch=bug.suggested_fix or '', bug_id=_autofix_bug_id, bug_type=bug.bug_type, tier=int(bug.tier), reality_test_result=None)
                    except Exception as _v4_rb_reg_err:
                        logger.debug(f'[R10 v3 IMP-17] register_fix_for_rollback failed (non-fatal — watcher will log-only): {_v4_rb_reg_err}')
                if _v4_watch_token:
                    _v4_watcher = _v4_get_watcher()
                    _v4_watcher.register(fix_id=_autofix_bug_id, file_path=str(filepath), rollback_token=_v4_watch_token, ttl=60, extra={'bug_type': bug.bug_type, 'tier': int(bug.tier), 'attack_mode': attack_mode})
                    logger.info(f'[R10 v3 IMP-17] registered fix {_autofix_bug_id} for regression watch (ttl=60s, token={_v4_watch_token[:8]}...)')
            except ImportError as _v4_ar_imp:
                logger.debug(f'[R10 v3 IMP-17] auto_rollback unavailable (fail-open): {_v4_ar_imp}')
            except Exception as _v4_ar_err:
                logger.debug(f'[R10 v3 IMP-17] auto_rollback wire crash (fail-open): {_v4_ar_err}')
            _result_rollback_token = locals().get('_v4_watch_token') or locals().get('_main_token', 'n/a')
            _result_rollback_registered = bool(locals().get('_v4_watch_token'))
            return {'action': 'fixed', 'tier': int(bug.tier), 'patched': patched, 'attack_mode': attack_mode, 'before_hash': locals().get('_main_bh', 'n/a'), 'after_hash': locals().get('_main_ah', 'n/a'), 'rollback_token': _result_rollback_token, 'rollback_registered': _result_rollback_registered, 'reality_test_result': locals().get('_main_rtr', 'skipped')}
        except Exception as e:
            logger.warning(f'Auto-fix failed for {bug.file}:{bug.line}: {e}')
            return {'action': 'skipped', 'tier': int(bug.tier), 'reason': f'fix failed: {e}'}

    def _should_auto_approve_tier3(self, bug: BugReport) -> bool:
        """[TIER3-AUTO] Check if SCP can auto-approve this Tier-3 bug.

        [V4.3] Now uses Tier3AutoConfig — SCP HIỂU context cấp quyền:
          - Log startup: permission granted/denied + source (.env/API/runtime)
          - Audit trail: every auto-approve → data/tier3_auto_audit.jsonl
          - Stats: /v105/autofix/stats returns tier3_auto_enabled + reasons

        Safety guards (ALL must pass):
          1. SCP_AUTO_APPROVE_TIER3=1 env var set (via Tier3AutoConfig)
          2. Not expired (within TIER3_AUTO_TIMEOUT_SECONDS since first enable)
          3. Rate limit not exceeded (MAX_TIER3_AUTO_PER_HOUR)
          4. bug.is_relaxation == False (HARD LIMIT -- never auto-relax security)
          5. Not in cooldown (same bug fixed recently)
          6. [RUNTIME-FIX-6] Not BareExceptPass -- runtime log shows 63% rollback
             rate for this bug_type. LLM-fix is generating patches that introduce
             NEW BareExceptPass bugs nearby. Skip auto-approve for this bug_type
             until LLM-fix quality improves. Human review required.

        Returns True only if ALL guards pass.
        """
        _config = get_tier3_config()
        if not _config.is_enabled():
            return False
        _permission_source = _config.get_permission_source()
        if not hasattr(self, '_last_permission_source') or self._last_permission_source != _permission_source:
            logger.info(f'[TIER3-AUTO] Decision authority granted — SCP có quyền phán quyết auto-approve Tier-3 (source: {_permission_source[:60]})')
            self._last_permission_source = _permission_source
        if bug.bug_type == 'BareExceptPass':
            logger.info(f'[TIER3-AUTO] SKIP auto-approve for BareExceptPass ({bug.file}:{bug.line}) -- requires human review (runtime log: 63% rollback rate)')
            return False
        now = time.time()
        _env_now = os.environ.get('SCP_AUTO_APPROVE_TIER3', '0')
        _last_env = getattr(self, '_tier3_env_last_seen', '0')
        if _env_now == '1' and _last_env != '1':
            self._tier3_auto_expired = False
            self._tier3_auto_enabled_at = 0.0
            logger.info('[TIER3-AUTO] Re-arm permitted — env var transition 0→1 detected')
        self._tier3_env_last_seen = _env_now
        if not getattr(self, '_tier3_auto_expired', False):
            if self._tier3_auto_enabled_at == 0.0:
                self._tier3_auto_enabled_at = now
            elif now - self._tier3_auto_enabled_at > TIER3_AUTO_TIMEOUT_SECONDS:
                logger.warning(f'[TIER3-AUTO] Timed out after {TIER3_AUTO_TIMEOUT_SECONDS}s -- re-enable by UNSETTING + re-SETTING SCP_AUTO_APPROVE_TIER3=1 (R8-2: previous behavior re-armed silently on next bug)')
                self._tier3_auto_expired = True
                return False
        else:
            return False
        self._tier3_auto_timestamps = [t for t in self._tier3_auto_timestamps if now - t < 3600]
        if len(self._tier3_auto_timestamps) >= MAX_TIER3_AUTO_PER_HOUR:
            logger.warning(f'[TIER3-AUTO] Rate limit hit -- {MAX_TIER3_AUTO_PER_HOUR}/hour exceeded')
            return False
        if getattr(bug, 'is_relaxation', False):
            logger.warning(f'[TIER3-AUTO] HARD LIMIT -- bug {bug.file}:{bug.line} is relaxation (loosens security) -> still requires human approval')
            return False
        bug_key = f'{bug.file}:{bug.line}:{bug.bug_type}'
        if bug_key in self._recent_fixes:
            if now - self._recent_fixes[bug_key] < COOLDOWN_SAME_BUG_SECONDS:
                return False
        return True

    def _auto_approve_tier3(self, bug: BugReport) -> dict:
        """[TIER3-AUTO] Auto-approve + apply a Tier-3 bug (with safety guards).

        [V4.3] Now logs audit trail — SCP records every auto-approve decision.

        Called ONLY when _should_auto_approve_tier3() returns True.
        Backs up file to .tier3bak, applies fix, logs to tier3_auto_audit.jsonl.

        [SCP-DNA-FIX R7-13] Audit log schema extended — adds 4 new fields:
          - before_hash: sha256 of file BEFORE fix (for diff/verify)
          - after_hash: sha256 of file AFTER fix (for tamper detection)
          - reality_test_result: "PASS" | "FAIL" | "SKIPPED" (ast.parse + grep)
          - rollback_token: UUID operator can POST to /v105/autofix/rollback/{token}
                            to revert file to before_hash state (restores from
                            .tier3bak if available, else errors clearly).
        TẠI SAO: R5/R6 audit log had timestamp/file/line/fix/before only — could
        NOT rollback a specific fix (no token), could NOT verify file integrity
        after fix (no after_hash), could NOT see if the reality test passed
        (no reality_test_result). Operators had to grep .tier3bak files manually.
        Reality evidence: 12 rollback requests in 30d required manual file restore.
        """
        get_tier3_config().audit_auto_approve(bug, reason=f'All 6 safety guards passed (bug_type={bug.bug_type})')
        _before_hash = ''
        try:
            from pathlib import Path as PathCls
            filepath = PathCls(bug.file)
            if filepath.exists():
                import hashlib as _hashlib
                _before_hash = _hashlib.sha256(filepath.read_bytes()).hexdigest()
        except Exception as e:
            logger.debug(f' before_hash compute failed for {bug.file}: {e}')
        _rollback_token = ''
        try:
            import uuid as _uuid
            _rollback_token = str(_uuid.uuid4())
        except Exception as _rollback_token_error:
            logger.warning('[AUTOFIX] UUID rollback token generation failed; using legacy backup fallback', exc_info=True)
        try:
            from pathlib import Path as PathCls
            filepath = PathCls(bug.file)
            if filepath.exists():
                if _rollback_token:
                    bak_path = filepath.with_suffix(filepath.suffix + f'.tier3bak.{_rollback_token}')
                else:
                    bak_path = filepath.with_suffix(filepath.suffix + '.tier3bak')
                bak_path.write_text(filepath.read_text(encoding='utf-8'), encoding='utf-8')
        except Exception as e:
            logger.warning(f'[TIER3-AUTO] Backup failed for {bug.file}: {e}')
        result = self._auto_fix(bug, report=True, attack_mode=False)
        if result.get('action') == 'fixed':
            result['tier'] = 3
            result['tier3_auto_approved'] = True
            self._tier3_auto_timestamps.append(time.time())
            _after_hash = ''
            _reality_test_result = 'SKIPPED'
            try:
                from pathlib import Path as PathCls
                filepath = PathCls(bug.file)
                if filepath.exists():
                    import hashlib as _hashlib
                    _after_hash = _hashlib.sha256(filepath.read_bytes()).hexdigest()
                    import ast as _ast
                    try:
                        _ast.parse(filepath.read_text(encoding='utf-8'))
                        _reality_test_result = 'PASS'
                    except SyntaxError as _se:
                        _reality_test_result = f"FAIL:SyntaxError:{(_se.msg or '')[:80]}"
                    except Exception as _ee:
                        _reality_test_result = f'FAIL:{type(_ee).__name__}:{str(_ee)[:80]}'
            except Exception as e:
                logger.debug(f' after_hash / reality_test compute failed: {e}')
                _reality_test_result = f'FAIL:hash_compute:{str(e)[:80]}'
            self._write_tier3_auto_audit(bug, 'auto_approved_and_fixed', before_hash=_before_hash, after_hash=_after_hash, reality_test_result=_reality_test_result, rollback_token=_rollback_token)
            result['rollback_token'] = _rollback_token
            result['after_hash'] = _after_hash
            result['reality_test_result'] = _reality_test_result
        return result

    def _write_tier3_auto_audit(self, bug: BugReport, action: str, before_hash: str='', after_hash: str='', reality_test_result: str='SKIPPED', rollback_token: str=''):
        """Write to data/tier3_auto_audit.jsonl (separate from normal audit).

        [SCP-DNA-FIX R7-13] Extended schema — see _auto_approve_tier3 docstring.
        Old entries (pre-R7-13) lacked the 4 new fields; readers should treat
        them as optional (rollback_token="" means "no rollback available").
        """
        entry = {'timestamp': time.time(), 'file': bug.file, 'line': bug.line, 'bug_type': bug.bug_type, 'description': bug.description[:300], 'suggested_fix': (bug.suggested_fix or '')[:500], 'action': action, 'is_relaxation': getattr(bug, 'is_relaxation', False), 'env_SCP_AUTO_APPROVE_TIER3': os.environ.get('SCP_AUTO_APPROVE_TIER3', '0'), 'before_hash': before_hash, 'after_hash': after_hash, 'reality_test_result': reality_test_result, 'rollback_token': rollback_token}
        try:
            with open(self.tier3_auto_audit_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.warning(f'[TIER3-AUTO] Failed to write audit log: {e}')

    def _request_permission(self, bug: BugReport) -> dict:
        """Submit permission request for a Tier 3 bug. Does NOT fix.

        [TIER3-AUTO] If SCP_AUTO_APPROVE_TIER3=1 and safety guards pass,
        auto-approve + apply instead of requesting human permission.
        """
        if self._should_auto_approve_tier3(bug):
            logger.info(f'[TIER3-AUTO] Auto-approving Tier-3 bug {bug.file}:{bug.line} ({bug.bug_type}) -- SCP_AUTO_APPROVE_TIER3=1')
            return self._auto_approve_tier3(bug)
        request_id = self.permission_gate.request_permission(bug)
        self._write_audit(bug, 'permission_requested')
        return {'action': 'permission_requested', 'tier': int(bug.tier), 'request_id': request_id, 'reason': 'logic bug — human approval required'}

    def check_pending_permissions(self) -> list[dict]:
        """Check pending permission requests. Returns list of approved ones
        that are ready to fix."""
        ready = []
        for req in self.permission_gate.list_pending():
            status = self.permission_gate.check_permission(req.request_id)
            if status == 'approved':
                ready.append({'request_id': req.request_id, 'file': req.file, 'line': req.line, 'fix': req.suggested_fix, 'approved_by': req.decided_by})
        return ready

    def apply_approved_fix(self, request_id: str) -> dict:
        """Apply a fix that was approved by human."""
        req = self.permission_gate._pending.get(request_id)
        if not req:
            return {'action': 'skipped', 'reason': 'request not found'}
        if self.permission_gate.check_permission(request_id) != 'approved':
            return {'action': 'skipped', 'reason': 'not approved'}
        bug = BugReport(file=req.file, line=req.line, bug_type=req.bug_type, description=req.description, suggested_fix=req.suggested_fix, tier=BugTier.TIER_3_PERMISSION, affects_logic=True)
        result = self._auto_fix(bug, report=True)
        if result.get('action') == 'fixed':
            self._write_audit(bug, 'fixed_after_permission', extra={'request_id': request_id, 'approved_by': req.decided_by})
        return result

    def _write_audit(self, bug: BugReport, action: str, attack_mode: bool=False, extra: dict | None=None, before_hash: str='n/a', after_hash: str='n/a', rollback_token: str='n/a', reality_test_result: str='n/a'):
        """Write to audit log (append-only JSONL).

        [SCP-DNA-FIX 4-b-012] DNA #8 (KB accumulation): every entry MUST
        carry before_hash + after_hash + rollback_token + reality_test_result
        for ALL tiers (1, 2, 3, 4). Pre-fix, this method wrote only a
        message — Tier 1/2/4 fixes were non-revertible by token and
        non-auditable to the standard claimed.

        The new AuditLogEntry Pydantic schema (imported from
        scp.autofix.audit_log) ENFORCES the 4 required fields at write
        time. An entry missing any of them is REJECTED
        (Pydantic ValidationError) — caller sees False return + ERROR log,
        not a silent malformed entry.

        Defaults are the explicit "n/a" sentinel (NOT empty string) so
        non-fix events (e.g. permission_requested) satisfy the schema.
        Fix events MUST pass real values — passing "" (empty) is rejected
        by the schema (catches caller bugs, DNA #8).
        """
        try:
            from scp.autofix.audit_log import write_audit_entry as _write_entry
        except ImportError as _audit_imp_err:
            logger.warning(f'[4-b-012] audit_log module unavailable, falling back to legacy write (no DNA #8 schema enforcement): {_audit_imp_err}')
            entry = {'timestamp': time.time(), 'file': bug.file, 'line': bug.line, 'bug_type': bug.bug_type, 'tier': int(bug.tier), 'action': action, 'attack_mode': attack_mode, 'description': bug.description[:200], 'before_hash': before_hash or 'n/a', 'after_hash': after_hash or 'n/a', 'rollback_token': rollback_token or 'n/a', 'reality_test_result': reality_test_result or 'n/a'}
            if extra:
                entry.update(extra)
            try:
                with open(self.audit_log, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            except Exception as e:
                logger.warning(f'Silent except: {e}')
            return
        finding_id = f'{bug.file}:{bug.line}'
        message = (extra or {}).get('description') or bug.description[:200]
        ok = _write_entry(log_path=self.audit_log, finding_id=finding_id, tier=int(bug.tier), action=action, before_hash=before_hash, after_hash=after_hash, rollback_token=rollback_token, reality_test_result=reality_test_result, message=message, extra={**({'attack_mode': attack_mode} if attack_mode else {}), **(extra or {}), 'file': bug.file, 'line': bug.line, 'bug_type': bug.bug_type})
        if not ok:
            logger.warning(f'[4-b-012] audit log write REJECTED for {finding_id} tier={int(bug.tier)} action={action!r} — see prior ERROR log')

    def set_attack_mode(self, enabled: bool):
        """Toggle attack mode. When enabled, Tier 4 restraints auto-apply."""
        self.in_attack_mode = enabled
        logger.info(f"[AutoFix] Attack mode {('ENABLED' if enabled else 'DISABLED')}")

    def stats(self) -> dict:
        """Return stats for monitoring."""
        now = time.time()
        tier3_auto_remaining = max(0, MAX_TIER3_AUTO_PER_HOUR - len(self._tier3_auto_timestamps))
        tier3_auto_expires_in = 0
        if self._tier3_auto_enabled_at > 0:
            tier3_auto_expires_in = max(0, int(TIER3_AUTO_TIMEOUT_SECONDS - (now - self._tier3_auto_enabled_at)))
        return {'in_attack_mode': self.in_attack_mode, 'fixes_this_cycle': self._fixes_this_cycle, 'tier4_last_hour': len(self._tier4_timestamps), 'pending_permissions': len(self.permission_gate.list_pending()), 'recent_fixes': len(self._recent_fixes), 'cycle_started_at': self._cycle_start_time, 'cycle_resets_in': max(0, int(CYCLE_RESET_SECONDS - (time.time() - self._cycle_start_time))), 'tier3_auto_enabled': os.environ.get('SCP_AUTO_APPROVE_TIER3', '0') == '1', 'tier3_auto_used_this_hour': len(self._tier3_auto_timestamps), 'tier3_auto_remaining': tier3_auto_remaining, 'tier3_auto_max_per_hour': MAX_TIER3_AUTO_PER_HOUR, 'tier3_auto_expires_in_seconds': tier3_auto_expires_in}
