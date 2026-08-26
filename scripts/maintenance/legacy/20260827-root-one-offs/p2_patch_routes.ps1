param([string]$Root = 'C:\Users\check\Downloads\scp')
$ErrorActionPreference = 'Stop'

function Load-Lines([string]$path) {
    $list = New-Object 'System.Collections.Generic.List[string]'
    foreach ($line in (Get-Content -LiteralPath $path)) { [void]$list.Add([string]$line) }
    return $list
}
function Save-Lines([string]$path, [System.Collections.Generic.List[string]]$lines) {
    [IO.File]::WriteAllLines($path, $lines, (New-Object Text.UTF8Encoding($false)))
}
function Backup-File([string]$path, [string]$tag) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $bak = $path + '.bak-before-p2-' + $tag + '-' + $stamp
    Copy-Item -LiteralPath $path -Destination $bak -Force
    return $bak
}
function Find-Exact([System.Collections.Generic.List[string]]$lines, [string]$needle, [int]$start = 0) {
    for ($i=$start; $i -lt $lines.Count; $i++) { if ($lines[$i] -eq $needle) { return $i } }
    return -1
}
function Find-Starts([System.Collections.Generic.List[string]]$lines, [string]$prefix, [int]$start = 0) {
    for ($i=$start; $i -lt $lines.Count; $i++) { if ($lines[$i].StartsWith($prefix)) { return $i } }
    return -1
}
function Add-ImportAndLedger([System.Collections.Generic.List[string]]$lines, [string]$ledgerVar) {
    $changed = $false
    if ((Find-Starts $lines 'from scp.core.request_run_ledger import') -lt 0) {
        $router = Find-Starts $lines 'router = APIRouter'
        if ($router -lt 0) { throw 'router declaration missing' }
        [void]$lines.Insert($router, 'from scp.core.request_run_ledger import RequestRunLedger, traced_request')
        [void]$lines.Insert($router + 1, '')
        $changed = $true
    }
    if ((Find-Exact $lines ($ledgerVar + ' = RequestRunLedger()')) -lt 0) {
        $router = Find-Starts $lines 'router = APIRouter'
        if ($router -lt 0) { throw 'router declaration missing for ledger' }
        [void]$lines.Insert($router + 1, ($ledgerVar + ' = RequestRunLedger()'))
        [void]$lines.Insert($router + 2, '')
        $changed = $true
    }
    return $changed
}
function Add-RouteDecorators([System.Collections.Generic.List[string]]$lines, [string]$ledgerVar, [hashtable]$routes) {
    $changed = $false
    foreach ($name in $routes.Keys) {
        $fn = Find-Starts $lines ('async def ' + $name + '(')
        if ($fn -lt 0) { throw "route function missing: $name" }
        $decorator = '@traced_request(' + $ledgerVar + ', require_write=' + ($(if($routes[$name].write){'True'}else{'False'})) + ', action="' + $routes[$name].action + '")'
        $already = $false
        for ($j=[Math]::Max(0,$fn-4); $j -lt $fn; $j++) { if ($lines[$j] -eq $decorator) { $already=$true } }
        if (-not $already) { [void]$lines.Insert($fn, $decorator); $changed=$true }
    }
    return $changed
}
function Patch-Routes([string]$relative, [string]$ledgerVar, [hashtable]$routes, [string]$tag) {
    $path = Join-Path $Root $relative
    if (-not (Test-Path $path)) { throw "missing route file: $relative" }
    $lines = Load-Lines $path
    $changed = Add-ImportAndLedger $lines $ledgerVar
    if (Add-RouteDecorators $lines $ledgerVar $routes) { $changed=$true }
    if ($changed) { $bak=Backup-File $path $tag;Save-Lines $path $lines;Write-Output ('PATCHED='+$relative+'|BACKUP='+$bak) }
}

