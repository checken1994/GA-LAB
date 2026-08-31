# Auto-extracted from why_engine.py
from __future__ import annotations
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from scp.core.db_manager import db_exec, db_query_all, db_query_one, init_db
from scp.meta.why_sources.crypto import query_crypto as _why_query_crypto
from scp.meta.why_sources.frankfurter import query_frankfurter as _why_query_frankfurter
from scp.meta.why_sources.nasa import query_nasa as _why_query_nasa
from scp.meta.why_sources.open_meteo import query_open_meteo as _why_query_open_meteo
from scp.meta.why_sources.pubchem import query_pubchem as _why_query_pubchem
from scp.meta.why_sources.rest_countries import query_rest_countries as _why_query_rest_countries
from scp.meta.why_sources.wikidata import query_wikidata as _why_query_wikidata
from scp.meta.why_sources.wikipedia import query_wikipedia as _why_query_wikipedia

def init_why_db():
    """Tạo WHY Engine tables."""
    db_exec("\n        CREATE TABLE IF NOT EXISTS why_verification_plans (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            timestamp TEXT NOT NULL,\n            question TEXT NOT NULL,\n            target TEXT,\n            evidence_type TEXT,\n            proof_criteria TEXT,\n            falsification_criteria TEXT,\n            verification_strategy TEXT,\n            sources_to_query TEXT,\n            status TEXT DEFAULT 'pending',\n            verdict TEXT,\n            executed_at TEXT,\n            claimed_by TEXT,\n            claimed_at REAL\n        )\n    ")
    db_exec('CREATE INDEX IF NOT EXISTS idx_why_status ON why_verification_plans(status)')
    try:
        db_exec('ALTER TABLE why_verification_plans ADD COLUMN claimed_by TEXT')
    except Exception as e:
        logger.debug(f'[why_engine.py:130] silenced: {e}')
    try:
        db_exec('ALTER TABLE why_verification_plans ADD COLUMN claimed_at REAL')
    except Exception:
        pass
    db_exec('CREATE INDEX IF NOT EXISTS idx_why_claimed ON why_verification_plans(claimed_by)')
