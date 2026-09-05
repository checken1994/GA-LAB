from __future__ import annotations

import ast
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "scp/knowledge/knowledge_runtime.py"
CONTRACT = ROOT / "scp/knowledge/promotion_contract.py"
RUNTIME_TEST = ROOT / "tests/T02_contract/test_knowledge_runtime.py"
AUTHORITY = ROOT / "scp/knowledge/promotion_authority.py"
AUTHORITY_TEST = ROOT / "tests/T02_contract/test_knowledge_runtime_authority.py"
PROMOTION_TEST = ROOT / "tests/T02_contract/test_knowledge_promotion.py"


def _dedent(value: str) -> str:
    return textwrap.dedent(value).strip("\n") + "\n"


def replace_method(text: str, class_name: str, method_name: str, replacement: str) -> str:
    tree = ast.parse(text)
    target = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                    target = child
                    break
    if target is None:
        raise RuntimeError(f"method not found: {class_name}.{method_name}")
    lines = text.splitlines(keepends=True)
    return "".join(lines[: target.lineno - 1]) + _dedent(replacement) + "".join(lines[target.end_lineno :])


def replace_function(text: str, function_name: str, replacement: str) -> str:
    tree = ast.parse(text)
    target = next(
        (node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name),
        None,
    )
    if target is None:
        raise RuntimeError(f"function not found: {function_name}")
    lines = text.splitlines(keepends=True)
    return "".join(lines[: target.lineno - 1]) + _dedent(replacement) + "".join(lines[target.end_lineno :])


