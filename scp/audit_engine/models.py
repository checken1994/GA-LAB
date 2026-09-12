import enum
from dataclasses import dataclass
from typing import List

class OracleVerdict(enum.Enum):
    NOT_FALSIFIED = "NOT_FALSIFIED"
    FALSIFIED = "FALSIFIED"
    INVALID_TEST_SETUP = "INVALID_TEST_SETUP"
    INCONCLUSIVE = "INCONCLUSIVE"
    OBSERVABILITY_INSUFFICIENT = "OBSERVABILITY_INSUFFICIENT"
    CONTAMINATED = "CONTAMINATED"

@dataclass(frozen=True)
class AuditChallenge:
    challenge_id: str
    required_profile: str
    target_contract_hash: str

@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    verdict: OracleVerdict
    challenge_id: str
    observer_coverage_hash: str

@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    challenge: AuditChallenge
    records: List[EvidenceRecord]

@dataclass(frozen=True)
class PromotionDecision:
    promoted: bool
    reason: str
    bundle_id: str