# Core PCController: audit intent is required before mutation; post-audit failure is visible and write_file rolls back.
$core = Join-Path $Root 'scp\pc_control\pc_controller.py'
if (-not (Test-Path $core)) { throw 'missing pc_controller.py' }
$coreText = [IO.File]::ReadAllText($core)
if ($coreText -notmatch 'P2-FIX-AUDIT') {
    $nl = "`n"
    $oldImport = 'import asyncio' + $nl
    $newImport = 'import asyncio' + $nl + 'import hashlib' + $nl
    if (([regex]::Matches($coreText,[regex]::Escape($oldImport))).Count -ne 1) { throw 'core import anchor mismatch' }
    $coreText = $coreText.Replace($oldImport,$newImport)
    $oldAudit = '    def _audit(self, event: str, payload: dict[str, Any]) -> None:' + $nl + '        record = {' + $nl + '            "timestamp": time.time(),' + $nl + '            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),' + $nl + '            "event": event,' + $nl + '            **payload,' + $nl + '        }' + $nl + '        try:' + $nl + '            with self.audit_path.open("a", encoding="utf-8") as handle:' + $nl + '                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")' + $nl + '        except OSError:' + $nl + '            logger.exception("Unable to append PC controller audit entry")' + $nl
    $newAudit = '    # P2-FIX-AUDIT: return a durable result; callers must fail closed.' + $nl + '    def _audit(self, event: str, payload: dict[str, Any]) -> bool:' + $nl + '        record = {' + $nl + '            "timestamp": time.time(),' + $nl + '            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),' + $nl + '            "event": event,' + $nl + '            **payload,' + $nl + '        }' + $nl + '        try:' + $nl + '            with self.audit_path.open("a", encoding="utf-8") as handle:' + $nl + '                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")' + $nl + '                handle.flush()' + $nl + '                os.fsync(handle.fileno())' + $nl + '            return True' + $nl + '        except OSError:' + $nl + '            logger.exception("Unable to append PC controller audit entry")' + $nl + '            return False' + $nl
    if (([regex]::Matches($coreText,[regex]::Escape($oldAudit))).Count -ne 1) { throw 'core audit anchor mismatch' }
    $coreText = $coreText.Replace($oldAudit,$newAudit)
    $oldExec = '        result = await asyncio.to_thread(self._run_sync, command, timeout)' + $nl + '        self._audit("EXECUTE", {**base, **result})' + $nl + '        return {**base, **result}' + $nl
    $newExec = '        if not self._audit("EXECUTE_INTENT", {**base, "timeout": timeout}):' + $nl + '            return {**base, "success": False, "output": "", "error": "Audit storage unavailable; action blocked", "auditStatus": "DB_WRITE_FAILED"}' + $nl + '        result = await asyncio.to_thread(self._run_sync, command, timeout)' + $nl + '        post_audit_ok = self._audit("EXECUTE", {**base, **result})' + $nl + '        if not post_audit_ok:' + $nl + '            return {**base, **result, "executed": True, "auditStatus": "DB_WRITE_FAILED", "error": "Audit write failed after execution"}' + $nl + '        return {**base, **result, "auditStatus": "OK"}' + $nl
    if (([regex]::Matches($coreText,[regex]::Escape($oldExec))).Count -ne 1) { throw 'core execute anchor mismatch' }
    $coreText = $coreText.Replace($oldExec,$newExec)
    $oldWriteGate = '        if self.kill_switch_engaged() or capability_level < CapabilityLevel.WORKSPACE or not approved:' + $nl + '            return {"success": False, "error": "Write requires capability >= 3 and explicit approval"}' + $nl + '        target.parent.mkdir(parents=True, exist_ok=True)' + $nl + '        backup_id = uuid.uuid4().hex' + $nl
    $newWriteGate = '        if self.kill_switch_engaged() or capability_level < CapabilityLevel.WORKSPACE or not approved:' + $nl + '            return {"success": False, "error": "Write requires capability >= 3 and explicit approval"}' + $nl + '        content_hash = hashlib.sha256(content.encode("utf-8", "replace")).hexdigest()' + $nl + '        intent = {"path": str(target), "bytes": len(content.encode("utf-8")), "content_sha256": content_hash, "capability_level": int(capability_level)}' + $nl + '        if not self._audit("WRITE_FILE_INTENT", intent):' + $nl + '            return {"success": False, "error": "Audit storage unavailable; write blocked", "auditStatus": "DB_WRITE_FAILED"}' + $nl + '        target.parent.mkdir(parents=True, exist_ok=True)' + $nl + '        backup_id = uuid.uuid4().hex' + $nl
    if (([regex]::Matches($coreText,[regex]::Escape($oldWriteGate))).Count -ne 1) { throw 'core write gate anchor mismatch' }
    $coreText = $coreText.Replace($oldWriteGate,$newWriteGate)
    $oldWriteResult = '        result = {"success": True, "path": str(target), "backupId": backup_id if existed else None, "bytes": len(content.encode("utf-8"))}' + $nl + '        self._audit("WRITE_FILE", result)' + $nl + '        return result' + $nl
    $newWriteResult = '        result = {"success": True, "path": str(target), "backupId": backup_id if existed else None, "bytes": len(content.encode("utf-8")), "content_sha256": content_hash}' + $nl + '        if not self._audit("WRITE_FILE", result):' + $nl + '            try:' + $nl + '                if existed:' + $nl + '                    shutil.copy2(backup_path, target)' + $nl + '                else:' + $nl + '                    target.unlink(missing_ok=True)' + $nl + '            except OSError:' + $nl + '                logger.exception("Write rollback failed after audit failure")' + $nl + '            return {"success": False, "path": str(target), "error": "Audit write failed; write rolled back", "auditStatus": "DB_WRITE_FAILED"}' + $nl + '        return {**result, "auditStatus": "OK"}' + $nl
    if (([regex]::Matches($coreText,[regex]::Escape($oldWriteResult))).Count -ne 1) { throw 'core write result anchor mismatch' }
    $coreText = $coreText.Replace($oldWriteResult,$newWriteResult)
    $oldKill = '    def engage_kill_switch(self, reason: str = "user requested") -> dict[str, Any]:' + $nl + '        self.kill_switch_path.write_text(json.dumps({"reason": reason, "timestamp": time.time()}, ensure_ascii=False), encoding="utf-8")' + $nl + '        self._audit("KILL_SWITCH_ENGAGED", {"reason": reason})' + $nl + '        return {"success": True, "killSwitch": True, "reason": reason}' + $nl
    $newKill = '    def engage_kill_switch(self, reason: str = "user requested") -> dict[str, Any]:' + $nl + '        reason_hash = hashlib.sha256(reason.encode("utf-8", "replace")).hexdigest()' + $nl + '        if not self._audit("KILL_SWITCH_INTENT", {"reason_sha256": reason_hash}):' + $nl + '            return {"success": False, "killSwitch": self.kill_switch_engaged(), "error": "Audit storage unavailable; kill-switch action blocked", "auditStatus": "DB_WRITE_FAILED"}' + $nl + '        self.kill_switch_path.write_text(json.dumps({"reason": reason, "timestamp": time.time()}, ensure_ascii=False), encoding="utf-8")' + $nl + '        if not self._audit("KILL_SWITCH_ENGAGED", {"reason_sha256": reason_hash}):' + $nl + '            return {"success": True, "killSwitch": True, "reason": reason, "auditStatus": "DB_WRITE_FAILED"}' + $nl + '        return {"success": True, "killSwitch": True, "reason": reason, "auditStatus": "OK"}' + $nl
    if (([regex]::Matches($coreText,[regex]::Escape($oldKill))).Count -ne 1) { throw 'core kill anchor mismatch' }
    $coreText = $coreText.Replace($oldKill,$newKill)
    $oldClear = '    def clear_kill_switch(self, approved: bool = False) -> dict[str, Any]:' + $nl + '        if not approved:' + $nl + '            return {"success": False, "error": "Clearing kill switch requires explicit approval"}' + $nl + '        self.kill_switch_path.unlink(missing_ok=True)' + $nl + '        self._audit("KILL_SWITCH_CLEARED", {})' + $nl + '        return {"success": True, "killSwitch": False}' + $nl
    $newClear = '    def clear_kill_switch(self, approved: bool = False) -> dict[str, Any]:' + $nl + '        if not approved:' + $nl + '            return {"success": False, "error": "Clearing kill switch requires explicit approval"}' + $nl + '        if not self._audit("KILL_SWITCH_CLEAR_INTENT", {}):' + $nl + '            return {"success": False, "killSwitch": True, "error": "Audit storage unavailable; clear blocked", "auditStatus": "DB_WRITE_FAILED"}' + $nl + '        self.kill_switch_path.unlink(missing_ok=True)' + $nl + '        if not self._audit("KILL_SWITCH_CLEARED", {}):' + $nl + '            self.kill_switch_path.write_text(json.dumps({"reason": "audit failure fail-closed", "timestamp": time.time()}, ensure_ascii=False), encoding="utf-8")' + $nl + '            return {"success": False, "killSwitch": True, "error": "Audit write failed; kill switch re-engaged", "auditStatus": "DB_WRITE_FAILED"}' + $nl + '        return {"success": True, "killSwitch": False, "auditStatus": "OK"}' + $nl
    if (([regex]::Matches($coreText,[regex]::Escape($oldClear))).Count -ne 1) { throw 'core clear anchor mismatch' }
    $coreText = $coreText.Replace($oldClear,$newClear)
    $bak=Backup-File $core 'pc-controller'
    [IO.File]::WriteAllText($core,$coreText,(New-Object Text.UTF8Encoding($false)))
    Write-Output ('PATCHED=pc_controller.py|BACKUP='+$bak)
}

