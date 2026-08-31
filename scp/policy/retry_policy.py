# -*- coding: utf-8 -*-
"""Step 3: Auto-retry policy for WAITING_APPROVAL tasks.

When a plan step is stuck in WAITING_APPROVAL beyond SCP_RETRY_TIMEOUT_SEC,
this module auto-retries up to SCP_MAX_AUTO_RETRIES times.
"""
from __future__ import annotations

import logging
import os
import time
import threading
from typing import Callable

logger = logging.getLogger("scp.policy.retry_policy")

RETRY_TIMEOUT_SEC = float(os.environ.get("SCP_RETRY_TIMEOUT_SEC", "300"))
MAX_AUTO_RETRIES = int(os.environ.get("SCP_MAX_AUTO_RETRIES", "3"))


class RetryPolicy:
    def __init__(self, get_plans_fn: Callable[[], list], retry_fn: Callable[[str, str], None]):
        self._get_plans = get_plans_fn
        self._retry_fn = retry_fn
        self._retry_counts: dict[str, int] = {}
        self._waiting_since: dict[str, float] = {}
        self._lock = threading.Lock()

    def observe(self, plan: dict) -> None:
        plan_id = str(plan.get("planId", ""))
        state = str(plan.get("state", ""))
        with self._lock:
            if state == "WAITING_APPROVAL":
                self._waiting_since.setdefault(plan_id, time.monotonic())
            else:
                self._waiting_since.pop(plan_id, None)

    def check_and_retry(self) -> list[str]:
        retried: list[str] = []
        now = time.monotonic()
        with self._lock:
            expired = [pid for pid, ts in self._waiting_since.items() if (now - ts) >= RETRY_TIMEOUT_SEC]
        for plan_id in expired:
            with self._lock:
                count = self._retry_counts.get(plan_id, 0)
                if count >= MAX_AUTO_RETRIES:
                    logger.warning("[retry_policy] plan=%s max retries reached", plan_id)
                    self._waiting_since.pop(plan_id, None)
                    continue
                self._retry_counts[plan_id] = count + 1
                self._waiting_since.pop(plan_id, None)
            plans = self._get_plans()
            plan = next((p for p in plans if str(p.get("planId")) == plan_id), None)
            if not plan:
                continue
            step = next((s for s in plan.get("steps", []) if s.get("state") == "WAITING_APPROVAL"), None)
            if not step:
                continue
            step_id = str(step.get("stepId", ""))
            logger.info("[retry_policy] auto-retry plan=%s step=%s (attempt %d/%d)", plan_id, step_id, self._retry_counts[plan_id], MAX_AUTO_RETRIES)
            try:
                self._retry_fn(plan_id, step_id)
                retried.append(plan_id)
            except Exception:
                logger.exception("[retry_policy] retry_fn failed plan=%s step=%s", plan_id, step_id)
        return retried


def start_retry_monitor(get_plans_fn: Callable[[], list], retry_fn: Callable[[str, str], None], interval_sec: float = 60.0) -> RetryPolicy:
    policy = RetryPolicy(get_plans_fn, retry_fn)

    def _loop() -> None:
        while True:
            time.sleep(interval_sec)
            try:
                policy.check_and_retry()
            except Exception:
                logger.exception("[retry_policy] monitor loop error")

    t = threading.Thread(target=_loop, daemon=True, name="scp-retry-monitor")
    t.start()
    logger.info("[retry_policy] started (timeout=%ss, max=%d)", RETRY_TIMEOUT_SEC, MAX_AUTO_RETRIES)
    return policy