def write_authority() -> None:
    AUTHORITY.write_text(_dedent(r'''
        """Derived promotion authority for the S06 Knowledge Runtime.

        M8 must never treat caller counts, opaque ids, model confidence, or an
        arbitrary EvidenceStore row as truth authority.  This adapter derives:
        * evidence existence/integrity from canonical EvidenceStore,
        * independent support from canonical LineageStore,
        * Reality verification from strict, immutable RealityVerifier result
          payloads bound to this exact knowledge id, scope, and input evidence.

        A Reality result is recognized only when it is a TEST_RESULT collected
        by the canonical ``scp-reality-verifier`` collector and its immutable
        payload satisfies ``scp.reality_verification.v1``.  MODEL_RESPONSE and
        caller metadata are never accepted as verification authority.
        """
        from __future__ import annotations

        import json
        from dataclasses import dataclass
        from typing import Sequence

        from scp.contracts.verdicts import Verdict, parse_verdict
        from scp.epistemic.evidence_store import EvidenceIntegrityError, EvidenceStore
        from scp.epistemic.lineage import LineageStore


        class PromotionAuthorityError(RuntimeError):
            """Canonical promotion evidence is missing or invalid (fail closed)."""


        @dataclass(frozen=True)
        class IndependentSupport:
            evidence_refs: tuple[str, ...]
            source_ids: tuple[str, ...]
            known_independent_lineages: int
            unknown_pairs: int
            shared_lineage_pairs: int


        @dataclass(frozen=True)
        class RealityAssessment:
            evidence_id: str
            episode_id: str
            adversarial_check_passed: bool
            counterexample_check_passed: bool
            temporal_stability: bool


        @dataclass(frozen=True)
        class GoldAssessment:
            episode_ids: tuple[str, ...]
            repeated_verification: bool
            adversarial_check_passed: bool
            counterexample_check_passed: bool
            temporal_stability: bool


        class PromotionAuthority:
            """Read-only derivation layer over canonical epistemic authorities."""

            REALITY_SCHEMA = "scp.reality_verification.v1"
            REALITY_COLLECTOR = "scp-reality-verifier"

            def __init__(self, evidence_store: EvidenceStore, lineage_store: LineageStore) -> None:
                self.evidence_store = evidence_store
                self.lineage_store = lineage_store

            @staticmethod
            def _refs(refs: Sequence[str]) -> list[str]:
                return list(dict.fromkeys(str(ref).strip() for ref in refs if str(ref).strip()))

            def _load(self, refs: Sequence[str]) -> list[dict]:
                normalized = self._refs(refs)
                if not normalized:
                    raise PromotionAuthorityError("at least one canonical evidence ref is required")
                records: list[dict] = []
                for ref in normalized:
                    try:
                        records.append(self.evidence_store.get(ref))
                    except (KeyError, EvidenceIntegrityError) as exc:
                        raise PromotionAuthorityError(
                            f"evidence ref {ref!r} is missing or failed EvidenceStore integrity"
                        ) from exc
                return records

            def require_support(self, refs: Sequence[str]) -> tuple[dict, ...]:
                """Every support occurrence must exist and pass canonical integrity."""
                return tuple(self._load(refs))

            def assess_independent_support(self, refs: Sequence[str]) -> IndependentSupport:
                records = self._load(refs)
                source_ids: list[str] = []
                for record in records:
                    source_id = str(record.get("source_id") or "").strip()
                    if not source_id:
                        raise PromotionAuthorityError(
                            f"evidence {record['evidence_id']} has no source_id; independence is UNKNOWN"
                        )
                    source_ids.append(source_id)
                assessment = self.lineage_store.assess_independent_support(source_ids)
                return IndependentSupport(
                    evidence_refs=tuple(record["evidence_id"] for record in records),
                    source_ids=tuple(sorted(set(source_ids))),
                    known_independent_lineages=int(assessment["known_independent_lineages"]),
                    unknown_pairs=int(assessment["unknown_pairs"]),
                    shared_lineage_pairs=int(assessment["shared_lineage_pairs"]),
                )

            def _parse_reality(
                self,
                record: dict,
                *,
                knowledge_id: str,
                scope: dict,
                support_refs: Sequence[str],
            ) -> RealityAssessment:
                if str(record.get("kind") or "").upper() != "TEST_RESULT":
                    raise PromotionAuthorityError(
                        f"evidence {record['evidence_id']} is not TEST_RESULT Reality evidence"
                    )
                if str(record.get("collector_id") or "") != self.REALITY_COLLECTOR:
                    raise PromotionAuthorityError(
                        f"evidence {record['evidence_id']} was not produced by canonical RealityVerifier"
                    )
                try:
                    payload = json.loads(self.evidence_store.read_content(record["evidence_id"]).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
                    raise PromotionAuthorityError("Reality evidence payload is not canonical JSON") from exc
                if not isinstance(payload, dict) or payload.get("schema") != self.REALITY_SCHEMA:
                    raise PromotionAuthorityError("Reality evidence schema is not recognized")
                if str(payload.get("knowledge_id") or "") != str(knowledge_id):
                    raise PromotionAuthorityError("Reality evidence is bound to a different knowledge_id")
                if payload.get("knowledge_scope") != scope:
                    raise PromotionAuthorityError("Reality evidence scope does not match knowledge scope")
                try:
                    verdict = parse_verdict(payload.get("verdict"))
                except ValueError as exc:
                    raise PromotionAuthorityError("Reality evidence verdict is invalid") from exc
                if verdict is not Verdict.VERIFIED:
                    raise PromotionAuthorityError(f"Reality verdict is {verdict.value}, not VERIFIED")
                if payload.get("temporal_validity") is not True:
                    raise PromotionAuthorityError("Reality evidence did not establish temporal_validity")
                postconditions = payload.get("postconditions")
                if not isinstance(postconditions, list) or not postconditions:
                    raise PromotionAuthorityError("Reality evidence has no independently checked postconditions")
                if any(not isinstance(item, dict) or item.get("passed") is not True for item in postconditions):
                    raise PromotionAuthorityError("Reality evidence contains an unpassed postcondition")

                inputs = self._refs(payload.get("input_evidence_refs") or [])
                allowed = set(self._refs(support_refs))
                if not inputs or not set(inputs).issubset(allowed):
                    raise PromotionAuthorityError(
                        "Reality evidence is not bound to the canonical support evidence for this knowledge"
                    )
                self.require_support(inputs)

                episode_id = str(payload.get("episode_id") or record.get("attempt_id") or "").strip()
                if not episode_id:
                    raise PromotionAuthorityError("Reality evidence lacks a durable episode_id")
                return RealityAssessment(
                    evidence_id=str(record["evidence_id"]),
                    episode_id=episode_id,
                    adversarial_check_passed=payload.get("adversarial_check") is True,
                    counterexample_check_passed=payload.get("counterexample_check") is True,
                    temporal_stability=payload.get("temporal_stability") is True,
                )

            def require_verification(
                self,
                refs: Sequence[str],
                *,
                knowledge_id: str,
                scope: dict,
                support_refs: Sequence[str],
            ) -> tuple[RealityAssessment, ...]:
                records = self._load(refs)
                return tuple(
                    self._parse_reality(
                        record,
                        knowledge_id=knowledge_id,
                        scope=scope,
                        support_refs=support_refs,
                    )
                    for record in records
                )

            def assess_gold(
                self,
                refs: Sequence[str],
                *,
                knowledge_id: str,
                scope: dict,
                support_refs: Sequence[str],
                min_episodes: int,
            ) -> GoldAssessment:
                assessments = self.require_verification(
                    refs,
                    knowledge_id=knowledge_id,
                    scope=scope,
                    support_refs=support_refs,
                )
                episodes = tuple(sorted({item.episode_id for item in assessments}))
                return GoldAssessment(
                    episode_ids=episodes,
                    repeated_verification=len(episodes) >= int(min_episodes),
                    adversarial_check_passed=bool(assessments)
                    and all(item.adversarial_check_passed for item in assessments),
                    counterexample_check_passed=bool(assessments)
                    and all(item.counterexample_check_passed for item in assessments),
                    temporal_stability=bool(assessments)
                    and all(item.temporal_stability for item in assessments),
                )
    '''), encoding="utf-8")


def patch_contract() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    if "counterexample_check_passed: bool = False" not in text:
        text = text.replace(
            "    adversarial_check_passed: bool = False\n    revalidation_failed: bool = False",
            "    adversarial_check_passed: bool = False\n    counterexample_check_passed: bool = False\n    revalidation_failed: bool = False",
            1,
        )
    if 'missing.append("counterexample_check_passed")' not in text:
        text = text.replace(
            '        if not ctx.adversarial_check_passed:\n            missing.append("adversarial_check_passed")\n        if not ctx.provenance_present:',
            '        if not ctx.adversarial_check_passed:\n            missing.append("adversarial_check_passed")\n        if not ctx.counterexample_check_passed:\n            missing.append("counterexample_check_passed")\n        if not ctx.provenance_present:',
            1,
        )
    ast.parse(text)
    CONTRACT.write_text(text, encoding="utf-8")


