from fastapi import APIRouter
from pydantic import BaseModel
import os
import json
from pathlib import Path

from scp.self_model.capability_map import CapabilityMap
from scp.epistemic.evidence_store import EvidenceStore

audit_router = APIRouter(tags=["Audit Engine"])
capability_router = APIRouter(tags=["Self Model"])

@audit_router.get("/v106/audit/reports")
def get_audit_reports():
    '''Reads legacy audit reports from R8 and R9'''
    results = {}
    for r_dir in ['audit_r8', 'audit_r9']:
        dpath = os.path.join("scp", r_dir)
        if os.path.exists(dpath):
            results[r_dir] = os.listdir(dpath)
    return {"status": "Audit engine active", "available_reports": results}

@capability_router.get("/v106/capabilities/{cap_id}")
def get_capability(cap_id: str):
    '''Recomputes capability maturity on the fly'''
    _ROOT = Path(__file__).resolve().parent.parent.parent.parent
    _FOUNDATION = _ROOT / "data" / "foundation"
    
    os.makedirs(_FOUNDATION, exist_ok=True)
    os.makedirs(_FOUNDATION / "evidence_objects", exist_ok=True)
    if not os.path.exists(_FOUNDATION / "governance.sqlite"):
        open(_FOUNDATION / "governance.sqlite", 'a').close()
        
    _EVIDENCE_STORE = EvidenceStore(_FOUNDATION / "epistemic.sqlite", _FOUNDATION / "evidence_objects")
    
    cmap = CapabilityMap(
        governance_db_path=_FOUNDATION / "governance.sqlite",
        evidence_store=_EVIDENCE_STORE,
        reference_path=_ROOT / "spec" / "complete_scp_reference.yaml",
        bindings_path=_ROOT / "spec" / "implementation_bindings.yaml"
    )
    res = cmap.recompute_capability(cap_id, tested_sha="HEAD")
    cmap.db.close()
    return res
