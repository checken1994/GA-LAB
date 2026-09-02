import sqlite3
import json
from pathlib import Path
import uuid
from typing import Dict, Any, List

from scp.contracts.time import now_utc_iso

class LearningDB:
    """
    Manages the data/cognitive/learning.sqlite database.
    Stores open_questions, missing_pieces, hypotheses, experiments, lessons.
    Append-only principle for all historical truth logs.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS open_questions (
                    question_id TEXT PRIMARY KEY,
                    title TEXT,
                    question TEXT,
                    scope_json TEXT,
                    trigger TEXT,
                    related_claim_refs_json TEXT,
                    related_knowledge_refs_json TEXT,
                    known_evidence_refs_json TEXT,
                    needed_observations_json TEXT,
                    needed_capabilities_json TEXT,
                    status TEXT,
                    created_at TEXT
                );
                
                CREATE TABLE IF NOT EXISTS missing_pieces (
                    missing_piece_id TEXT PRIMARY KEY,
                    question_id TEXT NOT NULL,
                    kind TEXT,
                    description TEXT,
                    blocks_claims_json TEXT,
                    blocks_decisions_json TEXT,
                    needed_evidence_json TEXT,
                    discovered_by TEXT,
                    created_at TEXT
                );
                
                CREATE TABLE IF NOT EXISTS hypotheses (
                    hypothesis_id TEXT PRIMARY KEY,
                    question_ref TEXT NOT NULL,
                    hypothesis TEXT,
                    mechanism TEXT,
                    predictions_json TEXT,
                    assumptions_json TEXT,
                    needed_capabilities_json TEXT,
                    status TEXT,
                    created_at TEXT
                );
            """)

    def execute_insert(self, table: str, data: Dict[str, Any]):
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        values = tuple(data.values())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", values)
