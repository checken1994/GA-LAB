"""Bounded, redacted chat memory persistence for SCP WebSocket sessions.

This is intentionally not a general transcript archive. It stores a short,
redacted conversation window so a reconnect can resume context without writing
provider keys, bearer tokens, raw patches, or unbounded user data to disk.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ChatMemoryStore:
    VERSION = "1.0"
    MAX_CONTENT_CHARS = 800
    MAX_RECORDS = 5000
    RETENTION_SECONDS = 7 * 24 * 60 * 60
    _SECRET_PATTERNS = (
        re.compile(r"(?i)\b(?:openrouter_api_key|scp_auth_password|scp_auth_token_secret|api[_ -]?key|password|token|secret)\s*[:=]\s*[^\s,;]+"),
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b"),
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----.*?-----END [A-Z ]+ PRIVATE KEY-----"),
    )
    _SAFE_METADATA_KEYS = {
        "type", "verdict", "confidence", "domain", "governance", "run_id", "trace_id",
        "agent_run_id", "agent_trace_id", "status", "run_status", "ledger_status",
    }

    def __init__(self, path: str | Path | None = None) -> None:
        raw = str(path or os.environ.get("SCP_CHAT_MEMORY_PATH", "data/chat_memory.jsonl"))
        self.path = Path(raw)
        if not self.path.is_absolute():
            self.path = Path.cwd() / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def redact(cls, value: Any) -> str:
        text = str(value or "")[: cls.MAX_CONTENT_CHARS]
        for pattern in cls._SECRET_PATTERNS:
            text = pattern.sub("[REDACTED]", text)
        return text

    @classmethod
    def _metadata(cls, metadata: dict[str, Any] | None) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in (metadata or {}).items():
            if key not in cls._SAFE_METADATA_KEYS:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe[key] = cls.redact(value)
        return safe

    @staticmethod
    def _record_hash(record: dict[str, Any]) -> str:
        body = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def append(self, session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> bool:
        record = {
            "version": self.VERSION,
            "ts": time.time(),
            "session_id": self.redact(session_id)[:64],
            "role": str(role or "unknown")[:32],
            "content": self.redact(content),
            "metadata": self._metadata(metadata),
        }
        record["record_hash"] = self._record_hash(record)
        try:
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._prune_if_needed()
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("chat_memory_store: append failed for %s: %s", self.path, exc, exc_info=True)
            return False

    def load(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        wanted = self.redact(session_id)[:64]
        cutoff = time.time() - self.RETENTION_SECONDS
        rows: list[dict[str, Any]] = []
        if not self.path.exists():
            return rows
        try:
            for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    # Corrupt record must be visible; skipping keeps the reader resilient.
                    logger.warning("chat_memory_store: corrupt line in %s", self.path, exc_info=True)
                    continue
                if row.get("session_id") != wanted or float(row.get("ts", 0)) < cutoff:
                    continue
                rows.append({
                    "role": str(row.get("role", "unknown"))[:32],
                    "content": self.redact(row.get("content", "")),
                    "timestamp": float(row.get("ts", 0)),
                    "metadata": self._metadata(row.get("metadata", {})),
                })
        except OSError as exc:
            logger.warning("chat_memory_store: read failed for %s: %s", self.path, exc, exc_info=True)
            return []
        return rows[-max(1, min(int(limit), 100)) :]

    def _prune_if_needed(self) -> None:
        try:
            if self.path.stat().st_size < 2_000_000:
                return
            cutoff = time.time() - self.RETENTION_SECONDS
            rows: list[dict[str, Any]] = []
            for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    # Corrupt record must be visible; skipping keeps the reader resilient.
                    logger.warning("chat_memory_store: corrupt line in %s", self.path, exc_info=True)
                    continue
                if float(row.get("ts", 0)) >= cutoff:
                    rows.append(row)
            rows = rows[-self.MAX_RECORDS :]
            fd, temp_name = tempfile.mkstemp(prefix="chat-memory-", suffix=".jsonl", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                    for row in rows:
                        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        except (OSError, TypeError, ValueError) as exc:
            # silent-by-design: prune is best-effort; failure must not turn chat
            # into an unbounded memory path, but it must be observable.
            logger.debug("chat_memory_store: prune failed for %s (non-fatal): %s", self.path, exc, exc_info=True)
            return


__all__ = ["ChatMemoryStore"]