def patch_runtime() -> None:
    text = RUNTIME.read_text(encoding="utf-8")
    import_marker = ")\n\n# Promotable ladder in strict order; GOLD is the top of the ladder."
    imports = (
        ")\nfrom scp.knowledge.promotion_authority import PromotionAuthority, PromotionAuthorityError\n"
        "from scp.knowledge.promotion_contract import DecisionAction, PromotionContext, evaluate_promotion\n\n"
        "# Promotable ladder in strict order; GOLD is the top of the ladder."
    )
    if "from scp.knowledge.promotion_authority import" not in text:
        if import_marker not in text:
            raise RuntimeError("runtime import marker not found")
        text = text.replace(import_marker, imports, 1)

    schema_start = text.index("-- CE-S06-01 must_not direct_status_mutation")
    schema_end = text.index("-- CE-S06-02 must_not history_overwrite")
    guard = _dedent(r'''
        -- CE-S06-01 must_not direct_status_mutation.  Audit history is never
        -- write authority: a status-changing UPDATE needs a connection-scoped,
        -- operation-scoped capability that exists only inside transition().
        DROP TRIGGER IF EXISTS trg_kobjects_no_direct_status_mutation;
        CREATE TRIGGER trg_kobjects_no_direct_status_mutation
        BEFORE UPDATE ON knowledge_objects
        WHEN OLD.status <> NEW.status
        BEGIN
            SELECT CASE
                WHEN scp_transition_authorized(NEW.knowledge_id, OLD.status, NEW.status) = 1 THEN NULL
                ELSE RAISE(ABORT, 'direct status mutation forbidden: use GoldLifecycle (CE-S06-01)')
            END;
        END;

        -- New authority rows enter at RAW.  This also closes INSERT OR REPLACE
        -- as a way to import a pre-promoted VERIFIED/GOLD object.
        CREATE TRIGGER IF NOT EXISTS trg_kobjects_raw_insert_only
        BEFORE INSERT ON knowledge_objects
        WHEN NEW.status <> 'RAW'
        BEGIN
            SELECT RAISE(ABORT, 'non-RAW knowledge insert forbidden: use GoldLifecycle');
        END;

    ''')
    text = text[:schema_start] + guard + text[schema_end:]

    text = replace_method(text, "KnowledgeStore", "__init__", r'''
        def __init__(self, db_path: str | Path) -> None:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._active_transition: tuple[str, str, str] | None = None
            self._conn.create_function(
                "scp_transition_authorized",
                3,
                lambda knowledge_id, from_status, to_status: int(
                    self._active_transition
                    == (str(knowledge_id), str(from_status), str(to_status))
                ),
            )
            self._conn.executescript(_SCHEMA)
            self._index: "RetrievalIndex | None" = None
            self._conn.commit()
    ''')

    text = replace_method(text, "KnowledgeStore", "transition", r'''
        def transition(
            self,
            obj: KnowledgeObject,
            to_status: str | KnowledgeStatus,
            *,
            decision: str,
            reason_codes: Sequence[str],
            evidence_refs: Sequence[str] = (),
            actor: str = "system",
        ) -> LifecycleResult:
            """Persist one ontology-valid transition with non-replayable authority."""
            from_status = parse_status_value(obj.status)
            target = parse_status_value(to_status)
            try:
                validate_transition(from_status, target)
            except ValueError as exc:
                raise KnowledgeTransitionRejected(
                    f"transition {from_status} -> {target} rejected by ontology: {exc}",
                    reason_codes=["INVALID_TRANSITION"],
                ) from exc
            obj.status = target
            obj.updated_at = now_utc_iso()
            try:
                validate_object(obj)
            except ValueError as exc:
                obj.status = from_status
                raise KnowledgeTransitionRejected(
                    f"transition {from_status} -> {target} rejected by ontology validation: {exc}",
                    reason_codes=["ONTOLOGY_VALIDATION_FAILED"],
                ) from exc

            refs = [str(ref) for ref in evidence_refs]
            event_id = new_id("kse")
            ts = obj.updated_at
            try:
                self._conn.execute(
                    """
                    INSERT INTO knowledge_status_events (
                        event_id, knowledge_id, from_status, to_status, decision,
                        reason_codes_json, evidence_refs_json, actor, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        obj.knowledge_id,
                        from_status,
                        target,
                        decision,
                        json.dumps(list(reason_codes), ensure_ascii=False),
                        json.dumps(refs, ensure_ascii=False),
                        actor,
                        ts,
                    ),
                )
                self._active_transition = (obj.knowledge_id, from_status, target)
                try:
                    self._persist(obj)
                finally:
                    self._active_transition = None
                self._conn.commit()
            except Exception:
                self._active_transition = None
                self._conn.rollback()
                obj.status = from_status
                raise
            return LifecycleResult(
                knowledge_id=obj.knowledge_id,
                action=decision,
                from_status=from_status,
                to_status=target,
                reason_codes=list(reason_codes),
                evidence_refs=refs,
                event_id=event_id,
                timestamp=ts,
            )
    ''')

    text = replace_method(text, "KnowledgeStore", "_persist", r'''
        def _persist(self, obj: KnowledgeObject) -> None:
            validity = obj.validity if isinstance(obj.validity, dict) else {}
            row = (
                obj.knowledge_id,
                parse_type_value(obj.type),
                parse_status_value(obj.status),
                obj.title,
                parse_data_class_value(obj.data_class),
                to_payload_json(obj),
                int(obj.independent_lineages),
                len(obj.evidence_refs),
                validity.get("volatility"),
                validity.get("last_validated_at"),
                validity.get("review_after"),
                obj.created_at,
                obj.updated_at,
            )
            exists = self._conn.execute(
                "SELECT 1 FROM knowledge_objects WHERE knowledge_id = ?",
                (obj.knowledge_id,),
            ).fetchone()
            if exists is None:
                self._conn.execute(
                    """
                    INSERT INTO knowledge_objects (
                        knowledge_id, type, status, title, data_class, payload_json,
                        independent_lineages, evidence_count, volatility,
                        last_validated_at, review_after, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
            else:
                self._conn.execute(
                    """
                    UPDATE knowledge_objects SET
                        type=?, status=?, title=?, data_class=?, payload_json=?,
                        independent_lineages=?, evidence_count=?, volatility=?,
                        last_validated_at=?, review_after=?, created_at=?, updated_at=?
                    WHERE knowledge_id=?
                    """,
                    row[1:] + (obj.knowledge_id,),
                )
            if self._index is not None:
                self._index.sync_object(obj)
    ''')

    text = replace_method(text, "GoldLifecycle", "__init__", r'''
        def __init__(
            self,
            store: KnowledgeStore,
            *,
            min_independent_lineages: int = 2,
            min_success_observations: int = 2,
            gold_review_after_seconds: int = 90 * 86400,
            actor: str = "gold_lifecycle",
            promotion_authority: PromotionAuthority | None = None,
        ) -> None:
            self.store = store
            self.min_independent_lineages = int(min_independent_lineages)
            self.min_success_observations = int(min_success_observations)
            self.gold_review_after_seconds = int(gold_review_after_seconds)
            self.actor = actor
            self.promotion_authority = promotion_authority
    ''')

    text = replace_method(text, "GoldLifecycle", "promote", r'''
        def promote(
            self,
            knowledge_id: str,
            *,
            target: str | KnowledgeStatus | None = None,
            evidence_refs: Sequence[str] | None = None,
            verification_evidence_refs: Sequence[str] | None = None,
            independent_lineages: int | None = None,
            success_observations: int | None = None,
            success_evidence_refs: Sequence[str] | None = None,
            actor: str | None = None,
            now: str | datetime | None = None,
        ) -> LifecycleResult:
            """Promote one rung using derived authority, never caller assertions.

            ``independent_lineages`` and ``success_observations`` remain accepted
            for compatibility but intentionally carry zero promotion authority.
            """
            obj = self.store.get(knowledge_id)
            current = parse_status_value(obj.status)
            if target is None:
                if current not in _PROMOTION_LADDER or current == KnowledgeStatus.GOLD.value:
                    raise KnowledgeTransitionRejected(
                        f"no default promotion rung from status {current}; pass target explicitly",
                        reason_codes=["NO_PROMOTION_RUNG"],
                    )
                target_status = _PROMOTION_LADDER[_PROMOTION_LADDER.index(current) + 1]
            else:
                target_status = parse_status_value(target)

            support_refs = list(dict.fromkeys(
                [str(ref) for ref in (obj.validity or {}).get("support_evidence_refs", []) if str(ref).strip()]
                + [str(ref) for ref in (evidence_refs or []) if str(ref).strip()]
            ))
            verify_refs = [str(ref) for ref in (verification_evidence_refs or []) if str(ref).strip()]
            success_refs = [str(ref) for ref in (success_evidence_refs or []) if str(ref).strip()]

            gate = self._gate(
                obj,
                target_status,
                support_refs=support_refs,
                verification_evidence_refs=verify_refs,
                success_evidence_refs=success_refs,
                now=now,
            )
            if gate is not None:
                message, reason_codes, missing = gate
                raise KnowledgeTransitionRejected(
                    f"promotion {current} -> {target_status} REJECTED: {message}",
                    reason_codes=reason_codes,
                    missing_pieces=missing,
                )

            authority = self.promotion_authority
            assert authority is not None
            now_dt = _as_utc_datetime(now)
            for ref in support_refs + verify_refs + success_refs:
                if ref not in obj.evidence_refs:
                    obj.evidence_refs.append(ref)
            obj.validity["support_evidence_refs"] = support_refs

            if support_refs:
                support = authority.assess_independent_support(support_refs)
                obj.independent_lineages = support.known_independent_lineages
                obj.validity["lineage_sources"] = list(support.source_ids)
                obj.validity["lineage_unknown_pairs"] = support.unknown_pairs

            if target_status == KnowledgeStatus.CURATED.value:
                obj.validity["provenance_refs"] = sorted(set(support_refs))
            elif target_status == KnowledgeStatus.VERIFIED.value:
                obj.validity["verification_evidence_refs"] = verify_refs
                obj.validity["last_validated_at"] = _iso(now_dt)
            elif target_status == KnowledgeStatus.GOLD.value:
                gold = authority.assess_gold(
                    success_refs,
                    knowledge_id=obj.knowledge_id,
                    scope=obj.scope,
                    support_refs=support_refs,
                    min_episodes=self.min_success_observations,
                )
                obj.validity["gold_verification_evidence_refs"] = success_refs
                obj.validity["verified_success_episode_ids"] = list(gold.episode_ids)
                obj.validity["repeated_success_observations"] = len(gold.episode_ids)
                seconds = self._gold_review_after_seconds(obj)
                obj.validity["review_after"] = _iso(now_dt + timedelta(seconds=seconds))
                obj.validity["gold_review_after_seconds"] = seconds

            return self.store.transition(
                obj,
                target_status,
                decision="PROMOTE",
                reason_codes=[f"GATE_PASSED_{current}_TO_{target_status}"],
                evidence_refs=obj.evidence_refs,
                actor=actor or self.actor,
            )
    ''')

    text = replace_method(text, "GoldLifecycle", "_gate", r'''
        def _gate(
            self,
            obj: KnowledgeObject,
            target_status: str,
            *,
            support_refs: Sequence[str],
            verification_evidence_refs: Sequence[str],
            success_evidence_refs: Sequence[str],
            now: str | datetime | None,
        ) -> tuple[str, list[str], list[str]] | None:
            """Derive PromotionContext and delegate policy to canonical contract."""
            import copy

            current = parse_status_value(obj.status)
            try:
                validate_transition(current, target_status)
            except ValueError as exc:
                return (str(exc), ["INVALID_TRANSITION"], [str(exc)])

            authority = self.promotion_authority
            if authority is None:
                return (
                    "canonical promotion authority is unavailable",
                    ["PROMOTION_AUTHORITY_MISSING"],
                    ["EvidenceStore + LineageStore + RealityVerifier authority required"],
                )

            derived = copy.deepcopy(obj)
            derived.evidence_refs = list(dict.fromkeys(str(ref) for ref in support_refs if str(ref).strip()))
            ctx = PromotionContext(
                provenance_present=bool(derived.evidence_refs),
                unresolved_material_contradictions=self.store.open_contradiction_count(obj.knowledge_id),
                contradiction_scan_completed=True,
                evidence_count=len(derived.evidence_refs),
            )

            try:
                if derived.evidence_refs:
                    authority.require_support(derived.evidence_refs)
                    support = authority.assess_independent_support(derived.evidence_refs)
                    derived.independent_lineages = support.known_independent_lineages
                    ctx.independent_lineage_count = support.known_independent_lineages
                    ctx.evidence_authority_verified = True

                if target_status == KnowledgeStatus.VERIFIED.value:
                    authority.require_verification(
                        verification_evidence_refs,
                        knowledge_id=obj.knowledge_id,
                        scope=obj.scope,
                        support_refs=derived.evidence_refs,
                    )
                    ctx.reality_verified = True
                    ctx.scope_match = True
                    ctx.evidence_authority_verified = True
                    if not derived.validity:
                        derived.validity = {"promotion_scope": obj.scope}

                if target_status == KnowledgeStatus.GOLD.value:
                    gold = authority.assess_gold(
                        success_evidence_refs,
                        knowledge_id=obj.knowledge_id,
                        scope=obj.scope,
                        support_refs=derived.evidence_refs,
                        min_episodes=self.min_success_observations,
                    )
                    ctx.repeated_verification = gold.repeated_verification
                    ctx.temporal_stability = gold.temporal_stability
                    ctx.adversarial_check_passed = gold.adversarial_check_passed
                    ctx.counterexample_check_passed = gold.counterexample_check_passed
                    ctx.evidence_authority_verified = True
            except PromotionAuthorityError as exc:
                return ("authority requirements not met", ["AUTHORITY_EVIDENCE_REJECTED"], [str(exc)])

            decision = evaluate_promotion(derived, KnowledgeStatus(target_status), ctx)
            if decision.action is DecisionAction.PROMOTE:
                return None
            missing = list(decision.missing_pieces) + list(decision.contradictions)
            return (
                "canonical promotion contract held or blocked the transition",
                [str(code) for code in decision.reason_codes],
                missing,
            )
    ''')

    ast.parse(text)
    RUNTIME.write_text(text, encoding="utf-8")


