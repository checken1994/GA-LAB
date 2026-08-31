'\nSCP - Viet Nam | Self-Correcting Pipeline\nCopyright (c) 2026 SCP Vietnam Project. All Rights Reserved.\n\n\n\n\nLicense: See LICENSE file\nContact: scp-vietnam@example.com\n'

from __future__ import annotations

'\nSCP V34 — WHY Engine.\n\nNeo hỏi "Tại sao?" → WHY Engine biến câu hỏi thành quy trình kiểm chứng.\n\nNhiệm vụ của WHY Engine KHÔNG phải trả lời "Tại sao?", mà là:\n    1. Câu hỏi này đang hỏi về đối tượng nào?          (target_identification)\n    2. Muốn trả lời cần loại bằng chứng nào?           (evidence_type_selection)\n    3. Điều gì sẽ được coi là chứng minh?              (proof_criteria)\n    4. Điều gì có thể bác bỏ câu trả lời?              (falsification_criteria)\n\nWHY Engine output = VerificationPlan (không phải answer).\n\nVí dụ:\n    Neo: "Tại sao giá bitcoin hiện tại là $62000?"\n    WHY Engine tạo VerificationPlan:\n        target: bitcoin_price_usd\n        evidence_type: real_time_market_data\n        proof_criteria: ≥3 exchange APIs agree within 2%\n        falsification_criteria: any exchange reports price differing >10%\n        verification_strategy: multi_source_median\n        sources_to_query: [Binance, Coinbase, Kraken, Bitstamp, KuCoin]\n\nSau đó RealityJudge thực thi plan → verdict.\n'

import json

import logging

import os

import re

import sys

import time

from dataclasses import dataclass

from datetime import datetime

from typing import Any

logger = logging.getLogger('scp.why_engine')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, SCRIPT_DIR)

from scp.core.db_manager import db_exec, db_query_all, db_query_one, init_db

from scp.meta.why_sources.crypto import query_crypto as _why_query_crypto

from scp.meta.why_sources.frankfurter import query_frankfurter as _why_query_frankfurter

from scp.meta.why_sources.nasa import query_nasa as _why_query_nasa

from scp.meta.why_sources.open_meteo import query_open_meteo as _why_query_open_meteo

from scp.meta.why_sources.pubchem import query_pubchem as _why_query_pubchem

from scp.meta.why_sources.rest_countries import query_rest_countries as _why_query_rest_countries

from scp.meta.why_sources.wikidata import query_wikidata as _why_query_wikidata

from scp.meta.why_sources.wikipedia import query_wikipedia as _why_query_wikipedia

_METAWHY_MONITOR_SINGLETON = None

_METAWHY_MONITOR_LOCK = __import__('threading').Lock()

def _get_metawhy_monitor():
    """Lazy singleton for MetaWhyMonitor. Returns None if init failed."""
    global _METAWHY_MONITOR_SINGLETON
    if _METAWHY_MONITOR_SINGLETON is None:
        with _METAWHY_MONITOR_LOCK:
            if _METAWHY_MONITOR_SINGLETON is None:
                try:
                    from scp.meta.metawhy_monitor import MetaWhyMonitor
                    _data_dir = os.environ.get('SCP_DATA_DIR', 'data')
                    _METAWHY_MONITOR_SINGLETON = MetaWhyMonitor(data_dir=_data_dir)
                    logger.info('[V5.3-WIRE] MetaWhyMonitor initialized — WHY patterns will be recorded passively')
                except Exception as e:
                    logger.warning(f'[V5.3-WIRE] MetaWhyMonitor init failed: {e} — monitoring disabled')
                    _METAWHY_MONITOR_SINGLETON = False
    return _METAWHY_MONITOR_SINGLETON if _METAWHY_MONITOR_SINGLETON is not False else None

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

@dataclass
class VerificationPlan:
    """Plan sinh ra bởi WHY Engine."""
    question: str
    target: str
    target_type: str
    evidence_type: str
    proof_criteria: str
    falsification_criteria: str
    verification_strategy: str
    sources_to_query: list[str]
    expected_answer_type: str
    confidence_threshold: float
    reasoning: str

def main():
    """[Task 8-A] CLI delegate — implementation in scp.meta.why_engine_cli."""
    from scp.meta.why_engine_cli import main as _cli_main
    return _cli_main()

if __name__ == '__main__':
    main()

from .why_engine_parts.whyengine import WhyEngine
