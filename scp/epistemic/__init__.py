"""Epistemic foundation (26-P0.05+): evidence store, source identity, lineage."""
from scp.epistemic.evidence_store import EvidenceStore, EvidenceIntegrityError, EVIDENCE_KINDS
from scp.epistemic.runtime_bridge import (
    EpistemicStack,
    RuntimeEvidenceBridge,
    build_epistemic_stack,
    get_runtime_bridge,
    reset_runtime_bridge,
)

__all__ = [
    "EvidenceStore",
    "EvidenceIntegrityError",
    "EVIDENCE_KINDS",
    "EpistemicStack",
    "RuntimeEvidenceBridge",
    "build_epistemic_stack",
    "get_runtime_bridge",
    "reset_runtime_bridge",
]