def patch_runtime_tests() -> None:
    text = RUNTIME_TEST.read_text(encoding="utf-8")
    import_marker = "from scp.knowledge.ontology import KnowledgeObject, KnowledgeStatus\n"
    extras = (
        "from scp.epistemic.evidence_store import EvidenceStore\n"
        "from scp.epistemic.lineage import IndependenceStatus, LineageStore\n"
        "from scp.knowledge.promotion_authority import PromotionAuthority\n"
    )
    if extras not in text:
        text = text.replace(import_marker, import_marker + extras, 1)

    text = replace_function(text, "make_store", r'''
        def make_store(tmp_path) -> tuple[KnowledgeStore, RetrievalIndex, GoldLifecycle, TemporalRevalidation]:
            store = KnowledgeStore(tmp_path / "knowledge_runtime.db")
            index = store.attach_index(RetrievalIndex(store))
            evidence = EvidenceStore(tmp_path / "epistemic.db", tmp_path / "evidence_objects")
            lineage = LineageStore(tmp_path / "epistemic.db")
            lifecycle = GoldLifecycle(store, promotion_authority=PromotionAuthority(evidence, lineage))
            revalidation = TemporalRevalidation(store)
            return store, index, lifecycle, revalidation
    ''')

    text = replace_function(text, "walk_to_gold", r'''
        def _support(lifecycle: GoldLifecycle, knowledge_id: str, source_id: str) -> str:
            authority = lifecycle.promotion_authority
            assert authority is not None
            record = authority.evidence_store.observe(
                kind="RUNTIME_OBSERVATION",
                content=f"support:{knowledge_id}:{source_id}".encode(),
                collector_id="t02-support",
                collector_version="1",
                source_id=source_id,
            )
            return record["evidence_id"]


        def _mark_independent(lifecycle: GoldLifecycle, sources: list[str], refs: list[str]) -> None:
            authority = lifecycle.promotion_authority
            assert authority is not None
            for i, source_a in enumerate(sources):
                for source_b in sources[i + 1:]:
                    authority.lineage_store.record_relation(
                        source_a,
                        source_b,
                        status=IndependenceStatus.INDEPENDENT,
                        basis=[{"type": "independent_runtime_observation"}],
                        evidence_refs=refs,
                    )


        def _reality(
            lifecycle: GoldLifecycle,
            knowledge_id: str,
            *,
            episode_id: str,
            gold_checks: bool = False,
        ) -> str:
            authority = lifecycle.promotion_authority
            assert authority is not None
            obj = lifecycle.store.get(knowledge_id)
            support_refs = list((obj.validity or {}).get("support_evidence_refs", []))
            payload = {
                "schema": "scp.reality_verification.v1",
                "knowledge_id": knowledge_id,
                "knowledge_scope": obj.scope,
                "verdict": "VERIFIED",
                "input_evidence_refs": support_refs,
                "postconditions": [{"name": "claim_postcondition", "passed": True}],
                "episode_id": episode_id,
                "temporal_validity": True,
                "adversarial_check": bool(gold_checks),
                "counterexample_check": bool(gold_checks),
                "temporal_stability": bool(gold_checks),
            }
            import json
            record = authority.evidence_store.observe(
                kind="TEST_RESULT",
                content=json.dumps(payload, sort_keys=True).encode(),
                collector_id="scp-reality-verifier",
                collector_version="1",
                source_id=f"reality:{episode_id}",
                attempt_id=episode_id,
            )
            return record["evidence_id"]


        def walk_to_gold(lifecycle: GoldLifecycle, knowledge_id: str) -> None:
            a = _support(lifecycle, knowledge_id, "source-a")
            lifecycle.promote(knowledge_id, evidence_refs=[a])

            b = _support(lifecycle, knowledge_id, "source-b")
            _mark_independent(lifecycle, ["source-a", "source-b"], [a, b])
            lifecycle.promote(knowledge_id, evidence_refs=[b])

            c = _support(lifecycle, knowledge_id, "source-c")
            _mark_independent(lifecycle, ["source-a", "source-b", "source-c"], [a, b, c])
            verification = _reality(lifecycle, knowledge_id, episode_id="verify-1")
            lifecycle.promote(
                knowledge_id,
                evidence_refs=[c],
                verification_evidence_refs=[verification],
            )

            success_1 = _reality(lifecycle, knowledge_id, episode_id="gold-1", gold_checks=True)
            success_2 = _reality(lifecycle, knowledge_id, episode_id="gold-2", gold_checks=True)
            lifecycle.promote(knowledge_id, success_evidence_refs=[success_1, success_2])
    ''')

    text = replace_function(text, "test_promote_walk_raw_to_gold_all_valid_transitions_pass", r'''
        def test_promote_walk_raw_to_gold_all_valid_transitions_pass(tmp_path):
            store, _, lifecycle, _ = make_store(tmp_path)
            obj = make_fact()
            store.upsert(obj)
            walk_to_gold(lifecycle, obj.knowledge_id)

            gold = store.get(obj.knowledge_id)
            assert gold.status is KnowledgeStatus.GOLD
            assert gold.independent_lineages >= 3
            assert gold.validity["last_validated_at"]
            assert gold.validity["review_after"]
            assert gold.validity["repeated_success_observations"] == 2
            assert len(gold.validity["verified_success_episode_ids"]) == 2
            assert [event["to_status"] for event in store.history(obj.knowledge_id)] == [
                "CURATED", "CORROBORATED", "VERIFIED", "GOLD",
            ]
    ''')

    text = replace_function(text, "test_gold_without_evidence_refs_rejected", r'''
        def test_gold_without_evidence_refs_rejected(tmp_path):
            with pytest.raises(ValueError):
                KnowledgeObject(type="FACT", title="gold", content={"k": "v"}, status="GOLD")

            store, _, _, _ = make_store(tmp_path)
            forged = KnowledgeObject(
                type="FACT",
                title="verified but evidence-less",
                content={"k": "v"},
                status="VERIFIED",
                scope={"domain": "d"},
            )
            with pytest.raises(sqlite3.IntegrityError, match="non-RAW knowledge insert forbidden"):
                store.upsert(forged)
            assert store.find(forged.knowledge_id) is None
    ''')

    text = replace_function(text, "test_corroboration_requires_independent_lineage_threshold", r'''
        def test_corroboration_requires_independent_lineage_threshold(tmp_path):
            store, _, lifecycle, _ = make_store(tmp_path)
            obj = make_fact()
            store.upsert(obj)
            a = _support(lifecycle, obj.knowledge_id, "source-a")
            lifecycle.promote(obj.knowledge_id, evidence_refs=[a])
            b = _support(lifecycle, obj.knowledge_id, "source-b")

            with pytest.raises(KnowledgeTransitionRejected) as excinfo:
                lifecycle.promote(
                    obj.knowledge_id,
                    evidence_refs=[b],
                    independent_lineages=999,
                )
            assert any("independent_lineage" in piece for piece in excinfo.value.missing_pieces)
            assert store.get(obj.knowledge_id).status is KnowledgeStatus.CURATED

            _mark_independent(lifecycle, ["source-a", "source-b"], [a, b])
            result = lifecycle.promote(obj.knowledge_id, evidence_refs=[b])
            assert result.to_status == "CORROBORATED"
            assert store.get(obj.knowledge_id).independent_lineages == 2
    ''')

    text = replace_function(text, "test_curated_with_open_contradiction_cannot_corroborate", r'''
        def test_curated_with_open_contradiction_cannot_corroborate(tmp_path):
            store, _, lifecycle, _ = make_store(tmp_path)
            obj = make_fact()
            store.upsert(obj)
            a = _support(lifecycle, obj.knowledge_id, "source-a")
            lifecycle.promote(obj.knowledge_id, evidence_refs=[a])
            b = _support(lifecycle, obj.knowledge_id, "source-b")
            _mark_independent(lifecycle, ["source-a", "source-b"], [a, b])
            lifecycle.report_contradiction(
                obj.knowledge_id,
                evidence_ref=b,
                description="unit price contradicts other sources",
            )
            with pytest.raises(KnowledgeTransitionRejected) as excinfo:
                lifecycle.promote(obj.knowledge_id, evidence_refs=[b])
            assert any("contradiction" in piece for piece in excinfo.value.missing_pieces)
    ''')

    text = replace_function(text, "test_direct_status_mutation_blocked_at_storage_layer", r'''
        def test_direct_status_mutation_blocked_at_storage_layer(tmp_path):
            store, _, lifecycle, _ = make_store(tmp_path)
            obj = make_fact()
            store.upsert(obj)
            ev = _support(lifecycle, obj.knowledge_id, "source-a")
            lifecycle.promote(obj.knowledge_id, evidence_refs=[ev])

            foreign = sqlite3.connect(store.db_path)
            with pytest.raises(sqlite3.Error):
                foreign.execute(
                    "UPDATE knowledge_objects SET status = 'GOLD' WHERE knowledge_id = ?",
                    (obj.knowledge_id,),
                )
            foreign.close()
            assert store.get(obj.knowledge_id).status is KnowledgeStatus.CURATED
            assert len(store.history(obj.knowledge_id)) == 1
    ''')

    ast.parse(text)
    RUNTIME_TEST.write_text(text, encoding="utf-8")


