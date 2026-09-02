import dataclasses
from typing import List, Optional

@dataclasses.dataclass
class MissingPieceFinding:
    blind_spot: str
    affected_coverage: str
    evidence_refs: List[str]

class EpistemicBoundary:
    def __init__(self):
        self.findings: List[MissingPieceFinding] = []
        self.verdict: Optional[str] = None
        self.known_independent_lineages = 0

    def evaluate_lineage(self, source_a_lineage: str, source_b_lineage: str) -> None:
        if source_a_lineage != source_b_lineage:
            self.known_independent_lineages = 2
        else:
            self.known_independent_lineages = 1
            self.verdict = "UNVERIFIED"

    def record_contradiction(self, finding: MissingPieceFinding) -> None:
        self.verdict = "CONTRADICTED"
        self.findings.append(finding)

    def is_support_condition_satisfied(self) -> bool:
        return self.known_independent_lineages >= 2
