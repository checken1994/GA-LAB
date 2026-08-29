"""
Mảnh ghép #39 — Environment Snapshot Manager: thử sai mà không phải trả giá.

TẠI SAO: Git commit chỉ lưu text — KHÔNG lưu trạng thái Database, file JSONL
runtime, hay bất kỳ state nào ngoài code. Nếu Autofix làm hỏng DB trong lúc
thử nghiệm, hệ thống không có đường lui về trạng thái VẬT LÝ trước đó.
SnapshotManager chụp state (code files + SQLite qua backup API) TRƯỚC khi
thực thi hành động từ LLM, và RESTORE về đúng điểm đó khi Reality hô FAIL.

Mọi file được ghi kèm sha256 trong manifest — restore chỉ chấp nhận
manifest hợp lệ (không restore từ snapshot bị giả mạo).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


class SnapshotManager:
    """Chụp + phục hồi trạng thái môi trường (files + SQLite) có provenance."""

    def __init__(self, snapshot_root: str | Path, retain: int = 10):
        self.root = Path(snapshot_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.retain = int(retain)

    def snapshot(self, paths: list[str | Path], tag: str = "pre-action") -> dict[str, Any]:
        """Chụp các file/DB vào snapshots/<tag>-<ts>/. Trả về manifest."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        snap_dir = self.root / f"{tag}-{stamp}-{int(time.time() * 1000) % 10**6:06d}"
        snap_dir.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, Any] = {
            "tag": tag,
            "created_at": time.time(),
            "files": {},
            "databases": {},
        }
        for raw in paths:
            src = Path(raw)
            if not src.exists():
                continue
            if src.suffix in {".sqlite3", ".db", ".sqlite"}:
                # SQLite: backup API (online-safe khi WAL đang chạy)
                dest = snap_dir / (src.name + ".snapshot")
                dst_conn = sqlite3.connect(str(dest))
                try:
                    src_conn = sqlite3.connect(str(src))
                    try:
                        src_conn.backup(dst_conn)
                    finally:
                        src_conn.close()
                finally:
                    dst_conn.close()
                manifest["databases"][str(src)] = {
                    "snapshot_file": str(dest),
                    "sha256": _sha256_file(dest),
                }
            elif src.is_file():
                dest = snap_dir / src.name
                shutil.copy2(src, dest)
                manifest["files"][str(src)] = {
                    "snapshot_file": str(dest),
                    "sha256": _sha256_file(dest),
                }
        manifest_path = snap_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        self._prune()
        return {"snapshot_dir": str(snap_dir), "manifest": manifest}

    def restore(self, snapshot_dir: str | Path) -> dict[str, Any]:
        """Phục hồi từ snapshot. CHỈ chấp nhận manifest khớp sha256 (fail-closed:
        snapshot bị giả mạo/sát hỏng sẽ bị từ chối, không đè dữ liệu sống)."""
        snap = Path(snapshot_dir)
        manifest_path = snap / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError(f"snapshot manifest missing: {snap}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        restored, rejected = [], []
        for original, meta in manifest.get("files", {}).items():
            snap_file = Path(meta["snapshot_file"])
            if not snap_file.exists() or _sha256_file(snap_file) != meta["sha256"]:
                rejected.append(original)
                continue
            Path(original).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snap_file, original)
            restored.append(original)
        for original, meta in manifest.get("databases", {}).items():
            snap_file = Path(meta["snapshot_file"])
            if not snap_file.exists() or _sha256_file(snap_file) != meta["sha256"]:
                rejected.append(original)
                continue
            src_conn = sqlite3.connect(str(snap_file))
            try:
                dst_conn = sqlite3.connect(original)
                try:
                    src_conn.backup(dst_conn)
                finally:
                    dst_conn.close()
            finally:
                src_conn.close()
            restored.append(original)
        if rejected:
            raise RuntimeError(f"snapshot integrity failed for: {rejected} — restore ABORTED")
        return {"restored": restored, "snapshot_dir": str(snap)}

    def latest(self, tag: str | None = None) -> Path | None:
        candidates = sorted(
            (d for d in self.root.iterdir() if d.is_dir() and (tag is None or d.name.startswith(tag))),
            key=lambda d: d.name,
        )
        return candidates[-1] if candidates else None

    def _prune(self) -> None:
        dirs = sorted((d for d in self.root.iterdir() if d.is_dir()), key=lambda d: d.name)
        for old in dirs[: max(0, len(dirs) - self.retain)]:
            shutil.rmtree(old, ignore_errors=True)
