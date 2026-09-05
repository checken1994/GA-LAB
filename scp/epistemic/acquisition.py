"""S03 Internet Acquisition runtime (spec CE-S03-01 / CE-S03-02).

Implements the acquisition authorities on top of the existing epistemic
foundations (reuse, not reimplementation):

  - ``AcquisitionScheduler`` decides WHEN to acquire: PULL (explicit
    question / missing evidence, gain 1.0) vs CURIOSITY (uncertainty-driven,
    gain = uncertainty x novelty, capped items). A resource-budget pre-check
    happens here; exhaustion yields WAIT_RESOURCE with the pending need
    preserved — never a silent skip (CE-S03-02 WAIT_RESOURCE_or_BLOCKED).
  - ``SourcePolicy`` is the per-domain gate: blocklist > allowlist (default
    DENY for unknown hosts — 'discovered_host -> automatic_egress_allow' is a
    forbidden path), mechanical per-domain rate limits (reuse of the
    ``TokenBucket`` from the learning loop) and freshness requirements
    (min refresh interval before a re-fetch is allowed).
  - ``AcquisitionPipeline`` runs the CE-S03-01 authority path:
    bounded fetch (canonical ``scp.core.url_fetcher``) -> quarantine scan
    (``top_systems_learning.inspect_untrusted``) -> immutable evidence
    occurrence (``GovernedEvidenceWriter``) -> source identity
    (``SourceStore``) -> lineage assessment (``LineageStore``, default
    UNKNOWN_INDEPENDENCE) -> claim-extraction trigger (the ONLY path towards
    knowledge; never a direct knowledge write, never a direct action).
  - ``FreeAPIQualifier`` walks DISCOVERED -> HTTPS check -> auth check ->
    bounded health probe -> schema observation -> VERIFIED_FREE_API. Any
    unknown/failure step lands in QUARANTINE; an unverified host is never
    auto-trusted ('unqualified_api_dispatch' forbidden).

Fail-closed invariants:
  - no fetch without a policy ALLOW + budget reserve + rate-limit token;
  - quarantined content is stored as provenance evidence with
    ``quarantined=True`` (like the learning-loop ledger) and its
    claim-extraction trigger is suppressed — it can never enter knowledge;
  - budget caps are fixed at construction: no self-increase API exists;
  - every terminal state is explicit (WAIT_RESOURCE / BLOCKED_POLICY /
    SKIPPED_* / QUARANTINED / FAILED) — nothing is silently dropped.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable
from urllib.parse import urlsplit

from scp.contracts.data_class import DataClass
from scp.contracts.time import now_utc_iso
from scp.core.top_systems_learning import TokenBucket, inspect_untrusted
from scp.epistemic.lineage import IndependenceStatus, LineageStore
from scp.epistemic.source_identity import SourceKind, SourceStore, canonicalize_url

COLLECTOR_ID = "acquisition-runtime"
COLLECTOR_VERSION = "s03-m7-1"

# Hard upper bound for a single fetch, independent of caller configuration.
ABSOLUTE_MAX_FETCH_BYTES = 2_000_000


class AcquisitionTrigger(str, Enum):
    PULL = "PULL"            # explicit question / missing evidence (CE-S03-01)
    CURIOSITY = "CURIOSITY"  # uncertainty-driven exploration (capped)


class AcquisitionStatus(str, Enum):
    ACQUIRED = "ACQUIRED"
    QUARANTINED = "QUARANTINED"
    WAIT_RESOURCE = "WAIT_RESOURCE"      # preserve_pending_need (CE-S03-02)
    BLOCKED_POLICY = "BLOCKED_POLICY"    # SourcePolicy deny (fail-closed)
    SKIPPED_FRESH = "SKIPPED_FRESH"      # freshness window not elapsed yet
    SKIPPED_LOW_GAIN = "SKIPPED_LOW_GAIN"  # curiosity below gain threshold
    FAILED = "FAILED"                    # fetch/storage error (per-item)


def _clamp01(value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def question_digest(question: str) -> str:
    return "sha256:" + hashlib.sha256(str(question or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Resource budget (X03_RESOURCE_GOVERNOR minimum world budget)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BudgetReservation:
    ok: bool
    fetch_cap_bytes: int
    reasons: tuple[str, ...] = ()


class AcquisitionBudget:
    """Fixed-cap acquisition budget: (max_fetches, max_total_bytes).

    Counts are ATTEMPT-based: a failed fetch still consumes the fetch slot
    (attempts cost real resources), while only successful bytes count against
    the byte total. The caps are fixed at construction and there is NO API to
    raise them — 'budget_self_increase' is a must-not-effect (CE-S03-02).
    """

    def __init__(self, *, max_fetches: int, max_total_bytes: int) -> None:
        if int(max_fetches) <= 0 or int(max_total_bytes) <= 0:
            raise ValueError("budget caps must be positive")
        self.max_fetches = int(max_fetches)
        self.max_total_bytes = int(max_total_bytes)
        self._fetches_used = 0
        self._bytes_used = 0
        self._lock = threading.Lock()

    def reserve(self) -> BudgetReservation:
        """Atomically claim one fetch attempt and return its byte cap."""
        with self._lock:
            if self._fetches_used >= self.max_fetches:
                return BudgetReservation(False, 0, ("fetch_budget_exhausted",))
            remaining_bytes = self.max_total_bytes - self._bytes_used
            if remaining_bytes <= 0:
                return BudgetReservation(False, 0, ("byte_budget_exhausted",))
            self._fetches_used += 1
            return BudgetReservation(True, min(remaining_bytes, ABSOLUTE_MAX_FETCH_BYTES))

    def commit_bytes(self, byte_count: int) -> None:
        with self._lock:
            self._bytes_used += max(0, int(byte_count))

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "max_fetches": self.max_fetches,
                "max_total_bytes": self.max_total_bytes,
                "fetches_used": self._fetches_used,
                "bytes_used": self._bytes_used,
                "fetches_left": max(0, self.max_fetches - self._fetches_used),
                "bytes_left": max(0, self.max_total_bytes - self._bytes_used),
            }

    @property
    def exhausted(self) -> bool:
        snap = self.snapshot()
        return snap["fetches_left"] <= 0 or snap["bytes_left"] <= 0


# ---------------------------------------------------------------------------
# AcquisitionScheduler — WHEN to acquire (pull vs curiosity, gain, budget)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AcquisitionRequest:
    question: str
    trigger: AcquisitionTrigger
    urls: tuple[str, ...] = ()
    uncertainty: float = 0.0   # 0..1 — how uncertain the current answer is
    novelty: float = 0.5       # 0..1 — how novel the candidate source area is
    task_id: str | None = None
    trace_id: str | None = None
    max_items: int = 1

    def __post_init__(self) -> None:
        if not str(self.question or "").strip():
            raise ValueError("acquisition request requires a question/need")
        urls = tuple(str(u or "").strip() for u in self.urls if str(u or "").strip())
        if not urls:
            raise ValueError("acquisition request requires at least one candidate URL")
        object.__setattr__(self, "urls", urls)


@dataclass(frozen=True)
class ScheduleDecision:
    scheduled: bool
    status: AcquisitionStatus | None
    information_gain: float
    effective_max_items: int
    reasons: tuple[str, ...] = ()


class AcquisitionScheduler:
    """Pull beats curiosity; curiosity must clear a gain floor and is capped.

    'curiosity -> unbounded_monitoring' is a forbidden path: curiosity
    requests are hard-capped at ``curiosity_max_items`` regardless of what the
    caller asked for, and low-gain curiosity is explicitly NOT scheduled
    (returned as SKIPPED_LOW_GAIN — never silently dropped).
    """

    def __init__(
        self,
        *,
        budget: AcquisitionBudget | None = None,
        min_curiosity_gain: float = 0.15,
        curiosity_max_items: int = 1,
        max_items_per_request: int = 4,
    ) -> None:
        if not 0.0 <= float(min_curiosity_gain) <= 1.0:
            raise ValueError("min_curiosity_gain must be within [0, 1]")
        if int(curiosity_max_items) < 1 or int(max_items_per_request) < 1:
            raise ValueError("item caps must be >= 1")
        self.budget = budget
        self.min_curiosity_gain = float(min_curiosity_gain)
        self.curiosity_max_items = int(curiosity_max_items)
        self.max_items_per_request = int(max_items_per_request)

    def information_gain(self, request: AcquisitionRequest) -> float:
        """Deterministic gain score. PULL is an explicit need -> 1.0."""
        if request.trigger is AcquisitionTrigger.PULL:
            return 1.0
        return round(_clamp01(request.uncertainty) * _clamp01(request.novelty), 6)

    def schedule(self, request: AcquisitionRequest) -> ScheduleDecision:
        trigger = request.trigger if isinstance(request.trigger, AcquisitionTrigger) \
            else AcquisitionTrigger(str(request.trigger).strip().upper())
        gain = self.information_gain(request)
        if trigger is AcquisitionTrigger.CURIOSITY and gain < self.min_curiosity_gain:
            return ScheduleDecision(
                scheduled=False,
                status=AcquisitionStatus.SKIPPED_LOW_GAIN,
                information_gain=gain,
                effective_max_items=0,
                reasons=(
                    f"curiosity_gain_{gain}_below_threshold_{self.min_curiosity_gain}",
                    "curiosity -> unbounded_monitoring forbidden: low-gain exploration is not scheduled",
                ),
            )
        cap = self.max_items_per_request
        if trigger is AcquisitionTrigger.CURIOSITY:
            cap = min(cap, self.curiosity_max_items)
        effective_items = max(1, min(int(request.max_items), cap))
        reasons = [f"trigger_{trigger.value}", f"information_gain_{gain}"]
        if trigger is AcquisitionTrigger.CURIOSITY:
            reasons.append(f"items_capped_to_{effective_items}_curiosity")
        # Resource budget pre-check (CE-S03-02): exhausted budget is an
        # explicit WAIT_RESOURCE with the pending need preserved.
        if self.budget is not None and self.budget.exhausted:
            return ScheduleDecision(
                scheduled=False,
                status=AcquisitionStatus.WAIT_RESOURCE,
                information_gain=gain,
                effective_max_items=effective_items,
                reasons=tuple(reasons + ["resource_budget_exhausted", "pending_need_preserved"]),
            )
        return ScheduleDecision(
            scheduled=True,
            status=None,
            information_gain=gain,
            effective_max_items=effective_items,
            reasons=tuple(reasons),
        )


# ---------------------------------------------------------------------------
# SourcePolicy — allowlist/blocklist, per-source rate limits, freshness
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


class SourcePolicy:
    """Default-DENY domain gate for acquisition targets.

    - blocklist wins over allowlist (exact-host match, both fail-closed);
    - a host that is in neither list is DENIED: discovery never auto-allows
      egress ('discovered_host -> automatic_egress_allow' forbidden);
    - per-domain mechanical rate limits reuse the learning-loop TokenBucket;
    - freshness: a domain with ``min_refresh_seconds`` refuses re-fetches
      until the window elapsed (revalidation must be NEEDED, not habitual);
    - qualified free-API hosts are registered here by FreeAPIQualifier with
      their qualification provenance — the only way an API host enters the
      allowlist without a human-configured allowlist entry.
    """

    def __init__(
        self,
        *,
        allow_domains: tuple[str, ...] | list[str] = (),
        block_domains: tuple[str, ...] | list[str] = (),
        default_rate: tuple[int, float] = (10, 6.0),
        domain_rates: dict[str, tuple[int, float]] | None = None,
        rate_max_wait: float = 0.5,
        default_min_refresh_seconds: float = 0.0,
        domain_min_refresh_seconds: dict[str, float] | None = None,
        max_content_bytes: int = 1_000_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if int(max_content_bytes) <= 0:
            raise ValueError("max_content_bytes must be positive")
        self._allow = {self._clean_domain(d) for d in allow_domains}
        self._block = {self._clean_domain(d) for d in block_domains}
        overlap = self._allow & self._block
        if overlap:
            raise ValueError(f"domains cannot be both allowed and blocked: {sorted(overlap)}")
        self._default_rate = (int(default_rate[0]), float(default_rate[1]))
        self._domain_rates = {
            self._clean_domain(d): (int(c), float(r)) for d, (c, r) in (domain_rates or {}).items()
        }
        self._rate_max_wait = float(rate_max_wait)
        self._default_min_refresh = float(default_min_refresh_seconds)
        self._domain_min_refresh = {
            self._clean_domain(d): float(s) for d, s in (domain_min_refresh_seconds or {}).items()
        }
        self._max_content_bytes = int(max_content_bytes)
        self._clock = clock
        self._buckets: dict[str, TokenBucket] = {}
        self._last_fetch: dict[str, float] = {}
        self._qualified_apis: dict[str, dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _clean_domain(domain: str) -> str:
        host = str(domain or "").strip().lower().rstrip(".")
        if not host or "/" in host or "@" in host:
            raise ValueError(f"invalid domain: {domain!r}")
        return host

    @staticmethod
    def host_of(url: str) -> str:
        parts = urlsplit(str(url or "").strip())
        if parts.scheme not in {"http", "https"}:
            raise ValueError(f"scheme not allowed: {parts.scheme!r}")
        if not parts.hostname:
            raise ValueError("URL must contain a hostname")
        if parts.username is not None or parts.password is not None:
            raise ValueError("URL must not contain credentials")
        return parts.hostname.strip().lower().rstrip(".")

    def evaluate_url(self, url: str) -> PolicyDecision:
        host = self.host_of(url)  # raises on invalid/credential URLs -> deny
        with self._lock:
            if host in self._block:
                return PolicyDecision(False, f"domain_blocklisted:{host}")
            if host in self._allow:
                return PolicyDecision(True, f"domain_allowlisted:{host}")
            qualified = self._qualified_apis.get(host)
            if qualified:
                return PolicyDecision(
                    True,
                    f"qualified_free_api:{host}:{qualified.get('qualification', 'VERIFIED_FREE_API')}",
                )
        return PolicyDecision(
            False,
            f"domain_not_in_allowlist:{host} (discovery never auto-allows egress)",
        )

    def rate_limit_for(self, host: str) -> TokenBucket:
        with self._lock:
            bucket = self._buckets.get(host)
            if bucket is None:
                capacity, refill = self._domain_rates.get(host, self._default_rate)
                bucket = TokenBucket(capacity=capacity, refill_seconds=refill)
                self._buckets[host] = bucket
        return bucket

    @property
    def rate_max_wait(self) -> float:
        return self._rate_max_wait

    def min_refresh_seconds(self, host: str) -> float:
        with self._lock:
            return self._domain_min_refresh.get(host, self._default_min_refresh)

    def note_fetch(self, host: str, *, at: float | None = None) -> None:
        with self._lock:
            self._last_fetch[host] = float(at) if at is not None else self._clock()

    def is_stale(self, host: str) -> tuple[bool, float]:
        """(is_stale, seconds_since_last_fetch). Never-fetched -> stale."""
        with self._lock:
            last = self._last_fetch.get(host)
        if last is None:
            return True, float("inf")
        age = self._clock() - last
        return age >= self.min_refresh_seconds(host), age

    def register_qualified_api(self, host: str, *, base_url: str, evidence_id: str) -> None:
        """Called ONLY by FreeAPIQualifier on full verification success."""
        host = self._clean_domain(host)
        with self._lock:
            if host in self._block:
                raise ValueError(f"cannot qualify a blocklisted domain: {host}")
            self._qualified_apis[host] = {
                "qualification": "VERIFIED_FREE_API",
                "base_url": str(base_url),
                "evidence_id": str(evidence_id),
                "qualified_at": now_utc_iso(),
            }

    def is_qualified_free_api(self, host: str) -> bool:
        with self._lock:
            return self._clean_domain(host) in self._qualified_apis

    @property
    def max_content_bytes(self) -> int:
        return self._max_content_bytes


# ---------------------------------------------------------------------------
# AcquisitionPipeline — CE-S03-01 authority path
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AcquisitionResult:
    status: AcquisitionStatus
    trigger: AcquisitionTrigger
    url: str
    source_id: str | None = None
    evidence_id: str | None = None
    information_gain: float = 0.0
    quarantined: bool = False
    quarantine_reason: str = ""
    claim_extraction: str = "NOT_RUN"
    pending: bool = False
    bytes_fetched: int = 0
    reasons: tuple[str, ...] = ()


class AcquisitionPipeline:
    """fetch -> quarantine -> evidence -> source identity -> lineage -> claims.

    The pipeline NEVER writes to a knowledge store itself: the only path
    towards knowledge is the ``claim_trigger`` hook, fired exclusively for
    non-quarantined ACQUIRED occurrences ('crawler -> direct_knowledge' and
    'direct_knowledge_write' are forbidden paths).
    """

    def __init__(
        self,
        *,
        writer,                      # GovernedEvidenceWriter (privacy-governed)
        lineage: LineageStore,
        source_store: SourceStore,
        policy: SourcePolicy,
        scheduler: AcquisitionScheduler | None = None,
        budget: AcquisitionBudget | None = None,
        fetcher: Callable[[str, int], bytes] | None = None,
        claim_trigger: Callable[[AcquisitionResult], None] | None = None,
    ) -> None:
        self.writer = writer
        self.lineage = lineage
        self.source_store = source_store
        self.policy = policy
        self.scheduler = scheduler or AcquisitionScheduler(budget=budget)
        self.budget = budget
        self.claim_trigger = claim_trigger
        self._fetcher = fetcher or self._default_fetcher
        self._known_sources: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _default_fetcher(url: str, max_bytes: int) -> bytes:
        # Single canonical SSRF-safe fetcher — do NOT create a second impl.
        from scp.core.url_fetcher import _safe_fetch_url

        return _safe_fetch_url(url, max_bytes=max_bytes, timeout=8.0)

    # ------------------------------------------------------------------
    def acquire(self, request: AcquisitionRequest) -> list[AcquisitionResult]:
        decision = self.scheduler.schedule(request)
        if not decision.scheduled:
            return [
                AcquisitionResult(
                    status=decision.status or AcquisitionStatus.FAILED,
                    trigger=request.trigger,
                    url=request.urls[0],
                    information_gain=decision.information_gain,
                    pending=decision.status is AcquisitionStatus.WAIT_RESOURCE,
                    reasons=decision.reasons,
                )
            ]
        results: list[AcquisitionResult] = []
        for url in request.urls[: decision.effective_max_items]:
            results.append(self._acquire_one(request, url, decision))
        return results

    # ------------------------------------------------------------------
    def _acquire_one(
        self, request: AcquisitionRequest, url: str, decision: ScheduleDecision
    ) -> AcquisitionResult:
        # 1) SourcePolicy gate (fail-closed; invalid URL raises -> deny).
        try:
            policy_decision = self.policy.evaluate_url(url)
        except ValueError as exc:
            policy_decision = PolicyDecision(False, f"invalid_url:{exc}")
        if not policy_decision.allowed:
            return AcquisitionResult(
                status=AcquisitionStatus.BLOCKED_POLICY,
                trigger=request.trigger,
                url=url,
                information_gain=decision.information_gain,
                reasons=(policy_decision.reason,),
            )

        host = self.policy.host_of(url)

        # 2) Freshness requirement: recent content is not re-fetched.
        stale, age = self.policy.is_stale(host)
        if not stale:
            return AcquisitionResult(
                status=AcquisitionStatus.SKIPPED_FRESH,
                trigger=request.trigger,
                url=url,
                information_gain=decision.information_gain,
                reasons=(
                    f"domain_fresh:{host}",
                    f"age_{age:.1f}s_below_min_refresh",
                    "explicit skip — content still within freshness window",
                ),
            )

        # 3) Mechanical per-source rate limit (TokenBucket, fail-closed).
        try:
            self.policy.rate_limit_for(host).acquire(max_wait=self.policy.rate_max_wait)
        except RuntimeError as exc:
            return AcquisitionResult(
                status=AcquisitionStatus.WAIT_RESOURCE,
                trigger=request.trigger,
                url=url,
                information_gain=decision.information_gain,
                pending=True,
                reasons=(f"local_rate_limit:{host}", str(exc), "pending_need_preserved"),
            )

        # 4) Resource budget reserve (attempt-based; no self-increase).
        if self.budget is not None:
            reservation = self.budget.reserve()
            if not reservation.ok:
                return AcquisitionResult(
                    status=AcquisitionStatus.WAIT_RESOURCE,
                    trigger=request.trigger,
                    url=url,
                    information_gain=decision.information_gain,
                    pending=True,
                    reasons=tuple(reservation.reasons) + ("pending_need_preserved",),
                )
            fetch_cap = min(self.policy.max_content_bytes, reservation.fetch_cap_bytes)
        else:
            fetch_cap = self.policy.max_content_bytes
        if fetch_cap <= 0:
            return AcquisitionResult(
                status=AcquisitionStatus.WAIT_RESOURCE,
                trigger=request.trigger,
                url=url,
                information_gain=decision.information_gain,
                pending=True,
                reasons=("byte_budget_exhausted", "pending_need_preserved"),
            )

        # 5) Bounded fetch via the canonical SSRF-safe fetcher.
        try:
            content = self._fetcher(url, fetch_cap)
        except Exception as exc:  # fetcher failure is a per-item, fail-closed event
            return AcquisitionResult(
                status=AcquisitionStatus.FAILED,
                trigger=request.trigger,
                url=url,
                information_gain=decision.information_gain,
                reasons=(f"fetch_failed:{type(exc).__name__}:{str(exc)[:160]}",),
            )
        if not content:
            return AcquisitionResult(
                status=AcquisitionStatus.FAILED,
                trigger=request.trigger,
                url=url,
                information_gain=decision.information_gain,
                reasons=("fetch_failed:empty_body",),
            )
        if len(content) > fetch_cap:
            return AcquisitionResult(
                status=AcquisitionStatus.FAILED,
                trigger=request.trigger,
                url=url,
                information_gain=decision.information_gain,
                reasons=(f"fetch_failed:response_exceeds_cap_{fetch_cap}",),
            )
        if self.budget is not None:
            self.budget.commit_bytes(len(content))
        self.policy.note_fetch(host)

        # 6) Quarantine scan (deterministic, pre-persistence).
        text = content.decode("utf-8", errors="replace")
        quarantined, quarantine_reason = inspect_untrusted(text)

        # 7) Source identity (canonical registry entry).
        try:
            source = self.source_store.register(
                kind=SourceKind.WEB_DOCUMENT,
                identity=url,
                metadata={"host": host, "collector": COLLECTOR_ID},
            )
        except ValueError as exc:
            return AcquisitionResult(
                status=AcquisitionStatus.FAILED,
                trigger=request.trigger,
                url=url,
                information_gain=decision.information_gain,
                quarantined=quarantined,
                quarantine_reason=quarantine_reason,
                reasons=(f"source_identity_failed:{exc}",),
            )

        # 8) Lineage assessment: relations to every previously acquired
        # source DEFAULT to the DB UNKNOWN_INDEPENDENCE — never inferred.
        lineage_summary = self._assess_lineage(source.source_id)

        # 9) Immutable evidence occurrence (privacy-governed write).
        record = self.writer.observe(
            kind="HTTP_RESPONSE",
            content=content,
            collector_id=COLLECTOR_ID,
            collector_version=COLLECTOR_VERSION,
            source_id=source.source_id,
            task_id=request.task_id,
            trace_id=request.trace_id,
            data_class=DataClass.PUBLIC,
            metadata={
                "observation_type": "internet_acquisition",
                "trigger": request.trigger.value,
                "question_sha256": question_digest(request.question),
                "url_canonical": source.canonical_identity,
                "host": host,
                "acquisition_status": AcquisitionStatus.QUARANTINED.value
                if quarantined
                else AcquisitionStatus.ACQUIRED.value,
                "quarantined": quarantined,
                "quarantine_reason": quarantine_reason,
                "bytes_fetched": len(content),
                "lineage": lineage_summary,
            },
            mime_type="application/octet-stream",
        )

        status = AcquisitionStatus.QUARANTINED if quarantined else AcquisitionStatus.ACQUIRED
        result = AcquisitionResult(
            status=status,
            trigger=request.trigger,
            url=url,
            source_id=source.source_id,
            evidence_id=record["evidence_id"],
            information_gain=decision.information_gain,
            quarantined=quarantined,
            quarantine_reason=quarantine_reason,
            claim_extraction="NOT_RUN",
            bytes_fetched=len(content),
            reasons=(
                f"bounded_fetch_{len(content)}_of_cap_{fetch_cap}",
                policy_decision.reason,
                f"lineage_default_{IndependenceStatus.UNKNOWN_INDEPENDENCE.value}",
            )
            + ((f"quarantine:{quarantine_reason}",) if quarantined else ()),
        )

        # 10) Claim extraction trigger — the only road to knowledge, and it
        # is structurally closed for quarantined content.
        if quarantined:
            result = replace(result, claim_extraction="SUPPRESSED_QUARANTINE")
        elif self.claim_trigger is not None:
            try:
                self.claim_trigger(result)
                result = replace(result, claim_extraction="TRIGGERED")
            except Exception as exc:
                result = replace(
                    result,
                    claim_extraction="ERROR",
                    reasons=result.reasons
                    + (f"claim_trigger_error:{type(exc).__name__}:{str(exc)[:120]}",),
                )
        else:
            result = replace(result, claim_extraction="NO_TRIGGER_CONFIGURED")
        return result

    # ------------------------------------------------------------------
    def _assess_lineage(self, source_id: str) -> dict:
        with self._lock:
            peers = sorted(self._known_sources - {source_id})
        if peers:
            # ensure_relation uses the DB DEFAULT: UNKNOWN_INDEPENDENCE.
            for peer in peers:
                self.lineage.ensure_relation(source_id, peer)
            summary = self.lineage.assess_independent_support([source_id, *peers])
        else:
            summary = {
                "source_count": 1,
                "known_independent_lineages": 0,
                "unknown_pairs": 0,
                "shared_lineage_pairs": 0,
            }
        summary["default_status"] = IndependenceStatus.UNKNOWN_INDEPENDENCE.value
        with self._lock:
            self._known_sources.add(source_id)
        return summary


# ---------------------------------------------------------------------------
# FreeAPIQualifier — world.free_api_qualification (CE-S03-02)
# ---------------------------------------------------------------------------
class FreeApiState(str, Enum):
    DISCOVERED = "DISCOVERED"
    QUARANTINE = "QUARANTINE"              # unverified / unknown / failed — never trusted
    VERIFIED_FREE_API = "VERIFIED_FREE_API"


@dataclass(frozen=True)
class ApiDiscovery:
    base_url: str
    discovered_via: str = ""       # provenance of the discovery (never an allow)
    advertised_free: bool = False  # a CLAIM from the discovery source — not trusted


@dataclass(frozen=True)
class QualificationStep:
    step: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class FreeApiQualification:
    state: FreeApiState
    base_url: str
    steps: tuple[QualificationStep, ...] = ()
    schema_evidence_id: str | None = None
    source_id: str | None = None
    reasons: tuple[str, ...] = ()

    @property
    def is_verified(self) -> bool:
        return self.state is FreeApiState.VERIFIED_FREE_API


@dataclass(frozen=True)
class ProbeResponse:
    status: int          # 0 = transport/probe error
    body: bytes = b""
    error: str = ""


class FreeAPIQualifier:
    """DISCOVERED -> HTTPS -> auth -> bounded health probe -> schema -> VERIFIED.

    An advertised-free claim from any discovery source is treated as DATA, not
    authorization. Every step must OBSERVE success; the first unknown/failed
    step lands the host in QUARANTINE and nothing is registered anywhere:
    'unqualified_api_dispatch' and 'discovered_host -> automatic_egress_allow'
    stay forbidden.
    """

    def __init__(
        self,
        *,
        writer,
        source_store: SourceStore,
        policy: SourcePolicy,
        prober: Callable[[str], ProbeResponse] | None = None,
        auth_probe_path: str = "/",
        health_probe_path: str = "/",
        schema_path: str = "/openapi.json",
        max_probe_bytes: int = 65_536,
    ) -> None:
        self.writer = writer
        self.source_store = source_store
        self.policy = policy
        self._prober = prober or self._default_prober
        self._auth_path = auth_probe_path
        self._health_path = health_probe_path
        self._schema_path = schema_path
        self._max_probe_bytes = int(max_probe_bytes)

    @staticmethod
    def _default_prober(url: str) -> ProbeResponse:
        from scp.core.url_fetcher import _safe_fetch_url

        try:
            return ProbeResponse(200, _safe_fetch_url(url, max_bytes=65_536, timeout=8.0))
        except Exception as exc:
            return ProbeResponse(0, b"", f"{type(exc).__name__}:{str(exc)[:160]}")

    # ------------------------------------------------------------------
    def qualify(self, discovery: ApiDiscovery) -> FreeApiQualification:
        steps: list[QualificationStep] = []
        reasons: list[str] = []

        def quarantine(reason: str, step: str, detail: str) -> FreeApiQualification:
            steps.append(QualificationStep(step, False, detail))
            reasons.append(reason)
            return FreeApiQualification(
                state=FreeApiState.QUARANTINE,
                base_url=str(discovery.base_url),
                steps=tuple(steps),
                reasons=tuple(reasons + ["unverified_host_never_auto_trusted"]),
            )

        # Step 0: base URL identity (canonical, https-only checked below).
        try:
            canonical = canonicalize_url(discovery.base_url)
        except ValueError as exc:
            return quarantine(f"invalid_base_url:{exc}", "IDENTITY", str(exc))
        parts = urlsplit(canonical)
        if parts.scheme != "https" or not parts.hostname:
            return quarantine("https_required", "HTTPS_CHECK", f"scheme={parts.scheme!r}")
        host = parts.hostname
        steps.append(QualificationStep("HTTPS_CHECK", True, f"https://{host}"))

        # Step 1: auth/payment check — a probe that demands payment, requires
        # unverifiable credentials, or fails outright is NOT proven free.
        auth = self._prober(canonical.rstrip("/") + self._auth_path)
        if auth.status in range(200, 300):
            steps.append(QualificationStep("AUTH_CHECK", True, f"status={auth.status}"))
        elif auth.status == 402:
            return quarantine("payment_required", "AUTH_CHECK", "status=402")
        elif auth.status in {401, 403}:
            return quarantine(
                "auth_required_cannot_prove_free", "AUTH_CHECK", f"status={auth.status}"
            )
        else:
            return quarantine(
                "auth_probe_failed", "AUTH_CHECK", auth.error or f"status={auth.status}"
            )

        # Step 2: bounded health probe.
        health = self._prober(canonical.rstrip("/") + self._health_path)
        if health.status in range(200, 300) and health.body:
            steps.append(
                QualificationStep("HEALTH_PROBE", True, f"status={health.status} bytes={len(health.body)}")
            )
        else:
            return quarantine(
                "health_probe_failed",
                "HEALTH_PROBE",
                health.error or f"status={health.status} bytes={len(health.body)}",
            )

        # Step 3: schema observation — must be a parseable JSON object.
        schema = self._prober(canonical.rstrip("/") + self._schema_path)
        if schema.status not in range(200, 300) or not schema.body:
            return quarantine(
                "schema_unobservable",
                "SCHEMA_OBSERVATION",
                schema.error or f"status={schema.status}",
            )
        try:
            parsed = json.loads(schema.body.decode("utf-8", errors="strict"))
            if not isinstance(parsed, dict):
                raise ValueError("schema root is not a JSON object")
        except (ValueError, UnicodeDecodeError) as exc:
            return quarantine("schema_unobservable", "SCHEMA_OBSERVATION", str(exc)[:160])
        steps.append(
            QualificationStep("SCHEMA_OBSERVATION", True, f"paths={len(parsed.get('paths') or {})}")
        )

        # Step 4: register identity + immutable schema evidence.
        try:
            source = self.source_store.register(
                kind=SourceKind.API_ENDPOINT,
                identity=canonical,
                metadata={
                    "host": host,
                    "discovered_via": str(discovery.discovered_via or ""),
                    "advertised_free": bool(discovery.advertised_free),
                    "qualifier": "FreeAPIQualifier",
                },
            )
            record = self.writer.observe(
                kind="HTTP_RESPONSE",
                content=schema.body[: self._max_probe_bytes],
                collector_id=COLLECTOR_ID,
                collector_version=COLLECTOR_VERSION,
                source_id=source.source_id,
                data_class=DataClass.PUBLIC,
                metadata={
                    "observation_type": "free_api_schema_observation",
                    "base_url_canonical": canonical,
                    "host": host,
                    "qualification_steps": [f"{s.step}:{'OK' if s.ok else 'FAIL'}" for s in steps],
                    "discovered_via": str(discovery.discovered_via or ""),
                },
                mime_type="application/json",
            )
        except Exception as exc:
            return quarantine(f"qualification_storage_failed:{exc}", "EVIDENCE", str(exc)[:160])

        # Step 5: ONLY NOW does the host enter the policy allowlist, with
        # provenance. Until this line the host was never trusted.
        self.policy.register_qualified_api(
            host, base_url=canonical, evidence_id=record["evidence_id"]
        )
        steps.append(QualificationStep("POLICY_REGISTRATION", True, f"host={host}"))
        return FreeApiQualification(
            state=FreeApiState.VERIFIED_FREE_API,
            base_url=canonical,
            steps=tuple(steps),
            schema_evidence_id=record["evidence_id"],
            source_id=source.source_id,
            reasons=("all_observed_steps_succeeded", f"policy_allows_{host}_as_qualified_free_api"),
        )


__all__ = [
    "ABSOLUTE_MAX_FETCH_BYTES",
    "AcquisitionBudget",
    "AcquisitionPipeline",
    "AcquisitionRequest",
    "AcquisitionResult",
    "AcquisitionScheduler",
    "AcquisitionStatus",
    "AcquisitionTrigger",
    "ApiDiscovery",
    "BudgetReservation",
    "COLLECTOR_ID",
    "COLLECTOR_VERSION",
    "FreeAPIQualifier",
    "FreeApiQualification",
    "FreeApiState",
    "PolicyDecision",
    "ProbeResponse",
    "QualificationStep",
    "ScheduleDecision",
    "SourcePolicy",
]