def patch_promotion_tests() -> None:
    text = PROMOTION_TEST.read_text(encoding="utf-8")
    if "counterexample_check_passed=True" not in text:
        text = text.replace(
            "        temporal_stability=True,\n        adversarial_check_passed=True,\n        provenance_present=True",
            "        temporal_stability=True,\n        adversarial_check_passed=True,\n        counterexample_check_passed=True,\n        provenance_present=True",
            1,
        )
    ast.parse(text)
    PROMOTION_TEST.write_text(text, encoding="utf-8")


def write_adversarial_tests() -> None:
    AUTHORITY_TEST.write_text(_dedent(r'''
        """Issue #37: caller assertions and raw SQL must not mint epistemic maturity."""
        from __future__ import annotations

        import json
        import sqlite3
        from datetime import datetime, timedelta, timezone

        import pytest

        from scp.epistemic.evidence_store import EvidenceStore
        from scp.epistemic.lineage import IndependenceStatus, LineageStore
        from scp.knowledge.knowledge_runtime import (
            GoldLifecycle,
            KnowledgeStore,
            KnowledgeTransitionRejected,
            TemporalRevalidation,
        )
        from scp.knowledge.ontology import KnowledgeObject, KnowledgeStatus
        from scp.knowledge.promotion_authority import PromotionAuthority


        def build(tmp_path):
            store = KnowledgeStore(tmp_path / "knowledge.db")
            evidence = EvidenceStore(tmp_path / "epistemic.db", tmp_path / "objects")
            lineage = LineageStore(tmp_path / "epistemic.db")
            lifecycle = GoldLifecycle(store, promotion_authority=PromotionAuthority(evidence, lineage))
            obj = KnowledgeObject(
                type="FACT",
                title="authority-bound fact",
                content={"subject": "svc", "predicate": "state", "object": "ok"},
                scope={"domain": "issue37"},
            )
            store.upsert(obj)
            return store, evidence, lineage, lifecycle, obj


        def support(evidence, obj, source):
            return evidence.observe(
                kind="RUNTIME_OBSERVATION",
                content=f"support:{source}".encode(),
                collector_id="issue37-support",
                collector_version="1",
                source_id=source,
            )["evidence_id"]


        def reality(evidence, obj, support_refs, episode, *, trusted=True, gold=False):
            payload = {
                "schema": "scp.reality_verification.v1",
                "knowledge_id": obj.knowledge_id,
                "knowledge_scope": obj.scope,
                "verdict": "VERIFIED",
                "input_evidence_refs": support_refs,
                "postconditions": [{"name": "postcondition", "passed": True}],
                "episode_id": episode,
                "temporal_validity": True,
                "adversarial_check": bool(gold),
                "counterexample_check": bool(gold),
                "temporal_stability": bool(gold),
            }
            return evidence.observe(
                kind="TEST_RESULT",
                content=json.dumps(payload, sort_keys=True).encode(),
                collector_id="scp-reality-verifier" if trusted else "caller-self-report",
                collector_version="1",
                source_id=f"verifier:{episode}",
                attempt_id=episode,
            )["evidence_id"]


        def mark_independent(lineage, sources, refs):
            for i, a in enumerate(sources):
                for b in sources[i + 1:]:
                    lineage.record_relation(
                        a,
                        b,
                        status=IndependenceStatus.INDEPENDENT,
                        basis=[{"type": "independent_runtime_observation"}],
                        evidence_refs=refs,
                    )


        def to_corroborated(store, evidence, lineage, lifecycle, obj):
            a = support(evidence, obj, "source-a")
            b = support(evidence, obj, "source-b")
            lifecycle.promote(obj.knowledge_id, evidence_refs=[a])
            mark_independent(lineage, ["source-a", "source-b"], [a, b])
            lifecycle.promote(obj.knowledge_id, evidence_refs=[b])
            return [a, b]


        def to_verified(store, evidence, lineage, lifecycle, obj):
            refs = to_corroborated(store, evidence, lineage, lifecycle, obj)
            c = support(evidence, obj, "source-c")
            refs.append(c)
            mark_independent(lineage, ["source-a", "source-b", "source-c"], refs)
            verification = reality(evidence, obj, refs, "verify-1")
            lifecycle.promote(
                obj.knowledge_id,
                evidence_refs=[c],
                verification_evidence_refs=[verification],
            )
            return refs


        def test_fake_or_nonexistent_evidence_id_cannot_curate(tmp_path):
            store, evidence, lineage, lifecycle, obj = build(tmp_path)
            with pytest.raises(KnowledgeTransitionRejected) as excinfo:
                lifecycle.promote(obj.knowledge_id, evidence_refs=["ev_nonexistent_issue37"])
            assert any("missing or failed EvidenceStore integrity" in item for item in excinfo.value.missing_pieces)
            assert store.get(obj.knowledge_id).status is KnowledgeStatus.RAW


        def test_forged_independent_lineage_scalar_cannot_corroborate(tmp_path):
            store, evidence, lineage, lifecycle, obj = build(tmp_path)
            a = support(evidence, obj, "source-a")
            b = support(evidence, obj, "source-b")
            lifecycle.promote(obj.knowledge_id, evidence_refs=[a])
            with pytest.raises(KnowledgeTransitionRejected):
                lifecycle.promote(obj.knowledge_id, evidence_refs=[b], independent_lineages=999)
            assert store.get(obj.knowledge_id).status is KnowledgeStatus.CURATED


        def test_arbitrary_verification_id_cannot_grant_verified(tmp_path):
            store, evidence, lineage, lifecycle, obj = build(tmp_path)
            refs = to_corroborated(store, evidence, lineage, lifecycle, obj)
            untrusted = reality(evidence, obj, refs, "fake-verifier", trusted=False)
            with pytest.raises(KnowledgeTransitionRejected) as excinfo:
                lifecycle.promote(obj.knowledge_id, verification_evidence_refs=[untrusted])
            assert any("canonical RealityVerifier" in item for item in excinfo.value.missing_pieces)
            assert store.get(obj.knowledge_id).status is KnowledgeStatus.CORROBORATED


        def test_scalar_success_observations_cannot_grant_gold(tmp_path):
            store, evidence, lineage, lifecycle, obj = build(tmp_path)
            to_verified(store, evidence, lineage, lifecycle, obj)
            with pytest.raises(KnowledgeTransitionRejected):
                lifecycle.promote(obj.knowledge_id, success_observations=999999)
            assert store.get(obj.knowledge_id).status is KnowledgeStatus.VERIFIED


        def test_historical_transition_event_cannot_authorize_later_raw_update(tmp_path):
            store, evidence, lineage, lifecycle, obj = build(tmp_path)
            ev = support(evidence, obj, "source-a")
            lifecycle.promote(obj.knowledge_id, evidence_refs=[ev])

            scheduler = TemporalRevalidation(store, review_after_seconds={"STABLE": 1})
            scheduler.assign(
                obj.knowledge_id,
                "STABLE",
                now=datetime.now(timezone.utc) - timedelta(seconds=10),
            )
            assert scheduler.sweep(now=datetime.now(timezone.utc))[0].to_status == "UNDER_REVIEW"
            lifecycle.promote(
                obj.knowledge_id,
                target=KnowledgeStatus.CURATED,
                evidence_refs=[ev],
            )
            assert any(
                event["from_status"] == "CURATED" and event["to_status"] == "UNDER_REVIEW"
                for event in store.history(obj.knowledge_id)
            )

            foreign = sqlite3.connect(store.db_path)
            with pytest.raises(sqlite3.Error):
                foreign.execute(
                    "UPDATE knowledge_objects SET status='UNDER_REVIEW' WHERE knowledge_id=?",
                    (obj.knowledge_id,),
                )
            foreign.close()
            assert store.get(obj.knowledge_id).status is KnowledgeStatus.CURATED


        def test_insert_or_replace_cannot_bypass_lifecycle_authority(tmp_path):
            store, evidence, lineage, lifecycle, obj = build(tmp_path)
            foreign = sqlite3.connect(store.db_path)
            with pytest.raises(sqlite3.IntegrityError, match="non-RAW knowledge insert forbidden"):
                foreign.execute(
                    """
                    INSERT OR REPLACE INTO knowledge_objects (
                        knowledge_id, type, status, title, data_class, payload_json,
                        independent_lineages, evidence_count, volatility,
                        last_validated_at, review_after, created_at, updated_at
                    )
                    SELECT knowledge_id, type, 'GOLD', title, data_class, payload_json,
                           999, 999, volatility, last_validated_at, review_after, created_at, updated_at
                    FROM knowledge_objects WHERE knowledge_id=?
                    """,
                    (obj.knowledge_id,),
                )
            foreign.close()
            assert store.get(obj.knowledge_id).status is KnowledgeStatus.RAW
    '''), encoding="utf-8")


def main() -> None:
    write_authority()
    patch_contract()
    patch_runtime()
    patch_runtime_tests()
    patch_promotion_tests()
    write_adversarial_tests()
    for path in (AUTHORITY, CONTRACT, RUNTIME, RUNTIME_TEST, PROMOTION_TEST, AUTHORITY_TEST):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print("Issue #37 deterministic patch applied; Python syntax validated.")


if __name__ == "__main__":
    main()
