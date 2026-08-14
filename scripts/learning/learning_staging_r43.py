from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SCP R43 isolated learning staging")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--count", type=int, default=2)
    p.add_argument("--run-provider", action="store_true", help="run bounded Ollama/LLM provider cycle")
    p.add_argument("--provider-timeout", type=int, default=5, help="provider timeout seconds; staging always overrides OLLAMA_TIMEOUT")
    p.add_argument("--stage", type=Path, default=None)
    return p.parse_args()


def copy_db(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        shutil.copy2(source, target)
    else:
        sqlite3.connect(str(target)).close()


def safe_db_counts(db: Path) -> dict[str, int | str | None]:
    result: dict[str, int | str | None] = {}
    if not db.exists():
        return result
    try:
        with sqlite3.connect(str(db), timeout=5) as con:
            for table in ("knowledge", "experiences", "error_history", "memory"):
                try:
                    result[table] = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                except sqlite3.Error:
                    result[table] = None
    except sqlite3.Error as exc:
        result["error"] = type(exc).__name__
    return result


async def run_provider_cycle(root: Path, stage: Path, count: int) -> dict:
    sys.path.insert(0, str(root))
    from scp.core.fast_learning_engine import FastLearningEngine

    engine = FastLearningEngine(scp_db_path=str(stage / "v13.db"), data_dir=str(stage))
    started = time.time()
    result = await engine.fast_learning_cycle(count=max(1, min(count, 3)))
    result["elapsed_ms"] = int((time.time() - started) * 1000)
    result["stats"] = engine.stats()
    return result


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    stage = (args.stage or root / ".private-secrets" / "release-audit" / "learning-staging-r43").resolve()
    stage.mkdir(parents=True, exist_ok=True)
    source_db = root / "data" / "v13.db"
    stage_db = stage / "v13.db"
    if not stage_db.exists():
        copy_db(source_db, stage_db)
    manifest = {
        "stage": str(stage),
        "source_db": str(source_db),
        "stage_db": str(stage_db),
        "source_db_sha256": sha256(source_db),
        "stage_db_sha256_before": sha256(stage_db),
        "created_at": utc_now(),
        "dangerous_flags": {
            "SCP_DEV_MODE": "0",
            "SCP_SKIP_STARTUP_GATE": "0",
            "SCP_AUTO_APPROVE_TIER3": "0",
            "SCP_TIER3_ALLOW_RELAXATION": "0",
            "SCP_TIER3_ALLOW_BAREEXCEPTPASS": "0",
        },
        "closed_loop": "1",
        "provider_run_requested": bool(args.run_provider),
        "count_bound": max(1, min(args.count, 3)),
        "source_counts": safe_db_counts(source_db),
        "stage_counts_before": safe_db_counts(stage_db),
    }
    (stage / "staging_env.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.run_provider:
        os.environ["SCP_DEV_MODE"] = "0"
        os.environ["SCP_SKIP_STARTUP_GATE"] = "0"
        os.environ["SCP_AUTO_APPROVE_TIER3"] = "0"
        os.environ["SCP_TIER3_ALLOW_RELAXATION"] = "0"
        os.environ["SCP_TIER3_ALLOW_BAREEXCEPTPASS"] = "0"
        os.environ["SCP_ENABLE_CLOSED_LOOP"] = "1"
        os.environ["OLLAMA_TIMEOUT"] = str(max(1, min(args.provider_timeout, 30)))
        manifest["provider_timeout_seconds"] = int(os.environ["OLLAMA_TIMEOUT"])
        result = asyncio.run(run_provider_cycle(root, stage, args.count))
        manifest["provider_result"] = {
            "asked": result.get("asked"),
            "verified": result.get("verified"),
            "stored": result.get("stored"),
            "adaptive_mode": result.get("adaptive_mode"),
            "elapsed_ms": result.get("elapsed_ms"),
        }
    manifest["stage_counts_after"] = safe_db_counts(stage_db)
    manifest["stage_db_sha256_after"] = sha256(stage_db)
    manifest["completed_at"] = utc_now()
    (stage / "staging_env.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
