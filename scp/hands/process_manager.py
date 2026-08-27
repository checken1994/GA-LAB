"""SCP Hands v3.4 managed process primitives.

Only fixed, catalogued commands can be started. A process can be stopped only
when its PID is owned by this manager instance; arbitrary PID termination is
never exposed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class ManagedProcessManager:
    def __init__(self, data_dir: Path, project_root: Path) -> None:
        self.data_dir = data_dir
        self.project_root = project_root
        self.ledger_path = data_dir / "processes.jsonl"
        self._owned: dict[int, subprocess.Popen[Any]] = {}
        self._meta: dict[int, dict[str, Any]] = {}
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.catalog: dict[str, list[str]] = {
            "hands_probe": [sys.executable, str(project_root / "scp" / "hands" / "process_probe.py")],
        }

    def catalog_public(self) -> list[dict[str, Any]]:
        return [{"commandId": key, "description": "Fixed SCP-owned diagnostic process", "approval": "capability>=3 and approved"} for key in sorted(self.catalog)]

    def _record(self, event: str, payload: dict[str, Any]) -> None:
        record = {"timestamp": time.time(), "event": event, **payload}
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, default=str) + "\n")

    @staticmethod
    def _alive(process: subprocess.Popen[Any]) -> bool:
        return process.poll() is None

    def start(self, command_id: str) -> dict[str, Any]:
        command = self.catalog.get(command_id)
        if not command:
            result = {"success": False, "error": "Unknown managed command"}
            self._record("PROCESS_START_BLOCKED", {"commandId": command_id, **result})
            return result
        try:
            kwargs: dict[str, Any] = {
                "cwd": str(self.project_root),
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "env": {**os.environ, "SCP_HANDS_OWNED": "1", "SCP_HANDS_COMMAND_ID": command_id},
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen(command, **kwargs)
            now = time.time()
            metadata = {"pid": process.pid, "commandId": command_id, "startedAt": now, "command": command}
            self._owned[process.pid] = process
            self._meta[process.pid] = metadata
            result = {"success": True, "pid": process.pid, "commandId": command_id, "startedAt": now, "owned": True}
            self._record("PROCESS_STARTED", result)
            return result
        except OSError as exc:
            result = {"success": False, "commandId": command_id, "error": str(exc)}
            self._record("PROCESS_START_FAILED", result)
            return result

    def info(self, pid: int) -> dict[str, Any]:
        process = self._owned.get(pid)
        metadata = self._meta.get(pid, {"pid": pid, "owned": False})
        if process is not None:
            return {"success": True, **metadata, "owned": True, "alive": self._alive(process), "returnCode": process.poll()}
        return {"success": False, "pid": pid, "owned": False, "error": "PID is not owned by Hands"}

    def list_owned(self) -> dict[str, Any]:
        processes = []
        for pid, process in list(self._owned.items()):
            item = {**self._meta.get(pid, {"pid": pid}), "owned": True, "alive": self._alive(process), "returnCode": process.poll()}
            processes.append(item)
            if process.poll() is not None:
                self._owned.pop(pid, None)
                self._meta.pop(pid, None)
        return {"success": True, "processes": processes, "count": len(processes), "catalog": self.catalog_public()}

    def stop(self, pid: int) -> dict[str, Any]:
        process = self._owned.get(pid)
        if process is None:
            result = {"success": False, "pid": pid, "error": "PID is not owned by Hands; arbitrary stop is blocked"}
            self._record("PROCESS_STOP_BLOCKED", result)
            return result
        try:
            if self._alive(process):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            result = {"success": True, "pid": pid, "owned": True, "stopped": True, "returnCode": process.poll()}
            self._record("PROCESS_STOPPED", result)
            self._owned.pop(pid, None)
            self._meta.pop(pid, None)
            return result
        except OSError as exc:
            result = {"success": False, "pid": pid, "owned": True, "error": str(exc)}
            self._record("PROCESS_STOP_FAILED", result)
            return result