# Route surfaces. All receive run_id/trace_id; state-changing routes require audit storage before entry.
Patch-Routes 'scp\api\webhook.py' '_WEBHOOK_LEDGER' @{
    analyze_prompt=@{write=$false;action='webhook_analyze'}; register_system=@{write=$false;action='webhook_register'}; list_threats=@{write=$false;action='webhook_threats'}; list_alerts=@{write=$false;action='webhook_alerts'}; list_systems=@{write=$false;action='webhook_systems'}
} 'webhook'
Patch-Routes 'scp\api\routes\admin_v98.py' '_ADMIN_V98_LEDGER' @{
    analyze_session=@{write=$false;action='v98_analyze_session'}; run_simulation=@{write=$true;action='v98_run_simulation'}; run_intel_crawl=@{write=$true;action='v98_run_intel_crawl'}; v98_status=@{write=$false;action='v98_status'}; counter_stats=@{write=$false;action='v98_counter_stats'}; canary_triggers=@{write=$false;action='v98_canary_triggers'}; error_store_stats=@{write=$false;action='v98_error_store_stats'}; attack_memory_stats=@{write=$false;action='v98_attack_memory_stats'}
} 'admin-v98'
Patch-Routes 'scp\api\routes\admin_v100.py' '_ADMIN_V100_LEDGER' @{
    v100_status=@{write=$false;action='v100_status'}; v100_crawl=@{write=$true;action='v100_crawl'}; antibody_stats=@{write=$false;action='v100_antibody_stats'}; antibody_check=@{write=$false;action='v100_antibody_check'}; knowledge_stats=@{write=$false;action='v100_knowledge_stats'}; knowledge_search=@{write=$false;action='v100_knowledge_search'}; h8_stats=@{write=$false;action='v100_h8_stats'}; h8_bypasses=@{write=$false;action='v100_h8_bypasses'}; h8_analyses=@{write=$false;action='v100_h8_analyses'}
} 'admin-v100'
Patch-Routes 'scp\api\routes\v102_v103_routes.py' '_ADMIN_V102_LEDGER' @{
    orchestrator_stats=@{write=$false;action='v102_orchestrator_stats'}; notifications_recent=@{write=$false;action='v102_notifications'}; storage_stats=@{write=$false;action='v103_storage_stats'}; storage_maintain=@{write=$true;action='v103_storage_maintain'}; gcg_test=@{write=$true;action='v103_gcg_test'}; v103_crawled_attacks=@{write=$false;action='v103_crawled_attacks'}; v103_force_crawl=@{write=$true;action='v103_force_crawl'}; v103_status=@{write=$false;action='v103_status'}
} 'admin-v102'
Patch-Routes 'scp\api\routes\v104_routes.py' '_ADMIN_V104_LEDGER' @{
    v104_status=@{write=$false;action='v104_status'}; v104_multi_turn_check=@{write=$false;action='v104_multi_turn_check'}; v104_image_check=@{write=$false;action='v104_image_check'}; v104_voice_check=@{write=$false;action='v104_voice_check'}; v104_cross_language_transfer=@{write=$false;action='v104_cross_language_transfer'}; v104_explain=@{write=$false;action='v104_explain'}; v104_fact_check=@{write=$false;action='v104_fact_check'}; v104_learn_ollama=@{write=$true;action='v104_learn_ollama'}; v104_learn_local=@{write=$true;action='v104_learn_local'}; v104_learn_news=@{write=$true;action='v104_learn_news'}; v104_learn_all=@{write=$true;action='v104_learn_all'}; v104_learn_status=@{write=$false;action='v104_learn_status'}; v104_learn_matrix=@{write=$false;action='v104_learn_matrix'}; v104_learn_ollama_matrix=@{write=$true;action='v104_learn_matrix_run'}; v1042_learn_fast=@{write=$true;action='v104_fast_learning'}; v1042_learn_fast_status=@{write=$false;action='v104_fast_status'}; v1042_learn_fast_benchmark=@{write=$false;action='v104_fast_benchmark'}
} 'admin-v104'
Patch-Routes 'scp\api\routes\v105_routes.py' '_ADMIN_V105_LEDGER' @{
    v105_list_permissions=@{write=$false;action='v105_list_permissions'}; v105_approve_permission=@{write=$true;action='v105_approve_autofix'}; v105_deny_permission=@{write=$true;action='v105_deny_autofix'}; v105_toggle_attack_mode=@{write=$true;action='v105_attack_mode'}; v105_autofix_stats=@{write=$false;action='v105_autofix_stats'}; v105_run_deep_audit=@{write=$true;action='v105_run_audit'}; deterministic_worker_status=@{write=$false;action='v105_worker_status'}; runtime_subsystem_status=@{write=$false;action='v105_subsystem_status'}; deterministic_worker_job=@{write=$false;action='v105_worker_job'}; autofix_monitor=@{write=$false;action='v105_autofix_monitor'}; cleanup_cache=@{write=$true;action='v105_cleanup_cache'}; v105_toggle_tier3_auto=@{write=$true;action='v105_tier3_auto'}; v105_autofix_rollback=@{write=$true;action='v105_autofix_rollback'}
} 'admin-v105'
Patch-Routes 'scp\api\routes\prediction_routes.py' '_PREDICTION_LEDGER' @{
    run_prediction_cycle=@{write=$true;action='prediction_run_cycle'}; get_pending_predictions=@{write=$false;action='prediction_pending'}; get_all_predictions=@{write=$false;action='prediction_all'}; verify_predictions=@{write=$true;action='prediction_verify'}; prediction_stats=@{write=$false;action='prediction_stats'}
} 'prediction'
Patch-Routes 'scp\api\routes\hands_routes.py' '_HANDS_LEDGER' @{
    hands_status=@{write=$false;action='hands_status'}; hands_actions=@{write=$false;action='hands_actions'}; hands_plan=@{write=$false;action='hands_plan'}; hands_execute=@{write=$true;action='hands_execute'}; hands_rollback=@{write=$true;action='hands_rollback'}; planner_status=@{write=$false;action='hands_planner_status'}; planner_list=@{write=$false;action='hands_planner_list'}; planner_get=@{write=$false;action='hands_planner_get'}; planner_create=@{write=$true;action='hands_planner_create'}; planner_run=@{write=$true;action='hands_planner_run'}; planner_parse=@{write=$false;action='hands_planner_parse'}; planner_run_dag=@{write=$true;action='hands_planner_run_dag'}; planner_rollback=@{write=$true;action='hands_planner_rollback'}
} 'hands'
Patch-Routes 'scp\api\routes\pc_controller_routes.py' '_PC_LEDGER' @{
    pc_status=@{write=$false;action='pc_status'}; pc_plan=@{write=$false;action='pc_plan'}; pc_execute=@{write=$true;action='pc_execute'}; pc_read=@{write=$false;action='pc_read'}; pc_write=@{write=$true;action='pc_write'}; pc_kill=@{write=$true;action='pc_kill'}; pc_clear_kill=@{write=$true;action='pc_clear_kill'}
} 'pc-controller-routes'
Patch-Routes 'scp\api\routes\web_control_routes.py' '_WEB_CONTROL_LEDGER' @{
    web_status=@{write=$false;action='web_status'}; search_web=@{write=$false;action='web_search'}; browse=@{write=$true;action='web_browse'}; ask_resilient=@{write=$true;action='ai_ask_resilient'}; ask_ai=@{write=$true;action='ai_ask'}; cross_verify=@{write=$false;action='ai_cross_verify'}
} 'web-control'

Write-Output 'P2_ROUTE_PATCH=PASS'
